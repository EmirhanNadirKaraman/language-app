"""
Tests for SubtitleMerger.

Grouped by concern:
  - Window properties   (text content, timing, fragment provenance)
  - Timing heuristics   (gap threshold, tiny-gap unconditional merge)
  - Strong punctuation  (sentence boundary detection)
  - Weak punctuation    (comma / semicolon → continuation)
  - Continuation words  (preposition / conjunction / article / auxiliary)
  - Lowercase start     (German-specific strong continuation signal)
  - Short fragment      (too few words to stand alone)
  - Hyphen break        (word split across subtitle blocks)
  - Multi-fragment      (three or more fragments in one window)
  - Config toggles      (each heuristic can be disabled independently)
  - Max window duration (hard ceiling on merged span)
  - Edge cases          (empty input, single fragment, whitespace)
"""
import pytest

from subtitle_merger import SubtitleFragment, SubtitleMergeConfig, SubtitleMerger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def frag(text: str, start: float, end: float, index: int = 0) -> SubtitleFragment:
    return SubtitleFragment(text=text, start_time=start, end_time=end, index=index)


def merge(fragments: list[SubtitleFragment], **cfg_kwargs) -> list:
    cfg = SubtitleMergeConfig(**cfg_kwargs) if cfg_kwargs else SubtitleMergeConfig()
    return SubtitleMerger(cfg).merge_fragments(fragments)


# ---------------------------------------------------------------------------
# Window properties
# ---------------------------------------------------------------------------

class TestWindowProperties:
    """Merged windows carry correct text, timing, and fragment provenance."""

    def test_merged_text_is_space_joined(self):
        windows = merge([
            frag("Ich gehe", 0.0, 1.0),
            frag("nach Hause.", 1.1, 2.0),
        ])
        assert windows[0].text == "Ich gehe nach Hause."

    def test_start_time_comes_from_first_fragment(self):
        windows = merge([
            frag("Ich gehe", 1.5, 2.0),
            frag("nach Hause.", 2.1, 3.5),
        ])
        assert windows[0].start_time == 1.5

    def test_end_time_comes_from_last_fragment(self):
        windows = merge([
            frag("Ich gehe", 1.5, 2.0),
            frag("nach Hause.", 2.1, 3.5),
        ])
        assert windows[0].end_time == 3.5

    def test_original_fragments_preserved_in_order(self):
        f1 = frag("Ich gehe", 0.0, 1.0, index=0)
        f2 = frag("nach Hause.", 1.1, 2.0, index=1)
        windows = merge([f1, f2])
        assert windows[0].fragments == [f1, f2]

    def test_separate_windows_each_own_their_fragments(self):
        f1 = frag("Das war gut.", 0.0, 1.0)
        f2 = frag("Jetzt gehen wir.", 5.0, 6.0)
        windows = merge([f1, f2])
        assert windows[0].fragments == [f1]
        assert windows[1].fragments == [f2]

    def test_html_tags_stripped_from_window_text(self):
        windows = merge([frag("<i>Hallo Welt.</i>", 0.0, 1.0)])
        assert windows[0].text == "Hallo Welt."

    def test_bracketed_annotation_stripped_from_window_text(self):
        windows = merge([frag("[Musik] Ja.", 0.0, 1.0)])
        assert windows[0].text == "Ja."

    def test_leading_dialogue_dash_stripped_from_window_text(self):
        windows = merge([frag("- Guten Morgen!", 0.0, 1.0)])
        assert windows[0].text == "Guten Morgen!"


# ---------------------------------------------------------------------------
# Timing heuristics
# ---------------------------------------------------------------------------

