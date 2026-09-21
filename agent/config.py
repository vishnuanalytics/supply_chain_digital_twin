"""Environment-driven configuration for the LangGraph agent."""
import os
from datetime import date

from dotenv import load_dotenv

load_dotenv()


def _list(name: str, default: str) -> list[str]:
    return [p.strip() for p in os.getenv(name, default).split(",") if p.strip()]


LLM_PROVIDER_ORDER = _list("LLM_PROVIDER_ORDER", "groq,openrouter,anthropic")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

POSTGRES_URL = os.getenv("POSTGRES_URL", "")

# The seed data was authored as of this date (see docs/data_reference.md). We
# pin "today" to this value everywhere the agent reasons about relative dates
# (contract expiry windows, "this month", etc.) so the demo stays internally
# consistent regardless of the wall-clock date it's actually run on.
DEMO_REFERENCE_DATE = date.fromisoformat(os.getenv("DEMO_REFERENCE_DATE", "2026-09-21"))
