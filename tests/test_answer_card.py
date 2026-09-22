"""ui/answer_card.py's collapsed layers: "Show graph trace" and "Show reasoning" must
both render collapsed by default, so the primary answer text stays the focal point -
the graph trace used to render inline/always-open, moved behind its own expander on
direct user request ("Can you add drop down option for the knowledge graph trace to
like, show reasoning"). Uses AppTest with agent.db.run_cypher mocked (the graph trace's
one live dependency) rather than a real Neo4j call, so this needs no live credentials.
"""
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

SAMPLE_STATE = {
    "answer": "There are 7 raw materials with only one supplier.",
    "confidence": "high",
    "neo4j_result": [{"raw_material_id": "RM2", "raw_material_name": "Steel Rod Stock"}],
    "postgres_result": None,
    "semantic_result": None,
    "simulation_result": None,
    "reasoning_log": [{"node": "synthesize", "engine_used": "groq", "latency_ms": 500}],
    "decision_log": [],
    "resolved_question": None,
    "question": "Which raw materials have only one supplier?",
}

_MOCK_CYPHER_ROWS = [
    {"a_label": "RawMaterial", "a": {"id": "RM2", "name": "Steel Rod Stock"},
     "b_label": None, "b": None, "rel_type": None, "rel_props": None},
]


def _mini_app(state: dict):
    from ui.answer_card import render_answer_card
    render_answer_card(state)


def _run(state: dict = SAMPLE_STATE) -> AppTest:
    with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
        at = AppTest.from_function(_mini_app, kwargs={"state": state})
        at.run(timeout=30)
    return at


class TestCollapsedLayers:
    def test_renders_with_no_exception(self):
        at = _run()
        assert not at.exception

    def test_both_graph_trace_and_reasoning_are_expanders(self):
        at = _run()
        labels = {e.label for e in at.expander}
        assert "🕸️ Show graph trace" in labels
        assert "🔍 Show reasoning" in labels

    def test_both_expanders_start_collapsed(self):
        at = _run()
        for e in at.expander:
            assert e.proto.expanded is False

    def test_expanding_graph_trace_does_not_raise(self):
        at = _run()
        graph_expander = next(e for e in at.expander if "graph trace" in e.label)
        graph_expander.expanded = True
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at.run(timeout=30)
        assert not at.exception

    def test_no_neo4j_result_shows_the_not_traversed_caption(self):
        state = {**SAMPLE_STATE, "neo4j_result": None}
        at = _run(state)
        graph_expander = next(e for e in at.expander if "graph trace" in e.label)
        graph_expander.expanded = True
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at.run(timeout=30)
        assert not at.exception
        captions = [c.value for c in at.caption]
        assert any("didn't traverse the graph directly" in c for c in captions)