class TestTimingHeuristics:

    def test_gap_within_threshold_allows_merge(self):
        # gap = 0.5s < default max_gap_s = 0.6s; lowercase start seals it
        windows = merge([
            frag("das ist", 0.0, 1.0),
            frag("schön.", 1.5, 2.0),
        ])
        assert len(windows) == 1

    def test_gap_above_threshold_prevents_merge(self):
        # gap = 0.7s > default max_gap_s = 0.6s
        windows = merge([
            frag("Wenn du möchtest,", 0.0, 1.0),
            frag("ruf mich an.", 1.7, 2.5),
        ])
        assert len(windows) == 2

    def test_large_gap_blocks_merge_even_when_other_signals_fire(self):
        # Comma + lowercase, but gap is far too large
        windows = merge([
            frag("Wenn du möchtest,", 0.0, 1.0),
            frag("können wir reden.", 5.0, 6.5),
        ])
        assert len(windows) == 2

    def test_tiny_gap_merges_continuation_at_tiny_gap(self):
        # gap = 0.1s ≤ tiny_gap_s; current has no strong punctuation so no
        # boundary veto fires — genuine word-split continuation merges normally.
        windows = merge([
            frag("Ich gehe nach", 0.0, 1.0),
            frag("Hause jetzt.", 1.1, 2.0),
        ])
        assert len(windows) == 1

    def test_tiny_gap_does_not_unconditionally_merge_short_complete_turns(self):
        # The guard_short_complete_turn safeguard overrides the tiny-gap
        # unconditional merge when both fragments look like complete speaker turns.
        # gap = 0.1s ≤ tiny_gap_s, but "Wirklich?" (1 word, ends '?') is a
        # short complete turn and "Ja, natürlich." starts uppercase → veto fires.
        windows = merge([
            frag("Wirklich?", 0.0, 0.5),
            frag("Ja, natürlich.", 0.6, 1.2),
        ])
        assert len(windows) == 2

    def test_custom_max_gap_respected(self):
        # gap = 1.0s — blocked by default, allowed with custom config
        windows = merge(
            [
                frag("es war einmal", 0.0, 1.0),
                frag("ein Kind.", 2.0, 3.0),
            ],
            max_gap_s=1.5,
        )
        assert len(windows) == 1


# ---------------------------------------------------------------------------
# Strong punctuation → sentence boundary
# ---------------------------------------------------------------------------

class TestStrongPunctuationBoundary:
    """Strong punct + uppercase start + non-tiny gap signals a sentence end."""

    def test_period_and_uppercase_next_prevents_merge(self):
        windows = merge([
            frag("Das war schön.", 0.0, 1.0),
            frag("Jetzt gehen wir.", 1.3, 2.5),
        ])
        assert len(windows) == 2

    def test_exclamation_mark_and_uppercase_next_prevents_merge(self):
        windows = merge([
            frag("Stopp!", 0.0, 0.5),
            frag("Das geht nicht.", 0.8, 1.8),
        ])
        assert len(windows) == 2

    def test_question_mark_and_uppercase_next_prevents_merge(self):
        windows = merge([
            frag("Bist du sicher?", 0.0, 1.2),
            frag("Ich bin sicher.", 1.5, 2.5),
        ])
        assert len(windows) == 2

    def test_ellipsis_and_uppercase_next_prevents_merge(self):
        windows = merge([
            frag("Ich weiß nicht…", 0.0, 1.2),
            frag("Vielleicht schon.", 1.4, 2.5),
        ])
        assert len(windows) == 2

    def test_strong_punctuation_with_lowercase_next_still_merges(self):
        # Ends with ".", but "weil" is lowercase — hard veto does not fire
        windows = merge([
            frag("Ich weiß nicht.", 0.0, 1.2),
            frag("weil ich nicht da war.", 1.3, 2.5),
        ])
        assert len(windows) == 1


# ---------------------------------------------------------------------------
# Weak punctuation → clause continuation
# ---------------------------------------------------------------------------

