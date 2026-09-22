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
