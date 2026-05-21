"""Add surrogate integer PK to channel, new integer FK column on video

Phase 1 of 3 — additive only, nothing breaks in this migration.
  - channel.id SERIAL is added and auto-filled for all existing rows
  - video.channel_id_new INTEGER (nullable) is added; backfilled in 020

Revision ID: 019
Revises: 018
Create Date: 2026-03-28
"""
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add serial id to channel — Postgres auto-populates all existing rows.
    op.execute("ALTER TABLE channel ADD COLUMN id SERIAL")

    # Add nullable integer column that will hold the backfilled FK.
    op.execute("ALTER TABLE video ADD COLUMN channel_id_new INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE video DROP COLUMN IF EXISTS channel_id_new")
    op.execute("ALTER TABLE channel DROP COLUMN IF EXISTS id")