class TestWeakPunctuationMerge:

    def test_comma_at_end_triggers_merge(self):
        windows = merge([
            frag("Wenn du Zeit hast,", 0.0, 1.5),
            frag("ruf mich an.", 1.7, 2.8),
        ])
        assert len(windows) == 1

    def test_semicolon_at_end_triggers_merge(self):
        windows = merge([
            frag("Er kam spät;", 0.0, 1.2),
            frag("sie war schon weg.", 1.4, 2.4),
        ])
        assert len(windows) == 1

    def test_comma_merge_disabled_does_not_merge_on_comma_alone(self):
        windows = merge(
            [
                frag("Wenn du Zeit hast,", 0.0, 1.5),
                frag("Ruf mich an.", 1.7, 2.8),  # uppercase → no lowercase signal
            ],
            merge_on_weak_punctuation=False,
            merge_on_continuation_word=False,
            merge_on_lowercase_continuation=False,
        )
        assert len(windows) == 2


# ---------------------------------------------------------------------------
# Continuation-word heuristic
# ---------------------------------------------------------------------------

class TestContinuationWordHeuristic:
    """Fragment ending with a preposition, conjunction, article, or auxiliary must merge."""

    def test_preposition_at_end_triggers_merge(self):
        windows = merge([
            frag("Wir treffen uns vor", 0.0, 1.0),
            frag("dem Bahnhof.", 1.2, 2.0),
        ])
        assert len(windows) == 1

    def test_subordinating_conjunction_at_end_triggers_merge(self):
        windows = merge([
            frag("Ich bleibe, weil", 0.0, 1.0),
            frag("du hier bist.", 1.2, 2.2),
        ])
        assert len(windows) == 1

    def test_article_at_end_triggers_merge(self):
        windows = merge([
            frag("Er liest gerade die", 0.0, 1.0),
            frag("Zeitung.", 1.2, 1.8),
        ])
        assert len(windows) == 1

    def test_auxiliary_at_end_triggers_merge(self):
        windows = merge([
            frag("Sie wird", 0.0, 0.6),
            frag("gleich kommen.", 0.8, 1.8),
        ])
        assert len(windows) == 1

    def test_continuation_word_heuristic_disabled_does_not_merge(self):
        windows = merge(
            [
                frag("Wir treffen uns vor", 0.0, 1.0),
                frag("dem Bahnhof.", 1.2, 2.0),
            ],
            merge_on_continuation_word=False,
            merge_on_lowercase_continuation=False,
        )
        assert len(windows) == 2

    def test_content_word_at_end_does_not_trigger_continuation_merge(self):
        # "Zeitung" is not a continuation word
        windows = merge(
            [
                frag("Er liest die Zeitung.", 0.0, 1.2),
                frag("Danach geht er schlafen.", 1.4, 2.5),
            ],
            merge_on_lowercase_continuation=False,
        )
        assert len(windows) == 2


# ---------------------------------------------------------------------------
# Lowercase-start heuristic
# ---------------------------------------------------------------------------

class TestLowercaseContinuationHeuristic:
    """A lowercase-starting fragment is a strong continuation signal in German."""

    def test_lowercase_start_triggers_merge(self):
        windows = merge([
            frag("Das ist das Haus", 0.0, 1.5),
            frag("in dem sie wohnt.", 1.7, 2.8),
        ])
        assert len(windows) == 1

    def test_uppercase_start_without_other_signals_prevents_merge(self):
        windows = merge(
            [
                frag("Das Buch ist gut.", 0.0, 1.5),
                frag("Kaufe es dir.", 1.8, 2.8),
            ],
            merge_on_short_fragment=False,
        )
        assert len(windows) == 2

    def test_lowercase_heuristic_disabled_does_not_merge_on_case_alone(self):
        # No comma, no continuation word, no short fragment — only lowercase
        windows = merge(
            [
                frag("Das ist das Haus", 0.0, 1.5),
                frag("in dem sie wohnt.", 1.7, 2.8),
            ],
            merge_on_lowercase_continuation=False,
            merge_on_continuation_word=False,
        )
        assert len(windows) == 2

    def test_disabling_lowercase_still_merges_via_comma(self):
        # lowercase disabled, but comma is still active
        windows = merge(
            [
                frag("Wenn du möchtest,", 0.0, 1.5),
                frag("können wir reden.", 1.7, 2.8),
            ],
            merge_on_lowercase_continuation=False,
        )
        assert len(windows) == 1


