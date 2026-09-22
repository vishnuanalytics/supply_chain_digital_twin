"""The Ask tab's continuous-chat behaviour: asking a second question in the same
session must (a) render both turns in chronological (oldest-first) chat bubbles, not
a reversed stack of separate report cards, and (b) actually pass the first turn's Q&A
into the second call's conversation_history, so a follow-up like "what about the
second one?" can be resolved - not just visually plausible.

Uses Streamlit's AppTest with agent.graph's get_graph() mocked, so this needs no live
LLM/Neo4j/Postgres - see agent_runner.py's own note on why get_graph must be patched
via ui.agent_runner.get_graph (imported by name at module load), not agent.graph.get_graph.
"""
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest


def _mini_app():
    import streamlit as st

    from ui.sidebar import render_sidebar
    from ui.tabs.ask import render_ask_tab
    from ui.theme import inject_css

    st.set_page_config(page_title="test", layout="wide")
    inject_css()
    render_sidebar()
    render_ask_tab()


def _make_fake_graph(seen_conversation_histories, call_count):
    def fake_stream(initial_input, config, stream_mode="values"):
        call_count["n"] += 1
        question = initial_input.get("question")
        seen_conversation_histories.append(list(initial_input.get("conversation_history", [])))
        yield {
            "answer": f"Mock answer #{call_count['n']} for: {question}",
            "confidence": "high",
            "reasoning_log": [{"node": "synthesize", "engine_used": "mock", "latency_ms": 10}],
            "decision_log": [],
            "neo4j_result": None,
            "postgres_result": None,
            "semantic_result": None,
            "simulation_result": None,
            "question": question,
        }

    fake_graph = MagicMock()
    fake_graph.stream.side_effect = fake_stream
    return fake_graph


class TestContinuousChatFlow:
    def test_two_questions_render_as_one_chronological_thread_with_shared_context(self):
        seen_conversation_histories: list[list[dict]] = []
        call_count = {"n": 0}
        fake_graph = _make_fake_graph(seen_conversation_histories, call_count)

        with patch("ui.agent_runner.get_graph", return_value=fake_graph), \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_mini_app)
            at.run(timeout=30)
            assert not at.exception

            example_buttons = [b for b in at.button if b.key and b.key.startswith("example_")]
            assert len(example_buttons) == 6

            example_buttons[0].click().run(timeout=30)
            assert not at.exception

            # First question answered: exactly one user + one assistant bubble.
            assert [m.name for m in at.chat_message] == ["user", "assistant"]

            at.chat_input[0].set_value("What about the second one on that list?").run(timeout=30)
            assert not at.exception

            # Chronological (oldest first), not a reversed stack: user, assistant,
            # user, assistant - exactly the order a real chat thread would show.
            assert [m.name for m in at.chat_message] == ["user", "assistant", "user", "assistant"]

            # The graph was actually invoked twice, and the second call's
            # conversation_history genuinely carries the first turn's Q&A - this is
            # what makes a follow-up like "the second one" resolvable, not just a UI
            # that looks continuous.
            assert call_count["n"] == 2
            assert seen_conversation_histories[0] == []
            assert len(seen_conversation_histories[1]) == 1
            assert "Mock answer #1" in seen_conversation_histories[1][0]["answer"]

    def test_example_questions_hidden_once_a_conversation_has_started(self):
        seen_conversation_histories: list[list[dict]] = []
        call_count = {"n": 0}
        fake_graph = _make_fake_graph(seen_conversation_histories, call_count)

        with patch("ui.agent_runner.get_graph", return_value=fake_graph), \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_mini_app)
            at.run(timeout=30)
            example_buttons_before = [b for b in at.button if b.key and b.key.startswith("example_")]
            assert len(example_buttons_before) == 6

            example_buttons_before[0].click().run(timeout=30)

            example_buttons_after = [b for b in at.button if b.key and b.key.startswith("example_")]
            assert example_buttons_after == []
