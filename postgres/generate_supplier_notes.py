#!/usr/bin/env python3
"""Generates postgres/supplier_notes_seed.sql — free-text audit/quality/risk notes per
supplier/vendor, with embeddings computed locally via fastembed (ONNX runtime, model
sentence-transformers/all-MiniLM-L6-v2 - same model agent/semantic_search.py embeds
queries with, so the two are always comparable; no LLM API call, no quota) so semantic
search works without needing to re-embed anything at query time beyond the user's own
question.

Separate from generate_seed_data.py/seed_data.sql on purpose: this whole feature is an
optional build-step-8 extension (needs pgvector, which not every Postgres instance
has), so it stays out of the core seed pipeline everything else depends on.

Re-run this script (`python3 postgres/generate_supplier_notes.py`) whenever the notes
below change; do not hand-edit supplier_notes_seed.sql.
"""
from datetime import date

from fastembed import TextEmbedding

OUT_PATH = "postgres/supplier_notes_seed.sql"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# (supplier_id, note_type, note_text, noted_date) - grounded in the real supplier/vendor
# names and ids from neo4j/seed_data.cypher. Deliberately differentiated content (some
# suppliers clean, some with real findings) so a semantic search actually has something
# meaningful to distinguish between, not just paraphrases of the same sentence.
NOTES = [
    ("S1", "quality", "Great Lakes Steel Co is ISO 9001:2015 certified with a strong "
     "quality track record. A minor OSHA citation for machine guarding was issued in "
     "early 2025 and fully remediated within the required 30-day window.", date(2025, 6, 10)),
    ("S1", "risk", "Great Lakes Steel Co carries an A credit rating and stable financial "
     "outlook. No supply continuity concerns on file.", date(2026, 1, 15)),

    ("S2", "sustainability", "Titan Aluminum Works sources over 60% recycled aluminum "
     "and passed its third-party sustainability audit with no major findings in 2026.", date(2026, 3, 1)),
    ("S2", "quality", "Titan Aluminum Works has had zero quality-related returns in the "
     "past 18 months. Not yet ISO 14001 certified, but has an active application in progress.", date(2026, 2, 20)),

    ("S3", "compliance", "Continental Rubber Industries was found non-compliant with "
     "REACH chemical-substance reporting requirements during a 2025 audit. A corrective "
     "action plan was submitted and verified complete as of Q1 2026.", date(2026, 2, 5)),
    ("S3", "risk", "Continental Rubber Industries flagged as medium risk pending "
     "follow-up verification of the REACH corrective action plan's long-term compliance.", date(2026, 2, 5)),

    ("S4", "risk", "Copperline Metals Inc holds an AA credit rating, the strongest of "
     "any raw-material supplier in the program, with no financial stability concerns.", date(2026, 1, 10)),
    ("S4", "quality", "Copperline Metals Inc has no quality nonconformances on file. "
     "Certified to ISO 9001 and IATF 16949.", date(2025, 11, 12)),

    ("S5", "quality", "PolyForm Plastics Ltd is ISO 14001 certified for environmental "
     "management. Minor shipment delays were noted in Q2 2026 due to a resin shortage, "
     "since resolved.", date(2026, 6, 1)),
    ("S5", "sustainability", "PolyForm Plastics Ltd has committed to a 20% reduction in "
     "manufacturing waste by 2027 as part of its sustainability roadmap.", date(2026, 4, 18)),

    ("S6", "risk", "Diversified Metals & Materials Inc is a backup-only supplier with "
     "limited audit history so far. A full certification review is scheduled once its "
     "order volume increases beyond backup-only status.", date(2026, 1, 5)),

    ("V1", "quality", "Precision Electronics Corp is IATF 16949 certified with an "
     "excellent on-time delivery record and no open compliance flags.", date(2026, 3, 22)),
    ("V1", "risk", "Precision Electronics Corp shows strong financial stability and no "
     "supply risk indicators.", date(2026, 3, 22)),

    ("V2", "compliance", "Midwest Bearing & Motion Co issued a voluntary product recall "
     "in late 2024 for a bearing lot with a heat-treatment defect. The recall was fully "
     "resolved and the affected process step now has enhanced in-line quality monitoring.", date(2024, 11, 30)),
    ("V2", "risk", "Midwest Bearing & Motion Co remains under enhanced quality "
     "monitoring following its 2024 recall, with no further incidents reported since.", date(2026, 1, 20)),

    ("V3", "compliance", "National Harness & Assembly Inc is SA8000 certified for social "
     "accountability, with a strong labor-practices audit score and no findings.", date(2026, 2, 14)),
    ("V3", "quality", "National Harness & Assembly Inc has maintained a 100% on-time "
     "delivery rate over the past four consecutive quarters.", date(2026, 5, 1)),
]


def _sql_escape(text: str) -> str:
    return text.replace("'", "''")


def main() -> None:
    print(f"Loading local embedding model ({MODEL_NAME}, via fastembed/ONNX, cached after first run)...")
    model = TextEmbedding(model_name=MODEL_NAME)

    lines = [
        "-- Generated by postgres/generate_supplier_notes.py - do not hand-edit.",
        f"-- Embeddings computed locally via fastembed ({MODEL_NAME}, 384 dims).",
        "TRUNCATE supplier_notes RESTART IDENTITY;",
        "",
    ]
    texts = [note[2] for note in NOTES]
    embeddings = list(model.embed(texts))

    for (supplier_id, note_type, note_text, noted_date), embedding in zip(NOTES, embeddings):
        vector_literal = "[" + ",".join(f"{x:.6f}" for x in embedding) + "]"
        lines.append(
            "INSERT INTO supplier_notes (supplier_id, note_type, note_text, noted_date, embedding) "
            f"VALUES ('{supplier_id}', '{note_type}', '{_sql_escape(note_text)}', "
            f"'{noted_date.isoformat()}', '{vector_literal}');"
        )

    with open(OUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {len(NOTES)} notes with embeddings to {OUT_PATH}")


if __name__ == "__main__":
    main()
