"""Deterministic what-if simulations (disruption / capacity / cost impact).

These are hand-coded rather than LLM-generated because they require reliable
multi-hop traversal + arithmetic (graph impact -> inventory buffer -> risk),
not freeform querying — the LLM's job upstream (classify_query) is just to
detect which simulation applies and extract its parameters from the question.
"""
import re
import time

from .. import db
from ..state import AgentState

# Generic words the classifier LLM tends to include in extracted entity names
# ("our aluminum SUPPLIER") that would otherwise never match a real node name.
_STOPWORDS = {
    "supplier", "suppliers", "vendor", "vendors", "material", "materials", "raw",
    "part", "parts", "product", "products", "company", "the", "our", "a", "an", "of",
}
# Maps classify_query's entity_type hint ("supplier"/"raw_material"/"vendor"/"product") to
# the Neo4j label to prefer when a name/keyword matches more than one label — this is more
# reliable than guessing from stray role words left in entity_name.
_ENTITY_TYPE_TO_LABEL = {
    "supplier": "Supplier", "raw_material": "RawMaterial", "vendor": "ThirdPartyVendor", "product": "Product",
}
# Fallback if entity_type wasn't provided: guess from role words left in entity_name itself.
_ROLE_LABEL_HINTS = {
    "supplier": "Supplier", "suppliers": "Supplier", "vendor": "ThirdPartyVendor", "vendors": "ThirdPartyVendor",
    "material": "RawMaterial", "materials": "RawMaterial", "part": "IntermediatePart", "parts": "IntermediatePart",
    "product": "Product", "products": "Product",
}


def resolve_entity(name: str | None, labels: list[str], entity_type: str | None = None) -> list[dict]:
    if not name:
        return []
    words = re.findall(r"[A-Za-z0-9]+", name)
    keywords = [w for w in words if w.lower() not in _STOPWORDS] or words or [name]
    preferred_label = _ENTITY_TYPE_TO_LABEL.get((entity_type or "").lower()) or next(
        (_ROLE_LABEL_HINTS[w.lower()] for w in words if w.lower() in _ROLE_LABEL_HINTS), None
    )

    rows = db.run_cypher(
        """
        MATCH (n)
        WHERE any(lbl IN labels(n) WHERE lbl IN $labels)
          AND any(k IN $keywords WHERE toLower(n.name) CONTAINS toLower(k))
        RETURN labels(n)[0] AS label, n.id AS id, n.name AS name
        LIMIT 25
        """,
        {"labels": labels, "keywords": keywords},
    )

    # Rank by closeness rather than taking the first (arbitrarily-ordered) match: an exact
    # name match beats a partial one, and matching more of the keywords beats matching just
    # one shared generic word (e.g. "SUV Suspension Kit" vs "Sedan Suspension Kit" both
    # contain "Suspension"/"Kit", but only one is an exact/near-exact match).
    name_lower = name.lower()

    def score(row: dict) -> tuple:
        row_name = row["name"].lower()
        exact = row_name == name_lower
        substring_match = name_lower in row_name or row_name in name_lower
        keyword_hits = sum(1 for k in keywords if k.lower() in row_name)
        label_match = preferred_label is not None and row["label"] == preferred_label
        return (label_match, exact, substring_match, keyword_hits)

    rows.sort(key=score, reverse=True)
    return rows


def simulate_disruption(entity_name: str | None, delay_days: int | None, entity_type: str | None = None) -> dict:
    delay_days = delay_days or 21
    matches = resolve_entity(entity_name, ["Supplier", "RawMaterial"], entity_type)
    if not matches:
        return {"error": f"Could not find a supplier or raw material matching '{entity_name}'."}
    match = matches[0]

    if match["label"] == "Supplier":
        materials = db.run_cypher(
            """
            MATCH (rm:RawMaterial)-[r:SOURCED_FROM]->(s:Supplier {id: $id})
            RETURN rm.id AS id, rm.name AS name, r.lead_time_days AS lead_time_days, r.is_primary AS is_primary
            """,
            {"id": match["id"]},
        )
    else:
        edges = db.run_cypher(
            """
            MATCH (rm:RawMaterial {id: $id})-[r:SOURCED_FROM]->(s:Supplier)
            RETURN r.lead_time_days AS lead_time_days, r.is_primary AS is_primary,
                   s.id AS supplier_id, s.name AS supplier_name
            """,
            {"id": match["id"]},
        )
        materials = [{"id": match["id"], "name": match["name"], **e} for e in edges]

    affected = []
    for material in materials:
        products = db.run_cypher(
            """
            MATCH (rm:RawMaterial {id: $id})-[:USED_IN]->(:IntermediatePart)-[:USED_IN]->(p:Product)
            RETURN DISTINCT p.id AS id, p.name AS name
            """,
            {"id": material["id"]},
        )
        inventory = db.run_sql(
            "SELECT quantity_on_hand, reorder_point, unit_of_measure FROM inventory_levels "
            "WHERE item_id = %s AND warehouse_id = 'F1'",
            (material["id"],),
        )
        stock = inventory[0] if inventory else None
        if stock:
            if stock["quantity_on_hand"] <= stock["reorder_point"]:
                risk_level = "high"
                stock_status = "already at or below its reorder point"
            elif stock["quantity_on_hand"] <= stock["reorder_point"] * 2:
                risk_level = "medium"
                stock_status = "above its reorder point but with less than a 2x buffer"
            else:
                risk_level = "low"
                stock_status = "comfortably above its reorder point (more than 2x buffer)"
        else:
            risk_level, stock_status = "unknown", "no inventory data on file"

        affected.append({
            "material_id": material["id"],
            "material_name": material["name"],
            "normal_lead_time_days": material.get("lead_time_days"),
            "effective_lead_time_days": (material.get("lead_time_days") or 0) + delay_days,
            "is_primary_source": material.get("is_primary"),
            "on_hand_quantity": stock["quantity_on_hand"] if stock else None,
            "reorder_point": stock["reorder_point"] if stock else None,
            "risk_level": risk_level,
            "stock_status": stock_status,
            "affected_products": products,
        })

    return {
        "disrupted_entity": match["name"],
        "delay_days": delay_days,
        "affected_materials": affected,
    }


