"""Persistent sidebar: live graph stats, the "Use Jev for fast decisions" toggle
(build step 8), and the previous query's engine/latency breakdown.
"""
import streamlit as st

from agent import config, db


@st.cache_data(ttl=60, show_spinner=False)
def _graph_counts() -> tuple[int, int] | None:
    try:
        nodes = db.run_cypher("MATCH (n) RETURN count(n) AS n")[0]["n"]
        rels = db.run_cypher("MATCH ()-->() RETURN count(*) AS n")[0]["n"]
        return nodes, rels
    except Exception:  # noqa: BLE001 - sidebar must never crash the whole app
        return None


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## Supply Chain Digital Twin")
        st.caption("Ask plain-English questions about the supply chain - no SQL or Cypher required.")

        st.markdown("### Live graph stats")
        counts = _graph_counts()
        if counts:
            nodes, rels = counts
            col1, col2 = st.columns(2)
            col1.metric("Nodes", nodes)
            col2.metric("Relationships", rels)
        else:
            st.caption("⚠️ Couldn't reach Neo4j right now.")
        st.caption(f"Demo data as of {config.DEMO_REFERENCE_DATE.isoformat()}")

        st.markdown("### Decision engine")
        st.session_state["use_jev"] = st.toggle(
            "Use Jev for fast decisions", value=st.session_state.get("use_jev", False),
            help="Routes classify_query's query_type/simulation detection through TypeSafe "
                 "AI's Jev (a fast, cheap typed-decision model) instead of a full LLM call. "
                 "Always falls back to Claude/Groq automatically if Jev errors or isn't configured.",
        )
        if st.session_state["use_jev"] and not config.TYPESAFE_API_KEY:
            st.caption("⚠️ No TYPESAFE_API_KEY set - every decision will fall back to the normal LLM path.")
        if config.LANGSMITH_TRACING_ENABLED:
            st.caption(f"🔍 LangSmith tracing on · project `{config.LANGSMITH_PROJECT}`")

        last_log = st.session_state.get("last_reasoning_log")
        if last_log:
            st.markdown("### Last query, by the numbers")
            for entry in last_log:
                node = entry.get("node", "?")
                engine = entry.get("engine_used", "?")
                latency = entry.get("latency_ms")
                latency_str = f"{latency:.0f} ms" if isinstance(latency, (int, float)) else "—"
                st.caption(f"**{node}** → `{engine}` · {latency_str}")
