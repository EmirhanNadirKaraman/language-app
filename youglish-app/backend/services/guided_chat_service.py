"""
Guided chat: target selection and progress updates.

Target selection priority:
  1. Soonest-due active SRS card (srs_cards, direction='active', due_date <= now)
  2. Any 'learning' word not yet in srs_cards for active direction
  3. Random word from word_table not yet in user_word_knowledge

Progress update delegates to progression_service, which is the single source
of truth for passive/active rule application.
"""
import asyncpg

from . import progression_service


async def get_next_target(
    pool: asyncpg.Pool, user_id: str, language: str
) -> dict | None:
    """
    Return {item_id, item_type, word, lemma} for the next practice target,
    or None if word_table has no entries for this language.
    """
    async with pool.acquire() as conn:
        # Priority 1: soonest-due active SRS card
        row = await conn.fetchrow(
            """
            SELECT sc.item_id, sc.item_type, wt.word, wt.lemma
            FROM srs_cards sc
            JOIN word_table wt
              ON wt.word_id = sc.item_id AND sc.item_type = 'word'
            WHERE sc.user_id    = $1::uuid
              AND sc.direction  = 'active'
              AND sc.due_date  <= NOW()
              AND wt.language   = $2
            ORDER BY sc.due_date ASC
            LIMIT 1
            """,
            user_id, language,
        )
        if row:
            return dict(row)

        # Priority 2: learning word without an active SRS card yet
        row = await conn.fetchrow(
            """
            SELECT uwk.item_id, uwk.item_type, wt.word, wt.lemma
            FROM user_word_knowledge uwk
            JOIN word_table wt
              ON wt.word_id = uwk.item_id AND uwk.item_type = 'word'
            WHERE uwk.user_id   = $1::uuid
              AND uwk.status    = 'learning'
              AND wt.language   = $2
              AND NOT EXISTS (
                  SELECT 1 FROM srs_cards sc
                  WHERE sc.user_id   = $1::uuid
                    AND sc.item_id   = uwk.item_id
                    AND sc.item_type = uwk.item_type
                    AND sc.direction = 'active'
              )
            ORDER BY uwk.last_seen DESC NULLS LAST
            LIMIT 1
            """,
            user_id, language,
        )
        if row:
            return dict(row)

        # Priority 3: random word not yet tagged by this user
        row = await conn.fetchrow(
            """
            SELECT wt.word_id AS item_id, 'word'::text AS item_type,
                   wt.word, wt.lemma
            FROM word_table wt
            WHERE wt.language = $2
              AND NOT EXISTS (
                  SELECT 1 FROM user_word_knowledge uwk
                  WHERE uwk.user_id   = $1::uuid
                    AND uwk.item_id   = wt.word_id
                    AND uwk.item_type = 'word'
              )
            ORDER BY random()
            LIMIT 1
            """,
            user_id, language,
        )
        return dict(row) if row else None


async def get_target_by_id(
    pool: asyncpg.Pool,
    item_id: int,
    item_type: str,
    language: str,
) -> dict | None:
    """
    Return {item_id, item_type, word, lemma} for a specific practice target.

    Used when the prep view directly hands off a target instead of letting
    get_next_target() choose automatically.
    """
    if item_type == "word":
        row = await pool.fetchrow(
            """
            SELECT word_id AS item_id, 'word'::text AS item_type, word, lemma
            FROM word_table
            WHERE word_id = $1 AND language = $2
            """,
            item_id, language,
        )
    elif item_type == "phrase":
        row = await pool.fetchrow(
            """
            SELECT phrase_id AS item_id, 'phrase'::text AS item_type,
                   surface_form AS word, canonical AS lemma
            FROM phrase_table
            WHERE phrase_id = $1 AND language = $2
            """,
            item_id, language,
        )
    else:
        return None

    return dict(row) if row else None


async def update_progress(
    pool: asyncpg.Pool,
    user_id: str,
    item_id: int,
    item_type: str,
    *,
    target_used: bool,
    target_counted: bool,
) -> None:
    """
    Update mastery progress after a guided turn.

    Maps the turn outcome to a progression event and delegates to
    progression_service.apply_progression, which owns all passive/active rules.

    target_used=True, target_counted=True  → guided_counted
    target_used=True, target_counted=False → guided_used
    target_used=False                      → guided_not_used
    """
    if target_used and target_counted:
        event = "guided_counted"
    elif target_used:
        event = "guided_used"
    else:
        event = "guided_not_used"

    await progression_service.apply_progression(pool, user_id, item_id, item_type, event)
