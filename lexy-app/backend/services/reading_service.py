"""
reading_service.py

Service layer for the interactive reading feature.

Responsibilities:
  - Bulk word-status lookup for a book page (for highlighting)
  - Save / list / update reading_selections (custom learning units)
"""
from __future__ import annotations

import json
import re

import asyncpg


async def get_word_statuses_for_page(
    pool: asyncpg.Pool,
    user_id: str,
    doc_id: str,
    page_number: int,
    language: str,
) -> dict[str, str]:
    """
    Return {word_lowercase: status} for all user-tagged words visible on a page.

    Strategy:
      1. Fetch display text for every non-ignored block on the page.
      2. Extract unique alphabetic word tokens (lowercase).
      3. Batch-join against word_table + user_word_knowledge to get statuses.

    Words not in word_table or without a knowledge row are absent from the result
    (the frontend treats absence as unknown).
    """
    rows = await pool.fetch(
        """
        SELECT b.clean_text, b.corrected_text, b.user_text_override, b.correction_status
          FROM book_blocks b
          JOIN book_pages  p ON p.page_id = b.page_id
         WHERE p.doc_id       = $1::uuid
           AND p.page_number  = $2
           AND b.block_type  != 'ignored'
         ORDER BY b.block_index
        """,
        doc_id, page_number,
    )

    all_words: set[str] = set()
    for r in rows:
        if r["user_text_override"] is not None:
            text = r["user_text_override"]
        elif r["correction_status"] == "approved" and r["corrected_text"]:
            text = r["corrected_text"]
        else:
            text = r["clean_text"] or ""

        for w in re.findall(r"[^\W\d_]+", text, re.UNICODE):
            all_words.add(w.lower())

    if not all_words:
        return {}

    words_list = list(all_words)
    status_rows = await pool.fetch(
        """
        SELECT LOWER(w.word) AS word_lc, uwk.status
          FROM word_table w
          JOIN user_word_knowledge uwk
               ON uwk.item_id   = w.word_id
              AND uwk.item_type = 'word'
              AND uwk.user_id   = $1::uuid
         WHERE LOWER(w.word) = ANY($2::text[])
           AND w.language    = $3
        """,
        user_id, words_list, language,
    )

    return {r["word_lc"]: r["status"] for r in status_rows}


async def save_selection(
    pool: asyncpg.Pool,
    user_id: str,
    doc_id: str,
    canonical: str,
    surface_text: str,
    sentence_text: str,
    anchors: list[dict],
    note: str | None,
) -> dict:
    """
    Persist a custom learning unit and return the saved row dict.

    anchors format: [{"block_id": int, "token_index": int, "surface": str}, ...]
    """
    row = await pool.fetchrow(
        """
        INSERT INTO reading_selections
            (user_id, doc_id, canonical, surface_text, sentence_text, anchors, note)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6::jsonb, $7)
        RETURNING selection_id, user_id, doc_id, canonical, surface_text,
                  sentence_text, anchors, note, status, created_at, updated_at
        """,
        user_id, doc_id, canonical, surface_text, sentence_text,
        json.dumps(anchors), note,
    )
    return dict(row)


async def list_selections_for_page(
    pool: asyncpg.Pool,
    user_id: str,
    doc_id: str,
    block_ids: list[int],
) -> list[dict]:
    """
    Return all saved selections that anchor to any of the given block_ids.
    Used to highlight already-saved tokens when rendering a page.
    """
    if not block_ids:
        return []

    rows = await pool.fetch(
        """
        SELECT selection_id, user_id, doc_id, canonical, surface_text,
               sentence_text, anchors, note, status, created_at, updated_at
          FROM reading_selections
         WHERE user_id = $1::uuid
           AND doc_id  = $2::uuid
           AND EXISTS (
               SELECT 1
                 FROM jsonb_array_elements(anchors) a
                WHERE (a->>'block_id')::int = ANY($3::int[])
           )
         ORDER BY created_at
        """,
        user_id, doc_id, block_ids,
    )
    return [dict(r) for r in rows]


async def list_all_selections(
    pool: asyncpg.Pool,
    user_id: str,
    doc_id: str,
) -> list[dict]:
    """Return all selections for a document (for the library/review view)."""
    rows = await pool.fetch(
        """
        SELECT selection_id, user_id, doc_id, canonical, surface_text,
               sentence_text, anchors, note, status, created_at, updated_at
          FROM reading_selections
         WHERE user_id = $1::uuid AND doc_id = $2::uuid
         ORDER BY created_at DESC
        """,
        user_id, doc_id,
    )
    return [dict(r) for r in rows]


async def update_selection(
    pool: asyncpg.Pool,
    selection_id: str,
    user_id: str,
    note: str | None = None,
    status: str | None = None,
) -> dict | None:
    """Partial update of note and/or status."""
    sets: list[str] = []
    params: list = [selection_id, user_id]

    if note is not None:
        params.append(note or None)
        sets.append(f"note = ${len(params)}")

    if status is not None:
        params.append(status)
        sets.append(f"status = ${len(params)}")

    if not sets:
        row = await pool.fetchrow(
            "SELECT * FROM reading_selections WHERE selection_id=$1::uuid AND user_id=$2::uuid",
            selection_id, user_id,
        )
        return dict(row) if row else None

    sets.append("updated_at = NOW()")
    query = f"""
        UPDATE reading_selections
           SET {', '.join(sets)}
         WHERE selection_id = $1::uuid AND user_id = $2::uuid
        RETURNING *
    """
    row = await pool.fetchrow(query, *params)
    return dict(row) if row else None


