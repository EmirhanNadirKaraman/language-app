"""
test_subtitle_cleaner.py
------------------------
Tests for subtitle_cleaner.SubtitleTextCleaner and the updated parse_srt().

Coverage
--------
  TestAssTagStripping          — {\\an8} {\\b1} {\\pos(...)} ASS/SSA tags
  TestVttTimestampTagStripping — <00:00:01.234> WebVTT cue tags
  TestHtmlEntityDecoding       — &amp; &nbsp; &lt; &#160; etc.
  TestWhitespaceNormalization  — \\xa0 \\u200b soft-hyphen BOM etc.
  TestStrayTimestampStripping  — 00:01:23,456 and --> remnants in body
  TestCleanPassthrough         — clean text returns unchanged
  TestHasAlphabeticContent     — the fragment-filtering predicate
  TestFeatureToggles           — each step can be disabled independently
  TestCleanCombined            — multiple artifact types in one string
  TestParseSrtIntegration      — parse_srt() with messy SRT content
  TestEncodingFallback         — _read_subtitle_file() encoding chain
"""
import tempfile
from pathlib import Path

import pytest

from subtitle_cleaner import SubtitleCleanerConfig, SubtitleTextCleaner
from pipeline import _read_subtitle_file, parse_srt


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def cleaner() -> SubtitleTextCleaner:
    return SubtitleTextCleaner()


# ---------------------------------------------------------------------------
# TestAssTagStripping
# ---------------------------------------------------------------------------

class TestAssTagStripping:

    def test_positioning_tag_removed(self, cleaner):
        assert cleaner.clean("{\\an8}Das ist gut.") == "Das ist gut."

    def test_bold_tag_removed(self, cleaner):
        assert cleaner.clean("{\\b1}Achtung!{\\b0}") == "Achtung!"

    def test_italic_tag_removed(self, cleaner):
        assert cleaner.clean("{\\i1}Wirklich?{\\i0}") == "Wirklich?"

    def test_position_with_coordinates_removed(self, cleaner):
        assert cleaner.clean("{\\pos(100,200)}Hallo.") == "Hallo."

    def test_colour_tag_removed(self, cleaner):
        assert cleaner.clean("{\\c&H00FF00&}Text{\\c}") == "Text"

    def test_move_tag_removed(self, cleaner):
        result = cleaner.clean("{\\move(0,0,100,100,0,1000)}Er kommt.")
        assert result == "Er kommt."

    def test_multiple_ass_tags_all_removed(self, cleaner):
        result = cleaner.clean("{\\an8}{\\b1}{\\i1}Wichtige Meldung!{\\i0}{\\b0}")
        assert result == "Wichtige Meldung!"

    def test_standalone_ass_tag_yields_empty_string(self, cleaner):
        # A fragment that is only a positioning tag has no text content.
        assert cleaner.clean("{\\an8}") == ""

    def test_ass_tag_mid_sentence_removed(self, cleaner):
        result = cleaner.clean("Das ist {\\b1}wirklich{\\b0} gut.")
        assert result == "Das ist wirklich gut."

    def test_normal_text_without_curly_braces_unchanged(self, cleaner):
        # Curly braces in German are genuinely rare but let's confirm the
        # regex only matches the specific {backslash...} pattern.
        text = "Das ist wirklich gut."
        assert cleaner.clean(text) == text


# ---------------------------------------------------------------------------
# TestVttTimestampTagStripping
# ---------------------------------------------------------------------------

class TestVttTimestampTagStripping:

    def test_single_timestamp_tag_removed(self, cleaner):
        result = cleaner.clean("<00:00:01.234>Das ist gut.")
        assert result == "Das ist gut."

    def test_multiple_timestamp_tags_removed(self, cleaner):
        # Karaoke-style VTT with per-word cue timing.
        result = cleaner.clean(
            "<00:00:01.000>Das <00:00:01.400>ist <00:00:01.700>wirklich gut."
        )
        assert result == "Das ist wirklich gut."

    def test_timestamp_tag_between_words_leaves_clean_spacing(self, cleaner):
        result = cleaner.clean("Er<00:00:02.500> kommt.")
        assert result == "Er kommt."

    def test_single_digit_hour_also_matched(self, cleaner):
        # VTT also allows H:MM:SS.mmm format.
        result = cleaner.clean("<0:00:01.500>Gut.")
        assert result == "Gut."


