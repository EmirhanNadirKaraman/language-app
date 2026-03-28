"""Drop processed_channel table — superseded by channel table

Revision ID: 017
Revises: 016
Create Date: 2026-03-28
"""
from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS processed_channel")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS processed_channel (
            channel_id   TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL
        )
    """)
