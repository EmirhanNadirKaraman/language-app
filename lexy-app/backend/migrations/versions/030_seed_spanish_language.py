"""Idempotently seed Spanish into language_table (Stage 0 — second-language plan)

Revision ID: 030
Revises: 029
Create Date: 2026-05-21

Stage 0 of the second-language plan: ensure `language_table` contains the
'es' row so downstream FK-linked rows (channel.language, sentence.language,
video.language, phrase_table.language, grammar_rule_table.language,
word_table.language) can reference it.

Live audit on 2026-05-21 showed the prod DB already had all 12 expected
language rows (`de en es fr it ja ko pl pt ru sv tr`). This migration is
defensive: it lands the intent in version control so a fresh-DB setup
(or any env that bypassed the original out-of-band creation) gets the
row too. The INSERT is idempotent.

Other column values copied from the existing 'fr/it/pt' rows (Romance
sibling defaults — they share the same regex and flags):

  iso_code              = 'spa'   (ISO 639-2/T 3-letter)
  regex                 = '^[A-Z](.*)[!?.]$'   (sentence-shape gate)
  is_learnable          = true
  is_interface_language = false   (UI is English-only for now)

No phrase-extraction or runtime change lands here — that's Stage 1+.
"""
from alembic import op


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO language_table
            (language, iso_code, regex, is_learnable, is_interface_language)
        VALUES
            ('es', 'spa', '^[A-Z](.*)[!?.]$', TRUE, FALSE)
        ON CONFLICT (language) DO NOTHING
        """
    )


def downgrade() -> None:
    # Defensive: leave the row in place on downgrade. Other rows (channels,
    # videos, sentences) may reference it via FK and the cascade is set to
    # ON DELETE CASCADE on some of those — a blind DELETE here could remove
    # legitimate user data.
    #
    # If a developer truly wants to remove 'es' (e.g. shrinking back to a
    # German-only deployment), do it manually after auditing the FK fanout.
    pass
