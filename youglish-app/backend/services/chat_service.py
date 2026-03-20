import asyncpg
import json


async def create_session(
    pool: asyncpg.Pool,
    user_id: str,
    session_type: str = "free",
    *,
    target_item_id: int | None = None,
    target_item_type: str | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO chat_sessions
            (user_id, session_type, target_item_id, target_item_type)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        user_id,
        session_type,
        target_item_id,
        target_item_type,
    )
    return _session_dict(row)


async def get_session(pool: asyncpg.Pool, session_id: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    return _session_dict(row) if row else None


async def list_sessions(pool: asyncpg.Pool, user_id: str) -> list[dict]:
    rows = await pool.fetch(
        "SELECT * FROM chat_sessions WHERE user_id = $1 ORDER BY started_at DESC",
        user_id,
    )
    return [_session_dict(r) for r in rows]


async def save_message(
    pool: asyncpg.Pool,
    session_id: str,
    role: str,
    content: str,
    *,
    language_detected: str | None = None,
    corrections: list | None = None,
    word_matches: list | None = None,
    evaluation: dict | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO chat_messages
            (session_id, role, content, language_detected,
             corrections, word_matches, evaluation)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7::jsonb)
        RETURNING *
        """,
        session_id,
        role,
        content,
        language_detected,
        json.dumps(corrections)  if corrections  is not None else None,
        json.dumps(word_matches) if word_matches is not None else None,
        json.dumps(evaluation)   if evaluation   is not None else None,
    )
    return _message_dict(row)


async def get_messages(pool: asyncpg.Pool, session_id: str) -> list[dict]:
    rows = await pool.fetch(
        "SELECT * FROM chat_messages WHERE session_id = $1 ORDER BY created_at ASC",
        session_id,
    )
    return [_message_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_dict(row) -> dict:
    return {
        "session_id": str(row["session_id"]),
        "user_id": str(row["user_id"]),          # used for ownership checks, stripped by response_model
        "session_type": row["session_type"],
        "target_item_id": row["target_item_id"],
        "target_item_type": row["target_item_type"],
        "started_at": row["started_at"],
    }


def _message_dict(row) -> dict:
    return {
        "message_id":       row["message_id"],
        "session_id":       str(row["session_id"]),
        "role":             row["role"],
        "content":          row["content"],
        "language_detected": row["language_detected"],
        "corrections":  json.loads(row["corrections"])  if row["corrections"]  is not None else None,
        "word_matches": json.loads(row["word_matches"]) if row["word_matches"] is not None else None,
        "evaluation":   json.loads(row["evaluation"])   if row["evaluation"]   is not None else None,
        "created_at":       row["created_at"],
    }
