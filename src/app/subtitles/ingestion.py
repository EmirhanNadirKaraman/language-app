from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.subtitles.cleaning import SubtitleTextCleaner
from app.subtitles.models import SubtitleFragment


_SRT_TIMESTAMP = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
    r"\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)

# Encoding preference order for subtitle files.
_SUBTITLE_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def _parse_timestamp(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _read_subtitle_file(path: Path) -> str:
    """
    Read a subtitle file, trying common encodings in order.

    Encoding priority: utf-8-sig → utf-8 → cp1252 → latin-1.
    latin-1 never raises UnicodeDecodeError, so the chain always produces a result.
    """
    for encoding in _SUBTITLE_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="latin-1", errors="replace")


def parse_srt(
    path: str | Path,
    cleaner: Optional[SubtitleTextCleaner] = None,
) -> list[SubtitleFragment]:
    """
    Parse an SRT file into a list of SubtitleFragment objects.

    Handles:
      - Standard SRT timestamps: 00:00:01,234 --> 00:00:03,456
      - WebVTT-style dots:        00:00:01.234 --> 00:00:03.456
      - Windows (CRLF) and Unix (LF) line endings
      - Multi-line subtitle blocks (lines joined with a space)
      - Encoding fallback: utf-8-sig → utf-8 → cp1252 → latin-1
      - ASS/SSA styling tags, VTT timestamp cues, HTML entities,
        non-standard whitespace, stray SRT timestamps in body text
      - Fragments that reduce to no alphabetic content after cleaning are dropped

    Returns fragments in file order (index = 0-based over kept blocks).

    Raises:
        FileNotFoundError: if *path* does not exist.
        ValueError:        if no valid SRT blocks are found after cleaning.
    """
    raw_text = _read_subtitle_file(Path(path))
    blocks = re.split(r"\r?\n\r?\n", raw_text.strip())

    if cleaner is None:
        cleaner = SubtitleTextCleaner()

    fragments: list[SubtitleFragment] = []

    for raw_block in blocks:
        lines = [ln.rstrip() for ln in raw_block.splitlines()]
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines:
            continue

        m = _SRT_TIMESTAMP.match(lines[0].strip())
        if not m:
            continue

        start = _parse_timestamp(*m.group(1, 2, 3, 4))
        end = _parse_timestamp(*m.group(5, 6, 7, 8))

        raw_content = " ".join(ln for ln in lines[1:] if ln.strip())
        if not raw_content:
            continue

        content = cleaner.clean(raw_content)

        if not SubtitleTextCleaner.has_alphabetic_content(content):
            continue

        fragments.append(SubtitleFragment(
            text=content,
            start_time=start,
            end_time=end,
            index=len(fragments),
        ))

    if not fragments:
        raise ValueError(f"No valid SRT blocks found in {path!r}")

    return fragments
