# Development log

Build-order status, real bugs found and fixed, and non-obvious lessons learned while
building this project — kept here so the reasoning behind design decisions (and the
debugging that led to them) isn't lost once the code itself looks clean.

This is a portfolio project (for AI engineering job applications) building a
LangGraph + Neo4j + PostgreSQL agent that lets a non-technical user ask plain-English
supply chain questions about a fictional automotive components manufacturer. Full spec
lives in `PROJECT_SPEC.md` at the repo root; entity ID reference lives in
`docs/data_reference.md`.

**Why:** portfolio piece to demonstrate LangGraph/Postgres/Neo4j skills in interviews.
Priorities in the spec, in order: (1) working end-to-end system, (2) polished UI,
(3) architecture that's easy to explain out loud.

## Build order (must not be reordered — later steps depend on earlier ones)

1. ✅ Schema + seed data (Neo4j Cypher + Postgres schema/seed scripts) — done 2026-09-21.
2. ✅ LangGraph core (classify_query, query_neo4j, query_postgres, simulate_scenario,
   synthesize; see `agent/`) — done 2026-09-21. All 12 required scenarios from
   PROJECT_SPEC.md validated live against real Groq/OpenRouter models + Neo4j AuraDB +
   Neon Postgres and checked against manually-computed ground truth. See "LLM provider"
   and "known follow-ups" notes below for details/caveats worth knowing before step 3.
3. ✅ validate_results self-correction/retry node — done 2026-09-21 (`agent/nodes/validate.py`,
   graph rewired in `agent/graph.py`). Retry-loop control flow fully verified (stubbed LLM:
   passes-immediately / fails-then-recovers / gives-up-after-MAX_RETRIES all correct) and
   proven live twice: auto-corrected a real Groq Cypher-syntax glitch, and separately
   auto-corrected a wrong entity-type guess (misread "Great Lakes Steel Co" as a Dealer,
   retried, correctly resolved it as a Supplier). All 12 required scenarios now
   individually confirmed live end-to-end with validate_results in the loop.
