"""Add llm_cache table for prompt-keyed response caching

Revision ID: 003
Revises: 002
Create Date: 2026-03-20
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_cache (
            cache_key   TEXT        PRIMARY KEY,
            prompt_key  TEXT        NOT NULL,
            model       TEXT        NOT NULL,
            response    JSONB       NOT NULL,
            hit_count   INTEGER     NOT NULL DEFAULT 0,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_hit_at TIMESTAMPTZ,
            expires_at  TIMESTAMPTZ          -- NULL = permanent
        )
    """)
    op.execute("CREATE INDEX ON llm_cache (prompt_key)")
    op.execute("CREATE INDEX ON llm_cache (expires_at) WHERE expires_at IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_cache")
