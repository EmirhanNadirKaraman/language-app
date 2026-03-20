import uuid as _uuid
from typing import Literal

import asyncpg

VALID_STATUSES = {"unknown", "learning", "known"}
VALID_ITEM_TYPES = {"word", "phrase", "grammar_rule"}


async def lookup_word_by_text(
    pool: asyncpg.Pool,
    user_id: str,
    word: str,
    language: str,
) -> dict | None:
    """Return word_id, lemma, and current user status for a surface form."""
    row = await pool.fetchrow(
        """
        SELECT
            w.word_id,
            w.word,
            w.lemma,
            uwk.status                        AS current_status,
            COALESCE(uwk.passive_level, 0)    AS passive_level,
            COALESCE(uwk.active_level,  0)    AS active_level,
            sc_p.due_date                     AS passive_due,
            sc_a.due_date                     AS active_due
        FROM word_table w
        LEFT JOIN user_word_knowledge uwk
               ON uwk.item_id   = w.word_id
              AND uwk.item_type = 'word'
              AND uwk.user_id   = $2::uuid
        LEFT JOIN srs_cards sc_p
               ON sc_p.item_id   = w.word_id
              AND sc_p.item_type = 'word'
              AND sc_p.user_id   = $2::uuid
              AND sc_p.direction = 'passive'
        LEFT JOIN srs_cards sc_a
               ON sc_a.item_id   = w.word_id
              AND sc_a.item_type = 'word'
              AND sc_a.user_id   = $2::uuid
              AND sc_a.direction = 'active'
        WHERE w.word ILIKE $1 AND w.language = $3
        LIMIT 1
        """,
        word,
        user_id,
        language,
    )
    if row is None:
        return None
    return {
        "word_id":       row["word_id"],
        "word":          row["word"],
        "lemma":         row["lemma"],
        "current_status": row["current_status"],
        "passive_level": row["passive_level"],
        "active_level":  row["active_level"],
        "passive_due":   row["passive_due"],
        "active_due":    row["active_due"],
    }


async def get_user_knowledge(pool: asyncpg.Pool, user_id: str) -> list[dict]:
    """Return all word/phrase knowledge rows for a user, newest first."""
    rows = await pool.fetch(
        """
        SELECT item_id, item_type, status, passive_level, active_level, notes, last_seen
        FROM user_word_knowledge
        WHERE user_id = $1::uuid
        ORDER BY last_seen DESC NULLS LAST
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def upsert_word_status(
    pool: asyncpg.Pool,
    user_id: str,
    item_type: str,
    item_id: int,
    status: str,
) -> dict:
    """
    Insert or update a user's knowledge status for a word/phrase/grammar_rule.

    - First call for a (user, item_id, item_type) pair → inserts a new row.
    - Subsequent calls → updates status and last_seen only.
      (passive_level, active_level, times_seen are updated by other services.)

    Raises ValueError on invalid item_type or status.
    """
    if item_type not in VALID_ITEM_TYPES:
        raise ValueError(f"item_type must be one of {sorted(VALID_ITEM_TYPES)}, got {item_type!r}")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}, got {status!r}")

    row = await pool.fetchrow(
        """
        INSERT INTO user_word_knowledge (user_id, item_id, item_type, status, last_seen)
        VALUES ($1::uuid, $2, $3, $4, NOW())
        ON CONFLICT (user_id, item_id, item_type)
        DO UPDATE SET
            status    = EXCLUDED.status,
            last_seen = NOW()
        RETURNING item_id, item_type, status, passive_level, active_level, notes, last_seen
        """,
        user_id,
        item_id,
        item_type,
        status,
    )
    return dict(row)
