"""
word_knowledge.py
-----------------
Time-aware evidence system for tracking per-user word knowledge.

The central idea is that learning state advances based on *qualified,
distinct* evidence events spread across time — not raw repetition counts.
Two exposures of the same video, or two exposures ten minutes apart, are
one learning event.  Five exposures over five days are five events.

Evidence types
--------------
  Passive  — reading or video exposure: each new content source and each
             new calendar day contribute at most one qualified event.
  Active   — successful spaced recall (chat / review): each day in which
             the user correctly produces the word counts as one event.

State machine (MVP)
-------------------
  UNKNOWN  ──2 passive──►  FAMILIAR  ──5 passive──►  PASSIVE  ──3 active──►  ACTIVE
  UNKNOWN  ─── mark_known ─────────────────────────► PASSIVE
  ANY      ─── mark_unknown ─► UNKNOWN  (resets all evidence)

All thresholds and spacing rules are configurable via EvidenceConfig.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LearningState(IntEnum):
    """
    Ordered mastery levels.  IntEnum allows >= comparisons so transition
    guards can be written as  record.state >= LearningState.PASSIVE.
    """
    UNKNOWN  = 0
    FAMILIAR = 1
    PASSIVE  = 2
    ACTIVE   = 3

    def label(self) -> str:
        return self.name.capitalize()


class PassiveSource(str, Enum):
    """Origin of a passive evidence event."""
    VIDEO   = "video"
    READING = "reading"


# ---------------------------------------------------------------------------
# Evidence event records  (frozen: these are facts, not mutable state)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PassiveEvidenceEvent:
    """
    One qualified passive evidence event.

    'Qualified' means it passed both the content-deduplication gate and
    the minimum-time-gap gate.  Only accepted events are stored here.
    """
    timestamp:  datetime
    source:     PassiveSource
    content_id: Optional[str] = None


@dataclass(frozen=True)
class ActiveEvidenceEvent:
    """
    One qualified active recall event.

    Only correct, time-spaced events are stored here.
    """
    timestamp: datetime
    correct:   bool = True


# ---------------------------------------------------------------------------
# Per-word knowledge record
# ---------------------------------------------------------------------------

@dataclass
class WordKnowledge:
    """
    Everything known about one (user_id, word) pair.

    All counts reflect *qualified* events only.  Rejected duplicates and
    too-soon events are not counted and do not update timestamps.

    Attributes:
        state:                  Current learning state.
        passive_evidence_count: Qualified passive events accepted so far.
        active_success_count:   Qualified active successes accepted so far.
        last_passive_event_at:  Timestamp of the last accepted passive event.
                                Used to enforce passive_min_gap.
        last_active_event_at:   Timestamp of the last accepted active success.
                                Used to enforce active_min_gap.
        seen_content_ids:       content_id values already counted for this
                                word.  A content_id can only contribute one
                                passive event across all time.
        passive_events:         Ordered list of all accepted passive events.
        active_events:          Ordered list of all accepted active events.
    """
    user_id:               str
    word:                  str
    state:                 LearningState = LearningState.UNKNOWN
    passive_evidence_count: int = 0
    active_success_count:  int = 0
    last_passive_event_at: Optional[datetime] = None
    last_active_event_at:  Optional[datetime] = None
    seen_content_ids:      set[str] = field(default_factory=set)
    passive_events:        list[PassiveEvidenceEvent] = field(default_factory=list)
    active_events:         list[ActiveEvidenceEvent]  = field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class EvidenceConfig:
    """
    Spacing rules and state-transition thresholds.

    Defaults are reasonable starting points; tune with real user data.

    Attributes:
        passive_min_gap:    Minimum time between consecutive qualified passive
                            events.  Watching a series in a single afternoon
                            counts once, not per episode.  Default: 12 h.
        active_min_gap:     Minimum time between consecutive qualified active
                            successes.  Multiple correct uses in one chat
                            session count once.  Default: 24 h.
        familiar_threshold: Qualified passive events needed to leave UNKNOWN.
        passive_threshold:  Total qualified passive events needed to reach
                            PASSIVE.  Must be >= familiar_threshold.
        active_threshold:   Qualified active successes needed to reach ACTIVE
                            from PASSIVE.
    """
    passive_min_gap:    timedelta = field(default_factory=lambda: timedelta(hours=12))
    active_min_gap:     timedelta = field(default_factory=lambda: timedelta(hours=24))
    familiar_threshold: int = 2
    passive_threshold:  int = 5
    active_threshold:   int = 3


# ---------------------------------------------------------------------------
# Knowledge store
# ---------------------------------------------------------------------------

class KnowledgeStore:
    """
    In-memory store for WordKnowledge records, keyed by (user_id, word).

    Enforces all evidence rules: content deduplication, time spacing, and
    state transitions.  Replace with a DB-backed implementation for
    production; the method signatures are the public contract.
    """

    def __init__(self, config: Optional[EvidenceConfig] = None) -> None:
        self.config = config or EvidenceConfig()
        self._store: dict[tuple[str, str], WordKnowledge] = {}

    # ------------------------------------------------------------------
    # Core evidence methods
    # ------------------------------------------------------------------

    def record_passive_evidence(
        self,
        user_id:    str,
        word:       str,
        timestamp:  datetime,
        source:     PassiveSource = PassiveSource.VIDEO,
        content_id: Optional[str] = None,
    ) -> bool:
        """
        Record a passive exposure event (video or reading).

        Returns True if the event was accepted and counted; False if rejected.

        Rejection reasons (checked in order):
          1. content_id was already counted for this (user, word) pair.
          2. timestamp is within passive_min_gap of the last accepted event.

        When content_id is None (no source identity), only the time-gap
        rule applies.
        """
        record = self._get_or_create(user_id, word)

        # Gate 1: content-level deduplication
        if content_id is not None and content_id in record.seen_content_ids:
            return False

        # Gate 2: time spacing
        if record.last_passive_event_at is not None:
            elapsed = timestamp - record.last_passive_event_at
            if elapsed < self.config.passive_min_gap:
                return False

        # Accepted — commit the event
        if content_id is not None:
            record.seen_content_ids.add(content_id)
        record.passive_evidence_count += 1
        record.last_passive_event_at = timestamp
        record.passive_events.append(PassiveEvidenceEvent(timestamp, source, content_id))

        self._apply_passive_transitions(record)
        return True

    def mark_known(
        self,
        user_id:   str,
        word:      str,
        timestamp: datetime,
    ) -> None:
        """
        Explicitly mark a word as known (e.g. user ticks it in a word list).

        This is an intentional user action, not passive exposure, so it
        bypasses deduplication and time-gap rules.  The word is promoted
        to at least PASSIVE.  If it is already ACTIVE it is left there.

        The passive_evidence_count is raised to passive_threshold to keep
        it internally consistent with the PASSIVE state.
        """
        record = self._get_or_create(user_id, word)

        if record.state < LearningState.PASSIVE:
            record.state = LearningState.PASSIVE

        # Ensure count is consistent with PASSIVE state
        if record.passive_evidence_count < self.config.passive_threshold:
            record.passive_evidence_count = self.config.passive_threshold

        record.last_passive_event_at = timestamp

    def mark_unknown(
        self,
        user_id:   str,
        word:      str,
        timestamp: datetime,
    ) -> None:
        """
        Explicitly reset a word to UNKNOWN (e.g. user says "I don't know this").

        All evidence counts, timestamps, and seen content history are cleared.
        Future evidence accumulates from zero.

        The timestamp parameter is retained for API symmetry and future
        audit-log integration; it is not currently written anywhere.
        """
        record = self._get_or_create(user_id, word)
        record.state                  = LearningState.UNKNOWN
        record.passive_evidence_count = 0
        record.active_success_count   = 0
        record.last_passive_event_at  = None
        record.last_active_event_at   = None
        record.seen_content_ids       = set()
        record.passive_events.clear()
        record.active_events.clear()

    def record_active_success(
        self,
        user_id:   str,
        word:      str,
        timestamp: datetime,
        correct:   bool = True,
    ) -> bool:
        """
        Record an active recall attempt (chat or spaced review).

        Returns True if the event was accepted and counted; False if rejected.

        Rejection reasons:
          1. correct is False — incorrect attempts are not learning evidence.
          2. Word has not yet reached PASSIVE — active recall only counts
             once the word has been passively acquired first.
          3. timestamp is within active_min_gap of the last accepted success.
             Multiple correct uses in the same chat session should be
             submitted at the same or closely spaced timestamps; only the
             first one in each gap window is counted.
        """
        if not correct:
            return False

        record = self._get_or_create(user_id, word)

        # Active recall is only meaningful once the word has been acquired passively
        if record.state < LearningState.PASSIVE:
            return False

        # Time spacing
        if record.last_active_event_at is not None:
            elapsed = timestamp - record.last_active_event_at
            if elapsed < self.config.active_min_gap:
                return False

        # Accepted
        record.active_success_count += 1
        record.last_active_event_at = timestamp
        record.active_events.append(ActiveEvidenceEvent(timestamp, correct=True))

        self._apply_active_transitions(record)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_state(self, user_id: str, word: str) -> LearningState:
        """Return current state; UNKNOWN for words never seen."""
        record = self._store.get((user_id, word))
        return record.state if record else LearningState.UNKNOWN

    def get_knowledge(self, user_id: str, word: str) -> Optional[WordKnowledge]:
        """Return the full WordKnowledge record, or None if not in the store."""
        return self._store.get((user_id, word))

    def reset_user(self, user_id: str) -> None:
        """Remove all records for a user.  Useful for testing and account resets."""
        to_remove = [k for k in self._store if k[0] == user_id]
        for k in to_remove:
            del self._store[k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create(self, user_id: str, word: str) -> WordKnowledge:
        key = (user_id, word)
        if key not in self._store:
            self._store[key] = WordKnowledge(user_id=user_id, word=word)
        return self._store[key]

    def _apply_passive_transitions(self, record: WordKnowledge) -> None:
        """
        Advance state based on current passive_evidence_count.

        Checks PASSIVE threshold before FAMILIAR so that a count reaching
        5 in one step (e.g. after a config change) skips straight to
        PASSIVE rather than stopping at FAMILIAR.
        """
        count = record.passive_evidence_count
        if record.state < LearningState.PASSIVE and count >= self.config.passive_threshold:
            record.state = LearningState.PASSIVE
        elif record.state < LearningState.FAMILIAR and count >= self.config.familiar_threshold:
            record.state = LearningState.FAMILIAR

    def _apply_active_transitions(self, record: WordKnowledge) -> None:
        """Advance PASSIVE → ACTIVE when active_threshold is reached."""
        if (record.state == LearningState.PASSIVE
                and record.active_success_count >= self.config.active_threshold):
            record.state = LearningState.ACTIVE


# ---------------------------------------------------------------------------
# Example flow
# ---------------------------------------------------------------------------

def _demo() -> None:
    """
    Example: 'anfangen' going from UNKNOWN → FAMILIAR → PASSIVE → ACTIVE
    over several days of video watching and chat practice.
    """
    def ts(day: int, hour: int = 20) -> datetime:
        return datetime(2024, 3, day, hour, 0, tzinfo=timezone.utc)

    store = KnowledgeStore()
    USER = "alice"
    WORD = "anfangen"

    print("─" * 60)
    print("  Evidence trace for 'anfangen'")
    print("─" * 60)

    def show(label: str) -> None:
        k = store.get_knowledge(USER, WORD)
        state = store.get_state(USER, WORD)
        passive = k.passive_evidence_count if k else 0
        active  = k.active_success_count   if k else 0
        print(f"  {label:<45}  state={state.label():<8}  passive={passive}  active={active}")

    # Day 1 — first encounter: two occurrences in the same video
    accepted = store.record_passive_evidence(USER, WORD, ts(1), PassiveSource.VIDEO, content_id="ep01")
    show(f"Day 1 video ep01 (accepted={accepted})")

    # Same episode rewatched an hour later — deduplication blocks it
    accepted = store.record_passive_evidence(USER, WORD, ts(1, 21), PassiveSource.VIDEO, content_id="ep01")
    show(f"Day 1 video ep01 again (accepted={accepted}, deduped)")

    # Different episode on the same day, but still within 12 h of the first
    accepted = store.record_passive_evidence(USER, WORD, ts(1, 22), PassiveSource.VIDEO, content_id="ep02")
    show(f"Day 1 video ep02, 2 h later (accepted={accepted}, too soon)")

    # Day 2 — different content, enough time has passed
    accepted = store.record_passive_evidence(USER, WORD, ts(2), PassiveSource.VIDEO, content_id="ep02")
    show(f"Day 2 video ep02 (accepted={accepted})")  # FAMILIAR reached

    # Day 3 — reading article
    accepted = store.record_passive_evidence(USER, WORD, ts(3), PassiveSource.READING, content_id="article-7")
    show(f"Day 3 reading article-7 (accepted={accepted})")

    # Day 4 — another reading
    accepted = store.record_passive_evidence(USER, WORD, ts(4), PassiveSource.READING, content_id="article-9")
    show(f"Day 4 reading article-9 (accepted={accepted})")

    # Day 5 — final passive event reaches PASSIVE threshold
    accepted = store.record_passive_evidence(USER, WORD, ts(5), PassiveSource.VIDEO, content_id="ep03")
    show(f"Day 5 video ep03 (accepted={accepted})")  # PASSIVE reached

    print()

    # Day 10 — first correct use in chat
    accepted = store.record_active_success(USER, WORD, ts(10))
    show(f"Day 10 chat correct (accepted={accepted})")

    # Same day — second use in the same session (within gap) — blocked
    accepted = store.record_active_success(USER, WORD, ts(10, 21))
    show(f"Day 10 chat again 1 h later (accepted={accepted}, too soon)")

    # Day 15 — second session
    accepted = store.record_active_success(USER, WORD, ts(15))
    show(f"Day 15 chat correct (accepted={accepted})")

    # Day 20 — third session reaches ACTIVE
    accepted = store.record_active_success(USER, WORD, ts(20))
    show(f"Day 20 chat correct (accepted={accepted})")  # ACTIVE reached

    print()
    print("  Final state:", store.get_state(USER, WORD).label())


if __name__ == "__main__":
    _demo()