def simulate_capacity(product_name: str | None, order_qty: int | None, timeframe_days: int | None) -> dict:
    order_qty = order_qty or 500
    timeframe_days = timeframe_days or 30
    matches = resolve_entity(product_name, ["Product"])
    if not matches:
        return {"error": f"Could not find a product matching '{product_name}'."}
    product = matches[0]

    cap_rows = db.run_sql(
        "SELECT max_units_per_week FROM production_capacity WHERE product_id = %s", (product["id"],)
    )
    if not cap_rows:
        return {"error": f"No production capacity data on file for {product['name']}."}
    max_per_week = float(cap_rows[0]["max_units_per_week"])

    backlog_rows = db.run_sql(
        "SELECT COALESCE(SUM(quantity), 0) AS backlog FROM dealer_orders "
        "WHERE product_id = %s AND fulfillment_status IN ('pending', 'backordered', 'partial')",
        (product["id"],),
    )
    backlog = float(backlog_rows[0]["backlog"]) if backlog_rows else 0.0

    weeks = timeframe_days / 7
    theoretical_capacity = max_per_week * weeks
    available_capacity = theoretical_capacity - backlog

    return {
        "product_id": product["id"],
        "product_name": product["name"],
        "requested_qty": order_qty,
        "timeframe_days": timeframe_days,
        "max_units_per_week": max_per_week,
        "theoretical_capacity": round(theoretical_capacity, 1),
        "existing_open_backlog": backlog,
        "available_capacity": round(available_capacity, 1),
        "feasible": available_capacity >= order_qty,
    }


def simulate_cost_impact(material_name: str | None, pct_change: float | None) -> dict:
    pct_change = pct_change if pct_change is not None else 10.0
    matches = resolve_entity(material_name, ["RawMaterial"])
    if not matches:
        return {"error": f"Could not find a raw material matching '{material_name}'."}
    material = matches[0]

    sourced = db.run_cypher(
        """
        MATCH (rm:RawMaterial {id: $id})-[r:SOURCED_FROM {is_primary: true}]->(s:Supplier)
        RETURN r.cost_per_unit AS cost_per_unit, r.currency AS currency, s.name AS supplier_name
        """,
        {"id": material["id"]},
    )
    if not sourced:
        return {"error": f"No primary sourcing cost on file for {material['name']}."}
    base_cost = sourced[0]["cost_per_unit"]
    delta_cost = base_cost * (pct_change / 100)

    impact_rows = db.run_cypher(
        """
        MATCH (rm:RawMaterial {id: $id})-[u1:USED_IN]->(:IntermediatePart)-[u2:USED_IN]->(p:Product)
        RETURN p.id AS product_id, p.name AS product_name,
               u1.quantity_required AS rm_qty_per_part, u2.quantity_required AS part_qty_per_product
        """,
        {"id": material["id"]},
    )
    # A raw material often reaches the same product through more than one intermediate
    # part (e.g. steel via both coil springs and shock absorbers) — aggregate by product
    # rather than emitting one row per path.
    qty_by_product: dict[str, dict] = {}
    for row in impact_rows:
        qty_per_path = (row["rm_qty_per_part"] or 0) * (row["part_qty_per_product"] or 0)
        entry = qty_by_product.setdefault(
            row["product_id"], {"product_id": row["product_id"], "product_name": row["product_name"], "material_qty_per_unit": 0.0}
        )
        entry["material_qty_per_unit"] += qty_per_path

    product_impacts = []
    for entry in qty_by_product.values():
        entry["material_qty_per_unit"] = round(entry["material_qty_per_unit"], 4)
        entry["added_cost_per_unit"] = round(entry["material_qty_per_unit"] * delta_cost, 4)
        product_impacts.append(entry)

    return {
        "material_id": material["id"],
        "material_name": material["name"],
        "primary_supplier": sourced[0]["supplier_name"],
        "pct_change": pct_change,
        "base_cost_per_unit": base_cost,
        "new_cost_per_unit": round(base_cost * (1 + pct_change / 100), 4),
        "currency": sourced[0]["currency"],
        "product_impacts": product_impacts,
        "note": (
            "Margin % impact is not computed — product selling prices aren't modeled in this "
            "system. Figures below are added raw-material cost per finished unit only."
        ),
    }


_SIMULATORS = {
    "disruption": lambda p: simulate_disruption(p.get("entity_name"), p.get("delay_days"), p.get("entity_type")),
    "capacity": lambda p: simulate_capacity(p.get("entity_name"), p.get("order_qty"), p.get("timeframe_days")),
    "cost_impact": lambda p: simulate_cost_impact(p.get("entity_name"), p.get("pct_change")),
}


def simulate_scenario_node(state: AgentState) -> dict:
    sim_type = state.get("simulation_type")
    params = state.get("simulation_params") or {}
    t0 = time.monotonic()

    fn = _SIMULATORS.get(sim_type)
    result = fn(params) if fn else {"error": f"Unknown simulation_type: {sim_type!r}"}
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    return {
        "simulation_result": result,
        "reasoning_log": [{
            "node": "simulate_scenario",
            "engine_used": "deterministic",
            "latency_ms": latency_ms,
            "simulation_type": sim_type,
            "params": params,
            "error": result.get("error"),
        }],
    }
