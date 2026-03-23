from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SubtitleFragment:
    """
    A single raw block from an SRT/VTT file. Immutable after parsing.

    Attributes:
        text:       Raw subtitle text, may include HTML tags or annotations.
        start_time: Block start time in seconds.
        end_time:   Block end time in seconds.
        index:      Original block index from the subtitle file (0-based).
    """
    text: str
    start_time: float
    end_time: float
    index: int = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def cleaned_text(self) -> str:
        """
        Return text with HTML tags, bracketed annotations, and leading
        dialogue dashes removed. Does not alter punctuation or letter case.
        """
        t = self.text
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"\[.*?\]|\(.*?\)", "", t)
        t = re.sub(r"^\s*[-–—]\s*", "", t)
        return t.strip()


@dataclass
class MergedSubtitleWindow:
    """
    A contiguous group of subtitle fragments merged into one utterance
    candidate, ready for spaCy sentence segmentation.

    Attributes:
        fragments:   The original fragments that form this window, in order.
        text:        Cleaned, joined text of all fragments.
        start_time:  Start time of the first fragment (seconds).
        end_time:    End time of the last fragment (seconds).
    """
    fragments: list[SubtitleFragment]
    text: str
    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def __repr__(self) -> str:
        preview = self.text if len(self.text) <= 60 else self.text[:57] + "..."
        return (
            f"MergedSubtitleWindow("
            f"n={len(self.fragments)}, "
            f"{self.start_time:.2f}s–{self.end_time:.2f}s, "
            f"{preview!r})"
        )


@dataclass
class CandidateUtterance:
    """
    A single candidate learnable unit produced by segmenting a MergedSubtitleWindow.

    Attributes:
        text:          Stripped sentence / utterance text.
        start_time:    Approximate start time in seconds.
        end_time:      Approximate end time in seconds.
        source_window: The MergedSubtitleWindow this sentence came from.
        char_start:    Character offset of this sentence within source_window.text.
        char_end:      End character offset within source_window.text (exclusive).
    """
    text: str
    start_time: float
    end_time: float
    source_window: MergedSubtitleWindow
    char_start: int
    char_end: int

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def char_length(self) -> int:
        return self.char_end - self.char_start

    def __repr__(self) -> str:
        preview = self.text if len(self.text) <= 60 else self.text[:57] + "..."
        return (
            f"CandidateUtterance("
            f"{self.start_time:.2f}s–{self.end_time:.2f}s, "
            f"{preview!r})"
        )
