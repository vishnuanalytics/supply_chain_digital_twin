"""Environment-driven configuration for the LangGraph agent."""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def _list(name: str, default: str) -> list[str]:
    return [p.strip() for p in os.getenv(name, default).split(",") if p.strip()]


LLM_PROVIDER_ORDER = _list("LLM_PROVIDER_ORDER", "groq,openrouter,anthropic,gemini")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

POSTGRES_URL = os.getenv("POSTGRES_URL", "")

# Optional (build step 8): TypeSafe AI's Jev fast/cheap typed-decision model, used as a
# swappable alternative to a full LLM call for classify_query's routing decision. The app
# never depends on this being set - decision_engine.py falls back to the normal Claude/Groq
# path on any error, including a missing key.
TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")

# Optional (build step 8): LangSmith tracing. LangSmith's own SDK reads LANGSMITH_TRACING/
# LANGSMITH_API_KEY/LANGSMITH_PROJECT directly from the environment (populated by load_dotenv()
# above), so no wiring is needed here beyond exposing the on/off state for the sidebar caption.
LANGSMITH_TRACING_ENABLED = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "supply-chain-digital-twin")

# The seed data was authored as of this date (see docs/data_reference.md). We
# pin "today" to this value everywhere the agent reasons about relative dates
# (contract expiry windows, "this month", etc.) so the demo stays internally
# consistent regardless of the wall-clock date it's actually run on.
DEMO_REFERENCE_DATE = date.fromisoformat(os.getenv("DEMO_REFERENCE_DATE", "2026-09-21"))
