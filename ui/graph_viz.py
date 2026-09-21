"""Neo4j graph fetching + streamlit-agraph Node/Edge construction, shared by the Graph
Explorer tab (full graph) and each answer card's graph-trace layer (highlighted subgraph).
"""
import re

import streamlit as st
from streamlit_agraph import Config, Edge, Node

from agent import db
from ui.theme import LABEL_COLORS, MUTED_EDGE_COLOR, MUTED_NODE_COLOR

# Matches our entity ID scheme: RM3, IP12, WH1, S6, V2, P4, D5, R2, C10, C0a, F1
_ID_PATTERN = re.compile(r"^(RM|IP|WH|V|S|P|D|R|C|F)\d+[a-z]?$")


def extract_ids(*sources) -> set[str]:
    """Recursively walks any nested dict/list/str structure (Cypher rows, SQL rows,
    simulation result dicts) and pulls out every string that looks like one of our
    entity IDs, regardless of which key it was stored under."""
    found: set[str] = set()

    def walk(obj) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v)
        elif isinstance(obj, str) and _ID_PATTERN.match(obj):
            found.add(obj)

    for src in sources:
        if src:
            walk(src)
    return found


@st.cache_data(ttl=300, show_spinner=False)
def fetch_full_graph() -> tuple[list[Node], list[Edge]]:
    node_rows = db.run_cypher(
        "MATCH (n) RETURN labels(n)[0] AS label, coalesce(n.id, n.contract_id) AS node_id, "
        "coalesce(n.name, n.contract_id) AS display_name"
    )
    edge_rows = db.run_cypher(
        "MATCH (a)-[r]->(b) RETURN coalesce(a.id, a.contract_id) AS source, "
        "coalesce(b.id, b.contract_id) AS target, type(r) AS rel_type"
    )

    nodes = [
        Node(
            id=row["node_id"],
            label=f"{row['display_name']}",
            title=f"{row['label']}: {row['display_name']} ({row['node_id']})",
            size=18,
            color=LABEL_COLORS.get(row["label"], MUTED_NODE_COLOR),
        )
        for row in node_rows
        if row["node_id"]
    ]
    edges = [
        Edge(source=row["source"], target=row["target"], label=row["rel_type"], color=MUTED_EDGE_COLOR)
        for row in edge_rows
        if row["source"] and row["target"]
    ]
    return nodes, edges


def fetch_highlighted_subgraph(highlighted_ids: set[str]) -> tuple[list[Node], list[Edge]]:
    """Fetches the highlighted nodes plus their immediate neighbors, so the trace has
    context (muted gray) around the actual traversal path (accent color) — matches the
    spec's "highlighted path, rest of graph muted gray" requirement without pulling the
    entire graph on every answer."""
    if not highlighted_ids:
        return [], []

    rows = db.run_cypher(
        """
        MATCH (n) WHERE coalesce(n.id, n.contract_id) IN $ids
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN labels(n)[0] AS n_label, coalesce(n.id, n.contract_id) AS n_id,
               coalesce(n.name, n.contract_id) AS n_name,
               labels(m)[0] AS m_label, coalesce(m.id, m.contract_id) AS m_id,
               coalesce(m.name, m.contract_id) AS m_name, type(r) AS rel_type
        LIMIT 300
        """,
        {"ids": list(highlighted_ids)},
    )

    node_info: dict[str, tuple[str, str]] = {}  # id -> (label, name)
    edges: list[Edge] = []
    seen_edges: set[tuple[str, str, str]] = set()

    for row in rows:
        node_info[row["n_id"]] = (row["n_label"], row["n_name"])
        if row["m_id"]:
            node_info.setdefault(row["m_id"], (row["m_label"], row["m_name"]))
            key = tuple(sorted([row["n_id"], row["m_id"]])) + (row["rel_type"],)
            if key not in seen_edges:
                seen_edges.add(key)
                both_highlighted = row["n_id"] in highlighted_ids and row["m_id"] in highlighted_ids
                edges.append(Edge(
                    source=row["n_id"], target=row["m_id"], label=row["rel_type"],
                    color=LABEL_COLORS.get(row["n_label"], MUTED_EDGE_COLOR) if both_highlighted else MUTED_EDGE_COLOR,
                ))

    nodes = [
        Node(
            id=node_id, label=name, title=f"{label}: {name} ({node_id})",
            size=26 if node_id in highlighted_ids else 14,
            color=LABEL_COLORS.get(label, MUTED_NODE_COLOR) if node_id in highlighted_ids else MUTED_NODE_COLOR,
        )
        for node_id, (label, name) in node_info.items()
    ]
    return nodes, edges


def default_config(height: int = 500, width: int = 700) -> Config:
    # Config's __init__ always appends "px" to width/height (so "100%" would become
    # the invalid CSS value "100%px" - pass a plain pixel int instead), defaults
    # `groups` to None which vis.js's own options validator rejects unless overridden
    # with an empty dict, and silently ignores any kwarg that isn't a real vis-network
    # option (nodeHighlightBehavior/highlightColor/collapsible aren't real options in
    # this vis-network version - confirmed via browser console, removed rather than
    # carrying dead config).
    return Config(height=height, width=width, directed=True, physics=True, hierarchical=False, groups={})