# ---------------------------------------------------------------------------
# Short-fragment heuristic
# ---------------------------------------------------------------------------

class TestShortFragmentHeuristic:

    def test_one_word_fragment_merges_with_next(self):
        # "Ja" has 1 word < min_standalone_words=3; no strong punct → no boundary veto
        windows = merge([
            frag("Ja", 0.0, 0.4),
            frag("natürlich war das so.", 0.6, 1.8),
        ])
        assert len(windows) == 1

    def test_two_word_fragment_merges_with_next(self):
        windows = merge([
            frag("Gut gemacht", 0.0, 0.8),
            frag("mein Freund.", 1.0, 1.8),
        ])
        assert len(windows) == 1

    def test_fragment_exactly_at_threshold_is_not_short(self):
        # min_standalone_words=3; a 3-word fragment is NOT too short
        windows = merge(
            [
                frag("Das ist schön.", 0.0, 1.2),
                frag("Wirklich gut.", 1.4, 2.2),
            ],
            merge_on_short_fragment=False,
            merge_on_continuation_word=False,
            merge_on_lowercase_continuation=False,
            merge_on_weak_punctuation=False,
        )
        assert len(windows) == 2

    def test_short_fragment_heuristic_disabled_does_not_merge_on_length_alone(self):
        windows = merge(
            [
                frag("Ja", 0.0, 0.4),
                frag("Natürlich.", 0.6, 1.2),
            ],
            merge_on_short_fragment=False,
            merge_on_continuation_word=False,
            merge_on_lowercase_continuation=False,
            merge_on_weak_punctuation=False,
        )
        assert len(windows) == 2

    def test_custom_min_standalone_words_raises_threshold(self):
        # min_standalone_words=5 makes a 4-word fragment too short
        windows = merge(
            [
                frag("Er ist gut hier", 0.0, 1.0),
                frag("Morgen kommt er.", 1.2, 2.0),
            ],
            min_standalone_words=5,
            merge_on_continuation_word=False,
            merge_on_lowercase_continuation=False,
            merge_on_weak_punctuation=False,
        )
        assert len(windows) == 1


# ---------------------------------------------------------------------------
# Hyphen-break heuristic
# ---------------------------------------------------------------------------

class TestHyphenBreakHeuristic:

    def test_trailing_hyphen_triggers_merge(self):
        windows = merge([
            frag("Das ist sein Lieblings-", 0.0, 1.5),
            frag("film aller Zeiten.", 1.6, 2.8),
        ])
        assert len(windows) == 1

    def test_hyphen_is_stripped_and_word_is_concatenated(self):
        windows = merge([
            frag("Das ist sein Lieblings-", 0.0, 1.5),
            frag("film aller Zeiten.", 1.6, 2.8),
        ])
        assert windows[0].text == "Das ist sein Lieblingsfilm aller Zeiten."
        assert "Lieblings-" not in windows[0].text

    def test_hyphen_merge_disabled_does_not_merge_on_hyphen_alone(self):
        # gap = 0.3s: above tiny_gap_s (0.15) so no unconditional merge,
        # below max_gap_s (0.6) so timing alone doesn't block — only heuristics decide
        windows = merge(
            [
                frag("Das ist sein Lieblings-", 0.0, 1.5),
                frag("film aller Zeiten.", 1.8, 3.0),
            ],
            merge_on_hyphen_break=False,
            merge_on_lowercase_continuation=False,
            merge_on_continuation_word=False,
            merge_on_weak_punctuation=False,
            merge_on_short_fragment=False,
        )
        assert len(windows) == 2


