"""
Recommendation engine tests.

Unit tests (no DB) — test pure functions:
  score_sentence:
    - higher due_count increases score
    - priority_count adds to score
    - exact target_unknown beats farther unknown_count
    - zero signals produce zero score
  rank_sentences:
    - due items appear before non-due items
    - limit is respected
    - empty candidates → empty result
    - priority_ids empty → priority_count = 0 for all
    - unknown_word_ids absent → priority_count = 0 (no KeyError)
  score_video:
    - higher priority_score increases score
    - shorter duration tiebreaks equal priority_score
    - zero inputs → zero score
  rank_videos:
    - video with highest priority_score ranked first
    - limit is respected
    - empty coverage → empty result
    - covered_item_ids are sorted

Integration tests (real DB):
  - recommend_sentences returns valid shape for a new user
  - all returned sentences have unknown_count in [min_unknown, max_unknown]
  - recommend_sentences respects limit
  - recommend_videos returns no_target_items for a new user
  - recommend_videos returns valid shape when user has learning words
  - target_item_count equals len(prioritized items)

HTTP tests (FastAPI client):
  - GET /api/v1/recommendations/sentences returns 200
  - GET /api/v1/recommendations/sentences requires auth → 403
  - GET /api/v1/recommendations/sentences response shape is correct
  - GET /api/v1/recommendations/videos returns 200
  - GET /api/v1/recommendations/videos requires auth → 403
  - GET /api/v1/recommendations/videos response shape is correct
"""
import uuid

import pytest

from backend.services.recommendation_service import (
    rank_sentences,
    rank_videos,
    recommend_sentences,
    recommend_videos,
    score_sentence,
    score_video,
)


# ---------------------------------------------------------------------------
# Unit tests — pure functions, no DB
# ---------------------------------------------------------------------------

class TestScoreSentence:
    def test_higher_due_count_increases_score(self):
        base = score_sentence(unknown_count=2, due_count=0, priority_count=0, target_unknown=2)
        with_due = score_sentence(unknown_count=2, due_count=1, priority_count=0, target_unknown=2)
        assert with_due > base

    def test_priority_count_adds_to_score(self):
        base = score_sentence(unknown_count=2, due_count=0, priority_count=0, target_unknown=2)
        with_priority = score_sentence(unknown_count=2, due_count=0, priority_count=1, target_unknown=2)
        assert with_priority > base

    def test_exact_target_unknown_beats_farther(self):
        exact = score_sentence(unknown_count=2, due_count=0, priority_count=0, target_unknown=2)
        farther = score_sentence(unknown_count=4, due_count=0, priority_count=0, target_unknown=2)
        assert exact > farther

    def test_zero_signals_produce_zero_score(self):
        assert score_sentence(unknown_count=0, due_count=0, priority_count=0, target_unknown=0) == 0.0

    def test_due_weight_dominates_priority(self):
        # 1 due item (weight 30) > 3 priority items (weight 10 each = 30) only when due_count=1 vs priority_count=3
        # Actually 30 == 30, so let's use due_count=2 vs priority_count=3
        mostly_due = score_sentence(unknown_count=2, due_count=2, priority_count=0, target_unknown=2)
        mostly_priority = score_sentence(unknown_count=2, due_count=0, priority_count=3, target_unknown=2)
        assert mostly_due > mostly_priority  # 60 > 30


