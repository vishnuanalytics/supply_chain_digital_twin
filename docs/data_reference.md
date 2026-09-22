# Data Reference — Entity IDs

Canonical ID scheme shared across Neo4j and PostgreSQL so the two stores can be
joined/cross-referenced by ID during agent development and evaluation. Keep this file
in sync whenever seed data changes.

## Facilities
| ID | Name | Location |
|----|------|----------|
| F1 | Riverside Manufacturing Plant | Columbus, OH |
| F2 | Westgate Assembly Plant | Reno, NV |

## Warehouses
| ID | Name | Location |
|----|------|----------|
| WH1 | North Distribution Center | Chicago, IL |
| WH2 | Central Distribution Center | Columbus, OH |
| WH3 | South Distribution Center | Dallas, TX |
| WH4 | West Distribution Center | Denver, CO |

## Regions
| ID | Name |
|----|------|
| R1 | Midwest |
| R2 | Northeast |
| R3 | South |
| R4 | West |
| R5 | Southwest |
| R6 | Pacific Northwest |
| R7 | Mountain |

## Dealers / Distributors
`buyer_type` distinguishes a smaller regional reseller ('dealer') from a larger
wholesale reseller ('distributor') — both buy finished Products from us and resell
downstream to end customers, just at different scale/tier. Revenue/payment data for
what they buy lives in PostgreSQL's `sales_records` (joined via `dealer_orders`) — see
that table's own comment in `postgres/schema.sql`.

| ID | Name | Type | Location | Region | Supplied by |
|----|------|------|----------|--------|-------------|
| D1 | Great Lakes Auto Parts | dealer | Chicago, IL | R1 | WH1, WH2 |
| D2 | Atlantic Motors Supply | dealer | Boston, MA | R2 | WH2 |
| D3 | Lone Star Auto Distributors | distributor | Dallas, TX | R3 | WH2, WH3 |
| D4 | Pacific Coast Parts | dealer | Los Angeles, CA | R4 | WH3 |
| D5 | Desert Auto Wholesale | distributor | Phoenix, AZ | R5 | WH3 |
| D6 | Northeast Wholesale Distributors | distributor | Philadelphia, PA | R2 | WH1, WH2 |
| D7 | Heartland Auto Dealers Co | dealer | Kansas City, MO | R1 | WH1, WH2 |
| D8 | Rocky Mountain Parts Distributors | distributor | Denver, CO | R7 | WH3, WH4 |
| D9 | Pacific Northwest Auto Supply | dealer | Seattle, WA | R6 | WH4 |
| D10 | Gulf Coast Auto Distributors | distributor | Houston, TX | R3 | WH3 |
| D11 | Carolina Motors Group | dealer | Charlotte, NC | R2 | WH2 |
| D12 | Southwest Regional Distributors | distributor | Albuquerque, NM | R5 | WH3, WH4 |

## Finished Products
| ID | Name | Category | Manufactured at | Stored in | Max units/week |
|----|------|----------|------------------|-----------|-----------------|
| P1 | Standard Brake System | Brake System | F1 | WH1, WH2 | 800 |
| P2 | Heavy-Duty Brake System | Brake System | F1 | WH2, WH3 | 500 |
| P3 | Sedan Suspension Kit | Suspension Kit | F1 | WH1, WH2 | 700 |
| P4 | SUV Suspension Kit | Suspension Kit | F1 | WH2, WH3 | 600 |
| P5 | ABS Sensor Module | Sensor Module | F1 | WH1, WH3 | 1200 |
| P6 | TPMS Sensor Module | Sensor Module | F1 | WH1, WH2, WH3 | 1500 |
| P7 | Panoramic Sunroof Assembly | Glass Assembly | F2 | WH4, WH2 | 250 |
| P8 | Front Seat Module | Seating | F2 | WH4 | 400 |
| P9 | Rain-Sensing Wiper Module | Sensor Module | F2 | WH4, WH1 | 900 |

