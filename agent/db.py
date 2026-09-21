"""Thin, read-only data access layer over Neo4j and PostgreSQL.

The agent generates Cypher/SQL from an LLM, so every query passes through
`_assert_read_only` first — this is a Q&A agent over a seeded demo dataset and
must never let a hallucinated or prompt-injected query mutate it.
"""
import re

import psycopg2
import psycopg2.extras
from neo4j import GraphDatabase

from . import config

_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|REMOVE|SET|DROP|DETACH|INSERT|UPDATE|ALTER|TRUNCATE|GRANT|REVOKE|CALL\s+apoc\.)\b",
    re.IGNORECASE,
)


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
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]


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
