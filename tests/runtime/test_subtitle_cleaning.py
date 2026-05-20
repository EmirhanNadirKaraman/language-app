"""
Runtime-aligned port of behavioural cleaner tests (W4 / #17 batch 1).

Targets the RUNTIME module `subtitle_cleaner.SubtitleTextCleaner` —
NOT the orphan refactor at `src/app/subtitles/cleaning.py`. The orphan
copy keeps its own coverage; this file validates the code that actually
ships in `pipeline.py:parse_srt`.

Ported nodeids (src/app suite):
  tests/subtitles/test_subtitle_cleaner.py::TestStripPositioning::test_positioning_tag_removed
  tests/subtitles/test_subtitle_cleaner.py::TestStripPositioning::test_bold_tag_removed
  tests/subtitles/test_subtitle_cleaner.py::TestStripPositioning::test_italic_tag_removed
  tests/subtitles/test_subtitle_cleaner.py::TestStripPositioning::test_position_with_coordinates_removed
  tests/subtitles/test_noise_filtering.py::test_standalone_musical_note
  tests/subtitles/test_noise_filtering.py::test_zero_width_format_character
"""
import pytest

from subtitle_cleaner import SubtitleTextCleaner
from utterance_unit_extractor import _has_garbage_symbols


@pytest.fixture
def cleaner() -> SubtitleTextCleaner:
    return SubtitleTextCleaner()


# ---------------------------------------------------------------------------
# ASS/SSA tag stripping — these are the most common positioning artifacts in
# real YouTube subtitle files and the cleaner MUST drop them before parsing.
# ---------------------------------------------------------------------------

class TestStripPositioning:

    def test_positioning_tag_removed(self, cleaner):
        assert cleaner.clean("{\\an8}Das ist gut.") == "Das ist gut."

    def test_bold_tag_removed(self, cleaner):
        assert cleaner.clean("{\\b1}Achtung!{\\b0}") == "Achtung!"

    def test_italic_tag_removed(self, cleaner):
        assert cleaner.clean("{\\i1}Wirklich?{\\i0}") == "Wirklich?"

    def test_position_with_coordinates_removed(self, cleaner):
        assert cleaner.clean("{\\pos(100,200)}Hallo.") == "Hallo."


# ---------------------------------------------------------------------------
# Noise filtering — the garbage-symbol predicate that downstream code uses
# to drop tokens that aren't really learnable units. Lives in
# `utterance_unit_extractor` at runtime (was in `app.extraction.models`).
# ---------------------------------------------------------------------------

class TestGarbageSymbolHelper:

    def test_standalone_musical_note(self):
        assert _has_garbage_symbols("♪") is True

    def test_zero_width_format_character(self):
        assert _has_garbage_symbols("text​") is True
