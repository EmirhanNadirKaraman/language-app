"""Create content_request table for user-submitted channel/video requests

Revision ID: 018
Revises: 017
Create Date: 2026-03-28
"""
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE content_request (
            request_id   SERIAL      PRIMARY KEY,
            user_id      UUID        REFERENCES users(user_id) ON DELETE SET NULL,
            request_type TEXT        NOT NULL CHECK (request_type IN ('channel', 'video')),
            content_id   TEXT        NOT NULL,
            status       TEXT        NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'done', 'failed')),
            error        TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (request_type, content_id)
        )
    """)
    op.execute("CREATE INDEX idx_content_request_status ON content_request (status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_content_request_status")
    op.execute("DROP TABLE IF EXISTS content_request")
