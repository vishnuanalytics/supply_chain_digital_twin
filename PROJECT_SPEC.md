# Supply Chain Digital Twin — Automotive Components Manufacturer

## Project Purpose
Build an AI agent system that lets a non-technical supply chain/procurement user ask
plain-English questions about a manufacturing company's supply chain and get instant,
traceable, data-grounded answers — without writing SQL or Cypher.

This is a portfolio project for AI engineering job applications (LangGraph, PostgreSQL,
Neo4j). Priorities in order: (1) working end-to-end system, (2) clean UI that visually
demonstrates depth, (3) architecture that's easy to explain in interviews.

**Positioning:** This is a lightweight decision-support layer that complements existing
ERP systems (like SAP) by answering conversational, cross-system questions fast — it is
NOT positioned as an ERP replacement. Do not build or describe it as one.

---

## Domain: Automotive Components Manufacturer (single tenant, no multi-tenancy)

One fictional company that:
- Buys **raw materials** (steel, aluminum, rubber, copper, plastics) from suppliers
- Buys **intermediate parts** (sensors, ECUs, bearings, wiring harnesses) from third-party vendors
- Manufactures **multiple finished products** (e.g., brake systems, suspension kits, sensor
  modules) at one facility
- Stores finished products in **warehouses**
- Distributes to **dealers/distributors** across regions
- Operates on **annual supplier contracts** (not ad-hoc monthly sourcing), with defined
  contract values, renewal dates, and monthly billing/shipment cycles

### Scale (keep it small and demoable — do not over-generate data)
- 1 manufacturing facility
- 2–3 warehouses
- 4–5 dealers
- 5–6 finished products
- ~15 intermediate parts
- ~10 raw materials
- ~8 suppliers/vendors (2–3 raw materials should have an approved backup/second supplier)
- ~8–10 contracts (mix of active, expiring soon, expired)
- 12 months of synthetic billing/shipment history per active contract

---

## Data Model

### Neo4j (structural / relationship graph)
```
(RawMaterial)-[:SOURCED_FROM {lead_time_days, cost_per_unit, is_primary}]->(Supplier)
(Supplier)-[:BACKUP_FOR]->(Supplier)                  // approved 2nd-supplier relationship
(RawMaterial)-[:USED_IN {quantity_required, unit_of_measure}]->(IntermediatePart)
(IntermediatePart)-[:PURCHASED_FROM]->(ThirdPartyVendor)
(IntermediatePart)-[:USED_IN {quantity_required}]->(Product)
(Product)-[:MANUFACTURED_AT]->(Facility)
(Product)-[:STORED_IN]->(Warehouse)
(Warehouse)-[:SUPPLIES]->(Dealer)
(Dealer)-[:SERVICES]->(Region)
(Supplier)-[:HAS_CONTRACT]->(Contract {contract_id, start_date, end_date, status,
                                        contract_value, renewal_notice_days})
(Supplier)-[:PREVIOUSLY_CONTRACTED]->(Contract {status: "expired"})   // supplier history
(Contract)-[:COVERS]->(RawMaterial)
```

### PostgreSQL (transactional / time-series)
```sql
inventory_levels(item_id, item_type, warehouse_id, quantity_on_hand,
                  unit_of_measure, reorder_point, last_updated)

purchase_orders(po_id, material_id, supplier_id, quantity, unit_of_measure,
                 price_per_unit, currency, order_date)

price_calibration(material_id, currency, price_per_unit, unit_of_measure,
                   effective_date)   -- normalizes cost comparisons across units/currencies

contracts(contract_id, supplier_id, start_date, end_date, contract_value,
          payment_terms, renewal_status)

monthly_billing(billing_id, contract_id, billing_month, amount_due,
                 amount_paid, status)   -- paid | pending | overdue

shipments(shipment_id, contract_id, po_id, ship_date, received_date,
          quantity, status)   -- in_transit | delivered | delayed

invoices(invoice_id, contract_id, shipment_id, po_id, amount, currency,
         due_date, status)   -- for 3-way match: PO vs shipment vs invoice

dealer_orders(order_id, dealer_id, product_id, quantity, order_date,
              fulfillment_status)

production_capacity(product_id, max_units_per_week)
supplier_performance(supplier_id, on_time_rate, avg_delay_days)
```

