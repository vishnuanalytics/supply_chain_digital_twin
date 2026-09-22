"""Free-browsing view of the full supply chain graph - interactive, draggable nodes,
colored by entity type. Two ways to narrow down the graph instead of always facing the
full 66-node/138-edge hairball: pick which entity types to show, or click any node to
zoom into just its direct connections.
"""
import streamlit as st

from ui.graph_viz import default_config, fetch_full_graph, fetch_node_neighborhood, keyed_agraph
from ui.theme import LABEL_COLORS

_COLOR_TO_LABEL = {color: label for label, color in LABEL_COLORS.items()}


def _pill_colors_css() -> str:
    """Colors each type-filter pill to match its entity type's actual node color (so
    "Facility" looks like the blue Facility nodes, etc.) - st.pills has no per-option
    color option, and CSS can't select a <button> by its text content, so this targets
    each pill purely by its position, which is safe because the pills are always
    rendered in LABEL_COLORS's fixed iteration order. Scoped to this widget's own
    `st-key-*` class (a class Streamlit derives from the `key=` we pass it) so it can
    never bleed into some other, unrelated button/pills group.
    """
    rules = []
    for i, (_, color) in enumerate(LABEL_COLORS.items(), start=1):
        selector = (
            f'.st-key-graph_type_filter div[data-testid="stButtonGroup"] > div > '
            f"button:nth-of-type({i})"
        )
        # Unselected: muted gray, same treatment as a plain inactive filter chip - the
        # color only shows up once you've actually selected that type, so on/off reads
        # clearly instead of every pill looking like a permanently "half-lit" version
        # of its color.
        rules.append(
            f"{selector} {{ border-color: #CBD5E1 !important; color: #64748B !important; "
            f"background-color: #F8FAFC !important; }}"
        )
        rules.append(
            f'{selector}[aria-pressed="true"] {{ border-color: {color} !important; '
            f"color: {color} !important; background-color: {color}26 !important; "
            f"font-weight: 700 !important; }}"
        )
    return f"<style>{' '.join(rules)}</style>"


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
        "Filter by entity type below, or click any node to zoom into its connections "
        "(pick how many hops out once focused). Drag nodes around, scroll to zoom."
    )

    all_labels = list(LABEL_COLORS.keys())
    selected_labels = st.pills(
        "Show entity types", all_labels, selection_mode="multi",
        default=all_labels, label_visibility="collapsed", key="graph_type_filter",
    ) or []
    st.markdown(_pill_colors_css(), unsafe_allow_html=True)

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
        col1, col2, col3 = st.columns([3, 2, 1.2])
        hops = col2.segmented_control(
            "Hops", [1, 2, 3], default=2, key="graph_hops",
            format_func=lambda h: f"{h} hop" + ("s" if h > 1 else ""),
        ) or 1
        focus_nodes, focus_edges, focus_name = fetch_node_neighborhood(focus_id, hops=hops)
        if not focus_name:
            st.session_state["graph_focus_node"] = None
            st.rerun()
        col1.markdown(
            f"**Focused on: {focus_name}** — showing connections up to {hops} "
            f"hop{'s' if hops > 1 else ''} out."
        )
        if col3.button("← Full graph", width="stretch"):
            st.session_state["graph_focus_node"] = None
            st.session_state["graph_view_gen"] += 1
            st.rerun()
        clicked = keyed_agraph(
            nodes=focus_nodes, edges=focus_edges, config=default_config(height=600, width=1300),
            key=f"graph_explorer_{view_gen}_{hops}",
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