`sales_records.unit_price` (PostgreSQL) is noise around a base list price defined in
`postgres/generate_seed_data.py`'s `PRODUCT_BASE_PRICE` — not itself a Neo4j property.

## Intermediate Parts
| ID | Name | Vendor | Used in raw materials |
|----|------|--------|------------------------|
| IP1 | ABS Wheel Speed Sensor | V1 | RM7, RM9 |
| IP2 | TPMS Sensor | V1 | RM7, RM9 |
| IP3 | Engine Control Unit (ECU) | V1 | RM7, RM8, RM9 |
| IP4 | Brake Control ECU | V1 | RM7, RM8, RM9 |
| IP5 | Wheel Bearing Assembly | V2 | RM1 |
| IP6 | Ball Joint Bearing | V2 | RM1 |
| IP7 | Wiring Harness — Brake | V3 | RM7, RM10 |
| IP8 | Wiring Harness — Suspension | V3 | RM7, RM10 |
| IP9 | Brake Caliper | V3 | RM3 |
| IP10 | Brake Rotor | V3 | RM1 |
| IP11 | Brake Pad Set | V3 | RM6 |
| IP12 | Coil Spring | V2 | RM2 |
| IP13 | Shock Absorber | V2 | RM2, RM4 |
| IP14 | Sway Bar Link | V2 | RM2 |
| IP15 | Pressure Valve Assembly | V3 | RM4, RM10 |
| IP16 | Windshield Assembly | V4 | RM11, RM4 |
| IP17 | Seat Cushion Pad | V3 | RM12, RM6 |
| IP18 | Rain/Light Sensor Module | V4 | RM7, RM9 |

## Raw Materials
| ID | Name | Category | Unit | Primary Supplier | Backup Supplier |
|----|------|----------|------|-------------------|-------------------|
| RM1 | Hot-Rolled Steel Sheet | Steel | kg | S1 | S6 |
| RM2 | Steel Rod Stock | Steel | kg | S1 | — |
| RM3 | Aluminum Alloy Billet | Aluminum | kg | S2 | S6 |
| RM4 | Aluminum Sheet | Aluminum | kg | S2 | — |
| RM5 | Natural Rubber Compound | Rubber | kg | S3 | — |
| RM6 | Synthetic Rubber Compound | Rubber | kg | S3 | — |
| RM7 | Copper Wire | Copper | kg | S4 | — |
| RM8 | Copper Alloy Bar | Copper | kg | S4 | — |
| RM9 | Engineering Plastic Resin (Nylon) | Plastic | kg | S5 | S6 |
| RM10 | Engineering Plastic Resin (ABS) | Plastic | kg | S5 | — |
| RM11 | Tempered Glass Panel | Glass | kg | S7 | — |
| RM12 | Polyurethane Foam Block | Foam | kg | S8 | — |

## Suppliers (raw materials) & Vendors (intermediate parts)
| ID | Name | Type | Location |
|----|------|------|----------|
| S1 | Great Lakes Steel Co | Raw material supplier | Cleveland, OH |
| S2 | Titan Aluminum Works | Raw material supplier | Pittsburgh, PA |
| S3 | Continental Rubber Industries | Raw material supplier | Akron, OH |
| S4 | Copperline Metals Inc | Raw material supplier | Phoenix, AZ |
| S5 | PolyForm Plastics Ltd | Raw material supplier | Houston, TX |
| S6 | Diversified Metals & Materials Inc | Raw material supplier (backup only) | Indianapolis, IN |
| S7 | Great Plains Glass Works | Raw material supplier | Wichita, KS |
| S8 | Coastal Foam Industries | Raw material supplier | Savannah, GA |
| V1 | Precision Electronics Corp | Third-party vendor | San Jose, CA |
| V2 | Midwest Bearing & Motion Co | Third-party vendor | Detroit, MI |
| V3 | National Harness & Assembly Inc | Third-party vendor | Toledo, OH |
| V4 | Apex Optics & Sensors Inc | Third-party vendor | Austin, TX |

## Contracts
Only raw-material suppliers hold contracts. Dates are relative to "today" =
2026-09-21 (the date this data was authored).

