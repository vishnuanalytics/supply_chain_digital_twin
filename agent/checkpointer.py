"""Postgres-backed LangGraph checkpointer (build step 8) so a paused human_approval_gate
interrupt survives an app restart, not just the current process's memory.
"""
from langgraph.checkpoint.postgres import PostgresSaver

from . import config

_checkpointer = None
_context_manager = None


def get_checkpointer() -> PostgresSaver:
    """Returns a process-wide PostgresSaver, running its one-time table setup
    (checkpoints/checkpoint_blobs/checkpoint_writes/checkpoint_migrations) the first
    time it's created. Kept open for the life of the process, like the Neo4j driver
    and Postgres connections elsewhere in agent/db.py."""
    global _checkpointer, _context_manager
    if _checkpointer is None:
        _context_manager = PostgresSaver.from_conn_string(config.POSTGRES_URL)
        _checkpointer = _context_manager.__enter__()
        _checkpointer.setup()
    return _checkpointer
