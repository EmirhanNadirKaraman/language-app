import re

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
# Free-chat vocabulary matching
# ---------------------------------------------------------------------------

async def match_learning_words(
    pool: asyncpg.Pool,
    user_id: str,
    text: str,
    language: str,
) -> list[dict]:
    """
    Find non-mastered vocabulary items the user is tracking that appear in `text`.

    Two paths combined:
      WORDS   — tokenises the message into lowercase alphabetic words and matches
                against word_table (surface OR lemma).
      PHRASES — delegates to matcher_service.match_sentence_with_ids, which runs
                the spaCy-based phrase extractor (verb patterns, separable verbs,
                reflexive verbs) and returns canonical phrase IDs. This catches
                inflected production like "ich freue mich auf X" matching the
                canonical "sich freuen auf".

    Returns a deduplicated list of dicts shaped:
        {item_id, item_type ∈ {'word','phrase'}, word}

    The polymorphic shape lets routers/chat.py:send_message iterate the matches
    and call apply_progression(..., item_type, ...) for each — words and phrases
    advance through the same free_chat_* events.
    """
    tokens = list({w.lower() for w in re.findall(r"[^\W\d_]+", text, re.UNICODE)})
    if not tokens:
        return []

    word_rows = await pool.fetch(
        """
        SELECT DISTINCT wt.word_id AS item_id, 'word'::text AS item_type, wt.word
          FROM word_table wt
          JOIN user_word_knowledge uwk
               ON uwk.item_id   = wt.word_id
              AND uwk.item_type = 'word'
              AND uwk.user_id   = $1::uuid
         WHERE (LOWER(wt.word) = ANY($2::text[]) OR LOWER(wt.lemma) = ANY($2::text[]))
           AND wt.language    = $3
           AND uwk.status    != 'known'
        """,
        user_id, tokens, language,
    )
    results: list[dict] = [dict(r) for r in word_rows]

    # Phrase matching — defer the import to avoid the matcher_service module-level
    # spaCy/phrase_finder bootstrap during chat_service import (and to make tests
    # that don't touch chat insensitive to matcher init failures).
    from . import matcher_service

    try:
        phrase_hits = await matcher_service.match_sentence_with_ids(pool, text, language)
    except Exception:
        # Free chat must not crash if phrase extraction errors — analytics-grade only.
        phrase_hits = []

    phrase_ids = list({p["phrase_id"] for p in phrase_hits if p.get("phrase_id") is not None})
    if phrase_ids:
        phrase_rows = await pool.fetch(
            """
            SELECT DISTINCT pt.phrase_id AS item_id,
                   'phrase'::text       AS item_type,
                   pt.surface_form      AS word
              FROM phrase_table pt
              JOIN user_word_knowledge uwk
                   ON uwk.item_id   = pt.phrase_id
                  AND uwk.item_type = 'phrase'
                  AND uwk.user_id   = $1::uuid
             WHERE pt.phrase_id  = ANY($2::int[])
               AND pt.language   = $3
               AND uwk.status   != 'known'
            """,
            user_id, phrase_ids, language,
        )
        results.extend(dict(r) for r in phrase_rows)

    return results


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
