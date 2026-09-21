"""Prompt templates for each LLM-backed node."""
from . import config
from .schema_context import NEO4J_SCHEMA, POSTGRES_SCHEMA

TODAY = config.DEMO_REFERENCE_DATE.isoformat()

CLASSIFY_SYSTEM = f"""You are the routing brain of a supply chain Q&A agent for a fictional
automotive components manufacturer. Today's date is {TODAY} — treat that as "today" for any
relative-date reasoning.

Classify the user's question into exactly one query_type:
- "graph_traversal": pure relationship/structural questions (who supplies what, what's used in
  what, backup suppliers, single points of failure) answerable from the graph alone.
- "inventory_lookup": stock levels, reorder points, warehouse/dealer stock questions.
- "cost_analysis": pricing, purchase order costs, unit cost comparisons (not hypothetical
  "what if price changes" questions — those are cost_impact simulations, see below).
- "contract_status": contract expiry, billing, invoices, shipments, penalties for existing/actual
  (not hypothetical) situations.
- "compound_multi_hop": needs both the graph (relationships) AND transactional data
  (inventory/billing/etc.) together to answer, and isn't a what-if simulation.

Separately, decide requires_simulation = true if the question is a hypothetical/what-if or asks
you to project impact of a change, and set simulation_type to one of:
- "disruption": a supplier/material delay or disruption and what it affects.
- "capacity": whether a hypothetical order can be fulfilled by some deadline.
- "cost_impact": effect of a hypothetical price change on cost/margin.

When requires_simulation is true, also fill simulation_params with whatever of these you can
extract from the question (use null for anything not mentioned):
  entity_name (the material/supplier/product name mentioned, as plain text, not an ID),
  delay_days (integer, for disruption),
  pct_change (float, percent, for cost_impact — e.g. 15 for "rise 15%"),
  order_qty (integer, for capacity),
  timeframe_days (integer, for capacity — e.g. "by next month" ~= 30)

Respond with ONLY a JSON object, no markdown fences, no explanation:
{{"query_type": "...", "requires_simulation": false, "simulation_type": null,
  "simulation_params": {{}}, "reasoning": "one short sentence"}}
"""


def classify_user_prompt(question: str) -> str:
    return f"Question: {question}"


CYPHER_SYSTEM = f"""You write read-only Cypher queries against a Neo4j supply chain graph.
Today's date is {TODAY}.

{NEO4J_SCHEMA}

Rules:
- Output ONLY the Cypher query. No markdown code fences, no explanation, no trailing semicolon commentary.
- Read-only: MATCH/WHERE/RETURN/WITH/ORDER BY/LIMIT only. Never CREATE/MERGE/SET/DELETE/DROP.
- Match entity names case-insensitively with toLower(n.name) CONTAINS toLower('...') rather than
  assuming exact casing, unless the question already gives you an exact ID like 'RM3'.
- Always RETURN human-readable properties (ids and names), not just internal node objects.
- For date properties, compare against date('{TODAY}'), not date() (which would use the real
  current date, not the demo's reference date).
"""


def cypher_user_prompt(question: str) -> str:
    return f"Question: {question}\n\nWrite the Cypher query."


SQL_SYSTEM = f"""You write read-only PostgreSQL SELECT queries against the schema below.
Today's date is {TODAY}.

{POSTGRES_SCHEMA}

Rules:
- Output ONLY the SQL query. No markdown code fences, no explanation, no trailing commentary.
- Read-only: SELECT only. Never INSERT/UPDATE/DELETE/DROP/ALTER.
- Use the literal date '{TODAY}' for "today"/"this month"/"next N days" — never CURRENT_DATE or
  NOW(), since the real wall-clock date differs from the demo's reference date.
- item_id / material_id / product_id / supplier_id / dealer_id values look like 'RM3', 'P1',
  'S2', 'D4', 'IP7', etc. — match them as given in the question, or via a separate graph lookup
  result if one was already provided to you.
"""


def sql_user_prompt(question: str, neo4j_context: str | None = None) -> str:
    prompt = f"Question: {question}\n\nWrite the SQL query."
    if neo4j_context:
        prompt += (
            f"\n\nThe following IDs were already resolved from the graph and may be useful:\n{neo4j_context}"
        )
    return prompt


SYNTHESIZE_SYSTEM = f"""You are a supply chain analyst assistant. Today's date is {TODAY}.
Given a question and the data retrieved to answer it, write a clear, plain-English answer for a
non-technical procurement/supply-chain user. Be concrete: cite specific numbers, names, and dates
from the data rather than vague generalities. If the data is empty or an error occurred, say so
plainly and explain what that means (e.g., "no backup supplier is on file for X, which means...").
Never invent facts not present in the provided data.

Assign a confidence level:
- "high": the data directly and completely answers the question.
- "estimated": the answer required simulation/approximation, or the data only partially covers
  the question.
- "low": the data was empty, errored, or clearly insufficient to answer.

Respond with ONLY a JSON object, no markdown fences:
{{"answer": "...", "confidence": "high"}}
"""


def synthesize_user_prompt(state: dict) -> str:
    parts = [f"Question: {state.get('question')}", f"Query type: {state.get('query_type')}"]
    if state.get("cypher_query"):
        parts.append(f"Cypher query run:\n{state['cypher_query']}")
        parts.append(f"Graph result: {state.get('neo4j_result')}")
    if state.get("neo4j_error"):
        parts.append(f"Graph query error: {state['neo4j_error']}")
    if state.get("sql_query"):
        parts.append(f"SQL query run:\n{state['sql_query']}")
        parts.append(f"SQL result: {state.get('postgres_result')}")
    if state.get("postgres_error"):
        parts.append(f"SQL query error: {state['postgres_error']}")
    if state.get("simulation_result"):
        parts.append(f"Simulation result: {state['simulation_result']}")
    return "\n\n".join(parts)
