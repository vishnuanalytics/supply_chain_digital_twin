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
    {"n_label": "RawMaterial", "n_id": "RM2", "n_name": "Steel Rod Stock", "n_props": {},
     "m_label": "Supplier", "m_id": "S1", "m_name": "Acme Metals", "m_props": {},
     "rel_type": "SOURCED_FROM", "r_props": {}},
]


def _mini_app(state: dict, card_key: str | None = None):
    from ui.answer_card import render_answer_card
    render_answer_card(state, card_key=card_key)


def _run(state: dict = SAMPLE_STATE, card_key: str | None = None) -> AppTest:
    with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
        at = AppTest.from_function(_mini_app, kwargs={"state": state, "card_key": card_key})
        at.run(timeout=30)
    return at


def _two_cards_app(state: dict):
    from ui.answer_card import render_answer_card
    render_answer_card(state, card_key="turn_0")
    render_answer_card(state, card_key="turn_1")


def _two_cards_app_no_keys(state: dict):
    # AppTest.from_function() execs only the function's own source text, isolated from
    # this module's globals - so `state` must be passed as a real argument (via
    # `kwargs=`), not referenced as a closure over a module-level constant.
    from ui.answer_card import render_answer_card
    render_answer_card(state)
    render_answer_card(state)


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


class TestCenterFitButton:
    """Real bug this button exists to work around: a Streamlit custom component's
    iframe negotiates its height once, at mount time - if it mounts while its expander
    ancestor is still collapsed, that negotiation measures a 0-height container and
    never re-fires, so the graph stays invisible even after the expander opens
    (confirmed live: iframe offsetHeight stuck at 0). Forcing a fresh `key` - which
    both opening the expander AND this button do - makes the component remount, and a
    remount that happens while the container is genuinely visible sizes correctly."""

    def test_button_appears_once_graph_trace_is_expanded_and_has_nodes(self):
        at = _run()
        graph_expander = next(e for e in at.expander if "graph trace" in e.label)
        graph_expander.expanded = True
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at.run(timeout=30)
        assert not at.exception
        labels = [b.label for b in at.button]
        assert any("Center / fit graph" in label for label in labels)

    def test_clicking_it_does_not_raise(self):
        at = _run()
        graph_expander = next(e for e in at.expander if "graph trace" in e.label)
        graph_expander.expanded = True
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at.run(timeout=30)

        fit_button = next(b for b in at.button if "Center / fit graph" in b.label)
        fit_button.click()
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at.run(timeout=30)
        assert not at.exception

    def test_no_button_when_the_answer_never_traversed_the_graph(self):
        state = {**SAMPLE_STATE, "neo4j_result": None}
        at = _run(state)
        graph_expander = next(e for e in at.expander if "graph trace" in e.label)
        graph_expander.expanded = True
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at.run(timeout=30)
        labels = [b.label for b in at.button]
        assert not any("Center / fit graph" in label for label in labels)


class TestCardKeyIsolation:
    """ui/tabs/ask.py's chat thread renders every turn's card on the same page at
    once, unlike the Billing tab's single drilldown - each card's expander/button keys
    must be unique per card or Streamlit raises a duplicate-widget-key error."""

    def test_two_cards_with_distinct_explicit_keys_render_together_without_raising(self):
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at = AppTest.from_function(_two_cards_app, kwargs={"state": SAMPLE_STATE})
            at.run(timeout=30)
        assert not at.exception
        assert len(at.expander) == 4  # 2 cards x (graph trace + reasoning)

    def test_two_identical_cards_with_no_explicit_key_collide(self):
        # Documents the real constraint (see render_answer_card's own docstring): the
        # auto-derived key is a hash of question+answer content, so two cards with
        # identical content and no explicit card_key DO collide - any caller that might
        # render more than one card on the same page (the Ask tab's chat history) must
        # pass its own unique key, which it does (see ui/tabs/ask.py's `card_key=`).
        with patch("agent.db.run_cypher", return_value=_MOCK_CYPHER_ROWS):
            at = AppTest.from_function(_two_cards_app_no_keys, kwargs={"state": SAMPLE_STATE})
            at.run(timeout=30)
        assert at.exception
        assert "multiple elements with the same" in at.exception[0].message
