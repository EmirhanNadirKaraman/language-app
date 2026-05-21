"""Initial user tables

Revision ID: 001
Revises:
Create Date: 2025-03-19
"""
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gen_random_uuid() is built-in on PostgreSQL 13+.
    # pgcrypto also provides it for older versions.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("""
        CREATE TABLE users (
            user_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            email         TEXT        UNIQUE NOT NULL,
            password_hash TEXT        NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            settings      JSONB       NOT NULL DEFAULT '{}'
        )
    """)

    op.execute("""
        CREATE TABLE user_word_knowledge (
            id                   SERIAL      PRIMARY KEY,
            user_id              UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            item_id              INTEGER     NOT NULL,
            item_type            TEXT        NOT NULL,  -- 'word' | 'phrase' | 'grammar_rule'
            status               TEXT        NOT NULL DEFAULT 'unknown',  -- 'unknown' | 'learning' | 'known'
            passive_level        INTEGER     NOT NULL DEFAULT 0,
            active_level         INTEGER     NOT NULL DEFAULT 0,
            times_seen           INTEGER     NOT NULL DEFAULT 0,
            times_used_correctly INTEGER     NOT NULL DEFAULT 0,
            last_seen            TIMESTAMPTZ,
            notes                TEXT,
            UNIQUE (user_id, item_id, item_type)
        )
    """)

    op.execute("""
        CREATE TABLE srs_cards (
            card_id       SERIAL      PRIMARY KEY,
            user_id       UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            item_id       INTEGER     NOT NULL,
            item_type     TEXT        NOT NULL,  -- 'word' | 'phrase' | 'grammar_rule'
            direction     TEXT        NOT NULL,  -- 'passive' | 'active'
            due_date      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            interval_days FLOAT       NOT NULL DEFAULT 1.0,
            ease_factor   FLOAT       NOT NULL DEFAULT 2.5,
            repetitions   INTEGER     NOT NULL DEFAULT 0,
            last_review   TIMESTAMPTZ,
            UNIQUE (user_id, item_id, item_type, direction)
        )
    """)

    op.execute("""
        CREATE TABLE word_lists (
            list_id     SERIAL      PRIMARY KEY,
            user_id     UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            name        TEXT        NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE word_list_items (
            id        SERIAL      PRIMARY KEY,
            list_id   INTEGER     NOT NULL REFERENCES word_lists(list_id) ON DELETE CASCADE,
            item_id   INTEGER     NOT NULL,
            item_type TEXT        NOT NULL,  -- 'word' | 'phrase' | 'grammar_rule'
            added_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (list_id, item_id, item_type)
        )
    """)

    op.execute("""
        CREATE TABLE chat_sessions (
            session_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            session_type     TEXT        NOT NULL,  -- 'free' | 'guided'
            target_item_id   INTEGER,
            target_item_type TEXT,
            started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE chat_messages (
            message_id        SERIAL      PRIMARY KEY,
            session_id        UUID        NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
            role              TEXT        NOT NULL,  -- 'user' | 'assistant'
            content           TEXT        NOT NULL,
            language_detected TEXT,                  -- 'de' | 'en' | 'mixed'
            corrections       JSONB,
            word_matches      JSONB,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Indexes on the hot query paths
    op.execute("CREATE INDEX ON user_word_knowledge (user_id)")
    op.execute("CREATE INDEX ON srs_cards (user_id, due_date)")
    op.execute("CREATE INDEX ON chat_messages (session_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_messages")
    op.execute("DROP TABLE IF EXISTS chat_sessions")
    op.execute("DROP TABLE IF EXISTS word_list_items")
    op.execute("DROP TABLE IF EXISTS word_lists")
    op.execute("DROP TABLE IF EXISTS srs_cards")
    op.execute("DROP TABLE IF EXISTS user_word_knowledge")
    op.execute("DROP TABLE IF EXISTS users")
