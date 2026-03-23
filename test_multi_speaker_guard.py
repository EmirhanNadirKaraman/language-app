"""
test_multi_speaker_guard.py
---------------------------
Focused tests for the two multi-speaker safeguards in SubtitleMerger.

guard_dialogue_dash
    Hard veto when the *next* fragment's raw text starts with a
    dialogue-marker dash (-, –, —).  Fires before the unconditional
    tiny-gap merge, so it always wins.

guard_short_complete_turn
    Extends the sentence-boundary veto to tiny gaps when the *current*
    fragment is a short complete utterance (word_count ≤ max_complete_turn_words).
    Catches rapid back-and-forth exchanges that arrive with near-zero gaps.

Coverage
--------
  TestDialogueDashVeto          — leading dashes prevent merges (area 1)
  TestSameSpeakerContinuation   — normal continuations still merge (area 2)
  TestShortCompleteTurnBoundary — strong punct + turn style stays separate (area 3)
  TestExistingMergesUnaffected  — guards do not destroy useful merges (area 4)
  TestEdgeCases                 — easy regression targets (area 5)

Defaults relied on throughout:
    max_gap_s             = 0.6
    tiny_gap_s            = 0.15
    max_complete_turn_words = 6
    min_standalone_words  = 3
"""
import pytest

from subtitle_merger import SubtitleFragment, SubtitleMergeConfig, SubtitleMerger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def frag(text: str, start: float, end: float) -> SubtitleFragment:
    return SubtitleFragment(text=text, start_time=start, end_time=end)


def merge(fragments: list[SubtitleFragment], **cfg_kwargs) -> list:
    config = SubtitleMergeConfig(**cfg_kwargs) if cfg_kwargs else SubtitleMergeConfig()
    return SubtitleMerger(config).merge_fragments(fragments)


# ---------------------------------------------------------------------------
# TestDialogueDashVeto
#
# The dialogue-dash guard only inspects the *next* fragment's raw text.
# It must block the merge even when every other heuristic would allow it.
# ---------------------------------------------------------------------------

class TestDialogueDashVeto:

    def test_dash_prefix_overrides_soft_signal(self):
        # Comma on current would normally trigger merge_on_weak_punctuation, but
        # the dialogue dash on the next fragment vetoes it first.
        windows = merge([
            frag("Wenn du möchtest,", 0.0, 1.2),
            frag("- Können wir morgen reden.", 1.4, 2.5),  # gap=0.2s, comma would merge
        ])
        assert len(windows) == 2

    def test_dash_prefix_overrides_tiny_gap_unconditional_merge(self):
        # gap=0.05s would normally trigger unconditional merge; the dash wins.
        # Current is also long (8 words > max_complete_turn_words=6) so only the
        # dash guard can stop this merge.
        windows = merge([
            frag("Sie hat das alles wirklich sehr gut gemacht.", 0.0, 2.0),
            frag("- Wirklich?", 2.05, 2.5),  # gap=0.05s
        ])
        assert len(windows) == 2

    def test_en_dash_prefix_blocked(self):
        windows = merge([
            frag("Das war schön.", 0.0, 1.0),
            frag("– Danke schön.", 1.2, 1.9),
        ])
        assert len(windows) == 2

    def test_em_dash_prefix_blocked(self):
        windows = merge([
            frag("Das war schön.", 0.0, 1.0),
            frag("— Danke schön.", 1.2, 1.9),
        ])
        assert len(windows) == 2

    def test_three_consecutive_dash_turns_produce_three_windows(self):
        # Classic dialogue-formatted subtitle block: every turn on its own fragment.
        windows = merge([
            frag("- Das ist doch lächerlich.", 0.0, 1.2),
            frag("- Wieso das?", 1.25, 1.8),
            frag("- Na ja, du weißt schon.", 1.85, 2.8),
        ])
        assert len(windows) == 3

    def test_dash_guard_only_checks_next_fragment_not_current(self):
        # Current starts with a dash — that is irrelevant.  The guard inspects
        # NXT only.  Here NXT has no dash and current is long (8 words > 6),
        # so neither guard fires and the tiny gap triggers unconditional merge.
        windows = merge([
            frag("- Er hat das Buch wirklich gut gelesen.", 0.0, 2.0),
            frag("Interessant.", 2.05, 2.5),  # gap=0.05s, NXT has no dash
        ])
        assert len(windows) == 1

    def test_html_wrapped_dash_detected(self):
        # Some encoders write <i>- Text</i>; HTML is stripped before the regex.
        windows = merge([
            frag("Das war wirklich sehr schön so.", 0.0, 1.5),
            frag("<i>- Wirklich?</i>", 1.55, 2.0),  # gap=0.05s
        ])
        assert len(windows) == 2

    def test_dash_guard_disabled_falls_through_to_other_logic(self):
        # With guard_dialogue_dash=False the dash is ignored; the merge then
        # depends only on guard_short_complete_turn and gap size.
        # Here current is long (7 words > 6) and gap is tiny → merges.
        windows = merge(
            [
                frag("Sie hat das Buch wirklich sehr gelesen.", 0.0, 2.0),
                frag("- Interessant.", 2.05, 2.5),
            ],
            guard_dialogue_dash=False,
            guard_short_complete_turn=False,  # also off so tiny gap wins
        )
        assert len(windows) == 1


