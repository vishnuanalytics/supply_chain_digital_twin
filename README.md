# Supply Chain Digital Twin

A conversational decision-support layer over a fictional automotive components
manufacturer's supply chain — ask plain-English questions and get traceable,
data-grounded answers backed by a Neo4j relationship graph and PostgreSQL
transactional data, with every answer showing its work.

**This is a decision-support layer, not an ERP replacement.** It complements
existing systems (like SAP) by answering conversational, cross-system questions
in seconds instead of requiring someone to write SQL or Cypher, dig through
multiple screens, or wait on a report.

![Ask a Question tab showing a real answer with confidence badge and supporting data](docs/screenshots/ask_a_question.png)

## Why not just ask an LLM directly?

A general-purpose LLM has no access to this company's actual live data, so it
would either refuse to answer or — worse — confidently make up
plausible-sounding numbers. Every answer here is grounded in a real Cypher or
SQL query against real data, shown in the "Show reasoning" panel on every
answer, and passed through a self-correction step (`validate_results`) before
being trusted. Confidence is reported honestly: a definite "no backup supplier
on file" is `high` confidence, a simulation-derived estimate is `estimated`,
and a genuinely unresolved question is `low` — never all `high` for the sake
of looking polished.

## How a question is answered

```mermaid
flowchart TD
    Q["User question"] --> CQ["classify_query<br/>(LLM: routes the question)"]
    CQ -->|"graph_traversal /<br/>compound_multi_hop"| QN["query_neo4j<br/>(LLM writes Cypher)"]
    CQ -->|"inventory / cost /<br/>contract_status"| QP["query_postgres<br/>(LLM writes SQL)"]
    CQ -->|"disruption / capacity /<br/>cost_impact"| SIM["simulate_scenario<br/>(deterministic Python)"]
    QN -->|"compound_multi_hop<br/>needs both stores"| QP
    QN -->|"else"| VR
    QP --> VR["validate_results<br/>(Corrective-RAG-style check)"]
    SIM --> VR
    VR -->|"invalid, retries left"| CQ
    VR -->|"valid, or gave up"| SY["synthesize<br/>(LLM writes the final answer)"]
    SY --> A["Plain-English answer +<br/>confidence + reasoning trace"]

    QN -.-> N4J[("Neo4j AuraDB<br/>(relationships)")]
    QP -.-> PG[("PostgreSQL / Neon<br/>(transactions)")]
```

`classify_query` routes each question by type; `query_neo4j`/`query_postgres`
generate read-only Cypher/SQL on the fly (never hand-written per question);
`simulate_scenario` handles what-if questions (disruption/capacity/cost-impact)
with hand-coded traversal + arithmetic instead of freeform LLM queries, since
those need reliable multi-hop reasoning rather than creativity;
`validate_results` catches a wrong or empty result and retries with feedback
before giving up; `synthesize` writes the final plain-English answer.

## The app

Four tabs, each answer rendered as a consistent 3-layer card (plain-English
answer + confidence, supporting data table/chart, and a graph-trace
visualization), with a collapsed "Show reasoning" panel underneath revealing
the actual Cypher/SQL and which LLM engine/latency answered each step.

| Tab | What it does |
|---|---|
| 💬 **Ask a Question** | Chat-style Q&A with 6 example questions, streaming status updates tied to the actual LangGraph node running (not a generic spinner) |
| 🕸️ **Graph Explorer** | The full supply chain graph — draggable, zoomable, colored by entity type |
| 📄 **Contracts & Billing** | Active contracts with color-coded expiry warnings, this month's billing summary, a per-contract shipment Gantt chart, and click-to-drill-down into the same 3-layer card |
| ℹ️ **About / Architecture** | This project's purpose and the diagram above, for technical reviewers |

<table>
<tr>
<td><img src="docs/screenshots/graph_explorer.png" alt="Graph Explorer tab"/></td>
<td><img src="docs/screenshots/contracts_billing.png" alt="Contracts & Billing dashboard"/></td>
</tr>
<tr>
<td align="center"><em>Graph Explorer</em></td>
<td align="center"><em>Contracts & Billing Dashboard</em></td>
</tr>
</table>