class TestRankSentences:
    def _make_candidate(self, sentence_id, unknown_count, due_count, unknown_word_ids=None):
        return {
            "sentence_id": sentence_id,
            "content": f"sentence {sentence_id}",
            "start_time": 0.0,
            "start_time_int": 0,
            "video_id": "vid_A",
            "video_title": "Video A",
            "thumbnail_url": "",
            "language": "de",
            "duration": 300.0,
            "unknown_count": unknown_count,
            "due_count": due_count,
            "unknown_word_ids": unknown_word_ids or [],
        }

    def test_due_items_ranked_first(self):
        candidates = [
            self._make_candidate(1, unknown_count=2, due_count=0),
            self._make_candidate(2, unknown_count=2, due_count=1),
        ]
        ranked = rank_sentences(candidates, target_unknown=2, priority_ids=set(), limit=10)
        assert ranked[0]["sentence_id"] == 2

    def test_limit_respected(self):
        candidates = [self._make_candidate(i, unknown_count=2, due_count=0) for i in range(20)]
        ranked = rank_sentences(candidates, target_unknown=2, priority_ids=set(), limit=5)
        assert len(ranked) == 5

    def test_empty_candidates_returns_empty(self):
        assert rank_sentences([], target_unknown=2, priority_ids=set(), limit=10) == []

    def test_empty_priority_ids_sets_priority_count_zero(self):
        candidates = [self._make_candidate(1, unknown_count=2, due_count=0, unknown_word_ids=[10, 20])]
        ranked = rank_sentences(candidates, target_unknown=2, priority_ids=set(), limit=10)
        assert ranked[0]["priority_count"] == 0

    def test_priority_ids_counted_correctly(self):
        candidates = [self._make_candidate(1, unknown_count=3, due_count=0, unknown_word_ids=[10, 20, 30])]
        ranked = rank_sentences(candidates, target_unknown=3, priority_ids={10, 30}, limit=10)
        assert ranked[0]["priority_count"] == 2

    def test_missing_unknown_word_ids_key_is_safe(self):
        candidate = {
            "sentence_id": 1,
            "content": "test",
            "start_time": 0.0,
            "start_time_int": 0,
            "video_id": "v",
            "video_title": "V",
            "thumbnail_url": "",
            "language": "de",
            "duration": 100.0,
            "unknown_count": 2,
            "due_count": 0,
            # unknown_word_ids intentionally absent
        }
        ranked = rank_sentences([candidate], target_unknown=2, priority_ids={1, 2}, limit=10)
        assert ranked[0]["priority_count"] == 0

    def test_score_field_present(self):
        candidates = [self._make_candidate(1, unknown_count=2, due_count=1)]
        ranked = rank_sentences(candidates, target_unknown=2, priority_ids=set(), limit=10)
        assert "score" in ranked[0]
        assert isinstance(ranked[0]["score"], (int, float))


class TestScoreVideo:
    def test_higher_priority_score_increases_score(self):
        high = score_video(priority_score=10.0, duration=300.0)
        low  = score_video(priority_score=2.0,  duration=300.0)
        assert high > low

    def test_shorter_duration_tiebreaks_equal_priority(self):
        short = score_video(priority_score=5.0, duration=100.0)
        long_ = score_video(priority_score=5.0, duration=1000.0)
        assert short > long_

    def test_zero_inputs_returns_zero(self):
        assert score_video(priority_score=0.0, duration=0.0) == 0.0


def _make_meta(video_id: str, duration: float = 300.0) -> dict:
    return {
        "title": video_id, "thumbnail_url": "", "language": "de",
        "duration": duration, "best_start_time": 0.0,
        "best_content": "", "best_sentence_id": 1,
    }


class TestRankVideos:
    def test_higher_priority_video_ranked_first(self):
        # vid_high covers items with scores 4.0 each; vid_low covers items 1.0 each
        coverage = {"vid_high": {1, 2}, "vid_low": {3, 4}}
        meta = {"vid_high": _make_meta("vid_high"), "vid_low": _make_meta("vid_low")}
        score_by_id = {1: 4.0, 2: 4.0, 3: 1.0, 4: 1.0}
        ranked = rank_videos(coverage, meta, score_by_id, limit=10)
        assert ranked[0]["video_id"] == "vid_high"

    def test_limit_respected(self):
        coverage = {f"vid_{i}": {i} for i in range(10)}
        meta = {f"vid_{i}": _make_meta(f"vid_{i}") for i in range(10)}
        score_by_id = {i: float(i + 1) for i in range(10)}
        ranked = rank_videos(coverage, meta, score_by_id, limit=3)
        assert len(ranked) == 3

    def test_empty_coverage_returns_empty(self):
        ranked = rank_videos({}, {}, score_by_id={1: 4.0, 2: 1.0}, limit=10)
        assert ranked == []

    def test_covered_item_ids_are_sorted(self):
        coverage = {"vid_A": {5, 1, 3}}
        meta = {"vid_A": _make_meta("vid_A")}
        ranked = rank_videos(coverage, meta, score_by_id={1: 4.0, 3: 4.0, 5: 4.0}, limit=10)
        assert ranked[0]["covered_item_ids"] == [1, 3, 5]

    def test_priority_score_field_present(self):
        coverage = {"vid_A": {1}}
        meta = {"vid_A": _make_meta("vid_A")}
        ranked = rank_videos(coverage, meta, score_by_id={1: 3.5}, limit=10)
        assert "priority_score" in ranked[0]
        assert ranked[0]["priority_score"] == pytest.approx(3.5)

    def test_score_field_present(self):
        coverage = {"vid_A": {1}}
        meta = {"vid_A": _make_meta("vid_A")}
        ranked = rank_videos(coverage, meta, score_by_id={1: 4.0}, limit=10)
        assert "score" in ranked[0]

    def test_item_not_in_score_by_id_contributes_zero(self):
        # vid_A covers item 1 (score 4.0) and item 99 (not in score_by_id)
        coverage = {"vid_A": {1, 99}}
        meta = {"vid_A": _make_meta("vid_A")}
        ranked = rank_videos(coverage, meta, score_by_id={1: 4.0}, limit=10)
        # covered_item_ids only includes items that are targets
        assert ranked[0]["covered_item_ids"] == [1]
        assert ranked[0]["covered_count"] == 1


