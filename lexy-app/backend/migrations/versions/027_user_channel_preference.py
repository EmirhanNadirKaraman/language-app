"""Move followed/liked/disliked channel prefs out of users.settings JSONB

Revision ID: 027
Revises: 026
Create Date: 2026-05-20

Creates a single relational table for the three channel preference kinds and
backfills from existing JSONB arrays. Source of truth flips to the new table;
the JSONB keys are intentionally NOT removed yet — they remain in
`users.settings` for one release as a fallback, and are simply ignored on
read going forward. A future migration can DELETE the keys once we're sure
no consumer still reads them.

`channel_names` (the display-name cache) STAYS in JSONB by design — it's not
a preference, just a lookup table, and there's no benefit to normalising it.
"""
from alembic import op


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Table ─────────────────────────────────────────────────────────────
    # PK = (user_id, youtube_channel_id, preference_kind) so the same user can
    # both follow AND like a channel (followed + liked are NOT mutually
    # exclusive per the spec; only liked vs disliked are). The service layer
    # owns the like/dislike mutual exclusion.
    #
    # No FK to channel(youtube_channel_id) — users may have channels in their
    # JSONB blob that pre-date the channel table or were never seeded
    # (especially during backfill). The relational model gains query speed
    # and audit ergonomics either way; we can layer the FK in a later
    # migration once a sweep confirms every stored value is referenceable.
    op.execute("""
        CREATE TABLE user_channel_preference (
            user_id            UUID         NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            youtube_channel_id TEXT         NOT NULL,
            preference_kind    TEXT         NOT NULL
                CHECK (preference_kind IN ('followed', 'liked', 'disliked')),
            created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, youtube_channel_id, preference_kind)
        )
    """)
    op.execute("""
        CREATE INDEX ix_user_channel_pref_user_kind
            ON user_channel_preference (user_id, preference_kind)
    """)

    # ── 2. Backfill from users.settings JSONB ────────────────────────────────
    # For each user, expand the three arrays into rows.
    #
    # `jsonb_array_elements_text` strips quotes and yields TEXT; `ON CONFLICT
    # DO NOTHING` is defensive against duplicate IDs inside a single user's
    # JSONB array (shouldn't happen, but the apply_channel_action helper used
    # sorted() on a set so duplicates were already deduped — harmless).
    for kind, json_key in [
        ("followed", "followed_channels"),
        ("liked",    "liked_channels"),
        ("disliked", "disliked_channels"),
    ]:
        op.execute(f"""
            INSERT INTO user_channel_preference (user_id, youtube_channel_id, preference_kind)
            SELECT u.user_id,
                   elem.value::text  AS youtube_channel_id,
                   '{kind}'          AS preference_kind
              FROM users u,
                   jsonb_array_elements_text(
                       COALESCE(u.settings -> '{json_key}', '[]'::jsonb)
                   ) AS elem(value)
             WHERE u.settings ? '{json_key}'
            ON CONFLICT DO NOTHING
        """)


def downgrade() -> None:
    # No JSONB restore — we never deleted those keys in the upgrade. The
    # service layer just stops reading from them. Reverting the migration is
    # safe: it drops the relational rows and the JSONB blob is still around.
    op.execute("DROP INDEX IF EXISTS ix_user_channel_pref_user_kind")
    op.execute("DROP TABLE IF EXISTS user_channel_preference")
