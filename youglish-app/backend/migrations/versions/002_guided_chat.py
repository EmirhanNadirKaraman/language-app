"""Add evaluation column to chat_messages for guided chat structured output

Revision ID: 002
Revises: 001
Create Date: 2025-03-19
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS evaluation JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS evaluation")
