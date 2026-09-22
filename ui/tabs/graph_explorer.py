"""Free-browsing view of the full supply chain graph - interactive, draggable nodes,
colored by entity type. Two ways to narrow down the graph instead of always facing the
full 66-node/138-edge hairball: pick which entity types to show, or click any node to
zoom into just its direct connections.
"""
import streamlit as st

from ui.graph_viz import default_config, fetch_full_graph, fetch_node_neighborhood, keyed_agraph
from ui.theme import LABEL_COLORS

_COLOR_TO_LABEL = {color: label for label, color in LABEL_COLORS.items()}


def _filtered_graph(nodes, edges, selected_labels):
    if len(selected_labels) == len(LABEL_COLORS):
        return nodes, edges  # everything selected - skip filtering, keep original order
    kept_ids = {n.id for n in nodes if _COLOR_TO_LABEL.get(n.color) in selected_labels}
    filtered_nodes = [n for n in nodes if n.id in kept_ids]
    filtered_edges = [e for e in edges if e.source in kept_ids and e.to in kept_ids]
    return filtered_nodes, filtered_edges


def render_graph_explorer_tab() -> None:
    st.markdown("### Graph Explorer")
    st.caption(
        "Filter by entity type below, or click any node to zoom into just its direct "
        "connections. Drag nodes around, scroll to zoom."
    )

    all_labels = list(LABEL_COLORS.keys())
    selected_labels = st.pills(
        "Show entity types", all_labels, selection_mode="multi",
        default=all_labels, label_visibility="collapsed", key="graph_type_filter",
    ) or []

    try:
        all_nodes, all_edges = fetch_full_graph()
    except Exception as exc:  # noqa: BLE001 - a broken DB connection shouldn't blank the whole tab
        st.markdown(
            '<div class="scdt-empty-state">🔴 Couldn\'t load the graph right now - '
            "Neo4j may be unreachable.</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Technical details"):
            st.code(str(exc))
        return

    if not all_nodes:
        st.markdown('<div class="scdt-empty-state">The graph is empty.</div>', unsafe_allow_html=True)
        return

    focus_id = st.session_state.get("graph_focus_node")
    # Bumped on every transition into or out of focus mode, and folded into the
    # component's key below, so each view is a genuinely fresh component instance -
    # otherwise switching views would keep replaying whatever node was last clicked
    # in a previous view instead of starting clean (see keyed_agraph's docstring).
    view_gen = st.session_state.setdefault("graph_view_gen", 0)

    if focus_id:
        focus_nodes, focus_edges, focus_name = fetch_node_neighborhood(focus_id)
        if not focus_name:
            st.session_state["graph_focus_node"] = None
            st.rerun()
        col1, col2 = st.columns([5, 1])
        col1.markdown(f"**Focused on: {focus_name}** — showing its direct connections only.")
        if col2.button("← Full graph", width="stretch"):
            st.session_state["graph_focus_node"] = None
            st.session_state["graph_view_gen"] += 1
            st.rerun()
        clicked = keyed_agraph(
            nodes=focus_nodes, edges=focus_edges, config=default_config(height=600, width=1300),
            key=f"graph_explorer_{view_gen}",
        )
        caption = f"{len(focus_nodes)} nodes · {len(focus_edges)} relationships in this view"
    else:
        display_nodes, display_edges = _filtered_graph(all_nodes, all_edges, set(selected_labels))
        if not display_nodes:
            st.markdown(
                '<div class="scdt-empty-state">No nodes match the selected type(s).</div>',
                unsafe_allow_html=True,
            )
            return
        clicked = keyed_agraph(
            nodes=display_nodes, edges=display_edges, config=default_config(height=650, width=1300),
            key=f"graph_explorer_{view_gen}",
        )
        caption = (
            f"{len(display_nodes)} of {len(all_nodes)} nodes · {len(display_edges)} relationships shown"
        )

    st.caption(caption)

    if clicked:
        st.session_state["graph_focus_node"] = clicked
        st.session_state["graph_view_gen"] += 1
        st.rerun()
