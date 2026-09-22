"""JSON import/export for the Graph Explorer tab's Neo4j graph data (nodes and
relationships only - Postgres is out of scope for this feature).

Import format:
{
  "nodes": [
    {"label": "Supplier", "properties": {"id": "S7", "name": "New Supplier Co", "city": "Austin", "state": "TX"}}
  ],
  "edges": [
    {"source": "RM1", "target": "S7", "type": "SOURCED_FROM",
     "properties": {"cost_per_unit": 1.1, "currency": "USD", "lead_time_days": 14, "is_primary": false}}
  ]
}

`properties.id` (or `properties.contract_id` for a Contract node - see
agent/db.py's id_property_for_label) is the node's unique key. Importing an id that
already exists updates that node's properties rather than creating a duplicate, so
re-running the same file twice is always safe. An edge's `source`/`target` must match
an existing node's id - either already in the graph, or an earlier node in the very
same import.
"""
import json

import streamlit as st

from agent import db
from ui.graph_viz import fetch_full_graph
from ui.sidebar import _graph_counts

EXAMPLE_IMPORT = {
    "nodes": [
        {
            "label": "Supplier",
            "properties": {"id": "S7", "name": "New Supplier Co", "city": "Austin", "state": "TX"},
        }
    ],
    "edges": [
        {
            "source": "RM1", "target": "S7", "type": "SOURCED_FROM",
            "properties": {"cost_per_unit": 1.1, "currency": "USD", "lead_time_days": 14, "is_primary": False},
        }
    ],
}


@st.cache_data(ttl=300, show_spinner=False)
def export_graph_json() -> str:
    node_rows = db.run_cypher("MATCH (n) RETURN labels(n)[0] AS label, properties(n) AS properties")
    edge_rows = db.run_cypher(
        "MATCH (a)-[r]->(b) RETURN coalesce(a.id, a.contract_id) AS source, "
        "coalesce(b.id, b.contract_id) AS target, type(r) AS type, properties(r) AS properties"
    )
    payload = {
        "nodes": [{"label": row["label"], "properties": row["properties"]} for row in node_rows],
        "edges": [
            {"source": row["source"], "target": row["target"], "type": row["type"], "properties": row["properties"]}
            for row in edge_rows
        ],
    }
    return json.dumps(payload, indent=2, default=str)


def import_graph_json(raw_json: str) -> list[str]:
    """Applies an import best-effort, one item at a time - a typo in item 4 shouldn't
    throw away 3 good items - and returns one human-readable result line per item.
    Clears export_graph_json's and the Explorer's own graph cache on any real change.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return [f"❌ Invalid JSON: {exc}"]

    if not isinstance(data, dict) or not ({"nodes", "edges"} & data.keys()):
        return ['❌ JSON must be an object with a "nodes" and/or "edges" list']

    results: list[str] = []
    changed = False

    for i, node in enumerate(data.get("nodes") or [], start=1):
        try:
            label = node.get("label")
            properties = node.get("properties")
            if not label:
                raise ValueError('missing "label"')
            if not isinstance(properties, dict):
                raise ValueError('missing or invalid "properties" object')
            node_id = db.upsert_node(label, properties)
            results.append(f"✅ Node {i}: {label} \"{node_id}\" saved")
            changed = True
        except ValueError as exc:
            results.append(f"❌ Node {i}: {exc}")

    for i, edge in enumerate(data.get("edges") or [], start=1):
        try:
            source, target, rel_type = edge.get("source"), edge.get("target"), edge.get("type")
            properties = edge.get("properties") or {}
            if not source or not target or not rel_type:
                raise ValueError('needs "source", "target", and "type"')
            if not isinstance(properties, dict):
                raise ValueError('"properties" must be an object if present')
            db.upsert_edge(source, target, rel_type, properties)
            results.append(f"✅ Edge {i}: {source} -[{rel_type}]-> {target} saved")
            changed = True
        except ValueError as exc:
            results.append(f"❌ Edge {i}: {exc}")

    if changed:
        fetch_full_graph.clear()
        export_graph_json.clear()
        _graph_counts.clear()  # so the sidebar's node/relationship counts update immediately too

    return results


def render_import_export_section() -> None:
    with st.expander("📤 Import / export graph data (JSON)"):
        st.caption(
            "Export the current graph, or add new suppliers/materials/contracts/etc. "
            "by uploading a JSON file. Re-running the same file is always safe - an id "
            "that already exists gets updated, never duplicated."
        )

        st.download_button(
            "⬇️ Download current graph as JSON", data=export_graph_json(),
            file_name="graph_export.json", mime="application/json", width="stretch",
        )

        st.markdown("**Add new data**")
        uploaded = st.file_uploader("Upload a JSON file", type=["json"], key="graph_import_uploader")
        if uploaded is not None and st.button("Import this file", width="stretch"):
            raw_json = uploaded.getvalue().decode("utf-8")
            results = import_graph_json(raw_json)
            for line in results:
                st.markdown(f"- {line}")
            if any(line.startswith("✅") for line in results):
                st.success(
                    "Import applied - already reflected in the graph below "
                    "(the sidebar's counts catch up on your next click)."
                )

        with st.popover("Expected JSON format"):
            st.code(json.dumps(EXAMPLE_IMPORT, indent=2), language="json")
            st.caption(
                "Every node needs \"label\" (one of: Facility, Warehouse, Region, Dealer, "
                "Product, IntermediatePart, RawMaterial, Supplier, ThirdPartyVendor, "
                "Contract) and \"properties\" including an \"id\" (Contract nodes use "
                "\"contract_id\" instead, matching their real schema). Every edge needs "
                "\"source\"/\"target\" (matching an existing or newly-added node's id) "
                "and \"type\" (one of: SOURCED_FROM, BACKUP_FOR, USED_IN, PURCHASED_FROM, "
                "MANUFACTURED_AT, STORED_IN, SUPPLIES, SERVICES, HAS_CONTRACT, "
                "PREVIOUSLY_CONTRACTED, COVERS)."
            )
