"""Drop video.youtube_channel_id_old

Phase 4 — cleanup. Run this after the new code is deployed and verified.
The youtube_channel_id is fully derivable via JOIN channel ON channel.id = video.channel_id.

Revision ID: 022
Revises: 021
Create Date: 2026-03-28
"""
from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE video DROP COLUMN IF EXISTS youtube_channel_id_old")


def downgrade() -> None:
    raise NotImplementedError(
        "Cannot restore youtube_channel_id_old after drop. Restore from backup if needed."
    )