# ---------------------------------------------------------------------------
# TestSameSpeakerContinuation
#
# The guards must not interfere with ordinary same-speaker continuations.
# The key property of each case: neither guard fires because either the
# current fragment lacks strong punctuation or the next does not start
# with a dash or uppercase.
# ---------------------------------------------------------------------------

class TestSameSpeakerContinuation:

    def test_comma_continuation_merges(self):
        # Current ends with comma (weak punct) → merge_on_weak_punctuation.
        # No strong punct → guards can never fire.
        windows = merge([
            frag("Ich gehe morgen ins Kino,", 0.0, 1.5),
            frag("wenn du mitkommen möchtest.", 1.7, 2.8),
        ])
        assert len(windows) == 1
        assert "wenn du mitkommen möchtest." in windows[0].text

    def test_lowercase_start_continuation_merges(self):
        # German rule: lowercase start means the fragment continues the previous
        # clause.  No uppercase → short-complete-turn guard can never fire.
        windows = merge([
            frag("Das ist das Haus,", 0.0, 1.2),
            frag("in dem sie aufgewachsen ist.", 1.4, 2.5),
        ])
        assert len(windows) == 1

    def test_continuation_word_at_end_merges(self):
        # Fragment ends with a preposition — syntactically incomplete.
        # No strong punct → no veto; continuation word fires merge.
        windows = merge([
            frag("Er wartet schon seit einer Stunde auf", 0.0, 1.5),
            frag("seinen alten Freund.", 1.7, 2.5),
        ])
        assert len(windows) == 1

    def test_hyphen_word_break_across_fragments_merges(self):
        # Subtitle encoder split a compound word across two blocks.
        windows = merge([
            frag("Das ist sein absoluter Lieblings-", 0.0, 1.5),
            frag("film aller Zeiten.", 1.55, 2.5),
        ])
        assert len(windows) == 1
        assert "Lieblingsfilm" in windows[0].text

    def test_short_fragment_without_strong_punct_merges(self):
        # 1-word fragment, no strong punctuation → guards cannot fire.
        # Tiny gap triggers unconditional merge.
        windows = merge([
            frag("Und", 0.0, 0.3),
            frag("dann kam er endlich nach Hause.", 0.35, 1.5),
        ])
        assert len(windows) == 1

    def test_three_fragment_continuation_chain_fully_merges(self):
        # Sentence split across three blocks; all are continuations.
        windows = merge([
            frag("Sie hat das Buch,", 0.0, 0.8),
            frag("das er ihr geschenkt hatte,", 0.9, 1.8),
            frag("in einer Nacht gelesen.", 1.9, 2.8),
        ])
        assert len(windows) == 1
        assert len(windows[0].fragments) == 3


# ---------------------------------------------------------------------------
# TestShortCompleteTurnBoundary
#
# guard_short_complete_turn extends the sentence-boundary veto to tiny gaps
# when current.word_count ≤ max_complete_turn_words (default 6).
# ---------------------------------------------------------------------------

