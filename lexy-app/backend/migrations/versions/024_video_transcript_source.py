"""Add transcript_source column to video table

Revision ID: 024
Revises: 023
Create Date: 2026-03-28
"""
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE video
        ADD COLUMN transcript_source TEXT NOT NULL DEFAULT 'auto'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE video DROP COLUMN transcript_source")