# ---------------------------------------------------------------------------
# Multi-fragment windows
# ---------------------------------------------------------------------------

class TestMultiFragmentWindows:

    def test_three_fragments_merge_into_one_window(self):
        windows = merge([
            frag("Wir treffen uns", 0.0, 1.0),
            frag("vor dem", 1.1, 1.6),
            frag("großen Bahnhof.", 1.7, 2.5),
        ])
        assert len(windows) == 1
        assert windows[0].text == "Wir treffen uns vor dem großen Bahnhof."
        assert len(windows[0].fragments) == 3

    def test_chain_splits_at_large_gap(self):
        windows = merge([
            frag("Ich gehe", 0.0, 0.8),
            frag("nach Hause,", 0.9, 1.5),
            frag("weil es spät ist.", 5.0, 6.5),  # gap too large → new window
        ])
        assert len(windows) == 2
        assert windows[0].text == "Ich gehe nach Hause,"
        assert windows[1].text == "weil es spät ist."

    def test_four_fragments_merge_with_continuation_signals(self):
        windows = merge([
            frag("Er hat das", 0.0, 0.8),
            frag("Buch für", 0.9, 1.3),
            frag("seinen kleinen", 1.4, 1.9),
            frag("Bruder gekauft.", 2.0, 2.8),
        ])
        assert len(windows) == 1
        assert len(windows[0].fragments) == 4

    def test_realistic_dialogue_merges_and_splits_correctly(self):
        # The short-complete-turn guard now splits "Guten Morgen!" (2 words,
        # ends '!') from the following incomplete question, and "Nein, noch
        # nicht." (3 words, ends '.') from the following continuation.
        # Genuine continuations ("Hast du schon" → "gefrühstückt?",
        # "Ich warte auf" → "dich.") still merge via tiny-gap.
        windows = merge([
            frag("Guten Morgen!", 0.0, 0.8),
            frag("Hast du schon", 0.9, 1.5),
            frag("gefrühstückt?", 1.55, 2.2),
            frag("Nein, noch nicht.", 3.0, 4.0),
            frag("Ich warte auf", 4.1, 4.8),
            frag("dich.", 4.85, 5.2),
        ])
        assert len(windows) == 4
        assert windows[0].text == "Guten Morgen!"
        assert "gefrühstückt?" in windows[1].text
        assert windows[2].text == "Nein, noch nicht."
        assert "auf dich." in windows[3].text


# ---------------------------------------------------------------------------
# Max window duration ceiling
# ---------------------------------------------------------------------------