# ---------------------------------------------------------------------------
# Integration tests — real DB
# ---------------------------------------------------------------------------

async def _any_language(pool) -> str:
    """Return any language present in the video table."""
    row = await pool.fetchrow("SELECT language FROM video LIMIT 1")
    if row is None:
        pytest.skip("No videos in DB — run the subtitle pipeline first")
    return row["language"]


async def _create_user(pool) -> str:
    """Insert a fresh test user and return its user_id string."""
    row = await pool.fetchrow(
        """
        INSERT INTO users (email, password_hash)
        VALUES ($1, 'x')
        RETURNING user_id
        """,
        f"test+{uuid.uuid4().hex[:12]}@example.com",
    )
    return str(row["user_id"])


async def test_recommend_sentences_new_user_valid_shape(db_pool):
    language = await _any_language(db_pool)
    user_id = await _create_user(db_pool)

    result = await recommend_sentences(
        db_pool, user_id=user_id, language=language,
        limit=5, target_unknown=2, min_unknown=0, max_unknown=10,
    )

    assert "sentences" in result
    assert "target_unknown" in result
    assert "total" in result
    assert isinstance(result["sentences"], list)
    assert result["target_unknown"] == 2
    assert result["total"] == len(result["sentences"])


async def test_recommend_sentences_unknown_count_within_range(db_pool):
    language = await _any_language(db_pool)
    user_id = await _create_user(db_pool)

    result = await recommend_sentences(
        db_pool, user_id=user_id, language=language,
        limit=20, target_unknown=2, min_unknown=1, max_unknown=3,
    )

    for s in result["sentences"]:
        assert 1 <= s["unknown_count"] <= 3, (
            f"sentence {s['sentence_id']} has unknown_count={s['unknown_count']}, "
            f"expected between 1 and 3"
        )


async def test_recommend_sentences_respects_limit(db_pool):
    language = await _any_language(db_pool)
    user_id = await _create_user(db_pool)

    result = await recommend_sentences(
        db_pool, user_id=user_id, language=language,
        limit=3, target_unknown=2, min_unknown=0, max_unknown=15,
    )

    assert len(result["sentences"]) <= 3


async def test_recommend_sentences_each_item_has_required_fields(db_pool):
    language = await _any_language(db_pool)
    user_id = await _create_user(db_pool)

    result = await recommend_sentences(
        db_pool, user_id=user_id, language=language,
        limit=5, target_unknown=2, min_unknown=0, max_unknown=10,
    )

    for s in result["sentences"]:
        for field in ("sentence_id", "content", "video_id", "unknown_count",
                      "due_count", "priority_count", "score"):
            assert field in s, f"missing field {field!r} in sentence result"


async def test_recommend_videos_no_target_items_for_new_user(db_pool):
    language = await _any_language(db_pool)
    user_id = await _create_user(db_pool)

    result = await recommend_videos(db_pool, user_id=user_id, language=language, limit=5)

    assert result["videos"] == []
    assert result["target_item_count"] == 0
    assert result["reason"] == "no_target_items"


async def test_recommend_videos_valid_shape_with_learning_words(db_pool):
    language = await _any_language(db_pool)
    user_id = await _create_user(db_pool)

    # Give the user some learning words (word_ids that actually exist)
    word_rows = await db_pool.fetch(
        """
        SELECT DISTINCT wts.word_id
        FROM word_to_sentence wts
        JOIN sentence s ON s.sentence_id = wts.sentence_id
        JOIN video v    ON v.video_id = s.video_id
        WHERE v.language = $1
        LIMIT 5
        """,
        language,
    )
    if not word_rows:
        pytest.skip("No word_to_sentence data for this language")

    for row in word_rows:
        await db_pool.execute(
            """
            INSERT INTO user_word_knowledge (user_id, item_id, item_type, status)
            VALUES ($1::uuid, $2, 'word', 'learning')
            ON CONFLICT DO NOTHING
            """,
            user_id, row["word_id"],
        )

    result = await recommend_videos(db_pool, user_id=user_id, language=language, limit=5)

    assert isinstance(result["videos"], list)
    assert result["target_item_count"] >= 1
    for v in result["videos"]:
        assert v["covered_count"] >= 1
        assert "priority_score" in v
        assert "score" in v


