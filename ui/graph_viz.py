"""Neo4j graph fetching + streamlit-agraph Node/Edge construction, shared by the Graph
Explorer tab (full graph) and each answer card's graph-trace layer (highlighted subgraph).
"""
import json
import re

import streamlit as st
from streamlit_agraph import Config, Edge, Node
from streamlit_agraph import _agraph as _raw_agraph

from agent import db
from ui.theme import LABEL_COLORS, MUTED_EDGE_COLOR, MUTED_NODE_COLOR

# Matches our entity ID scheme: RM3, IP12, WH1, S6, V2, P4, D5, R2, C10, C0a, F1
_ID_PATTERN = re.compile(r"^(RM|IP|WH|V|S|P|D|R|C|F)\d+[a-z]?$")


def keyed_agraph(nodes: list[Node], edges: list[Edge], config: Config, key: str):
    """streamlit_agraph.agraph() with an explicit `key`, which its own wrapper doesn't
    expose. Without one, the component is the same persistent widget across reruns and
    keeps re-reporting the last node someone clicked even after the displayed graph has
    completely changed (different nodes/edges/config) - a fresh `key` per distinct view
    forces a real remount, so switching views always starts from a clean "nothing
    clicked yet" state instead of replaying a stale click from a previous view.
    """
    data = {"nodes": [n.to_dict() for n in nodes], "edges": [e.to_dict() for e in edges]}
    return _raw_agraph(data=json.dumps(data), config=json.dumps(config.__dict__), key=key)


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
            size=16,
            color=LABEL_COLORS.get(row["label"], MUTED_NODE_COLOR),
            font={"size": 12, "color": "#334155"},
        )
        for row in node_rows
        if row["node_id"]
    ]
    edges = [
        # No `label` here - an always-on text label per edge is what made a 138-edge graph
        # unreadable (overlapping text everywhere). `title` still surfaces the relationship
        # type on hover, without the visual clutter.
        Edge(source=row["source"], target=row["target"], title=row["rel_type"], color=MUTED_EDGE_COLOR)
        for row in edge_rows
        if row["source"] and row["target"]
    ]
    return nodes, edges


_MAX_HOPS = 3


