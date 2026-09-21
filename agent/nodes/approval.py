"""human_approval_gate (build step 8): pauses via LangGraph's interrupt() before
"executing" a high-stakes recommendation. The one such recommendation this system
makes is reordering from a backup supplier during a disruption - only fires when
simulate_scenario's disruption result found a material already at/below its reorder
point (risk_level == "high") AND a real backup supplier is on file for it. Every other
question (the overwhelming majority - all lookups, and low/medium-risk simulations)
passes straight through untouched: approval-gating a plain answer would just be noise.
"""
import time

from .. import db
from ..state import AgentState


def _find_backup_supplier(material_id: str) -> dict | None:
    rows = db.run_cypher(
        """
        MATCH (rm:RawMaterial {id: $id})-[:SOURCED_FROM {is_primary: true}]->(primary:Supplier)
        MATCH (backup:Supplier)-[:BACKUP_FOR]->(primary)
        RETURN backup.id AS id, backup.name AS name
        LIMIT 1
        """,
        {"id": material_id},
    )
    return rows[0] if rows else None


def _build_recommendation(state: AgentState) -> dict | None:
    if state.get("simulation_type") != "disruption":
        return None
    sim = state.get("simulation_result") or {}
    for material in sim.get("affected_materials", []):
        if material.get("risk_level") != "high":
            continue
        backup = _find_backup_supplier(material["material_id"])
        if backup:
            return {
                "action_type": "reorder_from_backup",
                "material_id": material["material_id"],
                "material_name": material["material_name"],
                "backup_supplier_id": backup["id"],
                "backup_supplier_name": backup["name"],
                "description": (
                    f"Reorder {material['material_name']} from backup supplier "
                    f"{backup['name']} ({backup['id']}) - primary source is disrupted and "
                    f"on-hand stock is already at or below its reorder point."
                ),
            }
    return None


def human_approval_gate(state: AgentState) -> dict:
    from langgraph.types import interrupt

    t0 = time.monotonic()
    recommendation = _build_recommendation(state)

    if recommendation is None:
        return {
            "reasoning_log": [{
                "node": "human_approval_gate",
                "engine_used": "deterministic",
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "skipped": True,
            }],
        }

    # Everything above this line re-runs unchanged when the graph resumes after the
    # interrupt (LangGraph re-executes an interrupted node from its start) - it's pure
    # read-only lookups, so that's safe. Everything below runs exactly once, after a
    # real decision comes back.
    decision = interrupt({"type": "reorder_approval", **recommendation})

    approved = bool(decision.get("approved"))
    note = decision.get("note") or ""
    db.log_action(
        action_type=recommendation["action_type"],
        description=recommendation["description"],
        status="approved" if approved else "rejected",
        note=note,
    )

    return {
        "pending_action": recommendation,
        "action_decision": {"approved": approved, "note": note},
        "reasoning_log": [{
            "node": "human_approval_gate",
            "engine_used": "human",
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "recommendation": recommendation["description"],
            "approved": approved,
            "note": note,
        }],
    }