# ---------------------------------------------------------------------------
# TestHtmlEntityDecoding
# ---------------------------------------------------------------------------

class TestHtmlEntityDecoding:

    def test_ampersand_entity_decoded(self, cleaner):
        assert cleaner.clean("Tom &amp; Jerry") == "Tom & Jerry"

    def test_less_than_entity_decoded(self, cleaner):
        assert cleaner.clean("Wenn a &lt; b gilt") == "Wenn a < b gilt"

    def test_greater_than_entity_decoded(self, cleaner):
        assert cleaner.clean("Wenn a &gt; b gilt") == "Wenn a > b gilt"

    def test_nbsp_decoded_then_normalised_to_space(self, cleaner):
        # &nbsp; → \xa0 (by html.unescape) → " " (by normalize_whitespace)
        result = cleaner.clean("Das&nbsp;ist gut.")
        assert result == "Das ist gut."

    def test_numeric_entity_decoded(self, cleaner):
        assert cleaner.clean("&#160;Text") == "Text"   # \xa0 → space → stripped

    def test_hex_entity_decoded(self, cleaner):
        assert cleaner.clean("Das&#x27;s gut.") == "Das's gut."

    def test_named_umlaut_entity_decoded(self, cleaner):
        assert cleaner.clean("&Ouml;sterreich") == "Österreich"

    def test_literal_ampersand_without_entity_unchanged(self, cleaner):
        # A bare "&" that isn't part of an entity should survive intact.
        text = "Tom & Jerry fahren weg."
        assert cleaner.clean(text) == text

    def test_double_encoded_entity_decoded_once(self, cleaner):
        # html.unescape decodes one level only — &amp;amp; → &amp; not &
        result = cleaner.clean("&amp;amp;")
        assert result == "&amp;"


# ---------------------------------------------------------------------------
# TestWhitespaceNormalization
# ---------------------------------------------------------------------------

class TestWhitespaceNormalization:

    def test_non_breaking_space_becomes_regular_space(self, cleaner):
        result = cleaner.clean("Das\xa0ist gut.")
        assert result == "Das ist gut."

    def test_multiple_non_breaking_spaces_collapsed(self, cleaner):
        result = cleaner.clean("Das\xa0\xa0ist gut.")
        assert result == "Das ist gut."

    def test_zero_width_space_removed(self, cleaner):
        result = cleaner.clean("Das\u200bist gut.")
        assert result == "Dasist gut."

    def test_zero_width_space_between_words_removed(self, cleaner):
        result = cleaner.clean("Das \u200bist gut.")
        assert result == "Das ist gut."

    def test_soft_hyphen_removed(self, cleaner):
        result = cleaner.clean("Lieb\u00adlings\u00adfilm")
        assert result == "Lieblingsfilm"

    def test_zero_width_non_joiner_removed(self, cleaner):
        result = cleaner.clean("gut\u200cgemeint")
        assert result == "gutgemeint"

    def test_mid_file_bom_removed(self, cleaner):
        result = cleaner.clean("Text\ufeffmehr Text.")
        assert result == "Textmehr Text."  # BOM removed; surrounding text joined, trailing space preserved

    def test_multiple_different_invisible_chars_all_removed(self, cleaner):
        result = cleaner.clean("A\u200b\u200c\u200d\u2060B")
        assert result == "AB"


# ---------------------------------------------------------------------------
# TestStrayTimestampStripping
# ---------------------------------------------------------------------------

class TestStrayTimestampStripping:

    def test_stray_srt_timestamp_removed(self, cleaner):
        result = cleaner.clean("Das war schön. 00:01:23,456 Und das auch.")
        assert result == "Das war schön. Und das auch."

    def test_stray_vtt_timestamp_removed(self, cleaner):
        result = cleaner.clean("Das war schön. 00:01:23.456 Weiter.")
        assert result == "Das war schön. Weiter."

    def test_srt_arrow_remnant_removed(self, cleaner):
        result = cleaner.clean("Wir warten --> 00:02:00,000 auf dich.")
        assert result == "Wir warten auf dich."

    def test_stray_timestamp_at_start_removed(self, cleaner):
        result = cleaner.clean("00:00:05,000 Das ist gut.")
        assert result == "Das ist gut."

    def test_stray_timestamp_at_end_removed(self, cleaner):
        result = cleaner.clean("Das ist gut. 00:00:07,500")
        assert result == "Das ist gut."

    def test_legitimate_time_expression_not_stripped(self, cleaner):
        # "um 8:30 Uhr" has only H:MM — the regex requires HH:MM:SS,mmm.
        text = "Wir treffen uns um 8:30 Uhr."
        assert cleaner.clean(text) == text

    def test_plain_timestamp_without_arrow_removed(self, cleaner):
        # A stray full SRT timestamp with comma separator is removed even
        # when no --> arrow accompanies it.
        result = cleaner.clean("Text 00:05:30,000 mehr Text.")
        assert result == "Text mehr Text."


