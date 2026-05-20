"""
Runtime-aligned port of parse_srt formatting-preservation tests
(W4 / #17 batch 1).

Targets `pipeline.parse_srt` — the production SRT parser used by every
scraper run. NOT the orphan refactor at `src/app/subtitles/ingestion`.

Ported nodeids (src/app suite):
  tests/subtitles/test_subtitle_ingestion.py::TestHtmlTagPassthrough::test_italic_tag_preserved_in_fragment_text
  tests/subtitles/test_subtitle_ingestion.py::TestHtmlTagPassthrough::test_bold_tag_preserved_in_fragment_text
  tests/subtitles/test_subtitle_ingestion.py::TestHtmlTagPassthrough::test_font_colour_tag_text_content_survives
  tests/subtitles/test_subtitle_ingestion.py::TestHtmlTagPassthrough::test_nested_italic_and_bold_both_preserved
"""
from pathlib import Path

from pipeline import parse_srt


def _write_srt(content: str, tmp_path: Path) -> Path:
    p = tmp_path / "test.srt"
    p.write_bytes(content.encode("utf-8"))
    return p


def _block(n: int, start: str, end: str, *lines: str) -> str:
    """Return a single well-formed SRT block followed by a blank separator."""
    body = "\n".join(lines)
    return f"{n}\n{start} --> {end}\n{body}\n\n"


class TestHtmlTagPassthrough:
    """parse_srt MUST preserve HTML inline tags inside fragment text — they
    drive downstream rendering and the cleaner shouldn't be eating them."""

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
