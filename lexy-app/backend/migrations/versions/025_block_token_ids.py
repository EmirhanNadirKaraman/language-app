"""Add tokens JSONB column to book_blocks and backfill with stable UUIDs

Revision ID: 025
Revises: 024
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa
import json
import uuid
import regex as _re

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

_SPLIT = _re.compile(r'(\p{L}[\p{L}\p{M}\'-]*)')
_WORD  = _re.compile(r'^\p{L}')

def _tokenize(text: str) -> list[dict]:
    """Tokenize text, producing [{token_id: UUID, text: str, is_word: bool}]."""
    return [
        {"token_id": str(uuid.uuid4()), "text": p, "is_word": bool(_WORD.match(p))}
        for p in _SPLIT.split(text or "")
        if p
    ]


def upgrade() -> None:
    # Step 1: Add the column, nullable first
    op.execute("ALTER TABLE book_blocks ADD COLUMN tokens JSONB")

    # Step 2: Backfill using Python tokenizer
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("""
            SELECT block_id,
                   COALESCE(user_text_override,
                     CASE WHEN correction_status = 'approved' AND corrected_text IS NOT NULL
                          THEN corrected_text ELSE clean_text END,
                     ocr_text, '') AS display_text
              FROM book_blocks
        """)
    ).fetchall()

    for block_id, display_text in rows:
        tokens = _tokenize(display_text or "")
        conn.execute(
            sa.text(
                "UPDATE book_blocks SET tokens = :tokens WHERE block_id = :block_id"
            ),
            {"tokens": json.dumps(tokens), "block_id": block_id},
        )

    # Step 3: Set NOT NULL and default
    op.execute("""
        ALTER TABLE book_blocks
        ALTER COLUMN tokens SET NOT NULL,
        ALTER COLUMN tokens SET DEFAULT '[]'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE book_blocks DROP COLUMN tokens")
