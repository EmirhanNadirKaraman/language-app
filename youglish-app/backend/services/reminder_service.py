"""
reminder_service.py

Aggregates learning-activity counts into a compact summary used by the
browser-side reminder system to decide whether to show a notification.

Three counts are computed in parallel:
  srs_due_count      — passive SRS cards with due_date <= NOW() (not 'known')
  reading_due_count  — reading_selections with status='learning' and due now
  learning_item_count — all user_word_knowledge rows with status='learning'
"""
from __future__ import annotations

import asyncio

import asyncpg


async def get_summary(pool: asyncpg.Pool, user_id: str) -> dict:
    """Return reminder summary for the given user."""

    async def _srs_due() -> int:
        row = await pool.fetchrow(
            """
            SELECT COUNT(DISTINCT sc.item_id) AS n
              FROM srs_cards sc
              JOIN user_word_knowledge uwk
                ON uwk.item_id   = sc.item_id
               AND uwk.item_type = sc.item_type
               AND uwk.user_id   = sc.user_id
             WHERE sc.user_id   = $1::uuid
               AND sc.direction = 'passive'
               AND sc.due_date  <= NOW()
               AND uwk.status  != 'known'
            """,
            user_id,
        )
        return int(row["n"]) if row else 0

    async def _reading_due() -> int:
        row = await pool.fetchrow(
            """
            SELECT COUNT(*) AS n
              FROM reading_selections
             WHERE user_id = $1::uuid
               AND status  = 'learning'
               AND (next_review_at IS NULL OR next_review_at <= NOW())
            """,
            user_id,
        )
        return int(row["n"]) if row else 0

    async def _learning_items() -> int:
        row = await pool.fetchrow(
            """
            SELECT COUNT(*) AS n
              FROM user_word_knowledge
             WHERE user_id = $1::uuid
               AND status  = 'learning'
            """,
            user_id,
        )
        return int(row["n"]) if row else 0

    srs_due, reading_due, learning_items = await asyncio.gather(
        _srs_due(), _reading_due(), _learning_items()
    )

    total_due = srs_due + reading_due
    return {
        "srs_due_count":      srs_due,
        "reading_due_count":  reading_due,
        "learning_item_count": learning_items,
        "total_due":          total_due,
        "has_anything_due":   total_due > 0,
    }
