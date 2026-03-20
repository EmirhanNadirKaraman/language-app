"""
Word usage events — write and aggregate.

record_event() is fire-and-forget: call it with asyncio.create_task() from
routers so analytics failures never crash the main request path.

Valid contexts:  'free_chat' | 'guided_chat' | 'status_change' | 'srs_review'
Valid outcomes:  'seen' | 'used' | 'correct' | 'incorrect'
"""
import asyncpg


async def record_event(
    pool: asyncpg.Pool,
    user_id: str,
    item_id: int,
    item_type: str,
    context: str,
    outcome: str,
    metadata: dict | None = None,
) -> None:
    import json
    await pool.execute(
        """
        INSERT INTO word_usage_events
               (user_id, item_id, item_type, context, outcome, metadata)
        VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb)
        """,
        user_id,
        item_id,
        item_type,
        context,
        outcome,
        json.dumps(metadata) if metadata is not None else None,
    )


# ---------------------------------------------------------------------------
# Analytics aggregations — all join word_table for the word text
# ---------------------------------------------------------------------------

async def most_frequent_unknown_items(
    pool: asyncpg.Pool,
    user_id: str,
    limit: int = 10,
) -> list[dict]:
    """Items with status='unknown' that appeared most in chat/subtitle events."""
    rows = await pool.fetch(
        """
        SELECT e.item_id, e.item_type, wt.word, COUNT(*) AS event_count
        FROM word_usage_events e
        LEFT JOIN word_table wt ON wt.word_id = e.item_id AND e.item_type = 'word'
        JOIN user_word_knowledge uwk
          ON uwk.user_id   = e.user_id
         AND uwk.item_id   = e.item_id
         AND uwk.item_type = e.item_type
        WHERE e.user_id = $1::uuid
          AND uwk.status  = 'unknown'
          AND e.context  IN ('free_chat', 'guided_chat', 'status_change')
        GROUP BY e.item_id, e.item_type, wt.word
        ORDER BY event_count DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [dict(r) for r in rows]


async def most_frequent_learning_items(
    pool: asyncpg.Pool,
    user_id: str,
    limit: int = 10,
) -> list[dict]:
    """Items with status='learning' that the user interacted with most."""
    rows = await pool.fetch(
        """
        SELECT e.item_id, e.item_type, wt.word, COUNT(*) AS event_count
        FROM word_usage_events e
        LEFT JOIN word_table wt ON wt.word_id = e.item_id AND e.item_type = 'word'
        JOIN user_word_knowledge uwk
          ON uwk.user_id   = e.user_id
         AND uwk.item_id   = e.item_id
         AND uwk.item_type = e.item_type
        WHERE e.user_id = $1::uuid
          AND uwk.status = 'learning'
        GROUP BY e.item_id, e.item_type, wt.word
        ORDER BY event_count DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [dict(r) for r in rows]


async def recently_failed_items(
    pool: asyncpg.Pool,
    user_id: str,
    limit: int = 10,
) -> list[dict]:
    """Items most recently answered incorrectly, with fail count."""
    rows = await pool.fetch(
        """
        SELECT e.item_id, e.item_type, wt.word,
               COUNT(*) AS fail_count,
               MAX(e.created_at) AS last_failed
        FROM word_usage_events e
        LEFT JOIN word_table wt ON wt.word_id = e.item_id AND e.item_type = 'word'
        WHERE e.user_id = $1::uuid
          AND e.outcome  = 'incorrect'
        GROUP BY e.item_id, e.item_type, wt.word
        ORDER BY last_failed DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )
    return [dict(r) for r in rows]


async def most_interacted_items(
    pool: asyncpg.Pool,
    user_id: str,
    since_days: int = 30,
    limit: int = 10,
) -> list[dict]:
    """Items with most total events in the last `since_days` days."""
    rows = await pool.fetch(
        """
        SELECT e.item_id, e.item_type, wt.word,
               COUNT(*) AS total_interactions,
               MAX(e.created_at) AS last_seen
        FROM word_usage_events e
        LEFT JOIN word_table wt ON wt.word_id = e.item_id AND e.item_type = 'word'
        WHERE e.user_id    = $1::uuid
          AND e.created_at >= NOW() - ($2 || ' days')::INTERVAL
        GROUP BY e.item_id, e.item_type, wt.word
        ORDER BY total_interactions DESC
        LIMIT $3
        """,
        user_id,
        str(since_days),
        limit,
    )
    return [dict(r) for r in rows]
