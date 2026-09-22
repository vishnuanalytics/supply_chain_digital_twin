#!/usr/bin/env python3
"""Generates postgres/seed_data.sql — deterministic synthetic transactional data
for the Supply Chain Digital Twin, matching the entities defined in
docs/data_reference.md and the Neo4j seed graph (neo4j/seed_data.cypher).

Re-run this script (`python3 postgres/generate_seed_data.py`) whenever the
reference data below changes; do not hand-edit seed_data.sql.
"""

import random
from datetime import date, timedelta

random.seed(42)

TODAY = date(2026, 9, 21)
OUT_PATH = "postgres/seed_data.sql"

# ---------------------------------------------------------------------------
# Reference data (must stay in sync with docs/data_reference.md)
# ---------------------------------------------------------------------------

RAW_MATERIALS = {
    # material_id: (primary_supplier, base_cost_per_unit, unit)
    "RM1": ("S1", 0.85, "kg"),
    "RM2": ("S1", 1.10, "kg"),
    "RM3": ("S2", 2.40, "kg"),
    "RM4": ("S2", 2.10, "kg"),
    "RM5": ("S3", 3.20, "kg"),
    "RM6": ("S3", 3.60, "kg"),
    "RM7": ("S4", 8.75, "kg"),
    "RM8": ("S4", 9.40, "kg"),
    "RM9": ("S5", 1.95, "kg"),
    "RM10": ("S5", 2.05, "kg"),
    "RM11": ("S7", 4.35, "kg"),
    "RM12": ("S8", 1.60, "kg"),
}

# Materials with a rising price trend over the past year (steel, for the
# "steel prices rise 15%" cost-impact scenario) vs. flat/noisy for the rest.
RISING_TREND_MATERIALS = {"RM1", "RM2"}

INTERMEDIATE_PARTS = [f"IP{i}" for i in range(1, 19)]

PRODUCT_WAREHOUSES = {
    "P1": ["WH1", "WH2"],
    "P2": ["WH2", "WH3"],
    "P3": ["WH1", "WH2"],
    "P4": ["WH2", "WH3"],
    "P5": ["WH1", "WH3"],
    "P6": ["WH1", "WH2", "WH3"],
    "P7": ["WH4", "WH2"],
    "P8": ["WH4"],
    "P9": ["WH4", "WH1"],
}

PRODUCTION_CAPACITY = {
    "P1": 800, "P2": 500, "P3": 700, "P4": 600, "P5": 1200, "P6": 1500,
    "P7": 250, "P8": 400, "P9": 900,
}

# Finished-goods list price per unit - the base sales_records.unit_price is drawn from
# this with a small +/-5% noise band per sale, same pattern as purchase_orders' price
# noise around each raw material's base_cost above.
PRODUCT_BASE_PRICE = {
    "P1": 145.00, "P2": 210.00, "P3": 320.00, "P4": 410.00, "P5": 68.00, "P6": 54.00,
    "P7": 580.00, "P8": 340.00, "P9": 95.00,
}

DEALERS = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12"]
PRODUCTS = list(PRODUCT_WAREHOUSES.keys())

# Mirrors neo4j/seed_data.cypher's Dealer.buyer_type - Postgres itself has no name/type
# columns (see agent/prompts.py's SQL_SYSTEM note), so this exists purely to generate a
# realistic sales_records.channel value; the real, queryable buyer_type lives in Neo4j.
DEALER_TYPE = {
    "D1": "dealer", "D2": "dealer", "D3": "distributor", "D4": "dealer", "D5": "distributor",
    "D6": "distributor", "D7": "dealer", "D8": "distributor", "D9": "dealer", "D10": "distributor",
    "D11": "dealer", "D12": "distributor",
}

SUPPLIER_PERFORMANCE = {
    # supplier_id: (on_time_rate_pct, avg_delay_days)
    "S1": (94.5, 2.1),
    "S2": (81.5, 6.5),   # aluminum supplier — deliberately weaker, grounds the disruption scenario
    "S3": (96.0, 1.4),
    "S4": (91.0, 3.0),
    "S5": (93.5, 2.4),
    "S6": (89.0, 4.2),
    "S7": (93.0, 2.6),
    "S8": (95.0, 1.9),
    "V1": (95.5, 1.8),
    "V2": (92.0, 2.9),
    "V3": (90.5, 3.4),
    "V4": (88.5, 3.9),
}

