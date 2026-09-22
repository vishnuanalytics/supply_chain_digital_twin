"""Semantic search over free-text supplier/vendor notes (build step 8 extension) - the
one genuinely unstructured content in an otherwise fully-structured schema, so it's the
one place a keyword/exact-match Cypher or SQL query is the wrong tool: "any quality or
compliance concerns with our suppliers?" has no exact column to filter on the way
"which contracts expire in 90 days" does.

Embeddings are generated entirely locally via fastembed (ONNX runtime, model
sentence-transformers/all-MiniLM-L6-v2, 384 dims) - no LLM API call, no quota, works
even when every configured LLM provider is rate-limited (only classify_query's routing
decision needs an LLM at all). fastembed specifically over the more common
sentence-transformers[torch] package: the same model served through ONNX runtime pulls
in tens of MB instead of PyTorch's 700MB+ (or several GB with CUDA extras pulled in by
default) - a real difference for a Streamlit Cloud free-tier deployment's build size and
memory budget, not just a local nicety. See postgres/generate_supplier_notes.py for how
the seed data's own embeddings were generated the same way, so a query embedding and the
stored embeddings are always comparable.
"""
from . import db

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None


def _get_model():
    """Lazy singleton - loading the model takes a few seconds, so it's paid once per
    process, not once per question."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=_MODEL_NAME)
    return _model


def _embed(text: str) -> str:
    """Returns a pgvector literal string ("[0.1,0.2,...]") rather than a raw list -
    passing a Python list as a query parameter gets adapted to a Postgres ARRAY, not a
    vector, so the comparison is done with an explicit `%s::vector` cast in the SQL
    instead of relying on psycopg2's type adapters to guess correctly."""
    embedding = next(iter(_get_model().embed([text])))
    return "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"


def search_supplier_notes(query: str, k: int = 5) -> list[dict]:
    """Returns the k most semantically similar supplier/vendor notes to `query`, each
    with a similarity score (1 - cosine distance, so higher = more similar, 0..1)."""
    vector_literal = _embed(query)
    return db.run_sql(
        "SELECT supplier_id, note_type, note_text, noted_date, "
        "1 - (embedding <=> %s::vector) AS similarity "
        "FROM supplier_notes ORDER BY embedding <=> %s::vector LIMIT %s",
        (vector_literal, vector_literal, k),
    )
