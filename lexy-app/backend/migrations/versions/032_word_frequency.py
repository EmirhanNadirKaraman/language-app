"""Precomputed word_table.frequency for fast autocomplete (TODO #38, route B)

Revision ID: 032
Revises: 031
Create Date: 2026-05-23

The SearchBar autocomplete (/api/suggest) used to query only the German
phrase_blueprint table and ignored language entirely — empty for Spanish
(TODO #38). The fix surfaces frequency-ranked word suggestions per
language. Computing COUNT(word_to_sentence) on every keystroke works but
costs ~280ms of GROUP BY aggregation; this migration precomputes the
count into a column so suggest is a single indexed prefix lookup.

What this does:
  - Adds word_table.frequency INTEGER NOT NULL DEFAULT 0 — number of
    sentences the word appears in (proxy for corpus frequency).
  - Backfills it from the current word_to_sentence counts so existing
    corpus (German + the freshly-ingested Spanish) is immediately
    usable without a scraper re-run.
  - Adds a functional prefix index on (language, lower(word)) so the
    autocomplete query
        WHERE language = $1 AND lower(word) LIKE lower($2) || '%'
    is index-assisted.

Maintenance: the scraper recomputes frequency at the end of each run
(see subtitle-scraper/pipeline.py:recompute_word_frequencies). The
column can drift between runs (new sentences not yet counted) but only
ever undercounts recent words slightly — acceptable for autocomplete
ranking.
"""
from alembic import op


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE word_table ADD COLUMN IF NOT EXISTS frequency INTEGER NOT NULL DEFAULT 0"
    )
    # Backfill from existing word_to_sentence links.
    op.execute(
        """
        UPDATE word_table wt
           SET frequency = sub.c
          FROM (
              SELECT word_id, COUNT(*) AS c
                FROM word_to_sentence
               GROUP BY word_id
          ) sub
         WHERE wt.word_id = sub.word_id
           AND wt.frequency <> sub.c
        """
    )
    # Prefix-autocomplete index: language + case-insensitive word prefix.
    # text_pattern_ops makes `lower(word) LIKE 'x%'` index-usable.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_word_table_lang_lower_word
            ON word_table (language, lower(word) text_pattern_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_word_table_lang_lower_word")
    op.execute("ALTER TABLE word_table DROP COLUMN IF EXISTS frequency")
