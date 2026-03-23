from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.subtitles.models import CandidateUtterance


_INCOMPLETE_ENDING_WORDS: frozenset[str] = frozenset({
    "und", "oder", "aber", "denn", "sondern",
    "weil", "dass", "wenn", "ob", "als", "während", "obwohl",
    "damit", "sodass", "nachdem", "bevor", "bis", "seit", "falls",
    "sofern", "solange", "sobald", "indem", "seitdem",
    "in", "an", "auf", "über", "unter", "vor", "hinter", "neben",
    "zwischen", "mit", "nach", "bei", "von", "zu", "aus", "durch",
    "für", "gegen", "ohne", "um", "wegen", "trotz",
    "ein", "eine", "einen", "einem", "einer", "eines",
    "haben", "sein", "werden", "können", "müssen", "dürfen",
    "sollen", "wollen", "mögen",
    "dessen", "deren", "was", "wer", "wie", "wo", "wohin",
})

_SUSPICIOUS_START_CHARS: frozenset[str] = frozenset({",", ";", ":", "-", "–", "—", "…"})


@dataclass
class CheckResult:
    """The outcome of a single quality check."""
    name: str
    passed: bool
    reason: str


@dataclass
class QualityDecision:
    """The aggregated quality evaluation for one CandidateUtterance."""
    candidate: CandidateUtterance
    passed: bool
    checks: list[CheckResult]

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def failure_reasons(self) -> list[str]:
        return [c.reason for c in self.checks if not c.passed]

    def __repr__(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        preview = (
            self.candidate.text
            if len(self.candidate.text) <= 50
            else self.candidate.text[:47] + "..."
        )
        return f"QualityDecision({verdict}, {preview!r})"


@dataclass(frozen=True)
class RuleMetrics:
    """Rejection statistics for a single quality check, as a read-only snapshot."""
    rule_name: str
    times_evaluated: int
    times_rejected: int

    @property
    def rejection_rate(self) -> float:
        if self.times_evaluated == 0:
            return 0.0
        return self.times_rejected / self.times_evaluated

    def __repr__(self) -> str:
        return (
            f"RuleMetrics({self.rule_name!r}, "
            f"evaluated={self.times_evaluated:,}, "
            f"rejected={self.times_rejected:,} [{self.rejection_rate:.1%}])"
        )


class FilterMetrics:
    """A point-in-time snapshot of quality-filter statistics."""

    def __init__(
        self,
        total_evaluated: int,
        total_passed: int,
        total_rejected: int,
        whitelist_accepted: int,
        rules: dict[str, RuleMetrics],
    ) -> None:
        self.total_evaluated = total_evaluated
        self.total_passed = total_passed
        self.total_rejected = total_rejected
        self.whitelist_accepted = whitelist_accepted
        self.rules = rules

    @property
    def overall_rejection_rate(self) -> float:
        if self.total_evaluated == 0:
            return 0.0
        return self.total_rejected / self.total_evaluated

    def most_aggressive_rules(self) -> list[RuleMetrics]:
        return sorted(self.rules.values(), key=lambda r: r.times_rejected, reverse=True)

    def as_dict(self) -> dict:
        return {
            "total_evaluated": self.total_evaluated,
            "total_passed": self.total_passed,
            "total_rejected": self.total_rejected,
            "whitelist_accepted": self.whitelist_accepted,
            "overall_rejection_rate": round(self.overall_rejection_rate, 4),
            "rules": {
                name: {
                    "times_evaluated": r.times_evaluated,
                    "times_rejected": r.times_rejected,
                    "rejection_rate": round(r.rejection_rate, 4),
                }
                for name, r in self.rules.items()
            },
        }

    def format_table(self) -> str:
        lines: list[str] = []
        rate_str = f"{self.overall_rejection_rate:.1%}"
        lines.append(
            f"Total : {self.total_evaluated:,} evaluated — "
            f"{self.total_passed:,} passed, {self.total_rejected:,} rejected ({rate_str})"
        )
        if self.whitelist_accepted:
            lines.append(f"Whitelist admitted: {self.whitelist_accepted:,}")

        if not self.rules:
            lines.append("(no rule data yet)")
            return "\n".join(lines)

        col_w = max(len(name) for name in self.rules)
        header = f"\n  {'rule':<{col_w}}  {'evaluated':>9}  {'rejected':>8}  {'rate':>6}"
        sep    = f"  {'─' * col_w}  {'─'*9}  {'─'*8}  {'─'*6}"
        lines.append(header)
        lines.append(sep)

        for r in self.most_aggressive_rules():
            if r.rule_name == "whitelist":
                lines.append(
                    f"  {r.rule_name:<{col_w}}  {r.times_evaluated:>9,}  {'—':>8}  {'—':>6}"
                )
            else:
                rate_pct = f"{r.rejection_rate:.1%}"
                lines.append(
                    f"  {r.rule_name:<{col_w}}  {r.times_evaluated:>9,}"
                    f"  {r.times_rejected:>8,}  {rate_pct:>6}"
                )

        return "\n".join(lines)

    def __repr__(self) -> str:
        rate = f"{self.overall_rejection_rate:.1%}"
        return (
            f"FilterMetrics("
            f"evaluated={self.total_evaluated:,}, "
            f"passed={self.total_passed:,}, "
            f"rejected={self.total_rejected:,} [{rate}], "
            f"rules={list(self.rules)})"
        )


@dataclass
class QualityFilterConfig:
    """
    Thresholds and toggles for UtteranceQualityEvaluator.

    Attributes:
        min_tokens:           Minimum whitespace-split tokens required.
        max_tokens:           Maximum tokens allowed.
        min_alpha_ratio:      Minimum fraction of characters that must be alphabetic.
        max_word_repetitions: Maximum allowed occurrences of a single word.
        whitelist:            Short utterances that bypass all checks.
        check_*:              Boolean toggles for individual checks.
    """
    min_tokens: int = 3
    max_tokens: int = 60
    min_alpha_ratio: float = 0.60
    max_word_repetitions: int = 3

    whitelist: frozenset[str] = field(default_factory=lambda: frozenset({
        "keine ahnung",
        "ich weiß nicht",
        "weiß ich nicht",
        "auf jeden fall",
        "auf keinen fall",
        "natürlich",
        "genau",
        "stimmt",
        "überhaupt nicht",
        "gar nicht",
        "wie bitte",
        "bitte",
        "danke",
        "danke schön",
        "bitte schön",
        "gern geschehen",
        "entschuldigung",
        "tut mir leid",
        "es tut mir leid",
        "guten morgen",
        "guten abend",
        "guten tag",
        "auf wiedersehen",
        "tschüss",
        "hallo",
        "ja natürlich",
        "nein danke",
    }))

    check_token_count: bool = True
    check_incomplete_ending: bool = True
    check_suspicious_start: bool = True
    check_all_caps: bool = True
    check_non_alphabetic_ratio: bool = True
    check_word_repetition: bool = True


class UtteranceQualityEvaluator:
    """
    Evaluates CandidateUtterance objects against independent heuristic checks.

    Evaluation flow:
      1. Whitelist check — if matched, returns PASS immediately.
      2. All enabled checks run regardless of each other's outcome.
      3. The overall verdict is True only if every check passed.
    """

    def __init__(self, config: Optional[QualityFilterConfig] = None) -> None:
        self.config = config or QualityFilterConfig()
        self._reset_counters()

    def evaluate(self, candidate: CandidateUtterance) -> QualityDecision:
        """Evaluate a single CandidateUtterance and return a QualityDecision."""
        text = candidate.text
        tokens = text.split()

        if self._matches_whitelist(text):
            decision = QualityDecision(
                candidate=candidate,
                passed=True,
                checks=[CheckResult(
                    name="whitelist",
                    passed=True,
                    reason="Matched whitelist — admitted as a known-valid short utterance.",
                )],
            )
            self._record_metrics(decision)
            return decision

        checks: list[CheckResult] = []

        if self.config.check_token_count:
            checks.append(self._check_token_count(tokens))
        if self.config.check_incomplete_ending:
            checks.append(self._check_incomplete_ending(tokens, text))
        if self.config.check_suspicious_start:
            checks.append(self._check_suspicious_start(text))
        if self.config.check_all_caps:
            checks.append(self._check_all_caps(text))
        if self.config.check_non_alphabetic_ratio:
            checks.append(self._check_non_alphabetic_ratio(text))
        if self.config.check_word_repetition:
            checks.append(self._check_word_repetition(tokens))

        decision = QualityDecision(
            candidate=candidate,
            passed=all(c.passed for c in checks),
            checks=checks,
        )
        self._record_metrics(decision)
        return decision

    def filter(self, candidates: list[CandidateUtterance]) -> list[CandidateUtterance]:
        return [c for c in candidates if self.evaluate(c).passed]

    def evaluate_all(self, candidates: list[CandidateUtterance]) -> list[QualityDecision]:
        return [self.evaluate(c) for c in candidates]

    def filter_with_decisions(
        self,
        candidates: list[CandidateUtterance],
    ) -> tuple[list[CandidateUtterance], list[QualityDecision]]:
        decisions = self.evaluate_all(candidates)
        passed = [d.candidate for d in decisions if d.passed]
        return passed, decisions

    def _check_token_count(self, tokens: list[str]) -> CheckResult:
        n = len(tokens)
        if n < self.config.min_tokens:
            return CheckResult(
                name="token_count",
                passed=False,
                reason=(
                    f"{n} token{'s' if n != 1 else ''} — below minimum "
                    f"{self.config.min_tokens}. Add to whitelist if it is a valid short utterance."
                ),
            )
        if n > self.config.max_tokens:
            return CheckResult(
                name="token_count",
                passed=False,
                reason=(
                    f"{n} tokens — above maximum {self.config.max_tokens}. "
                    f"Likely a missed sentence boundary in the segmentation stage."
                ),
            )
        return CheckResult(
            name="token_count",
            passed=True,
            reason=f"{n} tokens (within [{self.config.min_tokens}, {self.config.max_tokens}]).",
        )

    def _check_incomplete_ending(self, tokens: list[str], text: str) -> CheckResult:
        stripped = text.rstrip()

        if stripped.endswith(","):
            return CheckResult(
                name="incomplete_ending",
                passed=False,
                reason="Ends with a comma — the clause is unfinished.",
            )
        if re.search(r"[-–—]\s*$", stripped):
            return CheckResult(
                name="incomplete_ending",
                passed=False,
                reason="Ends with a dash — the word or clause was cut off.",
            )

        if tokens:
            last_word = re.sub(r"[^\w]", "", tokens[-1], flags=re.UNICODE).lower()
            if last_word in _INCOMPLETE_ENDING_WORDS:
                return CheckResult(
                    name="incomplete_ending",
                    passed=False,
                    reason=(
                        f"Ends with '{last_word}' — a preposition, article, conjunction, "
                        f"or auxiliary that requires a following constituent."
                    ),
                )

        return CheckResult(
            name="incomplete_ending",
            passed=True,
            reason="Ending looks syntactically complete.",
        )

    def _check_suspicious_start(self, text: str) -> CheckResult:
        first = text.lstrip()[:1]

        if not first:
            return CheckResult(
                name="suspicious_start",
                passed=False,
                reason="Text is empty after stripping whitespace.",
            )

        if first.islower():
            return CheckResult(
                name="suspicious_start",
                passed=False,
                reason=(
                    f"Starts with lowercase '{first}' — in German this almost certainly "
                    f"means the utterance is a mid-sentence continuation fragment."
                ),
            )

        if first in _SUSPICIOUS_START_CHARS:
            return CheckResult(
                name="suspicious_start",
                passed=False,
                reason=(
                    f"Starts with '{first}' — punctuation at the start of a sentence "
                    f"indicates a merging or segmentation artefact."
                ),
            )

        return CheckResult(
            name="suspicious_start",
            passed=True,
            reason="Start looks normal.",
        )

    def _check_all_caps(self, text: str) -> CheckResult:
        words = [w for w in re.findall(r"[A-Za-zÄÖÜäöüß]{2,}", text)]
        if len(words) < 4:
            return CheckResult(
                name="all_caps",
                passed=True,
                reason="Too few words to evaluate all-caps ratio reliably.",
            )

        caps_count = sum(1 for w in words if w == w.upper())
        ratio = caps_count / len(words)

        if ratio >= 0.70:
            return CheckResult(
                name="all_caps",
                passed=False,
                reason=(
                    f"{caps_count}/{len(words)} words are ALL CAPS ({ratio:.0%}) — "
                    f"likely song lyrics, an annotation, or an encoding artefact."
                ),
            )

        return CheckResult(
            name="all_caps",
            passed=True,
            reason=f"{caps_count}/{len(words)} words are all-caps ({ratio:.0%}) — within threshold.",
        )

    def _check_non_alphabetic_ratio(self, text: str) -> CheckResult:
        if not text:
            return CheckResult(name="alpha_ratio", passed=False, reason="Empty text.")

        alpha = sum(1 for c in text if c.isalpha())
        ratio = alpha / len(text)

        if ratio < self.config.min_alpha_ratio:
            return CheckResult(
                name="alpha_ratio",
                passed=False,
                reason=(
                    f"Only {ratio:.0%} of characters are alphabetic "
                    f"(minimum {self.config.min_alpha_ratio:.0%}) — "
                    f"likely a symbol-heavy annotation or encoding artefact."
                ),
            )

        return CheckResult(
            name="alpha_ratio",
            passed=True,
            reason=f"{ratio:.0%} alphabetic characters (above minimum {self.config.min_alpha_ratio:.0%}).",
        )

    def _check_word_repetition(self, tokens: list[str]) -> CheckResult:
        if not tokens:
            return CheckResult(name="word_repetition", passed=True, reason="No tokens to check.")

        normalized = [
            re.sub(r"[^\w]", "", t, flags=re.UNICODE).lower()
            for t in tokens
        ]
        normalized = [t for t in normalized if t]

        if not normalized:
            return CheckResult(
                name="word_repetition",
                passed=True,
                reason="No word tokens after punctuation stripping.",
            )

        counts: dict[str, int] = {}
        for word in normalized:
            counts[word] = counts.get(word, 0) + 1

        most_frequent, max_count = max(counts.items(), key=lambda kv: kv[1])

        if max_count > self.config.max_word_repetitions:
            return CheckResult(
                name="word_repetition",
                passed=False,
                reason=(
                    f"'{most_frequent}' appears {max_count} times "
                    f"(maximum {self.config.max_word_repetitions}) — "
                    f"likely a subtitle sync artefact or song lyric."
                ),
            )

        return CheckResult(
            name="word_repetition",
            passed=True,
            reason=f"No word exceeds the repetition limit of {self.config.max_word_repetitions}.",
        )

    @property
    def metrics(self) -> FilterMetrics:
        rules: dict[str, RuleMetrics] = {
            name: RuleMetrics(
                rule_name=name,
                times_evaluated=self._rule_eval[name],
                times_rejected=self._rule_rej.get(name, 0),
            )
            for name in self._rule_eval
        }
        return FilterMetrics(
            total_evaluated=self._total_evaluated,
            total_passed=self._total_passed,
            total_rejected=self._total_evaluated - self._total_passed,
            whitelist_accepted=self._whitelist_accepted,
            rules=rules,
        )

    def reset_metrics(self) -> None:
        self._reset_counters()

    def _reset_counters(self) -> None:
        self._total_evaluated: int = 0
        self._total_passed: int = 0
        self._whitelist_accepted: int = 0
        self._rule_eval: dict[str, int] = {}
        self._rule_rej: dict[str, int] = {}

    def _record_metrics(self, decision: QualityDecision) -> None:
        self._total_evaluated += 1
        if decision.passed:
            self._total_passed += 1

        for check in decision.checks:
            self._rule_eval[check.name] = self._rule_eval.get(check.name, 0) + 1
            if not check.passed:
                self._rule_rej[check.name] = self._rule_rej.get(check.name, 0) + 1

        if any(c.name == "whitelist" for c in decision.checks):
            self._whitelist_accepted += 1

    def _matches_whitelist(self, text: str) -> bool:
        return self._normalize_text(text) in self.config.whitelist

    @staticmethod
    def _normalize_text(text: str) -> str:
        t = text.lower().strip()
        t = re.sub(r"[.!?,;:\u2026]+$", "", t).strip()
        return t
