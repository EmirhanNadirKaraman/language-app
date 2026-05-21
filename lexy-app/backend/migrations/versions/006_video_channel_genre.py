"""Add channel_id, channel_name, genre columns to video table

Revision ID: 006
Revises: 005
Create Date: 2026-03-21
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE video ADD COLUMN IF NOT EXISTS channel_id   TEXT")
    op.execute("ALTER TABLE video ADD COLUMN IF NOT EXISTS channel_name TEXT")
    op.execute("ALTER TABLE video ADD COLUMN IF NOT EXISTS genre        TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_video_channel_id ON video (channel_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_video_genre      ON video (genre)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_video_genre")
    op.execute("DROP INDEX IF EXISTS idx_video_channel_id")
    op.execute("ALTER TABLE video DROP COLUMN IF EXISTS genre")
    op.execute("ALTER TABLE video DROP COLUMN IF EXISTS channel_name")
    op.execute("ALTER TABLE video DROP COLUMN IF EXISTS channel_id")
