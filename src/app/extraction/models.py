from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from app.learning.units import LearningUnit, LearningUnitType
from app.subtitles.models import CandidateUtterance


# ---------------------------------------------------------------------------
# Universal POS tag sets (spaCy tag scheme, consistent across German models)
# ---------------------------------------------------------------------------

_CONTENT_POS: frozenset[str] = frozenset({
    "NOUN",   # Buch, Haus, Straße
    # PROPN intentionally excluded: person names, city names, brands, and
    # organisation names are not learnable vocabulary items.
    "VERB",   # gehen, kaufen, schlafen
    "AUX",    # haben, sein, werden, können, müssen …
    "ADJ",    # schön, groß, interessant
    "ADV",    # schnell, sehr, leider
    "INTJ",   # oh, ach, hm
})

_FUNCTION_POS: frozenset[str] = frozenset({
    "DET",    # der, die, das, ein, eine
    "PRON",   # ich, du, er, sie, wir, mich, sich
    "ADP",    # in, auf, mit, von, durch
    "CCONJ",  # und, oder, aber
    "SCONJ",  # weil, dass, wenn, ob
    "PART",   # zu (infinitive), nicht
})

# These POS tags are never learnable units
_SKIP_POS: frozenset[str] = frozenset({
    "PUNCT", "SPACE", "NUM", "SYM", "X",
})

# Unicode general categories that flag subtitle garbage embedded within otherwise
# alphabetic tokens — e.g. "♪text" or "word™".
_GARBAGE_UNICODE_CATEGORIES: frozenset[str] = frozenset({"So", "Sm", "Cf", "Co"})


def _has_garbage_symbols(text: str) -> bool:
    """
    Return True if any character in `text` belongs to a subtitle-garbage
    Unicode category.
    """
    return any(unicodedata.category(c) in _GARBAGE_UNICODE_CATEGORIES for c in text)


@dataclass
class TokenUnit:
    """
    A single token's contribution to the extracted learning unit set.

    Preserves full spaCy metadata so that downstream consumers (UI highlight
    engine, corpus analyser, debugger) can operate on token-level data without
    re-parsing.
    """
    unit: LearningUnit
    surface: str
    lemma: str
    pos: str
    dep: str
    token_index: int
    char_start: int
    char_end: int
    is_content_word: bool
    is_separable_compound: bool = False
    ent_type: str = ""

    def __repr__(self) -> str:
        flag = "*" if self.is_separable_compound else ""
        ent = f"[{self.ent_type}]" if self.ent_type else ""
        return f"TokenUnit({self.pos}:{self.surface!r}→{self.lemma!r}{flag}{ent})"


@dataclass
class UtteranceExtractionResult:
    """The extraction result for one CandidateUtterance."""
    utterance: CandidateUtterance
    token_units: list[TokenUnit]
    units: list[LearningUnit]
    skipped_count: int

    @property
    def content_units(self) -> list[LearningUnit]:
        """Deduplicated units from content-word tokens only."""
        seen: set[tuple[LearningUnitType, str]] = set()
        result: list[LearningUnit] = []
        for tu in self.token_units:
            if tu.is_content_word:
                ident = (tu.unit.unit_type, tu.unit.key)
                if ident not in seen:
                    seen.add(ident)
                    result.append(tu.unit)
        return result

    def surface_for_unit(self, unit: LearningUnit) -> list[str]:
        """Return all surface forms in this utterance that map to `unit`."""
        return [tu.surface for tu in self.token_units if tu.unit == unit]

    def __repr__(self) -> str:
        keys = [u.key for u in self.units]
        return (
            f"UtteranceExtractionResult("
            f"units={keys}, "
            f"skipped={self.skipped_count})"
        )


@dataclass
class UnitExtractionConfig:
    """Controls what the UtteranceUnitExtractor includes and how it normalises."""
    content_pos_tags: frozenset[str] = field(
        default_factory=lambda: frozenset(_CONTENT_POS)
    )
    function_pos_tags: frozenset[str] = field(
        default_factory=lambda: frozenset(_FUNCTION_POS)
    )
    include_function_words: bool = False

    skip_lemmas: frozenset[str] = field(default_factory=lambda: frozenset({
        # Discourse particles — semantically empty in most contexts
        "ja", "nein", "halt", "mal", "doch", "schon", "also",
        "eben", "eigentlich", "irgendwie", "quasi",
    }))

    skip_ent_types: frozenset[str] = field(default_factory=lambda: frozenset({
        "PER",  # Person names
        "LOC",  # Locations
        "ORG",  # Organisations
    }))

    min_lemma_length: int = 2
    combine_separable_verbs: bool = True
    deduplicate: bool = True
