"""Restructure channel/video tables to use surrogate integer PK

Phase 3 of 3 — renames columns, swaps the primary key, rewires the FK.

  channel:
    channel_id TEXT PK  →  youtube_channel_id TEXT UNIQUE NOT NULL
    id SERIAL           →  id INTEGER PK

  video:
    channel_id TEXT FK  →  youtube_channel_id_old TEXT  (kept for safety window)
    channel_id_new INT  →  channel_id INTEGER FK → channel.id

Run migration 022 after the new code is deployed and verified to drop
video.youtube_channel_id_old.

Revision ID: 021
Revises: 020
Create Date: 2026-03-28
"""
from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Drop old FK from video.channel_id → channel.channel_id ────────────
    op.execute("ALTER TABLE video DROP CONSTRAINT IF EXISTS fk_video_channel")

    # ── 2. Drop old PK on channel.channel_id ─────────────────────────────────
    op.execute("ALTER TABLE channel DROP CONSTRAINT channel_pkey")

    # ── 3. Rename channel.channel_id → channel.youtube_channel_id ────────────
    op.execute("ALTER TABLE channel RENAME COLUMN channel_id TO youtube_channel_id")
    op.execute("ALTER TABLE channel ALTER COLUMN youtube_channel_id SET NOT NULL")
    op.execute("""
        ALTER TABLE channel
            ADD CONSTRAINT channel_youtube_channel_id_key UNIQUE (youtube_channel_id)
    """)

    # ── 4. Promote channel.id to primary key ─────────────────────────────────
    op.execute("ALTER TABLE channel ADD CONSTRAINT channel_pkey PRIMARY KEY (id)")

    # ── 5. On video: rename old TEXT column, promote backfilled INT column ────
    op.execute("ALTER TABLE video RENAME COLUMN channel_id TO youtube_channel_id_old")
    op.execute("ALTER TABLE video RENAME COLUMN channel_id_new TO channel_id")

    # ── 6. Add FK and index on the new integer column ─────────────────────────
    op.execute("""
        ALTER TABLE video
            ADD CONSTRAINT fk_video_channel
            FOREIGN KEY (channel_id) REFERENCES channel (id)
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_video_channel_id ON video (channel_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_video_channel_id")
    op.execute("ALTER TABLE video DROP CONSTRAINT IF EXISTS fk_video_channel")
    op.execute("ALTER TABLE video RENAME COLUMN channel_id TO channel_id_new")
    op.execute("ALTER TABLE video RENAME COLUMN youtube_channel_id_old TO channel_id")
    op.execute("ALTER TABLE channel DROP CONSTRAINT IF EXISTS channel_pkey")
    op.execute("ALTER TABLE channel DROP CONSTRAINT IF EXISTS channel_youtube_channel_id_key")
    op.execute("ALTER TABLE channel RENAME COLUMN youtube_channel_id TO channel_id")
    op.execute("ALTER TABLE channel ADD CONSTRAINT channel_pkey PRIMARY KEY (channel_id)")
    op.execute("""
        ALTER TABLE video
            ADD CONSTRAINT fk_video_channel
            FOREIGN KEY (channel_id) REFERENCES channel (channel_id)
    """)