async def delete_selection(
    pool: asyncpg.Pool,
    selection_id: str,
    user_id: str,
) -> bool:
    """Delete a selection. Returns True if deleted, False if not found."""
    result = await pool.execute(
        "DELETE FROM reading_selections WHERE selection_id=$1::uuid AND user_id=$2::uuid",
        selection_id, user_id,
    )
    return result == "DELETE 1"


# ---------------------------------------------------------------------------
# Review scheduling
# ---------------------------------------------------------------------------

# Days to wait after each consecutive "got_it" response.
# Index = review_count before the event (0-based).
# Beyond index 5, the interval is capped at 30 days.
_REVIEW_INTERVALS_DAYS = [1, 2, 4, 7, 14, 30]


def _interval_days(review_count: int) -> int:
    if review_count < len(_REVIEW_INTERVALS_DAYS):
        return _REVIEW_INTERVALS_DAYS[review_count]
    return 30


async def record_review(
    pool: asyncpg.Pool,
    selection_id: str,
    user_id: str,
    outcome: str,  # 'got_it' | 'still_learning' | 'mastered'
) -> dict | None:
    """
    Update a selection after a review event.

    got_it:         increment review_count, set next_review_at per interval schedule
    still_learning: reset review_count to 0, set next_review_at = NOW() (due immediately)
    mastered:       set status = 'mastered', clear next_review_at (leaves rotation)
    """
    row = await pool.fetchrow(
        "SELECT review_count FROM reading_selections "
        "WHERE selection_id=$1::uuid AND user_id=$2::uuid",
        selection_id, user_id,
    )
    if not row:
        return None

    if outcome == "mastered":
        updated = await pool.fetchrow(
            """
            UPDATE reading_selections
               SET status        = 'mastered',
                   next_review_at = NULL,
                   updated_at    = NOW()
             WHERE selection_id = $1::uuid AND user_id = $2::uuid
            RETURNING *
            """,
            selection_id, user_id,
        )
    elif outcome == "got_it":
        new_count = row["review_count"] + 1
        days = _interval_days(row["review_count"])
        updated = await pool.fetchrow(
            """
            UPDATE reading_selections
               SET review_count   = $3,
                   next_review_at = NOW() + ($4 || ' days')::INTERVAL,
                   updated_at     = NOW()
             WHERE selection_id = $1::uuid AND user_id = $2::uuid
            RETURNING *
            """,
            selection_id, user_id, new_count, str(days),
        )
    else:  # still_learning — reset and bring back immediately
        updated = await pool.fetchrow(
            """
            UPDATE reading_selections
               SET review_count   = 0,
                   next_review_at = NOW(),
                   updated_at     = NOW()
             WHERE selection_id = $1::uuid AND user_id = $2::uuid
            RETURNING *
            """,
            selection_id, user_id,
        )

    return dict(updated) if updated else None


async def find_catalog_item(
    pool: asyncpg.Pool,
    doc_id: str,
    canonical: str,
) -> tuple[int, str] | None:
    """
    Look up a reading selection's canonical text in the word/phrase catalog.

    Returns (item_id, item_type) if a match is found in word_table or phrase_table
    for the document's language, or None if the canonical has no catalog entry
    (e.g. multi-word expressions not yet in phrase_table).

    Used to wire reading saves/reviews into the main progression system.
    """
    doc = await pool.fetchrow(
        "SELECT language FROM book_documents WHERE doc_id = $1::uuid",
        doc_id,
    )
    if not doc:
        return None

    language = doc["language"]
    canonical_lc = canonical.lower()

    # Single-word case: match against word_table
    row = await pool.fetchrow(
        "SELECT word_id FROM word_table WHERE LOWER(word) = $1 AND language = $2",
        canonical_lc, language,
    )
    if row:
        return (row["word_id"], "word")

    # Multi-word case: match against phrase_table surface form
    row = await pool.fetchrow(
        "SELECT phrase_id FROM phrase_table WHERE LOWER(surface_form) = $1 AND language = $2",
        canonical_lc, language,
    )
    if row:
        return (row["phrase_id"], "phrase")

    return None


async def get_due_selections(
    pool: asyncpg.Pool,
    user_id: str,
    limit: int = 30,
) -> list[dict]:
    """
    Return selections due for review across all documents.

    Due = status='learning' AND (next_review_at IS NULL OR next_review_at <= NOW()).
    NULL next_review_at means newly saved (never reviewed) — returned first.
    Joins book_documents to include the document title for display.
    """
    rows = await pool.fetch(
        """
        SELECT rs.selection_id, rs.doc_id, rs.canonical, rs.surface_text,
               rs.sentence_text, rs.note, rs.status,
               rs.review_count, rs.next_review_at, rs.created_at,
               bd.title AS doc_title
          FROM reading_selections rs
          JOIN book_documents bd ON bd.doc_id = rs.doc_id
         WHERE rs.user_id = $1::uuid
           AND rs.status  = 'learning'
           AND (rs.next_review_at IS NULL OR rs.next_review_at <= NOW())
         ORDER BY rs.next_review_at ASC NULLS FIRST, rs.created_at ASC
         LIMIT $2
        """,
        user_id, limit,
    )
    return [dict(r) for r in rows]
