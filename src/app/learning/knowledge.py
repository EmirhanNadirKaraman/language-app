from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Optional

from app.learning.units import LearningUnit, LearningUnitType, UserKnowledgeProfile


class KnowledgeState(IntEnum):
    """
    Ordered mastery levels for a single learning unit.

    Using IntEnum gives free comparison operators:
        KnowledgeState.KNOWN_PASSIVE >= KnowledgeState.EXPOSED  # True
    """
    UNSEEN = 0
    EXPOSED = 1
    UNLOCKED = 2
    KNOWN_PASSIVE = 3
    KNOWN_ACTIVE = 4
    MASTERED = 5

    def label(self) -> str:
        return {
            0: "Unseen",
            1: "Exposed",
            2: "Unlocked",
            3: "Known (passive)",
            4: "Known (active)",
            5: "Mastered",
        }[self.value]


@dataclass
class KnowledgeFilterPolicy:
    """
    Defines what counts as "known" when building the i+1 filter.

    Attributes:
        min_known_state: Units at or above this state are treated as known.
    """
    min_known_state: KnowledgeState = KnowledgeState.KNOWN_PASSIVE

    def is_known(self, state: KnowledgeState) -> bool:
        return state >= self.min_known_state

    def is_unknown(self, state: KnowledgeState) -> bool:
        return not self.is_known(state)


@dataclass
class ExposurePolicy:
    """
    Controls automatic state transitions triggered by record_exposure().

    Attributes:
        auto_advance:       When True, record_exposure() may advance state.
        exposures_to_unlock: Exposures needed to advance EXPOSED → UNLOCKED.
    """
    auto_advance: bool = True
    exposures_to_unlock: int = 5


@dataclass
class UserUnitKnowledge:
    """One user's knowledge record for one learning unit."""
    user_id: str
    unit: LearningUnit
    state: KnowledgeState = KnowledgeState.UNSEEN
    exposure_count: int = 0
    correct_recall_count: int = 0
    state_changed_at: Optional[datetime] = None
    last_exposed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return (
            f"UserUnitKnowledge("
            f"user={self.user_id!r}, "
            f"unit={self.unit.key!r}, "
            f"state={self.state.name}, "
            f"exposures={self.exposure_count})"
        )