| ID | Supplier | Covers | Start | End | Status | Value | Penalty clause |
|----|----------|--------|-------|-----|--------|-------|-----------------|
| C1 | S1 | RM1 | 2026-03-01 | 2027-03-01 | active | $1,200,000 | Yes |
| C2 | S1 | RM2 | 2025-10-05 | 2026-10-05 | active (expiring <30d) | $450,000 | No |
| C3 | S2 | RM3 | 2025-11-15 | 2026-11-15 | active (expiring <90d) | $980,000 | Yes |
| C4 | S2 | RM4 | 2026-06-01 | 2027-06-01 | active | $520,000 | No |
| C5 | S3 | RM5 | 2026-01-20 | 2027-01-20 | active | $610,000 | No |
| C6 | S3 | RM6 | 2025-12-10 | 2026-12-10 | active (expiring <90d) | $340,000 | Yes |
| C7 | S4 | RM7 | 2026-04-15 | 2027-04-15 | active | $890,000 | Yes |
| C8 | S4 | RM8 | 2025-08-01 | 2026-08-01 | expired | $410,000 | No |
| C9 | S5 | RM9 | 2026-02-28 | 2027-02-28 | active | $730,000 | No |
| C10 | S5 | RM10 | 2025-10-01 | 2026-10-01 | active (expiring <30d) | $295,000 | No |
| C11 | S7 | RM11 | 2026-05-01 | 2027-05-01 | active | $560,000 | Yes |
| C12 | S8 | RM12 | 2026-07-01 | 2027-07-01 | active | $275,000 | No |
| C0a | S1 | RM1 (previous) | 2025-01-01 | 2025-12-31 | expired | $1,100,000 | No |
| C0b | S4 | RM8 (previous) | 2024-08-01 | 2025-08-01 | expired | $395,000 | No |

`monthly_billing`, `shipments`, `invoices`, and `purchase_orders` in PostgreSQL are
generated programmatically by `postgres/generate_seed_data.py` against this contract
list — see that script for the exact logic (including a few intentionally-injected
delays and PO/invoice mismatches used by scenarios 7 and 11).

Each contract also carries an `account_manager` (who to actually contact — one of eight
named reps, keyed by supplier) and `auto_renew` (whether expiry needs a manual renewal
decision or renews on its own, `random.random() < 0.65`). Each shipment carries
`carrier`, `freight_mode` (`truck`/`rail`/`ocean`/`air` — bulk steel/aluminum materials
skew rail via `Union Pacific Railroad`/`CSX Transportation`, everything else skews truck
via the remaining carrier pool), `tracking_number`, and (only when `status='delayed'`) a
`delay_reason` drawn from a small realistic pool (winter storm, carrier capacity
shortage, customs hold, port congestion, mechanical breakdown, supplier production
delay). These feed the Contracts & Billing tab's shipment detail dialog — see
`ui/tabs/billing.py`'s `_recommended_action()` for how they're turned into a single
priority-ordered recommendation.

## Sales (the outbound/sell side — mirrors Contracts above, but us -> dealers/distributors)
`dealer_orders` (what/how much a dealer ordered, and its fulfillment status) and
`sales_records` (the revenue/payment side, one row per order that actually shipped —
see that table's own comment in `postgres/schema.sql`) are both generated
programmatically by `postgres/generate_seed_data.py` against the `DEALERS`/`PRODUCTS`/
`PRODUCT_BASE_PRICE`/`DEALER_TYPE` reference data in that script, over the 6 months
ending on the demo reference date above (no sale is ever dated after "today" — see that
script's `max_day_offset` cap). "Where we're selling" (revenue by region) crosses both
stores: `sales_records`/`dealer_orders` have the revenue and `dealer_id`, but only
Neo4j's `Dealer -[:SERVICES]-> Region` has the region - joined by `dealer_id` in
`ui/tabs/sales.py`'s own fetch functions (a direct cross-database-by-ID join, not
through the LLM agent, same as that tab's dealer directory lookup).
