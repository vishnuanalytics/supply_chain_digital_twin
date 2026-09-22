"""The exact-match answer cache: agent/db.py's _cache_key/get_cached_answer/
cache_answer/invalidate_query_cache, and ui/agent_runner.run_question()'s use of them.

Deliberately exact-match only, never semantic/fuzzy - see query_cache's own comment in
postgres/schema.sql for why. These tests cover both the normalization rules (case/
whitespace-insensitive, never meaning-insensitive) and the two safety properties that
matter most: a question asked with conversation context is never cached or served from
cache, and only a successfully-answered question is ever cached (never an error or a
paused interrupt).
"""
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from agent import db


def _ask_mini_app():
    import streamlit as st

    from ui.sidebar import render_sidebar
    from ui.tabs.ask import render_ask_tab
    from ui.theme import inject_css

    st.set_page_config(page_title="test", layout="wide")
    inject_css()
    render_sidebar()
    render_ask_tab()


def _fake_graph(answer_text: str, question_key: str = "question"):
    def fake_stream(initial_input, config, stream_mode="values"):
        yield {
            "answer": answer_text, "confidence": "high", "reasoning_log": [], "decision_log": [],
            "neo4j_result": None, "postgres_result": None, "semantic_result": None,
            "simulation_result": None, question_key: initial_input.get("question"),
        }

    graph = MagicMock()
    graph.stream.side_effect = fake_stream
    return graph


class TestCacheKey:
    def test_same_question_different_case_and_whitespace_produces_the_same_key(self):
        assert db._cache_key("How many suppliers do we have?") == db._cache_key(
            "  how many suppliers do we have?  "
        )
        assert db._cache_key("How many suppliers do we have?") == db._cache_key(
            "how   many suppliers do we have?"
        )

    def test_different_questions_produce_different_keys(self):
        # The exact case this cache must never confuse - two different questions that
        # would likely embed very close together under a semantic/fuzzy match.
        assert db._cache_key("What's the price of RM1?") != db._cache_key("What's the price of RM2?")


class TestGetCachedAnswer:
    def test_returns_state_json_on_a_hit(self):
        with patch("agent.db.run_sql", return_value=[{"state_json": {"answer": "6 suppliers."}}]) as mock_run_sql:
            result = db.get_cached_answer("How many suppliers do we have?")
        assert result == {"answer": "6 suppliers."}
        query, params = mock_run_sql.call_args[0]
        assert "WHERE cache_key = %s" in query
        assert params == (db._cache_key("How many suppliers do we have?"),)

    def test_returns_none_on_a_miss(self):
        with patch("agent.db.run_sql", return_value=[]):
            assert db.get_cached_answer("Never asked before") is None


class TestCacheAnswer:
    def test_upserts_by_cache_key_with_json_serialized_state(self):
        import json

        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with patch("agent.db.get_postgres_connection", return_value=conn):
            db.cache_answer("How many suppliers?", {"answer": "6", "confidence": "high"})

        cursor.execute.assert_called_once()
        query, params = cursor.execute.call_args[0]
        assert "ON CONFLICT" in query
        cache_key, question, state_json = params
        assert cache_key == db._cache_key("How many suppliers?")
        assert question == "How many suppliers?"
        assert json.loads(state_json) == {"answer": "6", "confidence": "high"}
        conn.commit.assert_called_once()
        conn.close.assert_called_once()


