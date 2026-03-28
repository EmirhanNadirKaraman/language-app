"""Backfill video.channel_id_new from channel.id

Phase 2 of 3 — sets the integer FK on every video that has a channel_id.
Aborts if any video with a non-NULL channel_id is left unmatched, so a
missing channel row is caught before the schema swap in 021.

Revision ID: 020
Revises: 019
Create Date: 2026-03-28
"""
import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Join on the current TEXT channel_id column (still named channel_id in
    # both tables at this point — rename happens in 021).
    op.execute("""
        UPDATE video v
           SET channel_id_new = ch.id
          FROM channel ch
         WHERE ch.channel_id = v.channel_id
           AND v.channel_id IS NOT NULL
    """)

    conn = op.get_bind()
    missing = conn.execute(sa.text("""
        SELECT COUNT(*)
          FROM video
         WHERE channel_id IS NOT NULL
           AND channel_id_new IS NULL
    """)).scalar()

    if missing:
        raise RuntimeError(
            f"Backfill incomplete: {missing} video row(s) have a channel_id "
            "with no matching channel row. Fix the channel table first."
        )


def downgrade() -> None:
    op.execute("UPDATE video SET channel_id_new = NULL")
