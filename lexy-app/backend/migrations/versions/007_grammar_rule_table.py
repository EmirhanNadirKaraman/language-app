"""Add grammar_rule_table for first-class grammar rule support

Revision ID: 007
Revises: 006
Create Date: 2026-03-21
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE grammar_rule_table (
            rule_id                 SERIAL      PRIMARY KEY,
            slug                    TEXT        NOT NULL,
            title                   TEXT        NOT NULL,
            rule_type               TEXT        NOT NULL,
            short_explanation       TEXT        NOT NULL,
            language                TEXT        NOT NULL DEFAULT 'de',
            pattern_hint            TEXT,
            applicable_phrase_types TEXT[]      NOT NULL DEFAULT '{}',
            UNIQUE (slug, language)
        )
    """)
    op.execute("CREATE INDEX ON grammar_rule_table (language)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS grammar_rule_table")
