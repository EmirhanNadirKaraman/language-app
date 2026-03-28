"""Drop video.channel_name — channel names now live in the channel table

Revision ID: 016
Revises: 015
Create Date: 2026-03-28
"""
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE video DROP COLUMN IF EXISTS channel_name")


def downgrade() -> None:
    op.execute("ALTER TABLE video ADD COLUMN IF NOT EXISTS channel_name TEXT")
    # Best-effort restore from channel table
    op.execute("""
        UPDATE video v
           SET channel_name = ch.channel_name
          FROM channel ch
         WHERE ch.channel_id = v.channel_id
    """)
