"""Shared state passed between LangGraph nodes."""
import operator
from typing import Annotated, Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    question: str

    # set by classify_query
    query_type: str  # graph_traversal | inventory_lookup | cost_analysis | contract_status | compound_multi_hop
    requires_simulation: bool
    simulation_type: Optional[str]  # disruption | capacity | cost_impact
    simulation_params: dict

    # set by query_neo4j
    cypher_query: Optional[str]
    neo4j_result: Optional[list[dict]]
    neo4j_error: Optional[str]

    # set by query_postgres
    sql_query: Optional[str]
    postgres_result: Optional[list[dict]]
    postgres_error: Optional[str]

    # set by simulate_scenario
    simulation_result: Optional[dict[str, Any]]

    # set by validate_results; feedback (if any) is read back by classify_query/query_neo4j/
    # query_postgres on a retry so the regenerated query actually tries something different
    validation_passed: bool
    validation_feedback: Optional[str]
    retry_count: int

    # set by synthesize
    answer: Optional[str]
    confidence: Optional[str]  # high | estimated | low

    # appended to by every node: {node, provider, model, latency_ms, ...}
    reasoning_log: Annotated[list[dict], operator.add]
