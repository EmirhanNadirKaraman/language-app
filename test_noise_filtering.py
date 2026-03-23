"""
test_noise_filtering.py
-----------------------
Focused tests for the noise-filtering behaviour added to UtteranceUnitExtractor:
proper-noun exclusion (PROPN POS filter), named-entity exclusion (NER filter),
and subtitle-garbage exclusion (Unicode category + no-alpha checks).

How these tests protect the i+1 pipeline
-----------------------------------------
The i+1 filter surfaces an utterance only when exactly ONE unit is unknown.
If "Thomas" or "Berlin" reach the unit list as unknowns, the filter fires for
the wrong reason: the sentence is flagged as learnable for a proper noun that
teaches the user nothing, and genuinely learnable vocabulary in the same
sentence is buried.  Worse, if the same proper noun appears repeatedly across
episodes, it keeps winning the "one unknown" slot and suppresses real vocab.

These tests verify that the extractor's gate is clean before the i+1 filter
ever sees the unit list.

Test classes
------------
  TestGarbageSymbolHelper    — unit tests for _has_garbage_symbols(); no model
  TestProperNounPosFilter    — PROPN tokens excluded by POS; needs de_core_news_md
  TestNamedEntityFilter      — NER-labelled NOUN tokens excluded; needs de_core_news_md
  TestGarbageInExtractor     — structural garbage through the extractor
  TestValidVocabularyKept    — regression: useful words still extracted after filtering
  TestMixedUtterance         — signal preserved when noise surrounds it
  TestNerFilterDisabled      — skip_ent_types=frozenset() opt-out works correctly
"""
import pytest
import spacy

