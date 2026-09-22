"""agent/semantic_search.py + agent/nodes/query_semantic.py: the local-embedding search
path. The embedding model itself isn't mocked-around in every test (it's real, local,
free, and fast - no reason to fake it), but the DB call is, so these stay fast/offline
like the rest of the suite; one test uses the real model end-to-end to catch a genuine
integration break between _embed()'s output format and how it's used in SQL.
"""
from unittest.mock import patch

from agent.nodes.query_semantic import query_semantic_node
from agent.semantic_search import _embed, search_supplier_notes


class TestEmbed:
    def test_returns_a_pgvector_literal_string(self):
        result = _embed("quality certification issues")
        assert result.startswith("[")
        assert result.endswith("]")
        # 384 dims, comma-separated
        assert result.count(",") == 383

    def test_is_deterministic(self):
        assert _embed("same text") == _embed("same text")

    def test_different_text_gives_different_embedding(self):
        assert _embed("product recall") != _embed("financial stability")


class TestSearchSupplierNotes:
    def test_builds_a_vector_cast_query_with_the_embedding_and_limit(self):
        with patch("agent.semantic_search.db.run_sql") as mock_sql, \
             patch("agent.semantic_search._embed", return_value="[0.1,0.2]"):
            mock_sql.return_value = [{"supplier_id": "S1", "similarity": 0.9}]
            result = search_supplier_notes("quality issues", k=3)
            query, params = mock_sql.call_args[0]
            assert "::vector" in query
            assert "supplier_notes" in query
            assert params == ("[0.1,0.2]", "[0.1,0.2]", 3)
            assert result == [{"supplier_id": "S1", "similarity": 0.9}]

    def test_real_embedding_round_trips_through_a_real_query_shape(self):
        # Not mocked - confirms _embed()'s literal format is actually valid to
        # interpolate as a query parameter (a real, if slow, integration check that a
        # future change to the literal's formatting doesn't silently break the SQL).
        with patch("agent.semantic_search.db.run_sql") as mock_sql:
            mock_sql.return_value = []
            search_supplier_notes("test question")
            vector_literal = mock_sql.call_args[0][1][0]
            assert vector_literal.startswith("[") and vector_literal.endswith("]")
            values = vector_literal[1:-1].split(",")
            assert len(values) == 384
            for v in values:
                float(v)  # every component must parse as a plain float


class TestQuerySemanticNode:
    def test_success_returns_results_and_logs_row_count(self):
        with patch("agent.nodes.query_semantic.semantic_search.search_supplier_notes") as mock_search:
            mock_search.return_value = [{"supplier_id": "S1", "similarity": 0.8}]
            result = query_semantic_node({"question": "any quality concerns?"})
            assert result["semantic_result"] == [{"supplier_id": "S1", "similarity": 0.8}]
            assert result["semantic_error"] is None
            assert result["reasoning_log"][0]["row_count"] == 1
            assert result["reasoning_log"][0]["node"] == "query_semantic"

    def test_uses_resolved_question_when_present(self):
        with patch("agent.nodes.query_semantic.semantic_search.search_supplier_notes") as mock_search:
            mock_search.return_value = []
            query_semantic_node({
                "question": "any concerns about it?",
                "resolved_question": "any concerns about Great Lakes Steel Co?",
            })
            mock_search.assert_called_once_with("any concerns about Great Lakes Steel Co?")

    def test_failure_is_caught_and_reported_not_raised(self):
        with patch("agent.nodes.query_semantic.semantic_search.search_supplier_notes") as mock_search:
            mock_search.side_effect = RuntimeError("connection refused")
            result = query_semantic_node({"question": "any quality concerns?"})
            assert result["semantic_result"] == []
            assert "connection refused" in result["semantic_error"]
