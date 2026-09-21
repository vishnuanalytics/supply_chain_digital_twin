"""Free-browsing view of the full supply chain graph - interactive, draggable nodes,
colored by entity type.
"""
import streamlit as st
from streamlit_agraph import agraph

from ui.graph_viz import default_config, fetch_full_graph
from ui.theme import LABEL_COLORS


def render_graph_explorer_tab() -> None:
    st.markdown("### Graph Explorer")
    st.caption("The full supply chain graph. Drag nodes around, scroll to zoom, hover for details.")

    legend_cols = st.columns(len(LABEL_COLORS))
    for col, (label, color) in zip(legend_cols, LABEL_COLORS.items()):
        col.markdown(
            f'<span style="color:{color}; font-size:1.3rem;">●</span> '
            f'<span style="font-size:0.8rem;">{label}</span>',
            unsafe_allow_html=True,
        )

    try:
        nodes, edges = fetch_full_graph()
    except Exception as exc:  # noqa: BLE001 - a broken DB connection shouldn't blank the whole tab
        st.markdown(
            '<div class="scdt-empty-state">🔴 Couldn\'t load the graph right now - '
            "Neo4j may be unreachable.</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Technical details"):
            st.code(str(exc))
        return

    if not nodes:
        st.markdown('<div class="scdt-empty-state">The graph is empty.</div>', unsafe_allow_html=True)
        return

    agraph(nodes=nodes, edges=edges, config=default_config(height=650, width=1300))
    st.caption(f"{len(nodes)} nodes · {len(edges)} relationships")
