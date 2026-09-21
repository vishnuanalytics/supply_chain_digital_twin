from .. import db, llm_client, prompts
from ..state import AgentState
from ..utils import strip_code_fence


def query_neo4j_node(state: AgentState) -> dict:
    result = llm_client.complete(
        system=prompts.CYPHER_SYSTEM,
        user=prompts.cypher_user_prompt(state["question"]),
        max_tokens=500,
    )
    cypher = strip_code_fence(result.content)

    neo4j_result, error = None, None
    try:
        neo4j_result = db.run_cypher(cypher)
    except Exception as exc:  # noqa: BLE001 - surfaced to synthesize/validate, not fatal
        error = str(exc)

    return {
        "cypher_query": cypher,
        "neo4j_result": neo4j_result,
        "neo4j_error": error,
        "reasoning_log": [{
            "node": "query_neo4j",
            "engine_used": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "cypher_query": cypher,
            "row_count": len(neo4j_result) if neo4j_result is not None else 0,
            "error": error,
        }],
    }
