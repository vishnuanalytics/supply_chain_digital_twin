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
- Optional (build step 8): **LangSmith** for tracing, **TypeSafe AI's Jev** as a swappable fast/cheap decision engine, **`langgraph-checkpoint-postgres`** for the human-in-the-loop approval gate's paused state

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

All 8 build steps in [`PROJECT_SPEC.md`](PROJECT_SPEC.md)'s Build Order are
complete: schema + seed data, the LangGraph core, the self-correction
(`validate_results`) loop, the evaluation harness, the full Streamlit UI, the
Contracts & Billing dashboard, the polish pass, and the optional extensions
below. Both schema/seed scripts were validated against throwaway
`postgres:16-alpine` and `neo4j:5-community` Docker containers during
development, and the UI was verified with real headless-Chromium browser
testing, not just Python-level checks. See
[`docs/development_log.md`](docs/development_log.md) for the real bugs found
along the way and the non-obvious lessons behind design decisions that
aren't visible from reading the code alone.

### Optional extensions (build step 8)

- **LangSmith tracing** — every node and every LLM call (including failed
  fallback attempts across providers) is instrumented with `@traceable`.
  Set `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` in `.env` to see full
  run traces at [smith.langchain.com](https://smith.langchain.com); leave it
  unset and nothing changes (the decorator is a no-op).
- **Human-in-the-loop approval gate** — when a disruption simulation finds a
  material already at/below its reorder point *and* a backup supplier on
  file, the graph pauses (via LangGraph's `interrupt()`, backed by a
  `PostgresSaver` checkpointer so the pause survives a restart) and the Ask
  tab shows an Approve/Reject prompt before "executing" the reorder
  recommendation (logged to a new `action_log` table). Every other question —
  the large majority — passes through untouched.
- **Jev decision-engine toggle** — the sidebar's "Use Jev for fast decisions"
  toggle routes `classify_query`'s routing/simulation-detection decisions
  through [TypeSafe AI's Jev](https://typesafe.ai) (a typed Choice/Noul model,
  ~100ms and a fraction of a cent per call) instead of a full LLM call, only
  falling through to a scoped Claude/Groq call to extract freeform simulation
  parameters when a what-if simulation is actually detected. Always falls
  back to the normal full-LLM path on any error or missing `TYPESAFE_API_KEY`
  — the app never depends on Jev being reachable.

## Deploying

The fastest option is [Streamlit Community Cloud](https://streamlit.io/cloud),
which builds and hosts straight from this GitHub repo for free. The app's
config code (`agent/config.py`) reads everything via `os.getenv(...)`, and
`app.py` bridges Streamlit Cloud's `st.secrets` into `os.environ` at startup
(a no-op locally, where config keeps coming from `.env` as usual), so no code
changes are needed between local and deployed.

1. Push this repo to GitHub (already done if you're reading this on GitHub).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with
   GitHub.
3. Click **New app**, then pick:
   - **Repository**: `vishnuanalytics/supply_chain_digital_twin`
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. Before deploying, open **Advanced settings → Secrets** and paste in the
   block below, filling in each value from your own local `.env` (never
   commit or share those real values — this template only shows the shape):

   ```toml
   LLM_PROVIDER_ORDER = "groq,openrouter,anthropic"

   GROQ_API_KEY = "your-groq-key"
   GROQ_MODEL = "openai/gpt-oss-120b"

   OPENROUTER_API_KEY = "your-openrouter-key"
   OPENROUTER_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

   ANTHROPIC_API_KEY = "your-anthropic-key"
   ANTHROPIC_MODEL = "claude-sonnet-5"

   NEO4J_URI = "neo4j+s://your-instance.databases.neo4j.io"
   NEO4J_USERNAME = "neo4j"
   NEO4J_PASSWORD = "your-neo4j-password"
   NEO4J_DATABASE = "your-aura-database-id"

   POSTGRES_URL = "postgresql://user:password@host/dbname?sslmode=require"

   DEMO_REFERENCE_DATE = "2026-09-21"

   # Optional (build step 8) - leave these out entirely to skip Jev/LangSmith
   TYPESAFE_API_KEY = "your-typesafe-key"
   TYPESAFE_MODEL = "jev-latest"
   LANGSMITH_TRACING = "false"
   LANGSMITH_API_KEY = "your-langsmith-key"
   LANGSMITH_PROJECT = "supply-chain-digital-twin"
   ```

5. Click **Deploy**. The first build takes a few minutes (installing
   `requirements.txt`); after that, pushes to `main` auto-redeploy.
6. Once it's live, sanity-check the sidebar shows real Neo4j node/relationship
   counts (confirms the DB creds and the secrets bridge both worked), then ask
   a question from the **Ask a Question** tab to confirm at least one LLM
   provider is reachable from Streamlit Cloud's network.

`.python-version` pins the build to Python 3.12 to match local development.
