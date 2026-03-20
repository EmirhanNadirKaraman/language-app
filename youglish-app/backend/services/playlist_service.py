"""
Playlist generation: find a minimal set of videos that collectively cover
a given list of target vocabulary items.

Architecture
------------
Two clean layers:

  1. Pure functions (no DB, fully unit-testable):
       greedy_cover(coverage, targets, max_videos, video_durations)
       compute_coverage_stats(selected_ids, coverage, targets)

  2. Async DB + orchestration:
       _fetch_coverage(pool, item_ids, language)
       generate_playlist(pool, item_ids, item_type, language, max_videos, optimizer)

ILP interface (deferred, no changes needed to call site)
---------------------------------------------------------
Any optimizer that follows the same signature as greedy_cover can be passed
as the `optimizer` argument to generate_playlist:

    def ilp_cover(
        coverage: dict[str, set[int]],
        targets: set[int],
        max_videos: int,
        video_durations: dict[str, float] | None = None,
    ) -> list[str]:
        # Requires: pip install pulp
        # Variables: x[v] ∈ {0,1}; Minimize sum(x); cover all targets
        ...

Phrase support (deferred)
-------------------------
_fetch_coverage currently handles item_type='word' only.  Adding 'phrase'
requires a JOIN through sentence_to_phrase instead of word_to_sentence, but
the rest of the pipeline (greedy_cover, compute_coverage_stats, _build_result)
is item-type-agnostic.
"""
from __future__ import annotations

import math

import asyncpg


# ---------------------------------------------------------------------------
# Pure algorithm — no DB, fully unit-testable
# ---------------------------------------------------------------------------

def greedy_cover(
    coverage: dict[str, set[int]],
    targets: set[int],
    max_videos: int,
    video_durations: dict[str, float] | None = None,
) -> list[str]:
    """
    Greedy set cover over vocabulary items.

    Each round: pick the video that covers the most *uncovered* targets.
    Tiebreak: prefer shorter videos (lower duration).
    Stop when all targets are covered, max_videos is reached, or no remaining
    video adds new coverage.

    Args:
        coverage:        video_id → set of item_ids covered by that video
        targets:         item_ids to cover
        max_videos:      hard cap on playlist length
        video_durations: optional video_id → duration (seconds) for tiebreaking

    Returns:
        List of video_ids in selection order (first = best value).
    """
    if not targets or not coverage:
        return []

    durations = video_durations or {}
    uncovered = set(targets)
    remaining = dict(coverage)   # shallow copy — we remove selected videos
    selected: list[str] = []

    while uncovered and remaining and len(selected) < max_videos:
        best_vid = max(
            remaining,
            key=lambda vid: (
                len(remaining[vid] & uncovered),      # more coverage → better
                -durations.get(vid, 0.0),             # shorter → better (less negative)
            ),
        )
        new_items = remaining[best_vid] & uncovered
        if not new_items:
            break   # no remaining video covers anything new

        selected.append(best_vid)
        uncovered -= new_items
        del remaining[best_vid]

    return selected


def compute_coverage_stats(
    selected_video_ids: list[str],
    coverage: dict[str, set[int]],
    targets: set[int],
) -> dict:
    """
    Compute aggregate coverage statistics.

    Returns a dict with:
        target_count      — total targets requested
        covered_count     — targets covered by at least one selected video
        coverage_pct      — float 0–100, one decimal place
        uncovered_item_ids — sorted list of item_ids not covered
        video_count       — number of videos selected
    """
    if not targets:
        return {
            "target_count": 0,
            "covered_count": 0,
            "coverage_pct": 0.0,
            "uncovered_item_ids": [],
            "video_count": len(selected_video_ids),
        }

    covered: set[int] = set()
    for vid in selected_video_ids:
        if vid in coverage:
            covered |= coverage[vid] & targets

    uncovered = targets - covered
    return {
        "target_count": len(targets),
        "covered_count": len(covered),
        "coverage_pct": round(100.0 * len(covered) / len(targets), 1),
        "uncovered_item_ids": sorted(uncovered),
        "video_count": len(selected_video_ids),
    }


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------

async def _fetch_coverage(
    pool: asyncpg.Pool,
    item_ids: list[int],
    language: str,
) -> tuple[dict[str, set[int]], dict[str, dict]]:
    """
    Query the DB for all videos that contain at least one of the target words.

    Returns:
        coverage   — video_id → set of item_ids (word_ids) covered
        video_meta — video_id → {title, thumbnail_url, language, duration,
                                   best_start_time, best_content, best_sentence_id}

    The 'best' sentence for each video is the earliest occurrence of any
    target word, used as the playlist entry point.

    Future: to support item_type='phrase', replace word_to_sentence with
    sentence_to_phrase JOIN phrase_blueprint and filter by blueprint_id.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (v.video_id, wts.word_id)
            v.video_id,
            v.title,
            v.thumbnail_url,
            v.language,
            v.duration,
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
                "title": row["title"],
                "thumbnail_url": row["thumbnail_url"],
                "language": row["language"],
                "duration": float(row["duration"] or 0),
                "best_start_time": float(row["start_time"]),
                "best_content": row["content"],
                "best_sentence_id": row["sentence_id"],
            }
        else:
            # Keep the earliest sentence across all matched words in this video
            if float(row["start_time"]) < video_meta[vid]["best_start_time"]:
                video_meta[vid]["best_start_time"] = float(row["start_time"])
                video_meta[vid]["best_content"] = row["content"]
                video_meta[vid]["best_sentence_id"] = row["sentence_id"]

        coverage[vid].add(wid)

    return coverage, video_meta


def _build_result(
    selected_video_ids: list[str],
    coverage: dict[str, set[int]],
    video_meta: dict[str, dict],
    targets: set[int],
) -> dict:
    """Assemble the final response dict from selected video_ids."""
    videos = []
    for vid in selected_video_ids:
        meta = video_meta[vid]
        vid_covered = sorted(coverage[vid] & targets)
        videos.append({
            "video_id": vid,
            "title": meta["title"],
            "thumbnail_url": meta["thumbnail_url"],
            "language": meta["language"],
            "start_time": meta["best_start_time"],
            "start_time_int": math.floor(meta["best_start_time"]),
            "content": meta["best_content"],
            "covered_item_ids": vid_covered,
            "covered_count": len(vid_covered),
        })

    stats = compute_coverage_stats(selected_video_ids, coverage, targets)
    return {"videos": videos, "coverage": stats}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def generate_playlist(
    pool: asyncpg.Pool,
    item_ids: list[int],
    item_type: str,
    language: str,
    max_videos: int,
    optimizer=greedy_cover,
) -> dict:
    """
    Generate a playlist covering *item_ids* using the given optimizer.

    optimizer — any function matching greedy_cover's signature.
                Defaults to greedy_cover.  Pass ilp_cover for optimal results
                once that is implemented.

    Raises ValueError for unsupported item_type values.
    """
    if item_type != "word":
        raise ValueError(
            f"item_type {item_type!r} is not yet supported. Only 'word' is implemented."
        )

    targets = set(item_ids)
    coverage, video_meta = await _fetch_coverage(pool, item_ids, language)

    if not coverage:
        return _build_result([], {}, {}, targets)

    durations = {vid: meta["duration"] for vid, meta in video_meta.items()}
    selected_ids = optimizer(coverage, targets, max_videos, durations)
    return _build_result(selected_ids, coverage, video_meta, targets)
