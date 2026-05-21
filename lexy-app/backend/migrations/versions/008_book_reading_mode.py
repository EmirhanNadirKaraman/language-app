"""Add book reading mode tables: book_documents, book_pages, book_blocks

Revision ID: 008
Revises: 007
Create Date: 2026-03-21
"""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE book_documents (
            doc_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       UUID        NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            title         TEXT        NOT NULL,
            filename      TEXT        NOT NULL,
            file_path     TEXT        NOT NULL,
            total_pages   INTEGER,
            language      TEXT        NOT NULL DEFAULT 'de',
            source_type   TEXT        NOT NULL DEFAULT 'unknown',
            status        TEXT        NOT NULL DEFAULT 'pending',
            error_message TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON book_documents (user_id)")
    op.execute("CREATE INDEX ON book_documents (status)")

    op.execute("""
        CREATE TABLE book_pages (
            page_id      SERIAL      PRIMARY KEY,
            doc_id       UUID        NOT NULL REFERENCES book_documents(doc_id) ON DELETE CASCADE,
            page_number  INTEGER     NOT NULL,
            image_path   TEXT,
            width_pt     FLOAT,
            height_pt    FLOAT,
            is_scanned   BOOLEAN     NOT NULL DEFAULT FALSE,
            UNIQUE (doc_id, page_number)
        )
    """)
    op.execute("CREATE INDEX ON book_pages (doc_id)")

    op.execute("""
        CREATE TABLE book_blocks (
            block_id          SERIAL      PRIMARY KEY,
            page_id           INTEGER     NOT NULL REFERENCES book_pages(page_id) ON DELETE CASCADE,
            doc_id            UUID        NOT NULL,
            block_index       INTEGER     NOT NULL,
            block_type        TEXT        NOT NULL DEFAULT 'text',
            bbox_x0           FLOAT,
            bbox_y0           FLOAT,
            bbox_x1           FLOAT,
            bbox_y1           FLOAT,
            ocr_text          TEXT,
            clean_text        TEXT,
            corrected_text    TEXT,
            correction_status TEXT        NOT NULL DEFAULT 'none',
            ocr_confidence    FLOAT,
            is_header_footer  BOOLEAN     NOT NULL DEFAULT FALSE,
            user_text_override TEXT
        )
    """)
    op.execute("CREATE INDEX ON book_blocks (page_id)")
    op.execute("CREATE INDEX ON book_blocks (doc_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS book_blocks")
    op.execute("DROP TABLE IF EXISTS book_pages")
    op.execute("DROP TABLE IF EXISTS book_documents")
