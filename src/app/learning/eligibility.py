from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, runtime_checkable

from app.learning.units import LearningUnit


@runtime_checkable
class KnowledgeSource(Protocol):
    """
    Minimal read interface required by UtteranceEligibilityEvaluator.

    Any object that implements is_known() satisfies this protocol.
    """

    def is_known(self, user_id: str, unit: LearningUnit) -> bool:
        """Return True if `unit` meets the known threshold for `user_id`."""
        ...


class IneligibilityReason(str, Enum):
    """
    Enumerated reasons why an utterance is not eligible for a target unit.

    Checks are applied in priority order — the first failure is reported.
    """
    NO_LEARNABLE_UNITS = "no_learnable_units"
    TARGET_NOT_IN_UTTERANCE = "target_not_in_utterance"
    TARGET_ALREADY_KNOWN = "target_already_known"
    OTHER_UNKNOWNS_PRESENT = "other_unknowns_present"


@dataclass
class EligibilityDecision:
    """The full result of evaluating whether an utterance is eligible for target T."""
    eligible: bool
    target_unit: LearningUnit
    ineligibility_reason: Optional[IneligibilityReason] = None
    known_units: list[LearningUnit] = field(default_factory=list)
    unknown_units: list[LearningUnit] = field(default_factory=list)
    blocking_units: list[LearningUnit] = field(default_factory=list)

    @property
    def failure_summary(self) -> str:
        if self.eligible:
            return ""
        r = self.ineligibility_reason
        if r == IneligibilityReason.NO_LEARNABLE_UNITS:
            return "No learnable units found in utterance."
        if r == IneligibilityReason.TARGET_NOT_IN_UTTERANCE:
            return f"Target '{self.target_unit.key}' is not in the utterance's unit list."
        if r == IneligibilityReason.TARGET_ALREADY_KNOWN:
            return (
                f"Target '{self.target_unit.key}' is already known — "
                "cannot be an acquisition target."
            )
        if r == IneligibilityReason.OTHER_UNKNOWNS_PRESENT:
            keys = [u.key for u in self.blocking_units]
            return (
                f"{len(self.blocking_units)} other unknown unit(s) besides "
                f"'{self.target_unit.key}': {keys}"
            )
        return "Ineligible (unrecognised reason)."

    def __repr__(self) -> str:
        status = "ELIGIBLE" if self.eligible else f"INELIGIBLE({self.ineligibility_reason})"
        return f"EligibilityDecision({status}, target={self.target_unit.key!r})"


class UtteranceEligibilityEvaluator:
    """
    Evaluates i+1 eligibility for a specific target unit given an utterance's
    learning units and a user's knowledge state.

    The evaluator is stateless beyond its reference to the knowledge source.
    """

    def __init__(self, knowledge_source: KnowledgeSource) -> None:
        self.knowledge_source = knowledge_source

    def evaluate(
        self,
        user_id: str,
        units: list[LearningUnit],
        target: LearningUnit,
    ) -> EligibilityDecision:
        """
        Evaluate whether an utterance is eligible for target unit `target`.

        Returns EligibilityDecision with eligible=True only when:
          - target is present in units
          - target is not yet known by the user
          - all other units are already known by the user
        """
        if not units:
            return self._ineligible(
                target=target,
                reason=IneligibilityReason.NO_LEARNABLE_UNITS,
                known=[],
                unknown=[],
                blocking=[],
            )

        known, unknown = self._partition(user_id, units)

        if not self._unit_present(units, target):
            return self._ineligible(
                target=target,
                reason=IneligibilityReason.TARGET_NOT_IN_UTTERANCE,
                known=known,
                unknown=unknown,
                blocking=[],
            )

        if self.knowledge_source.is_known(user_id, target):
            return self._ineligible(
                target=target,
                reason=IneligibilityReason.TARGET_ALREADY_KNOWN,
                known=known,
                unknown=unknown,
                blocking=[],
            )

        blocking = self._blocking_units(unknown, target)
        if blocking:
            return self._ineligible(
                target=target,
                reason=IneligibilityReason.OTHER_UNKNOWNS_PRESENT,
                known=known,
                unknown=unknown,
                blocking=blocking,
            )

        return EligibilityDecision(
            eligible=True,
            target_unit=target,
            ineligibility_reason=None,
            known_units=known,
            unknown_units=unknown,
            blocking_units=[],
        )

    def find_eligible_targets(
        self,
        user_id: str,
        units: list[LearningUnit],
    ) -> list[EligibilityDecision]:
        """Return EligibilityDecisions for every unit that is a valid i+1 target."""
        return [
            d
            for unit in units
            for d in [self.evaluate(user_id, units, unit)]
            if d.eligible
        ]

    def evaluate_all(
        self,
        user_id: str,
        units: list[LearningUnit],
    ) -> list[EligibilityDecision]:
        """Evaluate every unit in `units` as a potential target, returning all decisions."""
        return [self.evaluate(user_id, units, unit) for unit in units]

    def _partition(
        self,
        user_id: str,
        units: list[LearningUnit],
    ) -> tuple[list[LearningUnit], list[LearningUnit]]:
        known: list[LearningUnit] = []
        unknown: list[LearningUnit] = []
        for unit in units:
            (known if self.knowledge_source.is_known(user_id, unit) else unknown).append(unit)
        return known, unknown

    @staticmethod
    def _unit_present(units: list[LearningUnit], target: LearningUnit) -> bool:
        target_id = (target.unit_type, target.key)
        return any((u.unit_type, u.key) == target_id for u in units)

    @staticmethod
    def _blocking_units(
        unknown: list[LearningUnit],
        target: LearningUnit,
    ) -> list[LearningUnit]:
        target_id = (target.unit_type, target.key)
        return [u for u in unknown if (u.unit_type, u.key) != target_id]

    @staticmethod
    def _ineligible(
        target: LearningUnit,
        reason: IneligibilityReason,
        known: list[LearningUnit],
        unknown: list[LearningUnit],
        blocking: list[LearningUnit],
    ) -> EligibilityDecision:
        return EligibilityDecision(
            eligible=False,
            target_unit=target,
            ineligibility_reason=reason,
            known_units=known,
            unknown_units=unknown,
            blocking_units=blocking,
        )
