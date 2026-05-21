"""Add sentence_count to book_pages

Revision ID: 012
Revises: 011
Create Date: 2026-03-24
"""
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE book_pages ADD COLUMN IF NOT EXISTS sentence_count INT")


def downgrade() -> None:
    op.execute("ALTER TABLE book_pages DROP COLUMN IF EXISTS sentence_count")
