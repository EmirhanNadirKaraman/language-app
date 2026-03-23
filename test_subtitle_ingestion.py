"""
test_subtitle_ingestion.py
--------------------------
Integration tests for the subtitle ingestion pipeline: parse_srt() with
SubtitleTextCleaner acting on realistic German subtitle files.

Why subtitle-ingestion robustness matters early in the pipeline
---------------------------------------------------------------
parse_srt() is the single entry point for all text that flows downstream.
Every stage that follows — SubtitleMerger, UtteranceQualityEvaluator,
spaCy tokenisation, phrase matching — was written to handle clean German
prose, not file-format debris.  An ASS styling tag like {\\an8} that
reaches the tokeniser produces a meaningless token; a stray SRT timestamp
in the body text skews alpha-ratio checks and can let low-quality fragments
past the quality filter; an &amp; entity that survives into phrase matching
will silently fail to match the expected lemma.

Fixing artifact leakage at the source is far cheaper than patching every
consumer.  It also keeps each consumer's test surface focused on its own
logic rather than defensive artifact handling that does not belong there.

These tests exercise the full ingestion path (parse_srt → SubtitleTextCleaner)
and are grouped by the six main artifact classes:

  1. Simple HTML tags (<i>, <b>, <font>)   — intentionally preserved here;
                                             stripped downstream by cleaned_text()
  2. Styling / position artifacts          — ASS tags, VTT cue timestamps
  3. Blank and garbage lines               — dropped when no alphabetic content
  4. Malformed subtitle content            — ValueError when nothing survives;
                                             graceful degradation otherwise
  5. Spoken text preservation              — dialogue dashes, umlauts, etc.
  6. Realistic messy snippet files         — multiple artifact types combined
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline import parse_srt
from subtitle_cleaner import SubtitleCleanerConfig, SubtitleTextCleaner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_srt(content: str, tmp_path: Path, encoding: str = "utf-8") -> Path:
    """Write *content* to a temporary .srt file and return its path."""
    p = tmp_path / "test.srt"
    p.write_bytes(content.encode(encoding))
    return p


def _block(n: int, start: str, end: str, *lines: str) -> str:
    """Return a single well-formed SRT block followed by a blank separator."""
    body = "\n".join(lines)
    return f"{n}\n{start} --> {end}\n{body}\n\n"


# ---------------------------------------------------------------------------
# 1. HTML tag pass-through
#    <i>, <b>, <font color="..."> are intentionally NOT stripped here.
#    SubtitleFragment.cleaned_text() handles them downstream, so stripping
#    them early would break any code that inspects fragment.text directly.
# ---------------------------------------------------------------------------

class TestHtmlTagPassthrough:

    def test_italic_tag_preserved_in_fragment_text(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000", "<i>Ich gehe jetzt.</i>")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "<i>" in fragments[0].text
        assert "</i>" in fragments[0].text

    def test_bold_tag_preserved_in_fragment_text(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000", "<b>Achtung!</b>")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "<b>" in fragments[0].text

    def test_font_colour_tag_text_content_survives(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     '<font color="red">Das ist gefährlich.</font>')
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "Das ist gefährlich." in fragments[0].text

    def test_nested_italic_and_bold_both_preserved(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "<b><i>Das ist sehr wichtig.</i></b>")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "Das ist sehr wichtig." in fragments[0].text
        assert "<b>" in fragments[0].text
        assert "<i>" in fragments[0].text

    def test_html_entity_inside_italic_tag_decoded(self, tmp_path):
        # HTML entity decoding runs even when tags are preserved.
        # &amp; → &, but the surrounding <i> tag stays intact.
        srt = _block(1, "00:00:01,000", "00:00:03,000", "<i>Tom &amp; Jerry</i>")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "&amp;" not in fragments[0].text
        assert "Tom & Jerry" in fragments[0].text
        assert "<i>" in fragments[0].text

    def test_html_tagged_fragment_not_dropped_by_alpha_filter(self, tmp_path):
        # The alpha filter must see through the tag wrappers and keep the fragment.
        srt = _block(1, "00:00:01,000", "00:00:03,000", "<i>Ja.</i>")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1


# ---------------------------------------------------------------------------
# 2. Styling and position artifact removal
#    ASS/SSA override tags and WebVTT karaoke cue timestamps are stripped
#    before the fragment is created.  The spoken text must survive intact.
# ---------------------------------------------------------------------------

class TestStylingArtifactRemoval:

    def test_ass_positioning_tag_stripped(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "{\\an8}Das ist wirklich interessant.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "{" not in fragments[0].text
        assert "Das ist wirklich interessant." in fragments[0].text

    def test_multiple_ass_tags_all_stripped(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "{\\an8}{\\b1}Achtung, Spoiler!{\\b0}")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "Achtung, Spoiler!" in fragments[0].text
        assert "{" not in fragments[0].text

    def test_ass_colour_override_stripped(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "{\\c&H00FF00&}Grüner Text hier.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "Grüner Text hier." in fragments[0].text

    def test_ass_coordinate_position_tag_stripped(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "{\\pos(320,460)}Untertitel unten.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "Untertitel unten." in fragments[0].text

    def test_vtt_karaoke_cue_timestamps_stripped(self, tmp_path):
        # Word-level timing tags from karaoke-style VTT — purely positional,
        # carry no text content.
        srt = _block(1, "00:00:01,000", "00:00:04,000",
                     "<00:00:01.000>Ich <00:00:01.300>gehe <00:00:01.600>nach <00:00:02.000>Hause.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert fragments[0].text == "Ich gehe nach Hause."

    def test_stray_srt_arrow_remnant_stripped(self, tmp_path):
        # Malformed block split: timing arrow bleeds into body text.
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "Wir warten --> 00:02:00,000 auf dich.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "-->" not in fragments[0].text
        assert "Wir warten" in fragments[0].text
        assert "auf dich" in fragments[0].text

    def test_stray_srt_timestamp_in_body_stripped(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "Das war schön. 00:01:23,456 Und das auch.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert re.search(r"\d{2}:\d{2}:\d{2},\d{3}", fragments[0].text) is None
        assert "Das war schön." in fragments[0].text
        assert "Und das auch." in fragments[0].text


# ---------------------------------------------------------------------------
# 3. Blank and garbage line filtering
#    Fragments that contain no alphabetic content after cleaning are dropped.
#    When all fragments are garbage, parse_srt() raises ValueError.
# ---------------------------------------------------------------------------

class TestBlankAndGarbageFiltering:

    def test_music_note_only_raises_value_error(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:02,000", "♪ ♫")
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt(srt, tmp_path)))

    def test_ass_only_tag_raises_value_error(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:02,000", "{\\an8}")
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt(srt, tmp_path)))

    def test_punctuation_only_raises_value_error(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:02,000", "---")
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt(srt, tmp_path)))

    def test_digit_only_fragment_raises_value_error(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:02,000", "123")
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt(srt, tmp_path)))

    def test_garbage_fragment_between_valid_ones_is_dropped(self, tmp_path):
        srt = (
            _block(1, "00:00:01,000", "00:00:03,000", "Hallo, wie geht es dir?")
            + _block(2, "00:00:04,000", "00:00:05,000", "♪ ♫")
            + _block(3, "00:00:06,000", "00:00:08,000", "Mir geht es gut, danke.")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 2
        assert "Hallo" in fragments[0].text
        assert "danke" in fragments[1].text

    def test_multiple_garbage_fragments_between_valid_ones_dropped(self, tmp_path):
        srt = (
            _block(1, "00:00:01,000", "00:00:03,000", "Ich weiß es nicht.")
            + _block(2, "00:00:04,000", "00:00:05,000", "♪")
            + _block(3, "00:00:05,500", "00:00:06,000", "{\\an8}")
            + _block(4, "00:00:06,500", "00:00:07,000", "---")
            + _block(5, "00:00:08,000", "00:00:10,000", "Vielleicht morgen.")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 2

    def test_dropped_garbage_does_not_create_index_gaps(self, tmp_path):
        # Fragment indices must be contiguous (0, 1, 2), not (0, 2, 4).
        srt = (
            _block(1, "00:00:01,000", "00:00:03,000", "Erster Satz.")
            + _block(2, "00:00:04,000", "00:00:05,000", "♪ ♫")
            + _block(3, "00:00:06,000", "00:00:08,000", "Zweiter Satz.")
            + _block(4, "00:00:09,000", "00:00:10,000", "---")
            + _block(5, "00:00:11,000", "00:00:13,000", "Dritter Satz.")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert [f.index for f in fragments] == [0, 1, 2]


# ---------------------------------------------------------------------------
# 4. Malformed subtitle content — graceful degradation
#    Files that are completely invalid raise ValueError.
#    Files with partial content return only the valid fragments.
# ---------------------------------------------------------------------------

class TestMalformedSubtitleGrace:

    def test_empty_file_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt("", tmp_path)))

    def test_whitespace_only_file_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt("   \n\n\n  ", tmp_path)))

    def test_non_srt_file_raises_value_error(self, tmp_path):
        # A plain text file with no timestamp lines produces no valid blocks.
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt("Das ist kein Untertitel.\n", tmp_path)))

    def test_all_blocks_pure_garbage_raises_value_error(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:02,000", "♪") + \
              _block(2, "00:00:03,000", "00:00:04,000", "{\\an8}") + \
              _block(3, "00:00:05,000", "00:00:06,000", "---")
        with pytest.raises(ValueError):
            parse_srt(str(_write_srt(srt, tmp_path)))

    def test_utf8_bom_file_parsed_correctly(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000", "Ich gehe nach Hause.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path, encoding="utf-8-sig")))
        assert len(fragments) == 1
        assert fragments[0].text == "Ich gehe nach Hause."

    def test_cp1252_encoded_umlauts_decoded_correctly(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000", "Das ist wunderschön.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path, encoding="cp1252")))
        assert len(fragments) == 1
        assert "wunderschön" in fragments[0].text

    def test_windows_smart_quotes_survive_cp1252_decode(self, tmp_path):
        # cp1252 code points 0x93/0x94 are curly quotes — must not corrupt.
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "Er sagte \u201eDas stimmt.\u201c")
        fragments = parse_srt(str(_write_srt(srt, tmp_path, encoding="cp1252")))
        assert len(fragments) == 1
        assert "Das stimmt" in fragments[0].text


# ---------------------------------------------------------------------------
# 5. Spoken text preservation
#    Artefact removal must leave genuine dialogue completely intact.
#    This section guards the boundary between "strip this" and "keep this".
# ---------------------------------------------------------------------------

class TestSpokenTextPreservation:

    def test_plain_german_sentence_preserved_exactly(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:04,000",
                     "Das ist eine sehr schöne Stadt.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert fragments[0].text == "Das ist eine sehr schöne Stadt."

    def test_dialogue_dash_preserved_for_speaker_detection(self, tmp_path):
        # The multi-speaker guard in SubtitleMerger reads the raw leading dash —
        # stripping it here would silently break speaker-turn detection.
        srt = _block(1, "00:00:01,000", "00:00:03,000", "- Wie geht's dir?")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert fragments[0].text.startswith("-")

    def test_bracket_annotation_preserved(self, tmp_path):
        # [Musik], [lacht] etc. are handled by cleaned_text() downstream.
        srt = _block(1, "00:00:01,000", "00:00:03,000", "[Musik] Ja, natürlich.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert "[Musik]" in fragments[0].text

    def test_parenthetical_annotation_preserved(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "(lacht) Das war lustig.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert "(lacht)" in fragments[0].text

    def test_german_umlauts_and_eszett_preserved(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:04,000",
                     "Übrigens, das Mädchen heißt Bärbel.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert "Übrigens" in fragments[0].text
        assert "Mädchen" in fragments[0].text
        assert "heißt" in fragments[0].text
        assert "Bärbel" in fragments[0].text

    def test_music_note_with_surrounding_text_kept(self, tmp_path):
        # Fragment has alphabetic content; the music note just stays in text.
        srt = _block(1, "00:00:01,000", "00:00:03,000", "♪ La la la ♪")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "la" in fragments[0].text.lower()

    def test_legitimate_time_expression_not_stripped(self, tmp_path):
        # "8:30" does not match the HH:MM:SS,mmm pattern and must survive.
        srt = _block(1, "00:00:01,000", "00:00:04,000",
                     "Ich komme um 8:30 Uhr.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert "8:30" in fragments[0].text

    def test_multiline_block_joined_with_space(self, tmp_path):
        srt = _block(1, "00:00:01,000", "00:00:04,000",
                     "Ich weiß nicht,", "ob das wirklich stimmt.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "Ich weiß nicht," in fragments[0].text
        assert "ob das wirklich stimmt." in fragments[0].text
        # Joined with a space, not a newline
        assert "\n" not in fragments[0].text

    def test_fragment_timing_parsed_correctly(self, tmp_path):
        srt = _block(1, "00:01:23,456", "00:01:26,789",
                     "Das war ein langer Tag.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert abs(fragments[0].start_time - 83.456) < 0.001
        assert abs(fragments[0].end_time - 86.789) < 0.001


# ---------------------------------------------------------------------------
# 6. Realistic messy subtitle snippets
#    End-to-end tests that mirror real-world files with several artifact
#    types mixed together.  If these pass, the ingestion stage is robust
#    enough to feed clean input to the rest of the pipeline.
# ---------------------------------------------------------------------------

class TestRealisticMessySnippets:

    def test_documentary_file_ass_positioned_with_one_garbage_fragment(self, tmp_path):
        srt = (
            _block(1, "00:00:10,500", "00:00:13,000",
                   "{\\an8}Im Jahr 1989 fiel die Berliner Mauer.")
            + _block(2, "00:00:13,500", "00:00:16,000",
                     "Das war ein historischer Moment.")
            + _block(3, "00:00:16,500", "00:00:17,500", "♪")
            + _block(4, "00:00:18,000", "00:00:21,000",
                     "{\\an8}Millionen Menschen feierten.")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 3  # ♪-only fragment dropped
        assert "Im Jahr 1989 fiel die Berliner Mauer." in fragments[0].text
        assert "Das war ein historischer Moment." in fragments[1].text
        assert "Millionen Menschen feierten." in fragments[2].text
        assert all("{" not in f.text for f in fragments)

    def test_file_mixing_ass_entities_html_tags_and_garbage(self, tmp_path):
        srt = (
            _block(1, "00:00:01,000", "00:00:03,000",
                   "{\\an8}Tom &amp; Jerry laufen schnell.")
            + _block(2, "00:00:04,000", "00:00:05,000", "♪ ♫")
            + _block(3, "00:00:06,000", "00:00:08,000",
                     "<i>Das war wirklich lustig!</i>")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 2
        assert "Tom & Jerry laufen schnell." in fragments[0].text
        assert "<i>" in fragments[1].text          # italic tag preserved
        assert "Das war wirklich lustig!" in fragments[1].text

    def test_karaoke_vtt_style_file_words_reconstructed(self, tmp_path):
        # Some tools emit .srt-like files with per-word VTT cue timestamps.
        srt = (
            _block(1, "00:00:01,000", "00:00:05,000",
                   "<00:00:01.000>Ich <00:00:01.300>fahre <00:00:01.700>nach <00:00:02.100>Berlin.")
            + _block(2, "00:00:06,000", "00:00:09,000",
                     "<00:00:06.000>Bis <00:00:06.400>morgen!")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 2
        assert fragments[0].text == "Ich fahre nach Berlin."
        assert fragments[1].text == "Bis morgen!"

    def test_stray_timing_from_bad_block_split_stripped(self, tmp_path):
        # A missing blank-line separator causes the next block's timestamp
        # to bleed into the previous block's body text.
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\n"
            "Das war ein langer Tag. 00:00:03,001\n"
            "\n"
            "2\n00:00:03,001 --> 00:00:05,000\n"
            "Endlich zu Hause.\n"
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        for f in fragments:
            assert re.search(r"\d{2}:\d{2}:\d{2}[,.]\d{3}", f.text) is None

    def test_nbsp_from_subtitle_editor_normalised(self, tmp_path):
        # Some subtitle editors insert non-breaking spaces instead of regular
        # spaces; these must be normalised before reaching the tokeniser.
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "{\\an8}Das\xa0ist\xa0wirklich\xa0gut.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "\xa0" not in fragments[0].text
        assert "Das ist wirklich gut." in fragments[0].text

    def test_multi_speaker_dialogue_with_ass_tags_cleaned(self, tmp_path):
        # Each turn has a leading dash (needed by SubtitleMerger's speaker
        # guard) and an ASS positioning tag.  Dashes survive; tags do not.
        srt = (
            _block(1, "00:00:01,000", "00:00:03,000",
                   "{\\an8}- Wohin gehst du?")
            + _block(2, "00:00:03,500", "00:00:05,500",
                     "{\\an8}- Ich gehe ins Kino.")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 2
        assert fragments[0].text.startswith("-")
        assert fragments[1].text.startswith("-")
        assert all("{" not in f.text for f in fragments)

    def test_html_entity_in_styled_fragment_decoded(self, tmp_path):
        # &amp; inside an ASS-positioned block must be decoded to &.
        # The ASS tag is stripped; the entity is decoded.
        srt = _block(1, "00:00:01,000", "00:00:03,000",
                     "{\\an8}Österreich &amp; Deutschland arbeiten zusammen.")
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 1
        assert "&amp;" not in fragments[0].text
        assert "& Deutschland" in fragments[0].text
        assert "{" not in fragments[0].text

    def test_realistic_news_ticker_snippet(self, tmp_path):
        # Ticker-style subtitles: multiple lines per block, ASS positioned,
        # HTML entity for ampersand.
        srt = (
            _block(1, "00:01:05,200", "00:01:09,000",
                   "{\\an8}Bundesregierung &amp; Opposition",
                   "einigen sich auf neuen Plan.")
            + _block(2, "00:01:10,000", "00:01:12,000", "♪")
            + _block(3, "00:01:13,500", "00:01:17,000",
                     "{\\an8}Details werden morgen bekanntgegeben.")
        )
        fragments = parse_srt(str(_write_srt(srt, tmp_path)))
        assert len(fragments) == 2  # ♪ dropped
        assert "Bundesregierung & Opposition" in fragments[0].text
        assert "einigen sich auf neuen Plan." in fragments[0].text
        assert "Details werden morgen bekanntgegeben." in fragments[1].text
