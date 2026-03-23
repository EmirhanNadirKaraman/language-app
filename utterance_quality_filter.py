"""
utterance_quality_filter.py
---------------------------
Quality-filtering stage for candidate utterances extracted from subtitle windows.

Takes CandidateUtterance objects (output of SubtitleSegmenter) and evaluates
each one against a set of independent heuristic checks, producing a structured
QualityDecision that records the outcome of every check and why.

Design principles:
  - Each heuristic lives in its own method — easy to disable, tune, or test.
  - Every rejection carries a human-readable reason — useful during tuning.
  - The whitelist lets you unconditionally admit known-valid short utterances
    that would otherwise fail the token count or other length checks.
  - No dependency on spaCy at this stage; all checks use the raw text string
    and whitespace-split tokens, which is sufficient for surface heuristics.

Usage:
    from utterance_quality_filter import QualityFilterConfig, UtteranceQualityEvaluator

    evaluator = UtteranceQualityEvaluator()
    passed, decisions = evaluator.filter_with_decisions(candidates)

    # Inspect rejections
    for d in decisions:
        if not d.passed:
            print(d.candidate.text, "→", d.failure_reasons)

    # Inspect per-rule rejection counts after a batch run
    print(evaluator.metrics.format_table())

    # Most aggressive rule
    top = evaluator.metrics.most_aggressive_rules()[0]
    print(f"{top.rule_name} rejected {top.times_rejected} utterances ({top.rejection_rate:.1%})")

    # Reset counters between batches
    evaluator.reset_metrics()
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from subtitle_segmenter import CandidateUtterance


# ---------------------------------------------------------------------------
# Module-level linguistic constants (German)
# ---------------------------------------------------------------------------

# Words that make an utterance syntactically incomplete when they appear last.
# A sentence cannot end with a bare preposition, article, or subordinating
# conjunction — it means the clause was cut off mid-thought.
_INCOMPLETE_ENDING_WORDS: frozenset[str] = frozenset({
    # Coordinating conjunctions
    "und", "oder", "aber", "denn", "sondern",
    # Subordinating conjunctions
    "weil", "dass", "wenn", "ob", "als", "während", "obwohl",
    "damit", "sodass", "nachdem", "bevor", "bis", "seit", "falls",
    "sofern", "solange", "sobald", "indem", "seitdem",
    # Prepositions
    "in", "an", "auf", "über", "unter", "vor", "hinter", "neben",
    "zwischen", "mit", "nach", "bei", "von", "zu", "aus", "durch",
    "für", "gegen", "ohne", "um", "wegen", "trotz",
    # Indefinite articles — a sentence cannot end with "ein" ("Das ist ein." ✗)
    # Definite articles are intentionally excluded: "das", "die", "der", "dem",
    # "den", "des" also function as demonstrative pronouns at sentence-final
    # position ("Was war das?", "Wem gehört die?") and would generate false
    # positives on common German questions and responses.
    "ein", "eine", "einen", "einem", "einer", "eines",
    # Auxiliaries / modals whose presence at the end signals a missing infinitive
    "haben", "sein", "werden", "können", "müssen", "dürfen",
    "sollen", "wollen", "mögen",
    # Relative and interrogative words that open a dependent clause
    "dessen", "deren", "was", "wer", "wie", "wo", "wohin",
})

# Characters that should never begin a well-formed sentence — their presence
# indicates a merging artefact or a mis-segmented continuation.
_SUSPICIOUS_START_CHARS: frozenset[str] = frozenset({",", ";", ":", "-", "–", "—", "…"})


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    """
    The outcome of a single quality check.

    Attributes:
        name:   Short machine-readable identifier (e.g. "token_count").
        passed: True if the check found no problem, False if the utterance
                failed this check.
        reason: Human-readable explanation of the outcome — always filled,
                whether the check passed or failed, to support easy debugging.
    """
    name: str
    passed: bool
    reason: str


@dataclass
class QualityDecision:
    """
    The aggregated quality evaluation for one CandidateUtterance.

    An utterance passes if and only if every check in `checks` passed.
    If the utterance was admitted via the whitelist, `checks` contains a
    single whitelist CheckResult and no other checks were run.

    Attributes:
        candidate: The utterance that was evaluated.
        passed:    Overall verdict — True only if all checks passed.
        checks:    Full record of every check that was run, in order.
    """
    candidate: CandidateUtterance
    passed: bool
    checks: list[CheckResult]

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def failure_reasons(self) -> list[str]:
        """Convenience: just the reason strings for failed checks."""
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
    """
    Rejection statistics for a single quality check, as a read-only snapshot.

    Attributes:
        rule_name:       Machine-readable name matching CheckResult.name.
        times_evaluated: Number of utterances this check was run against.
                         Disabled checks and whitelisted utterances are not
                         counted here — only utterances that reached the check.
        times_rejected:  Number of utterances this check caused to fail.
                         One utterance can fail multiple checks simultaneously.
    """
    rule_name: str
    times_evaluated: int
    times_rejected: int

    @property
    def rejection_rate(self) -> float:
        """Fraction of evaluated utterances that this rule rejected."""
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
    """
    A point-in-time snapshot of quality-filter statistics.

    Produced by UtteranceQualityEvaluator.metrics; does not update after
    creation.  Create a new snapshot after each batch if you need fresh data.

    Attributes:
        total_evaluated:   Total calls to evaluate() since last reset.
        total_passed:      Utterances that cleared all checks (includes whitelist).
        total_rejected:    Utterances that failed at least one check.
        whitelist_accepted: Utterances admitted via whitelist (subset of total_passed).
        rules:             Per-rule statistics, keyed by rule name, ordered by
                           number of rejections descending.  Treat as read-only.
    """

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
        """Fraction of all evaluated utterances that were rejected."""
        if self.total_evaluated == 0:
            return 0.0
        return self.total_rejected / self.total_evaluated

    def most_aggressive_rules(self) -> list[RuleMetrics]:
        """
        Return all rules sorted by times_rejected descending.

        Use this to identify which check is cutting the most candidates so
        you can decide whether to relax its threshold or accept the loss.
        """
        return sorted(self.rules.values(), key=lambda r: r.times_rejected, reverse=True)

    def as_dict(self) -> dict:
        """
        Export all metrics as a plain dict.

        Suitable for JSON serialisation, structured logging, or passing to a
        dashboard.  All values are primitive types (int or float).
        """
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
        """
        Return a human-readable per-rule breakdown table.

        Example output::

            Total : 1,234 evaluated — 891 passed, 343 rejected (27.8%)
            Whitelist admitted: 12

              rule                   evaluated   rejected     rate
              ──────────────────────────────────────────────────
              token_count                1,222        287    23.5%
              incomplete_ending          1,222        112     9.2%
              suspicious_start           1,222         98     8.0%
              alpha_ratio                1,222         34     2.8%
              all_caps                   1,222         18     1.5%
              word_repetition            1,222          7     0.6%
              whitelist                  1,234         —        —
        """
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
                # Whitelist entries are always accepted — show count but no rate
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
        min_tokens:
            Utterances with fewer whitespace-split tokens are rejected.
            Default 3 requires at least a minimal subject-verb pair plus one
            more word. Lower this if you want to keep very short responses
            not covered by the whitelist (e.g. "Ja." or "Nein.").

        max_tokens:
            Utterances with more tokens than this are rejected. Extremely
            long candidates usually indicate a missed sentence boundary in
            the segmentation stage and are rarely useful as learning units.

        min_alpha_ratio:
            Minimum fraction of characters that must be alphabetic. Text
            below this threshold is likely a symbol-heavy annotation remnant
            (e.g. "♪ la la ♪") or an uncleaned bracketed label.
            Counted over the full text including spaces and punctuation.

        max_word_repetitions:
            If any single word (normalised, case-folded) appears more than
            this many times, the utterance is flagged as a subtitle sync
            artefact or song lyric. Set high (e.g. 99) to disable.

        whitelist:
            Set of normalised short utterances that bypass all checks.
            Normalisation: lowercase + strip trailing sentence punctuation.
            Add entries for common conversational fragments in your target
            domain that would otherwise fail min_tokens.

        check_*:
            Boolean toggles to disable individual checks during ablation
            or when adapting to a specific subtitle corpus.
    """
    min_tokens: int = 3
    max_tokens: int = 60
    min_alpha_ratio: float = 0.60
    max_word_repetitions: int = 3

    whitelist: frozenset[str] = field(default_factory=lambda: frozenset({
        # Common short but complete German utterances
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

    # Feature toggles
    check_token_count: bool = True
    check_incomplete_ending: bool = True
    check_suspicious_start: bool = True
    check_all_caps: bool = True
    check_non_alphabetic_ratio: bool = True
    check_word_repetition: bool = True


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class UtteranceQualityEvaluator:
    """
    Evaluates CandidateUtterance objects against independent heuristic checks
    and returns structured QualityDecision objects.

    Evaluation flow:
      1. Whitelist check. If the normalised text matches a whitelist entry,
         a PASS decision is returned immediately and no other checks run.
         This is the intended bypass for known-valid short utterances.

      2. All enabled checks run regardless of each other's outcome.
         This "run all" design is intentional: during corpus tuning, seeing
         every reason a candidate was rejected (not just the first) is far
         more useful than short-circuiting at the first failure.

      3. The overall verdict is True only if every check passed.

    Tradeoffs:
      - Token counting uses str.split() (whitespace tokens), not spaCy tokens.
        This is slightly inaccurate for punctuation-attached words ("Hause."
        counts as one token, same as "Hause"). Acceptable for heuristics.
      - Checks are language-specific to German but most generalize to other
        highly-inflected languages with similar subtitle conventions.
      - The all-caps check uses a 70 % uppercase-word ratio with a minimum
        word count to avoid false positives from sentences with abbreviations.
    """

    def __init__(self, config: Optional[QualityFilterConfig] = None) -> None:
        self.config = config or QualityFilterConfig()
        self._reset_counters()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, candidate: CandidateUtterance) -> QualityDecision:
        """
        Evaluate a single CandidateUtterance and return a QualityDecision.

        If the text matches the whitelist, all other checks are skipped and
        the decision is PASS. Otherwise every enabled check is run and the
        results are recorded.
        """
        text = candidate.text
        tokens = text.split()

        # --- Whitelist fast path ---
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

        # --- Run all enabled checks ---
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
        """Return only the candidates that pass quality evaluation."""
        return [c for c in candidates if self.evaluate(c).passed]

    def evaluate_all(self, candidates: list[CandidateUtterance]) -> list[QualityDecision]:
        """Return a QualityDecision for every candidate, pass or fail."""
        return [self.evaluate(c) for c in candidates]

    def filter_with_decisions(
        self,
        candidates: list[CandidateUtterance],
    ) -> tuple[list[CandidateUtterance], list[QualityDecision]]:
        """
        Return both the filtered candidates and the full decision list.

        Useful during tuning: the decisions let you inspect every rejection
        without running evaluation twice.
        """
        decisions = self.evaluate_all(candidates)
        passed = [d.candidate for d in decisions if d.passed]
        return passed, decisions

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_token_count(self, tokens: list[str]) -> CheckResult:
        """
        Reject utterances that are too short or too long.

        Too short: likely a fragment or a lone interjection not in the whitelist.
        Too long:  likely a missed sentence boundary upstream — not a useful
                   learning unit and usually hard to comprehend in isolation.
        """
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
        """
        Reject utterances that are syntactically open at the end.

        Two sub-checks:
          1. Punctuation ending: a trailing comma, dash, or en-dash signals
             that the clause was cut off mid-sentence.
          2. Word ending: certain German function words (prepositions, articles,
             subordinating conjunctions, auxiliaries) cannot end a complete
             utterance — their presence last means the head noun, verb, or
             infinitive is missing.

        Tradeoff: "Bis morgen." ends with "morgen" not "bis", so it passes.
        A fragment like "Er geht nach" ends with "nach" (preposition) and fails.
        """
        stripped = text.rstrip()

        # Sub-check 1: punctuation-level incomplete ending
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

        # Sub-check 2: syntactically open last word
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
        """
        Reject utterances that begin in a way that suggests fragmentation.

        Two sub-checks:
          1. Lowercase start: In German, every sentence-initial word is
             capitalised (proper nouns, nouns, all sentence starters). A
             lowercase first character is a near-certain indicator that this
             utterance is a continuation fragment, not a full utterance.
          2. Punctuation start: Leading commas, semicolons, or dashes are
             merging artefacts — a sentence cannot begin with these.

        Note: starting with "Und" or "Aber" (uppercase) is intentionally NOT
        flagged. These are stylistically common in spoken German.
        """
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
        """
        Reject utterances where the majority of words are fully uppercase.

        ALL-CAPS text in subtitles typically indicates one of:
          - Song lyrics or chanted dialogue ("ICH WILL DAS NICHT")
          - Scene annotations not caught by the cleaner ("RÜCKBLENDE")
          - Shouted lines that some SRT encoders mark in caps

        The check requires at least 4 multi-character words to fire, to avoid
        false positives from sentences that happen to contain one or two
        legitimate abbreviations (EU, USA, UNO).

        Tradeoff: a sentence like "UNO, EU und NATO beschlossen" has 3/4 words
        in all-caps but the threshold of 0.70 still passes it (75 % — just
        above threshold). Lower the all_caps_ratio constant if that matters.
        """
        # Extract only multi-character alphabetic words
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
        """
        Reject utterances where alphabetic characters make up less than
        min_alpha_ratio of the total character count.

        Low alpha ratios catch:
          - Music-note symbols ("♪ La la la ♪")
          - Uncleaned bracket annotations ("[Applaus] [Musik]")
          - Purely punctuation or number-heavy text

        Tradeoff: ellipsis-heavy text ("Ja... ich weiß nicht.") scores ~67 %,
        which passes the default 60 % threshold. Reduce min_alpha_ratio if you
        are processing hesitant speech with frequent "...".
        """
        if not text:
            return CheckResult(
                name="alpha_ratio",
                passed=False,
                reason="Empty text.",
            )

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
        """
        Reject utterances where any single word appears excessively often.

        Excessive repetition in subtitle text usually indicates:
          - Subtitle sync artefacts ("ja ja ja ja ja")
          - Song lyrics with a repeated refrain ("la la la la")
          - Mismerged duplicate blocks

        Normalisation strips punctuation and lowercases before counting so
        "Ja," and "Ja" and "ja" all count toward the same word.

        Tradeoff: legitimate emphasis ("nein nein nein!") can trigger this.
        Raise max_word_repetitions if you observe too many false positives
        for your specific corpus.
        """
        if not tokens:
            return CheckResult(
                name="word_repetition",
                passed=True,
                reason="No tokens to check.",
            )

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

    # ------------------------------------------------------------------
    # Metrics API
    # ------------------------------------------------------------------

    @property
    def metrics(self) -> FilterMetrics:
        """
        Return a FilterMetrics snapshot of all statistics since the last reset.

        The snapshot is computed from live counters at call time and does not
        update if evaluation continues afterwards.  Call reset_metrics() to
        start a fresh measurement window (e.g. between episodes or batches).
        """
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
        """
        Reset all accumulated statistics to zero.

        Call this between measurement windows — for example between episodes,
        corpus segments, or A/B config experiments.
        """
        self._reset_counters()

    # ------------------------------------------------------------------
    # Private: metrics internals
    # ------------------------------------------------------------------

    def _reset_counters(self) -> None:
        self._total_evaluated: int = 0
        self._total_passed: int = 0
        self._whitelist_accepted: int = 0
        # rule_name → count of utterances evaluated / rejected by that rule
        self._rule_eval: dict[str, int] = {}
        self._rule_rej: dict[str, int] = {}

    def _record_metrics(self, decision: QualityDecision) -> None:
        """
        Update live counters from a completed QualityDecision.

        Called once at the end of every evaluate() call, after the decision
        object is fully built.  Reads CheckResult names and outcomes — no
        coupling to individual check implementations.
        """
        self._total_evaluated += 1
        if decision.passed:
            self._total_passed += 1

        for check in decision.checks:
            self._rule_eval[check.name] = self._rule_eval.get(check.name, 0) + 1
            if not check.passed:
                self._rule_rej[check.name] = self._rule_rej.get(check.name, 0) + 1

        if any(c.name == "whitelist" for c in decision.checks):
            self._whitelist_accepted += 1

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _matches_whitelist(self, text: str) -> bool:
        """Return True if the normalised text is in the configured whitelist."""
        return self._normalize_text(text) in self.config.whitelist

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalise text for whitelist lookup.

        Steps:
          1. Lowercase
          2. Strip leading/trailing whitespace
          3. Strip trailing sentence-final punctuation (. ! ? , ; : …)

        This lets whitelist entries be written without punctuation:
        "keine ahnung" matches "Keine Ahnung.", "Keine Ahnung!" etc.
        """
        t = text.lower().strip()
        t = re.sub(r"[.!?,;:\u2026]+$", "", t).strip()
        return t


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _make_candidate(text: str) -> CandidateUtterance:
    """Create a minimal CandidateUtterance for demo purposes."""
    from subtitle_merger import MergedSubtitleWindow, SubtitleFragment
    window = MergedSubtitleWindow(
        fragments=[SubtitleFragment(text=text, start_time=0.0, end_time=2.0)],
        text=text,
        start_time=0.0,
        end_time=2.0,
    )
    return CandidateUtterance(
        text=text,
        start_time=0.0,
        end_time=2.0,
        source_window=window,
        char_start=0,
        char_end=len(text),
    )


def _demo() -> None:
    evaluator = UtteranceQualityEvaluator()

    cases: list[tuple[str, str]] = [
        # (label, text)
        ("Good utterance",           "Ich gehe morgen ins Kino mit meiner Freundin."),
        ("Good — long sentence",     "Das ist wirklich eine sehr interessante Frage, über die ich noch nie nachgedacht habe."),
        ("Whitelist: short phrase",  "Keine Ahnung."),
        ("Whitelist: polite reply",  "Danke schön!"),
        ("Too short (1 token)",      "Vielleicht."),
        ("Too short (2 tokens)",     "Sehr schön."),
        ("Incomplete: comma end",    "Wenn du möchtest,"),
        ("Incomplete: dash end",     "Das war ein sehr langer –"),
        ("Incomplete: preposition",  "Ich warte auf"),
        ("Incomplete: article end",  "Er kauft die"),
        ("Lowercase start",          "weil ich nicht kommen kann."),
        ("Punct start",              ", und dann ging er."),
        ("ALL CAPS lyrics",          "ICH WILL DICH NICHT VERLIEREN NIEMALS"),
        ("Symbol-heavy annotation",  "♪ La la la la ♪"),
        ("Word repetition",          "ja ja ja ja ja nein"),
        ("Good: with abbreviation",  "Die EU und die UNO haben reagiert."),
    ]

    print(f"{'─' * 70}")
    print(f"  {'TEXT':<42}  {'VERDICT':<6}  REASON")
    print(f"{'─' * 70}")

    for label, text in cases:
        decision = evaluator.evaluate(_make_candidate(text))
        verdict = "PASS" if decision.passed else "FAIL"
        reasons = "; ".join(decision.failure_reasons) or "—"
        preview = text if len(text) <= 40 else text[:37] + "..."
        print(f"  {preview:<42}  {verdict:<6}  {reasons}")

    print(f"{'─' * 70}")

    # Demonstrate filter_with_decisions for batch tuning
    print("\n  filter_with_decisions() summary:")
    all_candidates = [_make_candidate(text) for _, text in cases]
    passed, decisions = evaluator.filter_with_decisions(all_candidates)
    n_pass = sum(1 for d in decisions if d.passed)
    n_fail = sum(1 for d in decisions if not d.passed)
    print(f"  {len(all_candidates)} candidates → {n_pass} passed, {n_fail} rejected")

    # ── Per-rule metrics ───────────────────────────────────────────────
    print("\n" + "─" * 70)
    print("  FILTER METRICS")
    print("─" * 70)
    print(evaluator.metrics.format_table())

    print("\n  Most aggressive rule:")
    top = evaluator.metrics.most_aggressive_rules()[0]
    print(f"  {top}")

    print("\n  as_dict() (for logging / JSON):")
    import json
    print(json.dumps(evaluator.metrics.as_dict(), indent=4))

    # Reset between batches
    evaluator.reset_metrics()
    print(f"\n  After reset_metrics(): {evaluator.metrics}")

    # Demonstrate toggling a check off
    print("\n" + "─" * 70)
    print("  With check_suspicious_start=False:")
    relaxed_cfg = QualityFilterConfig(check_suspicious_start=False)
    relaxed = UtteranceQualityEvaluator(relaxed_cfg)
    d = relaxed.evaluate(_make_candidate("weil ich nicht kommen kann."))
    print(f"  'weil ich nicht kommen kann.' → {'PASS' if d.passed else 'FAIL'}")
    if not d.passed:
        print(f"  Still fails: {d.failure_reasons}")


if __name__ == "__main__":
    _demo()
