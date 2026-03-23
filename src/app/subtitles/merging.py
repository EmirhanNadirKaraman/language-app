from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.subtitles.models import MergedSubtitleWindow, SubtitleFragment


_CONTINUATION_WORDS: frozenset[str] = frozenset({
    "und", "oder", "aber", "denn", "sondern",
    "weil", "dass", "wenn", "ob", "als", "während", "obwohl",
    "damit", "sodass", "nachdem", "bevor", "bis", "seit", "falls",
    "sofern", "solange", "sobald", "indem", "seitdem",
    "in", "an", "auf", "über", "unter", "vor", "hinter", "neben",
    "zwischen", "mit", "nach", "bei", "von", "zu", "aus", "durch",
    "für", "gegen", "ohne", "um", "wegen", "trotz",
    "der", "die", "das", "dem", "den", "des",
    "ein", "eine", "einen", "einem", "einer", "eines",
    "haben", "sein", "werden", "können", "müssen", "dürfen",
    "sollen", "wollen", "mögen",
    "dessen", "deren", "was", "wer", "wie", "wo", "wohin",
})

_STRONG_PUNCT: frozenset[str] = frozenset({".", "!", "?", "…"})
_WEAK_PUNCT: frozenset[str] = frozenset({",", ";"})
_DIALOGUE_DASH_RE = re.compile(r"^\s*[-–—]\s*\S", re.UNICODE)


@dataclass
class SubtitleMergeConfig:
    """
    Thresholds and feature toggles for SubtitleMerger.

    Attributes:
        max_gap_s:              Fragments further apart than this are never merged.
        tiny_gap_s:             Gap below this is treated as "essentially no pause".
        max_window_duration_s:  Hard ceiling on a merged window's total span.
        min_standalone_words:   Fragment shorter than this is merged if timing allows.
        merge_on_*:             Toggle individual soft-signal heuristics.
        guard_dialogue_dash:    Veto merge when next fragment starts with dialogue dash.
        guard_short_complete_turn: Also veto tiny-gap merges for short complete turns.
        max_complete_turn_words: Word-count ceiling for guard_short_complete_turn.
    """
    max_gap_s: float = 0.6
    tiny_gap_s: float = 0.15
    max_window_duration_s: float = 8.0
    min_standalone_words: int = 3
    merge_on_lowercase_continuation: bool = True
    merge_on_weak_punctuation: bool = True
    merge_on_continuation_word: bool = True
    merge_on_short_fragment: bool = True
    merge_on_hyphen_break: bool = True
    guard_dialogue_dash: bool = True
    guard_short_complete_turn: bool = True
    max_complete_turn_words: int = 6


class SubtitleMerger:
    """
    Merges consecutive SubtitleFragment objects into MergedSubtitleWindow
    objects using timing and German-specific linguistic heuristics.
    """

    def __init__(self, config: Optional[SubtitleMergeConfig] = None) -> None:
        self.config = config or SubtitleMergeConfig()

    def merge_fragments(
        self,
        fragments: list[SubtitleFragment],
    ) -> list[MergedSubtitleWindow]:
        """Merge a list of subtitle fragments into utterance windows."""
        if not fragments:
            return []

        windows: list[MergedSubtitleWindow] = []
        current_group: list[SubtitleFragment] = [fragments[0]]

        for nxt in fragments[1:]:
            cur = current_group[-1]
            projected_duration = nxt.end_time - current_group[0].start_time

            if (
                projected_duration <= self.config.max_window_duration_s
                and self._should_merge(cur, nxt)
            ):
                current_group.append(nxt)
            else:
                windows.append(self._build_window(current_group))
                current_group = [nxt]

        windows.append(self._build_window(current_group))
        return windows

    def _should_merge(
        self,
        current: SubtitleFragment,
        nxt: SubtitleFragment,
    ) -> bool:
        gap = nxt.start_time - current.end_time

        if gap > self.config.max_gap_s:
            return False

        if (
            self.config.guard_dialogue_dash
            and self._next_starts_with_dialogue_dash(nxt)
        ):
            return False

        if (
            self._ends_with_strong_punctuation(current)
            and self._starts_with_uppercase(nxt)
        ):
            if gap > self.config.tiny_gap_s:
                return False
            if (
                self.config.guard_short_complete_turn
                and current.word_count <= self.config.max_complete_turn_words
            ):
                return False

        if gap <= self.config.tiny_gap_s:
            return True

        signals: list[bool] = [
            self.config.merge_on_weak_punctuation
                and self._ends_with_weak_punctuation(current),
            self.config.merge_on_continuation_word
                and self._ends_with_continuation_word(current),
            self.config.merge_on_lowercase_continuation
                and self._starts_with_lowercase(nxt),
            self.config.merge_on_short_fragment
                and self._is_too_short(current),
            self.config.merge_on_hyphen_break
                and self._ends_with_hyphen(current),
        ]
        return any(signals)

    def _ends_with_strong_punctuation(self, frag: SubtitleFragment) -> bool:
        cleaned = frag.cleaned_text().rstrip()
        return bool(cleaned) and cleaned[-1] in _STRONG_PUNCT

    def _ends_with_weak_punctuation(self, frag: SubtitleFragment) -> bool:
        cleaned = frag.cleaned_text().rstrip()
        return bool(cleaned) and cleaned[-1] in _WEAK_PUNCT

    def _ends_with_continuation_word(self, frag: SubtitleFragment) -> bool:
        cleaned = frag.cleaned_text()
        tokens = cleaned.lower().split()
        if not tokens:
            return False
        last_token = re.sub(r"[^\w]", "", tokens[-1], flags=re.UNICODE)
        return last_token in _CONTINUATION_WORDS

    def _starts_with_lowercase(self, frag: SubtitleFragment) -> bool:
        cleaned = frag.cleaned_text().lstrip()
        return bool(cleaned) and cleaned[0].islower()

    def _starts_with_uppercase(self, frag: SubtitleFragment) -> bool:
        cleaned = frag.cleaned_text().lstrip()
        return bool(cleaned) and cleaned[0].isupper()

    def _is_too_short(self, frag: SubtitleFragment) -> bool:
        return frag.word_count < self.config.min_standalone_words

    def _ends_with_hyphen(self, frag: SubtitleFragment) -> bool:
        return frag.cleaned_text().rstrip().endswith("-")

    def _next_starts_with_dialogue_dash(self, nxt: SubtitleFragment) -> bool:
        raw = re.sub(r"<[^>]+>", "", nxt.text)
        return bool(_DIALOGUE_DASH_RE.match(raw))

    def _build_window(self, group: list[SubtitleFragment]) -> MergedSubtitleWindow:
        cleaned_texts = [f.cleaned_text() for f in group]
        merged_text = self._join_texts(cleaned_texts)
        return MergedSubtitleWindow(
            fragments=list(group),
            text=merged_text,
            start_time=group[0].start_time,
            end_time=group[-1].end_time,
        )

    @staticmethod
    def _join_texts(texts: list[str]) -> str:
        if not texts:
            return ""
        result = texts[0]
        for text in texts[1:]:
            if result.endswith("-"):
                result = result[:-1] + text
            else:
                result = result + " " + text
        return result.strip()
