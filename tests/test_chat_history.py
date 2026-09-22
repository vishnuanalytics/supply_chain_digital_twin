"""agent/db.py's chat_history persistence: log_chat_turn/list_chat_sessions/
get_chat_session. No live database needed - these tests mock get_postgres_connection
(for the write path) and run_sql (for the two read paths), the same pattern
test_db_safety.py uses for upsert_node/upsert_edge.
"""
import json
from unittest.mock import MagicMock, patch

from agent import db


class TestLogChatTurn:
    def test_writes_session_id_question_and_json_serialized_state(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with patch("agent.db.get_postgres_connection", return_value=conn):
            db.log_chat_turn("sess-1", "What is X?", {"answer": "X is Y", "confidence": "high"})

        cursor.execute.assert_called_once()
        query, params = cursor.execute.call_args[0]
        assert "INSERT INTO chat_history" in query
        session_id, question, state_json = params
        assert session_id == "sess-1"
        assert question == "What is X?"
        assert json.loads(state_json) == {"answer": "X is Y", "confidence": "high"}
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_serializes_non_json_native_values_via_default_str(self):
        # Postgres rows surfaced into `state` can carry Decimal/date values - these
        # aren't natively JSON-serializable, so log_chat_turn must fall back to str()
        # rather than raising.
        import datetime
        from decimal import Decimal

        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        state = {"answer": "42", "total": Decimal("42.50"), "as_of": datetime.date(2026, 1, 1)}
        with patch("agent.db.get_postgres_connection", return_value=conn):
            db.log_chat_turn("sess-1", "How much?", state)

        _, params = cursor.execute.call_args[0]
        stored = json.loads(params[2])
        assert stored["total"] == "42.50"
        assert stored["as_of"] == "2026-01-01"

    def test_closes_connection_even_if_execute_raises(self):
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value.execute.side_effect = RuntimeError("boom")
        with patch("agent.db.get_postgres_connection", return_value=conn):
            try:
                db.log_chat_turn("sess-1", "q", {"answer": "a"})
            except RuntimeError:
                pass
        conn.close.assert_called_once()


class TestListChatSessions:
    def test_queries_grouped_by_session_ordered_by_recency_with_limit(self):
        with patch("agent.db.run_sql", return_value=[]) as mock_run_sql:
            db.list_chat_sessions(limit=5)

        query, params = mock_run_sql.call_args[0]
        assert "GROUP BY session_id" in query
        assert "ORDER BY last_activity DESC" in query
        assert params == (5,)

    def test_returns_rows_from_run_sql_unchanged(self):
        rows = [{"session_id": "s1", "first_question": "hi", "turn_count": 2, "last_activity": "t"}]
        with patch("agent.db.run_sql", return_value=rows):
            result = db.list_chat_sessions()
        assert result == rows


class TestGetChatSession:
    def test_queries_by_session_id_ordered_oldest_first(self):
        with patch("agent.db.run_sql", return_value=[]) as mock_run_sql:
            db.get_chat_session("sess-1")

        query, params = mock_run_sql.call_args[0]
        assert "WHERE session_id = %s" in query
        assert "ORDER BY created_at ASC" in query
        assert params == ("sess-1",)

    def test_returns_rows_from_run_sql_unchanged(self):
        rows = [{"question": "q1", "state_json": {"answer": "a1"}, "created_at": "t1"}]
        with patch("agent.db.run_sql", return_value=rows):
            result = db.get_chat_session("sess-1")
        assert result == rows
