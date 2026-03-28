"""Create notification table for pipeline → frontend push events

Revision ID: 023
Revises: 022
Create Date: 2026-03-28
"""
from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE notification (
            notification_id SERIAL      PRIMARY KEY,
            user_id         UUID        REFERENCES users(user_id) ON DELETE CASCADE,
            type            TEXT        NOT NULL,
            payload         JSONB       NOT NULL DEFAULT '{}',
            seen            BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_notification_user_unseen
            ON notification (user_id, seen)
            WHERE seen = FALSE
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notification_user_unseen")
    op.execute("DROP TABLE IF EXISTS notification")
