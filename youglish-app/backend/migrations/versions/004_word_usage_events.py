"""Add word_usage_events table for interaction tracking

Revision ID: 004
Revises: 003
Create Date: 2026-03-20
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

# Valid contexts:  'free_chat' | 'guided_chat' | 'status_change' | 'srs_review'
# Valid outcomes:  'seen' | 'used' | 'correct' | 'incorrect'


def upgrade() -> None:
    op.execute("""
        CREATE TABLE word_usage_events (
            event_id   BIGSERIAL   PRIMARY KEY,
            user_id    UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            item_id    INTEGER     NOT NULL,
            item_type  TEXT        NOT NULL,   -- 'word' | 'phrase' | 'grammar_rule'
            context    TEXT        NOT NULL,   -- 'free_chat' | 'guided_chat' | 'status_change' | 'srs_review'
            outcome    TEXT        NOT NULL,   -- 'seen' | 'used' | 'correct' | 'incorrect'
            metadata   JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # Primary analytics access patterns
    op.execute("CREATE INDEX ON word_usage_events (user_id, created_at DESC)")
    op.execute("CREATE INDEX ON word_usage_events (user_id, item_id, item_type)")
    op.execute("CREATE INDEX ON word_usage_events (user_id, context, outcome, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS word_usage_events")
