from .. import llm_client, prompts
from ..state import AgentState
from ..utils import extract_json

VALID_CONFIDENCE = {"high", "estimated", "low"}


def synthesize_node(state: AgentState) -> dict:
    result = llm_client.complete(
        system=prompts.SYNTHESIZE_SYSTEM,
        user=prompts.synthesize_user_prompt(state),
        max_tokens=800,
    )

    try:
        parsed = extract_json(result.content)
        answer = parsed.get("answer") or "I wasn't able to generate an answer from the retrieved data."
        confidence = parsed.get("confidence") if parsed.get("confidence") in VALID_CONFIDENCE else "low"
    except ValueError:
        answer = result.content.strip() or "I wasn't able to generate an answer from the retrieved data."
        confidence = "low"

    return {
        "answer": answer,
        "confidence": confidence,
        "reasoning_log": [{
            "node": "synthesize",
            "engine_used": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "confidence": confidence,
        }],
    }