class UserKnowledgeStore:
    """
    In-memory store for UserUnitKnowledge records.

    Provides all read and write operations needed by the pipeline.
    """

    def __init__(
        self,
        filter_policy: Optional[KnowledgeFilterPolicy] = None,
        exposure_policy: Optional[ExposurePolicy] = None,
    ) -> None:
        self.filter_policy = filter_policy or KnowledgeFilterPolicy()
        self.exposure_policy = exposure_policy or ExposurePolicy()
        self._store: dict[str, dict[tuple[LearningUnitType, str], UserUnitKnowledge]] = {}

    def get_knowledge(self, user_id: str, unit: LearningUnit) -> UserUnitKnowledge:
        """Return the knowledge record for (user_id, unit); default UNSEEN if absent."""
        return self._user_store(user_id).get(
            self._key(unit),
            UserUnitKnowledge(user_id=user_id, unit=unit),
        )

    def get_state(self, user_id: str, unit: LearningUnit) -> KnowledgeState:
        record = self._user_store(user_id).get(self._key(unit))
        return record.state if record else KnowledgeState.UNSEEN

    def is_known(self, user_id: str, unit: LearningUnit) -> bool:
        return self.filter_policy.is_known(self.get_state(user_id, unit))

    def unknown_units(
        self,
        user_id: str,
        units: list[LearningUnit],
    ) -> list[LearningUnit]:
        return [u for u in units if not self.is_known(user_id, u)]

    def find_sole_unknown(
        self,
        user_id: str,
        units: list[LearningUnit],
    ) -> Optional[LearningUnit]:
        """Return the one unknown unit if exactly one; otherwise None. This is the i+1 gate."""
        unknowns = self.unknown_units(user_id, units)
        return unknowns[0] if len(unknowns) == 1 else None

    def get_summary(self, user_id: str) -> dict[KnowledgeState, int]:
        counts: dict[KnowledgeState, int] = {s: 0 for s in KnowledgeState}
        for record in self._user_store(user_id).values():
            counts[record.state] += 1
        return counts

    def build_profile(self, user_id: str) -> UserKnowledgeProfile:
        """Build a UserKnowledgeProfile snapshot for the i+1 filter stage."""
        known_keys = frozenset(
            (rec.unit.unit_type, rec.unit.key)
            for rec in self._user_store(user_id).values()
            if self.filter_policy.is_known(rec.state)
        )
        return UserKnowledgeProfile(user_id=user_id, known_keys=known_keys)

    def set_state(
        self,
        user_id: str,
        unit: LearningUnit,
        state: KnowledgeState,
    ) -> UserUnitKnowledge:
        """Directly set the knowledge state for (user_id, unit)."""
        record = self._get_or_create(user_id, unit)
        record.state = state
        record.state_changed_at = datetime.now(timezone.utc)
        return record

    def record_exposure(
        self,
        user_id: str,
        unit: LearningUnit,
    ) -> UserUnitKnowledge:
        """
        Record that (user_id, unit) was the i+1 target of a surfaced utterance.
        Auto-advances state per ExposurePolicy.
        """
        record = self._get_or_create(user_id, unit)
        record.exposure_count += 1
        record.last_exposed_at = datetime.now(timezone.utc)

        if self.exposure_policy.auto_advance:
            if record.state == KnowledgeState.UNSEEN:
                self._advance(record, KnowledgeState.EXPOSED)
            elif (
                record.state == KnowledgeState.EXPOSED
                and record.exposure_count >= self.exposure_policy.exposures_to_unlock
            ):
                self._advance(record, KnowledgeState.UNLOCKED)

        return record

    def seed_known_units(
        self,
        user_id: str,
        units: list[LearningUnit],
        state: KnowledgeState = KnowledgeState.KNOWN_PASSIVE,
    ) -> None:
        """Bulk-mark a list of units as known for a new user."""
        for unit in units:
            self.set_state(user_id, unit, state)

    def reset_user(self, user_id: str) -> None:
        """Remove all knowledge records for a user."""
        self._store.pop(user_id, None)

    def _user_store(self, user_id: str) -> dict[tuple[LearningUnitType, str], UserUnitKnowledge]:
        return self._store.get(user_id, {})

    def _get_or_create(self, user_id: str, unit: LearningUnit) -> UserUnitKnowledge:
        if user_id not in self._store:
            self._store[user_id] = {}
        inner = self._store[user_id]
        k = self._key(unit)
        if k not in inner:
            inner[k] = UserUnitKnowledge(user_id=user_id, unit=unit)
        return inner[k]

    @staticmethod
    def _key(unit: LearningUnit) -> tuple[LearningUnitType, str]:
        return (unit.unit_type, unit.key)

    @staticmethod
    def _advance(record: UserUnitKnowledge, new_state: KnowledgeState) -> None:
        record.state = new_state
        record.state_changed_at = datetime.now(timezone.utc)

    def save(self, path: Path | str) -> None:
        """Serialise the entire store to a UTF-8 JSON file."""
        path = Path(path)
        users: dict[str, dict] = {}
        for user_id, records in self._store.items():
            user_records: dict[str, dict] = {}
            for record in records.values():
                rec_key = f"{record.unit.unit_type.value}:{record.unit.key}"
                user_records[rec_key] = {
                    "unit_type":            record.unit.unit_type.value,
                    "key":                  record.unit.key,
                    "display_form":         record.unit.display_form,
                    "language":             record.unit.language,
                    "state":                record.state.value,
                    "exposure_count":       record.exposure_count,
                    "correct_recall_count": record.correct_recall_count,
                    "state_changed_at":     record.state_changed_at.isoformat() if record.state_changed_at else None,
                    "last_exposed_at":      record.last_exposed_at.isoformat() if record.last_exposed_at else None,
                    "created_at":           record.created_at.isoformat(),
                }
            users[user_id] = user_records

        payload = json.dumps({"version": 1, "users": users}, ensure_ascii=False, indent=2)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(
        cls,
        path: Path | str,
        filter_policy: Optional[KnowledgeFilterPolicy] = None,
        exposure_policy: Optional[ExposurePolicy] = None,
    ) -> "UserKnowledgeStore":
        """Deserialise a store from a JSON file written by save()."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        version = raw.get("version")
        if version != 1:
            raise ValueError(f"Unsupported store file version: {version!r}")

        store = cls(filter_policy=filter_policy, exposure_policy=exposure_policy)
        for user_id, records in raw.get("users", {}).items():
            store._store[user_id] = {}
            for rec_key, rec in records.items():
                unit = LearningUnit(
                    unit_type=LearningUnitType(rec["unit_type"]),
                    key=rec["key"],
                    display_form=rec["display_form"],
                    language=rec.get("language", "de"),
                )
                record = UserUnitKnowledge(
                    user_id=user_id,
                    unit=unit,
                    state=KnowledgeState(rec["state"]),
                    exposure_count=rec["exposure_count"],
                    correct_recall_count=rec["correct_recall_count"],
                    state_changed_at=datetime.fromisoformat(rec["state_changed_at"]) if rec["state_changed_at"] else None,
                    last_exposed_at=datetime.fromisoformat(rec["last_exposed_at"]) if rec["last_exposed_at"] else None,
                    created_at=datetime.fromisoformat(rec["created_at"]),
                )
                store._store[user_id][cls._key(unit)] = record
        return store
