"""Add review tracking columns to reading_selections

Adds simple spaced-repetition scheduling directly on reading_selections so
that custom learning units can be reviewed and progressed without wiring into
the srs_cards integer-ID system (which is incompatible with UUID PKs).

  review_count   — number of consecutive "Got it" responses; drives the
                   interval schedule [1,2,4,7,14,30] days
  next_review_at — when the selection is next due; NULL means newly saved
                   (never reviewed) — treated as immediately due

Revision ID: 010
Revises: 009
Create Date: 2026-03-22
"""
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE reading_selections
            ADD COLUMN review_count   INT         NOT NULL DEFAULT 0,
            ADD COLUMN next_review_at TIMESTAMPTZ
    """)
    # Partial index: only index rows that are still in the learning queue.
    # Used by get_due_selections() to avoid scanning mastered rows.
    op.execute("""
        CREATE INDEX ON reading_selections (user_id, next_review_at)
        WHERE status = 'learning'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE reading_selections
            DROP COLUMN IF EXISTS next_review_at,
            DROP COLUMN IF EXISTS review_count
    """)
