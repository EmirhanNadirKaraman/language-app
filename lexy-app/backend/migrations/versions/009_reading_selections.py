"""Add reading_selections table for interactive reading custom learning units

Revision ID: 009
Revises: 008
Create Date: 2026-03-21
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE reading_selections (
            selection_id  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            doc_id        UUID        NOT NULL REFERENCES book_documents(doc_id) ON DELETE CASCADE,

            -- Normalized form: lowercase surface text, tokens in document order
            canonical     TEXT        NOT NULL,

            -- Exact surface form as selected (space-separated tokens in order)
            surface_text  TEXT        NOT NULL,

            -- The full text of the block containing the first selected token (context container)
            sentence_text TEXT        NOT NULL,

            -- Positional anchors: [{block_id, token_index, surface}]
            anchors       JSONB       NOT NULL DEFAULT '[]',

            -- Optional user note attached to this unit
            note          TEXT,

            -- Lightweight status for review tracking
            status        TEXT        NOT NULL DEFAULT 'learning',

            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON reading_selections (user_id, doc_id)")
    op.execute("CREATE INDEX ON reading_selections (user_id, canonical)")
    # GIN index for fast JSONB anchor lookups (filter by block_id)
    op.execute("CREATE INDEX ON reading_selections USING GIN (anchors)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reading_selections")