# contract_id, supplier_id, material_id, start, end, value, penalty_clause
CONTRACTS = [
    ("C1",  "S1", "RM1",  date(2026, 3, 1),  date(2027, 3, 1),  1200000, True,  "Net 45"),
    ("C2",  "S1", "RM2",  date(2025, 10, 5), date(2026, 10, 5), 450000,  False, "Net 45"),
    ("C3",  "S2", "RM3",  date(2025, 11, 15), date(2026, 11, 15), 980000, True, "Net 30"),
    ("C4",  "S2", "RM4",  date(2026, 6, 1),  date(2027, 6, 1),  520000,  False, "Net 30"),
    ("C5",  "S3", "RM5",  date(2026, 1, 20), date(2027, 1, 20), 610000,  False, "Net 30"),
    ("C6",  "S3", "RM6",  date(2025, 12, 10), date(2026, 12, 10), 340000, True, "Net 30"),
    ("C7",  "S4", "RM7",  date(2026, 4, 15), date(2027, 4, 15), 890000,  True,  "Net 45"),
    ("C8",  "S4", "RM8",  date(2025, 8, 1),  date(2026, 8, 1),  410000,  False, "Net 45"),
    ("C9",  "S5", "RM9",  date(2026, 2, 28), date(2027, 2, 28), 730000,  False, "Net 30"),
    ("C10", "S5", "RM10", date(2025, 10, 1), date(2026, 10, 1), 295000,  False, "Net 30"),
    ("C11", "S7", "RM11", date(2026, 5, 1),  date(2027, 5, 1),  560000,  True,  "Net 30"),
    ("C12", "S8", "RM12", date(2026, 7, 1),  date(2027, 7, 1),  275000,  False, "Net 30"),
    ("C0a", "S1", "RM1",  date(2025, 1, 1),  date(2025, 12, 31), 1100000, False, "Net 45"),
    ("C0b", "S4", "RM8",  date(2024, 8, 1),  date(2025, 8, 1),  395000,  False, "Net 45"),
]

PENALTY_TERMS = "2% of shipment value per week delayed, capped at 10% of shipment value."

sql_sections: list[str] = []


def add_section(title: str, lines: list[str]) -> None:
    sql_sections.append(f"-- {'-' * 76}\n-- {title}\n-- {'-' * 76}\n" + "\n".join(lines) + "\n")


def sql_str(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, date):
        return f"'{value.isoformat()}'"
    return "'" + str(value).replace("'", "''") + "'"


def insert(table: str, columns: list[str], rows: list[tuple]) -> str:
    col_list = ", ".join(columns)
    values = ",\n  ".join(
        "(" + ", ".join(sql_str(v) for v in row) + ")" for row in rows
    )
    return f"INSERT INTO {table} ({col_list}) VALUES\n  {values};"


def months_back(n: int) -> list[date]:
    """Returns the 1st of each of the last n months, oldest first, ending this month."""
    months = []
    y, m = TODAY.year, TODAY.month
    for _ in range(n):
        months.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


# ---------------------------------------------------------------------------
# contracts
# ---------------------------------------------------------------------------
contract_rows = []
for contract_id, supplier_id, material_id, start, end, value, penalty, terms in CONTRACTS:
    days_to_expiry = (end - TODAY).days
    if end < TODAY:
        status = "expired"
    elif days_to_expiry <= 90:
        status = "expiring_soon"
    else:
        status = "active"
    contract_rows.append((
        contract_id, supplier_id, start, end, value, terms, status,
        penalty, PENALTY_TERMS if penalty else None,
    ))

add_section("contracts", [insert(
    "contracts",
    ["contract_id", "supplier_id", "start_date", "end_date", "contract_value",
     "payment_terms", "renewal_status", "penalty_clause", "penalty_terms"],
    contract_rows,
)])

# ---------------------------------------------------------------------------
# purchase_orders (12 months per raw material, from its primary supplier;
# RM1/RM3/RM9 also get a couple of backup-supplier POs to exercise the
# supplier-comparison scenario)
# ---------------------------------------------------------------------------
po_rows = []
po_counter = 1
po_by_material_month: dict[tuple[str, date], str] = {}

