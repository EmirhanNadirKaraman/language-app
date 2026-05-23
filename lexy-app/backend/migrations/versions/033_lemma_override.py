"""Lemma override table — fix bad spaCy lemmas without bigger models (#39 slice 1)

Revision ID: 033
Revises: 032
Create Date: 2026-05-24

The Spanish phrase extractor (#36) builds canonical phrases from spaCy lemmas
(e.g. reflexive canonical = verb_lemma + "se"). spaCy's Spanish lemmatizer
hard-codes wrong lemmas for some verbs — `ducha`→`duchaber`, `ducho`→`duchir`
— and this is identical across es_core_news_sm / _md / _lg (verified
2026-05-24), so bumping the model size does NOT fix it. The deterministic fix
is an override table the extractor consults before trusting `token.lemma_`.

v1 (this slice) keys on (language, observed_lemma) → corrected_lemma — the
lemmatizer always produces the same wrong lemma regardless of POS/context, so
a context-free map is sufficient and easy to reason about. The `surface_form`
and `pos` columns are reserved (nullable, unused in v1) so a later slice can
add context-sensitive overrides without another migration.

User flagging / candidate-promotion (design items 3-5) is slice 2 — this table
only holds *promoted* overrides; `source` records how each entry got here.
"""
from alembic import op


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lemma_override (
            id              SERIAL PRIMARY KEY,
            language        TEXT NOT NULL,
            observed_lemma  TEXT NOT NULL,
            corrected_lemma TEXT NOT NULL,
            surface_form    TEXT,          -- reserved (slice 2: context-sensitive)
            pos             TEXT,          -- reserved (slice 2)
            source          TEXT NOT NULL DEFAULT 'manual'
                            CHECK (source IN ('manual','llm','admin','user_flag_reviewed')),
            status          TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','inactive')),
            confidence      REAL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # One context-free correction per (language, observed_lemma). The partial
    # predicate leaves room for slice-2 context-sensitive rows (surface_form /
    # pos non-null) to coexist without colliding.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_lemma_override_lang_observed
            ON lemma_override (language, observed_lemma)
            WHERE surface_form IS NULL AND pos IS NULL
        """
    )
    # Lookup index for the loader (language + active).
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_lemma_override_lang_status
            ON lemma_override (language, status)
        """
    )
    # Seed the known Spanish lemmatizer errors so the table is useful on
    # `alembic upgrade head` without waiting for slice 2's promotion flow.
    op.execute(
        """
        INSERT INTO lemma_override (language, observed_lemma, corrected_lemma, source)
        VALUES ('es', 'duchaber', 'duchar', 'manual'),
               ('es', 'duchir',   'duchar', 'manual')
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lemma_override")
