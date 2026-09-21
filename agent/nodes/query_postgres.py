from .. import db, llm_client, prompts
from ..state import AgentState
from ..utils import strip_code_fence


def query_postgres_node(state: AgentState) -> dict:
    neo4j_context = None
    if state.get("neo4j_result"):
        neo4j_context = str(state["neo4j_result"])

    result = llm_client.complete(
        system=prompts.SQL_SYSTEM,
        user=prompts.sql_user_prompt(
            state["question"], neo4j_context=neo4j_context, feedback=state.get("validation_feedback")
        ),
        max_tokens=500,
    )
    sql = strip_code_fence(result.content)

    postgres_result, error = None, None
    try:
        postgres_result = db.run_sql(sql)
    except Exception as exc:  # noqa: BLE001 - surfaced to synthesize/validate, not fatal
        error = str(exc)

    return {
        "sql_query": sql,
        "postgres_result": postgres_result,
        "postgres_error": error,
        "reasoning_log": [{
            "node": "query_postgres",
            "engine_used": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "sql_query": sql,
            "row_count": len(postgres_result) if postgres_result is not None else 0,
            "error": error,
        }],
    }
