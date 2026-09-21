from .. import llm_client, prompts
from ..state import AgentState
from ..utils import extract_json

VALID_QUERY_TYPES = {
    "graph_traversal", "inventory_lookup", "cost_analysis", "contract_status", "compound_multi_hop",
}
VALID_SIMULATION_TYPES = {"disruption", "capacity", "cost_impact", None}


def classify_query(state: AgentState) -> dict:
    result = llm_client.complete(
        system=prompts.CLASSIFY_SYSTEM,
        user=prompts.classify_user_prompt(state["question"], feedback=state.get("validation_feedback")),
        max_tokens=400,
    )

    try:
        parsed = extract_json(result.content)
        query_type = parsed.get("query_type") if parsed.get("query_type") in VALID_QUERY_TYPES else "compound_multi_hop"
        simulation_type = parsed.get("simulation_type")
        if simulation_type not in VALID_SIMULATION_TYPES:
            simulation_type = None
        requires_simulation = bool(parsed.get("requires_simulation")) and simulation_type is not None
        simulation_params = parsed.get("simulation_params") or {}
        parse_ok = True
    except (ValueError, KeyError):
        # Fail safe: treat as the most capable, if slowest, path rather than erroring out.
        query_type, requires_simulation, simulation_type, simulation_params = (
            "compound_multi_hop", False, None, {},
        )
        parse_ok = False

    return {
        "query_type": query_type,
        "requires_simulation": requires_simulation,
        "simulation_type": simulation_type,
        "simulation_params": simulation_params,
        # Clear any previous attempt's data so a retry down a different path (e.g. Postgres
        # instead of Neo4j) never leaves stale results for validate_results/synthesize to see.
        "cypher_query": None,
        "neo4j_result": None,
        "neo4j_error": None,
        "sql_query": None,
        "postgres_result": None,
        "postgres_error": None,
        "simulation_result": None,
        "validation_passed": True,
        "reasoning_log": [{
            "node": "classify_query",
            "engine_used": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "output": {"query_type": query_type, "requires_simulation": requires_simulation,
                       "simulation_type": simulation_type},
            "parse_ok": parse_ok,
        }],
    }
