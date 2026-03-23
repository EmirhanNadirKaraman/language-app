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

    # Exposures (populated only when record_exposures=True)
    exposures_recorded: int = 0
    exposures_deduplicated: int = 0

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
        return (
            self.ineligible_all_known
            + self.ineligible_too_many_unknowns
            + self.ineligible_no_units
        )

    def top_blocking_units(self, n: int = 5) -> list[tuple[str, int]]:
        """Return the top-N units by blocking frequency, sorted descending."""
        return Counter(self.blocking_unit_counts).most_common(n)

    def as_dict(self) -> dict:
        """Return all metrics as a flat dict for JSON serialisation or logging."""
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

    def format_summary(
        self,
        title: str = "Pipeline Run Summary",
        source: Optional[str] = None,
        user: Optional[str] = None,
        top_n_blockers: int = 5,
    ) -> str:
        """Return a formatted multi-line text summary suitable for print() or logging."""
        lines: list[str] = []
        sep = "─" * 50

        def row(label: str, value: str, indent: int = 2) -> None:
            lines.append(f"{'  ' * (indent - 1) + '  '}{label:<32}{value}")

        def section(heading: str) -> None:
            lines.append(f"\n{heading}")
            lines.append(sep)

        lines.append(title)
        lines.append("=" * len(title))
        if source:
            lines.append(f"  source : {source}")
        if user:
            lines.append(f"  user   : {user}")

        section("Ingestion → Segmentation")
        row("fragments ingested", str(self.fragments_ingested))
        row("windows merged", str(self.windows_merged))
        row("candidates segmented", str(self.candidates_segmented))

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

        section("Unit Extraction")
        avg = self.avg_units_per_utterance
        row("total units extracted", str(self.total_units_extracted))
        row("avg units / utterance", f"{avg:.1f}" if avg is not None else "—")
        if self.utterances_with_no_units:
            row("utterances with no units", str(self.utterances_with_no_units))

        section("i+1 Eligibility Filter")
        row("eligible (i+1 matches)", _fmt_count_pct(self.eligible_utterances, self.i1_rate))
        row("ineligible — all known", str(self.ineligible_all_known))
        row("ineligible — too many unknowns", str(self.ineligible_too_many_unknowns))
        if self.ineligible_no_units:
            row("ineligible — no units", str(self.ineligible_no_units))

        top = self.top_blocking_units(n=top_n_blockers)
        if top:
            lines.append(f"\n  Top {top_n_blockers} blocking units")
            for key, count in top:
                lines.append(f"    {key:<26} ×{count}")

        section("Exposures")
        row("recorded", str(self.exposures_recorded))
        if self.exposures_deduplicated:
            row("deduplicated (skipped)", str(self.exposures_deduplicated))

        return "\n".join(lines)


def _fmt_count_pct(count: int, rate: Optional[float]) -> str:
    if rate is None:
        return str(count)
    return f"{count}  ({rate:.1%})"
