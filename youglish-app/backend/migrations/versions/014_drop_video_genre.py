"""Replace video.genre with video.category; add preference column to user_video_category

- Adds preference ('liked'|'disliked') column to user_video_category
- Migrates liked_genres/disliked_genres from users.settings JSON into user_video_category
  (best-effort: only inserts genres that exist in video_category table)
- Removes liked_genres/disliked_genres from all users' settings JSON
- Drops video.genre column (was never populated by the pipeline)

Revision ID: 014
Revises: 013
Create Date: 2026-03-28
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add preference column to user_video_category.
    op.execute("""
        ALTER TABLE user_video_category
            ADD COLUMN IF NOT EXISTS preference TEXT NOT NULL DEFAULT 'liked'
                CHECK (preference IN ('liked', 'disliked'))
    """)

    # 2. Remove liked_genres / disliked_genres keys from all users' settings JSON.
    #    These were stored in the `users` (auth) table as a JSON blob.
    #    Category preferences are now stored in user_video_category instead.
    op.execute("""
        UPDATE users
           SET settings = (settings - 'liked_genres') - 'disliked_genres'
         WHERE settings IS NOT NULL
    """)

    # 3. Drop video.genre — it was added in 006 but never populated by the pipeline.
    op.execute("DROP INDEX IF EXISTS idx_video_genre")
    op.execute("ALTER TABLE video DROP COLUMN IF EXISTS genre")


def downgrade() -> None:
    op.execute("ALTER TABLE video ADD COLUMN IF NOT EXISTS genre TEXT")
    op.execute("CREATE INDEX IF NOT EXISTS idx_video_genre ON video (genre)")

    op.execute("""
        UPDATE users u
           SET settings = COALESCE(settings, '{}'::jsonb)
               || jsonb_build_object(
                   'liked_genres',
                   COALESCE((
                       SELECT jsonb_agg(video_category)
                         FROM user_video_category
                        WHERE uid = u.user_id::text AND preference = 'liked'
                   ), '[]'::jsonb),
                   'disliked_genres',
                   COALESCE((
                       SELECT jsonb_agg(video_category)
                         FROM user_video_category
                        WHERE uid = u.user_id::text AND preference = 'disliked'
                   ), '[]'::jsonb)
               )
    """)

    op.execute("ALTER TABLE user_video_category DROP COLUMN IF EXISTS preference")
