"""Thin, read-only data access layer over Neo4j and PostgreSQL.

The agent generates Cypher/SQL from an LLM, so every query passes through
`_assert_read_only` first — this is a Q&A agent over a seeded demo dataset and
must never let a hallucinated or prompt-injected query mutate it.
"""
import hashlib
import json
import re

import neo4j.time
import psycopg2
import psycopg2.extras
from neo4j import GraphDatabase

from . import config

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|REMOVE|SET|DROP|DETACH|INSERT|UPDATE|ALTER|TRUNCATE|GRANT|REVOKE|CALL\s+apoc\.)\b",
    re.IGNORECASE,
)

# A few Neo4j nodes (e.g. Contract) have real date-typed properties (see
# neo4j/seed_data.cypher's `date(row.start)`), which the driver returns as its own
# neo4j.time.Date/DateTime/Time - not a Python datetime.date/datetime/time subclass.
# langgraph's checkpointer serializer (needed for human_approval_gate's interrupt/resume
# state, build step 8) doesn't know these types and raises "Type is not msgpack
# serializable", so every row returned from Neo4j gets normalized to native Python
# temporal types here, once, rather than leaving every caller to remember to convert.
_NEO4J_TEMPORAL_TYPES = (neo4j.time.Date, neo4j.time.DateTime, neo4j.time.Time)


def _to_native(value):
    if isinstance(value, _NEO4J_TEMPORAL_TYPES):
        return value.to_native()
    if isinstance(value, dict):
        return {k: _to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    return value


class QuerySafetyError(Exception):
    pass


def _assert_read_only(query: str) -> None:
    if _WRITE_KEYWORDS.search(query):
        raise QuerySafetyError(f"Refusing to run a non-read-only query: {query!r}")


_neo4j_driver = None


def get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    return _neo4j_driver


def run_cypher(query: str, params: dict | None = None) -> list[dict]:
    _assert_read_only(query)
    driver = get_neo4j_driver()
    with driver.session(database=config.NEO4J_DATABASE) as session:
        result = session.run(query, params or {})
        return [_to_native(record.data()) for record in result]


def get_postgres_connection():
    return psycopg2.connect(config.POSTGRES_URL)


def run_sql(query: str, params: tuple | None = None) -> list[dict]:
    _assert_read_only(query)
    conn = get_postgres_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def log_action(action_type: str, description: str, status: str, note: str = "") -> None:
    """The one deliberate write path in this app (everything else is read-only LLM-
    generated Cypher/SQL, checked by _assert_read_only). Used only by
    agent/nodes/approval.py after a human has approved or rejected a recommendation -
    never called with LLM-generated input."""
    conn = get_postgres_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO action_log (action_type, description, status, note) VALUES (%s, %s, %s, %s)",
                (action_type, description, status, note),
            )
        conn.commit()
    finally:
        conn.close()


def log_chat_turn(session_id: str, question: str, state: dict) -> None:
    """Persists one answered question so conversation history survives a page refresh
    or server restart - see chat_history's own comment in postgres/schema.sql for why
    the whole state dict is stored, not just question/answer text. `state` goes through
    json.dumps(default=str) since it can contain Decimal/date values from Postgres rows
    that aren't natively JSON-serializable; Postgres then auto-casts that JSON text to
    the column's jsonb type on insert (confirmed directly, not assumed), and psycopg2
    hands it back as a plain Python dict on read with no extra deserialization step."""
    conn = get_postgres_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (session_id, question, state_json) VALUES (%s, %s, %s)",
                (session_id, question, json.dumps(state, default=str)),
            )
        conn.commit()
    finally:
        conn.close()


def list_chat_sessions(limit: int = 20) -> list[dict]:
    """One row per session, most recently active first - session_id, its first
    question (as a display label), how many turns it has, and when it was last active.
    Used to populate a "past conversations" browser without pulling every session's
    full (potentially large) state_json just to list them."""
    return run_sql(
        """
        SELECT session_id,
               (array_agg(question ORDER BY created_at ASC))[1] AS first_question,
               count(*) AS turn_count,
               max(created_at) AS last_activity
        FROM chat_history
        GROUP BY session_id
        ORDER BY last_activity DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_chat_session(session_id: str) -> list[dict]:
    """Every turn in one session, oldest first, each with its full renderable state."""
    return run_sql(
        "SELECT question, state_json, created_at FROM chat_history "
        "WHERE session_id = %s ORDER BY created_at ASC",
        (session_id,),
    )


def _cache_key(question: str) -> str:
    """Normalizes case/whitespace only (never meaning) - this is an EXACT-match cache
    key, not a semantic one. See query_cache's own comment in postgres/schema.sql for
    why fuzzy matching is deliberately not used here."""
    normalized = " ".join(question.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_answer(question: str) -> dict | None:
    """Returns a previously-cached answer's full state dict only if this exact question
    (case/whitespace-insensitive) has been asked before, or None on a cache miss."""
    rows = run_sql("SELECT state_json FROM query_cache WHERE cache_key = %s", (_cache_key(question),))
    return rows[0]["state_json"] if rows else None


def cache_answer(question: str, state: dict) -> None:
    """Stores a successfully-answered question's full state for exact-match reuse.
    `state` is JSON-serialized the same way log_chat_turn does (default=str, for
    Decimal/date values from Postgres rows) - ON CONFLICT so re-caching the same
    question just refreshes it rather than erroring."""
    conn = get_postgres_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_cache (cache_key, question, state_json)
                VALUES (%s, %s, %s)
                ON CONFLICT (cache_key) DO UPDATE SET state_json = EXCLUDED.state_json, created_at = now()
                """,
                (_cache_key(question), question.strip(), json.dumps(state, default=str)),
            )
        conn.commit()
    finally:
        conn.close()


