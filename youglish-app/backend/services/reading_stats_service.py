import asyncpg

# Count unique lemmas in a video, grouped by the user's best known status for each lemma.
#
# A lemma can have multiple surface forms (word_ids). If the user has marked any
# surface form as 'known', the lemma counts as known. Same for 'learning'.
# Lemmas with no user_word_knowledge row count as 'unknown'.
_STATS_QUERY = """
WITH video_lemmas AS (
    SELECT DISTINCT wt.lemma
    FROM sentence s
    JOIN word_to_sentence wts ON wts.sentence_id = s.sentence_id
    JOIN word_table wt         ON wt.word_id = wts.word_id
    WHERE s.video_id = $1
),
lemma_status AS (
    SELECT
        vl.lemma,
        COALESCE(MAX(
            CASE uwk.status
                WHEN 'known'    THEN 2
                WHEN 'learning' THEN 1
                ELSE 0
            END
        ), 0) AS status_rank
    FROM video_lemmas vl
    JOIN word_table wt ON wt.lemma = vl.lemma
    LEFT JOIN user_word_knowledge uwk
           ON uwk.item_id   = wt.word_id
          AND uwk.item_type = 'word'
          AND uwk.user_id   = $2::uuid
    GROUP BY vl.lemma
)
SELECT
    COUNT(*)                                                          AS total_lemmas,
    COUNT(*) FILTER (WHERE status_rank = 2)                          AS known,
    COUNT(*) FILTER (WHERE status_rank = 1)                          AS learning,
    COUNT(*) FILTER (WHERE status_rank = 0)                          AS unknown,
    COALESCE(ROUND(
        COUNT(*) FILTER (WHERE status_rank = 2)::numeric
        / NULLIF(COUNT(*), 0) * 100, 1), 0)                         AS known_pct,
    COALESCE(ROUND(
        COUNT(*) FILTER (WHERE status_rank = 1)::numeric
        / NULLIF(COUNT(*), 0) * 100, 1), 0)                         AS learning_pct,
    COALESCE(ROUND(
        COUNT(*) FILTER (WHERE status_rank = 0)::numeric
        / NULLIF(COUNT(*), 0) * 100, 1), 0)                         AS unknown_pct
FROM lemma_status
"""


async def get_video_word_statuses(
    pool: asyncpg.Pool, video_id: str, user_id: str
) -> dict[str, str]:
    """Return {word_lowercase: status} for all user-tagged words in a video."""
    rows = await pool.fetch(
        """
        SELECT DISTINCT w.word, uwk.status
        FROM sentence s
        JOIN word_to_sentence wts ON wts.sentence_id = s.sentence_id
        JOIN word_table w         ON w.word_id = wts.word_id
        JOIN user_word_knowledge uwk
               ON uwk.item_id   = w.word_id
              AND uwk.item_type = 'word'
              AND uwk.user_id   = $2::uuid
        WHERE s.video_id = $1
        """,
        video_id,
        user_id,
    )
    return {r["word"].lower(): r["status"] for r in rows}


async def get_video_stats(pool: asyncpg.Pool, video_id: str, user_id: str) -> dict:
    row = await pool.fetchrow(_STATS_QUERY, video_id, user_id)
    if row is None:
        return {
            "total_lemmas": 0,
            "known": 0, "learning": 0, "unknown": 0,
            "known_pct": 0.0, "learning_pct": 0.0, "unknown_pct": 0.0,
        }
    return {
        "total_lemmas": row["total_lemmas"],
        "known":        row["known"],
        "learning":     row["learning"],
        "unknown":      row["unknown"],
        "known_pct":    float(row["known_pct"]),
        "learning_pct": float(row["learning_pct"]),
        "unknown_pct":  float(row["unknown_pct"]),
    }
