"""Persistent sidebar: live graph stats + the previous query's engine/latency
breakdown. The "Use Jev for fast decisions" toggle from the spec is deliberately not
here yet - the spec says to build it after the Jev integration itself exists (build
order step 8), and a toggle for a feature that doesn't exist yet would just be dead UI.
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

        last_log = st.session_state.get("last_reasoning_log")
        if last_log:
            st.markdown("### Last query, by the numbers")
            for entry in last_log:
                node = entry.get("node", "?")
                engine = entry.get("engine_used", "?")
                latency = entry.get("latency_ms")
                latency_str = f"{latency:.0f} ms" if isinstance(latency, (int, float)) else "—"
                st.caption(f"**{node}** → `{engine}` · {latency_str}")