def invalidate_query_cache() -> None:
    """Clears the whole answer cache - called after the one live write path that can
    change what a cached answer should say (a Neo4j graph import, see
    ui/graph_import_export.py). A stale cache entry silently returning wrong data would
    be worse than no cache at all, so this clears everything rather than trying to
    guess which cached questions a given import could have affected."""
    conn = get_postgres_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE query_cache")
        conn.commit()
    finally:
        conn.close()


# Every Cypher string above this point is fixed application code, safe to write. From
# here down is the one place user-supplied *data* (an uploaded JSON file's node/edge
# properties, via ui/graph_import.py) reaches Neo4j - never routed through run_cypher's
# LLM-facing path, and never allowed to supply the label/relationship type text that
# ends up interpolated into a query (Cypher has no way to parameterize a label or
# relationship type - only a hardcoded allow-list checked before string-building the
# query is safe). Property *values* are always sent as parameters, never interpolated.
VALID_NODE_LABELS = {
    "Facility", "Warehouse", "Region", "Dealer", "Product", "IntermediatePart",
    "RawMaterial", "Supplier", "ThirdPartyVendor", "Contract",
}
# Must stay in lockstep with agent/prompts.py's CYPHER_SYSTEM closed list - that prompt
# tells the LLM these are the *only* relationship types that exist in the graph, so an
# import creating any other type would silently make that claim false.
VALID_REL_TYPES = {
    "SOURCED_FROM", "BACKUP_FOR", "USED_IN", "PURCHASED_FROM", "MANUFACTURED_AT",
    "STORED_IN", "SUPPLIES", "SERVICES", "HAS_CONTRACT", "PREVIOUSLY_CONTRACTED", "COVERS",
}


def id_property_for_label(label: str) -> str:
    """Every label keys its unique id as `id`, except Contract (`contract_id`, matching
    its own real schema constraint) - see neo4j/schema.cypher."""
    return "contract_id" if label == "Contract" else "id"


def upsert_node(label: str, properties: dict) -> str:
    """Creates a node if its id doesn't exist yet, or merges these properties into the
    existing one if it does - "add new data" should be forgiving of re-running the same
    import twice, not error out on a duplicate. Returns the node's id."""
    if label not in VALID_NODE_LABELS:
        raise ValueError(f"Unknown node label {label!r} - must be one of {sorted(VALID_NODE_LABELS)}")
    id_key = id_property_for_label(label)
    node_id = properties.get(id_key)
    if not node_id:
        raise ValueError(f"A {label} node needs a non-empty '{id_key}' property")

    driver = get_neo4j_driver()
    with driver.session(database=config.NEO4J_DATABASE) as session:
        session.run(
            f"MERGE (n:{label} {{{id_key}: $id_value}}) SET n += $properties",
            {"id_value": node_id, "properties": properties},
        )
    return str(node_id)


def upsert_edge(source_id: str, target_id: str, rel_type: str, properties: dict) -> None:
    """Both endpoints must already exist (either already in the graph, or created by an
    earlier node in the same import) - silently creating a bare placeholder node for a
    typo'd id would be far more confusing than a clear error."""
    if rel_type not in VALID_REL_TYPES:
        raise ValueError(f"Unknown relationship type {rel_type!r} - must be one of {sorted(VALID_REL_TYPES)}")

    driver = get_neo4j_driver()
    with driver.session(database=config.NEO4J_DATABASE) as session:
        result = session.run(
            f"""
            MATCH (a) WHERE coalesce(a.id, a.contract_id) = $source_id
            MATCH (b) WHERE coalesce(b.id, b.contract_id) = $target_id
            MERGE (a)-[r:{rel_type}]->(b)
            SET r += $properties
            RETURN a.id AS matched
            """,
            {"source_id": source_id, "target_id": target_id, "properties": properties},
        )
        if result.single() is None:
            raise ValueError(f"Couldn't find both '{source_id}' and '{target_id}' already in the graph")