class TestInvalidateQueryCache:
    def test_truncates_the_table(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with patch("agent.db.get_postgres_connection", return_value=conn):
            db.invalidate_query_cache()
        cursor.execute.assert_called_once_with("TRUNCATE query_cache")
        conn.commit.assert_called_once()


class TestRunQuestionCacheBehavior:
    """Driven through the Ask tab via AppTest (not a direct run_question() call) -
    st.status()'s .update() needs a real Streamlit script-run context to work, same
    reason test_ask_tab_chat_flow.py uses AppTest rather than calling run_question()
    bare."""

    def test_cache_hit_skips_the_graph_and_makes_no_llm_call(self):
        cached_state = {
            "answer": "6 suppliers.", "confidence": "high", "reasoning_log": [], "decision_log": [],
            "neo4j_result": None, "postgres_result": None, "semantic_result": None,
            "simulation_result": None, "question": "How many suppliers do we have?",
        }
        fake_graph = MagicMock()
        with patch("ui.agent_runner.get_graph", return_value=fake_graph), \
             patch("agent.db.get_cached_answer", return_value=cached_state) as mock_get_cached, \
             patch("agent.db.cache_answer") as mock_cache_answer, \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_ask_mini_app)
            at.run(timeout=30)
            at.chat_input[0].set_value("How many suppliers do we have?").run(timeout=30)
            assert not at.exception

            mock_get_cached.assert_called_once_with("How many suppliers do we have?")
            fake_graph.stream.assert_not_called()
            mock_cache_answer.assert_not_called()
            assert [m.name for m in at.chat_message] == ["user", "assistant"]

    def test_cache_miss_runs_the_graph_and_then_caches_the_result(self):
        fake_graph = _fake_graph("6 suppliers.")
        with patch("ui.agent_runner.get_graph", return_value=fake_graph), \
             patch("agent.db.get_cached_answer", return_value=None) as mock_get_cached, \
             patch("agent.db.cache_answer") as mock_cache_answer, \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_ask_mini_app)
            at.run(timeout=30)
            at.chat_input[0].set_value("How many suppliers do we have?").run(timeout=30)
            assert not at.exception

            mock_get_cached.assert_called_once_with("How many suppliers do we have?")
            fake_graph.stream.assert_called_once()
            mock_cache_answer.assert_called_once()
            cached_question, cached_state = mock_cache_answer.call_args[0]
            assert cached_question == "How many suppliers do we have?"
            assert cached_state["answer"] == "6 suppliers."

    def test_a_followup_question_with_conversation_history_is_never_cached_or_served_from_cache(self):
        fake_graph = _fake_graph("First answer.")
        with patch("ui.agent_runner.get_graph", return_value=fake_graph), \
             patch("agent.db.get_cached_answer", return_value=None) as mock_get_cached, \
             patch("agent.db.cache_answer") as mock_cache_answer, \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_ask_mini_app)
            at.run(timeout=30)
            at.chat_input[0].set_value("Who supplies RM3?").run(timeout=30)
            assert not at.exception
            # First (standalone) turn: cache checked and written, as usual.
            assert mock_get_cached.call_count == 1
            assert mock_cache_answer.call_count == 1

            mock_get_cached.reset_mock()
            mock_cache_answer.reset_mock()
            at.chat_input[0].set_value("what about its backup supplier?").run(timeout=30)
            assert not at.exception

            # Second turn has real conversation_history behind it - never touches the
            # cache in either direction, since the same question text could mean
            # something different depending on what came before it.
            mock_get_cached.assert_not_called()
            mock_cache_answer.assert_not_called()

    def test_an_errored_question_is_not_cached(self):
        fake_graph = MagicMock()
        fake_graph.stream.side_effect = RuntimeError("provider down")
        with patch("ui.agent_runner.get_graph", return_value=fake_graph), \
             patch("agent.db.get_cached_answer", return_value=None), \
             patch("agent.db.cache_answer") as mock_cache_answer, \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_ask_mini_app)
            at.run(timeout=30)
            at.chat_input[0].set_value("How many suppliers do we have?").run(timeout=30)
            assert not at.exception

            mock_cache_answer.assert_not_called()


class TestGraphImportInvalidatesCache:
    def test_a_successful_import_clears_the_answer_cache(self):
        from ui.graph_import_export import import_graph_json

        with patch("agent.db.upsert_node", return_value="S9"), \
             patch("ui.graph_import_export.fetch_full_graph"), \
             patch("ui.graph_import_export.export_graph_json"), \
             patch("ui.graph_import_export._graph_counts"), \
             patch("agent.db.invalidate_query_cache") as mock_invalidate:
            import_graph_json(
                '{"nodes": [{"label": "Supplier", "properties": {"id": "S9", "name": "New Co"}}]}'
            )
        mock_invalidate.assert_called_once()

    def test_an_import_where_nothing_actually_changed_does_not_touch_the_cache(self):
        from ui.graph_import_export import import_graph_json

        with patch("agent.db.invalidate_query_cache") as mock_invalidate:
            import_graph_json('{"nodes": [{"label": "NotARealLabel", "properties": {"id": "X"}}]}')
        mock_invalidate.assert_not_called()
