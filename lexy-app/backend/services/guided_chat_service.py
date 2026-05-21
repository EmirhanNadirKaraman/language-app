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
    Return {item_id, item_type, word, lemma} for the next practice target.

    Priority order (each tier considers both words and phrases):
      1. Soonest-due active SRS card (any item_type, joined to the relevant
         display table for the language).
      2. Any 'learning' item that does NOT yet have an active SRS card.
      3. Random untagged item from the catalog (word_table ∪ phrase_table).

    Returns None when no catalog item is available for the language.

    For phrases:
        word  = phrase_table.surface_form
        lemma = phrase_table.canonical
    """
    async with pool.acquire() as conn:
        # Priority 1: soonest-due active SRS card across words AND phrases.
        # CASE expressions resolve display fields from the appropriate table.
        row = await conn.fetchrow(
            """
            SELECT sc.item_id,
                   sc.item_type,
                   CASE sc.item_type
                       WHEN 'word'   THEN wt.word
                       WHEN 'phrase' THEN pt.surface_form
                   END AS word,
                   CASE sc.item_type
                       WHEN 'word'   THEN wt.lemma
                       WHEN 'phrase' THEN pt.canonical
                   END AS lemma
              FROM srs_cards sc
              LEFT JOIN word_table wt
                     ON sc.item_type = 'word'
                    AND wt.word_id   = sc.item_id
                    AND wt.language  = $2
              LEFT JOIN phrase_table pt
                     ON sc.item_type  = 'phrase'
                    AND pt.phrase_id  = sc.item_id
                    AND pt.language   = $2
             WHERE sc.user_id    = $1::uuid
               AND sc.direction  = 'active'
               AND sc.due_date  <= NOW()
               AND (
                       (sc.item_type = 'word'   AND wt.word_id   IS NOT NULL)
                    OR (sc.item_type = 'phrase' AND pt.phrase_id IS NOT NULL)
                   )
             ORDER BY sc.due_date ASC
             LIMIT 1
            """,
            user_id, language,
        )
        if row:
            return dict(row)

        # Priority 2: learning item (word OR phrase) without an active SRS card.
        row = await conn.fetchrow(
            """
            SELECT uwk.item_id,
                   uwk.item_type,
                   CASE uwk.item_type
                       WHEN 'word'   THEN wt.word
                       WHEN 'phrase' THEN pt.surface_form
                   END AS word,
                   CASE uwk.item_type
                       WHEN 'word'   THEN wt.lemma
                       WHEN 'phrase' THEN pt.canonical
                   END AS lemma
              FROM user_word_knowledge uwk
              LEFT JOIN word_table wt
                     ON uwk.item_type = 'word'
                    AND wt.word_id    = uwk.item_id
                    AND wt.language   = $2
              LEFT JOIN phrase_table pt
                     ON uwk.item_type  = 'phrase'
                    AND pt.phrase_id   = uwk.item_id
                    AND pt.language    = $2
             WHERE uwk.user_id  = $1::uuid
               AND uwk.status   = 'learning'
               AND uwk.item_type IN ('word', 'phrase')
               AND (
                       (uwk.item_type = 'word'   AND wt.word_id   IS NOT NULL)
                    OR (uwk.item_type = 'phrase' AND pt.phrase_id IS NOT NULL)
                   )
               AND NOT EXISTS (
                   SELECT 1
                     FROM srs_cards sc
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

        # Priority 3: random item not yet tagged by this user — words ∪ phrases.
        row = await conn.fetchrow(
            """
            WITH candidates AS (
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
                UNION ALL
                SELECT pt.phrase_id AS item_id, 'phrase'::text AS item_type,
                       pt.surface_form AS word, pt.canonical AS lemma
                  FROM phrase_table pt
                 WHERE pt.language = $2
                   AND NOT EXISTS (
                       SELECT 1 FROM user_word_knowledge uwk
                        WHERE uwk.user_id   = $1::uuid
                          AND uwk.item_id   = pt.phrase_id
                          AND uwk.item_type = 'phrase'
                   )
            )
            SELECT * FROM candidates ORDER BY random() LIMIT 1
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
