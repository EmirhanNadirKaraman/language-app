"""Add chat_sessions.language column (Stage 3 — second-language plan)

Revision ID: 031
Revises: 030
Create Date: 2026-05-21

Pre-Stage-3 `chat_sessions` carried no language column. Guided sessions
derived language from the target item's catalog row at every message
turn (a JOIN against word_table / phrase_table). Free chat had nothing
to derive from and hardcoded 'de' in routers/chat.py.

Stage 3 introduces per-session language storage so:
  - free chat can run in the user's active target language;
  - guided chat avoids the per-message catalog JOIN for `language`;
  - the LLM system prompt + hint generator pick the right tutor voice;
  - chat_service.match_learning_words is called with the correct
    language for both free and guided message flows.

Column is nullable on purpose — legacy rows (pre-031) stay NULL and
the application reads them as DEFAULT_LANGUAGE ('de') so existing
German sessions in the wild keep working byte-for-byte. New rows
created by the post-Stage-3 routes always get a non-NULL value.

No FK to language_table because legacy NULL rows would violate it; the
application layer is the source of truth for valid codes and the
catalog join already validates language indirectly via the target item.
"""
from alembic import op


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_sessions
          ADD COLUMN IF NOT EXISTS language TEXT NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS language")
