"""Add phrase_table for first-class phrase tracking

Revision ID: 005
Revises: 004
Create Date: 2026-03-20
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE phrase_table (
            phrase_id    SERIAL      PRIMARY KEY,
            canonical    TEXT        NOT NULL,
            surface_form TEXT        NOT NULL,
            phrase_type  TEXT        NOT NULL DEFAULT 'verb_pattern',
            language     TEXT        NOT NULL DEFAULT 'de',
            UNIQUE (canonical, language)
        )
    """)
    op.execute("CREATE INDEX ON phrase_table (language)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS phrase_table")
