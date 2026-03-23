"""
test_exposure_integration.py
----------------------------
Integration tests for ExposureService — the orchestrator that keeps
QualifiedExposureCounter and UserKnowledgeStore in sync.

Regression being prevented
--------------------------
Before the ExposureService refactor, QualifiedExposureCounter.record() and
UserKnowledgeStore.record_exposure() were two independent call sites with no
shared write path.  This produced two concrete failure modes:

  1. Duplicate-replay inflation
     A caller that forgot to check the counter first could replay the same
     subtitle clip multiple times and advance the store's knowledge state on
     every replay.  A user who sought back five times within one sitting would
     unlock a word that they had genuinely seen only once.

  2. Silent count divergence
     A caller that called one component but not the other left the two counters
     out of sync with no error or warning.  Any later code comparing
     counter.get_raw_count() against store.exposure_count would produce
     inconsistent results, making it impossible to trust either number.

All tests here verify that ExposureService.record_qualified_exposure() is the
single correct write point and that the invariant

    counter.get_raw_count(user_id, unit)
        == store.get_knowledge(user_id, unit).exposure_count

holds after every accepted call.
"""
import pytest

from exposure_counter import CountingPolicy, DuplicateRule, QualifiedExposureCounter
from exposure_service import ExposureService
from learning_units import LearningUnit, LearningUnitType
from user_knowledge import ExposurePolicy, KnowledgeState, UserKnowledgeStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER = "alice"
OTHER_USER = "bob"


def lemma(key: str) -> LearningUnit:
    return LearningUnit(LearningUnitType.LEMMA, key, key)


def utt(n: int) -> str:
    """Generate a distinct utterance ID for each exposure in a sequence."""
    return f"utt:sentence-{n}"


def _assert_invariant(
    service: ExposureService,
    user_id: str,
    unit: LearningUnit,
    expected_count: int,
) -> None:
    """Assert the core invariant: counter and store show the same count."""
    raw = service.counter.get_raw_count(user_id, unit)
    stored = service.store.get_knowledge(user_id, unit).exposure_count
    assert raw == expected_count, f"counter raw_count: expected {expected_count}, got {raw}"
    assert stored == expected_count, f"store exposure_count: expected {expected_count}, got {stored}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def target() -> LearningUnit:
    return lemma("schön")


@pytest.fixture
def store() -> UserKnowledgeStore:
    """Bare store with default policy (exposures_to_unlock=5)."""
    return UserKnowledgeStore()


@pytest.fixture
def fast_store() -> UserKnowledgeStore:
    """Store with a low threshold so progression tests stay short."""
    return UserKnowledgeStore(exposure_policy=ExposurePolicy(exposures_to_unlock=3))


@pytest.fixture
def counter() -> QualifiedExposureCounter:
    """Default counter: DEDUPLICATE_UTTERANCE."""
    return QualifiedExposureCounter()


@pytest.fixture
def service(counter: QualifiedExposureCounter, store: UserKnowledgeStore) -> ExposureService:
    return ExposureService(counter, store)


@pytest.fixture
def fast_service(fast_store: UserKnowledgeStore) -> ExposureService:
    """Service wired to fast_store for threshold-focused tests."""
    return ExposureService(QualifiedExposureCounter(), fast_store)


# ---------------------------------------------------------------------------
# TestSingleExposure
# ---------------------------------------------------------------------------

