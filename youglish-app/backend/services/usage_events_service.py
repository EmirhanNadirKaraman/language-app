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
    sentence_id: int | None = None,
) -> None:
    import json
    await pool.execute(
        """
        INSERT INTO word_usage_events
               (user_id, item_id, item_type, context, outcome, metadata, sentence_id)
        VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7)
        """,
        user_id,
        item_id,
        item_type,
        context,
        outcome,
        json.dumps(metadata) if metadata is not None else None,
        sentence_id,
    )


async def record_transcript_click_event(
    pool: asyncpg.Pool,
    user_id: str,
    item_id: int,
    item_type: str,
    sentence_id: int,
) -> bool:
    """
    Atomic insert for transcript-click exposure events. Returns True if a new
    row was inserted, False if a row for (user, item, item_type, sentence_id,
    UTC day) already existed (dedup).

    Unique partial index `uq_word_usage_events_transcript_dedup` enforces the
    dedup contract — see migration 026. Same word clicked twice in the same
    sentence on the same day is a no-op the second time.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO word_usage_events
               (user_id, item_id, item_type, context, outcome, sentence_id)
        VALUES ($1::uuid, $2, $3, 'transcript', 'seen', $4)
        ON CONFLICT (user_id, item_id, item_type, sentence_id, event_day)
            WHERE context = 'transcript' AND sentence_id IS NOT NULL
        DO NOTHING
        RETURNING event_id
        """,
        user_id,
        item_id,
        item_type,
        sentence_id,
    )
    return row is not None


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
          AND e.context  IN ('free_chat', 'guided_chat', 'status_change', 'transcript')
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
