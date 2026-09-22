"""Persistent sidebar: a ChatGPT-style conversation list (new chat + past sessions,
always visible - not tucked behind a popover you have to open), live graph stats, the
"Use Jev for fast decisions" toggle (build step 8), and the previous query's
engine/latency breakdown.
"""
import uuid

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


def new_chat_session() -> None:
    """Starts a fresh conversation - a new session_id means new turns persist as a
    separate row group in chat_history rather than continuing the old session."""
    st.session_state["history"] = []
    st.session_state["conversation_history"] = []
    st.session_state["session_id"] = str(uuid.uuid4())
    st.session_state.pop("pending_approval", None)


def load_chat_session(session_id: str) -> None:
    """Reconstructs `history`/`conversation_history` from a persisted session so its
    cards render exactly as they did live (state_json is the same dict render_answer_card
    already knows how to render). Sets session_id to the loaded session rather than a
    fresh one, so continuing to chat appends new turns to this same persisted session -
    like clicking a past chat in ChatGPT's sidebar, this resumes it rather than just
    showing a read-only snapshot."""
    rows = db.get_chat_session(session_id)
    history = []
    conversation_history = []
    for row in rows:
        state = row["state_json"] or {}
        history.append({"question": row["question"], "state": state})
        answer = state.get("answer")
        if answer:
            conversation_history.append({"question": row["question"], "answer": answer})
    st.session_state["history"] = history
    st.session_state["conversation_history"] = conversation_history
    st.session_state["session_id"] = session_id
    st.session_state.pop("pending_approval", None)


def _render_conversations() -> None:
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("conversation_history", [])

    st.markdown("### 💬 Conversations")
    if st.button("➕ New chat", width="stretch", key="sidebar_new_chat"):
        new_chat_session()
        st.rerun()

    try:
        sessions = db.list_chat_sessions(limit=20)
    except Exception:
        sessions = []

    if not sessions:
        st.caption("No past conversations yet - ask a question to start one.")
        return

    current = st.session_state.get("session_id")
    for s in sessions:
        label = s["first_question"]
        if len(label) > 36:
            label = label[:36] + "..."
        is_current = s["session_id"] == current
        if st.button(
            ("▸ " if is_current else "") + label,
            key=f"sidebar_session_{s['session_id']}",
            width="stretch",
            disabled=is_current,
            help=f"{s['turn_count']} turn(s) · last active {s['last_activity']:%Y-%m-%d %H:%M}",
        ):
            load_chat_session(s["session_id"])
            st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## Supply Chain Digital Twin")
        st.caption("Ask plain-English questions about the supply chain - no SQL or Cypher required.")

        _render_conversations()

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
