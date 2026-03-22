"""
Recommendation engine — heuristic sentence and video recommendations.

Architecture
------------
Same two-layer pattern as playlist_service:

  Pure functions (no DB, fully unit-testable):
    score_sentence(unknown_count, due_count, priority_count, target_unknown) -> float
    rank_sentences(candidates, target_unknown, priority_ids, limit) -> list[dict]
    score_video(priority_score, duration) -> float
    channel_genre_multiplier(channel_id, genre, prefs) -> float
    rank_videos(coverage, video_meta, score_by_id, limit, prefs) -> list[dict]

  Async DB + orchestration:
    fetch_sentence_candidates(pool, user_id, language, min_unknown, max_unknown, fetch_limit)
    recommend_sentences(pool, user_id, language, limit, target_unknown, min_unknown, max_unknown)
    recommend_videos(pool, user_id, language, limit)
    recommend_followed_channel_videos(pool, user_id, language, prefs, limit)

Target prioritization
---------------------
Both orchestrators delegate target selection to prioritization_service.
get_prioritized_items() combines four signals:
  - due SRS cards           (weight 4)
  - recent mistakes         (weight 3, exponential decay)
  - frequent unknowns       (weight 2, linear rank)
  - learning-status items   (weight 1)

Channel / genre preference scoring
-----------------------------------
  channel multiplier: followed×1.8, liked×1.3, disliked×0.2, else 1.0
  genre multiplier:   liked×1.2,    disliked×0.4, else 1.0
  final_score = base_score × channel_multiplier × genre_multiplier
"""
from __future__ import annotations

import math

import asyncpg

from .prioritization_service import get_prioritized_items


# ---------------------------------------------------------------------------
# Pure functions — no DB, fully unit-testable
# ---------------------------------------------------------------------------

def score_sentence(
    unknown_count: int,
    due_count: int,
    priority_count: int,
    target_unknown: int,
) -> float:
    """
    Score a single sentence candidate. Higher is better.

    The score is only meaningful relative to other candidates in the same
    batch — it is not bounded or normalised.
    """
    return (
        due_count * 30
        + priority_count * 10
        - abs(unknown_count - target_unknown) * 5
    )


def rank_sentences(
    candidates: list[dict],
    target_unknown: int,
    priority_ids: set[int],
    limit: int,
) -> list[dict]:
    """
    Score and sort sentence candidates; return the top `limit`.

    Each candidate dict must contain:
      unknown_count     int
      due_count         int
      unknown_word_ids  list[int]   — unknown word_ids present in the sentence

    Returns dicts augmented with 'priority_count' and 'score'.
    unknown_word_ids is kept in the dict but excluded from API responses by
    the Pydantic response model (SentenceRecommendation does not declare it).
    """
    scored = []
    for c in candidates:
        priority_count = len(set(c.get("unknown_word_ids") or []) & priority_ids)
        s = score_sentence(c["unknown_count"], c["due_count"], priority_count, target_unknown)
        scored.append({**c, "priority_count": priority_count, "score": s})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def score_video(priority_score: float, duration: float) -> float:
    """
    Score a video candidate. Higher is better.

    priority_score — sum of prioritization scores for the items this video covers.
                     Items with higher urgency (due, recent mistake) contribute more.
    duration       — tiny penalty to avoid always picking very long videos when
                     coverage scores are equal.
    """
    return priority_score - duration / 10_000


def channel_genre_multiplier(
    channel_id: str | None,
    genre: str | None,
    prefs: dict,
) -> float:
    """
    Return a preference multiplier for a video based on its channel and genre.

      channel: followed×1.8, liked×1.3, disliked×0.2, else 1.0
      genre:   liked×1.2,    disliked×0.4, else 1.0
    """
    followed  = set(prefs.get("followed_channels") or [])
    liked_ch  = set(prefs.get("liked_channels") or [])
    disliked_ch = set(prefs.get("disliked_channels") or [])
    liked_g   = set(prefs.get("liked_genres") or [])
    disliked_g = set(prefs.get("disliked_genres") or [])

    if channel_id in followed:
        ch_mult = 1.8
    elif channel_id in liked_ch:
        ch_mult = 1.3
    elif channel_id in disliked_ch:
        ch_mult = 0.2
    else:
        ch_mult = 1.0

    if genre in liked_g:
        g_mult = 1.2
    elif genre in disliked_g:
        g_mult = 0.4
    else:
        g_mult = 1.0

    return ch_mult * g_mult


