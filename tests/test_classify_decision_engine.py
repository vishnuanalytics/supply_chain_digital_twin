"""agent/nodes/classify.py + agent/decision_engine.py: the Jev fast-path and its
fallback to the full Claude/Groq classify call. This is the control-flow this project's
Jev toggle depends on entirely - Jev must never be a hard dependency, so "Jev raises"
falling through cleanly is the single most important behavior to pin down with a test.
"""
from unittest.mock import patch

from agent.decision_engine import DecisionResult
from agent.llm_client import LLMResult
from agent.nodes.classify import classify_query


def _claude_result(content: str) -> LLMResult:
    return LLMResult(content=content, provider="groq", model="test-model", latency_ms=42.0)


class TestClassifyQueryJevPath:
    def test_use_jev_false_never_calls_jev(self):
        with patch("agent.nodes.classify.decision_engine.classify_via_jev") as mock_jev, \
             patch("agent.nodes.classify.llm_client.complete") as mock_complete:
            mock_complete.return_value = _claude_result(
                '{"query_type": "graph_traversal", "requires_simulation": false, '
                '"simulation_type": null, "simulation_params": {}, "reasoning": "x"}'
            )
            result = classify_query({"question": "which materials have one supplier?", "use_jev": False})
            assert result["query_type"] == "graph_traversal"
            assert result["decision_log"][0]["engine_used"] == "claude:groq"
            mock_jev.assert_not_called()

    def test_jev_success_without_simulation_skips_claude_entirely(self):
        with patch("agent.nodes.classify.decision_engine.classify_via_jev") as mock_jev, \
             patch("agent.nodes.classify.llm_client.complete") as mock_complete:
            mock_jev.return_value = DecisionResult(
                value={"query_type": "inventory_lookup", "requires_simulation": False, "simulation_type": None},
                confidence={"query_type": 0.9}, engine_used="jev", latency_ms=95.0,
            )
            result = classify_query({"question": "what's the stock level of RM3?", "use_jev": True})
            assert result["query_type"] == "inventory_lookup"
            assert result["decision_log"][0]["engine_used"] == "jev"
            mock_complete.assert_not_called()

    def test_jev_success_with_simulation_only_extracts_params_via_claude(self):
        with patch("agent.nodes.classify.decision_engine.classify_via_jev") as mock_jev, \
             patch("agent.nodes.classify.decision_engine.extract_simulation_params") as mock_params, \
             patch("agent.nodes.classify.llm_client.complete") as mock_complete:
            mock_jev.return_value = DecisionResult(
                value={"query_type": "compound_multi_hop", "requires_simulation": True, "simulation_type": "disruption"},
                confidence={"query_type": 0.8}, engine_used="jev", latency_ms=110.0,
            )
            mock_params.return_value = {"entity_name": "aluminum", "entity_type": "supplier", "delay_days": 21}
            result = classify_query({"question": "our aluminum supplier had a delay", "use_jev": True})
            assert result["requires_simulation"] is True
            assert result["simulation_params"]["entity_name"] == "aluminum"
            mock_params.assert_called_once()
            mock_complete.assert_not_called()  # the full classify call is skipped, only the scoped one runs

    def test_jev_failure_falls_back_to_claude_and_logs_both_attempts(self):
        with patch("agent.nodes.classify.decision_engine.classify_via_jev") as mock_jev, \
             patch("agent.nodes.classify.llm_client.complete") as mock_complete:
            mock_jev.side_effect = RuntimeError("TYPESAFE_API_KEY not set")
            mock_complete.return_value = _claude_result(
                '{"query_type": "contract_status", "requires_simulation": false, '
                '"simulation_type": null, "simulation_params": {}, "reasoning": "x"}'
            )
            result = classify_query({"question": "which contracts expire soon?", "use_jev": True})
            assert result["query_type"] == "contract_status"
            assert len(result["decision_log"]) == 2
            assert result["decision_log"][0]["error"] == "TYPESAFE_API_KEY not set"
            assert result["decision_log"][1]["engine_used"] == "claude:groq"

    def test_malformed_claude_json_fails_safe_to_compound_multi_hop(self):
        with patch("agent.nodes.classify.llm_client.complete") as mock_complete:
            mock_complete.return_value = _claude_result("not valid json at all")
            result = classify_query({"question": "anything", "use_jev": False})
            assert result["query_type"] == "compound_multi_hop"
            assert result["requires_simulation"] is False

    def test_classify_clears_stale_state_from_a_previous_attempt(self):
        with patch("agent.nodes.classify.llm_client.complete") as mock_complete:
            mock_complete.return_value = _claude_result(
                '{"query_type": "graph_traversal", "requires_simulation": false, '
                '"simulation_type": null, "simulation_params": {}, "reasoning": "x"}'
            )
            result = classify_query({"question": "x", "use_jev": False})
            for key in ("cypher_query", "neo4j_result", "neo4j_error", "sql_query", "postgres_result",
                        "postgres_error", "simulation_result"):
                assert result[key] is None
