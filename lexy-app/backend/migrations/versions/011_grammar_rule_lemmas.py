"""Add applicable_lemmas column to grammar_rule_table

Revision ID: 011
Revises: 010
Create Date: 2026-03-22
"""
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE grammar_rule_table
        ADD COLUMN IF NOT EXISTS applicable_lemmas TEXT[] NOT NULL DEFAULT '{}'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_grammar_rule_table_applicable_lemmas
        ON grammar_rule_table
        USING GIN (applicable_lemmas)
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_grammar_rule_table_applicable_lemmas
    """)
    op.execute("""
        ALTER TABLE grammar_rule_table
        DROP COLUMN IF EXISTS applicable_lemmas
    """)