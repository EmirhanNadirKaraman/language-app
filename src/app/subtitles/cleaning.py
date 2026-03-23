from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional


_ASS_TAG_RE = re.compile(r"\{[^}]*\}")
_VTT_TIMESTAMP_TAG_RE = re.compile(r"<\d{1,2}:\d{2}:\d{2}\.\d{3}>")
_STRAY_TIMESTAMP_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}[,.]\d{3}\b")
_SRT_ARROW_RE = re.compile(r"\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")
_NBSP_RE = re.compile(r"\xa0")
_INVISIBLE_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")


@dataclass
class SubtitleCleanerConfig:
    """
    Feature toggles for SubtitleTextCleaner.

    Attributes:
        strip_ass_tags:           Remove ASS/SSA override blocks such as {\\an8}.
        strip_vtt_timestamp_tags: Remove WebVTT in-cue timestamp tags.
        decode_html_entities:     Decode HTML character references.
        normalize_whitespace:     Replace non-breaking spaces, remove invisible chars.
        strip_stray_timestamps:   Remove isolated SRT timestamp strings.
    """
    strip_ass_tags: bool = True
    strip_vtt_timestamp_tags: bool = True
    decode_html_entities: bool = True
    normalize_whitespace: bool = True
    strip_stray_timestamps: bool = True


class SubtitleTextCleaner:
    """
    Applies a configurable pipeline of text-level cleaning steps to raw
    subtitle content.

    Cleaning order:
      1. Strip ASS/SSA tags
      2. Strip VTT timestamp tags
      3. Decode HTML entities
      4. Normalize whitespace
      5. Strip stray timestamps
      6. Collapse whitespace (always applied)
    """

    def __init__(self, config: Optional[SubtitleCleanerConfig] = None) -> None:
        self.config = config or SubtitleCleanerConfig()

    def clean(self, text: str) -> str:
        """Apply all enabled cleaning steps and return the result."""
        t = text
        if self.config.strip_ass_tags:
            t = self._strip_ass_tags(t)
        if self.config.strip_vtt_timestamp_tags:
            t = self._strip_vtt_timestamp_tags(t)
        if self.config.decode_html_entities:
            t = self._decode_html_entities(t)
        if self.config.normalize_whitespace:
            t = self._normalize_whitespace(t)
        if self.config.strip_stray_timestamps:
            t = self._strip_stray_timestamps(t)
        return self._collapse_whitespace(t)

    @staticmethod
    def has_alphabetic_content(text: str) -> bool:
        """Return True if *text* contains at least one Unicode alphabetic character."""
        return any(c.isalpha() for c in text)

    @staticmethod
    def _strip_ass_tags(text: str) -> str:
        return _ASS_TAG_RE.sub("", text)

    @staticmethod
    def _strip_vtt_timestamp_tags(text: str) -> str:
        return _VTT_TIMESTAMP_TAG_RE.sub("", text)

    @staticmethod
    def _decode_html_entities(text: str) -> str:
        return html.unescape(text)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        t = _NBSP_RE.sub(" ", text)
        t = _INVISIBLE_RE.sub("", t)
        return t

    @staticmethod
    def _strip_stray_timestamps(text: str) -> str:
        t = _SRT_ARROW_RE.sub("", text)
        t = _STRAY_TIMESTAMP_RE.sub("", t)
        return t

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        return re.sub(r" {2,}", " ", text).strip()
