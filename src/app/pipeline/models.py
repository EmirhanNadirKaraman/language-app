from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from app.exposure.models import CountingPolicy
from app.extraction.models import UnitExtractionConfig, UtteranceExtractionResult
from app.learning.knowledge import ExposurePolicy, KnowledgeFilterPolicy
from app.learning.units import LearningUnit
from app.subtitles.merging import SubtitleMergeConfig
from app.subtitles.models import CandidateUtterance
from app.subtitles.quality import QualityFilterConfig
from app.subtitles.segmentation import SegmentationConfig


@dataclass
class I1Match:
    """
    A single i+1 match: an utterance the user can learn from right now.

    Attributes:
        utterance:   The i+1 candidate utterance.
        target_unit: The one unit in this utterance the user does not yet know.
        extraction:  Full extraction result for UI highlighting and debugging.
    """
    utterance: CandidateUtterance
    target_unit: LearningUnit
    extraction: UtteranceExtractionResult

    @property
    def utterance_id(self) -> str:
        """Stable identifier derived from utterance text and timing."""
        raw = f"{self.utterance.text}|{self.utterance.start_time:.3f}|{self.utterance.end_time:.3f}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def __repr__(self) -> str:
        return (
            f"I1Match("
            f"[{self.utterance.start_time:.2f}s–{self.utterance.end_time:.2f}s] "
            f"{self.utterance.text!r} → {self.target_unit.key!r})"
        )


@dataclass
class PipelineConfig:
    """
    Aggregate configuration for all pipeline stages.

    All fields have sensible defaults — only override what you need.
    """
    merge: SubtitleMergeConfig = field(default_factory=SubtitleMergeConfig)
    segment: SegmentationConfig = field(default_factory=SegmentationConfig)
    quality: QualityFilterConfig = field(default_factory=QualityFilterConfig)
    extract: UnitExtractionConfig = field(default_factory=UnitExtractionConfig)
    filter_policy: KnowledgeFilterPolicy = field(default_factory=KnowledgeFilterPolicy)
    exposure_policy: ExposurePolicy = field(default_factory=ExposurePolicy)
    counting: CountingPolicy = field(default_factory=CountingPolicy)
    nlp_batch_size: int = 64
