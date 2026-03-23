from __future__ import annotations

import warnings
from typing import Optional

from spacy.language import Language
from spacy.tokens import Doc, Token

from app.extraction.models import (
    TokenUnit,
    UtteranceExtractionResult,
    UnitExtractionConfig,
    _SKIP_POS,
    _has_garbage_symbols,
)
from app.learning.units import LearningUnit, LearningUnitType
from app.subtitles.models import CandidateUtterance


class UtteranceUnitExtractor:
    """
    Extracts learning units from CandidateUtterance objects using spaCy.

    For single utterances call extract().
    For large batches call extract_batch(), which uses nlp.pipe() internally
    for 2–4× throughput improvement over sequential nlp() calls.
    """

    def __init__(
        self,
        nlp: Language,
        config: Optional[UnitExtractionConfig] = None,
    ) -> None:
        self.nlp = nlp
        self.config = config or UnitExtractionConfig()
        self._validate_pipeline()

    def extract(self, utterance: CandidateUtterance) -> UtteranceExtractionResult:
        """Extract learning units from a single utterance."""
        doc = self.nlp(utterance.text)
        return self._process_doc(utterance, doc)

    def extract_batch(
        self,
        utterances: list[CandidateUtterance],
        batch_size: int = 64,
    ) -> list[UtteranceExtractionResult]:
        """Extract learning units from a list of utterances using nlp.pipe()."""
        non_empty = [(i, u) for i, u in enumerate(utterances) if u.text.strip()]
        if not non_empty:
            return []

        indices, valid = zip(*non_empty)
        texts = [u.text for u in valid]
        results: list[UtteranceExtractionResult] = []

        for utterance, doc in zip(valid, self.nlp.pipe(texts, batch_size=batch_size)):
            results.append(self._process_doc(utterance, doc))

        return results

    def _process_doc(
        self,
        utterance: CandidateUtterance,
        doc: Doc,
    ) -> UtteranceExtractionResult:
        """Walk the spaCy Doc and build TokenUnits, then deduplicate into units."""
        # Pass 1: index separable particles
        svp_token_indices: set[int] = set()
        particle_for_head: dict[int, Token] = {}

        if self.config.combine_separable_verbs:
            for token in doc:
                if token.dep_ == "svp":
                    svp_token_indices.add(token.i)
                    particle_for_head[token.head.i] = token

        # Pass 2: extract token units
        token_units: list[TokenUnit] = []
        skipped_count = 0

        for token in doc:
            if token.i in svp_token_indices:
                continue

            if self._should_skip(token):
                skipped_count += 1
                continue

            if token.pos_ == "":
                is_content, is_function = True, False
            else:
                is_content = token.pos_ in self.config.content_pos_tags
                is_function = token.pos_ in self.config.function_pos_tags

            if not is_content and not (is_function and self.config.include_function_words):
                skipped_count += 1
                continue

            if self._is_entity_noise(token):
                skipped_count += 1
                continue

            lemma_raw, is_compound = self._build_lemma(
                token, particle_for_head.get(token.i)
            )
            key = lemma_raw.lower()

            if len(key) < self.config.min_lemma_length or key in self.config.skip_lemmas:
                skipped_count += 1
                continue

            unit = LearningUnit(
                unit_type=LearningUnitType.LEMMA,
                key=key,
                display_form=lemma_raw,
            )

            token_units.append(TokenUnit(
                unit=unit,
                surface=token.text,
                lemma=lemma_raw,
                pos=token.pos_,
                dep=token.dep_,
                token_index=token.i,
                char_start=token.idx,
                char_end=token.idx + len(token.text),
                is_content_word=is_content,
                is_separable_compound=is_compound,
                ent_type=token.ent_type_,
            ))

        units = self._deduplicate(token_units) if self.config.deduplicate else [
            tu.unit for tu in token_units
        ]

        return UtteranceExtractionResult(
            utterance=utterance,
            token_units=token_units,
            units=units,
            skipped_count=skipped_count,
        )

    def _build_lemma(
        self,
        token: Token,
        particle: Optional[Token],
    ) -> tuple[str, bool]:
        base = token.lemma_ if token.lemma_.strip() else token.text

        if particle is not None:
            prefix = particle.text.lower()
            combined = prefix + base[0].lower() + base[1:]
            return combined, True

        return base, False

    @staticmethod
    def _should_skip(token: Token) -> bool:
        if token.is_punct or token.is_space:
            return True
        if token.is_digit or token.like_num:
            return True
        if token.pos_ in _SKIP_POS:
            return True
        if not any(c.isalpha() for c in token.text):
            return True
        if _has_garbage_symbols(token.text):
            return True
        return False

    def _is_entity_noise(self, token: Token) -> bool:
        if not self.config.skip_ent_types:
            return False
        return token.ent_type_ in self.config.skip_ent_types

    @staticmethod
    def _deduplicate(token_units: list[TokenUnit]) -> list[LearningUnit]:
        seen: set[tuple[LearningUnitType, str]] = set()
        result: list[LearningUnit] = []
        for tu in token_units:
            ident = (tu.unit.unit_type, tu.unit.key)
            if ident not in seen:
                seen.add(ident)
                result.append(tu.unit)
        return result

    def _validate_pipeline(self) -> None:
        pipe_names = set(self.nlp.pipe_names)

        if not (pipe_names & {"tagger", "morphologizer"}):
            warnings.warn(
                "No tagger or morphologizer found. token.lemma_ will fall back "
                "to the surface form — inflected forms won't normalise to their "
                "lemma.  Load de_core_news_md or larger for correct extraction.",
                UserWarning,
                stacklevel=3,
            )

        if self.config.combine_separable_verbs and "parser" not in pipe_names and "dep" not in pipe_names:
            warnings.warn(
                "combine_separable_verbs=True requires a dependency parser, "
                "but no 'parser' component was found.  Separable verbs will not "
                "be combined.  Set combine_separable_verbs=False to silence this.",
                UserWarning,
                stacklevel=3,
            )