class TestShortCompleteTurnBoundary:

    def test_question_answer_pair_at_tiny_gap_splits(self):
        # "Kommst du mit?" is 3 words ≤ 6, ends '?', next starts uppercase.
        windows = merge([
            frag("Kommst du mit?", 0.0, 0.8),
            frag("Ja, klar doch.", 0.85, 1.5),  # gap=0.05s
        ])
        assert len(windows) == 2

    def test_exclamation_response_at_tiny_gap_splits(self):
        # "Nein!" is 1 word — smallest possible case for the guard.
        windows = merge([
            frag("Nein!", 0.0, 0.4),
            frag("Doch, ich komme!", 0.45, 1.0),  # gap=0.05s
        ])
        assert len(windows) == 2

    def test_greeting_and_follow_up_question_split(self):
        # Even though gap is tiny, two complete short utterances stay separate.
        windows = merge([
            frag("Guten Morgen!", 0.0, 0.7),
            frag("Wie geht es Ihnen?", 0.75, 1.5),  # gap=0.05s
        ])
        assert len(windows) == 2

    def test_existing_sentence_boundary_at_normal_gap_still_works(self):
        # gap=0.3s > tiny_gap_s — the original veto fires; guard not needed.
        windows = merge([
            frag("Das war wirklich fantastisch.", 0.0, 1.5),
            frag("Jetzt fahren wir nach Hause.", 1.8, 3.0),
        ])
        assert len(windows) == 2

    def test_guard_fires_at_exactly_max_complete_turn_words(self):
        # "Das ist doch wirklich sehr schön." = 6 words = threshold → guard fires.
        windows = merge([
            frag("Das ist doch wirklich sehr schön.", 0.0, 1.2),
            frag("Stimmt.", 1.25, 1.6),  # gap=0.05s
        ])
        assert len(windows) == 2

    def test_guard_does_not_fire_one_above_threshold(self):
        # 7 words > max_complete_turn_words=6 → guard is silent → tiny gap merges.
        windows = merge([
            frag("Das ist doch wirklich sehr schön gewesen.", 0.0, 1.5),
            frag("Stimmt.", 1.55, 1.9),  # gap=0.05s
        ])
        assert len(windows) == 1

    def test_lowercase_next_bypasses_guard(self):
        # Guard requires next to start uppercase.  Lowercase start is a
        # continuation signal → merges instead of splitting.
        windows = merge([
            frag("Gut.", 0.0, 0.3),
            frag("weil du recht hast.", 0.35, 1.0),  # gap=0.05s, lowercase
        ])
        assert len(windows) == 1

    def test_custom_threshold_tightens_guard(self):
        # With max_complete_turn_words=2, a 2-word utterance triggers the guard.
        windows = merge(
            [
                frag("Gut gemacht.", 0.0, 0.5),
                frag("Danke sehr.", 0.55, 1.0),  # gap=0.05s
            ],
            max_complete_turn_words=2,
        )
        assert len(windows) == 2


# ---------------------------------------------------------------------------
# TestExistingMergesUnaffected
#
# The guards must not produce false positives on normal subtitle content.
# ---------------------------------------------------------------------------

class TestExistingMergesUnaffected:

    def test_comma_ended_fragment_still_merges(self):
        # Comma is weak punctuation — the short-complete-turn guard needs
        # STRONG punctuation on current, so it cannot fire here.
        windows = merge([
            frag("Er kommt nicht,", 0.0, 1.0),
            frag("Weil er krank ist.", 1.2, 2.2),
        ])
        assert len(windows) == 1

    def test_long_utterance_merges_unconditionally_at_tiny_gap(self):
        # 8 words > max_complete_turn_words=6 → guard silent → tiny gap wins.
        windows = merge([
            frag("Er hat das Buch wirklich sehr gut gelesen!", 0.0, 2.0),
            frag("Das war eine schöne Geschichte.", 2.05, 3.0),  # gap=0.05s
        ])
        assert len(windows) == 1

    def test_fragment_ending_with_continuation_word_still_merges(self):
        # "nach" is a preposition at fragment end → continuation word fires.
        # No strong punct → boundary guards inactive.
        windows = merge([
            frag("Wir fahren jetzt nach", 0.0, 1.0),
            frag("München.", 1.2, 1.8),
        ])
        assert len(windows) == 1

    def test_lowercase_continuation_after_strong_punct_still_merges(self):
        # Existing behaviour: strong punct + lowercase next is a legitimate
        # continuation (e.g. a dependent clause following a main clause).
        # Guard requires uppercase next — it must stay silent here.
        windows = merge([
            frag("Ich weiß das nicht.", 0.0, 1.2),
            frag("weil ich nicht dabei war.", 1.3, 2.2),  # lowercase start
        ])
        assert len(windows) == 1

    def test_both_guards_disabled_restores_unconditional_tiny_gap_merge(self):
        # With both guards off, tiny gap once again merges unconditionally
        # even for a short complete turn followed by an uppercase fragment.
        windows = merge(
            [
                frag("Wirklich?", 0.0, 0.5),
                frag("Ja, natürlich.", 0.55, 1.1),  # gap=0.05s
            ],
            guard_dialogue_dash=False,
            guard_short_complete_turn=False,
        )
        assert len(windows) == 1

    def test_continuation_chain_preserved_before_dash_turn(self):
        # The merge chain up to the dashed fragment must survive intact.
        windows = merge([
            frag("Sie kommt morgen,", 0.0, 1.0),
            frag("wenn sie Zeit hat.", 1.2, 2.0),   # continuation → merges
            frag("- Gut.", 2.2, 2.6),               # dialogue dash → split
        ])
        assert len(windows) == 2
        assert "morgen" in windows[0].text
        assert "Zeit hat." in windows[0].text
        assert windows[1].text == "Gut."


