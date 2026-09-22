"""Swappable "fast decision" layer for classify_query's routing choice (build step 8's
decision-engine abstraction).

Two engines, same result shape (`value`, `confidence`, `engine_used`, `latency_ms`) so
classify_query never needs to know which one actually ran:
  - Jev (TypeSafe AI): typed Choice/Noul questions answered in ~100ms for a few cents,
    no free-text generation. Used for query_type/requires_simulation/simulation_type,
    which are genuine categorical decisions.
  - Claude/Groq (via llm_client.complete): the existing full classify call. Always the
    fallback on any Jev error (missing key, auth, timeout, network) - the app must never
    depend on Jev being reachable - and still the only way to extract simulation_params,
    which is freeform extraction with no typed-primitive equivalent.
"""
import time
from dataclasses import dataclass
from typing import Optional

from langsmith import traceable

from . import config, llm_client, prompts
from .utils import extract_json

VALID_QUERY_TYPES = {
    "graph_traversal", "inventory_lookup", "cost_analysis", "contract_status", "compound_multi_hop",
    "semantic_search",
}
VALID_SIMULATION_TYPES = {"disruption", "capacity", "cost_impact"}

_QUERY_TYPE_CRITERIA = {
    "graph_traversal": "Pure relationship/structural question (who supplies what, what's used in "
                        "what, backup suppliers, single points of failure) answerable from the graph alone.",
    "inventory_lookup": "Stock levels, reorder points, warehouse/dealer stock - no entity named that "
                         "would need resolving from the graph first.",
    "cost_analysis": "Pricing, purchase order costs, unit cost comparisons for an ACTUAL (not "
                      "hypothetical 'what if price changes') situation.",
    "contract_status": "Contract expiry, billing, invoices, shipments, or penalties for an ACTUAL "
                        "situation, with no specific supplier/dealer/product named by name.",
    "compound_multi_hop": "Needs both the graph (relationships) AND transactional data together, OR "
                           "names any entity (supplier/dealer/product/material) BY NAME rather than by "
                           "ID for a question that needs Postgres data (Postgres has no name columns, "
                           "so the name must resolve via the graph first).",
    "semantic_search": "A qualitative question about a supplier/vendor's quality, compliance, risk, "
                        "or sustainability record - no exact column to filter on, needs free-text "
                        "search over audit/quality notes instead.",
}


@dataclass
class DecisionResult:
    value: dict  # {"query_type", "requires_simulation", "simulation_type"}
    confidence: Optional[dict]  # per-field confidence, engine-specific shape
    engine_used: str  # "jev" | "claude"
    latency_ms: float


@traceable(run_type="llm", name="jev")
def classify_via_jev(question: str, feedback: Optional[str] = None) -> DecisionResult:
    """Raises on any error - missing key, auth failure, timeout, network - so the caller
    can fall back to the Claude path. Never partially succeeds."""
    from typesafe_sdk import Choice, Noul, TypeSafeClient

    if not config.TYPESAFE_API_KEY:
        raise RuntimeError("TYPESAFE_API_KEY not set")

    state = question if not feedback else (
        f"{question}\n\n(A previous attempt at this question was rejected: {feedback})"
    )
    t0 = time.monotonic()
    client = TypeSafeClient(api_key=config.TYPESAFE_API_KEY, model=config.TYPESAFE_MODEL)
    resp = client.system_one(state, {
        "query_type": Choice(
            instructions="Which query type best answers this supply-chain question?",
            criteria=_QUERY_TYPE_CRITERIA,
        ),
        "requires_simulation": Noul(
            instructions="Does answering this well require projecting downstream impact (a "
                         "what-if or a real disruption/delay/order-feasibility/price-change "
                         "question), rather than just looking up existing facts?",
            criteria={"true": "Needs impact projection or feasibility/cost simulation.",
                      "false": "A plain lookup of existing facts answers it."},
        ),
        "simulation_type": Choice(
            instructions="IF this needs simulation, which kind? (Ignored if it doesn't.)",
            criteria={
                "disruption": "A supplier/material delay or disruption (happened or hypothetical) "
                               "and what it affects.",
                "capacity": "Whether an order can be fulfilled by some deadline.",
                "cost_impact": "Effect of a price change on cost/margin.",
            },
        ),
    })
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    qt = resp.choices["query_type"]
    sim = resp.choices["simulation_type"]
    requires_simulation = resp.nouls["requires_simulation"].noul >= 0.5

    query_type = qt.choice if qt.choice in VALID_QUERY_TYPES else "compound_multi_hop"
    simulation_type = sim.choice if requires_simulation and sim.choice in VALID_SIMULATION_TYPES else None
    requires_simulation = requires_simulation and simulation_type is not None

    return DecisionResult(
        value={
            "query_type": query_type,
            "requires_simulation": requires_simulation,
            "simulation_type": simulation_type,
        },
        confidence={
            "query_type": qt.confidence,
            "requires_simulation": resp.nouls["requires_simulation"].noul,
            "simulation_type": sim.confidence if simulation_type else None,
        },
        engine_used="jev",
        latency_ms=latency_ms,
    )


def classify_via_claude(question: str, feedback: Optional[str] = None) -> tuple[DecisionResult, dict]:
    """The full classify_query call - also returns simulation_params (JSON-parsed) since
    Claude, unlike Jev, extracts those in the same pass. Second return value is the raw
    parsed dict for classify_query to reuse rather than re-parsing."""
    t0 = time.monotonic()
    result = llm_client.complete(
        system=prompts.CLASSIFY_SYSTEM,
        user=prompts.classify_user_prompt(question, feedback=feedback),
        max_tokens=400,
    )
    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    parsed = extract_json(result.content)

    query_type = parsed.get("query_type") if parsed.get("query_type") in VALID_QUERY_TYPES else "compound_multi_hop"
    simulation_type = parsed.get("simulation_type")
    if simulation_type not in VALID_SIMULATION_TYPES:
        simulation_type = None
    requires_simulation = bool(parsed.get("requires_simulation")) and simulation_type is not None

    decision = DecisionResult(
        value={
            "query_type": query_type,
            "requires_simulation": requires_simulation,
            "simulation_type": simulation_type,
        },
        confidence=None,
        engine_used=f"claude:{result.provider}",
        latency_ms=latency_ms,
    )
    return decision, parsed


def extract_simulation_params(question: str, simulation_type: str) -> dict:
    """Scoped-down Claude call used only after Jev has already decided requires_simulation
    is true - extracts just the freeform params, not the full classify_query output."""
    result = llm_client.complete(
        system=prompts.SIMULATION_PARAMS_SYSTEM,
        user=prompts.simulation_params_user_prompt(question, simulation_type),
        max_tokens=200,
    )
    try:
        return extract_json(result.content)
    except ValueError:
        return {}