def fetch_node_neighborhood(node_id: str, hops: int = 1) -> tuple[list[Node], list[Edge], str | None]:
    """Ego view for the Graph Explorer's click-to-focus: the clicked node (large, full
    color) plus everything within `hops` steps of it, so exploring the graph feels like
    drilling into one entity at a time instead of always staring at the full 66-node
    hairball. Returns (nodes, edges, focus_name).

    `hops` > 1 matters for chains like Product -[USED_IN]-> IntermediatePart
    -[USED_IN]-> RawMaterial: at hops=1, clicking the Product only reaches the
    IntermediatePart, never the RawMaterial feeding it - a real gap reported directly.
    Two queries, not one: the first finds which nodes are within range (and how far -
    used to size nodes by proximity to the focus), the second pulls every edge that
    exists *among* that whole node set - not just the ones touching the focus node
    directly - so an IntermediatePart -> RawMaterial edge between two non-focus nodes
    still shows up, not just a hub-and-spoke star out of the center.

    Neo4j doesn't allow a parameter for a variable-length path's hop bound
    ([*1..$hops] is a syntax error) - it must be a literal int, so `hops` is clamped to
    a small fixed range (_MAX_HOPS) before being interpolated into the query text,
    never taken from free-text/LLM input.
    """
    hops = max(1, min(hops, _MAX_HOPS))

    focus_rows = db.run_cypher(
        "MATCH (n) WHERE coalesce(n.id, n.contract_id) = $id "
        "RETURN labels(n)[0] AS label, coalesce(n.name, n.contract_id) AS name",
        {"id": node_id},
    )
    if not focus_rows:
        return [], [], None
    focus_name = focus_rows[0]["name"]
    node_info: dict[str, tuple[str, str, int]] = {node_id: (focus_rows[0]["label"], focus_name, 0)}

    neighbor_rows = db.run_cypher(
        f"""
        MATCH (n) WHERE coalesce(n.id, n.contract_id) = $id
        MATCH p = (n)-[*1..{hops}]-(m)
        WITH m, min(length(p)) AS hop_distance
        RETURN labels(m)[0] AS label, coalesce(m.id, m.contract_id) AS id,
               coalesce(m.name, m.contract_id) AS name, hop_distance
        """,
        {"id": node_id},
    )
    for row in neighbor_rows:
        node_info[row["id"]] = (row["label"], row["name"], row["hop_distance"])

    edge_rows = db.run_cypher(
        """
        MATCH (a)-[r]->(b)
        WHERE coalesce(a.id, a.contract_id) IN $ids AND coalesce(b.id, b.contract_id) IN $ids
        RETURN labels(a)[0] AS a_label, coalesce(a.id, a.contract_id) AS a_id,
               coalesce(b.id, b.contract_id) AS b_id, type(r) AS rel_type
        """,
        {"ids": list(node_info.keys())},
    )
    edges = [
        Edge(
            source=row["a_id"], target=row["b_id"], title=row["rel_type"],
            color=LABEL_COLORS.get(row["a_label"], MUTED_EDGE_COLOR),
        )
        for row in edge_rows
    ]

    nodes = [
        Node(
            id=nid, label=name, title=f"{label}: {name} ({nid})",
            # Bigger and more sharply labeled the closer a node is to the clicked one,
            # so a 2-3 hop view still reads as "centered on X" rather than a flat blob.
            size=30 if dist == 0 else max(12, 20 - 4 * dist),
            color=LABEL_COLORS.get(label, MUTED_NODE_COLOR),
            font={"size": 15 if dist == 0 else max(9, 13 - 2 * dist), "color": "#334155"},
        )
        for nid, (label, name, dist) in node_info.items()
    ]
    return nodes, edges, focus_name


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
                    source=row["n_id"], target=row["m_id"], title=row["rel_type"],
                    color=LABEL_COLORS.get(row["n_label"], MUTED_EDGE_COLOR) if both_highlighted else MUTED_EDGE_COLOR,
                ))

    nodes = [
        Node(
            id=node_id, label=name, title=f"{label}: {name} ({node_id})",
            size=26 if node_id in highlighted_ids else 14,
            color=LABEL_COLORS.get(label, MUTED_NODE_COLOR) if node_id in highlighted_ids else MUTED_NODE_COLOR,
            font={"size": 13 if node_id in highlighted_ids else 11, "color": "#334155"},
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
    # carrying dead config). Any kwarg passed here lands directly in Config.__dict__ and
    # gets JSON-serialized straight into vis-network's options, so `edges`/`nodes`/
    # `interaction` below map 1:1 onto https://visjs.github.io/vis-network/docs/network/ -
    # EXCEPT `physics`, which collides with Config's own named `physics: bool` parameter
    # (passing a dict there gets bound to that param and corrupts Config's own physics-
    # dict construction), so it's set by mutating config.physics after construction instead.
    config = Config(
        height=height, width=width, directed=True, hierarchical=False, groups={},
        # A fixed seed makes the force-directed layout reproducible across reloads -
        # without it, the same graph rearranges itself every time the page refreshes,
        # which reads as flaky rather than as a deliberately explorable, stable map.
        layout={"randomSeed": 42},
        edges={
            # Straight overlapping lines through shared hub nodes were the biggest
            # source of "clumsy" - smooth curves fan them apart automatically.
            "smooth": {"type": "continuous", "roundness": 0.15},
            "color": {"opacity": 0.55, "inherit": False},
            "width": 1,
            "selectionWidth": 1.5,
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.4}},
            "font": {"size": 0},  # rely on hover title, not always-on labels
        },
        nodes={
            "borderWidth": 2,
            "borderWidthSelected": 3,
            "shadow": {"enabled": True, "size": 6, "x": 1, "y": 2},
        },
        interaction={"hover": True, "tooltipDelay": 120, "dragNodes": True},
    )
    config.physics = {
        "enabled": True,
        "solver": "barnesHut",
        "barnesHut": {
            "gravitationalConstant": -6000,
            "centralGravity": 0.25,
            "springLength": 130,
            "springConstant": 0.035,
            "damping": 0.5,
            "avoidOverlap": 0.6,
        },
        "stabilization": {"enabled": True, "iterations": 250, "fit": True},
    }
    return config
