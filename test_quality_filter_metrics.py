"""
test_quality_filter_metrics.py
------------------------------
Pytest suite for the per-rule rejection metrics instrumentation added to
UtteranceQualityEvaluator.

Why this matters for subtitle-pipeline tuning
---------------------------------------------
Subtitle corpora are messy.  A strict token_count threshold might silently
discard 30 % of candidates; a suspicious_start check might fire on every
continuation fragment in the corpus.  Without per-rule counts you can't tell
which check is responsible, so you tune blindly.  These tests verify that the
instrumentation is accurate enough to be trusted during that tuning process —
specifically that every counter increments exactly once per triggering event,
that the whitelist fast-path is tracked separately from normal passes, and
that the total_passed + total_rejected invariant is always maintained.

Coverage
--------
  TestValidUtteranceAccepted     — valid sentence increments total_passed
  TestSingleRuleRejection        — each rule increments its own counter only
  TestMultipleRuleCounters       — independent counters accumulate correctly
  TestWhitelistMetrics           — whitelist path tracked via whitelist_accepted
  TestMetricsConsistency         — invariants hold across N mixed evaluations
  TestResetMetrics               — reset_metrics() zeroes all counters cleanly
  TestFormatTable                — format_table() produces sane human output
"""
import pytest

from subtitle_merger import MergedSubtitleWindow, SubtitleFragment
from subtitle_segmenter import CandidateUtterance
from utterance_quality_filter import (
    FilterMetrics,
    QualityFilterConfig,
    RuleMetrics,
    UtteranceQualityEvaluator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candidate(text: str) -> CandidateUtterance:
    window = MergedSubtitleWindow(
        fragments=[SubtitleFragment(text=text, start_time=0.0, end_time=3.0)],
        text=text,
        start_time=0.0,
        end_time=3.0,
    )
    return CandidateUtterance(
        text=text,
        start_time=0.0,
        end_time=3.0,
        source_window=window,
        char_start=0,
        char_end=len(text),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evaluator() -> UtteranceQualityEvaluator:
    """Fresh evaluator with default config for each test."""
    return UtteranceQualityEvaluator()


# ---------------------------------------------------------------------------
# TestValidUtteranceAccepted
# A well-formed German sentence must increase total_passed and populate all
# six default rule entries (but not whitelist_accepted).
# ---------------------------------------------------------------------------

class TestValidUtteranceAccepted:

    def test_total_evaluated_increments_after_one_call(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        assert evaluator.metrics.total_evaluated == 1

    def test_total_passed_increments_for_valid_utterance(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        assert evaluator.metrics.total_passed == 1

    def test_total_rejected_zero_for_valid_utterance(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        assert evaluator.metrics.total_rejected == 0

    def test_overall_rejection_rate_zero_after_clean_pass(self, evaluator):
        evaluator.evaluate(make_candidate("Das Buch liegt auf dem Tisch."))
        assert evaluator.metrics.overall_rejection_rate == 0.0

    def test_all_six_default_checks_appear_in_rules(self, evaluator):
        evaluator.evaluate(make_candidate("Sie arbeitet sehr hart und lernt viel."))
        m = evaluator.metrics
        for rule in (
            "token_count", "incomplete_ending", "suspicious_start",
            "all_caps", "alpha_ratio", "word_repetition",
        ):
            assert rule in m.rules, f"Expected rule '{rule}' in metrics after a normal evaluation"

    def test_valid_utterance_has_zero_rejections_for_all_rules(self, evaluator):
        evaluator.evaluate(make_candidate("Er liest ein spannendes Buch."))
        m = evaluator.metrics
        for rule_name, rm in m.rules.items():
            assert rm.times_rejected == 0, f"Rule '{rule_name}' should not reject a clean sentence"


# ---------------------------------------------------------------------------
# TestSingleRuleRejection
# Each check has a reliable German example that triggers exactly that rule
# and no others.  The negative assertions verify the counter is precise —
# a rule must not borrow rejection credit from an unrelated failure.
# ---------------------------------------------------------------------------

class TestSingleRuleRejection:

    def test_token_count_rejection_increments_token_count_counter(self, evaluator):
        # 1 token — below min_tokens=3; every other check passes.
        evaluator.evaluate(make_candidate("Vielleicht."))
        assert evaluator.metrics.rules["token_count"].times_rejected == 1
        assert evaluator.metrics.total_rejected == 1

    def test_token_count_rejection_does_not_fire_other_counters(self, evaluator):
        evaluator.evaluate(make_candidate("Vielleicht."))
        m = evaluator.metrics
        for rule in ("incomplete_ending", "suspicious_start",
                     "all_caps", "alpha_ratio", "word_repetition"):
            assert m.rules[rule].times_rejected == 0, (
                f"Rule '{rule}' should not be rejected for a short-but-clean token"
            )

    def test_incomplete_ending_rejection_increments_correct_counter(self, evaluator):
        # 3 tokens, ends with preposition "auf" — incomplete_ending fires only.
        evaluator.evaluate(make_candidate("Ich warte auf"))
        assert evaluator.metrics.rules["incomplete_ending"].times_rejected == 1

    def test_suspicious_start_rejection_increments_correct_counter(self, evaluator):
        # Lowercase-initial German — signals a mid-sentence fragment.
        evaluator.evaluate(make_candidate("und dann kam er nach Hause."))
        assert evaluator.metrics.rules["suspicious_start"].times_rejected == 1

    def test_word_repetition_rejection_increments_correct_counter(self, evaluator):
        # "ja" repeated 5 times, exceeds max_word_repetitions=3.
        # Uppercase start so suspicious_start does not also fire.
        evaluator.evaluate(make_candidate("Ja ja ja ja ja nein."))
        assert evaluator.metrics.rules["word_repetition"].times_rejected == 1

    def test_alpha_ratio_rejection_increments_correct_counter(self, evaluator):
        # "♪ La la ♪": 4 alpha chars out of 9 total ≈ 44 % < min 60 %.
        # suspicious_start passes (♪ is neither lowercase nor in _SUSPICIOUS_START_CHARS).
        evaluator.evaluate(make_candidate("♪ La la ♪"))
        assert evaluator.metrics.rules["alpha_ratio"].times_rejected == 1

    def test_all_caps_rejection_increments_correct_counter(self, evaluator):
        # 6/6 multi-char words are ALL CAPS → 100 % ≥ threshold 70 %.
        evaluator.evaluate(make_candidate("ICH WILL DICH NICHT VERLIEREN NIEMALS"))
        assert evaluator.metrics.rules["all_caps"].times_rejected == 1

    def test_rejection_rate_is_one_for_the_single_fired_rule(self, evaluator):
        evaluator.evaluate(make_candidate("Vielleicht."))
        assert evaluator.metrics.rules["token_count"].rejection_rate == 1.0

    def test_rejection_rate_is_zero_for_unfired_rule(self, evaluator):
        evaluator.evaluate(make_candidate("Vielleicht."))
        assert evaluator.metrics.rules["word_repetition"].rejection_rate == 0.0


# ---------------------------------------------------------------------------
# TestMultipleRuleCounters
# Different utterances hitting different rules must keep their counters
# independent.  Totals must be additive.
# ---------------------------------------------------------------------------

class TestMultipleRuleCounters:

    def test_two_different_rules_each_fire_exactly_once(self, evaluator):
        evaluator.evaluate(make_candidate("Vielleicht."))          # token_count
        evaluator.evaluate(make_candidate("Ich warte auf"))        # incomplete_ending
        m = evaluator.metrics
        assert m.rules["token_count"].times_rejected == 1
        assert m.rules["incomplete_ending"].times_rejected == 1

    def test_total_evaluated_counts_all_utterances(self, evaluator):
        for text in (
            "Vielleicht.",                       # rejected
            "Ich warte auf",                     # rejected
            "Ich gehe morgen ins Kino.",         # passed
        ):
            evaluator.evaluate(make_candidate(text))
        assert evaluator.metrics.total_evaluated == 3

    def test_total_passed_plus_rejected_equals_total_evaluated(self, evaluator):
        for text in (
            "Vielleicht.",
            "Ich warte auf",
            "Ich gehe morgen ins Kino.",
            "Das Wetter ist heute sehr schön.",
        ):
            evaluator.evaluate(make_candidate(text))
        m = evaluator.metrics
        assert m.total_passed + m.total_rejected == m.total_evaluated

    def test_rule_evaluated_count_equals_number_of_non_whitelist_calls(self, evaluator):
        # All three sentences reach the heuristic checks (none match the whitelist).
        for text in (
            "Ich gehe morgen ins Kino.",
            "Das Buch liegt auf dem Tisch.",
            "Vielleicht.",
        ):
            evaluator.evaluate(make_candidate(text))
        assert evaluator.metrics.rules["token_count"].times_evaluated == 3

    def test_same_rule_rejected_multiple_times_accumulates(self, evaluator):
        # Three one-token utterances that are not on the whitelist.
        for text in ("Vielleicht.", "Schön.", "Wirklich."):
            evaluator.evaluate(make_candidate(text))
        assert evaluator.metrics.rules["token_count"].times_rejected == 3


# ---------------------------------------------------------------------------
# TestWhitelistMetrics
# The whitelist fast-path skips every heuristic check.  Whitelist hits must
# increment total_passed and whitelist_accepted but leave heuristic rule
# entries absent from the rules dict.
# ---------------------------------------------------------------------------

class TestWhitelistMetrics:

    def test_whitelist_match_increments_total_passed(self, evaluator):
        evaluator.evaluate(make_candidate("Keine Ahnung."))
        assert evaluator.metrics.total_passed == 1

    def test_whitelist_match_increments_whitelist_accepted(self, evaluator):
        evaluator.evaluate(make_candidate("Keine Ahnung."))
        assert evaluator.metrics.whitelist_accepted == 1

    def test_whitelist_match_does_not_increment_total_rejected(self, evaluator):
        evaluator.evaluate(make_candidate("Keine Ahnung."))
        assert evaluator.metrics.total_rejected == 0

    def test_whitelist_fast_path_skips_all_heuristic_checks(self, evaluator):
        # Only the "whitelist" rule entry should exist — none of the six checks.
        evaluator.evaluate(make_candidate("Danke schön!"))
        m = evaluator.metrics
        for rule in ("token_count", "incomplete_ending", "suspicious_start",
                     "all_caps", "alpha_ratio", "word_repetition"):
            assert rule not in m.rules, (
                f"Rule '{rule}' must not appear when only a whitelist utterance was evaluated"
            )

    def test_whitelist_accepted_not_incremented_for_normal_pass(self, evaluator):
        # A long valid sentence passes via the normal path — not the whitelist.
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino mit meiner Freundin."))
        assert evaluator.metrics.whitelist_accepted == 0

    def test_whitelist_and_normal_pass_tracked_separately(self, evaluator):
        evaluator.evaluate(make_candidate("Keine Ahnung."))                    # whitelist
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))        # normal pass
        m = evaluator.metrics
        assert m.total_passed == 2
        assert m.whitelist_accepted == 1

    def test_multiple_whitelist_entries_accumulate(self, evaluator):
        for phrase in ("Keine Ahnung.", "Danke schön!", "Natürlich.", "Genau."):
            evaluator.evaluate(make_candidate(phrase))
        assert evaluator.metrics.whitelist_accepted == 4


# ---------------------------------------------------------------------------
# TestMetricsConsistency
# Core invariants that must hold regardless of which utterances are evaluated.
# The snapshot must be frozen at creation time — a live evaluator advancing
# further must not mutate an already-returned FilterMetrics object.
# ---------------------------------------------------------------------------

class TestMetricsConsistency:

    def test_invariant_holds_after_every_individual_evaluation(self, evaluator):
        texts = (
            "Ich gehe morgen ins Kino.",
            "Vielleicht.",
            "Keine Ahnung.",
            "und dann kam er nach Hause.",
            "Das Buch liegt auf dem Tisch.",
        )
        for i, text in enumerate(texts, start=1):
            evaluator.evaluate(make_candidate(text))
            m = evaluator.metrics
            assert m.total_passed + m.total_rejected == m.total_evaluated, (
                f"Invariant broken after {i} evaluations"
            )

    def test_rule_evaluated_never_exceeds_total_evaluated(self, evaluator):
        for text in (
            "Ich gehe morgen ins Kino.",
            "Das Wetter ist heute sehr schön.",
            "Keine Ahnung.",                    # whitelist — contributes no rule entries
        ):
            evaluator.evaluate(make_candidate(text))
        m = evaluator.metrics
        for name, rm in m.rules.items():
            assert rm.times_evaluated <= m.total_evaluated, (
                f"Rule '{name}' evaluated more times than total utterances"
            )

    def test_rule_rejected_never_exceeds_rule_evaluated(self, evaluator):
        for text in (
            "Vielleicht.",
            "Ich warte auf",
            "Ja ja ja ja ja nein.",
            "Ich gehe morgen ins Kino.",
        ):
            evaluator.evaluate(make_candidate(text))
        for name, rm in evaluator.metrics.rules.items():
            assert rm.times_rejected <= rm.times_evaluated, (
                f"Rule '{name}' rejected more times than it was evaluated"
            )

    def test_snapshot_is_frozen_after_further_evaluations(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        snapshot = evaluator.metrics               # snapshot at count=1

        evaluator.evaluate(make_candidate("Das Buch liegt auf dem Tisch."))
        evaluator.evaluate(make_candidate("Vielleicht."))

        assert snapshot.total_evaluated == 1       # snapshot unchanged
        assert evaluator.metrics.total_evaluated == 3  # live counter advanced

    def test_known_split_is_recorded_correctly(self, evaluator):
        good = "Ich gehe morgen ins Kino."
        bad  = "Vielleicht."
        for _ in range(7):
            evaluator.evaluate(make_candidate(good))
        for _ in range(3):
            evaluator.evaluate(make_candidate(bad))
        m = evaluator.metrics
        assert m.total_evaluated == 10
        assert m.total_passed == 7
        assert m.total_rejected == 3
        assert m.rules["token_count"].times_rejected == 3


# ---------------------------------------------------------------------------
# TestResetMetrics
# reset_metrics() must zero every counter.  Subsequent evaluations must
# accumulate from zero as if the evaluator were fresh.
# ---------------------------------------------------------------------------

class TestResetMetrics:

    def test_reset_zeroes_total_evaluated(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        evaluator.reset_metrics()
        assert evaluator.metrics.total_evaluated == 0

    def test_reset_zeroes_total_passed(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        evaluator.reset_metrics()
        assert evaluator.metrics.total_passed == 0

    def test_reset_zeroes_whitelist_accepted(self, evaluator):
        evaluator.evaluate(make_candidate("Keine Ahnung."))
        evaluator.reset_metrics()
        assert evaluator.metrics.whitelist_accepted == 0

    def test_reset_clears_rule_entries(self, evaluator):
        evaluator.evaluate(make_candidate("Vielleicht."))
        assert "token_count" in evaluator.metrics.rules
        evaluator.reset_metrics()
        assert evaluator.metrics.rules == {}

    def test_counters_accumulate_from_zero_after_reset(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        evaluator.evaluate(make_candidate("Vielleicht."))
        evaluator.reset_metrics()
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        m = evaluator.metrics
        assert m.total_evaluated == 1
        assert m.total_passed == 1
        assert m.total_rejected == 0

    def test_double_reset_is_idempotent(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        evaluator.reset_metrics()
        evaluator.reset_metrics()
        assert evaluator.metrics.total_evaluated == 0


# ---------------------------------------------------------------------------
# TestFormatTable
# format_table() is the primary human-facing output for corpus-tuning sessions.
# Verify it returns a non-empty string with the key identifiers present.
# ---------------------------------------------------------------------------

class TestFormatTable:

    def test_returns_a_string(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        assert isinstance(evaluator.metrics.format_table(), str)

    def test_includes_rule_name_for_fired_rule(self, evaluator):
        evaluator.evaluate(make_candidate("Vielleicht."))
        assert "token_count" in evaluator.metrics.format_table()

    def test_includes_total_counts_header(self, evaluator):
        evaluator.evaluate(make_candidate("Ich gehe morgen ins Kino."))
        table = evaluator.metrics.format_table()
        assert "evaluated" in table
        assert "passed" in table

    def test_fresh_evaluator_does_not_crash(self, evaluator):
        # No evaluations yet — format_table must handle the empty state.
        table = evaluator.metrics.format_table()
        assert isinstance(table, str)
        assert "0" in table

    def test_whitelist_row_uses_dash_for_rejected_and_rate(self, evaluator):
        # Whitelist entries are always accepted — the table shows "—" in those columns.
        evaluator.evaluate(make_candidate("Keine Ahnung."))
        table = evaluator.metrics.format_table()
        assert "—" in table
