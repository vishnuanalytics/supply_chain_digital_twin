# Data Reference — Entity IDs

Canonical ID scheme shared across Neo4j and PostgreSQL so the two stores can be
joined/cross-referenced by ID during agent development and evaluation. Keep this file
in sync whenever seed data changes.

## Facility
| ID | Name | Location |
|----|------|----------|
| F1 | Riverside Manufacturing Plant | Columbus, OH |

## Warehouses
| ID | Name | Location |
|----|------|----------|
| WH1 | North Distribution Center | Chicago, IL |
| WH2 | Central Distribution Center | Columbus, OH |
| WH3 | South Distribution Center | Dallas, TX |

## Regions
| ID | Name |
|----|------|
| R1 | Midwest |
| R2 | Northeast |
| R3 | South |
| R4 | West |
| R5 | Southwest |

## Dealers
| ID | Name | Location | Region | Supplied by |
|----|------|----------|--------|-------------|
| D1 | Great Lakes Auto Parts | Chicago, IL | R1 | WH1, WH2 |
| D2 | Atlantic Motors Supply | Boston, MA | R2 | WH2 |
| D3 | Lone Star Auto Distributors | Dallas, TX | R3 | WH2, WH3 |
| D4 | Pacific Coast Parts | Los Angeles, CA | R4 | WH3 |
| D5 | Desert Auto Wholesale | Phoenix, AZ | R5 | WH3 |

## Finished Products
| ID | Name | Stored in | Max units/week |
|----|------|-----------|-----------------|
| P1 | Standard Brake System | WH1, WH2 | 800 |
| P2 | Heavy-Duty Brake System | WH2, WH3 | 500 |
| P3 | Sedan Suspension Kit | WH1, WH2 | 700 |
| P4 | SUV Suspension Kit | WH2, WH3 | 600 |
| P5 | ABS Sensor Module | WH1, WH3 | 1200 |
| P6 | TPMS Sensor Module | WH1, WH2, WH3 | 1500 |

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

## Raw Materials
| ID | Name | Unit | Primary Supplier | Backup Supplier |
|----|------|------|-------------------|-------------------|
| RM1 | Hot-Rolled Steel Sheet | kg | S1 | S6 |
| RM2 | Steel Rod Stock | kg | S1 | — |
| RM3 | Aluminum Alloy Billet | kg | S2 | S6 |
| RM4 | Aluminum Sheet | kg | S2 | — |
| RM5 | Natural Rubber Compound | kg | S3 | — |
| RM6 | Synthetic Rubber Compound | kg | S3 | — |
| RM7 | Copper Wire | kg | S4 | — |
| RM8 | Copper Alloy Bar | kg | S4 | — |
| RM9 | Engineering Plastic Resin (Nylon) | kg | S5 | S6 |
| RM10 | Engineering Plastic Resin (ABS) | kg | S5 | — |

## Suppliers (raw materials) & Vendors (intermediate parts)
| ID | Name | Type | Location |
|----|------|------|----------|
| S1 | Great Lakes Steel Co | Raw material supplier | Cleveland, OH |
| S2 | Titan Aluminum Works | Raw material supplier | Pittsburgh, PA |
| S3 | Continental Rubber Industries | Raw material supplier | Akron, OH |
| S4 | Copperline Metals Inc | Raw material supplier | Phoenix, AZ |
| S5 | PolyForm Plastics Ltd | Raw material supplier | Houston, TX |
| S6 | Diversified Metals & Materials Inc | Raw material supplier (backup only) | Indianapolis, IN |
| V1 | Precision Electronics Corp | Third-party vendor | San Jose, CA |
| V2 | Midwest Bearing & Motion Co | Third-party vendor | Detroit, MI |
| V3 | National Harness & Assembly Inc | Third-party vendor | Toledo, OH |

## Contracts
Only raw-material suppliers (S1–S6) hold contracts. Dates are relative to "today" =
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
| C0a | S1 | RM1 (previous) | 2025-01-01 | 2025-12-31 | expired | $1,100,000 | No |
| C0b | S4 | RM8 (previous) | 2024-08-01 | 2025-08-01 | expired | $395,000 | No |

`monthly_billing`, `shipments`, `invoices`, and `purchase_orders` in PostgreSQL are
generated programmatically by `postgres/generate_seed_data.py` against this contract
list — see that script for the exact logic (including a few intentionally-injected
delays and PO/invoice mismatches used by scenarios 7 and 11).
