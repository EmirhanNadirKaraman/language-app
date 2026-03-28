"""Create channel table and wire video.channel_id as FK

- Creates channel(channel_id, channel_name, language, active)
- Seeds it from distinct channel_id/channel_name/language values already in video
- Adds FK from video.channel_id → channel.channel_id

Revision ID: 015
Revises: 014
Create Date: 2026-03-28
"""
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the channel table.
    #    language is nullable — channels imported from subscribed_channels.txt
    #    may not have a known language until their first video is processed.
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel (
            channel_id   TEXT PRIMARY KEY,
            channel_name TEXT NOT NULL DEFAULT '',
            language     TEXT REFERENCES language_table(language),
            active       BOOLEAN NOT NULL DEFAULT TRUE
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_language ON channel (language)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_active ON channel (active)
    """)

    # 2. Seed from existing video rows — take the most common channel_name per channel_id.
    op.execute("""
        INSERT INTO channel (channel_id, channel_name, language)
        SELECT DISTINCT ON (channel_id)
            channel_id,
            COALESCE(channel_name, ''),
            language
        FROM video
        WHERE channel_id IS NOT NULL
        ORDER BY channel_id, channel_name NULLS LAST
        ON CONFLICT (channel_id) DO NOTHING
    """)

    # 3. Add FK from video.channel_id → channel.channel_id.
    #    Nullable — videos that predate channel tracking have NULL channel_id.
    op.execute("""
        ALTER TABLE video
            ADD CONSTRAINT fk_video_channel
            FOREIGN KEY (channel_id) REFERENCES channel (channel_id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE video DROP CONSTRAINT IF EXISTS fk_video_channel")
    op.execute("DROP INDEX IF EXISTS idx_channel_active")
    op.execute("DROP INDEX IF EXISTS idx_channel_language")
    op.execute("DROP TABLE IF EXISTS channel")