async def test_recommend_videos_target_item_count_matches_db(db_pool):
    language = await _any_language(db_pool)
    user_id = await _create_user(db_pool)

    word_rows = await db_pool.fetch(
        """
        SELECT DISTINCT wts.word_id
        FROM word_to_sentence wts
        JOIN sentence s ON s.sentence_id = wts.sentence_id
        JOIN video v    ON v.video_id = s.video_id
        WHERE v.language = $1
        LIMIT 4
        """,
        language,
    )
    if not word_rows:
        pytest.skip("No word_to_sentence data for this language")

    word_ids = [r["word_id"] for r in word_rows]
    for wid in word_ids:
        await db_pool.execute(
            """
            INSERT INTO user_word_knowledge (user_id, item_id, item_type, status)
            VALUES ($1::uuid, $2, 'word', 'learning')
            ON CONFLICT DO NOTHING
            """,
            user_id, wid,
        )

    result = await recommend_videos(db_pool, user_id=user_id, language=language, limit=10)
    assert result["target_item_count"] == len(word_ids)


# ---------------------------------------------------------------------------
# HTTP tests — FastAPI client
# ---------------------------------------------------------------------------

async def _auth_token(client) -> str:
    email = f"test+{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return resp.json()["access_token"]


async def _language_param(db_pool) -> str:
    row = await db_pool.fetchrow("SELECT language FROM video LIMIT 1")
    if row is None:
        pytest.skip("No videos in DB")
    return row["language"]


async def test_sentences_endpoint_returns_200(client, db_pool):
    token = await _auth_token(client)
    language = await _language_param(db_pool)

    resp = await client.get(
        "/api/v1/recommendations/sentences",
        params={"language": language},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


async def test_sentences_endpoint_requires_auth(client, db_pool):
    language = await _language_param(db_pool)
    resp = await client.get(
        "/api/v1/recommendations/sentences",
        params={"language": language},
    )
    assert resp.status_code == 403


async def test_sentences_response_shape(client, db_pool):
    token = await _auth_token(client)
    language = await _language_param(db_pool)

    resp = await client.get(
        "/api/v1/recommendations/sentences",
        params={"language": language, "limit": 5, "target_unknown": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()

    assert "sentences" in body
    assert "target_unknown" in body
    assert "total" in body
    assert body["target_unknown"] == 2
    assert isinstance(body["sentences"], list)

    for s in body["sentences"]:
        for field in ("sentence_id", "content", "video_id", "video_title",
                      "start_time", "unknown_count", "due_count",
                      "priority_count", "score"):
            assert field in s, f"missing field {field!r}"


async def test_videos_endpoint_returns_200(client, db_pool):
    token = await _auth_token(client)
    language = await _language_param(db_pool)

    resp = await client.get(
        "/api/v1/recommendations/videos",
        params={"language": language},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


async def test_videos_endpoint_requires_auth(client, db_pool):
    language = await _language_param(db_pool)
    resp = await client.get(
        "/api/v1/recommendations/videos",
        params={"language": language},
    )
    assert resp.status_code == 403


async def test_videos_response_shape(client, db_pool):
    token = await _auth_token(client)
    language = await _language_param(db_pool)

    resp = await client.get(
        "/api/v1/recommendations/videos",
        params={"language": language, "limit": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()

    assert "videos" in body
    assert "target_item_count" in body
    assert "reason" in body

    for v in body["videos"]:
        for field in ("video_id", "title", "thumbnail_url", "language",
                      "duration", "start_time", "priority_score",
                      "covered_item_ids", "covered_count", "score"):
            assert field in v, f"missing field {field!r}"


async def test_videos_new_user_returns_no_target_items(client, db_pool):
    token = await _auth_token(client)
    language = await _language_param(db_pool)

    resp = await client.get(
        "/api/v1/recommendations/videos",
        params={"language": language},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()

    assert resp.status_code == 200
    assert body["videos"] == []
    assert body["reason"] == "no_target_items"
    assert body["target_item_count"] == 0
