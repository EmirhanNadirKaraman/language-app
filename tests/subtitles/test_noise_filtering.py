"""
test_noise_filtering.py
-----------------------
Focused tests for the noise-filtering behaviour added to UtteranceUnitExtractor.
"""
import pytest
import spacy

from app.subtitles.models import MergedSubtitleWindow, SubtitleFragment, CandidateUtterance
from app.extraction.extractor import UtteranceUnitExtractor
from app.extraction.models import UnitExtractionConfig, UtteranceExtractionResult, _has_garbage_symbols


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
# ---------------------------------------------------------------------------

class TestGarbageSymbolHelper:

    def test_standalone_musical_note(self):
        assert _has_garbage_symbols("♪") is True

    def test_musical_note_fused_with_text(self):
        assert _has_garbage_symbols("♪Danke♪") is True

    def test_trademark_symbol(self):
        assert _has_garbage_symbols("word™") is True

    def test_zero_width_format_character(self):
        assert _has_garbage_symbols("text\u200b") is True

    def test_normal_german_word_not_garbage(self):
        assert _has_garbage_symbols("schön") is False

    def test_word_with_hyphen_not_garbage(self):
        assert _has_garbage_symbols("nicht-so-schön") is False


# ---------------------------------------------------------------------------
# TestProperNounPosFilter
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
        result = extractor.extract(make_candidate("Anna fährt nach Hause."))
        assert "fahren" in keys(result)


# ---------------------------------------------------------------------------
# TestNamedEntityFilter
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
        result = extractor.extract(make_candidate("Der deutsche Film ist gut."))
        assert "deutsch" in keys(result)

    def test_common_noun_without_ner_label_passes_through(self, extractor):
        result = extractor.extract(make_candidate("Das Buch liegt auf dem Tisch."))
        assert "buch" in keys(result)
        assert "tisch" in keys(result)


# ---------------------------------------------------------------------------
# TestGarbageInExtractor
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
        result = extractor.extract(make_candidate("[MUSIK]"))
        assert result.units == []

    def test_skipped_count_reflects_garbage_tokens(self, extractor):
        result = extractor.extract(make_candidate("♪ --- ..."))
        assert result.skipped_count > 0
        assert result.units == []


# ---------------------------------------------------------------------------
# TestValidVocabularyKept
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
        result = extractor.extract(make_candidate("♪ Das Leben ist schön ♪"))
        assert "schön" in keys(result)
        assert "leben" in keys(result)

    def test_full_noise_mix_valid_units_survive(self, extractor):
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
# ---------------------------------------------------------------------------

class TestNerFilterDisabled:

    def test_noun_tagged_entity_passes_through_when_ner_filter_off(self, nlp):
        config = UnitExtractionConfig(skip_ent_types=frozenset())
        extractor_no_ner = UtteranceUnitExtractor(nlp, config)

        result = extractor_no_ner.extract(make_candidate("Er fährt nach Berlin."))
        assert "fahren" in keys(result)

    def test_per_tagged_noun_passes_through_when_ner_filter_off(self, nlp):
        config = UnitExtractionConfig(skip_ent_types=frozenset())
        extractor_no_ner = UtteranceUnitExtractor(nlp, config)

        result = extractor_no_ner.extract(
            make_candidate("Der neue Chef arbeitet sehr gut.")
        )
        assert "arbeiten" in keys(result)
        assert "chef" in keys(result)
