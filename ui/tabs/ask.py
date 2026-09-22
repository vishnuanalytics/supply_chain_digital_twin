"""The default "Ask a Question" tab: a real chat thread (chat bubbles, oldest-to-newest,
input pinned at the bottom) rather than a stack of report-style cards - follow-ups
already worked under the hood (conversation_history/resolved_question), but rendering
newest-first as isolated cards made it look like separate one-off Q&As instead of one
continuous conversation. Example questions only show before the thread has started,
same as a typical chat app's empty-state suggestions.
"""
import uuid

import streamlit as st

from agent import db
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


def _remember(question: str, result: dict) -> None:
    """Feeds this turn's Q&A into conversation_history so a follow-up like "what about
    its backup supplier?" can be resolved next time - kept separate from the `history`
    list (which drives the rendered thread and can include error turns that shouldn't
    pollute the agent's own context). Also persists the turn to Postgres so it survives
    a page refresh or server restart; that write is best-effort and must never block the
    live chat, so a DB failure is swallowed rather than surfaced."""
    state = result.get("state") or {}
    answer = state.get("answer")
    if answer:
        st.session_state["conversation_history"].append({"question": question, "answer": answer})
        try:
            db.log_chat_turn(st.session_state["session_id"], question, state)
        except Exception:
            pass


def _render_turn(item: dict) -> None:
    with st.chat_message("user"):
        st.markdown(item["question"])
    with st.chat_message("assistant"):
        if "error" in item:
            render_error_card(item["question"], item["error"], show_question=False)
        else:
            render_answer_card(item["state"])


def _render_approval_prompt(pending: dict) -> None:
    """Rendered as the assistant's turn in the thread whenever human_approval_gate has
    paused a run (build step 8) - the question isn't answered yet, so it stays out of
    `history` until this is resolved."""
    rec = pending["interrupt"]
    with st.chat_message("user"):
        st.markdown(pending["question"])
    with st.chat_message("assistant"):
        st.markdown('<div class="scdt-card">', unsafe_allow_html=True)
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
            _remember(pending["question"], result)
            st.rerun()


def render_ask_tab() -> None:
    # session_id/history/conversation_history are set up by render_sidebar()'s
    # "Conversations" section, which always runs before any tab (see app.py) - the
    # New chat button and past-session list live there now, ChatGPT-sidebar style,
    # rather than behind a popover local to this tab.
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("conversation_history", [])

    st.markdown("### Ask a question")
    st.caption(
        "Chat naturally - this is one continuous conversation, so follow-ups like "
        "\"what's its on-time delivery rate?\" right after asking about a supplier "
        "just work, no need to restate context. Saved automatically - see "
        "\"💬 Conversations\" in the sidebar for past chats."
    )

    history = st.session_state["history"]
    pending_approval = st.session_state.get("pending_approval")
    # Peek (don't pop) so a question that's already queued - either from the previous
    # pass's st.rerun() below, or one submitted via chat_input on this very pass -
    # hides the examples too, not just a non-empty `history`.
    has_pending_question = st.session_state.get("pending_question") is not None

    if not history and not pending_approval and not has_pending_question:
        st.caption("Try one of these to get started:")
        cols = st.columns(3)
        clicked = False
        for i, q in enumerate(EXAMPLE_QUESTIONS):
            if cols[i % 3].button(q, key=f"example_{i}", width="stretch"):
                st.session_state["pending_question"] = q
                clicked = True
        if clicked:
            # Rerun immediately so the examples disappear right away instead of
            # sitting alongside the in-progress answer for one extra render pass.
            st.rerun()

    # The thread so far, oldest first - a real conversation log, not a reverse-
    # chronological stack of separate report cards.
    for item in history:
        _render_turn(item)

    if pending_approval:
        _render_approval_prompt(pending_approval)
        return  # wait for the approve/reject click before accepting new input

    typed = st.chat_input("Ask about suppliers, inventory, contracts, disruptions...")
    if typed:
        st.session_state["pending_question"] = typed

    pending = st.session_state.pop("pending_question", None)
    if pending:
        # Rendered live, right here at the end of the thread (not via the loop above),
        # so the "thinking..." status indicator shows in the correct place - as the
        # next message in the conversation, right above the input - rather than at the
        # top of the page.
        with st.chat_message("user"):
            st.markdown(pending)
        with st.chat_message("assistant"):
            result = run_question(pending, conversation_history=st.session_state["conversation_history"])
            if "interrupt" in result:
                st.session_state["pending_approval"] = {**result, "question": pending}
                st.rerun()
            else:
                st.session_state["history"].append({"question": pending, **result})
                if "state" in result:
                    st.session_state["last_reasoning_log"] = result["state"].get("reasoning_log")
                if "error" in result:
                    render_error_card(pending, result["error"], show_question=False)
                else:
                    render_answer_card(result["state"])
                _remember(pending, result)
