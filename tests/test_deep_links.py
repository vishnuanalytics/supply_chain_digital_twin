"""URL query-param deep-linking, added alongside the migration off st.tabs() to
st.navigation() (real per-tab URLs instead of one flat URL with no sub-paths):
  - ?q=<question>          - ui/tabs/ask.py auto-submits it, then clears it from the URL
  - ?session=<uuid>        - ui/sidebar.py loads that specific past conversation
  - ?node=<id>             - ui/tabs/graph_explorer.py opens straight into that node's focus view

Uses Streamlit's AppTest with the relevant DB/graph calls mocked, so this needs no live
LLM/Neo4j/Postgres credentials.
"""
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest


def _ask_mini_app():
    import streamlit as st

    from ui.sidebar import render_sidebar
    from ui.tabs.ask import render_ask_tab
    from ui.theme import inject_css

    st.set_page_config(page_title="test", layout="wide")
    inject_css()
    render_sidebar()
    render_ask_tab()


def _graph_explorer_mini_app():
    import streamlit as st

    from ui.tabs.graph_explorer import render_graph_explorer_tab
    from ui.theme import inject_css

    st.set_page_config(page_title="test", layout="wide")
    inject_css()
    render_graph_explorer_tab()


def _make_fake_graph():
    def fake_stream(initial_input, config, stream_mode="values"):
        yield {
            "answer": f"Mock answer for: {initial_input.get('question')}",
            "confidence": "high",
            "reasoning_log": [{"node": "synthesize", "engine_used": "mock", "latency_ms": 10}],
            "decision_log": [], "neo4j_result": None, "postgres_result": None,
            "semantic_result": None, "simulation_result": None,
            "question": initial_input.get("question"),
        }

    fake_graph = MagicMock()
    fake_graph.stream.side_effect = fake_stream
    return fake_graph


class TestQuestionDeepLink:
    def test_q_param_is_auto_submitted_and_then_cleared_from_the_url(self):
        with patch("ui.agent_runner.get_graph", return_value=_make_fake_graph()), \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_ask_mini_app)
            at.query_params["q"] = "Which raw materials have only one supplier?"
            at.run(timeout=30)
            assert not at.exception

            assert [m.name for m in at.chat_message] == ["user", "assistant"]
            assert at.chat_message[0].markdown[0].value == "Which raw materials have only one supplier?"
            # Consumed once - must not linger in the URL, or refreshing/re-running
            # would keep re-asking the same question forever.
            assert "q" not in at.query_params

    def test_no_q_param_shows_the_normal_empty_state(self):
        with patch("ui.agent_runner.get_graph", return_value=_make_fake_graph()), \
             patch("agent.db.log_chat_turn"), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]):

            at = AppTest.from_function(_ask_mini_app)
            at.run(timeout=30)
            assert not at.exception
            assert at.chat_message == []


class TestSessionDeepLink:
    def test_session_param_loads_that_specific_past_conversation(self):
        past_rows = [
            {"question": "How many suppliers do we have?",
             "state_json": {"answer": "6 suppliers.", "confidence": "high"},
             "created_at": "2026-09-20"},
        ]
        with patch("agent.db.get_chat_session", return_value=past_rows), \
             patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]), \
             patch("agent.db.log_chat_turn"):

            at = AppTest.from_function(_ask_mini_app)
            at.query_params["session"] = "shared-session-id"
            at.run(timeout=30)
            assert not at.exception

            assert at.session_state["session_id"] == "shared-session-id"
            assert len(at.session_state["history"]) == 1
            assert at.session_state["history"][0]["question"] == "How many suppliers do we have?"

    def test_no_session_param_starts_a_fresh_session_and_writes_it_back_to_the_url(self):
        with patch("agent.db.list_chat_sessions", return_value=[]), \
             patch("agent.db.run_cypher", return_value=[{"n": 0}]), \
             patch("agent.db.log_chat_turn"):

            at = AppTest.from_function(_ask_mini_app)
            at.run(timeout=30)
            assert not at.exception

            assert at.session_state["history"] == []
            # A fresh session_id was generated and written back into the URL, so the
            # very first load is already a shareable/bookmarkable link. AppTest's
            # query_params mirrors real query-string semantics (list-valued per key),
            # unlike the real st.query_params proxy's single-value convenience.
            assert at.query_params.get("session") == [at.session_state["session_id"]]


class TestGraphNodeDeepLink:
    def test_node_param_opens_directly_into_that_nodes_focus_view(self):
        from streamlit_agraph import Node

        # Mocked at the ui.tabs.graph_explorer level (not the underlying Cypher) -
        # these are imported by name into that module, so patching agent.db.run_cypher
        # wouldn't reach them anyway (same gotcha class as llm_client._PROVIDER_FNS).
        # agent.db.run_cypher itself is ALSO mocked - render_graph_explorer_tab() calls
        # render_import_export_section() (ui/graph_import_export.py's export_graph_json,
        # a real live Neo4j call) before ever reaching the focus-view code under test;
        # missing this made the test pass locally only because real .env credentials
        # were present, while CI (correctly, by design - no live credentials) failed on
        # it - every live call path this function takes needs mocking, not just the one
        # this test cares about.
        full_graph_nodes = [Node(id="RM3", label="Aluminum Alloy Billet", size=16, color="#EF4444")]
        with patch("ui.tabs.graph_explorer.fetch_full_graph", return_value=(full_graph_nodes, [])), \
             patch(
                 "ui.tabs.graph_explorer.fetch_node_neighborhood",
                 return_value=(full_graph_nodes, [], "Aluminum Alloy Billet"),
             ), \
             patch("agent.db.run_cypher", return_value=[]):
            at = AppTest.from_function(_graph_explorer_mini_app)
            at.query_params["node"] = "RM3"
            at.run(timeout=30)
            assert not at.exception

            assert at.session_state["graph_focus_node"] == "RM3"
            markdowns = [m.value for m in at.markdown]
            assert any("Aluminum Alloy Billet" in m for m in markdowns)
            assert at.query_params.get("node") == ["RM3"]