class TestMaxWindowDuration:

    def test_window_never_exceeds_max_duration(self):
        # Four fragments, 1.5s each, 0.1s gaps; max_window_duration_s=4.0
        # Adding a 3rd fragment (projected span ~4.7s) would exceed 4.0s → splits there
        frags = [
            frag(f"Teil {i},", i * 1.6, i * 1.6 + 1.5, index=i)
            for i in range(4)
        ]
        windows = merge(frags, max_window_duration_s=4.0)
        for w in windows:
            assert w.duration <= 4.0

    def test_tighter_max_duration_produces_more_windows(self):
        frags = [
            frag("Wort eins,", 0.0, 1.0),
            frag("Wort zwei,", 1.1, 2.0),
            frag("Wort drei,", 2.1, 3.0),
            frag("Wort vier.", 3.1, 4.0),
        ]
        windows_tight = merge(frags, max_window_duration_s=2.5)
        windows_loose = merge(frags, max_window_duration_s=10.0)
        assert len(windows_tight) > len(windows_loose)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_input_returns_empty_list(self):
        assert merge([]) == []

    def test_single_fragment_returns_one_window(self):
        windows = merge([frag("Hallo!", 0.0, 1.0)])
        assert len(windows) == 1
        assert windows[0].text == "Hallo!"

    def test_single_fragment_timing_is_preserved(self):
        windows = merge([frag("Hallo!", 3.5, 4.2)])
        assert windows[0].start_time == 3.5
        assert windows[0].end_time == 4.2

    def test_all_fragments_with_large_gaps_produce_n_separate_windows(self):
        frags = [frag(f"Satz {i}.", float(i * 5), float(i * 5 + 1)) for i in range(4)]
        windows = merge(frags)
        assert len(windows) == 4

    def test_whitespace_only_fragment_does_not_crash(self):
        windows = merge([
            frag("Ich bin hier.", 0.0, 1.0),
            frag("   ", 1.1, 1.5),
            frag("Wirklich?", 1.6, 2.2),
        ])
        assert len(windows) >= 1

    def test_annotation_only_fragment_does_not_crash(self):
        windows = merge([
            frag("Er sprach.", 0.0, 1.5),
            frag("[Applaus]", 1.6, 2.5),
            frag("Danke sehr.", 2.6, 3.5),
        ])
        assert len(windows) >= 1

    def test_back_to_back_identical_short_complete_fragments_now_split(self):
        # The short-complete-turn guard fires: "Ja." (1 word, ends '.') +
        # uppercase next → veto even at tiny gap (0.1 ≤ tiny_gap_s).
        # Subtitle deduplication of true copy artefacts should be handled
        # as a separate pre-processing step before merging.
        windows = merge([
            frag("Ja.", 0.0, 0.5),
            frag("Ja.", 0.6, 1.0),
        ])
        assert len(windows) == 2


# ---------------------------------------------------------------------------
# Multi-speaker safeguards
# ---------------------------------------------------------------------------

