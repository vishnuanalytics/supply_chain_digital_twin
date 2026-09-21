from .. import config, decision_engine, llm_client, prompts
from ..state import AgentState
from ..utils import extract_json


def classify_query(state: AgentState) -> dict:
    question = state["question"]
    feedback = state.get("validation_feedback")
    decision_log: list[dict] = []

    jev_decision = None
    if state.get("use_jev"):
        try:
            jev_decision = decision_engine.classify_via_jev(question, feedback)
            simulation_params = (
                decision_engine.extract_simulation_params(question, jev_decision.value["simulation_type"])
                if jev_decision.value["requires_simulation"] else {}
            )
        except Exception as exc:  # noqa: BLE001 - Jev must never be a hard dependency
            decision_log.append({
                "decision": "query_type", "value": None, "confidence": None,
                "engine_used": "jev", "latency_ms": None, "error": str(exc),
            })
            jev_decision = None

    if jev_decision is not None:
        query_type = jev_decision.value["query_type"]
        requires_simulation = jev_decision.value["requires_simulation"]
        simulation_type = jev_decision.value["simulation_type"]
        engine_used, model, latency_ms, parse_ok = "jev", config.TYPESAFE_MODEL, jev_decision.latency_ms, True
        decision_log.append({
            "decision": "query_type", "value": query_type, "confidence": jev_decision.confidence,
            "engine_used": jev_decision.engine_used, "latency_ms": jev_decision.latency_ms,
        })
    else:
        result = llm_client.complete(
            system=prompts.CLASSIFY_SYSTEM,
            user=prompts.classify_user_prompt(question, feedback=feedback),
            max_tokens=400,
        )
        try:
            parsed = extract_json(result.content)
            query_type = parsed.get("query_type") if parsed.get("query_type") in decision_engine.VALID_QUERY_TYPES else "compound_multi_hop"
            simulation_type = parsed.get("simulation_type")
            if simulation_type not in decision_engine.VALID_SIMULATION_TYPES:
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
        engine_used, model, latency_ms = result.provider, result.model, result.latency_ms
        decision_log.append({
            "decision": "query_type", "value": query_type, "confidence": None,
            "engine_used": f"claude:{engine_used}", "latency_ms": latency_ms,
        })

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
            "engine_used": engine_used,
            "model": model,
            "latency_ms": latency_ms,
            "output": {"query_type": query_type, "requires_simulation": requires_simulation,
                       "simulation_type": simulation_type},
            "parse_ok": parse_ok,
        }],
        "decision_log": decision_log,
    }