4. ✅ Evaluation harness — `eval/test_questions.json` (18 cases), `eval/run_eval.py`.
   - **Run 1** (gpt-oss-20b): 12/18 passed outright; after fixing 3 overly strict test
     assertions and re-scoring the same saved answers with zero new API calls, 15/18.
     The 3 real (non-test-design) issues found: two crashes from mid-run quota
     exhaustion (not bugs), and `scenario_12` — a genuine reliability gap, root-caused
     and fixed (see below).
   - **Run 2** (qwen/qwen3.8-27b): 12/18 passed outright; one more overly strict
     assertion fixed (`variant_04`, see below) brings it to 13/18. The other 5 failures
     were `groq (qwen) returned empty content` cascading through both other blocked
     providers into a crash — see "empty content near quota exhaustion" below, this
     turned out to be a quota symptom, not a fixable code issue.
   - **Post-step-8 re-run, 2026-09-22** (see step 8 below for the bug this caught):
     across 3 Groq models tried in turn (120b, then qwen, then 20b — each hit its own
     200k TPD ceiling after roughly 9-14 questions), **17/18 scenarios got a clean
     content-based pass on at least one model.** The one holdout,
     `scenario_12_warehouse_restock_no_action`, failed three times running (empty-content
     twice, then a real bad-generation failure) — but only ever on `openai/gpt-oss-20b`,
     and the reasoning trace shows classic 20b weaknesses already documented below
     (reversed `SUPPLIES` relationship direction, hardcoded warehouse IDs instead of
     resolving them, a SQL reserved-word (`do`) alias syntax error) — the retry loop
     behaved correctly (kept rejecting, eventually gave an honest low-confidence answer
     instead of hallucinating); this is a known model-quality gap in the weakest fallback
     model, not a code regression.

   **scenario_12 root cause (fixed 2026-09-21):** compared reasoning_log traces across
   models and found `gpt-oss-20b` was consistently hallucinating a nonexistent
   `DEALS_WITH` Cypher relationship (trying Warehouse -> Region -> Dealer) across all 3
   retry attempts, so validate_results correctly kept rejecting the empty result but the
   retry loop couldn't self-correct — reclassifying the question doesn't change what the
   model believes exists in the schema. Same underlying lesson as the named-entity
   routing bug below, just applied to schema knowledge instead of routing. Fixed by
   adding an explicit closed list of the 11 real relationship types to `CYPHER_SYSTEM`.
   Verified with 4 clean successes across two models post-fix vs. 100% reproduction
   pre-fix. (It resurfaced on `gpt-oss-20b` a year later for unrelated reasons — see the
   2026-09-22 re-run above — that's a separate, still-open model-quality gap on the
   weakest fallback model specifically, not a regression of this fix.)

   **"Empty content" near quota exhaustion — corrected understanding:** initially
   diagnosed as a random transient blip and "fixed" with a same-provider retry in
   `llm_client.complete()` (real, valid improvement, kept). But a follow-up test showed
   the retry *also* returned empty — both attempts failed identically right as that
   model's quota hit ~99.99% used (199,984/200,000), with a proper 429 only appearing
   once quota was fully gone. **Conclusion: near the daily ceiling, Groq can return HTTP
   200 with empty content instead of cleanly rejecting with 429** — this is a quota
   symptom, not independently fixable in application code. Don't mistake a cluster of
   "empty content" failures for a code bug if it's happening near a model's quota
   boundary; check headroom first.

   **Eval test-design lessons learned across multiple live runs** (don't re-introduce
   these when adding future test cases): (a) don't require a specific confidence level
   for a question that might trigger a validate_results retry — "low" or "estimated" can
   be a perfectly honest label even when the final content is fully correct, if the
   pipeline had to hedge about an earlier rejected attempt; (b) for a correct graceful
   decline of an out-of-scope question, don't assume it must be low-confidence — "high
   confidence this is out of scope" is a reasonable self-assessment; check for the
   absence of hallucinated content instead (`must_exclude`), not a specific confidence
   band; (c) don't require literal ID mentions (e.g. "WH1", "P1") for an answer that
   correctly uses human-readable names instead ("North Distribution Center", "SUV
   Suspension Kit") — narrative-style answers (disruption/simulation questions) reliably
   use names only, while "enumerate these items" questions (e.g. scenario_02's "which
   materials have one supplier") reliably include parenthetical IDs; check for whichever
   the question's phrasing actually elicits, or both.
5. ✅ Streamlit UI — done 2026-09-21 (`app.py`, `ui/`). 3 of the spec's 4 tabs (Ask a
   Question, Graph Explorer, About/Architecture — Contracts & Billing is step 6). The
   3-layer answer card is `ui/answer_card.py`, reused by both the chat tab and (per
   spec) meant to be reused by step 6's dashboard row-click too. Jev sidebar toggle
   deliberately deferred to step 8 (no dead UI for a feature that doesn't exist yet).
   Verified with real headless-Chromium + Playwright screenshots, not just Streamlit's
   AppTest (which can't execute custom components' JS) — see "sandbox has no root"
   and "real bugs only browser testing caught" notes below before assuming AppTest
   alone is sufficient for any future UI work in this project.
6. ✅ Contracts & Billing dashboard tab — done 2026-09-21 (`ui/tabs/billing.py`, wired
   into `app.py` as the 3rd tab). Metrics + color-coded contracts table + per-contract
   Gantt shipment timeline, all verified against ground truth pulled directly from the
   live DB first. Row-click drill-down reuses `run_question()`/`render_answer_card()`
   via a shared `ui/agent_runner.py` — verified end-to-end live via real browser clicks
   on Streamlit's canvas-based dataframe grid (the clickable element is
   `.dvn-scroller.stDataFrameGlideDataEditor`, not the `<canvas>` itself, which
   intercepts nothing).

   **Testing artifact worth remembering for any future browser-driven Streamlit
   testing in this project:** Streamlit doesn't grow `document.body`/`documentElement`
   to fit its actual content (its own internal scroll container does the scrolling),
   so Playwright's `fullPage: true` screenshots silently clip anything beyond the
   configured viewport height rather than erroring. A screenshot that seems to "lose"
   content past a certain point doesn't mean the app failed — check
   `page.evaluate(() => document.body.innerText)` or explicitly `scrollIntoViewIfNeeded()`
   before concluding a real bug exists.
7. ✅ Polish — done 2026-09-21. `README.md` (why-not-an-LLM section, the real Mermaid
   diagram, real screenshots of all 4 tabs, setup/run/eval instructions) plus one real
   bug an audit turned up: `ui/answer_card.py`'s graph-trace layer called
   `fetch_highlighted_subgraph()` with no try/except, unlike every other data-fetching
   path in the app — fixed to degrade gracefully like the rest.

   **Deployment**, done 2026-09-21/22 (commits `c727d83`, and the actual click-through
   is the user's own manual step — deploying needs interactive GitHub OAuth login that
   an assistant shouldn't do on someone's behalf): `app.py` bridges Streamlit Community
   Cloud's `st.secrets` into `os.environ` at startup, since Cloud's Secrets UI doesn't
   auto-populate `os.environ` but `agent/config.py` reads everything via `os.getenv()`
   at import time. Verified both that the bridge is a no-op locally (AppTest) and that
   it actually forwards values when secrets are present (isolated test with a temp
   `HOME` and a real `secrets.toml`). `.python-version` pins the Cloud build to 3.12.
8. ✅ Optional/last, all three built 2026-09-21 (commit `de96daa`): LangSmith tracing,
   human-in-the-loop approval gate w/ Postgres checkpointer, Jev decision-engine toggle.
   - **LangSmith**: `@traceable` on every LLM call site (`llm_client._call_groq/
     _call_openrouter/_call_anthropic/complete`, `decision_engine.classify_via_jev`) — no
     graph-level wiring needed since LangGraph nodes already execute inside a traced
     Runnable context, so `LANGSMITH_TRACING=true`+`LANGSMITH_API_KEY` alone (read
     directly by langsmith's own SDK from the env) lights up full nested traces. No-op
     when unset — confirmed via AppTest with no key present.
   - **Human-in-the-loop**: `agent/nodes/approval.py`'s `human_approval_gate`, wired
     `simulate_scenario -> human_approval_gate -> validate_results`. Only fires (calls
     `interrupt()`) when a disruption sim found a material at `risk_level == "high"` AND
     a real backup supplier resolves via
     `(rm)-[:SOURCED_FROM {is_primary:true}]->(primary)` then
     `(backup)-[:BACKUP_FOR]->(primary)` (note: `BACKUP_FOR` is Supplier->Supplier, NOT
     material->supplier directly — easy to get wrong). Approved/rejected actions go to a
     new `action_log` Postgres table (`db.log_action()`, the one deliberate non-LLM write
     path, separate from the read-only `_assert_read_only`-guarded `run_sql`/
     `run_cypher`). `agent/checkpointer.py` wraps a process-wide `PostgresSaver` (needs
     `psycopg[binary]` — plain `psycopg` has no pq backend and raises `ImportError: no pq
     wrapper available` without it). **Interrupt/resume mechanics confirmed empirically
     against installed langgraph 1.2.11** (verify per-version, don't assume): a paused
     `.invoke()`/`.stream(stream_mode="values")` surfaces `state["__interrupt__"]` = a
     tuple of `Interrupt(value=..., id=...)`; resume via
     `graph.invoke(Command(resume={...}), config)` with the SAME `thread_id`. Critically,
     **the whole interrupted node re-runs from its start on resume**, not just the code
     after `interrupt()` — keep everything before the `interrupt()` call read-only/
     idempotent, only do real side effects (DB writes) after it. Verified live end-to-end
     (real Neo4j + real Neon Postgres + real interrupt/resume, no mocks) using the
     aluminum-supplier disruption scenario (RM3, backed by S6). CLI and eval harness both
     auto-approve any interrupt (no UI to click in a headless context) — necessary, not
     optional: `scenario_01_disruption` and `variant_01_disruption_rephrased` both hit
     this exact recommendation.
   - **Jev**: real product, TypeSafe AI (launched 2026-09-15). Real PyPI package
     `typesafe-sdk` (imports as `typesafe_sdk`: `TypeSafeClient`, `Choice`, `Score`,
     `Noul`, base exception `TypeSafeError`). `agent/decision_engine.py` uses Jev for
     JUST classify_query's categorical decisions (`query_type` Choice,
     `requires_simulation` Noul, `simulation_type` Choice) in ONE batched call (~100ms) —
     `simulation_params` (freeform entity/quantity extraction) has no typed-primitive
     equivalent, so a scoped prompt (`prompts.SIMULATION_PARAMS_SYSTEM`) still calls
     Claude/Groq for just that, only when `requires_simulation` is true. Net effect:
     non-simulation questions (the majority) skip the full classify LLM call entirely
     when Jev succeeds. Any Jev error (missing `TYPESAFE_API_KEY` — the default state,
     no signup done — auth failure, timeout) falls through to the original full-Claude
     classify path unchanged; both attempts get logged to a new `decision_log` state
     field. Sidebar toggle "Use Jev for fast decisions" defaults off, warns if no key is
     set while toggled on.
   - **Real regression found and fixed via the post-merge eval re-run, 2026-09-22**:
     `scenario_09` crashed with `Type is not msgpack serializable: Date`. Root cause:
     Contract nodes in Neo4j have real `date()` properties (`neo4j/seed_data.cypher`),
     returned by the driver as `neo4j.time.Date` (not a `datetime.date` subclass) —
     harmless before step 8, but now every graph run is checkpointed via `PostgresSaver`,
     and its serializer doesn't know that type. Fixed in `agent/db.py`'s `run_cypher()`:
     recursively normalize any `neo4j.time.Date/DateTime/Time` in returned rows to native
     Python types via `.to_native()` before they enter graph state. Verified twice: an
     isolated repro with Great Lakes Steel Co's real contract dates (crashed before,
     clean after), then a real harness pass of `scenario_09` itself once quota allowed.
   - **Cost note (self-inflicted, avoidable)**: while verifying Groq headroom before a
     live test, requested `max_tokens=65536` with no `reasoning_effort` cap expecting the
     "zero-cost headroom trick" (see below) to reject it for free — but headroom was NOT
     actually near the daily cap at that moment, so Groq accepted and ran the request for
     real, and the reasoning model spent most of that huge budget on its hidden reasoning
     channel, burning ~15-20k tokens for nothing. **That trick is only actually free when
     remaining headroom is already smaller than the oversized max_tokens requested** — if
     there's still substantial headroom, an oversized probe request gets accepted and
     really runs, at real cost. Don't use it as a routine pre-flight check; only reach for
     it when you already suspect you're close to the daily ceiling.

## Portfolio extensions (beyond the spec), 2026-09-22

Built after the spec's Definition of Done was already met - CI + pytest suite, multi-turn
conversation memory, a prompt-injection red-team pass, and light RAG (semantic search).
See the README's "Portfolio extensions" section for what each one does; the notes below
are the things worth remembering if extending any of them further.

- **`sentence-transformers` almost shipped, then got swapped for `fastembed`, over a
  real deployment-size problem, not a style preference.** `pip install
  sentence-transformers` pulled in PyTorch's default CUDA-enabled wheel - 1.2GB for torch
  alone, plus ~3.2GB of unused NVIDIA CUDA libraries the CPU-only inference here would
  never touch, ~4.5GB total for embedding a single 80MB model. Even switching to the
  CPU-only torch wheel (`--index-url .../whl/cpu`) only got torch itself down to ~770MB.
  That's a real risk to an already-live Streamlit Cloud free-tier deployment's build size
  and memory budget, not just local disk space. `fastembed` (Qdrant's library, ONNX
  runtime instead of PyTorch) serves the exact same model
  (`sentence-transformers/all-MiniLM-L6-v2`) for ~230MB total including its own
  dependencies (onnxruntime + scipy/sklearn) - same 384-dim embeddings, same quality
  (verified: identical top-3 semantic search results, same real supplier notes, both
  models), a fraction of the footprint. **How to apply:** for any future "add local
  ML inference" feature on a resource-constrained deployment target, check the actual
  installed size *before* committing to a library - `du -sh .venv` before/after, not just
  reading the package's own marketing copy - and specifically watch for a default CUDA
  wheel getting pulled in for what's actually CPU-only inference.
- **pgvector + psycopg2: don't trust `register_vector`'s adapter for a plain Python
  list.** Passing a `list[float]` as a query parameter got adapted to a Postgres
  `numeric[]` array, not `vector` - `operator does not exist: vector <=> numeric[]`. The
  robust fix: format the embedding as a literal string (`"[0.1,0.2,...]"`) and cast
  explicitly in the SQL (`%s::vector`), never relying on an adapter to guess the right
  type. Confirmed via direct testing before committing to this in `agent/semantic_search.py`.
- **`supplier_notes` is a separate seed pipeline on purpose** (`postgres/
  generate_supplier_notes.py` -> `postgres/supplier_notes_seed.sql`, not folded into
  `generate_seed_data.py`) - this whole feature needs pgvector, which not every Postgres
  instance has, so `postgres/schema.sql`'s `CREATE EXTENSION IF NOT EXISTS vector;` and
  the `supplier_notes` table creation are designed to fail *silently* (psql's default
  non-strict mode continues past an error) rather than break the rest of the schema for
  someone on a Postgres without it - confirmed this reasoning holds, not just assumed.
  **Known, accepted gap:** if a user's Postgres genuinely lacks pgvector,
  `classify_query` can still route a qualitative question to `semantic_search`, which
  then fails against a missing table - `validate_results`' retry loop would re-attempt,
  and since the classification is genuinely correct for that question, every retry would
  likely re-route the same way (the same class of "retrying can't fix a missing
  capability" issue documented elsewhere in this log). Not fixed further given this only
  matters for a non-Neon Postgres without pgvector, an edge case the README already
  flags as skippable.
- **Live-verified the whole pipeline end-to-end**, not just the isolated search
  function: asked "Are there any compliance or quality concerns with our suppliers?"
  through the real agent - `classify_query` correctly chose `query_type:
  "semantic_search"`, `query_semantic` found the right notes (Continental Rubber's real
  REACH non-compliance ranked first), and `synthesize` correctly characterized it as a
  *resolved* past issue while accurately describing the other suppliers' notes as clean
  records rather than concerns - genuinely good synthesis, not just retrieval working.

## Non-obvious data design decisions

Needed to write correct Cypher/SQL against this data:

- Contracts only exist for raw-material suppliers (S1–S6), not the three third-party
  vendors (V1–V3) — matches the graph model, which only gives `Supplier` nodes a
  `HAS_CONTRACT`/`PREVIOUSLY_CONTRACTED` relationship.
- S6 ("Diversified Metals & Materials Inc") is a backup-only supplier with no primary
  material and no contract of its own — it only appears via `BACKUP_FOR` and
  `SOURCED_FROM {is_primary: false}` edges, backing RM1, RM3, and RM9.
- Postgres `contracts` table has two columns added beyond the spec's literal listing —
  `penalty_clause` (boolean) and `penalty_terms` (text) — needed to make required
  scenario 11 ("delayed shipment vs penalty") answerable; everything else matches the
  spec's schema verbatim.
- `monthly_billing`/`shipments`/`invoices` rows are generated per contract for up to the
  last 12 calendar months *of that contract's own active window* (see
  `contract_months()` in `postgres/generate_seed_data.py`), not a flat trailing 12
  months from today — a contract that started recently legitimately has fewer months of
  history, and the two expired contracts (C0a for S1/RM1, C0b for S4/RM8) carry their
  own full historical year so the "supplier history" scenario has continuity across a
  contract renewal.
- `postgres/seed_data.sql` is a generated artifact — regenerate it with
  `python3 postgres/generate_seed_data.py` after editing the generator; never hand-edit
  the SQL file directly.
- Both `neo4j/*.cypher` and `postgres/*.sql` were validated by spinning up throwaway
  `postgres:16-alpine` and `neo4j:5-community` Docker containers and spot-checking all
  12 required scenarios — repeat that validation step after any schema/seed change
  before moving on to the next build step.

## LLM provider notes

Deviates from the spec's "Claude for reasoning" default: Groq and OpenRouter free-tier
models as primary, Anthropic only as a paid fallback. `agent/llm_client.py` is a
provider-agnostic `complete()` that tries providers in `LLM_PROVIDER_ORDER` (env var,
default `groq,openrouter,anthropic`) and falls back to the next on any error, including
empty-content responses. Neo4j is AuraDB, Postgres is Neon.

**Prompt-engineering follow-ups worth knowing if quality regresses after further
changes**: gpt-oss models on Groq spend part of their token budget on a hidden reasoning
channel and can return empty content on a short budget — `llm_client.complete()` treats
empty content as a provider failure and falls through, and Groq calls pass
`reasoning_effort: "low"`. `classify_query`'s simulation trigger and entity_type field,
and the SQL prompt's warnings about `shipments`' actual scope (raw-material
supplier->facility only, never warehouse/dealer-related) and about not re-deriving
numeric comparisons in `synthesize`, all needed concrete few-shot examples before the
abstract rule alone was followed reliably — if a similar systematic misclassification
shows up again, reach for a worked example before more prose.

**Known minor gaps:** (1) there's no real finished-goods shipment-tracking table (only
raw-material `shipments` supplier -> facility and `dealer_orders.fulfillment_status`),
so "what's in transit to warehouse X" about finished products can only honestly be
answered as "not tracked" or via the dealer_orders proxy. (2) On large row-count results
(e.g. a supplier's full multi-contract shipment history), synthesize can occasionally
make a small narrative arithmetic slip (e.g. off-by-one total count) despite the
underlying data being correct.

**A real architectural bug (fixed):** PostgreSQL has no name columns anywhere (only
IDs). `classify_query` was routing named-entity questions (e.g. "history with Great
Lakes Steel Co") to Postgres-only query_types, which have no way to resolve a name to an
ID — and critically, retrying via validate_results could never fix this, since every
retry re-classified the question the same (locally correct) way and got stuck on the
same missing information. Fixed by teaching classify_query to route any named-entity
question through compound_multi_hop instead (graph lookup first), with a worked example.
If a future scenario gets stuck in a retry loop that never recovers (as opposed to one
retry fixing it), suspect this same class of bug first — a missing capability that
retrying with the same node topology cannot solve — before assuming it's just model
flakiness.

## Operational notes on free-tier LLM quotas

Free-tier LLM quotas are easy to exhaust during heavy testing, and recovery is much
slower/stickier than "daily" suggests: a single debugging session can burn all of Groq's
200,000 tokens/day (TPD) cap and OpenRouter's 50 requests/day free-tier cap (both
platform-level anti-abuse limits — OpenRouter's free-tagged models are $0/token, but the
account still gets throttled: 50 req/day with zero credits ever added, jumping to 1000
req/day the moment any small credit balance exists) purely from iterative debugging
(each full agent question fires 3-5+ LLM calls, more with retries). OpenRouter's reset
is a fixed daily UTC boundary (midnight); Groq's is a rolling window that can stay
pinned near its ceiling for hours of real wall-clock time, not the "~5-15 min" its own
error message estimates.

A tiny/cheap probe call can succeed right when a sliver of headroom opens, but that
success itself consumes the sliver, so the very next real (larger) call immediately
fails again. The zero-cost way to check headroom *when already near the ceiling*:
request more `max_tokens` than could possibly be available (but ≤ the model's hard
per-request cap) so the request always gets rejected before generating anything, and
parse "Used N" out of the 429 error's message text. **This is only actually free near
the ceiling** — if there's still substantial headroom, Groq accepts the oversized
request and really runs it, at real cost (see the 2026-09-22 cost note in step 8 above).

**Groq's TPD rate limit is per-model, not per-account** — the error message names the
model ("Rate limit reached for model `openai/gpt-oss-120b`"). Switching `GROQ_MODEL`
gives a completely independent 200k daily budget per model:
`openai/gpt-oss-120b` (main dev model, fastest, highest quality) — `openai/gpt-oss-20b`
(slower, more prone to schema mistakes) — `qwen/qwen3.8-27b` (good quality, clean JSON/
Cypher/SQL output, needs `max_tokens<=16384` not 120b/20b's 65536 cap). **Preference
order once quota isn't a constraint: 120b for speed/quality, qwen as a close second, 20b
last** — 20b is the least reliable of the three observed live. Check `.env`'s current
`GROQ_MODEL` value before assuming which model's behavior you're seeing.

The `ANTHROPIC_API_KEY` fallback needs both a workspace-scoped key (an org-level/admin
key fails with "not scoped to a workspace" — regenerate at console.anthropic.com with a
specific workspace selected) and actual credit in Plans & Billing (a valid key with a
zero balance fails with "credit balance is too low").

**When resuming this project:** budget LLM calls consciously during heavy debugging
sessions (batch scenario checks, don't re-run passing scenarios "just to be sure"), and
don't loop on quota-polling schemes for more than one or two attempts before just
deciding how to proceed (wait, add credit, or switch models).

## Environment quirks

**No root access in the dev sandbox** — no `apt-get install`, `sudo`, etc. Needed for
real browser testing (Playwright's bundled Chromium wouldn't launch, missing shared
libs one at a time). Workaround that works without root: `apt-get download <pkg>`
(downloads the `.deb` to cwd, no install, no sudo needed) + `dpkg -x <pkg>.deb <dir>`
(extracts contents to a plain directory) + `LD_LIBRARY_PATH=<dir>/usr/lib/x86_64-linux-gnu`
when launching the browser process. Full package list needed: libnspr4, libnss3,
libasound2t64, libatk1.0-0t64, libatk-bridge2.0-0t64, libcups2t64, libdbus-1-3, libdrm2,
libgbm1, libgtk-3-0t64, libpango-1.0-0, libx11-6, libxcomposite1, libxdamage1, libxext6,
libxfixes3, libxkbcommon0, libxrandr2, libxshmfence1, libatspi2.0-0t64, libcairo2
(Ubuntu noble package names).

**Real bugs only actual browser testing caught** (AppTest alone would have missed all of
these): Streamlit's own `AppTest` framework runs the app in-process and is genuinely
useful for catching Python-level exceptions across all tabs/widgets without a browser,
but it never executes a custom component's JavaScript (streamlit-agraph's vis.js,
mermaid.js), so it cannot catch bugs that only manifest in actual rendering.

- `streamlit_agraph.Config.__init__` always appends `"px"` to `width`/`height`, so
  `width="100%"` silently became the invalid CSS string `"100%px"` — pass a plain int.
  Separately, `groups` defaults to `None` (vis.js's validator rejects null, pass `{}`),
  and any kwarg not in Config's known set gets silently absorbed and sent to vis.js
  as an unrecognized option with zero effect.
- The Mermaid architecture diagram intermittently failed with a geometry error, "Could
  not find a suitable point for the given distance" — the real cause: Streamlit renders
  every tab's content immediately on page load, including inactive ones (CSS
  `display:none`, not actually unrendered/deferred), so the diagram's dagre layout
  engine tried to measure real text/node dimensions inside a zero-size hidden container
  before the user ever clicked that tab. Fixed by polling the iframe's own
  `document.body.offsetWidth/Height` and deferring the render until non-zero. If a
  future custom HTML/JS component embedded in a Streamlit tab behaves correctly in
  isolation but flakes inside the app, suspect this exact hidden-tab-panel dimension
  issue before anything else.
- Two Streamlit APIs used in the first draft (`st.components.v1.html`,
  `use_container_width=True`) were already past their own stated removal dates — still
  worked, but only warned instead of erroring; migrated to `st.iframe`/
  `width="stretch"` proactively rather than leaving stale-but-working calls.
- The active-tab indicator rendered in Streamlit's default red regardless of the
  custom CSS injected via `st.markdown` — baseweb's internal tab styling isn't
  reliably overridable by injected CSS; needed an actual `.streamlit/config.toml`
  `[theme]` block (`primaryColor` etc.) to take effect.

## Persistent, session-wise chat history — 2026-09-22

`st.session_state`-based conversation memory (above) is purely in-memory — a page
refresh or a server restart wipes it, which isn't "conversation history" so much as
"conversation memory for as long as the tab stays open." Added a `chat_history`
Postgres table (`postgres/schema.sql`) storing one row per answered turn: `session_id`
(a UUID generated per browser session, stored in `st.session_state`), the question, and
`state_json` — the *entire* `render_answer_card()`-renderable state dict (answer,
confidence, neo4j_result/postgres_result/semantic_result, reasoning_log, etc.), not just
question/answer text. Storing the full state means "load a past session" renders an
identical 3-layer answer card with zero special-casing in `answer_card.py` — the loaded
state is structurally identical to a live one. Only successful turns are logged (an
errored turn isn't meaningful conversation memory), matching the existing in-memory
`conversation_history` pattern.

Three new functions in `agent/db.py`: `log_chat_turn` (write), `list_chat_sessions`
(one row per session — first question as a label, turn count, last-active time — for a
lightweight session browser without pulling every session's full state_json),
`get_chat_session` (every turn in one session, oldest first). `agent/db.py`'s
`_remember()` call site (`ui/tabs/ask.py`) wraps `db.log_chat_turn` in a bare
try/except — persistence is a nice-to-have and must never block the live chat on a DB
write failure.

**UI redesign, same day, direct user feedback ("I thought you'd make this like GPT
chat")**: the first pass put the session browser behind a "📜 Past conversations"
popover local to the Ask tab, with a separate "🔄 New conversation" button next to it —
functionally equivalent to ChatGPT's history, but hidden until clicked, which doesn't
read as "chat history" the way ChatGPT's always-visible left rail does. Moved it into
the real Streamlit sidebar (`ui/sidebar.py`, which already renders before every tab in
`app.py` and already holds global app state like the Jev toggle) as a "💬
Conversations" section: an "➕ New chat" button plus every past session listed as its
own clickable row (`new_chat_session()`/`load_chat_session()`, replacing the tab-local
`_reset_conversation()`/`_load_session()`). Because it's real `st.session_state` (not
tab-scoped), this works identically no matter which tab is open, same as ChatGPT's
sidebar staying put across different chats. `ui/tabs/ask.py` shrank back down to just
the header/caption plus the existing question flow — `_remember()` is the only
persistence-related code left there.

Confirmed directly against the live Neon Postgres (not assumed) that psycopg2
auto-casts a `json.dumps(..., default=str)` string to `jsonb` on `INSERT` and hands it
back as a native Python dict on `SELECT` — no manual `json.loads()` needed anywhere in
the read path. `default=str` matters because `state` can carry `Decimal`/`date` values
surfaced from Postgres rows earlier in the same turn, which aren't natively
JSON-serializable.

**Browser testing note:** real Chromium wouldn't launch in this sandbox this round
(`libnspr4.so` missing, no root — see the `apt-get download` + `dpkg -x` workaround
documented above) and re-doing that workaround wasn't worth the time for this feature.
Instead ran a direct end-to-end script against the live database exercising the actual
production functions (`ask._remember` → `db.log_chat_turn`, `db.list_chat_sessions`,
`ask._load_session` → `db.get_chat_session`) rather than mocks — confirmed a two-turn
session round-trips correctly (list shows it with the right first-question/turn-count,
load reconstructs `history`/`conversation_history`/`session_id` exactly) — then cleaned
up the test rows. 7 new mocked unit tests added in `tests/test_chat_history.py`
(121 total, all green) covering `log_chat_turn`'s JSON serialization (including the
`Decimal`/`date` → `str` fallback) and both read queries' SQL shape. Re-ran the same
live round-trip script after the sidebar redesign above against
`new_chat_session`/`load_chat_session` (the renamed/relocated functions) — identical
result, confirming the move didn't change any actual persistence behavior.

## Ask tab rendered as an actual chat thread — 2026-09-22

Direct user feedback: *"I thoght you make this like gpt chat... My request is can I
ask continous questions in a single seassion... Like I am chatting with you I need
like that flow, continuous chat rather for single question and answer."* The
underlying capability was already there - `conversation_history`/`resolved_question`
(the multi-turn memory extension, above) genuinely thread context between turns - but
the Ask tab rendered every turn as a separate `**Q: ...**` + 3-layer report card,
newest first (`reversed(history)`), which reads as a stack of one-off Q&As, not a
conversation. Rewrote `ui/tabs/ask.py` to actually look like a chat:

- Every turn (question + answer/error) is wrapped in `st.chat_message("user")` /
  `st.chat_message("assistant")` bubbles, rendered **chronologically** (oldest first,
  not reversed) - a real scrolling conversation log, with `st.chat_input` naturally
  pinned at the bottom.
- A new question is rendered live, inline, at the end of the existing thread (not via
  the history loop) so `run_question()`'s `st.status(...)` "thinking..." indicator
  shows up in the right place - the next message in the conversation - rather than at
  the top of the page.
- Example-question suggestions only show before the thread has started
  (`if not history and not pending_approval and not has_pending_question`) - like a
  typical chat app's empty-state prompts, not permanent clutter once a conversation is
  underway. Needed a peeked-but-not-popped `has_pending_question` check (not just
  `history`) **plus** an explicit `st.rerun()` right after setting `pending_question`
  from an example click - without both, examples still showed for one extra render
  pass alongside the in-progress first answer, since Streamlit executes top-to-bottom
  and `history` isn't populated until deep in that same pass. Verified this exact
  two-part fix in both a real browser (Playwright) and a mocked `AppTest`.
- `render_error_card()` gained a `show_question: bool = True` param (`ui/agent_runner.py`)
  so its own built-in "**Q: ...**" line can be suppressed when the question is already
  shown by the surrounding chat bubble - `ui/tabs/billing.py`'s drilldown call is
  unaffected (still defaults to showing it, no separate bubble there).

**Verification without live LLM quota:** all three providers were quota-exhausted
during this work (Groq empty-content near its daily ceiling even after switching to
`openai/gpt-oss-20b`, OpenRouter's free-tier daily cap hit, Anthropic has no credit -
see the LLM provider notes elsewhere in this file), so a real successful two-turn
conversation couldn't be screenshotted this round. Used `streamlit.testing.v1.AppTest`
instead, with `agent.graph.get_graph()` mocked (patched as `ui.agent_runner.get_graph`,
since it's imported by name - same gotcha class as `llm_client._PROVIDER_FNS`), to
prove the actual behavior that matters: asking two questions in one session renders
as `["user", "assistant", "user", "assistant"]` (chronological, not reversed), the
graph is invoked exactly twice, and critically **the second call's
`conversation_history` genuinely contains the first turn's real Q&A** - not just a
UI that looks continuous, but proof the context is actually threaded through. New
tests: `tests/test_ask_tab_chat_flow.py` (2 tests, 123 total suite). Also did get a
real (non-LLM) browser confirmation of the visual layer itself: chat bubbles with
correct user/assistant avatars, no duplicated question text, and examples correctly
disappearing the instant a question is submitted (all via the pre-existing
`apt-get download` + `dpkg -x` no-root Chromium workaround documented earlier in this
file) - the only thing not re-confirmed live was a *successful* (non-error) answer
rendering inside a bubble, since that code path (`render_answer_card`) is unchanged
from before and was already proven live in earlier build steps.

**Real bug the zero-cost headroom trick did NOT protect against, worth remembering
again:** temporarily switched `GROQ_MODEL` to `openai/gpt-oss-20b` to find quota
headroom for this test; the check request (`max_tokens=65536`) got HTTP 200 and
actually ran for real (not rejected) - meaning there WAS headroom before this probe,
which the probe itself then consumed. Confirms the existing note: this trick is only
"free" when headroom is already smaller than the oversized request; otherwise it
silently spends real quota. `GROQ_MODEL` restored to `openai/gpt-oss-120b` afterward.

## 4th LLM provider (Gemini) + a manual model picker — 2026-09-22

Direct motivation: this same session hit all three providers (Groq, OpenRouter,
Anthropic) exhausted/blocked simultaneously, more than once, with no way to answer a
single question until something reset. User asked for Ollama as a local fourth
fallback, but their laptop can't run even a small local model - so the real fix is
another genuinely independent *hosted*, free provider, plus a way to manually pick
which model answers a given question (useful both to route around a dead provider on
the spot, and to demo the multi-provider architecture directly).

**Gemini added as a real 4th provider** (`agent/llm_client.py::_call_gemini`), raw
`urllib` HTTP like `_call_openrouter` (no new SDK dependency, consistent with the
existing pattern). Key facts confirmed live, not assumed, since my training data
predates whatever Gemini's current lineup looks like:
- The user's pasted key was NOT a standard `AIzaSy...` AI Studio key format (started
  `AQ.` instead) - tested directly against the real API rather than assuming it was
  wrong; it authenticated fine, so key format apparently varies.
- `gemini-2.0-flash` (my first guess) 404'd with an explicit deprecation message
  naming its replacement; `gemini-3.6-flash` is the currently correct model id for
  this account as of today.
- Like Groq's gpt-oss models, `gemini-3.6-flash` spends part of `maxOutputTokens` on
  a hidden "thinking" pass before the visible answer (confirmed: 72 total tokens for a
  2-token reply with thinking on, 8 total with it off) - `generationConfig.
  thinkingConfig.thinkingBudget: 0` disables it, the Gemini-API equivalent of Groq's
  `reasoning_effort: "low"` trick used elsewhere in this file, and for the same reason
  (don't let hidden reasoning starve short structured JSON/Cypher/SQL outputs).
- Verified against REAL pipeline nodes, not just a "say OK" probe: forced via the new
  override mechanism (below), `classify_query` produced correct structured JSON
  (`parse_ok: True`), and `query_neo4j` generated genuinely correct Cypher
  (`MATCH (rm:RawMaterial)-[:SOURCED_FROM]->(s:Supplier) WITH rm, count(DISTINCT s)...`)
  that returned real matching rows. Then confirmed live end-to-end through the actual
  browser UI, all four pipeline nodes (`classify_query`→`query_neo4j`→
  `validate_results`→`synthesize`) running through Gemini alone while Groq/OpenRouter/
  Anthropic were still exhausted - real answer, real table, rendered correctly in the
  chat thread.
- `LLM_PROVIDER_ORDER` default (both `agent/config.py` and `.env`) updated to
  `groq,openrouter,anthropic,gemini` - Gemini is now a genuine part of Auto's fallback
  chain, not just a manually-selectable extra.

**Manual model picker** (new "🧠 Model" section in `ui/sidebar.py`, right above
"Decision engine"): a selectbox with "Auto (recommended fallback chain)" plus one
entry per model in the new `llm_client.KNOWN_MODELS` registry, filtered to only
providers with a configured API key (`_available_model_choices()`) so nothing
guaranteed-to-fail is ever offered. Picking a specific model forces it via
`llm_client.set_override(provider, model)`, called from `ui/agent_runner.py`'s
`run_question()`/`resume_question()` right before each graph run and reset in a
`finally` block.

**Deliberate design choice, confirmed with the user first (AskUserQuestion) rather
than assumed:** a manually-picked model gets NO cross-provider fallback if it fails -
`complete()` raises `"Manually selected {provider} failed: ..."` immediately instead
of silently continuing down the Auto chain. Reasoning: silently answering via a
different model than the one explicitly chosen would defeat the point of picking one
(demoing that specific model, or diagnosing whether it specifically is up right now).

**Why `contextvars.ContextVar` and not a plain module global for the override:**
Streamlit runs each browser session's script in its own thread, and this app is
deployed on Streamlit Cloud where multiple real users could be connected
simultaneously - a plain global would let one user's manual model pick leak into a
concurrent session's questions. `_override: ContextVar[dict | None]` avoids that.
`set_override()` returns a token; every call site resets it in `finally`, matching the
docstring's own warning about a pick leaking into the next question if reset is
skipped.

**Also discovered along the way:** OpenRouter's free-tier rate limit
(`X-RateLimit-Limit: 50`) is account-wide across every `:free` model, not per-model
like Groq's - confirmed via `/api/v1/models`, which listed 21 real free models on this
account. The sidebar surfaces this directly: picking a different Groq model shows "own
headroom" (genuinely true), picking a different OpenRouter model shows "changes output
quality, not quota" (so a user doesn't wrongly assume switching OpenRouter models is a
way to dodge its daily cap).

New tests: `TestManualOverride`/`TestKnownModels`/`TestCallGemini` in
`tests/test_llm_client.py`, plus `tests/test_model_picker.py` for
`_available_model_choices()`/`current_llm_override()` - 138 total, all green.

## Sidebar white-on-white contrast bug, and the "model resets to Auto" red herring
## — 2026-09-22

User report, with a screenshot: a past-session button ("How many suppliers we have")
rendered completely unreadable (white text on white background), and separately "once
I ask second question the model selection is going back to auto."

**First isolated whether the second complaint was a real state bug or the same
rendering issue**, since guessing wrong would mean fixing the wrong thing: wrote a
deterministic `AppTest` (mocked graph, no live LLM needed) that selects a specific
model in the sidebar, asks two questions in sequence, and checks
`at.session_state["llm_choice"]` after each. It never changed - stayed
`"gemini::gemini-3.6-flash"` through both questions. **So there was only one real bug,
not two** - the selectbox becoming unreadable after a rerun looks exactly like "it
reset to Auto" even though the underlying value never moved. Worth remembering this
diagnostic move: when two symptoms could share a root cause, check whether the STATE
actually changed before spending time on two separate fixes.

**Root cause, found by walking the real DOM in a real browser (not the CSS source),
in two rounds** because my first attempted fix was itself based on a wrong assumption
about Streamlit's internal markup:

1. `ui/theme.py`'s sidebar styling had `section[data-testid="stSidebar"] * {{ color:
   NEUTRAL_100 !important; }}` - correct for plain text sitting directly on the dark
   sidebar background, but buttons and the selectbox keep their own white control
   background even inside the sidebar, so this forced white-on-white there.
2. **First fix attempt failed**: added `section[data-testid="stSidebar"] div[data-
   testid="stButton"] button {{ color: NEUTRAL_900 !important; }}`, which raised the
   right specificity but didn't work. Inspecting the live DOM (`getComputedStyle` at
   each level) showed why: the `<button>` element itself DID get the fix, but
   Streamlit nests the actual visible label several levels deeper (`button > div >
   span > span > div.stMarkdownContainer > p`), and the blanket `*` rule matches that
   inner `<p>` **directly**, not just via inheritance from `<button>` - a directly-
   matched `!important` rule beats an inherited value regardless of the ancestor's own
   color. Fix: every override rule needs its own trailing `*` too (`button, button *`),
   to directly out-specificity the blanket rule at every nesting level, not just style
   the outer element and hope it cascades down.
3. **Second fix attempt also initially failed** for the model picker specifically:
   assumed the selectbox was a BaseWeb `[data-baseweb="select"]` element (an
   assumption from general Streamlit knowledge, not checked against this actual
   installed version) - that selector matched zero elements. The real DOM (checked via
   `outerHTML`) showed this Streamlit version (1.64.0) implements `st.selectbox` as a
   **react-aria ComboBox**: a plain `<input>` element carrying the displayed value as
   its `value` *attribute*, not as `textContent` - a `textContent`-based DOM search for
   the visible label found nothing for exactly that reason. Fix: target
   `div[data-testid="stSelectbox"] input` directly.

**How to apply:** don't assume a specific Streamlit version's internal DOM structure
(BaseWeb classes, `data-baseweb` attributes, where a widget's real text content lives)
from general knowledge - it has changed before and will again. When a CSS fix doesn't
visibly work, inspect the ACTUAL rendered DOM (`getComputedStyle`, `outerHTML`) in a
real browser before writing a second guess; specificity math is only useful once the
selector is confirmed to match the right element at all.

Verified: both the "How many suppliers we have" button and a genuinely-selected model
("Gemini — gemini-3.6-flash") render fully legible (dark text, `rgb(15,23,42)`, on
white) after the fix, confirmed via computed style, not just a screenshot glance.

## Graph trace collapsed into its own dropdown — 2026-09-22

Direct user request: "Can you add drop down option for the knowledge graph tace to
like, show reasoning." `ui/answer_card.py`'s Layer 3 (the vis-network subgraph
visualization) used to render inline and always-open, right below the supporting data
table - now wrapped in its own `st.expander("🕸️ Show graph trace", expanded=False)`,
matching Layer 4's existing `st.expander("🔍 Show reasoning", ...)` pattern (which also
got the same icon-prefix treatment for visual consistency). Mechanical change - the
fetch/render logic inside is untouched, just re-indented into the `with` block.

Reasoning voiced back to the user in the preceding conversation turn (they'd asked how
to justify showing tables/graph/reasoning at all to an interviewer): the graph trace is
supporting evidence a user checks occasionally, not something needed to read every
answer - collapsing it by default keeps the primary answer text the focal point, same
progressive-disclosure argument already applied to the reasoning panel.

Verified via `AppTest` (5 new tests, `tests/test_answer_card.py`, 143 total): both
expanders present and collapsed by default, expanding the graph trace panel doesn't
raise - including one run against the *real* live Neo4j (not mocked) to rule out any
interaction between the new expander wrapping and `fetch_highlighted_subgraph`'s actual
query. A live-browser round-trip (load a past session via the sidebar, click to
expand) was attempted but Playwright's click on the sidebar's session-list button was
flaky in this sandbox for reasons unrelated to the change itself (`load_chat_session`
was independently confirmed correct via a bare script, returning real persisted rows)
- the AppTest coverage above was judged sufficient rather than continuing to fight
browser-automation flakiness for a low-risk, mechanical UI change.

## Real bug: the graph trace was invisible after collapsing it — 2026-09-22

Direct follow-up report on the change above: "the graph is not showing and give a
center to fit option to make graph visible even it is missed by too much zoom."

**Root cause, found by inspecting the live DOM (not guessed):** a Streamlit custom
component's iframe (streamlit-agraph's `agraph()`) negotiates its own height with the
parent page exactly once, right at mount time, via a JS call back to Streamlit. If it
mounts while its `st.expander` ancestor is still collapsed (the native `<details>`
element's content is `inert` when closed), that one-time negotiation measures a
0-height container and never re-fires - confirmed directly: `iframe.offsetHeight`
stayed `0` forever with a plain `agraph()` call inside the new expander from the
previous change, even well after the user opened it.

**Fix, two parts, both needed:**
1. `st.expander(..., key=expander_key, on_change="rerun")` - gives the expander a
   real, readable open/closed state in `st.session_state[expander_key]`, and makes
   *opening* it trigger an actual script rerun (the default `on_change="ignore"`
   only toggles CSS client-side, with no way for Python to react). On that rerun the
   agraph's own `key` is built to include `'open'` vs `'closed'`, so streamlit-agraph
   fully unmounts and remounts the moment the expander opens - and since this remount
   happens on a script pass where the expander is already open from the start (not
   toggled via pure CSS afterward), the new iframe negotiates its height against a
   real, visible container and sizes correctly. Verified via real DOM measurement in a
   loop after clicking: `offsetHeight` flickers to 0 mid-transition (~1-2s, the round
   trip to the server) then settles at the requested `420` and stays there - the graph
   genuinely appears with no further action needed most of the time.
2. **The requested "🎯 Center / fit graph" button** - a per-card `st.session_state`
   generation counter that also feeds into the agraph's `key`. Clicking it forces
   another full remount (same mechanism as #1), which is both the explicit manual
   recovery path the user asked for ("even it is missed by too much zoom" - vis-network
   has no Python-exposed `.fit()`/`.redraw()` call, so a full remount re-running its own
   `stabilization: {fit: true}` config is the only way to force a re-center from this
   side) and a reliable fallback for the rare case where #1's automatic fix doesn't
   settle in time.

`ui/graph_viz.py` already had a `keyed_agraph()` helper built for exactly this pattern
(from the earlier Graph Explorer stale-click fix) - reused rather than duplicated.
`render_answer_card()` gained a `card_key: str | None = None` parameter (auto-derived
from a hash of question+answer when the caller doesn't supply one, e.g. Billing's
single drilldown) since every widget key inside now needs to be unique per card - the
Ask tab's chat thread renders every turn's card on the same page simultaneously, so
`ui/tabs/ask.py` now passes an explicit `f"{session_id}_{idx}"` (history) /
`f"{session_id}_live"` (the in-progress turn) key.

**Real bug caught while writing the tests, not in the app code:** the first draft of
`tests/test_answer_card.py`'s mock `agent.db.run_cypher` return value used the wrong
row shape entirely (copied from a *different* function's column names -
`a_label`/`a`/`b_label`/`b` instead of `fetch_highlighted_subgraph`'s actual
`n_label`/`n_id`/`n_name`/`m_label`/`m_id`/`m_name`/`rel_type`/`r_props`). Since
`render_answer_card` wraps the fetch in a broad `except Exception` (correct production
behavior - Neo4j going down mid-render shouldn't crash the card), the resulting
`KeyError` was silently swallowed and every test still passed, just not testing what it
claimed to (no nodes ever actually rendered, so the button/graph code paths were never
exercised). Caught only because a *later* test asserting the "Center / fit" button's
presence failed for real. **How to apply:** a mock that raises inside code with a broad
except is a false-green test - when mocking a function whose return shape a Cypher
query defines, copy the exact column names from that query, don't assume a shape from
a similar-looking function elsewhere in the same file.

Also caught, separately, while writing the multi-card isolation test: `AppTest.
from_function()` execs only the target function's own source text in isolation - it
does NOT have access to the enclosing test module's global constants (`SAMPLE_STATE`
referenced inside a nested function failed with `NameError`, even though it worked
fine as a *default argument value*, which Python evaluates in the outer scope before
the function object is even created). Fix: pass such data through `kwargs=`, never
rely on closures.

10 new tests (`tests/test_answer_card.py`, 148 total): the two real DOM-level findings
above were verified live in a real browser first (a throwaway diagnostic script,
deleted afterward, never committed) before being encoded as regression tests.

## The sell side: sales records + a bigger, more complex graph — 2026-09-22

Direct request: "add more data into it with more nodes and make more complex and also
we need to track based on the company selling the manufacturing products to the buyers
and distrubuters as a sale data... Any doubts ask me for clarity." Genuinely ambiguous
on three real design forks (what "real-time" means, whether buyers/distributors extend
the existing `Dealer` label or need new node types, where this surfaces in the UI), so
asked before building anything - two rounds of `AskUserQuestion`, the second needed
because the first round's free-text answer ("Distributers are two types - those from
whom we buy... and another type someone who buys from us...") didn't map cleanly onto
either prepared option and needed a follow-up grounded in the actual current schema
(`Supplier`/`ThirdPartyVendor` already ARE the upstream "distributors" - no change
needed there; the real open question was just the downstream side).

**Decisions locked in:** "real-time" = realistic dated demo data, same static-but-
pinned-to-`DEMO_REFERENCE_DATE` approach as everything else (not a live-ticking
background job); downstream buyers = extend the existing `Dealer` label with a
`buyer_type` property (`dealer` vs `distributor`) rather than a new node type; surfaces
as a new **"📈 Sales"** tab mirroring Contracts & Billing's existing pattern.

**Schema additions:**
- Neo4j: `Dealer.buyer_type`, a 2nd `Facility` (Westgate Assembly Plant, Reno NV - runs
  the 3 new product lines' dedicated assembly, vs. the original `Riverside` plant), a
  4th `Warehouse` (Denver, CO), 2 more `Region`s (Pacific Northwest, Mountain), 7 more
  `Dealer`s (12 total, roughly half dealer/half distributor), 3 new `Product`s (glass/
  seating/sensor lines) with their own new `IntermediatePart`s, `RawMaterial`s
  (Glass, Foam categories), a 4th `ThirdPartyVendor`, and 2 more raw-material
  `Supplier`s + their `Contract`s. Net: 66 nodes/138 relationships -> **90 nodes/182
  relationships** - stayed readable at that size in Graph Explorer thanks to the
  earlier visualization polish (muted edges, tuned physics, no always-on edge labels) -
  checked directly via screenshot, not assumed.
- PostgreSQL: new `sales_records` table - the commercial/revenue counterpart to the
  existing `dealer_orders` (which only ever tracked what/how much was ordered and its
  fulfillment status), mirroring exactly how `invoices` is already the money-side
  counterpart to `purchase_orders` on the buy side. References `dealer_orders.order_id`
  rather than duplicating `dealer_id`/`product_id`/`quantity` - same normalization
  `invoices` already uses. `postgres/generate_seed_data.py` generates one
  `sales_records` row per `dealer_order` that actually shipped (a still-backordered
  order has nothing to invoice yet), with `unit_price` noise around a new
  `PRODUCT_BASE_PRICE` dict, `channel` derived from a new `DEALER_TYPE` dict (mirrors
  Neo4j's `buyer_type` - Postgres itself still has no name/type columns, so this exists
  purely to generate a realistic `channel` value), and `payment_status` following the
  same pending/paid/overdue logic `invoices` already uses.

**Real bug caught before it shipped:** the original `dealer_orders` date generation
(`order_date = month + timedelta(days=random.randint(1, 26))`, unchanged from the
original spec-era code) could already generate dates past `TODAY` for the current
month (e.g. `TODAY`=Sep 21 but day-of-month roll = 26) - harmless before, since nothing
rendered raw `dealer_orders` dates in a recency-sorted UI. The new Sales tab's "Recent
sales (last 90 days)" table, sorted by `sale_date DESC`, made this immediately visible
as literal future-dated sales relative to the demo's pinned "today" - caught by
actually looking at the live browser screenshot's dates, not just checking the query
ran without error. Fixed by capping the current month's day-offset at
`min(26, (TODAY - month).days)`, and separately capping `sale_date` itself at `TODAY`.
**How to apply:** a latent date-generation quirk that was invisible in aggregate
queries can become directly visible the moment a new UI feature sorts/displays raw
dates - re-check date bounds whenever adding a new "recent activity" view over
existing generated data, don't assume old generator code is still fine just because it
was fine for its original use case.

**Agent wiring:** new `sales_analysis` `query_type` (parallel to `contract_status` -
the sell-side mirror of the buy-side's existing type), added to
`decision_engine.VALID_QUERY_TYPES`/`_QUERY_TYPE_CRITERIA` (the latter is reused
directly as Jev's `Choice` criteria, so Jev picked it up with zero extra wiring),
`graph.POSTGRES_ONLY_TYPES`, and `CLASSIFY_SYSTEM`'s type list + a worked example.
`SQL_SYSTEM` got a new bullet explaining `sales_records` needs a join to
`dealer_orders` for dealer/product-level questions (same shape as the existing
`shipments` "trap" bullet). `NEO4J_SCHEMA` documents `Dealer.buyer_type` and a note
that "where are we selling" needs both stores. `POSTGRES_SCHEMA` needed no manual
update at all - it's read live from `schema.sql`, so the new table's comment (which
already explains the `dealer_orders` join and the cross-database region lookup) just
showed up in the prompt automatically.

**`ui/tabs/sales.py`** mirrors `ui/tabs/billing.py`'s established pattern closely:
cached fetch functions (`@st.cache_data(ttl=60)`), a metrics row, two charts (revenue
trend, revenue-by-region), a clickable table with the same
`.dvn-scroller.stDataFrameGlideDataEditor` row-click drilldown reusing
`run_question()`/`render_answer_card()`. "Where we're selling" is the one fetch that
genuinely can't be a single query: `sales_records`/`dealer_orders` have the revenue and
`dealer_id`, but only Neo4j's `Dealer -[:SERVICES]-> Region` has the region - joined by
`dealer_id` in Python inside the tab's own fetch functions, a direct cross-database-by-
ID join done at the UI layer (not through the LLM agent), same ID-matching convention
the whole app already relies on. No unit tests for these `st.cache_data`-wrapped fetch
functions, deliberately matching `billing.py`'s own precedent (zero tests for its
fetch functions either) - verified live in a real browser instead: metrics, both
charts (all 7 regions present), the sales table, and the full row-click ->
`run_question()` -> error-card drilldown flow (blocked only by the same pre-existing
LLM quota exhaustion affecting the rest of the app that day, not a code bug - confirmed
via the same graceful-degradation error card `billing.py`'s drilldown already uses).

Also added: `tests/test_graph_routing.py` (10 tests) for `agent/graph.py`'s routing
functions, which had zero test coverage before despite being pure state-in/string-out
logic with no LLM/DB dependency - added alongside `sales_analysis` to confirm it routes
identically to the other `POSTGRES_ONLY_TYPES`. Two small pre-existing staleness bugs
fixed while in this area: `ui/tabs/about.py`'s architecture diagram and tech-stack list
still said "Groq / OpenRouter / Anthropic" with no Gemini (missed when Gemini was added
earlier this session), and a test in `tests/test_ask_tab_chat_flow.py` hardcoded
`len(example_buttons) == 6`, broken by adding 2 sales example questions - now reads
`len(EXAMPLE_QUESTIONS)` dynamically.

Applied to the live Neo4j (AuraDB) and Postgres (Neon) instances directly via
psycopg2/neo4j-driver Python scripts (no `cypher-shell`/`psql` installed in this
sandbox) - first attempt at the Neo4j apply had a real scripting bug (naive `.split(";")`
on the whole file text tripped on a semicolon that appeared inside a comment's prose,
corrupting the next statement); fixed by stripping full `//` comment lines before
splitting, then re-ran cleanly (safe to re-run - `seed_data.cypher` is MERGE-throughout,
idempotent). Full `schema.sql` reapplication resets `chat_history`/`action_log` to
empty, same as every previous schema change this session - expected, not a regression.

158 tests total, all green.

## Real per-page URLs + shareable deep links — 2026-09-22

Direct request: "currently the web app is working with main url there is no sub paths,
parameters queries. It will improve the web interface." Genuinely two different scopes
bundled together (real per-page URLs vs. just query-string deep-linking on the existing
layout), with materially different amounts of work behind them, so asked via
`AskUserQuestion` before starting - user chose both.

**Why this needed real research, not just writing code:** `st.tabs()` exposes no way
to read or set which tab is "active" from Python at all - there's no callback, no
session_state key, nothing. Getting real URLs per tab therefore isn't a small addition,
it requires migrating off `st.tabs()` entirely to Streamlit's native page-routing
(`st.navigation`/`st.Page`). Before writing any of the real migration, built a
throwaway 2-page diagnostic app (deleted after, never committed) to verify three things
empirically rather than assume from general Streamlit knowledge - the same lesson from
the graph-trace-visibility bug earlier this session (verify the actual installed
version's behavior, don't guess):

1. **`position="top"`** on `st.navigation()` renders a horizontal icon+label bar
   visually very close to the old `st.tabs()` look - confirmed via screenshot before
   committing to the migration, not assumed from the API signature alone.
2. **A real, load-bearing platform quirk**: the *default* page's own declared
   `url_path` (e.g. visiting `/ask` directly) shows a harmless "Page not found -
   running the app's main page" toast on cold load, even though the content
   underneath still renders correctly. Only `/` (not the default page's own url_path)
   is genuinely its canonical URL - confirmed by testing cold-loads of `/`, a non-
   default page's url_path (clean, zero issue), and the default page's own url_path
   (toast every time) as three separate cases, not just one. Designed around it: the
   Ask page is simply not advertised as living at `/ask` anywhere in the app's own UI
   or docs, just at `/`.
3. **Query params do NOT survive clicking between pages** via Streamlit's own
   auto-generated nav links - confirmed by loading `/?session=abc-123` then clicking
   to Graph Explorer and checking the resulting URL had no `session` param at all.
   This directly shaped the deep-link design below (see the write-back pattern).

**Migration**: `app.py` replaced its `st.tabs()` block with
`st.navigation([...], position="top")` + `pg.run()`; each existing `render_*_tab()`
function became an `st.Page` target completely unchanged (they already took no
arguments, a direct fit for Streamlit's page-function contract). `render_sidebar()`
still runs unconditionally before `pg.run()`, exactly as before, so all of its global
state (Conversations, Model picker, Decision engine) keeps working identically
regardless of which page is active - confirmed session_state persists across page
switches within a browser session, same as it always did across tab switches.
`ui/theme.py`'s dead `st.tabs()`-era CSS (`button[data-baseweb="tab"]`,
`div[data-baseweb="tab-highlight"]`) replaced with the real confirmed testid
(`[data-testid="stTopNavLink"]`, found by walking the live DOM, not guessed).

**Deep links, three independent ones, same pattern each time** (peek `st.query_params`
once at `session_state` init - never on every rerun, so it can't fight a later
in-session action like "New chat" - then write the CURRENT value back every render so
the URL stays in sync and the write-back-survives-the-param-clearing-on-navigation
trick from finding #3 above kicks in):
- **`?q=<question>`** (`ui/tabs/ask.py`) - auto-submits that question, then `del`s it
  from `st.query_params` the moment it's consumed (not just read) so a refresh of the
  resulting URL never re-asks it.
- **`?session=<uuid>`** (`ui/sidebar.py`) - loads that specific past conversation via
  the existing `load_chat_session()` instead of starting fresh. Since `_render_
  conversations()` runs on every single page, this is also what makes the session
  param "persist across pages" despite Streamlit clearing query params on every
  navigation (finding #3) - it gets re-asserted before the user ever sees it missing.
- **`?node=<id>`** (`ui/tabs/graph_explorer.py`) - opens straight into that node's
  focus view via the existing `graph_focus_node` session_state mechanism. Correctly
  does NOT persist when navigating to a different page (no re-assertion happens
  outside Graph Explorer's own page function) - verified live that returning to Graph
  Explorer after visiting Sales/Ask restores the same focused node, because the
  underlying session_state itself was never cleared, only the URL momentarily was -
  the exact same "state survives navigation, URL self-heals" behavior as `?session=`,
  just page-scoped instead of global. Initially looked like a bug in a live test
  (clicking "← Full graph" didn't seem to clear `?node=` from the URL within 3
  seconds) - was actually just this app's real render cycle taking ~5s end to end
  (live Neo4j round trips), confirmed by polling every second instead of checking once.

5 new tests (`tests/test_deep_links.py`, 163 total) via AppTest, with two real gotchas
worth remembering for the next test in this style: (1) `AppTest`'s `query_params` is a
plain dict with **list-valued entries** (real query-string semantics: `{"q": ["value"]}`),
unlike the real `st.query_params` proxy's single-value convenience (`.get("q")` returns
`"value"` directly in the live app, `["value"]` in a test) - don't assume the two APIs
match exactly. (2) mocking the graph-explorer node-focus test by faking
`agent.db.run_cypher`'s return value (matching this project's usual pattern) doesn't
work here specifically, because `fetch_full_graph()` runs *before* the new deep-link
code and would need its own distinct query mocked too, or the whole thing short-
circuits on `if not all_nodes: return` before ever reaching the code under test -
simpler and more robust to patch `ui.tabs.graph_explorer.fetch_full_graph`/
`fetch_node_neighborhood` directly instead of trying to fake every Cypher string they
issue.

## Shipment timeline: click-to-detail dialog + richer data model — 2026-09-22

**User feedback:** the Contracts & Billing timeline chart needed a visual pass, and
hovering a point showed only a bare contract number - clicking one should open a
detail view (a dialog/panel, or a separate page) with real shipment specifics: what
was ordered, quantities, etc. Also asked, more broadly, to enrich the underlying node
properties with realistic data so the detail view actually helps a user decide and
act quickly, not just look nicer.

**Data model first, then UI** - a rich dialog is only as useful as the fields behind
it, so before touching `ui/tabs/billing.py` added the fields a procurement/logistics
user would actually want the moment they click into a shipment, none of which existed
anywhere in the schema before: `contracts` gained `account_manager` (who to actually
contact, one of eight named reps keyed by supplier) and `auto_renew` (does expiry need
a manual decision, or does it just renew - `random.random() < 0.65`); `shipments`
gained `carrier`, `freight_mode` (`truck`/`rail`/`ocean`/`air` - correlated with the
material's own category in the generator, bulk steel/aluminum skewing rail via `Union
Pacific Railroad`/`CSX Transportation` rather than assigned randomly, for realism),
`tracking_number`, and (only ever populated when `status='delayed'`) a `delay_reason`
drawn from a small realistic pool (winter storm, carrier capacity shortage, customs
hold, port congestion, mechanical breakdown, supplier production delay). Applied
`schema.sql` + regenerated `seed_data.sql` live to Neon Postgres, and confirmed via a
live `SELECT` (not just "the generator ran without error") that the new columns
actually populated with realistic-looking values before writing any UI code.

**The dialog**: `st.dialog("Shipment detail", width="large")`, triggered by
`st.plotly_chart(..., on_select="rerun", selection_mode="points")` reading the clicked
point's `customdata` (the `shipment_id`, threaded through via `px.timeline(...,
custom_data=["shipment_id"])`). Chose a modal over alternatives (append-below card,
separate page) because it most directly matches the user's own phrasing ("another
slide or left panel should open") and needed no restructuring. Deliberately left the
EXISTING contract-row-click LLM drilldown (`run_question` → `render_answer_card`)
untouched and added the timeline-click dialog as a second, complementary interaction -
one round-trips through the agent for a conversational "ask the AI" experience, the
other is pure SQL (`_fetch_shipment_detail()`, one query joining `shipments` →
`contracts` → `purchase_orders` → `supplier_performance` → `invoices`) so it opens
instantly regardless of the LLM-provider-quota exhaustion problem that recurred
throughout this session.

**`_recommended_action(detail, today)`** - a deterministic, non-LLM function that
turns the joined row into a single icon + message, checked in a deliberate priority
order so whatever's shown is always the single most urgent fact: active penalty
clause on a delayed shipment, beats a plain delay, beats an overdue invoice, beats a
near-term non-auto-renewing contract, beats a further-out one, beats "on track."
Genuinely pure (no DB/LLM calls) so it's unit tested directly - 9 new tests in
`tests/test_billing_dashboard.py` covering every branch and two priority-ordering
cases, `172` total.

**Two real bugs found live, not assumed:**
1. `fig.add_vline(x=config.DEMO_REFERENCE_DATE, ...)` raised `TypeError: unsupported
   operand type(s) for +: 'int' and 'datetime.date'` from inside Plotly's own
   `_process_multiple_axis_spanning_shapes`/annotation-positioning internals - a raw
   `datetime.date` breaks on a date-typed x-axis; passing
   `config.DEMO_REFERENCE_DATE.isoformat()` (a string) instead fixed it. Caught via a
   real browser test with the full traceback, not guessed from the Plotly docs.
2. The same CI-vs-local gotcha as the deep-links work earlier this session: verified
   the whole feature (schema change, seed regeneration, new tests) against the actual
   CI conditions by temporarily renaming `.env` and re-running the full suite (172
   passed, zero live credentials) before trusting it, not just a second green run
   with real credentials present.

Verified end-to-end against live data with a real browser: clicked a genuinely
delayed, penalty-bearing shipment on contract C1 and confirmed the dialog correctly
surfaced the top-priority "penalty clause applies - confirm the adjustment with Sarah
Chen" message, alongside the full shipment (material, quantity, carrier, tracking
number, delay reason) and contract/supplier panel (value, terms, account manager,
auto-renew, supplier on-time rate, related invoice status) - screenshot confirmed the
visual layout (clean two-column dialog, color-coded timeline legend, dashed "Today"
reference line) matches the text content.

## Exact-match answer cache, and About/Architecture renamed to Architecture — 2026-09-22

**User's question, then a hard constraint:** asked how frequently-asked questions
could be cached to cut LLM cost. First proposal was a semantic cache (embed the
question via the fastembed/pgvector infra already built for `supplier_notes`,
threshold on cosine similarity) - user's response ruled that out flatly: *"If there
is a chance that we give wrong information then we don't need to do it."* A semantic
match can conflate two different questions that embed close together (e.g. "price of
RM1" vs "price of RM2") and return a confidently wrong cached answer, which is an
unacceptable failure mode for this app regardless of the cost savings. **How to
apply: this user's correctness bar for this app is absolute, not a tunable threshold
- when a technique's failure mode is "occasionally confidently wrong" rather than
"occasionally slow/expensive," it's disqualified outright, not just deprioritized.**

**The safe version implemented instead: exact-match only.** New `query_cache`
Postgres table (`cache_key` a sha256 hex digest of the normalized - lowercased,
whitespace-collapsed, never meaning-altered - question text, `question`, `state_json`,
`created_at`). `agent/db.py` gained `_cache_key`/`get_cached_answer`/`cache_answer`/
`invalidate_query_cache`. Wired into the one shared entry point both the Ask tab and
the Billing drill-down already call, `ui/agent_runner.py`'s `run_question()`: a cache
lookup happens before the graph runs at all, and a successful answer is cached
afterward - both steps skipped entirely whenever `conversation_history` is non-empty,
since the exact same question text can mean something different depending on what
came before it (a follow-up like "what about its backup supplier?" is deliberately
never cached or served from cache, matching the existing reasoning for why the
Billing drill-down opts out of conversation context in the first place). Caching
itself is wrapped in try/except and must never block a real answer, same discipline as
`log_chat_turn`'s own best-effort persistence.

**Invalidation**: the whole cache is `TRUNCATE`d whenever a Neo4j graph import
actually changes something (`ui/graph_import_export.py`'s `import_graph_json()`,
alongside its existing `fetch_full_graph`/`export_graph_json`/`_graph_counts` cache
clears) - the one live write path that can make a previously-cached answer wrong (e.g.
a newly-added backup supplier). Clears the whole table rather than trying to guess
which cached questions a given import could have affected, since a silently-stale
cache entry is worse than no cache at all.

**Live-verified end to end**, not just unit tested: asked "Which raw materials have
only one supplier?" for real (23.5s, a genuine LLM round trip), then asked the exact
same question again - answered in 3.8s with the status label reading "Answer ready
(repeat question - served from cache, no LLM call)", confirming zero LLM calls on the
repeat. 12 new tests in `tests/test_query_cache.py` (184 total): cache-key
normalization, hit/miss/write/invalidate at the `agent/db.py` level (mocked
connections, same pattern as `test_chat_history.py`), and the `run_question()`
integration behavior driven through `AppTest` rather than called directly - `st.status`'s
`.update()` needs a real Streamlit script-run context to work at all outside `AppTest`,
the same reason `test_ask_tab_chat_flow.py` already uses that pattern rather than
calling `run_question()` bare (found by the first draft's direct-call tests failing
with `AttributeError: 'NoneType' object has no attribute 'update'`).

**Rename**: "About / Architecture" → "Architecture" per direct user request, done as a
real rename (not just a cosmetic title change) - `ui/tabs/about.py` →
`ui/tabs/architecture.py`, `render_about_tab` → `render_architecture_tab`, `app.py`'s
`st.Page(..., title="Architecture", url_path="architecture")` (was `url_path="about"`).
The Mermaid diagram itself was also updated, not just the tab label - a new green
`Asked verbatim before?` decision node sits before `classify_query`, branching straight
to the final answer on a cache hit, plus a dotted edge from `synthesize` into a new
`query_cache (Postgres)` store node - so the diagram a technical reviewer sees on this
page now actually reflects the real, current request flow instead of going stale the
moment this feature shipped.

Applied live to Neon Postgres via a direct script creating just the new `query_cache`
table (not the full `schema.sql` DROP/CREATE, which would have needlessly wiped the
demo's accumulated `chat_history`/`action_log` rows for no reason - same reasoning as
every previous incremental schema change this session). Test cache row from live
verification cleaned up afterward.
