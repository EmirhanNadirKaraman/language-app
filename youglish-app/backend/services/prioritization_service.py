"""
Shared target prioritization layer.

Produces a scored, explainable list of learning items (words, phrases,
grammar rules) for a given user.  All downstream recommendation systems
(sentences, videos, playlists, future item recommendations) consume this
list instead of implementing their own ad-hoc signal logic.

Architecture
------------
Pure functions (no DB, fully unit-testable):
  compute_item_score(is_due, mistake_recency, freq_rank, is_learning, weights)
  explain_signals(is_due, mistake_recency, freq_rank, is_learning)

Async DB helpers (private):
  _fetch_due_items(pool, user_id, item_type)
  _fetch_recent_mistakes(pool, user_id, item_type, window_days)
  _fetch_learning_items(pool, user_id, item_type)

Orchestrator:
  get_prioritized_items(pool, user_id, item_type, limit, ...) -> list[PrioritizedItem]

Signals
-------
Signal           Source                                 Range     Weight
is_due           srs_cards.due_date <= NOW()            {0, 1}    4.0
mistake_recency  recent 'incorrect' in word_usage_events 0..1     3.0   exp(-days/7)
freq_rank        most_frequent_unknown_items rank        0..1      2.0   linear
is_learning      user_word_knowledge.status='learning'  {0, 1}    1.0

Max possible score = 10.0.  Weights are in DEFAULT_WEIGHTS and can be
overridden per-call; they are not user-configurable yet.

Adding a new signal
-------------------
1. Add a fetch helper for the new signal.
2. Call it inside get_prioritized_items (add to asyncio.gather).
3. Add signal weight to ScoringWeights.
4. Update compute_item_score and explain_signals.
No changes required in any downstream service.

Future integration points (deferred)
-------------------------------------
- liked_channels / liked_categories: channel and category preference multipliers
  are now live in recommendation_service via channel_category_multiplier().
- item_type='phrase' / 'grammar_rule': queries are already parameterised;
  add events and SRS cards for those types when ready.
- User-configurable weights: expose ScoringWeights fields in settings_service.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

import asyncpg

from .usage_events_service import most_frequent_unknown_items


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringWeights:
    due:      float = 4.0
    mistake:  float = 3.0
    freq:     float = 2.0
    learning: float = 1.0


DEFAULT_WEIGHTS = ScoringWeights()


@dataclass
class PrioritizedItem:
    item_id:   int
    item_type: str
    score:     float
    signals:   dict[str, float]   # raw signal values — for debugging / future API
    reasons:   list[str]          # human-readable — "review due", "recent mistake", …


# ---------------------------------------------------------------------------
# Pure functions — no DB, fully unit-testable
# ---------------------------------------------------------------------------

def compute_item_score(
    is_due: bool,
    mistake_recency: float,
    freq_rank: float,
    is_learning: bool,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
) -> float:
    """
    Weighted sum of normalised signals. Higher is more urgent.

    is_due          — 1 if a passive SRS card is overdue, 0 otherwise
    mistake_recency — exp(-days_since_last_mistake / 7), decays to ~0 over 30 days
    freq_rank       — linear rank among frequently-seen unknowns (0..1)
    is_learning     — 1 if user has status='learning', 0 otherwise
    """
    return (
        weights.due      * float(is_due)
        + weights.mistake  * mistake_recency
        + weights.freq     * freq_rank
        + weights.learning * float(is_learning)
    )


# Thresholds for human-readable reasons
_REASON_THRESHOLDS: list[tuple[str, float, str]] = [
    # (signal_key, threshold, reason_text)
    ("is_due",          0.5,  "review due"),
    ("mistake_recency", 0.4,  "recent mistake"),     # ≈ mistake within last 7 days
    ("freq_rank",       0.3,  "frequently encountered"),
    ("is_learning",     0.5,  "in study list"),
]


def explain_signals(
    is_due: bool,
    mistake_recency: float,
    freq_rank: float,
    is_learning: bool,
) -> list[str]:
    """
    Pure function. Return human-readable reasons for why an item is prioritised.

    Returns an empty list for a new user with no signals — not an error.
    """
    values = {
        "is_due":          float(is_due),
        "mistake_recency": mistake_recency,
        "freq_rank":       freq_rank,
        "is_learning":     float(is_learning),
    }
    return [
        reason
        for key, threshold, reason in _REASON_THRESHOLDS
        if values[key] >= threshold
    ]


# ---------------------------------------------------------------------------
# DB helpers (private)
# ---------------------------------------------------------------------------

async def _fetch_due_items(
    pool: asyncpg.Pool,
    user_id: str,
    item_type: str,
) -> set[int]:
    """Return item_ids with an overdue passive SRS card (status != 'known')."""
    rows = await pool.fetch(
        """
        SELECT DISTINCT sc.item_id
        FROM srs_cards sc
        JOIN user_word_knowledge uwk
          ON uwk.item_id   = sc.item_id
         AND uwk.item_type = sc.item_type
         AND uwk.user_id   = sc.user_id
        WHERE sc.user_id   = $1::uuid
          AND sc.item_type = $2
          AND sc.direction = 'passive'
          AND sc.due_date  <= NOW()
          AND uwk.status  != 'known'
        LIMIT 200
        """,
        user_id,
        item_type,
    )
    return {r["item_id"] for r in rows}


async def _fetch_recent_mistakes(
    pool: asyncpg.Pool,
    user_id: str,
    item_type: str,
    window_days: int,
) -> dict[int, float]:
    """
    Return item_id → days_since_last_mistake for incorrect events in the window.

    Only the most recent mistake per item is used.  Items with no mistake
    events in the window are absent from the result (treated as 0.0 recency).
    """
    rows = await pool.fetch(
        """
        SELECT
            item_id,
            EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 86400.0 AS days_since
        FROM word_usage_events
        WHERE user_id    = $1::uuid
          AND item_type  = $2
          AND outcome    = 'incorrect'
          AND created_at >= NOW() - ($3 || ' days')::INTERVAL
        GROUP BY item_id
        LIMIT 200
        """,
        user_id,
        item_type,
        str(window_days),
    )
    return {r["item_id"]: float(r["days_since"]) for r in rows}


async def _fetch_learning_items(
    pool: asyncpg.Pool,
    user_id: str,
    item_type: str,
) -> set[int]:
    """Return item_ids with status = 'learning'."""
    rows = await pool.fetch(
        """
        SELECT DISTINCT item_id
        FROM user_word_knowledge
        WHERE user_id   = $1::uuid
          AND item_type = $2
          AND status    = 'learning'
        LIMIT 200
        """,
        user_id,
        item_type,
    )
    return {r["item_id"] for r in rows}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def get_prioritized_items(
    pool: asyncpg.Pool,
    user_id: str,
    item_type: str = "word",
    limit: int = 100,
    mistake_window_days: int = 30,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
) -> list[PrioritizedItem]:
    """
    Return up to `limit` items sorted by priority score, highest first.

    Runs four signal queries concurrently, merges in Python, scores and
    sorts.  Returns an empty list for users with no signals (e.g. new users).

    item_type — only 'word' has signal data today; 'phrase' and
                'grammar_rule' return empty lists until those pipelines fire
                events and SRS cards.
    """
    due_ids, mistakes, freq_rows, learning_ids = await asyncio.gather(
        _fetch_due_items(pool, user_id, item_type),
        _fetch_recent_mistakes(pool, user_id, item_type, mistake_window_days),
        most_frequent_unknown_items(pool, user_id, limit=200),
        _fetch_learning_items(pool, user_id, item_type),
    )

    # Build freq_rank: top item gets 1.0, last gets 1/n.  Filter to item_type.
    freq_ids: list[int] = [
        r["item_id"] for r in freq_rows if r["item_type"] == item_type
    ]
    n_freq = len(freq_ids)
    freq_rank_by_id: dict[int, float] = (
        {item_id: (n_freq - rank) / n_freq for rank, item_id in enumerate(freq_ids)}
        if n_freq > 0
        else {}
    )

    # Union of all signal sets
    all_item_ids: set[int] = (
        due_ids | set(mistakes) | set(freq_rank_by_id) | learning_ids
    )
    if not all_item_ids:
        return []

    results: list[PrioritizedItem] = []
    for item_id in all_item_ids:
        is_due        = item_id in due_ids
        days          = mistakes.get(item_id)
        mistake_recency = math.exp(-days / 7.0) if days is not None else 0.0
        freq_rank     = freq_rank_by_id.get(item_id, 0.0)
        is_learning   = item_id in learning_ids

        score   = compute_item_score(is_due, mistake_recency, freq_rank, is_learning, weights)
        signals = {
            "is_due":          float(is_due),
            "mistake_recency": mistake_recency,
            "freq_rank":       freq_rank,
            "is_learning":     float(is_learning),
        }
        reasons = explain_signals(is_due, mistake_recency, freq_rank, is_learning)

        results.append(PrioritizedItem(
            item_id=item_id,
            item_type=item_type,
            score=score,
            signals=signals,
            reasons=reasons,
        ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:limit]
