"""Renders the consistent 3-layer answer card (+ collapsed reasoning layer) that every
question, whether from the chat tab or the billing dashboard, produces. Never skip a
layer for a "simple" answer - that consistency is the point.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_agraph import agraph

from ui.graph_viz import default_config, extract_ids, fetch_highlighted_subgraph
from ui.theme import ACCENT, confidence_badge_html


def _rows_to_dataframe(rows: list[dict] | None) -> pd.DataFrame | None:
    if not rows:
        return None
    return pd.DataFrame(rows)


def _simulation_chart(sim: dict):
    impacts = sim.get("product_impacts")
    if not impacts:
        return None
    df = pd.DataFrame(impacts)
    value_col = "added_cost_per_unit" if "added_cost_per_unit" in df.columns else None
    if not value_col:
        return None
    fig = go.Figure(go.Bar(
        x=df["product_name"], y=df[value_col], marker_color=ACCENT,
    ))
    fig.update_layout(
        title="Added cost per finished unit", yaxis_title="USD", margin=dict(t=40, b=10, l=10, r=10),
        height=320, plot_bgcolor="white",
    )
    return fig


def render_answer_card(state: dict) -> None:
    answer = state.get("answer") or "I wasn't able to generate an answer."
    confidence = state.get("confidence")

    st.markdown('<div class="scdt-card">', unsafe_allow_html=True)

    # Layer 1: plain-English answer + confidence
    st.markdown(
        f'<div class="scdt-answer-text">{answer}</div>{confidence_badge_html(confidence)}',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Layer 2: supporting data
    st.markdown("**Supporting data**")
    neo4j_df = _rows_to_dataframe(state.get("neo4j_result"))
    postgres_df = _rows_to_dataframe(state.get("postgres_result"))
    semantic_df = _rows_to_dataframe(state.get("semantic_result"))
    sim = state.get("simulation_result")

    shown_any_data = False
    if neo4j_df is not None:
        st.dataframe(neo4j_df, width="stretch", hide_index=True)
        shown_any_data = True
    if postgres_df is not None:
        st.dataframe(postgres_df, width="stretch", hide_index=True)
        shown_any_data = True
    if semantic_df is not None:
        if "similarity" in semantic_df.columns:
            semantic_df = semantic_df.copy()
            semantic_df["similarity"] = semantic_df["similarity"].round(3)
        st.caption("🔎 Semantic search over supplier/vendor audit & quality notes (higher similarity = more relevant)")
        st.dataframe(semantic_df, width="stretch", hide_index=True)
        shown_any_data = True
    if sim:
        chart = _simulation_chart(sim)
        if chart is not None:
            st.plotly_chart(chart, width="stretch")
            shown_any_data = True
        sim_display = {k: v for k, v in sim.items() if k not in ("product_impacts", "affected_materials")}
        if sim_display:
            st.dataframe(pd.DataFrame([sim_display]), width="stretch", hide_index=True)
            shown_any_data = True
        if sim.get("affected_materials"):
            st.dataframe(pd.DataFrame(sim["affected_materials"]), width="stretch", hide_index=True)
            shown_any_data = True
    if not shown_any_data:
        st.markdown(
            '<div class="scdt-empty-state">No rows matched this query — the answer above reflects that '
            'directly (e.g. "none on file" is often a real, correct result, not a failure).</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Layer 3: graph trace
    st.markdown("**Graph trace**")
    highlighted_ids = extract_ids(
        state.get("neo4j_result"), state.get("postgres_result"), state.get("simulation_result"),
        state.get("semantic_result"),
    )
    if highlighted_ids:
        try:
            nodes, edges = fetch_highlighted_subgraph(highlighted_ids)
        except Exception:  # noqa: BLE001 - Neo4j going down mid-render shouldn't crash the card
            st.caption("⚠️ Couldn't load the graph trace right now - Neo4j may be unreachable.")
        else:
            if nodes:
                agraph(nodes=nodes, edges=edges, config=default_config(height=420))
            else:
                st.caption("No graph nodes matched this answer's entities.")
    else:
        st.caption("This answer didn't traverse the graph directly (e.g. a pure billing/inventory lookup).")

    # Layer 4: collapsed reasoning
    with st.expander("Show reasoning", expanded=False):
        _render_reasoning(state)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_reasoning(state: dict) -> None:
    resolved = state.get("resolved_question")
    if resolved and resolved != state.get("question"):
        st.markdown(f"**🔗 Resolved as:** _{resolved}_")
        st.caption("A follow-up reference (\"it\", \"that supplier\", ...) was rewritten using recent conversation history.")
        st.markdown("---")

    decisions = state.get("decision_log") or []
    if decisions:
        st.markdown("**⚡ Decision engine**")
        for d in decisions:
            engine = d.get("engine_used", "?")
            latency = d.get("latency_ms")
            latency_str = f"{latency:.0f} ms" if isinstance(latency, (int, float)) else "—"
            if d.get("error"):
                st.markdown(f"- `{d.get('decision')}` via `{engine}`: :red[failed - {d['error']}] (fell back)")
            else:
                st.markdown(f"- `{d.get('decision')}` = **{d.get('value')}** via `{engine}` ({latency_str})")
        st.markdown("---")

    log = state.get("reasoning_log") or []
    if not log:
        st.caption("No reasoning steps recorded.")
        return
    for entry in log:
        node = entry.get("node", "?")
        engine = entry.get("engine_used", "?")
        model = entry.get("model")
        latency = entry.get("latency_ms")
        header = f"**{node}** — engine: `{engine}`" + (f", model: `{model}`" if model else "")
        if latency is not None:
            header += f" ({latency:.0f} ms)" if isinstance(latency, (int, float)) else f" ({latency})"
        st.markdown(header)
        if entry.get("cypher_query"):
            st.code(entry["cypher_query"], language="cypher")
        if entry.get("sql_query"):
            st.code(entry["sql_query"], language="sql")
        if node == "human_approval_gate" and not entry.get("skipped"):
            icon = "✅ approved" if entry.get("approved") else "❌ rejected"
            st.markdown(f"🔔 {entry.get('recommendation', '')} — **{icon}**")
            if entry.get("note"):
                st.caption(f"Note: {entry['note']}")
        if "valid" in entry:
            icon = "✅" if entry["valid"] else "❌"
            st.markdown(f"{icon} validation: {entry.get('reason', '')}")
        if entry.get("error"):
            st.markdown(f":red[error: {entry['error']}]")
        st.markdown("---")
