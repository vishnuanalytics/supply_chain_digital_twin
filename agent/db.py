"""Thin, read-only data access layer over Neo4j and PostgreSQL.

The agent generates Cypher/SQL from an LLM, so every query passes through
`_assert_read_only` first — this is a Q&A agent over a seeded demo dataset and
must never let a hallucinated or prompt-injected query mutate it.
"""
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