class TestSingleExposure:
    """
    The most basic contract: a single accepted call updates everything
    consistently and returns a well-formed ExposureEvent.
    """

    def test_returns_event_with_correct_fields(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        event = service.record_qualified_exposure(USER, target, utt(1))

        assert event is not None
        assert event.user_id == USER
        assert event.unit == target
        assert event.utterance_id == utt(1)
        assert event.weight == pytest.approx(1.0)

    def test_state_advances_from_unseen_to_exposed(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        assert service.store.get_state(USER, target) == KnowledgeState.UNSEEN

        service.record_qualified_exposure(USER, target, utt(1))

        assert service.store.get_state(USER, target) == KnowledgeState.EXPOSED

    def test_counter_and_store_both_show_count_one(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        service.record_qualified_exposure(USER, target, utt(1))

        _assert_invariant(service, USER, target, expected_count=1)

    def test_last_exposed_at_is_set_after_first_exposure(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        service.record_qualified_exposure(USER, target, utt(1))

        record = service.store.get_knowledge(USER, target)
        assert record.last_exposed_at is not None

    def test_unrelated_unit_is_unaffected(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        other = lemma("fantastisch")
        service.record_qualified_exposure(USER, target, utt(1))

        assert service.counter.get_raw_count(USER, other) == 0
        assert service.store.get_knowledge(USER, other).exposure_count == 0
        assert service.store.get_state(USER, other) == KnowledgeState.UNSEEN


# ---------------------------------------------------------------------------
# TestStateProgression
# ---------------------------------------------------------------------------

class TestStateProgression:
    """
    Exposure count drives state transitions according to ExposurePolicy.
    Tests use fast_service (exposures_to_unlock=3) to keep fixtures short.
    """

    def test_state_stays_exposed_below_threshold(
        self, fast_service: ExposureService, target: LearningUnit
    ) -> None:
        for i in range(2):  # 2 < threshold of 3
            fast_service.record_qualified_exposure(USER, target, utt(i))

        assert fast_service.store.get_state(USER, target) == KnowledgeState.EXPOSED

    def test_state_advances_to_unlocked_at_threshold(
        self, fast_service: ExposureService, target: LearningUnit
    ) -> None:
        for i in range(3):  # exactly at threshold
            fast_service.record_qualified_exposure(USER, target, utt(i))

        assert fast_service.store.get_state(USER, target) == KnowledgeState.UNLOCKED

    def test_exposures_beyond_threshold_do_not_advance_state_further(
        self, fast_service: ExposureService, target: LearningUnit
    ) -> None:
        for i in range(6):  # well past threshold
            fast_service.record_qualified_exposure(USER, target, utt(i))

        # record_exposure() only handles UNSEEN→EXPOSED and EXPOSED→UNLOCKED;
        # advancing past UNLOCKED belongs to the SRS review module.
        assert fast_service.store.get_state(USER, target) == KnowledgeState.UNLOCKED

    def test_counter_and_store_counts_agree_at_each_step(
        self, fast_service: ExposureService, target: LearningUnit
    ) -> None:
        for i in range(5):
            fast_service.record_qualified_exposure(USER, target, utt(i))
            _assert_invariant(fast_service, USER, target, expected_count=i + 1)

    def test_custom_threshold_two_exposures_to_unlock(
        self, target: LearningUnit
    ) -> None:
        quick_store = UserKnowledgeStore(
            exposure_policy=ExposurePolicy(exposures_to_unlock=2)
        )
        svc = ExposureService(QualifiedExposureCounter(), quick_store)

        svc.record_qualified_exposure(USER, target, utt(1))
        assert quick_store.get_state(USER, target) == KnowledgeState.EXPOSED

        svc.record_qualified_exposure(USER, target, utt(2))
        assert quick_store.get_state(USER, target) == KnowledgeState.UNLOCKED


# ---------------------------------------------------------------------------
# TestDeduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    """
    The counter's duplicate policy gates whether the store is updated.
    These tests verify that the service correctly forwards the counter's
    accept/reject decision to the store.
    """

    def test_same_utterance_id_rejected_on_second_call(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        first = service.record_qualified_exposure(USER, target, utt(1))
        second = service.record_qualified_exposure(USER, target, utt(1))

        assert first is not None
        assert second is None

    def test_store_not_updated_when_counter_rejects_duplicate(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        service.record_qualified_exposure(USER, target, utt(1))
        service.record_qualified_exposure(USER, target, utt(1))  # rejected

        # Both components must agree at count=1, not 2
        _assert_invariant(service, USER, target, expected_count=1)

    def test_two_distinct_utterance_ids_both_accepted(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        e1 = service.record_qualified_exposure(USER, target, utt(1))
        e2 = service.record_qualified_exposure(USER, target, utt(2))

        assert e1 is not None
        assert e2 is not None
        _assert_invariant(service, USER, target, expected_count=2)

    def test_allow_all_policy_accepts_same_utterance_multiple_times(
        self, store: UserKnowledgeStore, target: LearningUnit
    ) -> None:
        allow_all_counter = QualifiedExposureCounter(
            CountingPolicy(duplicate_rule=DuplicateRule.ALLOW_ALL)
        )
        svc = ExposureService(allow_all_counter, store)

        for _ in range(3):
            svc.record_qualified_exposure(USER, target, utt(1))

        _assert_invariant(svc, USER, target, expected_count=3)

    def test_deduplicate_session_allows_same_utterance_in_new_session(
        self, target: LearningUnit
    ) -> None:
        session_store = UserKnowledgeStore()
        session_counter = QualifiedExposureCounter(
            CountingPolicy(duplicate_rule=DuplicateRule.DEDUPLICATE_SESSION)
        )
        svc = ExposureService(session_counter, session_store)

        e1 = svc.record_qualified_exposure(
            USER, target, utt(1), session_id="ep1-week-01"
        )
        e2 = svc.record_qualified_exposure(
            USER, target, utt(1), session_id="ep1-week-01"  # dup in same session
        )
        e3 = svc.record_qualified_exposure(
            USER, target, utt(1), session_id="ep1-week-02"  # new session → accepted
        )

        assert e1 is not None
        assert e2 is None   # rejected: same session + same utterance
        assert e3 is not None
        _assert_invariant(svc, USER, target, expected_count=2)

    def test_diminishing_returns_accepts_repeats_with_decaying_weight(
        self, store: UserKnowledgeStore, target: LearningUnit
    ) -> None:
        dr_counter = QualifiedExposureCounter(
            CountingPolicy(
                duplicate_rule=DuplicateRule.DIMINISHING_RETURNS,
                diminishing_decay=0.5,
            )
        )
        svc = ExposureService(dr_counter, store)

        e1 = svc.record_qualified_exposure(USER, target, utt(1))
        e2 = svc.record_qualified_exposure(USER, target, utt(1))

        assert e1 is not None and e1.weight == pytest.approx(1.0)
        assert e2 is not None and e2.weight == pytest.approx(0.5)
        # Both were accepted → store incremented twice
        _assert_invariant(svc, USER, target, expected_count=2)


# ---------------------------------------------------------------------------
# TestAlreadyKnownTarget
# ---------------------------------------------------------------------------

class TestAlreadyKnownTarget:
    """
    States above UNLOCKED are managed by the SRS review module, not by
    ExposurePolicy.  Exposures recorded via the service must not accidentally
    trigger state regressions or re-advances beyond what the policy allows.
    """

    def test_exposure_on_known_passive_unit_increments_count_but_leaves_state(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        service.store.set_state(USER, target, KnowledgeState.KNOWN_PASSIVE)

        service.record_qualified_exposure(USER, target, utt(1))

        assert service.store.get_state(USER, target) == KnowledgeState.KNOWN_PASSIVE
        # Count still increments — the service doesn't suppress it
        _assert_invariant(service, USER, target, expected_count=1)

    def test_exposure_on_mastered_unit_leaves_state_unchanged(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        service.store.set_state(USER, target, KnowledgeState.MASTERED)

        service.record_qualified_exposure(USER, target, utt(1))

        assert service.store.get_state(USER, target) == KnowledgeState.MASTERED

    def test_auto_advance_disabled_records_exposure_without_state_change(
        self, target: LearningUnit
    ) -> None:
        no_advance_store = UserKnowledgeStore(
            exposure_policy=ExposurePolicy(auto_advance=False)
        )
        svc = ExposureService(QualifiedExposureCounter(), no_advance_store)

        svc.record_qualified_exposure(USER, target, utt(1))

        assert no_advance_store.get_state(USER, target) == KnowledgeState.UNSEEN
        assert no_advance_store.get_knowledge(USER, target).exposure_count == 1

    def test_onboarding_seed_state_not_overwritten_by_exposure(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        # Units seeded at KNOWN_PASSIVE represent words the user already knows.
        # An accidental exposure should not demote them.
        service.store.set_state(USER, target, KnowledgeState.KNOWN_PASSIVE)
        state_before = service.store.get_state(USER, target)

        service.record_qualified_exposure(USER, target, utt(1))

        assert service.store.get_state(USER, target) == state_before


# ---------------------------------------------------------------------------
# TestCounterStoreInvariant
# ---------------------------------------------------------------------------

class TestCounterStoreInvariant:
    """
    Systematic checks that counter.get_raw_count == store.exposure_count
    holds in every scenario the service is likely to encounter in production.
    """

    def test_invariant_holds_after_mix_of_accepted_and_rejected(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        service.record_qualified_exposure(USER, target, utt(1))  # accepted
        service.record_qualified_exposure(USER, target, utt(1))  # rejected (dup)
        service.record_qualified_exposure(USER, target, utt(2))  # accepted
        service.record_qualified_exposure(USER, target, utt(1))  # rejected (dup)
        service.record_qualified_exposure(USER, target, utt(3))  # accepted

        _assert_invariant(service, USER, target, expected_count=3)

    def test_invariant_holds_independently_per_user(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        service.record_qualified_exposure(USER, target, utt(1))
        service.record_qualified_exposure(USER, target, utt(2))
        service.record_qualified_exposure(OTHER_USER, target, utt(1))

        _assert_invariant(service, USER, target, expected_count=2)
        _assert_invariant(service, OTHER_USER, target, expected_count=1)

    def test_invariant_holds_across_multiple_units(
        self, service: ExposureService
    ) -> None:
        units = [lemma(k) for k in ("schön", "wunderbar", "interessant")]
        counts = [4, 2, 7]

        for unit, n in zip(units, counts):
            for i in range(n):
                service.record_qualified_exposure(USER, unit, f"utt:{unit.key}-{i}")

        for unit, expected in zip(units, counts):
            _assert_invariant(service, USER, unit, expected_count=expected)

    def test_invariant_holds_after_service_reset(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        for i in range(3):
            service.record_qualified_exposure(USER, target, utt(i))
        _assert_invariant(service, USER, target, expected_count=3)

        service.reset_user(USER)
        _assert_invariant(service, USER, target, expected_count=0)

    def test_bypassing_service_breaks_invariant(
        self, service: ExposureService, target: LearningUnit
    ) -> None:
        """
        Demonstrates the original bug: calling store.record_exposure() directly
        increments the store's count without going through the counter's
        deduplication check, so the two components diverge.

        This test documents the failure mode that ExposureService prevents.
        """
        service.record_qualified_exposure(USER, target, utt(1))  # count: 1

        # Bypassing the service: the counter rejects the duplicate, but the
        # store doesn't know that and increments anyway.
        rejected = service.counter.record(USER, target, utt(1))  # returns None (dup)
        assert rejected is None

        # A caller that ignores the return value and calls the store anyway
        # creates the divergence.
        service.store.record_exposure(USER, target)  # increments store to 2

        counter_count = service.counter.get_raw_count(USER, target)
        store_count = service.store.get_knowledge(USER, target).exposure_count
        assert counter_count != store_count, (
            "Invariant intentionally broken to document the pre-refactor bug"
        )


# ---------------------------------------------------------------------------
# TestPostUnlockBehavior
# ---------------------------------------------------------------------------

class TestPostUnlockBehavior:
    """
    Once a unit reaches UNLOCKED its onward transitions belong to the SRS
    review module, not to ExposurePolicy.  These tests verify that the service
    keeps recording exposures correctly without interfering with SRS-managed
    state, and that the counter/store invariant continues to hold.
    """

    def test_exposures_continue_accumulating_while_unit_is_unlocked(
        self, fast_service: ExposureService, target: LearningUnit
    ) -> None:
        # Reach UNLOCKED (threshold=3)
        for i in range(3):
            fast_service.record_qualified_exposure(USER, target, utt(i))
        assert fast_service.store.get_state(USER, target) == KnowledgeState.UNLOCKED

        # Two more exposures from new utterances (unit still below KNOWN_PASSIVE,
        # so the i+1 filter could still surface it)
        fast_service.record_qualified_exposure(USER, target, utt(3))
        fast_service.record_qualified_exposure(USER, target, utt(4))

        _assert_invariant(fast_service, USER, target, expected_count=5)
        assert fast_service.store.get_state(USER, target) == KnowledgeState.UNLOCKED

    def test_srs_promotion_to_known_passive_then_exposure_leaves_state(
        self, fast_service: ExposureService, target: LearningUnit
    ) -> None:
        # Reach UNLOCKED, then SRS promotes to KNOWN_PASSIVE
        for i in range(3):
            fast_service.record_qualified_exposure(USER, target, utt(i))
        fast_service.store.set_state(USER, target, KnowledgeState.KNOWN_PASSIVE)

        # A subsequent exposure (edge case: threshold was changed, or wrong call)
        # must not demote the state back below KNOWN_PASSIVE.
        fast_service.record_qualified_exposure(USER, target, utt(3))

        assert fast_service.store.get_state(USER, target) == KnowledgeState.KNOWN_PASSIVE

    def test_srs_demotion_then_further_exposures_do_not_re_advance_past_unlocked(
        self, fast_service: ExposureService, target: LearningUnit
    ) -> None:
        # Typical inactivity scenario: KNOWN_PASSIVE demoted back to UNLOCKED
        fast_service.store.set_state(USER, target, KnowledgeState.KNOWN_PASSIVE)
        fast_service.store.set_state(USER, target, KnowledgeState.UNLOCKED)

        # Further exposures increment the count but cannot auto-advance past UNLOCKED
        for i in range(4):
            fast_service.record_qualified_exposure(USER, target, utt(i))

        assert fast_service.store.get_state(USER, target) == KnowledgeState.UNLOCKED
        _assert_invariant(fast_service, USER, target, expected_count=4)

    def test_unit_seen_in_two_contexts_before_becoming_known(
        self, fast_service: ExposureService
    ) -> None:
        """
        A realistic sequence: two different unknown words learned from two
        different sentences.  Each follows the full UNSEEN→EXPOSED→UNLOCKED
        arc independently; neither's progression interferes with the other.
        """
        word_a = lemma("schön")
        word_b = lemma("wunderbar")

        for i in range(3):
            fast_service.record_qualified_exposure(USER, word_a, f"utt:schoen-{i}")
        for i in range(2):
            fast_service.record_qualified_exposure(USER, word_b, f"utt:wunderbar-{i}")

        assert fast_service.store.get_state(USER, word_a) == KnowledgeState.UNLOCKED
        assert fast_service.store.get_state(USER, word_b) == KnowledgeState.EXPOSED
        _assert_invariant(fast_service, USER, word_a, expected_count=3)
        _assert_invariant(fast_service, USER, word_b, expected_count=2)