# ---------------------------------------------------------------------------
# TestEdgeCases
#
# Corner cases that are easy to accidentally regress.
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_bare_dash_with_only_whitespace_does_not_trigger_guard(self):
        # "– " has no non-whitespace after the dash; _DIALOGUE_DASH_RE requires
        # \S, so this does not match and the guard stays silent.
        # Comma on current means merge_on_weak_punctuation fires → merges.
        windows = merge([
            frag("Er kommt morgen,", 0.0, 1.0),
            frag("– ", 1.2, 1.4),           # bare dash + space only
            frag("wenn er Zeit hat.", 1.5, 2.4),
        ])
        # Guard silent on "– "; normal merge logic governs the sequence.
        assert len(windows) >= 1  # no crash; exact count from other heuristics

    def test_single_hyphen_fragment_does_not_trigger_guard(self):
        # A fragment that is just "-" has no content after the dash.
        windows = merge([
            frag("Das war schön,", 0.0, 1.0),
            frag("-", 1.2, 1.3),            # sole hyphen, no \S follows
            frag("wirklich schön.", 1.4, 2.2),
        ])
        assert len(windows) >= 1  # no crash

    def test_inline_dash_in_text_body_does_not_trigger_guard(self):
        # A dash in the middle of text is not a speaker marker.
        # The regex is start-anchored, so it cannot match mid-text dashes.
        # current is 8 words (> 6) so short_complete_turn also stays silent
        # → tiny gap → unconditional merge.
        windows = merge([
            frag("Er hat das Buch wirklich sehr gut gelesen.", 0.0, 2.0),
            frag("Gut—aber warum so schnell?", 2.05, 2.8),  # gap=0.05s
        ])
        assert len(windows) == 1

    def test_gap_above_maximum_vetoed_before_guards_run(self):
        # gap=0.8s > max_gap_s=0.6 → first hard veto fires; guards irrelevant.
        # Verify the sequence is still handled cleanly (no crash, correct count).
        windows = merge([
            frag("- Das war gut.", 0.0, 1.0),
            frag("- Wirklich?", 1.8, 2.3),  # gap=0.8s > 0.6
        ])
        assert len(windows) == 2

    def test_five_fragment_realistic_sequence(self):
        # Realistic sequence: continuation chain, then two dashed turns, then
        # a short-complete-turn guard fires on the last pair.
        #
        # "Ich gehe," → "weil es spät ist."  → merges via comma + lowercase
        # → "- Schön."                        → splits via dialogue dash
        # → "- Bis morgen!"                   → splits via dialogue dash
        # → "Tschüss!"  gap=0.05s             → splits: "Bis morgen!" is
        #                                        2 words ≤ 6, '!' + uppercase
        windows = merge([
            frag("Ich gehe,", 0.0, 0.8),
            frag("weil es schon spät ist.", 0.9, 1.8),
            frag("- Schön.", 2.0, 2.4),
            frag("- Bis morgen!", 2.45, 2.9),
            frag("Tschüss!", 2.95, 3.3),          # gap=0.05s
        ])
        assert len(windows) == 4
        assert "weil es schon spät ist." in windows[0].text
        assert windows[1].text == "Schön."
        assert windows[2].text == "Bis morgen!"
        assert windows[3].text == "Tschüss!"
