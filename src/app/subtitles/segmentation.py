from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Literal, Optional

from spacy.language import Language
from spacy.tokens import Doc

from app.subtitles.models import CandidateUtterance, MergedSubtitleWindow


_SENT_COMPONENTS: frozenset[str] = frozenset({"sentencizer", "senter", "parser"})


@dataclass
class SegmentationConfig:
    """
    Configuration for SubtitleSegmenter.

    Attributes:
        component:  Which spaCy sentence segmentation component is expected.
        min_chars:  Drop candidates whose stripped text is shorter than this.
    """
    component: Literal["sentencizer", "senter"] = "senter"
    min_chars: int = 3


class SubtitleSegmenter:
    """
    Splits each MergedSubtitleWindow into CandidateUtterance objects using
    spaCy's sentence segmentation.
    """

    def __init__(
        self,
        nlp: Language,
        config: Optional[SegmentationConfig] = None,
    ) -> None:
        self.nlp = nlp
        self.config = config or SegmentationConfig()
        self._validate_pipeline()

    def segment_window(self, window: MergedSubtitleWindow) -> list[CandidateUtterance]:
        """Segment a single MergedSubtitleWindow into CandidateUtterance objects."""
        text = window.text.strip()
        if not text:
            return []
        doc = self.nlp(text)
        return self._extract_candidates(window, doc)

    def segment_windows(
        self,
        windows: list[MergedSubtitleWindow],
        batch_size: int = 64,
    ) -> list[CandidateUtterance]:
        """Segment a list of MergedSubtitleWindows using nlp.pipe()."""
        if not windows:
            return []

        texts = [w.text.strip() for w in windows]
        result: list[CandidateUtterance] = []

        for window, doc in zip(windows, self.nlp.pipe(texts, batch_size=batch_size)):
            if not window.text.strip():
                continue
            result.extend(self._extract_candidates(window, doc))

        return result

    def _extract_candidates(
        self,
        window: MergedSubtitleWindow,
        doc: Doc,
    ) -> list[CandidateUtterance]:
        total_chars = len(window.text.strip())
        candidates: list[CandidateUtterance] = []

        for sent in doc.sents:
            sent_text = sent.text.strip()
            if len(sent_text) < self.config.min_chars:
                continue

            start_time, end_time = self._interpolate_times(
                window, sent.start_char, sent.end_char, total_chars
            )
            candidates.append(
                CandidateUtterance(
                    text=sent_text,
                    start_time=start_time,
                    end_time=end_time,
                    source_window=window,
                    char_start=sent.start_char,
                    char_end=sent.end_char,
                )
            )

        return candidates

    @staticmethod
    def _interpolate_times(
        window: MergedSubtitleWindow,
        char_start: int,
        char_end: int,
        total_chars: int,
    ) -> tuple[float, float]:
        if total_chars == 0:
            return window.start_time, window.end_time

        duration = window.end_time - window.start_time
        start_time = window.start_time + (char_start / total_chars) * duration
        end_time = window.start_time + (char_end / total_chars) * duration
        return start_time, end_time

    def _validate_pipeline(self) -> None:
        active = set(self.nlp.pipe_names)
        if not active & _SENT_COMPONENTS:
            warnings.warn(
                f"No sentence segmentation component found in spaCy pipeline. "
                f"Expected one of {sorted(_SENT_COMPONENTS)}, "
                f"got: {sorted(active)}. "
                f"doc.sents will be empty at runtime.",
                UserWarning,
                stacklevel=3,
            )
