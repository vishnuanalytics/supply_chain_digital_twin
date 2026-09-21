"""The default "Ask a Question" tab: example questions, a chat-style input, and a
running history of 3-layer answer cards.
"""
import streamlit as st

from agent.graph import get_graph
from ui.answer_card import render_answer_card

EXAMPLE_QUESTIONS = [
    "Our aluminum supplier just had a 3-week delay. What's affected?",
    "Which raw materials have only one supplier?",
    "Find a backup supplier for aluminum alloy billet.",
    "Which supplier contracts expire in the next 90 days?",
    "What's our total outstanding balance across active contracts this month?",
    "Are any shipments delayed against contracts with penalty clauses?",
]

_LOADING_MESSAGES = {
    "classify_query": "Figuring out how to answer this...",
    "query_neo4j": "Traversing the supply graph...",
    "query_postgres": "Checking inventory, contracts & billing records...",
    "simulate_scenario": "Running the what-if simulation...",
    "validate_results": "Double-checking the results...",
    "synthesize": "Writing your answer...",
}


def _run_question(question: str) -> dict:
    """Runs the question through the agent with a live, descriptive status indicator
    (not a generic spinner) and returns either {"state": final_state} or
    {"error": "..."} for the tab to render.
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


def _render_error_card(question: str, error: str) -> None:
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


def render_ask_tab() -> None:
    st.markdown("### Ask a question")
    st.caption("Try one of these, or type your own question below.")

    if "history" not in st.session_state:
        st.session_state["history"] = []

    cols = st.columns(3)
    for i, q in enumerate(EXAMPLE_QUESTIONS):
        if cols[i % 3].button(q, key=f"example_{i}", width="stretch"):
            st.session_state["pending_question"] = q

    typed = st.chat_input("Ask about suppliers, inventory, contracts, disruptions...")
    if typed:
        st.session_state["pending_question"] = typed

    pending = st.session_state.pop("pending_question", None)
    if pending:
        result = _run_question(pending)
        st.session_state["history"].append({"question": pending, **result})
        if "state" in result:
            st.session_state["last_reasoning_log"] = result["state"].get("reasoning_log")

    if not st.session_state["history"]:
        st.markdown(
            '<div class="scdt-empty-state">No questions asked yet - click an example above '
            "or type your own to get started.</div>",
            unsafe_allow_html=True,
        )
        return

    for item in reversed(st.session_state["history"]):
        if "error" in item:
            _render_error_card(item["question"], item["error"])
        else:
            st.markdown(f"**Q: {item['question']}**")
            render_answer_card(item["state"])
