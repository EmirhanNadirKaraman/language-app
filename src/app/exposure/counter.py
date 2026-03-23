from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from app.exposure.models import (
    CountingPolicy,
    DuplicateRule,
    ExposureEvent,
    ExposureStats,
)
from app.learning.units import LearningUnit, LearningUnitType

_UnitKey = tuple[LearningUnitType, str]


def _unit_key(unit: LearningUnit) -> _UnitKey:
    return (unit.unit_type, unit.key)


class QualifiedExposureCounter:
    """
    Records and queries qualified exposure events for user/unit pairs.

    All state is held in Python dicts (MVP in-memory storage).  For
    production, replace the private _write_* and _read_* internals with
    database calls while keeping the public API unchanged.

    Args:
        policy: CountingPolicy that governs deduplication and weighting.
                Defaults to DEDUPLICATE_UTTERANCE with weight 1.0.
    """

    def __init__(self, policy: Optional[CountingPolicy] = None) -> None:
        self.policy = policy or CountingPolicy()

        # Primary event log: _events[user_id][unit_key] -> list[ExposureEvent]
        self._events: dict[str, dict[_UnitKey, list[ExposureEvent]]] = {}

        # Per-(user, unit, utterance_id) occurrence count
        self._utterance_counts: dict[str, dict[_UnitKey, dict[str, int]]] = {}

        # DEDUPLICATE_SESSION: seen (session_id, utterance_id) pairs per (user, unit)
        self._session_seen: dict[str, dict[_UnitKey, set[tuple[str, str]]]] = {}

    def record(
        self,
        user_id: str,
        unit: LearningUnit,
        utterance_id: str,
        occurred_at: Optional[datetime] = None,
        session_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Optional[ExposureEvent]:
        """
        Attempt to record a qualified exposure.

        Returns the ExposureEvent if the policy accepted the event, or None
        if the event was rejected as a duplicate.
        """
        if occurred_at is None:
            occurred_at = datetime.now(timezone.utc)

        unit_key = _unit_key(unit)

        if self._is_duplicate(user_id, unit_key, utterance_id, session_id):
            return None

        weight = self._compute_weight(user_id, unit_key, utterance_id)

        event = ExposureEvent(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            unit=unit,
            utterance_id=utterance_id,
            occurred_at=occurred_at,
            weight=weight,
            session_id=session_id,
            source_id=source_id,
        )

        self._append_event(user_id, unit_key, event)
        self._increment_utterance_count(user_id, unit_key, utterance_id)
        if session_id is not None:
            self._mark_session_seen(user_id, unit_key, session_id, utterance_id)

        return event

    def reset_user(self, user_id: str) -> None:
        """Remove all exposure records for a user."""
        self._events.pop(user_id, None)
        self._utterance_counts.pop(user_id, None)
        self._session_seen.pop(user_id, None)

    def get_raw_count(self, user_id: str, unit: LearningUnit) -> int:
        return len(self._get_events(user_id, _unit_key(unit)))

    def get_weighted_count(self, user_id: str, unit: LearningUnit) -> float:
        return sum(e.weight for e in self._get_events(user_id, _unit_key(unit)))

    def get_stats(self, user_id: str, unit: LearningUnit) -> ExposureStats:
        events = self._get_events(user_id, _unit_key(unit))
        if not events:
            return ExposureStats(
                unit=unit,
                raw_count=0,
                weighted_count=0.0,
                unique_utterances=0,
                first_exposure=None,
                last_exposure=None,
            )
        return ExposureStats(
            unit=unit,
            raw_count=len(events),
            weighted_count=sum(e.weight for e in events),
            unique_utterances=len({e.utterance_id for e in events}),
            first_exposure=min(e.occurred_at for e in events),
            last_exposure=max(e.occurred_at for e in events),
        )

    def get_all_stats(self, user_id: str) -> dict[LearningUnit, ExposureStats]:
        user_events = self._events.get(user_id, {})
        result: dict[LearningUnit, ExposureStats] = {}
        for unit_key, events in user_events.items():
            if events:
                unit = events[0].unit
                result[unit] = self.get_stats(user_id, unit)
        return result

    def get_events(self, user_id: str, unit: LearningUnit) -> list[ExposureEvent]:
        return list(self._get_events(user_id, _unit_key(unit)))

    def units_above_threshold(self, user_id: str, threshold: float) -> list[LearningUnit]:
        return [
            unit
            for unit, stats in self.get_all_stats(user_id).items()
            if stats.weighted_count >= threshold
        ]

    def _is_duplicate(
        self,
        user_id: str,
        unit_key: _UnitKey,
        utterance_id: str,
        session_id: Optional[str],
    ) -> bool:
        rule = self.policy.duplicate_rule

        if rule == DuplicateRule.ALLOW_ALL:
            return False

        if rule == DuplicateRule.DIMINISHING_RETURNS:
            return False

        if rule == DuplicateRule.DEDUPLICATE_UTTERANCE:
            return self._get_utterance_count(user_id, unit_key, utterance_id) > 0

        if rule == DuplicateRule.DEDUPLICATE_SESSION:
            if session_id is None:
                return self._get_utterance_count(user_id, unit_key, utterance_id) > 0
            seen = self._session_seen.get(user_id, {}).get(unit_key, set())
            return (session_id, utterance_id) in seen

        return False

    def _compute_weight(
        self,
        user_id: str,
        unit_key: _UnitKey,
        utterance_id: str,
    ) -> float:
        if self.policy.duplicate_rule != DuplicateRule.DIMINISHING_RETURNS:
            return 1.0
        n = self._get_utterance_count(user_id, unit_key, utterance_id)
        raw_weight = self.policy.diminishing_decay ** n
        return max(raw_weight, self.policy.min_weight)

    def _get_events(self, user_id: str, unit_key: _UnitKey) -> list[ExposureEvent]:
        return self._events.get(user_id, {}).get(unit_key, [])

    def _append_event(self, user_id: str, unit_key: _UnitKey, event: ExposureEvent) -> None:
        if user_id not in self._events:
            self._events[user_id] = {}
        self._events[user_id].setdefault(unit_key, []).append(event)

    def _get_utterance_count(self, user_id: str, unit_key: _UnitKey, utterance_id: str) -> int:
        return (
            self._utterance_counts
            .get(user_id, {})
            .get(unit_key, {})
            .get(utterance_id, 0)
        )

    def _increment_utterance_count(
        self, user_id: str, unit_key: _UnitKey, utterance_id: str
    ) -> None:
        if user_id not in self._utterance_counts:
            self._utterance_counts[user_id] = {}
        counts = self._utterance_counts[user_id]
        if unit_key not in counts:
            counts[unit_key] = {}
        counts[unit_key][utterance_id] = counts[unit_key].get(utterance_id, 0) + 1

    def _mark_session_seen(
        self,
        user_id: str,
        unit_key: _UnitKey,
        session_id: str,
        utterance_id: str,
    ) -> None:
        if user_id not in self._session_seen:
            self._session_seen[user_id] = {}
        if unit_key not in self._session_seen[user_id]:
            self._session_seen[user_id][unit_key] = set()
        self._session_seen[user_id][unit_key].add((session_id, utterance_id))
