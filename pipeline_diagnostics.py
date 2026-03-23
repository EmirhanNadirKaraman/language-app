"""
pipeline_diagnostics.py
-----------------------
Lightweight, in-process diagnostics for a single GermanSubtitlePipeline run.

No external telemetry stack, no threads, no I/O side effects.  All data is
plain Python — log it as JSON, print it as a text table, or assert against
it in tests.

Typical usage::

    matches, diag = pipeline.run_with_diagnostics(srt_path, user_id)
    print(diag.format_summary(source=srt_path, user=user_id))

    # Or inspect programmatically
    if diag.i1_rate is not None and diag.i1_rate < 0.10:
        print("Low i+1 rate — seed more vocabulary or relax quality thresholds")

Design notes
------------
All counters are populated by GermanSubtitlePipeline.run_with_diagnostics()
in a single pass.  The quality-filter's internal FilterMetrics is reset at
the start of each run_with_diagnostics() call, so rejection_by_rule reflects
exactly that run.  Calls to the normal run() method are not affected.

Blocking-unit tracking works by recording every unknown unit that appeared
alongside another unknown in an ineligible utterance.  The more times a unit
appears as a blocker, the more often it is stopping utterances from becoming
i+1 for other targets.  Learning those blocking units first is the highest-
leverage action for unlocking new content.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PipelineRunDiagnostics:
    """
    Metrics snapshot for one GermanSubtitlePipeline.run_with_diagnostics() call.

    All integer counters start at zero.  Derived properties (rates, top-N
    lists) are computed on demand and return None when the denominator is zero.

    Stage counters
    --------------
    fragments_ingested       Raw SubtitleFragments from parse_srt().
    windows_merged           Output of SubtitleMerger — merged groups.
    candidates_segmented     Output of SubtitleSegmenter — before quality filter.
    candidates_accepted      Passed the quality filter.
    candidates_rejected      Rejected by the quality filter.
    rejection_by_rule        Per-rule rejection counts, sourced from
                             UtteranceQualityEvaluator.metrics.  Only rules
                             with at least one rejection are included.

    Unit extraction
    ---------------
    total_units_extracted    Sum of len(extraction.units) across all accepted
                             candidates.  Includes only deduplicated units.
    utterances_with_no_units Accepted candidates for which extraction returned
                             an empty unit list (all tokens were uninformative).

    Eligibility (i+1 filter)
    ------------------------
    eligible_utterances       Candidates with exactly one unknown unit.
    ineligible_all_known      Candidates with zero unknown units.
    ineligible_too_many_unknowns  Candidates with two or more unknown units.
    ineligible_no_units       Candidates that produced no extractable units.
    blocking_unit_counts      For each unit key: how many times it appeared as
                              an extra unknown blocking i+1 eligibility for
                              some other target.

    Exposures
    ---------
    Populated only when run_with_diagnostics(record_exposures=True).

    exposures_recorded        Exposures accepted and written to the store.
    exposures_deduplicated    Exposure events rejected by the counting policy
                              as duplicates (not written to the store).
    """

    # Stage counts
    fragments_ingested: int = 0
    windows_merged: int = 0
    candidates_segmented: int = 0
    candidates_accepted: int = 0
    candidates_rejected: int = 0
    rejection_by_rule: dict[str, int] = field(default_factory=dict)

    # Unit extraction
    total_units_extracted: int = 0
    utterances_with_no_units: int = 0

    # i+1 eligibility
    eligible_utterances: int = 0
    ineligible_all_known: int = 0
    ineligible_too_many_unknowns: int = 0
    ineligible_no_units: int = 0
    blocking_unit_counts: dict[str, int] = field(default_factory=dict)

    # Exposures
    exposures_recorded: int = 0
    exposures_deduplicated: int = 0

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def quality_acceptance_rate(self) -> Optional[float]:
        """Fraction of segmented candidates that passed the quality filter."""
        if self.candidates_segmented == 0:
            return None
        return self.candidates_accepted / self.candidates_segmented

    @property
    def i1_rate(self) -> Optional[float]:
        """Fraction of quality-accepted candidates that are i+1 eligible."""
        if self.candidates_accepted == 0:
            return None
        return self.eligible_utterances / self.candidates_accepted

    @property
    def avg_units_per_utterance(self) -> Optional[float]:
        """Average units extracted per candidate that had at least one unit."""
        denominator = self.candidates_accepted - self.utterances_with_no_units
        if denominator <= 0:
            return None
        return self.total_units_extracted / denominator

    @property
    def total_ineligible(self) -> int:
        """Total candidates that did not become i+1 matches."""
        return (
            self.ineligible_all_known
            + self.ineligible_too_many_unknowns
            + self.ineligible_no_units
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def top_blocking_units(self, n: int = 5) -> list[tuple[str, int]]:
        """
        Return the top-N units by blocking frequency, sorted descending.

        Each entry is (unit_key, count).  A unit with count N appeared as an
        extra unknown in N utterances, preventing those utterances from
        reaching i+1 eligibility.  These are the highest-leverage units to
        learn: resolving them would unlock the most new content.

        Args:
            n: Maximum number of entries to return.

        Returns:
            List of (key, count) pairs, most frequent first.
        """
        return Counter(self.blocking_unit_counts).most_common(n)

    def as_dict(self) -> dict:
        """
        Return all metrics as a flat dict for JSON serialisation or logging.

        All values are primitive Python types (int, float, or list).
        """
        return {
            "fragments_ingested":           self.fragments_ingested,
            "windows_merged":               self.windows_merged,
            "candidates_segmented":         self.candidates_segmented,
            "candidates_accepted":          self.candidates_accepted,
            "candidates_rejected":          self.candidates_rejected,
            "rejection_by_rule":            dict(self.rejection_by_rule),
            "total_units_extracted":        self.total_units_extracted,
            "utterances_with_no_units":     self.utterances_with_no_units,
            "avg_units_per_utterance":      self.avg_units_per_utterance,
            "eligible_utterances":          self.eligible_utterances,
            "ineligible_all_known":         self.ineligible_all_known,
            "ineligible_too_many_unknowns": self.ineligible_too_many_unknowns,
            "ineligible_no_units":          self.ineligible_no_units,
            "quality_acceptance_rate":      self.quality_acceptance_rate,
            "i1_rate":                      self.i1_rate,
            "top_blocking_units":           self.top_blocking_units(),
            "exposures_recorded":           self.exposures_recorded,
            "exposures_deduplicated":       self.exposures_deduplicated,
        }

    # ------------------------------------------------------------------
    # Human-readable summary
    # ------------------------------------------------------------------

    def format_summary(
        self,
        title: str = "Pipeline Run Summary",
        source: Optional[str] = None,
        user: Optional[str] = None,
        top_n_blockers: int = 5,
    ) -> str:
        """
        Return a formatted multi-line text summary suitable for print() or logging.

        Args:
            title:          Header line.
            source:         Optional SRT source path or description.
            user:           Optional user identifier.
            top_n_blockers: Number of top blocking units to show.

        Returns:
            Multi-line string.  Sections with all-zero counts are still
            shown so the output format is stable across runs.
        """
        lines: list[str] = []
        sep = "─" * 50

        def row(label: str, value: str, indent: int = 2) -> None:
            lines.append(f"{'  ' * (indent - 1) + '  '}{label:<32}{value}")

        def section(heading: str) -> None:
            lines.append(f"\n{heading}")
            lines.append(sep)

        # Header
        lines.append(title)
        lines.append("=" * len(title))
        if source:
            lines.append(f"  source : {source}")
        if user:
            lines.append(f"  user   : {user}")

        # Stage funnel
        section("Ingestion → Segmentation")
        row("fragments ingested", str(self.fragments_ingested))
        row("windows merged", str(self.windows_merged))
        row("candidates segmented", str(self.candidates_segmented))

        # Quality filter
        section("Quality Filter")
        acc_rate = self.quality_acceptance_rate
        rej_rate = None if acc_rate is None else 1.0 - acc_rate
        row("accepted", _fmt_count_pct(self.candidates_accepted, acc_rate))
        row("rejected", _fmt_count_pct(self.candidates_rejected, rej_rate))
        if self.rejection_by_rule:
            for rule, count in sorted(
                self.rejection_by_rule.items(), key=lambda kv: -kv[1]
            ):
                row(rule, str(count), indent=3)

        # Unit extraction
        section("Unit Extraction")
        avg = self.avg_units_per_utterance
        row("total units extracted", str(self.total_units_extracted))
        row("avg units / utterance", f"{avg:.1f}" if avg is not None else "—")
        if self.utterances_with_no_units:
            row("utterances with no units", str(self.utterances_with_no_units))

        # i+1 eligibility
        section("i+1 Eligibility Filter")
        row("eligible (i+1 matches)", _fmt_count_pct(self.eligible_utterances, self.i1_rate))
        row("ineligible — all known", str(self.ineligible_all_known))
        row("ineligible — too many unknowns", str(self.ineligible_too_many_unknowns))
        if self.ineligible_no_units:
            row("ineligible — no units", str(self.ineligible_no_units))

        # Blocking units
        top = self.top_blocking_units(n=top_n_blockers)
        if top:
            lines.append(f"\n  Top {top_n_blockers} blocking units")
            for key, count in top:
                lines.append(f"    {key:<26} ×{count}")

        # Exposures
        section("Exposures")
        row("recorded", str(self.exposures_recorded))
        if self.exposures_deduplicated:
            row("deduplicated (skipped)", str(self.exposures_deduplicated))

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt_count_pct(count: int, rate: Optional[float]) -> str:
    """Format a count with an optional percentage: '18  (72.0%)'."""
    if rate is None:
        return str(count)
    return f"{count}  ({rate:.1%})"