## Example questions it answers

- *"Our aluminum supplier just had a 3-week delay. What's affected?"* — traces the graph to every downstream product, checks real inventory buffers, and flags risk level per material.
- *"Which raw materials have only one supplier?"* — single point of failure analysis.
- *"If steel prices rise 15%, how does that affect margins?"* — propagates a cost delta through the full bill of materials to every finished product (honestly noting that margin % isn't computable without selling-price data, rather than fabricating a number).
- *"Are any shipments delayed against contracts with penalty clauses?"* — joins graph-derived contract terms with live shipment status.
- *"Show our contract and shipment history with Great Lakes Steel Co."* — resolves a name to its graph ID first, then pulls the full transactional history, including continuity across a contract renewal.

The full list of 12 required scenarios (and the eval harness that checks them
automatically) is in [`PROJECT_SPEC.md`](PROJECT_SPEC.md) and
[`eval/test_questions.json`](eval/test_questions.json).

## Tech stack

- **LangGraph** for the agent's control flow (routing, retries, the graph above)
- **Neo4j** (AuraDB free tier) for supplier/product/contract relationships
- **PostgreSQL** (Neon free tier) for transactional data — inventory, billing, shipments, invoices
- **Groq → OpenRouter → Anthropic**, tried in that order with automatic fallback on any error — the app runs on free-tier models by default and only touches a paid key if both free providers fail
- **Streamlit** for the UI, `streamlit-agraph` for graph visualizations, `plotly` for the billing Gantt chart
- **Python** throughout; no JavaScript beyond the embedded Mermaid diagram

## Setup

1. **Databases**: create a Neo4j instance (AuraDB free tier) and a PostgreSQL
   database (Neon free tier).
2. **LLM keys**: get a free API key from [Groq](https://console.groq.com) and/or
   [OpenRouter](https://openrouter.ai); Anthropic is optional and only used if
   both free providers fail.
3. Copy `.env.example` to `.env` and fill in all the connection details and keys.
4. Install dependencies: `pip install -r requirements.txt`
5. Load the graph:
   ```
   cat neo4j/schema.cypher | cypher-shell -u <user> -p <password> -a <uri>
   cat neo4j/seed_data.cypher | cypher-shell -u <user> -p <password> -a <uri>
   ```
6. Load PostgreSQL:
   ```
   psql <connection-string> -f postgres/schema.sql
   psql <connection-string> -f postgres/seed_data.sql
   ```
   `postgres/seed_data.sql` is generated by `postgres/generate_seed_data.py`
   (deterministic, seeded) — regenerate it with `python3 postgres/generate_seed_data.py`
   if you change the reference data in that script; don't hand-edit the SQL file.

## Running it

```bash
streamlit run app.py
```

For a one-off question from the command line instead of the UI:

```bash
python3 -m agent.cli "Which raw materials have only one supplier?"
```

To run the evaluation harness (18 questions checked against ground-truth
assertions derived from the live data):

```bash
python3 eval/run_eval.py                  # all 18
python3 eval/run_eval.py --ids <id1,id2>  # a subset
```

## Project status

All 7 build steps in [`PROJECT_SPEC.md`](PROJECT_SPEC.md)'s Build Order are
complete: schema + seed data, the LangGraph core, the self-correction
(`validate_results`) loop, the evaluation harness, the full Streamlit UI, the
Contracts & Billing dashboard, and this polish pass. Both schema/seed scripts
were validated against throwaway `postgres:16-alpine` and `neo4j:5-community`
Docker containers during development, and the UI was verified with real
headless-Chromium browser testing, not just Python-level checks.

Optional, not built (by design — see PROJECT_SPEC.md's Build Order step 8):
LangSmith tracing, a human-in-the-loop approval gate with a Postgres
checkpointer, and the Jev decision-engine toggle.

## Deploying

The fastest option is [Streamlit Community Cloud](https://streamlit.io/cloud):
point it at this repo, set `app.py` as the entrypoint, and add the same
environment variables from `.env` as Streamlit secrets.
