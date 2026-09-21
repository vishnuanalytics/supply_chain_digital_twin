"""Builds the LangGraph agent: classify -> (neo4j and/or postgres, or a
deterministic simulation) -> validate -> synthesize, with a bounded retry loop
back to classify_query when validation fails.

Routing:
  classify_query
    -> simulate_scenario                          if requires_simulation
    -> query_neo4j                                if graph_traversal or compound_multi_hop
    -> query_postgres                              if inventory_lookup / cost_analysis / contract_status
  query_neo4j
    -> query_postgres                              if compound_multi_hop (need both stores)
    -> validate_results                            otherwise
  query_postgres -> validate_results
  simulate_scenario -> validate_results
  validate_results
    -> synthesize                                  if valid, or retries exhausted (best effort)
    -> classify_query                              if invalid and retries remain (Corrective-RAG-style retry)
"""
from langgraph.graph import END, StateGraph

from .nodes import (
    classify_query,
    query_neo4j_node,
    query_postgres_node,
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
    builder.add_node("simulate_scenario", simulate_scenario_node)
    builder.add_node("validate_results", validate_results_node)
    builder.add_node("synthesize", synthesize_node)

    builder.set_entry_point("classify_query")
    builder.add_conditional_edges("classify_query", _route_after_classify, {
        "simulate_scenario": "simulate_scenario",
        "query_neo4j": "query_neo4j",
        "query_postgres": "query_postgres",
    })
    builder.add_conditional_edges("query_neo4j", _route_after_neo4j, {
        "query_postgres": "query_postgres",
        "validate_results": "validate_results",
    })
    builder.add_edge("query_postgres", "validate_results")
    builder.add_edge("simulate_scenario", "validate_results")
    builder.add_conditional_edges("validate_results", _route_after_validate, {
        "synthesize": "synthesize",
        "classify_query": "classify_query",
    })
    builder.add_edge("synthesize", END)

    return builder.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def ask(question: str) -> AgentState:
    return get_graph().invoke({"question": question, "reasoning_log": [], "retry_count": 0})