# ---------------------------------------------------------------------------
# TestCleanPassthrough
# ---------------------------------------------------------------------------

class TestCleanPassthrough:
    """Clean German text should survive the cleaner unchanged."""

    def test_normal_sentence_unchanged(self, cleaner):
        text = "Ich gehe heute ins Kino."
        assert cleaner.clean(text) == text

    def test_sentence_with_html_tags_passes_through_uncleaned(self, cleaner):
        # HTML tags like <i> are NOT stripped by this cleaner — that is
        # SubtitleFragment.cleaned_text()'s responsibility.
        text = "<i>Das ist wirklich schön.</i>"
        assert cleaner.clean(text) == text

    def test_dialogue_dash_preserved(self, cleaner):
        # Leading dash is preserved so the multi-speaker guard can see it.
        text = "- Das war gut."
        assert cleaner.clean(text) == text

    def test_bracket_annotation_preserved(self, cleaner):
        # Bracket annotations are kept for downstream cleaned_text().
        text = "[Musik] Ja, natürlich."
        assert cleaner.clean(text) == text

    def test_music_note_preserved(self, cleaner):
        # ♪ is not stripped here — the quality filter handles it.
        text = "♪ La la la ♪"
        assert cleaner.clean(text) == text

    def test_german_umlauts_preserved(self, cleaner):
        text = "Österreich ist wunderschön."
        assert cleaner.clean(text) == text


# ---------------------------------------------------------------------------
# TestHasAlphabeticContent
# ---------------------------------------------------------------------------

class TestHasAlphabeticContent:

    def test_empty_string_false(self):
        assert SubtitleTextCleaner.has_alphabetic_content("") is False

    def test_whitespace_only_false(self):
        assert SubtitleTextCleaner.has_alphabetic_content("   ") is False

    def test_digits_only_false(self):
        assert SubtitleTextCleaner.has_alphabetic_content("123") is False

    def test_punctuation_only_false(self):
        assert SubtitleTextCleaner.has_alphabetic_content("...---!!!") is False

    def test_music_notes_only_false(self):
        assert SubtitleTextCleaner.has_alphabetic_content("♪ ♫ ♪") is False

    def test_normal_german_text_true(self):
        assert SubtitleTextCleaner.has_alphabetic_content("Das ist gut.") is True

    def test_single_letter_true(self):
        assert SubtitleTextCleaner.has_alphabetic_content("a") is True

    def test_bracket_annotation_true(self):
        # [Musik] still has letters — this is intentional: downstream handles it.
        assert SubtitleTextCleaner.has_alphabetic_content("[Musik]") is True

    def test_umlaut_true(self):
        assert SubtitleTextCleaner.has_alphabetic_content("ü") is True


# ---------------------------------------------------------------------------
# TestFeatureToggles
# ---------------------------------------------------------------------------