for material_id, (supplier_id, base_cost, uom) in RAW_MATERIALS.items():
    for i, month in enumerate(months_back(12)):
        if material_id in RISING_TREND_MATERIALS:
            price = round(base_cost * (1 + 0.012 * i) * random.uniform(0.98, 1.02), 4)
        else:
            price = round(base_cost * random.uniform(0.96, 1.04), 4)
        qty = round(random.uniform(800, 2200), 2)
        order_date = month + timedelta(days=random.randint(2, 8))
        po_id = f"PO{po_counter:04d}"
        po_counter += 1
        po_rows.append((po_id, material_id, supplier_id, qty, uom, price, "USD", order_date))
        po_by_material_month[(material_id, month)] = po_id

# Backup-supplier POs for materials with an approved second source
for material_id, backup_supplier, backup_cost in [("RM1", "S6", 0.95), ("RM3", "S6", 2.65), ("RM9", "S6", 2.20)]:
    for month in months_back(12)[::4]:  # quarterly test orders from the backup
        qty = round(random.uniform(150, 400), 2)
        order_date = month + timedelta(days=random.randint(10, 20))
        po_id = f"PO{po_counter:04d}"
        po_counter += 1
        price = round(backup_cost * random.uniform(0.98, 1.03), 4)
        po_rows.append((po_id, material_id, backup_supplier, qty, "kg", price, "USD", order_date))

add_section("purchase_orders", [insert(
    "purchase_orders",
    ["po_id", "material_id", "supplier_id", "quantity", "unit_of_measure",
     "price_per_unit", "currency", "order_date"],
    po_rows,
)])

# ---------------------------------------------------------------------------
# price_calibration (quarterly normalized price per material)
# ---------------------------------------------------------------------------
calibration_rows = []
quarter_months = months_back(12)[::3]
for material_id, (supplier_id, base_cost, uom) in RAW_MATERIALS.items():
    for i, month in enumerate(quarter_months):
        if material_id in RISING_TREND_MATERIALS:
            price = round(base_cost * (1 + 0.035 * i), 4)
        else:
            price = round(base_cost * random.uniform(0.99, 1.02), 4)
        calibration_rows.append((material_id, "USD", price, uom, month))

add_section("price_calibration", [insert(
    "price_calibration",
    ["material_id", "currency", "price_per_unit", "unit_of_measure", "effective_date"],
    calibration_rows,
)])

# ---------------------------------------------------------------------------
# monthly_billing + shipments + invoices
# Each contract gets one row per calendar month it was in force, most recent
# 12 months of that window (its own term for expired contracts, or up to
# "today" for active ones — so a currently-active contract that started
# recently naturally has less history than one that's been running a while;
# scenario 9 "supplier history" stitches this together with the supplier's
# PREVIOUSLY_CONTRACTED contract to see the full multi-year relationship).
# ---------------------------------------------------------------------------
billing_rows = []
shipment_rows = []
invoice_rows = []
billing_counter = 1
shipment_counter = 1
invoice_counter = 1


def contract_months(start: date, end: date) -> list[date]:
    window_end = min(end, TODAY)
    months = []
    y, m = start.year, start.month
    while date(y, m, 1) <= window_end:
        months.append(date(y, m, 1))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return months[-12:]


# Contracts whose supplier has a penalty clause get a couple of injected delays
DELAY_INJECTED_MONTHS = {"C1": [3, 7], "C3": [5], "C6": [8], "C7": [2, 9]}
# A few invoices are deliberately mismatched against their PO/shipment amount
MISMATCH_MONTHS = {"C2": [4], "C8": [1], "C9": [10]}

for contract_id, supplier_id, material_id, start, end, value, penalty, terms in CONTRACTS:
    monthly_amount = round(value / 12, 2)
    contract_month_list = contract_months(start, end)
    for i, month in enumerate(contract_month_list):
        billing_id = f"BILL{billing_counter:04d}"
        billing_counter += 1
        is_current_month = end >= TODAY and month == contract_month_list[-1]
        if is_current_month:
            b_status, paid = "pending", 0
        elif contract_id in MISMATCH_MONTHS and i in MISMATCH_MONTHS.get(contract_id, []):
            b_status, paid = "overdue", 0
        else:
            b_status, paid = "paid", monthly_amount
        billing_rows.append((billing_id, contract_id, month, monthly_amount, paid, b_status))

        po_id = po_by_material_month.get((material_id, month))
        ship_date = month + timedelta(days=random.randint(9, 14))
        qty = round(random.uniform(800, 2200), 2)
        is_delayed = i in DELAY_INJECTED_MONTHS.get(contract_id, [])
        shipment_id = f"SHIP{shipment_counter:04d}"
        shipment_counter += 1
        if is_delayed:
            s_status = "delayed"
            received = ship_date + timedelta(days=random.randint(18, 25))
        elif is_current_month:
            s_status = "in_transit"
            received = None
        else:
            s_status = "delivered"
            received = ship_date + timedelta(days=random.randint(3, 8))
        shipment_rows.append((shipment_id, contract_id, po_id, ship_date, received, qty, s_status))

        invoice_id = f"INV{invoice_counter:04d}"
        invoice_counter += 1
        due_date = ship_date + timedelta(days=45 if terms == "Net 45" else 30)
        is_mismatch = i in MISMATCH_MONTHS.get(contract_id, [])
        if is_mismatch:
            amount = round(monthly_amount * random.uniform(1.08, 1.15), 2)  # doesn't match PO/shipment value
            i_status = "mismatch"
        else:
            amount = monthly_amount
            i_status = "pending" if is_current_month else ("overdue" if b_status == "overdue" else "paid")
        invoice_rows.append((invoice_id, contract_id, shipment_id, po_id, amount, "USD", due_date, i_status))

