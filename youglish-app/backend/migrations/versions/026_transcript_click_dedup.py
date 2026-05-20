"""Add sentence_id + per-day dedup index for transcript-click events

Revision ID: 026
Revises: 025
Create Date: 2026-05-20

Adds:
  - word_usage_events.sentence_id  INTEGER NULL  (no FK — sentence cleanup must not cascade)
  - word_usage_events.event_day    DATE GENERATED STORED   (UTC calendar day)
  - UNIQUE INDEX uq_word_usage_events_transcript_dedup on
        (user_id, item_id, item_type, sentence_id, event_day)
    WHERE context = 'transcript' AND sentence_id IS NOT NULL.

Purpose:
Lets the transcript-click endpoint dedup repeated clicks on the same word in
the same sentence within a day via INSERT ... ON CONFLICT DO NOTHING.
Other contexts (free_chat, guided_chat, status_change, srs_review) are NOT
deduped — those events are meaningful per-occurrence.
"""
from alembic import op


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE word_usage_events
        ADD COLUMN sentence_id INTEGER NULL
    """)
    op.execute("""
        ALTER TABLE word_usage_events
        ADD COLUMN event_day DATE
        GENERATED ALWAYS AS ((created_at AT TIME ZONE 'UTC')::date) STORED
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_word_usage_events_transcript_dedup
            ON word_usage_events (user_id, item_id, item_type, sentence_id, event_day)
            WHERE context = 'transcript' AND sentence_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_word_usage_events_transcript_dedup")
    op.execute("ALTER TABLE word_usage_events DROP COLUMN IF EXISTS event_day")
    op.execute("ALTER TABLE word_usage_events DROP COLUMN IF EXISTS sentence_id")
