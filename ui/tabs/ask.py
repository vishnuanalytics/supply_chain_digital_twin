"""The default "Ask a Question" tab: example questions, a chat-style input, and a
running history of 3-layer answer cards.
"""
import streamlit as st

from ui.agent_runner import render_error_card, resume_question, run_question
from ui.answer_card import render_answer_card

EXAMPLE_QUESTIONS = [
    "Our aluminum supplier just had a 3-week delay. What's affected?",
    "Which raw materials have only one supplier?",
    "Find a backup supplier for aluminum alloy billet.",
    "Which supplier contracts expire in the next 90 days?",
    "What's our total outstanding balance across active contracts this month?",
    "Are any shipments delayed against contracts with penalty clauses?",
]


def _render_approval_prompt(pending: dict) -> None:
    """Shown instead of the normal example-questions/history view whenever
    human_approval_gate has paused a run (build step 8) - the question isn't answered
    yet, so it stays out of history until this is resolved."""
    rec = pending["interrupt"]
    st.markdown('<div class="scdt-card">', unsafe_allow_html=True)
    st.markdown(f"**Q: {pending['question']}**")
    st.markdown("🔔 **This answer includes a recommendation that needs your approval first:**")
    st.markdown(rec.get("description", "A recommended action needs your approval."))
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    approve = col1.button("✅ Approve", key="approve_action", width="stretch")
    reject = col2.button("❌ Reject", key="reject_action", width="stretch")

    if approve or reject:
        result = resume_question(pending["thread_id"], approved=approve)
        st.session_state.pop("pending_approval", None)
        st.session_state["history"].append({"question": pending["question"], **result})
        if "state" in result:
            st.session_state["last_reasoning_log"] = result["state"].get("reasoning_log")
        st.rerun()


def render_ask_tab() -> None:
    st.markdown("### Ask a question")
    st.caption("Try one of these, or type your own question below.")

    if "history" not in st.session_state:
        st.session_state["history"] = []

    pending_approval = st.session_state.get("pending_approval")
    if pending_approval:
        _render_approval_prompt(pending_approval)
        return

    cols = st.columns(3)
    for i, q in enumerate(EXAMPLE_QUESTIONS):
        if cols[i % 3].button(q, key=f"example_{i}", width="stretch"):
            st.session_state["pending_question"] = q

    typed = st.chat_input("Ask about suppliers, inventory, contracts, disruptions...")
    if typed:
        st.session_state["pending_question"] = typed

    pending = st.session_state.pop("pending_question", None)
    if pending:
        result = run_question(pending)
        if "interrupt" in result:
            st.session_state["pending_approval"] = {**result, "question": pending}
            st.rerun()
        else:
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
            render_error_card(item["question"], item["error"])
        else:
            st.markdown(f"**Q: {item['question']}**")
            render_answer_card(item["state"])