class TestFeatureToggles:
    """Every cleaning step can be disabled independently via config."""

    def test_ass_tags_not_stripped_when_disabled(self):
        cfg = SubtitleCleanerConfig(strip_ass_tags=False)
        c = SubtitleTextCleaner(cfg)
        result = c.clean("{\\an8}Das ist gut.")
        assert "{\\an8}" in result

    def test_vtt_tags_not_stripped_when_disabled(self):
        # Also disable stray timestamp stripping; otherwise _STRAY_TIMESTAMP_RE
        # matches the timestamp content inside the angle brackets (word boundary
        # fires after '<'), leaving '<>' with no timestamp.
        cfg = SubtitleCleanerConfig(strip_vtt_timestamp_tags=False, strip_stray_timestamps=False)
        c = SubtitleTextCleaner(cfg)
        result = c.clean("<00:00:01.234>Das ist gut.")
        assert "<00:00:01.234>" in result

    def test_html_entities_not_decoded_when_disabled(self):
        cfg = SubtitleCleanerConfig(decode_html_entities=False)
        c = SubtitleTextCleaner(cfg)
        result = c.clean("Tom &amp; Jerry")
        assert "&amp;" in result

    def test_whitespace_not_normalised_when_disabled(self):
        cfg = SubtitleCleanerConfig(normalize_whitespace=False)
        c = SubtitleTextCleaner(cfg)
        result = c.clean("Das\xa0ist gut.")
        assert "\xa0" in result

    def test_stray_timestamps_not_stripped_when_disabled(self):
        cfg = SubtitleCleanerConfig(strip_stray_timestamps=False)
        c = SubtitleTextCleaner(cfg)
        result = c.clean("Text 00:01:23,456 mehr Text.")
        assert "00:01:23,456" in result

    def test_all_steps_disabled_returns_whitespace_collapsed_only(self):
        # Even with everything disabled, whitespace collapsing still applies.
        cfg = SubtitleCleanerConfig(
            strip_ass_tags=False,
            strip_vtt_timestamp_tags=False,
            decode_html_entities=False,
            normalize_whitespace=False,
            strip_stray_timestamps=False,
        )
        c = SubtitleTextCleaner(cfg)
        result = c.clean("  Das  ist  gut.  ")
        assert result == "Das ist gut."


# ---------------------------------------------------------------------------
# TestCleanCombined
# ---------------------------------------------------------------------------

class TestCleanCombined:
    """Multiple artifact types in a single fragment."""

    def test_ass_tag_plus_entity(self, cleaner):
        result = cleaner.clean("{\\an8}Tom &amp; Jerry fahren weg.")
        assert result == "Tom & Jerry fahren weg."

    def test_vtt_timestamps_plus_nbsp(self, cleaner):
        result = cleaner.clean(
            "<00:00:01.000>Das\xa0ist <00:00:01.500>wirklich gut."
        )
        assert result == "Das ist wirklich gut."

    def test_ass_tag_plus_stray_timestamp_plus_nbsp(self, cleaner):
        result = cleaner.clean(
            "{\\an8}Das war schön. 00:01:23,456\xa0Ja, wirklich."
        )
        assert result == "Das war schön. Ja, wirklich."

    def test_fully_artifactual_fragment_yields_empty(self, cleaner):
        # Only an ASS tag — nothing left after cleaning.
        result = cleaner.clean("{\\an8}{\\b1}")
        assert result == ""
        assert not SubtitleTextCleaner.has_alphabetic_content(result)

    def test_real_world_styled_subtitle_line(self, cleaner):
        # Typical ASS-converted line: positioning + bold for the speaker name.
        result = cleaner.clean("{\\an2}{\\b1}Klaus:{\\b0} Das war nicht meine Absicht.")
        assert result == "Klaus: Das war nicht meine Absicht."


# ---------------------------------------------------------------------------
# TestParseSrtIntegration
# ---------------------------------------------------------------------------

def _write_srt(content: str, encoding: str = "utf-8") -> Path:
    """Write an SRT string to a temp file and return its Path."""
    f = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".srt", delete=False
    )
    f.write(content.encode(encoding))
    f.close()
    return Path(f.name)