add_section("monthly_billing", [insert(
    "monthly_billing",
    ["billing_id", "contract_id", "billing_month", "amount_due", "amount_paid", "status"],
    billing_rows,
)])
add_section("shipments", [insert(
    "shipments",
    ["shipment_id", "contract_id", "po_id", "ship_date", "received_date", "quantity", "status"],
    shipment_rows,
)])
add_section("invoices", [insert(
    "invoices",
    ["invoice_id", "contract_id", "shipment_id", "po_id", "amount", "currency", "due_date", "status"],
    invoice_rows,
)])

# ---------------------------------------------------------------------------
# dealer_orders (last 6 months, all dealers x all products)
# ---------------------------------------------------------------------------
dealer_order_rows = []
order_counter = 1
for month in months_back(6):
    for dealer_id in DEALERS:
        for product_id in PRODUCTS:
            if random.random() > 0.55:  # not every dealer orders every product every month
                continue
            order_id = f"DO{order_counter:04d}"
            order_counter += 1
            qty = round(random.uniform(20, 220), 0)
            # For the current (most recent) month, don't generate an order_date past
            # TODAY - without this cap, "day 1-26 of the current month" can land after
            # the demo's pinned "today" (e.g. TODAY=Sep 21 but day 26 = Sep 26), which
            # reads as a future-dated order/sale in any UI sorted by recency. Earlier
            # months are always fully in the past already, so only this month needs it.
            max_day_offset = min(26, max(1, (TODAY - month).days)) if month == months_back(6)[-1] else 26
            order_date = month + timedelta(days=random.randint(1, max_day_offset))
            roll = random.random()
            if roll > 0.93:
                status = "backordered"
            elif roll > 0.85:
                status = "partial"
            elif month == months_back(6)[-1]:
                status = "pending"
            else:
                status = "fulfilled"
            dealer_order_rows.append((order_id, dealer_id, product_id, qty, order_date, status))

add_section("dealer_orders", [insert(
    "dealer_orders",
    ["order_id", "dealer_id", "product_id", "quantity", "order_date", "fulfillment_status"],
    dealer_order_rows,
)])

# ---------------------------------------------------------------------------
# sales_records - one per dealer_order that actually shipped (a still-
# backordered order has nothing to invoice yet). unit_price is the product's
# base list price with the same +/-5% noise band purchase_orders uses for
# material costs; channel follows the dealer's buyer_type (distributors buy
# in bulk through a distributor channel; dealers split between walk-in
# "direct" and a smaller "online" share). payment_status mirrors invoices'
# logic: the most recent month is still pending, everything older is paid
# except a small deliberately-injected overdue tail.
# ---------------------------------------------------------------------------
sales_rows = []
sale_counter = 1
for order_id, dealer_id, product_id, qty, order_date, status in dealer_order_rows:
    if status == "backordered":
        continue
    base_price = PRODUCT_BASE_PRICE[product_id]
    unit_price = round(base_price * random.uniform(0.95, 1.05), 4)
    revenue = round(float(qty) * unit_price, 2)
    sale_date = min(order_date + timedelta(days=random.randint(1, 5)), TODAY)

    if DEALER_TYPE[dealer_id] == "distributor":
        channel = "distributor"
    else:
        channel = "online" if random.random() > 0.7 else "direct"

    if status == "pending":
        payment_status = "pending"
    elif random.random() > 0.95:
        payment_status = "overdue"
    else:
        payment_status = "paid"

    sale_id = f"SALE{sale_counter:04d}"
    sale_counter += 1
    sales_rows.append((sale_id, order_id, unit_price, "USD", revenue, sale_date, channel, payment_status))

