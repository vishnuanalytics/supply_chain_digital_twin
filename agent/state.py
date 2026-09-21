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

    # read by classify_query/human_approval_gate; set once at graph invocation from the UI's
    # "Use Jev for fast decisions" toggle (see agent/decision_engine.py)
    use_jev: Optional[bool]

    # set by human_approval_gate when a high-stakes recommendation was found and (dis)approved;
    # both stay None for the (overwhelming majority of) questions with no such recommendation
    pending_action: Optional[dict]
    action_decision: Optional[dict]  # {"approved": bool, "note": str}

    # set by synthesize
    answer: Optional[str]
    confidence: Optional[str]  # high | estimated | low

    # appended to by every node: {node, provider, model, latency_ms, ...}
    reasoning_log: Annotated[list[dict], operator.add]

    # appended to by classify_query (and human_approval_gate's pre-checks, if any) whenever a
    # decision-engine-eligible choice was made: {decision, value, confidence, engine_used, latency_ms}
    decision_log: Annotated[list[dict], operator.add]