def rank_videos(
    coverage: dict[str, set[int]],
    video_meta: dict[str, dict],
    score_by_id: dict[int, float],
    limit: int,
    prefs: dict | None = None,
) -> list[dict]:
    """
    Score each video by the sum of priority scores for the items it covers,
    then apply channel/genre preference multipliers when prefs are provided.

    score_by_id — item_id → priority score from get_prioritized_items().
                  Items absent from this dict contribute 0 to the video score.

    Returns list of dicts with keys:
      video_id, title, thumbnail_url, language, duration,
      start_time, start_time_int, priority_score, covered_item_ids,
      covered_count, score, channel_id, channel_name, genre
    """
    target_ids = set(score_by_id)
    _prefs = prefs or {}
    results = []

    for vid, word_ids in coverage.items():
        meta       = video_meta[vid]
        covered    = sorted(word_ids & target_ids)
        pri_score  = sum(score_by_id.get(wid, 0.0) for wid in covered)
        channel_id = meta.get("channel_id")
        genre      = meta.get("genre")
        multiplier = channel_genre_multiplier(channel_id, genre, _prefs)
        s          = score_video(pri_score, meta["duration"]) * multiplier

        results.append({
            "video_id":         vid,
            "title":            meta["title"],
            "thumbnail_url":    meta["thumbnail_url"],
            "language":         meta["language"],
            "duration":         meta["duration"],
            "start_time":       meta["best_start_time"],
            "start_time_int":   math.floor(meta["best_start_time"]),
            "priority_score":   pri_score,
            "covered_item_ids": covered,
            "covered_count":    len(covered),
            "score":            s,
            "channel_id":       channel_id,
            "channel_name":     meta.get("channel_name"),
            "genre":            genre,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# DB layer — coverage query (includes channel/genre columns)
# ---------------------------------------------------------------------------

async def _fetch_coverage(
    pool: asyncpg.Pool,
    item_ids: list[int],
    language: str,
) -> tuple[dict[str, set[int]], dict[str, dict]]:
    """
    Query videos that contain at least one target word.
    Includes channel_id, channel_name, genre for preference scoring.

    Returns:
        coverage   — video_id → set of word_ids covered
        video_meta — video_id → metadata dict
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (v.video_id, wts.word_id)
            v.video_id,
            v.title,
            v.thumbnail_url,
            v.language,
            v.duration,
            v.channel_id,
            v.channel_name,
            v.genre,
            wts.word_id,
            s.sentence_id,
            s.start_time,
            s.content
        FROM word_to_sentence wts
        JOIN sentence s ON s.sentence_id = wts.sentence_id
        JOIN video v    ON v.video_id    = s.video_id
        WHERE wts.word_id = ANY($1)
          AND v.language  = $2
        ORDER BY v.video_id, wts.word_id, s.start_time
        """,
        item_ids,
        language,
    )

    coverage: dict[str, set[int]] = {}
    video_meta: dict[str, dict] = {}

    for row in rows:
        vid = row["video_id"]
        wid = row["word_id"]

        if vid not in coverage:
            coverage[vid] = set()
            video_meta[vid] = {
                "title":          row["title"],
                "thumbnail_url":  row["thumbnail_url"],
                "language":       row["language"],
                "duration":       float(row["duration"] or 0),
                "channel_id":     row["channel_id"],
                "channel_name":   row["channel_name"],
                "genre":          row["genre"],
                "best_start_time": float(row["start_time"]),
            }
        else:
            if float(row["start_time"]) < video_meta[vid]["best_start_time"]:
                video_meta[vid]["best_start_time"] = float(row["start_time"])

        coverage[vid].add(wid)

    return coverage, video_meta


# ---------------------------------------------------------------------------
# DB layer — sentence candidates
# ---------------------------------------------------------------------------

_SENTENCE_CANDIDATE_SQL = """
SELECT
    s.sentence_id,
    s.content,
    s.start_time,
    v.video_id,
    v.title        AS video_title,
    v.thumbnail_url,
    v.language,
    v.duration,
    COUNT(DISTINCT wts.word_id)
        FILTER (WHERE uwk.status IS NULL OR uwk.status = 'unknown')
        AS unknown_count,
    COUNT(DISTINCT sc.card_id)
        FILTER (WHERE sc.due_date <= NOW())
        AS due_count,
    array_agg(DISTINCT wts.word_id)
        FILTER (WHERE uwk.status IS NULL OR uwk.status = 'unknown')
        AS unknown_word_ids
FROM sentence s
JOIN video v ON v.video_id = s.video_id
JOIN word_to_sentence wts ON wts.sentence_id = s.sentence_id
LEFT JOIN user_word_knowledge uwk
       ON uwk.item_id   = wts.word_id
      AND uwk.item_type = 'word'
      AND uwk.user_id   = $1::uuid
LEFT JOIN srs_cards sc
       ON sc.item_id   = wts.word_id
      AND sc.item_type = 'word'
      AND sc.user_id   = $1::uuid
      AND sc.direction = 'passive'
WHERE v.language = $2
GROUP BY
    s.sentence_id, s.content, s.start_time,
    v.video_id, v.title, v.thumbnail_url, v.language, v.duration
HAVING COUNT(DISTINCT wts.word_id)
       FILTER (WHERE uwk.status IS NULL OR uwk.status = 'unknown')
       BETWEEN $3 AND $4
ORDER BY due_count DESC, unknown_count ASC
LIMIT $5
"""


async def fetch_sentence_candidates(
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
    min_unknown: int,
    max_unknown: int,
    fetch_limit: int = 300,
) -> list[dict]:
    """
    Fetch up to `fetch_limit` candidate sentences filtered by unknown word count.

    Returns raw candidate dicts. Call rank_sentences() on the result.
    fetch_limit is an internal cap — the user-visible `limit` is applied
    after scoring in rank_sentences().
    """
    rows = await pool.fetch(
        _SENTENCE_CANDIDATE_SQL,
        user_id, language, min_unknown, max_unknown, fetch_limit,
    )
    return [
        {
            "sentence_id":      r["sentence_id"],
            "content":          r["content"],
            "start_time":       float(r["start_time"]),
            "start_time_int":   math.floor(float(r["start_time"])),
            "video_id":         r["video_id"],
            "video_title":      r["video_title"],
            "thumbnail_url":    r["thumbnail_url"],
            "language":         r["language"],
            "duration":         float(r["duration"] or 0),
            "unknown_count":    r["unknown_count"],
            "due_count":        r["due_count"],
            "unknown_word_ids": list(r["unknown_word_ids"] or []),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Orchestrators
# ---------------------------------------------------------------------------

async def recommend_sentences(
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
    limit: int,
    target_unknown: int,
    min_unknown: int,
    max_unknown: int,
) -> dict:
    """
    Return ranked sentence recommendations for a user.

    Priority items come from the shared prioritization layer, which combines
    due SRS cards, recent mistakes, frequency, and learning status into one
    scored list.  The top item_ids are used to boost sentences containing
    those items.

    If the initial candidate fetch returns nothing, one retry is made with a
    wider unknown range (min-1, max+2) to avoid an empty response when the
    user's vocabulary is sparse or the DB has few sentences.
    """
    items        = await get_prioritized_items(pool, user_id, limit=100)
    priority_ids = {item.item_id for item in items}

    candidates = await fetch_sentence_candidates(
        pool, user_id, language, min_unknown, max_unknown,
    )

    if not candidates:
        candidates = await fetch_sentence_candidates(
            pool, user_id, language,
            max(0, min_unknown - 1), max_unknown + 2,
        )

    ranked = rank_sentences(candidates, target_unknown, priority_ids, limit)
    return {
        "sentences":      ranked,
        "target_unknown": target_unknown,
        "total":          len(ranked),
    }


# ---------------------------------------------------------------------------
# Item recommendation helpers
# ---------------------------------------------------------------------------

_ENRICH_ITEMS_SQL = """
SELECT
    w.word_id,
    w.word,
    w.lemma,
    uwk.status          AS current_status,
    uwk.passive_level,
    uwk.active_level,
    sc.due_date
FROM word_table w
LEFT JOIN user_word_knowledge uwk
       ON uwk.item_id   = w.word_id
      AND uwk.item_type = 'word'
      AND uwk.user_id   = $1::uuid
LEFT JOIN srs_cards sc
       ON sc.item_id    = w.word_id
      AND sc.item_type  = 'word'
      AND sc.user_id    = $1::uuid
      AND sc.direction  = 'passive'
WHERE w.word_id = ANY($2::int[])
  AND w.language = $3
"""


async def enrich_items(
    pool: asyncpg.Pool,
    user_id: str,
    item_ids: list[int],
    language: str,
) -> dict[int, dict]:
    """
    Fetch display text and knowledge metadata for a list of word item_ids.

    Returns item_id → enrichment dict.  Items not found in word_table for the
    given language are absent from the result — the caller skips them.

    Only handles item_type='word'.  Phrase and grammar_rule enrichment is a
    TODO: add their lookup tables here when available.
    """
    if not item_ids:
        return {}
    rows = await pool.fetch(_ENRICH_ITEMS_SQL, user_id, item_ids, language)
    return {
        r["word_id"]: {
            "display_text":   r["word"],
            "secondary_text": r["lemma"] if r["lemma"] != r["word"] else None,
            "lemma":          r["lemma"],
            "current_status": r["current_status"],
            "passive_level":  r["passive_level"] or 0,
            "active_level":   r["active_level"] or 0,
            "due_date":       r["due_date"],
        }
        for r in rows
    }


async def recommend_items(
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
    item_type: str,
    limit: int,
) -> dict:
    """
    Return ranked item recommendations enriched with display text.

    Delegates scoring entirely to get_prioritized_items(), then enriches
    with the appropriate table depending on item_type:
      'word'   → word_table via enrich_items()
      'phrase' → phrase_table via phrase_service.enrich_phrases()
      other    → returns empty (not yet supported)

    Items not found in the relevant table for the given language are silently
    skipped (cross-language IDs can legitimately appear in signals).
    """
    items = await get_prioritized_items(pool, user_id, item_type=item_type, limit=limit)

    if not items:
        return {"items": [], "item_type": item_type, "language": language, "total": 0}

    item_ids = [item.item_id for item in items]

    if item_type == "word":
        enrichment = await enrich_items(pool, user_id, item_ids, language)
    elif item_type == "phrase":
        from .phrase_service import enrich_phrases
        enrichment = await enrich_phrases(pool, user_id, item_ids, language)
    else:
        return {"items": [], "item_type": item_type, "language": language, "total": 0}

    result = []
    for item in items:
        meta = enrichment.get(item.item_id)
        if meta is None:
            continue
        result.append({
            "item_id":        item.item_id,
            "item_type":      item.item_type,
            "score":          item.score,
            "display_text":   meta["display_text"],
            "secondary_text": meta["secondary_text"],
            "current_status": meta["current_status"],
            "passive_level":  meta["passive_level"],
            "active_level":   meta["active_level"],
            "due_date":       meta["due_date"],
            "signals":        item.signals,
            "reasons":        item.reasons,
        })

    return {"items": result, "item_type": item_type, "language": language, "total": len(result)}


async def recommend_videos(
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
    limit: int,
) -> dict:
    """
    Return ranked video recommendations for a user.

    Videos are ranked by their total priority coverage score — the sum of
    priority scores for the target items they contain — multiplied by
    channel/genre preference weights from the user's settings.

    Returns an empty list with reason='no_target_items' when the user has
    no prioritised items (e.g. a brand-new user with no SRS cards and no
    usage events).
    """
    from .settings_service import get_preferences

    items = await get_prioritized_items(pool, user_id, limit=100)

    if not items:
        return {
            "videos":            [],
            "target_item_count": 0,
            "reason":            "no_target_items",
        }

    score_by_id = {item.item_id: item.score for item in items}
    coverage, video_meta = await _fetch_coverage(pool, list(score_by_id), language)
    prefs  = await get_preferences(pool, user_id)
    ranked = rank_videos(coverage, video_meta, score_by_id, limit, prefs=prefs)

    return {
        "videos":            ranked,
        "target_item_count": len(items),
        "reason":            None,
    }


async def recommend_followed_channel_videos(
    pool: asyncpg.Pool,
    user_id: str,
    language: str,
    prefs: dict,
    limit: int,
) -> dict:
    """
    Return recent videos from the user's followed channels.

    Unlike the ranked recommendation feed, this is not filtered by priority
    items — it returns the most recent videos from followed channels for
    passive immersion browsing.
    """
    followed = list(prefs.get("followed_channels") or [])
    if not followed:
        return {"videos": [], "total": 0}

    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (v.video_id)
            v.video_id,
            v.title,
            v.thumbnail_url,
            v.language,
            v.duration,
            v.channel_id,
            v.channel_name,
            v.genre,
            s.start_time
        FROM video v
        JOIN sentence s ON s.video_id = v.video_id
        WHERE v.channel_id = ANY($1)
          AND v.language   = $2
        ORDER BY v.video_id, s.start_time
        LIMIT $3
        """,
        followed,
        language,
        limit,
    )

    videos = [
        {
            "video_id":         r["video_id"],
            "title":            r["title"],
            "thumbnail_url":    r["thumbnail_url"],
            "language":         r["language"],
            "duration":         float(r["duration"] or 0),
            "start_time":       float(r["start_time"]),
            "start_time_int":   math.floor(float(r["start_time"])),
            "priority_score":   0.0,
            "covered_item_ids": [],
            "covered_count":    0,
            "score":            0.0,
            "channel_id":       r["channel_id"],
            "channel_name":     r["channel_name"],
            "genre":            r["genre"],
        }
        for r in rows
    ]

    return {"videos": videos, "total": len(videos)}
