"""Corrective-RAG-style self-correction gate: checks whether the retrieved data
actually answers the question before handing it to synthesize, and routes back to
classify_query with feedback for a bounded number of retries if not.
"""
from .. import llm_client, prompts
from ..state import AgentState
from ..utils import extract_json

MAX_RETRIES = 2


def _hard_error(state: AgentState) -> str | None:
    if state.get("neo4j_error"):
        return f"Graph query failed: {state['neo4j_error']}"
    if state.get("postgres_error"):
        return f"SQL query failed: {state['postgres_error']}"
    sim_error = (state.get("simulation_result") or {}).get("error")
    if sim_error:
        return f"Simulation failed: {sim_error}"
    if state.get("semantic_error"):
        return f"Semantic search failed: {state['semantic_error']}"
    return None


def validate_results_node(state: AgentState) -> dict:
    retry_count = state.get("retry_count", 0)

    # Cheap deterministic check first: an actual execution error is unambiguous and
    # doesn't need an LLM call to confirm it's worth retrying.
    error = _hard_error(state)
    if error:
        return {
            "validation_passed": False,
            "validation_feedback": error,
            "retry_count": retry_count + 1,
            "reasoning_log": [{
                "node": "validate_results", "engine_used": "deterministic",
                "valid": False, "reason": error, "retry_count": retry_count + 1,
            }],
        }

    # Otherwise, ask the LLM whether the (possibly empty) result plausibly answers the
    # question — empty/thin results are often correct real answers, not failures, so this
    # needs judgment rather than a blanket "empty == invalid" rule.
    try:
        result = llm_client.complete(
            system=prompts.VALIDATE_SYSTEM,
            user=prompts.validate_user_prompt(state),
            max_tokens=300,
        )
        parsed = extract_json(result.content)
        valid = bool(parsed.get("valid", True))
        reason = parsed.get("reason", "")
        log_entry = {
            "node": "validate_results", "engine_used": result.provider, "model": result.model,
            "latency_ms": result.latency_ms, "valid": valid, "reason": reason, "retry_count": retry_count,
        }
    except Exception as exc:  # noqa: BLE001 - fail open: a broken validator must not block the pipeline
        valid, reason = True, f"validator unavailable ({exc}); proceeding without a retry"
        log_entry = {
            "node": "validate_results", "engine_used": "none", "valid": True, "reason": reason,
            "retry_count": retry_count,
        }

    new_retry_count = retry_count if valid else retry_count + 1
    log_entry["retry_count"] = new_retry_count
    return {
        "validation_passed": valid,
        "validation_feedback": None if valid else reason,
        "retry_count": new_retry_count,
        "reasoning_log": [log_entry],
    }
