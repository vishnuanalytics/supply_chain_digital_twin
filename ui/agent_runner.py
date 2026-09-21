"""Shared "run a question through the agent with a live status indicator" helper,
used by both the Ask a Question tab and the Contracts & Billing dashboard's row-click
drill-down - the spec asks for the exact same interaction pattern in both places.
"""
import streamlit as st

from agent.graph import get_graph

_LOADING_MESSAGES = {
    "classify_query": "Figuring out how to answer this...",
    "query_neo4j": "Traversing the supply graph...",
    "query_postgres": "Checking inventory, contracts & billing records...",
    "simulate_scenario": "Running the what-if simulation...",
    "validate_results": "Double-checking the results...",
    "synthesize": "Writing your answer...",
}


def run_question(question: str) -> dict:
    """Runs the question through the agent with a live, descriptive status indicator
    (not a generic spinner) and returns either {"state": final_state} or
    {"error": "..."} for the caller to render.
    """
    with st.status("Understanding your question...", expanded=False) as status:
        try:
            final_state = {}
            for snapshot in get_graph().stream(
                {"question": question, "reasoning_log": [], "retry_count": 0}, stream_mode="values"
            ):
                final_state = snapshot
                log = final_state.get("reasoning_log") or []
                if log:
                    last_node = log[-1].get("node")
                    status.update(label=_LOADING_MESSAGES.get(last_node, "Working..."))
            status.update(label="Answer ready", state="complete")
            return {"state": final_state}
        except Exception as exc:  # noqa: BLE001 - surfaced as a designed error state, not a crash
            status.update(label="Ran into a problem", state="error")
            return {"error": str(exc)}


def render_error_card(question: str, error: str) -> None:
    st.markdown('<div class="scdt-card">', unsafe_allow_html=True)
    st.markdown(f"**Q: {question}**")
    st.markdown(
        '<div class="scdt-empty-state">🔴 Couldn\'t reach any configured LLM provider to answer this. '
        "This usually means a free-tier daily quota is exhausted, or a provider needs a credit "
        "top-up. Check the terminal/logs for the exact provider errors, or try again in a bit."
        "</div>",
        unsafe_allow_html=True,
    )
    with st.expander("Technical details"):
        st.code(error)
    st.markdown("</div>", unsafe_allow_html=True)
