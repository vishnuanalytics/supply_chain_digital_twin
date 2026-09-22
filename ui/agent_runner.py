"""Shared "run a question through the agent with a live status indicator" helper,
used by both the Ask a Question tab and the Contracts & Billing dashboard's row-click
drill-down - the spec asks for the exact same interaction pattern in both places.
"""
import uuid

import streamlit as st

from agent import llm_client
from agent.graph import get_graph
from ui.sidebar import current_llm_override

_LOADING_MESSAGES = {
    "classify_query": "Figuring out how to answer this...",
    "query_neo4j": "Traversing the supply graph...",
    "query_postgres": "Checking inventory, contracts & billing records...",
    "query_semantic": "Searching supplier audit & quality notes...",
    "simulate_scenario": "Running the what-if simulation...",
    "human_approval_gate": "Checking whether this needs your approval...",
    "validate_results": "Double-checking the results...",
    "synthesize": "Writing your answer...",
}


def _stream(initial_input, config, status) -> dict:
    final_state = {}
    for snapshot in get_graph().stream(initial_input, config, stream_mode="values"):
        final_state = snapshot
        log = final_state.get("reasoning_log") or []
        if log:
            last_node = log[-1].get("node")
            status.update(label=_LOADING_MESSAGES.get(last_node, "Working..."))
    return final_state


def run_question(question: str, conversation_history: list[dict] | None = None) -> dict:
    """Runs the question through the agent with a live, descriptive status indicator
    (not a generic spinner). Returns one of:
      {"state": final_state}                        - answered normally
      {"interrupt": {...}, "thread_id": "..."}       - paused on human_approval_gate;
                                                        pass thread_id to resume_question()
      {"error": "..."}                               - for the caller to render

    `conversation_history` (a list of {"question", "answer"} dicts) is how the Ask tab's
    follow-up questions ("what about its backup supplier?") get resolved - passed
    explicitly by the caller (not read from session_state here) so the Billing tab's
    drill-down questions, which call this same helper, can deliberately opt out and
    stay free of unrelated chat context.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}, "run_name": "ask_question"}
    # Honors the sidebar's manual model picker for every LLM call this question makes -
    # (None, None) is a no-op (llm_client.complete() falls back to its normal Auto
    # chain). Always reset in `finally` so one question's manual pick can never leak
    # into the next (see llm_client.set_override's own docstring for why this matters).
    override_token = llm_client.set_override(*current_llm_override())
    try:
        with st.status("Understanding your question...", expanded=False) as status:
            try:
                final_state = _stream(
                    {
                        "question": question, "reasoning_log": [], "decision_log": [], "retry_count": 0,
                        "use_jev": st.session_state.get("use_jev", False),
                        "conversation_history": conversation_history or [],
                    },
                    config, status,
                )
                if "__interrupt__" in final_state:
                    status.update(label="Waiting for your approval...", state="running")
                    return {"interrupt": final_state["__interrupt__"][0].value, "thread_id": thread_id}
                status.update(label="Answer ready", state="complete")
                return {"state": final_state}
            except Exception as exc:  # noqa: BLE001 - surfaced as a designed error state, not a crash
                status.update(label="Ran into a problem", state="error")
                return {"error": str(exc)}
    finally:
        llm_client.reset_override(override_token)


def resume_question(thread_id: str, approved: bool, note: str = "") -> dict:
    """Resumes a graph paused by human_approval_gate with the user's decision. Same
    return shape as run_question() (minus a further interrupt - this app only ever
    pauses once per question)."""
    from langgraph.types import Command

    config = {"configurable": {"thread_id": thread_id}, "run_name": "ask_question_resume"}
    override_token = llm_client.set_override(*current_llm_override())
    try:
        with st.status("Finishing up...", expanded=False) as status:
            try:
                final_state = _stream(Command(resume={"approved": approved, "note": note}), config, status)
                status.update(label="Answer ready", state="complete")
                return {"state": final_state}
            except Exception as exc:  # noqa: BLE001
                status.update(label="Ran into a problem", state="error")
                return {"error": str(exc)}
    finally:
        llm_client.reset_override(override_token)


def render_error_card(question: str, error: str, show_question: bool = True) -> None:
    st.markdown('<div class="scdt-card">', unsafe_allow_html=True)
    if show_question:
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
