"""
Runtime-aligned port of the load-bearing learning-loop invariants
(W4 / #17 batch 1).

Two tiny but critical tests:

1. `KnowledgeStore` i+1 dedup invariant — a second exposure to the same
   `content_id` must be REJECTED so a user re-watching the same episode
   can't grind their way to mastery without seeing new context.
2. `VocabularyOnboarding` tier monotonicity — B1 must be a strict superset
   of A2 (and A2 of A1). The whole onboarding UX assumes this.

Targets RUNTIME modules `word_knowledge.py` + `onboarding.py`. NOT the
orphan refactor at `src/app/learning/`.

Ported nodeids (src/app suite):
  tests/learning/test_word_knowledge.py::TestContentDeduplication::test_second_exposure_same_content_is_rejected
  tests/learning/test_onboarding.py::TestGetTierLemmas::test_b1_is_superset_of_a2
"""
from datetime import datetime, timedelta, timezone

import pytest

from onboarding import LevelTier, VocabularyOnboarding
from word_knowledge import EvidenceConfig, KnowledgeStore


def _ts(day: int, hour: int = 12) -> datetime:
    return datetime(2024, 3, day, hour, 0, tzinfo=timezone.utc)


def _tight_config() -> EvidenceConfig:
    """Same shape the orphan test used — short gaps so the timestamp gate
    doesn't accidentally reject the second event for time-spacing reasons
    instead of content-dedup reasons. Locks the gap reasons separately."""
    return EvidenceConfig(
        passive_min_gap=timedelta(hours=12),
        active_min_gap=timedelta(hours=24),
        familiar_threshold=2,
        passive_threshold=5,
        active_threshold=3,
    )


@pytest.fixture
def store() -> KnowledgeStore:
    return KnowledgeStore(config=_tight_config())


USER = "u1"
WORD = "anfangen"


class TestContentDeduplication:
    """The single most load-bearing learning invariant: same content_id is
    counted at most once per (user, word). Without this, re-watching the
    same video would let users 'mass' their way to mastery."""

    def test_second_exposure_same_content_is_rejected(self, store):
        store.record_passive_evidence(USER, WORD, _ts(1), content_id="ep01")
        accepted = store.record_passive_evidence(USER, WORD, _ts(3), content_id="ep01")
        assert accepted is False


class TestOnboardingTierMonotonicity:
    """A2 ⊂ B1 (strict). The seeding UX promises 'pick your level and we'll
    mark everything at or below it as known' — that promise only holds if
    each tier is a strict superset of the previous."""

    def test_b1_is_superset_of_a2(self):
        a2 = VocabularyOnboarding.get_tier_lemmas(LevelTier.A2)
        b1 = VocabularyOnboarding.get_tier_lemmas(LevelTier.B1)
        assert a2 < b1  # strict subset
