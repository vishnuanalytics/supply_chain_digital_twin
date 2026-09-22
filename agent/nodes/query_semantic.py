"""query_semantic: semantic search over free-text supplier/vendor notes (build step 8
extension). Only classify_query's routing decision needs an LLM here - the embedding
and the search itself both run locally, so this node works even when every configured
LLM provider is rate-limited.
"""
import time

from .. import semantic_search
from ..state import AgentState


def query_semantic_node(state: AgentState) -> dict:
    question = state.get("resolved_question") or state["question"]
    t0 = time.monotonic()
    try:
        results = semantic_search.search_supplier_notes(question)
        error = None
    except Exception as exc:  # noqa: BLE001 - surfaced to synthesize/validate, not fatal
        results, error = [], str(exc)
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    return {
        "semantic_result": results,
        "semantic_error": error,
        "reasoning_log": [{
            "node": "query_semantic",
            "engine_used": "local-embedding (all-MiniLM-L6-v2)",
            "latency_ms": latency_ms,
            "row_count": len(results),
            "error": error,
        }],
    }
