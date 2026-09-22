"""Builds the LangGraph agent: classify -> (neo4j and/or postgres, a deterministic
simulation, or a local-embedding semantic search) -> [human_approval_gate] -> validate
-> synthesize, with a bounded retry loop back to classify_query when validation fails.

Routing:
  classify_query
    -> simulate_scenario                          if requires_simulation
    -> query_semantic                              if semantic_search
    -> query_neo4j                                if graph_traversal or compound_multi_hop
    -> query_postgres                              if inventory_lookup / cost_analysis / contract_status
  query_neo4j
    -> query_postgres                              if compound_multi_hop (need both stores)
    -> validate_results                            otherwise
  query_postgres -> validate_results
  query_semantic -> validate_results
  simulate_scenario -> human_approval_gate -> validate_results
    (human_approval_gate is a no-op pass-through unless a disruption sim found a
    high-risk material with a backup supplier on file - see agent/nodes/approval.py)
  validate_results
    -> synthesize                                  if valid, or retries exhausted (best effort)
    -> classify_query                              if invalid and retries remain (Corrective-RAG-style retry)
"""
import uuid

from langgraph.graph import END, StateGraph

from .checkpointer import get_checkpointer
from .nodes import (
    classify_query,
    human_approval_gate,
    query_neo4j_node,
    query_postgres_node,
    query_semantic_node,
    simulate_scenario_node,
    synthesize_node,
    validate_results_node,
)
from .nodes.validate import MAX_RETRIES
from .state import AgentState

POSTGRES_ONLY_TYPES = {"inventory_lookup", "cost_analysis", "contract_status"}


def _route_after_classify(state: AgentState) -> str:
    if state.get("requires_simulation"):
        return "simulate_scenario"
    if state.get("query_type") == "semantic_search":
        return "query_semantic"
    if state.get("query_type") in POSTGRES_ONLY_TYPES:
        return "query_postgres"
    return "query_neo4j"  # graph_traversal and compound_multi_hop both start in Neo4j


def _route_after_neo4j(state: AgentState) -> str:
    return "query_postgres" if state.get("query_type") == "compound_multi_hop" else "validate_results"


def _route_after_validate(state: AgentState) -> str:
    if state.get("validation_passed", True):
        return "synthesize"
    if state.get("retry_count", 0) > MAX_RETRIES:
        return "synthesize"  # give up and let synthesize give an honest, low-confidence answer
    return "classify_query"


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("classify_query", classify_query)
    builder.add_node("query_neo4j", query_neo4j_node)
    builder.add_node("query_postgres", query_postgres_node)
    builder.add_node("query_semantic", query_semantic_node)
    builder.add_node("simulate_scenario", simulate_scenario_node)
    builder.add_node("human_approval_gate", human_approval_gate)
    builder.add_node("validate_results", validate_results_node)
    builder.add_node("synthesize", synthesize_node)

    builder.set_entry_point("classify_query")
    builder.add_conditional_edges("classify_query", _route_after_classify, {
        "simulate_scenario": "simulate_scenario",
        "query_semantic": "query_semantic",
        "query_neo4j": "query_neo4j",
        "query_postgres": "query_postgres",
    })
    builder.add_conditional_edges("query_neo4j", _route_after_neo4j, {
        "query_postgres": "query_postgres",
        "validate_results": "validate_results",
    })
    builder.add_edge("query_postgres", "validate_results")
    builder.add_edge("query_semantic", "validate_results")
    builder.add_edge("simulate_scenario", "human_approval_gate")
    builder.add_edge("human_approval_gate", "validate_results")
    builder.add_conditional_edges("validate_results", _route_after_validate, {
        "synthesize": "synthesize",
        "classify_query": "classify_query",
    })
    builder.add_edge("synthesize", END)

    return builder.compile(checkpointer=get_checkpointer())


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def ask(
    question: str, thread_id: str | None = None, use_jev: bool = False,
    conversation_history: list[dict] | None = None,
) -> AgentState:
    thread_id = thread_id or str(uuid.uuid4())
    run_config = {"configurable": {"thread_id": thread_id}, "run_name": "ask_question"}
    return get_graph().invoke(
        {
            "question": question, "reasoning_log": [], "decision_log": [], "retry_count": 0,
            "use_jev": use_jev, "conversation_history": conversation_history or [],
        },
        run_config,
    )