add_section("sales_records", [insert(
    "sales_records",
    ["sale_id", "order_id", "unit_price", "currency", "revenue", "sale_date", "channel", "payment_status"],
    sales_rows,
)])

# ---------------------------------------------------------------------------
# production_capacity
# ---------------------------------------------------------------------------
add_section("production_capacity", [insert(
    "production_capacity",
    ["product_id", "max_units_per_week"],
    [(pid, cap) for pid, cap in PRODUCTION_CAPACITY.items()],
)])

# ---------------------------------------------------------------------------
# supplier_performance
# ---------------------------------------------------------------------------
add_section("supplier_performance", [insert(
    "supplier_performance",
    ["supplier_id", "on_time_rate", "avg_delay_days"],
    [(sid, rate, delay) for sid, (rate, delay) in SUPPLIER_PERFORMANCE.items()],
)])

# ---------------------------------------------------------------------------
# inventory_levels
# raw materials + intermediate parts are buffered at the facility (F1);
# finished products sit in the warehouses from PRODUCT_WAREHOUSES.
# A couple of rows are deliberately set below reorder_point (P4 @ WH3,
# RM3 @ F1) to ground the restock / disruption-impact scenarios.
# ---------------------------------------------------------------------------
inventory_rows = []

LOW_STOCK_ITEMS = {("P4", "WH3"), ("RM3", "F1")}

for material_id, (supplier_id, base_cost, uom) in RAW_MATERIALS.items():
    reorder_point = round(random.uniform(400, 900), 2)
    qty = round(reorder_point * random.uniform(0.4, 0.6), 2) if (material_id, "F1") in LOW_STOCK_ITEMS \
        else round(reorder_point * random.uniform(1.3, 2.2), 2)
    inventory_rows.append((material_id, "raw_material", "F1", qty, uom, reorder_point, TODAY))

for part_id in INTERMEDIATE_PARTS:
    reorder_point = round(random.uniform(150, 400), 2)
    qty = round(reorder_point * random.uniform(1.2, 2.0), 2)
    inventory_rows.append((part_id, "intermediate_part", "F1", qty, "units", reorder_point, TODAY))

for product_id, warehouses in PRODUCT_WAREHOUSES.items():
    for warehouse_id in warehouses:
        reorder_point = round(random.uniform(50, 150), 2)
        qty = round(reorder_point * random.uniform(0.4, 0.6), 2) if (product_id, warehouse_id) in LOW_STOCK_ITEMS \
            else round(reorder_point * random.uniform(1.2, 2.5), 2)
        inventory_rows.append((product_id, "product", warehouse_id, qty, "units", reorder_point, TODAY))

add_section("inventory_levels", [insert(
    "inventory_levels",
    ["item_id", "item_type", "warehouse_id", "quantity_on_hand", "unit_of_measure", "reorder_point", "last_updated"],
    inventory_rows,
)])

# ---------------------------------------------------------------------------
# write file
# ---------------------------------------------------------------------------
header = (
    "-- Supply Chain Digital Twin — PostgreSQL seed data\n"
    "-- GENERATED FILE — do not hand-edit. Regenerate with:\n"
    "--   python3 postgres/generate_seed_data.py\n"
    "-- Run schema.sql first.\n\n"
)

with open(OUT_PATH, "w") as f:
    f.write(header)
    f.write("\n\n".join(sql_sections))
    f.write("\n")

print(f"Wrote {OUT_PATH}")
print(f"  contracts: {len(contract_rows)}")
print(f"  purchase_orders: {len(po_rows)}")
print(f"  price_calibration: {len(calibration_rows)}")
print(f"  monthly_billing: {len(billing_rows)}")
print(f"  shipments: {len(shipment_rows)}")
print(f"  invoices: {len(invoice_rows)}")
print(f"  dealer_orders: {len(dealer_order_rows)}")
print(f"  sales_records: {len(sales_rows)}")
print(f"  production_capacity: {len(PRODUCTION_CAPACITY)}")
print(f"  supplier_performance: {len(SUPPLIER_PERFORMANCE)}")
print(f"  inventory_levels: {len(inventory_rows)}")