class TestParseSrtIntegration:

    def test_clean_srt_parses_normally(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Ich gehe heute ins Kino.\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\n"
            "Der Film ist wirklich gut.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert len(frags) == 2
            assert frags[0].text == "Ich gehe heute ins Kino."
            assert frags[1].text == "Der Film ist wirklich gut."
        finally:
            p.unlink()

    def test_ass_tags_stripped_before_fragment_creation(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "{\\an8}Das ist wirklich interessant.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert frags[0].text == "Das ist wirklich interessant."
        finally:
            p.unlink()

    def test_fragment_with_only_ass_tag_is_dropped(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "{\\an8}\n\n"
            "2\n00:00:03,000 --> 00:00:05,000\n"
            "Das hier bleibt erhalten.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert len(frags) == 1
            assert frags[0].text == "Das hier bleibt erhalten."
        finally:
            p.unlink()

    def test_html_entities_decoded_in_fragments(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Tom &amp; Jerry fahren nach &Ouml;sterreich.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert frags[0].text == "Tom & Jerry fahren nach Österreich."
        finally:
            p.unlink()

    def test_stray_timestamp_stripped_from_body(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Das war schön. 00:01:23,456 Wirklich.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert "00:01:23,456" not in frags[0].text
            assert "Das war schön." in frags[0].text
            assert "Wirklich." in frags[0].text
        finally:
            p.unlink()

    def test_music_note_only_fragment_dropped(self):
        # ♪ has no alphabetic content — fragment should be silently skipped.
        srt = (
            "1\n00:00:01,000 --> 00:00:02,000\n"
            "♪ ♫ ♪\n\n"
            "2\n00:00:03,000 --> 00:00:05,000\n"
            "Das ist gut.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert len(frags) == 1
            assert frags[0].text == "Das ist gut."
        finally:
            p.unlink()

    def test_multiline_block_joined_with_space(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Ich gehe morgen\n"
            "ins Kino.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert frags[0].text == "Ich gehe morgen ins Kino."
        finally:
            p.unlink()

    def test_fragment_indices_are_sequential(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:02,000\nEins.\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\nZwei.\n\n"
            "3\n00:00:05,000 --> 00:00:06,000\nDrei.\n"
        )
        p = _write_srt(srt)
        try:
            frags = parse_srt(p)
            assert [f.index for f in frags] == [0, 1, 2]
        finally:
            p.unlink()

    def test_custom_cleaner_is_used(self):
        # With stray_timestamps disabled, the timestamp survives.
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Text 00:01:23,456 mehr Text.\n"
        )
        p = _write_srt(srt)
        cfg = SubtitleCleanerConfig(strip_stray_timestamps=False)
        custom_cleaner = SubtitleTextCleaner(cfg)
        try:
            frags = parse_srt(p, cleaner=custom_cleaner)
            assert "00:01:23,456" in frags[0].text
        finally:
            p.unlink()


# ---------------------------------------------------------------------------
# TestEncodingFallback
# ---------------------------------------------------------------------------

class TestEncodingFallback:

    def test_utf8_file_read_correctly(self):
        p = _write_srt(
            "1\n00:00:01,000 --> 00:00:02,000\nÖsterreich.\n",
            encoding="utf-8",
        )
        try:
            text = _read_subtitle_file(p)
            assert "Österreich" in text
        finally:
            p.unlink()

    def test_utf8_bom_file_read_correctly(self):
        # utf-8-sig strips the BOM automatically.
        content = "1\n00:00:01,000 --> 00:00:02,000\nGuten Tag.\n"
        p = tempfile.NamedTemporaryFile(mode="wb", suffix=".srt", delete=False)
        p.write(b"\xef\xbb\xbf" + content.encode("utf-8"))  # BOM + UTF-8
        p.close()
        path = Path(p.name)
        try:
            text = _read_subtitle_file(path)
            assert "Guten Tag." in text
        finally:
            path.unlink()

    def test_cp1252_file_read_correctly(self):
        # German umlauts in cp1252 would fail UTF-8 decoding.
        content = "1\n00:00:01,000 --> 00:00:02,000\nSchönes Wetter heute.\n"
        p = tempfile.NamedTemporaryFile(mode="wb", suffix=".srt", delete=False)
        p.write(content.encode("cp1252"))
        p.close()
        path = Path(p.name)
        try:
            text = _read_subtitle_file(path)
            assert "Schönes Wetter heute." in text
        finally:
            path.unlink()

    def test_latin1_file_read_correctly(self):
        content = "1\n00:00:01,000 --> 00:00:02,000\nMünchen ist schön.\n"
        p = tempfile.NamedTemporaryFile(mode="wb", suffix=".srt", delete=False)
        p.write(content.encode("latin-1"))
        p.close()
        path = Path(p.name)
        try:
            text = _read_subtitle_file(path)
            assert "München" in text
        finally:
            path.unlink()

    def test_cp1252_srt_parses_fully(self):
        # End-to-end: parse_srt() on a cp1252 file produces correct fragments.
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Das Wetter ist schön.\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\n"
            "Wir fahren nach München.\n"
        )
        p = tempfile.NamedTemporaryFile(mode="wb", suffix=".srt", delete=False)
        p.write(srt.encode("cp1252"))
        p.close()
        path = Path(p.name)
        try:
            frags = parse_srt(path)
            assert len(frags) == 2
            assert "schön" in frags[0].text
            assert "München" in frags[1].text
        finally:
            path.unlink()
