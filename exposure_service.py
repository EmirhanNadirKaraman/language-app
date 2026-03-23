"""
exposure_service.py
-------------------
Thin orchestrator that coordinates QualifiedExposureCounter and
UserKnowledgeStore for every qualified exposure event.

Design invariant
----------------
After every accepted record_qualified_exposure() call:

    counter.get_raw_count(user_id, unit)
        == store.get_knowledge(user_id, unit).exposure_count

Neither component drives the other.  ExposureService is the single write
point for qualified exposure data — calling counter.record() or
store.record_exposure() directly bypasses this invariant and will cause
the two stores to diverge.

When to use
-----------
Replace every direct call to store.record_exposure() with a call to
ExposureService.record_qualified_exposure().  The service delegates to both
components in the correct order and respects the counter's deduplication
policy before touching the knowledge store.

Production notes
----------------
Both writes (counter event append, store exposure_count increment) are plain
dict mutations in this in-memory MVP and are trivially "atomic".  In a
production database backend, wrap them in a single transaction so that a
crash between the two writes cannot leave the invariant broken.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from exposure_counter import ExposureEvent, QualifiedExposureCounter
from learning_units import LearningUnit
from user_knowledge import UserKnowledgeStore


class ExposureService:
    """
    Coordinates QualifiedExposureCounter and UserKnowledgeStore for each
    qualified exposure event.

    Call record_qualified_exposure() whenever a user is shown an i+1
    utterance.  The service:
      1. Asks the counter whether this event is a duplicate under the
         configured CountingPolicy.
      2. If accepted: persists the event in the counter, then calls
         store.record_exposure() to trigger knowledge-state auto-advance.
      3. Returns the ExposureEvent on accept, None on reject.

    Design invariant
    ----------------
    After each accepted call:
        counter.get_raw_count(user_id, unit)
            == store.get_knowledge(user_id, unit).exposure_count

    Args:
        counter: QualifiedExposureCounter governing deduplication and event log.
        store:   UserKnowledgeStore owning state transitions and exposure_count.
    """

    def __init__(
        self,
        counter: QualifiedExposureCounter,
        store: UserKnowledgeStore,
    ) -> None:
        self.counter = counter
        self.store = store

    def record_qualified_exposure(
        self,
        user_id: str,
        unit: LearningUnit,
        utterance_id: str,
        occurred_at: Optional[datetime] = None,
        session_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Optional[ExposureEvent]:
        """
        Record a qualified i+1 exposure in both the counter and the store.

        The counter acts as gatekeeper: if it rejects the event as a duplicate
        under the current CountingPolicy, the store is NOT updated.  This
        prevents duplicate subtitle replays from inflating knowledge progress.

        Args:
            user_id:      The user who was shown the utterance.
            unit:         The sole-unknown acquisition target for this utterance.
            utterance_id: Stable identifier for the source utterance.  Derive
                          from I1Match.utterance_id for pipeline callers.
            occurred_at:  Exposure timestamp.  Defaults to now (UTC).
            session_id:   Optional session scope for DEDUPLICATE_SESSION policy.
            source_id:    Optional source material identifier (e.g. video ID).

        Returns:
            ExposureEvent if the exposure was accepted and recorded,
            None if the counter rejected it as a duplicate.
        """
        event = self.counter.record(
            user_id=user_id,
            unit=unit,
            utterance_id=utterance_id,
            occurred_at=occurred_at,
            session_id=session_id,
            source_id=source_id,
        )
        if event is not None:
            self.store.record_exposure(user_id, unit)
        return event

    def reset_user(self, user_id: str) -> None:
        """
        Reset all exposure data for a user in both counter and store.

        Clears the entire store partition for this user, including states set
        via store.set_state() (onboarding seeds, SRS promotions).  Call
        counter.reset_user() and store.reset_user() separately if you need
        finer control.
        """
        self.counter.reset_user(user_id)
        self.store.reset_user(user_id)