**Unit & price calibration requirement:** raw materials may be bought/measured in
different units (kg vs lb, per-unit vs per-batch) and different currencies. Always
resolve through `price_calibration` before comparing costs across suppliers.

---

## Agent Architecture (LangGraph)

Nodes:
1. `classify_query` — determine question type: graph_traversal | inventory_lookup |
   cost_analysis | contract_status | compound_multi_hop
2. `query_neo4j` — Cypher generation + execution for relationship/traversal questions
3. `query_postgres` — SQL generation + execution for transactional/time-series questions
4. `validate_results` — self-correction node: checks if results are empty, contradictory,
   or don't answer the question; routes back to `classify_query` with a refined approach
   if invalid (Corrective-RAG-style retry loop)
5. `simulate_scenario` — for disruption/what-if questions: traverse graph impact →
   check inventory buffers → calculate affected products/timelines
6. `synthesize` — combine results into a plain-English answer + structured data +
   confidence level
7. (optional, build after core works) `human_approval_gate` — uses LangGraph `interrupt()`
   to pause before "executing" a high-stakes recommendation (e.g., logging a reorder);
   use PostgreSQL as the LangGraph checkpointer (`langgraph-checkpoint-postgres`) so
   paused state survives restarts

### Decision engine abstraction (build LAST, after everything else works)
Some nodes (`classify_query` routing, urgency scoring, approval-gate boolean checks) can
optionally run through **TypeSafe AI's Jev model** (typed Choice/Score/Boolean decisions,
fast + cheap) instead of a full Claude call. Implement this as a swappable strategy:

- Both the Jev path and the Claude path must return the **same result shape**
  (`value`, `confidence`, `engine_used`, `latency_ms`) so downstream nodes never know
  or care which engine ran.
- Expose a UI toggle: "Use Jev for fast decisions" (on/off). When off, route the same
  decision through Claude with structured/tool-use output instead.
- Always wrap Jev calls with a fallback to the Claude path on error/timeout — never let
  the app depend on Jev being available.
- Log every decision (value, confidence, engine, latency) to a `decision_log` in graph
  state so the UI's "show reasoning" panel can display it.
- **Build the full Claude-only path first and get it completely working before adding
  Jev.** Treat Jev purely as an optional acceleration layer on top of a working system.

---

## Required Scenarios (must all work, and must be validated against manually-checked
ground truth before considering the project done)

1. **Disruption impact** — "Our aluminum supplier just had a 3-week delay. What's affected?"
2. **Single point of failure** — "Which raw materials have only one supplier?"
3. **Capacity feasibility** — "Can we fulfill a 500-unit order for [Product] by next month?"
4. **Cost impact simulation** — "If steel prices rise 15%, how does that affect margins?"
5. **Supplier comparison** — "Compare sourcing from Supplier A vs Supplier B for rubber."
6. **Second supplier lookup** — "Find a backup supplier for [material/part]."
7. **Invoice/PO mismatch** — "Which invoices don't match their purchase order or shipment?"
8. **Contract expiry** — "Which supplier contracts expire in the next 90 days?"
9. **Supplier history** — "Show our contract and shipment history with Supplier X."
10. **Billing summary** — "What's our total outstanding balance across active contracts this month?"
11. **Delayed shipment vs penalty** — "Are any shipments delayed against contracts with penalty clauses?"
12. **Warehouse/dealer stock** — "Which warehouse should restock Dealer X, and what's in transit?"

---

## UI Requirements (Streamlit)

