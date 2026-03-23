from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.exposure.counter import QualifiedExposureCounter
from app.exposure.models import ExposureEvent
from app.learning.units import LearningUnit
from app.learning.knowledge import UserKnowledgeStore


class ExposureService:
    """
    Coordinates QualifiedExposureCounter and UserKnowledgeStore for each
    qualified exposure event.

    Design invariant
    ----------------
    After every accepted record_qualified_exposure() call:
        counter.get_raw_count(user_id, unit)
            == store.get_knowledge(user_id, unit).exposure_count

    Neither component drives the other.  ExposureService is the single write
    point for qualified exposure data.

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

        Returns ExposureEvent if accepted, None if rejected as a duplicate.
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
        """Reset all exposure data for a user in both counter and store."""
        self.counter.reset_user(user_id)
        self.store.reset_user(user_id)