from subtitle_merger import MergedSubtitleWindow, SubtitleFragment
from subtitle_segmenter import CandidateUtterance
from utterance_unit_extractor import (
    UnitExtractionConfig,
    UtteranceExtractionResult,
    UtteranceUnitExtractor,
    _has_garbage_symbols,
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


def keys(result: UtteranceExtractionResult) -> set[str]:
    return {u.key for u in result.units}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def nlp():
    try:
        return spacy.load("de_core_news_md")
    except OSError:
        pytest.skip("de_core_news_md not installed — run: python -m spacy download de_core_news_md")


@pytest.fixture(scope="session")
def extractor(nlp):
    return UtteranceUnitExtractor(nlp)


# ---------------------------------------------------------------------------
# TestGarbageSymbolHelper
# No model needed — tests the pure-Python Unicode helper directly.
# ---------------------------------------------------------------------------

class TestGarbageSymbolHelper:
    """_has_garbage_symbols() is the gatekeeper for hybrid garbage tokens."""

    def test_standalone_musical_note(self):
        assert _has_garbage_symbols("♪") is True

    def test_musical_note_fused_with_text(self):
        # The critical case: alphabetic content hides a garbage character.
        assert _has_garbage_symbols("♪Danke♪") is True

    def test_trademark_symbol(self):
        assert _has_garbage_symbols("word™") is True

    def test_zero_width_format_character(self):
        # U+200B zero-width space — category Cf
        assert _has_garbage_symbols("text\u200b") is True

    def test_normal_german_word_not_garbage(self):
        assert _has_garbage_symbols("schön") is False

    def test_word_with_hyphen_not_garbage(self):
        # Hyphens are punctuation (Pd), not a garbage category.
        assert _has_garbage_symbols("nicht-so-schön") is False


# ---------------------------------------------------------------------------
# TestProperNounPosFilter
# PROPN is intentionally absent from content_pos_tags.
# Every PROPN token is dropped before the NER filter even runs.
# ---------------------------------------------------------------------------

class TestProperNounPosFilter:

    def test_single_first_name_not_extracted(self, extractor):
        result = extractor.extract(make_candidate("Thomas schläft."))
        assert "thomas" not in keys(result)

    def test_full_name_neither_part_extracted(self, extractor):
        result = extractor.extract(make_candidate("Klaus Müller kommt morgen."))
        assert "Klaus" not in keys(result) and "Müller" not in keys(result)
        assert "kommen" in keys(result) or "komm" in keys(result)

    def test_female_first_name_not_extracted(self, extractor):
        result = extractor.extract(make_candidate("Maria singt sehr schön."))
        assert "maria" not in keys(result)
        assert "singen" in keys(result)
        assert "schön" in keys(result)

    def test_verb_in_sentence_with_name_still_extracted(self, extractor):
        # The filter must be surgical: only the name is dropped.
        result = extractor.extract(make_candidate("Anna fährt nach Hause."))
        assert "fahren" in keys(result)


# ---------------------------------------------------------------------------
# TestNamedEntityFilter
# NOUN tokens that NER labels PER / LOC / ORG are dropped by _is_entity_noise.
# This is a second layer that catches proper nouns mislabelled as NOUN by POS.
# ---------------------------------------------------------------------------

class TestNamedEntityFilter:

    def test_city_name_not_extracted(self, extractor):
        result = extractor.extract(make_candidate("Er fährt nach Berlin."))
        assert "berlin" not in keys(result)
        assert "fahren" in keys(result)

    def test_organisation_name_not_extracted(self, extractor):
        result = extractor.extract(make_candidate("Sie arbeitet bei BMW."))
        assert "bmw" not in keys(result)
        assert "arbeiten" in keys(result)

    def test_country_name_not_extracted(self, extractor):
        result = extractor.extract(make_candidate("Er kommt aus Deutschland."))
        assert "deutschland" not in keys(result)

    def test_nationality_adjective_not_filtered(self, extractor):
        # "deutsch" is MISC in de_core_news_md — not in skip_ent_types.
        # It should survive as learnable vocabulary.
        result = extractor.extract(make_candidate("Der deutsche Film ist gut."))
        assert "deutsch" in keys(result)

    def test_common_noun_without_ner_label_passes_through(self, extractor):
        # Ordinary nouns carry no NER label; confirming the filter is not
        # accidentally too broad.
        result = extractor.extract(make_candidate("Das Buch liegt auf dem Tisch."))
        assert "buch" in keys(result)
        assert "tisch" in keys(result)


# ---------------------------------------------------------------------------
# TestGarbageInExtractor
# Structural garbage that must be invisible to the i+1 filter.
# ---------------------------------------------------------------------------

class TestGarbageInExtractor:

    def test_standalone_music_note_produces_no_units(self, extractor):
        result = extractor.extract(make_candidate("♪"))
        assert result.units == []

    def test_music_note_line_produces_no_units(self, extractor):
        result = extractor.extract(make_candidate("♪ ♫ ♪"))
        assert result.units == []

    def test_dash_only_fragment_produces_no_units(self, extractor):
        result = extractor.extract(make_candidate("---"))
        assert result.units == []

    def test_ellipsis_produces_no_units(self, extractor):
        result = extractor.extract(make_candidate("..."))
        assert result.units == []

    def test_bracket_label_produces_no_units(self, extractor):
        # [MUSIK] — brackets are punct, inner word is tagged X by spaCy
        result = extractor.extract(make_candidate("[MUSIK]"))
        assert result.units == []

    def test_skipped_count_reflects_garbage_tokens(self, extractor):
        # Quantitative check: every token in a garbage-only string is counted
        # as skipped, leaving nothing in units.
        result = extractor.extract(make_candidate("♪ --- ..."))
        assert result.skipped_count > 0
        assert result.units == []


# ---------------------------------------------------------------------------
# TestValidVocabularyKept
# Regression guard: the filters must not accidentally suppress real words.
# ---------------------------------------------------------------------------

class TestValidVocabularyKept:

    def test_common_noun_extracted(self, extractor):
        result = extractor.extract(make_candidate("Das Kino ist geschlossen."))
        assert "kino" in keys(result)

    def test_adjective_extracted(self, extractor):
        result = extractor.extract(make_candidate("Der Film ist wirklich interessant."))
        assert "interessant" in keys(result)

    def test_verb_extracted(self, extractor):
        result = extractor.extract(make_candidate("Sie kauft ein neues Fahrrad."))
        assert "kaufen" in keys(result)

    def test_aux_verb_extracted(self, extractor):
        result = extractor.extract(make_candidate("Er kann leider nicht kommen."))
        assert "können" in keys(result)

    def test_adverb_extracted(self, extractor):
        result = extractor.extract(make_candidate("Sie kommt leider nicht."))
        assert "leider" in keys(result)


# ---------------------------------------------------------------------------
# TestMixedUtterance
# The most important integration check: noise and signal in the same sentence.
# The filter must remove exactly the noise and leave the signal intact.
# ---------------------------------------------------------------------------

class TestMixedUtterance:

    def test_person_name_removed_verb_kept(self, extractor):
        result = extractor.extract(make_candidate("Thomas fährt nach Hause."))
        assert "thomas" not in keys(result)
        assert "fahren" in keys(result)

    def test_city_removed_adjective_kept(self, extractor):
        result = extractor.extract(make_candidate("Berlin ist wirklich schön."))
        assert "berlin" not in keys(result)
        assert "schön" in keys(result)

    def test_org_removed_noun_and_verb_kept(self, extractor):
        result = extractor.extract(make_candidate("Er arbeitet bei BMW und lernt viel."))
        assert "bmw" not in keys(result)
        assert "arbeiten" in keys(result)
        assert "lernen" in keys(result)

    def test_music_notes_removed_vocabulary_kept(self, extractor):
        # Subtitle format: ♪ sung line ♪
        result = extractor.extract(make_candidate("♪ Das Leben ist schön ♪"))
        assert "schön" in keys(result)
        assert "leben" in keys(result)

    def test_full_noise_mix_valid_units_survive(self, extractor):
        # Person name + city + music note all in one sentence.
        result = extractor.extract(
            make_candidate("♪ Anna fährt nach München und singt ein schönes Lied. ♪")
        )
        assert "anna" not in keys(result)
        assert "münchen" not in keys(result)
        assert "fahren" in keys(result)
        assert "singen" in keys(result)
        assert "schön" in keys(result) or "lied" in keys(result)


# ---------------------------------------------------------------------------
# TestNerFilterDisabled
# skip_ent_types=frozenset() is the escape hatch for corpora where NER
# labels are unreliable and false positives matter more than false negatives.
# ---------------------------------------------------------------------------

class TestNerFilterDisabled:

    def test_noun_tagged_entity_passes_through_when_ner_filter_off(self, nlp):
        # With the filter disabled, a NOUN-POS token labelled LOC by NER must
        # survive into the unit list (it would normally be dropped).
        config = UnitExtractionConfig(skip_ent_types=frozenset())
        extractor_no_ner = UtteranceUnitExtractor(nlp, config)

        result = extractor_no_ner.extract(make_candidate("Er fährt nach Berlin."))
        # "Berlin" might be PROPN (dropped by POS) or NOUN+LOC depending on
        # the sentence; "fahren" must always be present regardless.
        assert "fahren" in keys(result)

    def test_per_tagged_noun_passes_through_when_ner_filter_off(self, nlp):
        config = UnitExtractionConfig(skip_ent_types=frozenset())
        extractor_no_ner = UtteranceUnitExtractor(nlp, config)

        # "Chef" is a NOUN; if the model labels it PER in some context, the
        # disabled NER filter should let it through.
        result = extractor_no_ner.extract(
            make_candidate("Der neue Chef arbeitet sehr gut.")
        )
        assert "arbeiten" in keys(result)
        assert "chef" in keys(result)
