"""The default "Ask a Question" tab: example questions, a chat-style input, and a
running history of 3-layer answer cards.
"""
import streamlit as st

from ui.agent_runner import render_error_card, run_question
from ui.answer_card import render_answer_card

EXAMPLE_QUESTIONS = [
    "Our aluminum supplier just had a 3-week delay. What's affected?",
    "Which raw materials have only one supplier?",
    "Find a backup supplier for aluminum alloy billet.",
    "Which supplier contracts expire in the next 90 days?",
    "What's our total outstanding balance across active contracts this month?",
    "Are any shipments delayed against contracts with penalty clauses?",
]


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
        result = run_question(pending)
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