### Structure — use tabs, do not cram everything on one screen
1. **Ask a Question** (default tab) — chat-style input + 4–6 clickable example questions
   covering different scenario types (don't make users guess what to ask)
2. **Graph Explorer** — free browsing of the Neo4j network (interactive, draggable nodes)
3. **Contracts & Billing Dashboard** — table view described below
4. **About / Architecture** — short explanation + architecture diagram for technical viewers

### Every answer (in the "Ask a Question" tab) must render as a consistent 3-layer card:
1. **Plain-English answer** with a confidence indicator (🟢 high / 🟡 estimated / 🔴 low)
2. **Supporting data** — a table and/or chart
3. **Graph trace** — the relevant Neo4j subgraph with the traversal path highlighted
   (highlighted nodes/edges in one color, rest of graph muted gray)
4. Collapsed-by-default **"Show reasoning"** section revealing the actual Cypher/SQL
   generated and the decision engine + confidence/latency used at each step

Never skip layers for "simple" answers — consistency is what makes this look like a
real product rather than a one-off script.

### Contracts & Billing Dashboard tab must show:
- Table of active contracts with color-coded expiry warnings (red < 30 days,
  yellow < 90 days, green otherwise)
- Monthly billing summary: total due / paid / overdue this month
- Per-contract shipment timeline (simple Gantt-style chart, e.g. via `plotly`)
- Clicking a contract row opens the same 3-layer answer card pattern as the chat tab
  (so it stays visually consistent, not a second disconnected feature)

### Sidebar (persistent across tabs)
- Live stats: node/relationship counts, last data refresh time
- "Use Jev for fast decisions" toggle (build after core Claude-only path works)
- After each query: small comparison of which engine handled which decision + latency

### Visual polish requirements
- One consistent accent color + neutral palette — do not use default Streamlit theme
- Descriptive loading messages tied to what's actually happening
  (e.g., "Traversing supply graph...", "Checking inventory levels...") — not generic spinners
- Deliberately designed empty/error states (e.g., "No alternate supplier found — here's
  what that means for risk"), not raw exceptions or blank screens

---

## Explicitly Out of Scope (do not build these — they were considered and rejected)
- Multi-tenant support — single company only
- Google Maps / geocoding API integration — if any geographic visual is wanted, use
  static lat/long fields on Supplier nodes plotted with `pydeck` or `folium`, no API calls
- Full SAP/ERP replacement — this is a complement, not a replacement
- Forecasting/time-series ML layer — mentioned only as "future work" in README, not built

---

## Build Order (do not reorder — later steps depend on earlier ones being solid)

1. **Schema + seed data**: Neo4j Cypher scripts + PostgreSQL schema/seed scripts for the
   full data model above. Manually validate with raw queries before moving on.
2. **LangGraph core (Claude-only, no Jev yet)**: build `classify_query`, `query_neo4j`,
   `query_postgres`, `synthesize` as working nodes. Get all 12 scenarios answering
   correctly against manually-verified ground truth.
3. **Validation/self-correction loop**: add `validate_results` node with retry routing.
4. **Evaluation harness**: a JSON file of ~15–20 test questions with expected answer
   characteristics + a script that runs them all and reports pass/fail. This is a key
   differentiator — do not skip it in favor of newer features.
5. **Streamlit UI**: build the full tab structure and 3-layer answer card exactly as
   specified above, wired to the working LangGraph agent.
6. **Contracts & Billing dashboard tab**.
7. **Polish**: loading states, empty states, color scheme, README with architecture
   diagram (Mermaid) and a "why not just ask an LLM directly" section.
8. **Optional, only if steps 1–7 are fully done and tested**: LangSmith tracing,
   human-in-the-loop approval gate with Postgres checkpointer, Jev decision-engine toggle.

## Tech Stack
- Python, LangGraph, LangChain (or direct Anthropic SDK)
- Neo4j (AuraDB free tier)
- PostgreSQL (Supabase or Neon free tier), pgvector not required for this project
- Streamlit for UI, `streamlit-agraph` or `pyvis` for graph visualization, `plotly` for
  timeline/bar charts
- Claude (Sonnet) for reasoning/synthesis; TypeSafe AI Jev optional, added last

## Definition of Done
- All 12 scenarios answer correctly and consistently through the UI
- Evaluation harness runs and reports a pass rate
- Every answer renders the full 3-layer card with working graph visualization
- Contracts & Billing dashboard shows live data and color-coded expiry warnings
- README includes architecture diagram, example queries with screenshots, and a
  deployed live link (Streamlit Community Cloud is the fastest option)