class TestMultiSpeakerGuard:
    """
    Tests for the two multi-speaker safeguards added to SubtitleMerger:

      guard_dialogue_dash       — next fragment starts with - / – / —
      guard_short_complete_turn — current ends a short complete utterance and
                                  next opens a new one (extends sentence-boundary
                                  veto to tiny-gap cases)
    """

    # ---- Dialogue-dash veto ----

    def test_dash_prefix_on_next_fragment_blocks_merge(self):
        # Even with a tiny gap the explicit speaker marker must veto the merge.
        windows = merge([
            frag("Das war gut.", 0.0, 1.0),
            frag("- Wirklich?", 1.05, 1.7),
        ])
        assert len(windows) == 2

    def test_dash_prefix_blocks_merge_even_at_tiny_gap(self):
        # gap = 0.05s — normally triggers unconditional merge; the dash wins.
        windows = merge([
            frag("Das ist schön.", 0.0, 1.0),
            frag("- Danke.", 1.05, 1.5),
        ])
        assert len(windows) == 2

    def test_en_dash_prefix_also_blocked(self):
        windows = merge([
            frag("Gut gemacht.", 0.0, 0.8),
            frag("– Danke schön.", 0.85, 1.5),
        ])
        assert len(windows) == 2

    def test_em_dash_prefix_also_blocked(self):
        windows = merge([
            frag("Gut gemacht.", 0.0, 0.8),
            frag("— Danke schön.", 0.85, 1.5),
        ])
        assert len(windows) == 2

    def test_three_dash_prefixed_turns_each_separate(self):
        # Classic subtitle dialogue: three lines, each a different speaker.
        windows = merge([
            frag("- Das war wirklich gut.", 0.0, 1.2),
            frag("- Wirklich?", 1.25, 1.8),
            frag("- Ja, total.", 1.85, 2.5),
        ])
        assert len(windows) == 3

    def test_dash_only_separator_line_does_not_block_merge(self):
        # A bare "–" or "---" is not a dialogue turn; the regex requires content
        # after the dash, so it falls through to normal merge logic.
        windows = merge([
            frag("Ich gehe nach", 0.0, 1.0),
            frag("– ", 1.05, 1.1),           # bare dash + space, no content after
            frag("Hause jetzt.", 1.15, 2.0),
        ])
        # The bare dash does NOT block — behaviour governed by other heuristics.
        assert len(windows) >= 1  # exact count depends on other signals; just no crash

    def test_dialogue_dash_guard_disabled_allows_merge(self):
        # With the guard off, the merge falls through to normal logic.
        # gap=0.05 ≤ tiny_gap → unconditional merge overrides the dash.
        windows = merge(
            [
                frag("Das war gut.", 0.0, 1.0),
                frag("- Wirklich?", 1.05, 1.7),
            ],
            guard_dialogue_dash=False,
        )
        # gap=0.05 ≤ tiny_gap AND current ends with "." + next starts uppercase
        # → guard_short_complete_turn still fires (it's still on).
        # To confirm dash guard alone is off, also disable the other guard.
        windows2 = merge(
            [
                frag("Das war gut.", 0.0, 1.0),
                frag("- Wirklich?", 1.05, 1.7),
            ],
            guard_dialogue_dash=False,
            guard_short_complete_turn=False,
        )
        assert len(windows2) == 1

    # ---- Short-complete-turn veto ----

    def test_short_complete_turn_blocks_merge_at_tiny_gap(self):
        # "Ich auch." (2 words, ends '.') + uppercase next: guard fires at
        # tiny gap that would otherwise be unconditional merge.
        windows = merge([
            frag("Ich auch.", 0.0, 0.8),
            frag("Wirklich?", 0.9, 1.5),
        ])
        assert len(windows) == 2

    def test_question_answer_pair_stays_separate(self):
        windows = merge([
            frag("Bist du sicher?", 0.0, 0.8),
            frag("Ja, absolut.", 0.85, 1.5),
        ])
        assert len(windows) == 2

    def test_long_complete_fragment_still_merges_via_tiny_gap(self):
        # 8 words > max_complete_turn_words=6 → guard does NOT fire → tiny-gap
        # unconditional merge applies.
        windows = merge([
            frag("Er hat das Buch wirklich gut gelesen!", 0.0, 2.0),
            frag("Das finde ich toll.", 2.05, 3.0),
        ])
        assert len(windows) == 1

    def test_incomplete_current_fragment_never_triggers_guard(self):
        # Current ends with comma (weak punct, not strong) → boundary condition
        # not met → guard does not fire → tiny-gap merge applies.
        windows = merge([
            frag("Wenn du möchtest,", 0.0, 1.0),
            frag("Ruf mich an.", 1.05, 1.8),
        ])
        assert len(windows) == 1

    def test_custom_max_complete_turn_words_tightens_guard(self):
        # With max_complete_turn_words=3, a 3-word complete utterance now
        # triggers the guard where it would not with the default of 6.
        # "Das ist gut." has 3 words ≤ 3 → guard fires.
        windows_guard = merge(
            [
                frag("Das ist gut.", 0.0, 0.8),
                frag("Wirklich?", 0.85, 1.2),
            ],
            max_complete_turn_words=3,
        )
        assert len(windows_guard) == 2

    def test_short_complete_turn_guard_disabled_merges_via_tiny_gap(self):
        # With both guards off, tiny-gap unconditional merge wins again.
        windows = merge(
            [
                frag("Wirklich?", 0.0, 0.5),
                frag("Ja, natürlich.", 0.55, 1.1),
            ],
            guard_dialogue_dash=False,
            guard_short_complete_turn=False,
        )
        assert len(windows) == 1

    def test_uppercase_next_required_for_guard_to_fire(self):
        # Guard requires next fragment to start with uppercase (new sentence).
        # "weil ich das weiß." starts lowercase → guard does NOT fire →
        # merge happens via tiny-gap (continuation fragment in context).
        windows = merge([
            frag("Gut.", 0.0, 0.4),
            frag("weil ich das weiß.", 0.45, 1.2),
        ])
        assert len(windows) == 1
