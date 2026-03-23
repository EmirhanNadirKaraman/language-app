"""
utterance_unit_extractor.py
---------------------------
Maps CandidateUtterance objects to their extracted learning units.

This is the stage between segmentation and the i+1 filter.  It takes a
candidate utterance, parses it with spaCy, and returns two parallel views:

  token_units   — one TokenUnit per included token, with position metadata,
                  POS, dependency relation, and whether it was combined via
                  separable-verb merging.  Preserves duplicates.  Use this
                  for UI highlighting, debugging, and corpus analysis.

  units         — deduplicated LearningUnit list derived from token_units.
                  This is the set fed to UserKnowledgeProfile.find_sole_unknown()
                  for i+1 filtering.

Design choices worth calling out
---------------------------------
Function words (DET, PRON, ADP, CONJ):
    Off by default (include_function_words=False).  In German subtitle data,
    articles, prepositions and pronouns appear in almost every sentence.
    Including them as unknown units for a beginner user makes the i+1 filter
    fire almost never — the user needs to first mark dozens of "der/die/das"
    as known before any sentence becomes i+1.  The recommended approach is
    to keep them off in the extractor and handle them in onboarding via a
    seed "known" set at user creation time.
    Set include_function_words=True to include them (useful for A0 users or
    for corpus analysis).

AUX verbs (haben, sein, werden + modals):
    Included by default in content_pos_tags.  "Haben" and "sein" are major
    learning milestones in German; they should appear in the learnable set.

Separable verbs:
    When combine_separable_verbs=True (default), spaCy's svp dependency label
    is used to prepend the particle to the head verb lemma: "fängt ... an" →
    key="anfangen".  The particle token is then excluded from the unit list
    so it does not appear as a standalone unit.  This works reliably for
    present tense main clauses; it degrades in embedded clauses.  Failures
    produce a conservative fallback (the base verb lemma without the prefix).

Deduplication:
    Two occurrences of "gehen" in the same utterance count as one unknown unit
    for i+1 purposes.  token_units preserves both occurrences; units deduplicates.

Extending this stage:
    To add PHRASE units, create an additional extractor method (e.g.
    _extract_phrase_units) that uses spaCy noun chunks or a custom matcher
    and appends to token_units.  The deduplication and result assembly code
    is shared.
"""
from __future__ import annotations

import unicodedata
import warnings
from dataclasses import dataclass, field
from typing import Optional

from spacy.language import Language
from spacy.tokens import Doc, Token

from learning_units import LearningUnit, LearningUnitType
from subtitle_segmenter import CandidateUtterance


# ---------------------------------------------------------------------------
# Universal POS tag sets (spaCy tag scheme, consistent across German models)
# ---------------------------------------------------------------------------

_CONTENT_POS: frozenset[str] = frozenset({
    "NOUN",   # Buch, Haus, Straße
    # PROPN intentionally excluded: person names, city names, brands, and
    # organisation names are not learnable vocabulary items.  Any PROPN token
    # is silently dropped by the POS filter; NER-labelled NOUN tokens
    # (e.g. some city names tagged NOUN with ent_type=LOC) are caught by the
    # separate skip_ent_types filter below.
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
# So = Other Symbol (musical notes ♪♫, trademark ™, copyright ©, emoji etc.)
# Sm = Math Symbol (−, ×, ÷ used decoratively)
# Cf = Format character (zero-width joiners, soft hyphens from encoding errors)
# Co = Private-use area (garbled multi-byte sequences often land here)
_GARBAGE_UNICODE_CATEGORIES: frozenset[str] = frozenset({"So", "Sm", "Cf", "Co"})


def _has_garbage_symbols(text: str) -> bool:
    """
    Return True if any character in `text` belongs to a subtitle-garbage
    Unicode category.

    Catches hybrid tokens like "♪Danke♪" that survive the is-alphabetic check
    because they contain some real letters alongside the garbage characters.
    Pure garbage tokens (no alphabetic characters at all) are already rejected
    by the `not any(c.isalpha())` check in `_should_skip()` — this function
    handles the mixed case.
    """
    return any(unicodedata.category(c) in _GARBAGE_UNICODE_CATEGORIES for c in text)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TokenUnit:
    """
    A single token's contribution to the extracted learning unit set.

    Preserves full spaCy metadata so that downstream consumers (UI highlight
    engine, corpus analyser, debugger) can operate on token-level data without
    re-parsing.

    Attributes:
        unit:                 The normalised LearningUnit derived from this token.
        surface:              The exact token text as it appears in the utterance.
        lemma:                The lemma spaCy assigned, possibly modified by
                              separable-verb combination.
        pos:                  Universal POS tag (token.pos_).
        dep:                  Dependency relation label (token.dep_).
        token_index:          Token position index within the parsed Doc.
        char_start:           Character offset of the token within the utterance text.
        char_end:             End character offset (exclusive).
        is_content_word:      True for NOUN, PROPN, VERB, AUX, ADJ, ADV, INTJ.
        is_separable_compound:True when the token's lemma was combined with a
                              separable verb particle (e.g. "fange" + "an" →
                              "anfangen").
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
    """
    The extraction result for one CandidateUtterance.

    Attributes:
        utterance:     The source utterance.
        token_units:   All included tokens with metadata, in document order.
                       Contains duplicates if the same lemma appears more than once.
        units:         Deduplicated LearningUnit list for i+1 filtering.
                       Subset of the learning units in token_units.
        skipped_count: Number of tokens excluded by config (punct, filtered POS,
                       lemma too short, etc.).  Useful for sanity-checking config.
    """
    utterance: CandidateUtterance
    token_units: list[TokenUnit]
    units: list[LearningUnit]
    skipped_count: int

    @property
    def content_units(self) -> list[LearningUnit]:
        """
        Deduplicated units from content-word tokens only.

        When include_function_words=True, this lets you separate content
        and function contributions without re-running extraction.
        """
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
    """
    Controls what the UtteranceUnitExtractor includes and how it normalises.

    Attributes:
        content_pos_tags:
            Universal POS tags whose tokens are always included.
            Default: NOUN, PROPN, VERB, AUX, ADJ, ADV, INTJ.

        function_pos_tags:
            Universal POS tags whose tokens are included only when
            include_function_words=True.
            Default: DET, PRON, ADP, CCONJ, SCONJ, PART.

        include_function_words:
            When False (default), only content_pos_tags are extracted.
            When True, both content and function word tokens are included.
            See module docstring for the rationale.

        skip_lemmas:
            Specific lemmas to always exclude regardless of POS.
            Default: high-frequency German discourse particles that add noise
            without pedagogical value.

        skip_ent_types:
            Named-entity types (spaCy ent_type_) whose tokens are excluded
            regardless of POS tag.  Catches proper nouns that NER labels even
            when POS is NOUN (e.g. "Bayern" tagged NOUN + ent_type=LOC).
            Default: PER, LOC, ORG.  Set to frozenset() to disable NER
            filtering entirely.

        min_lemma_length:
            Drop tokens whose normalised lemma is shorter than this.
            Prevents single-letter abbreviation remnants from becoming units.

        combine_separable_verbs:
            When True, detects spaCy's "svp" dependency relation and prepends
            the particle to the head verb's lemma.  "fängt ... an" → "anfangen".

        deduplicate:
            When True (default), units are deduplicated across the utterance.
            Set False for corpus-frequency analysis where you want all occurrences.
    """
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
        # spaCy de_core_news_md NER labels for named entities that are not
        # useful vocabulary targets.
        "PER",  # Person names: Thomas, Maria, Müller, Dr. Schmidt
        "LOC",  # Locations: Berlin, Bayern, Rhein, Nordsee
        "ORG",  # Organisations: BMW, Bundesregierung, DFB
        # "MISC" intentionally excluded: it covers nationality adjectives
        # ("deutsch", "amerikanisch") and event names that are worth learning.
    }))

    min_lemma_length: int = 2
    combine_separable_verbs: bool = True
    deduplicate: bool = True


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class UtteranceUnitExtractor:
    """
    Extracts learning units from CandidateUtterance objects using spaCy.

    For single utterances call extract().
    For large batches call extract_batch(), which uses nlp.pipe() internally
    for 2–4× throughput improvement over sequential nlp() calls.

    The nlp pipeline should include at minimum a tagger (for POS tags) and a
    parser or dependency component (for separable verb detection).
    de_core_news_md and de_core_news_lg both satisfy this requirement.
    """

    def __init__(
        self,
        nlp: Language,
        config: Optional[UnitExtractionConfig] = None,
    ) -> None:
        self.nlp = nlp
        self.config = config or UnitExtractionConfig()
        self._validate_pipeline()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, utterance: CandidateUtterance) -> UtteranceExtractionResult:
        """
        Extract learning units from a single utterance.

        Parses the utterance text with the spaCy pipeline and delegates to
        _process_doc.  Prefer extract_batch() for many utterances.
        """
        doc = self.nlp(utterance.text)
        return self._process_doc(utterance, doc)

    def extract_batch(
        self,
        utterances: list[CandidateUtterance],
        batch_size: int = 64,
    ) -> list[UtteranceExtractionResult]:
        """
        Extract learning units from a list of utterances using nlp.pipe().

        Results are returned in the same order as the input.
        Empty utterances are skipped and produce no result entry.
        """
        non_empty = [(i, u) for i, u in enumerate(utterances) if u.text.strip()]
        if not non_empty:
            return []

        indices, valid = zip(*non_empty)
        texts = [u.text for u in valid]
        results: list[UtteranceExtractionResult] = []

        for utterance, doc in zip(valid, self.nlp.pipe(texts, batch_size=batch_size)):
            results.append(self._process_doc(utterance, doc))

        return results

    # ------------------------------------------------------------------
    # Core extraction logic
    # ------------------------------------------------------------------

    def _process_doc(
        self,
        utterance: CandidateUtterance,
        doc: Doc,
    ) -> UtteranceExtractionResult:
        """
        Walk the spaCy Doc and build TokenUnits, then deduplicate into units.

        Two-pass approach for separable verbs:
          Pass 1 — collect the index of every svp-dependent token and map
                   each to its head verb's index.
          Pass 2 — for each token, skip svp particles; when processing the
                   head verb, look up any associated particle and prepend it.
        """
        # --- Pass 1: index separable particles ---
        svp_token_indices: set[int] = set()
        particle_for_head: dict[int, Token] = {}

        if self.config.combine_separable_verbs:
            for token in doc:
                if token.dep_ == "svp":
                    svp_token_indices.add(token.i)
                    # A verb can have at most one svp child; last one wins if
                    # there are multiple (rare malformed parses)
                    particle_for_head[token.head.i] = token

        # --- Pass 2: extract token units ---
        token_units: list[TokenUnit] = []
        skipped_count = 0

        for token in doc:
            # Separable particles are folded into their head verb
            if token.i in svp_token_indices:
                continue

            # Orthographic / syntactic junk
            if self._should_skip(token):
                skipped_count += 1
                continue

            # POS-based inclusion check.
            # Blank-model fallback: when pos_ is empty (no tagger loaded),
            # treat every non-junk alphabetic token as a content word so the
            # pipeline produces some output and the structure is demonstrable.
            # Real lemmatisation still requires de_core_news_md or larger.
            if token.pos_ == "":
                is_content, is_function = True, False
            else:
                is_content = token.pos_ in self.config.content_pos_tags
                is_function = token.pos_ in self.config.function_pos_tags

            if not is_content and not (is_function and self.config.include_function_words):
                skipped_count += 1
                continue

            # Named-entity noise filter: runs after the POS gate so that
            # function words are already excluded and the NER check only needs
            # to handle content-word tokens.  Catches NOUN-tagged proper nouns
            # that survived the POS filter (e.g. "Bayern" tagged NOUN+LOC).
            if self._is_entity_noise(token):
                skipped_count += 1
                continue

            # Build the normalised lemma
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

        # --- Deduplication ---
        units = self._deduplicate(token_units) if self.config.deduplicate else [
            tu.unit for tu in token_units
        ]

        return UtteranceExtractionResult(
            utterance=utterance,
            token_units=token_units,
            units=units,
            skipped_count=skipped_count,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_lemma(
        self,
        token: Token,
        particle: Optional[Token],
    ) -> tuple[str, bool]:
        """
        Return (lemma_string, is_separable_compound).

        If a separable particle is provided, prepend it to the verb lemma.
        Falls back to token.text if token.lemma_ is empty (blank model).

        Separable combination:
            token.lemma_ = "fangen", particle.text = "an"
            → "anfangen"  (particle lowercased, verb lemma lowercased except
               leading character, which is already lowercase for verbs in German)
        """
        base = token.lemma_ if token.lemma_.strip() else token.text

        if particle is not None:
            prefix = particle.text.lower()
            # Lowercase the first char of base so "Fangen" → "fangen" before join
            combined = prefix + base[0].lower() + base[1:]
            return combined, True

        return base, False

    @staticmethod
    def _should_skip(token: Token) -> bool:
        """
        Return True for tokens that carry no learnable lexical content,
        regardless of config settings.

        Covers:
          - Punctuation, whitespace, numeric tokens.
          - POS tags in _SKIP_POS (PUNCT, SPACE, NUM, SYM, X).
          - Tokens with zero alphabetic characters (pure symbols: ♪, ---, ...).
          - Tokens containing subtitle-garbage Unicode characters even when
            some alphabetic characters are present (e.g. "♪Danke♪").
        """
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
        """
        Return True if this token should be excluded because it is a named
        entity of a type that produces no learnable vocabulary.

        This is a second filter layer, applied *after* the POS check:

          PROPN tokens  — already excluded by the POS gate (PROPN is not in
                          the default content_pos_tags).  No work needed here.
          NOUN tokens   — can be proper nouns that de_core_news_md POS-tags as
                          NOUN but NER-labels as PER/LOC/ORG.  For example,
                          "Bayern" often receives POS=NOUN + ent_type=LOC.
                          This filter catches those.

        Set config.skip_ent_types=frozenset() to disable NER filtering.
        """
        if not self.config.skip_ent_types:
            return False
        return token.ent_type_ in self.config.skip_ent_types

    @staticmethod
    def _deduplicate(token_units: list[TokenUnit]) -> list[LearningUnit]:
        """
        Build an ordered deduplicated list of LearningUnits from token_units.

        First occurrence of each (unit_type, key) pair wins; later duplicates
        are silently dropped.  Order follows document token order.
        """
        seen: set[tuple[LearningUnitType, str]] = set()
        result: list[LearningUnit] = []
        for tu in token_units:
            ident = (tu.unit.unit_type, tu.unit.key)
            if ident not in seen:
                seen.add(ident)
                result.append(tu.unit)
        return result

    def _validate_pipeline(self) -> None:
        """Warn if the pipeline is missing components needed for reliable extraction."""
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


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _make_utterance(text: str) -> CandidateUtterance:
    """Minimal CandidateUtterance for demo purposes."""
    from subtitle_merger import MergedSubtitleWindow, SubtitleFragment
    window = MergedSubtitleWindow(
        fragments=[SubtitleFragment(text=text, start_time=0.0, end_time=3.0)],
        text=text,
        start_time=0.0,
        end_time=3.0,
    )
    return CandidateUtterance(
        text=text, start_time=0.0, end_time=3.0,
        source_window=window, char_start=0, char_end=len(text),
    )


def _demo() -> None:
    try:
        import spacy
        nlp = spacy.load("de_core_news_md")
        print("  Using de_core_news_md — lemmatisation and dependency parsing active.\n")
    except OSError:
        import spacy
        nlp = spacy.blank("de")
        warnings.warn(
            "de_core_news_md not found. "
            "Install with: python -m spacy download de_core_news_md",
            stacklevel=1,
        )
        print("  Using blank model — surface forms only, no lemmatisation.\n")

    extractor = UtteranceUnitExtractor(nlp)

    # ------------------------------------------------------------------
    # 1. Basic extraction
    # ------------------------------------------------------------------
    print("─" * 62)
    print("  1. BASIC EXTRACTION")
    print("─" * 62)

    basic_cases = [
        "Das Buch liegt auf dem Tisch.",
        "Wir haben das interessante Konzert besucht.",
        "Er freut sich sehr über das Geschenk.",
    ]
    for text in basic_cases:
        result = extractor.extract(_make_utterance(text))
        keys = [u.key for u in result.units]
        print(f"\n  {text}")
        print(f"  → units : {keys}")
        print(f"    skipped: {result.skipped_count} tokens")

    # ------------------------------------------------------------------
    # 2. Separable verb detection
    # ------------------------------------------------------------------
    print("\n" + "─" * 62)
    print("  2. SEPARABLE VERB DETECTION")
    print("─" * 62)

    sep_cases = [
        ("Ich fange morgen mit dem Training an.", "anfangen expected"),
        ("Sie macht die Tür auf.",                "aufmachen expected"),
        ("Er ruft seine Mutter an.",              "anrufen expected"),
    ]
    for text, note in sep_cases:
        result = extractor.extract(_make_utterance(text))
        compounds = [tu for tu in result.token_units if tu.is_separable_compound]
        keys = [u.key for u in result.units]
        print(f"\n  {text}  [{note}]")
        print(f"  → units     : {keys}")
        if compounds:
            print(f"    compounds : {[(tu.surface, '→', tu.lemma) for tu in compounds]}")

    # ------------------------------------------------------------------
    # 3. Function word toggle
    # ------------------------------------------------------------------
    print("\n" + "─" * 62)
    print("  3. FUNCTION WORD TOGGLE")
    print("─" * 62)

    sentence = "Er liest das Buch mit großem Interesse."
    utt = _make_utterance(sentence)

    result_content = extractor.extract(utt)
    result_all = UtteranceUnitExtractor(
        nlp, UnitExtractionConfig(include_function_words=True)
    ).extract(utt)

    print(f"\n  {sentence}")
    print(f"  include_function_words=False : {[u.key for u in result_content.units]}")
    print(f"  include_function_words=True  : {[u.key for u in result_all.units]}")

    # ------------------------------------------------------------------
    # 4. Repeated lemma deduplication
    # ------------------------------------------------------------------
    print("\n" + "─" * 62)
    print("  4. DEDUPLICATION")
    print("─" * 62)

    text = "Sie geht ins Büro, weil sie arbeiten muss."
    result = extractor.extract(_make_utterance(text))
    print(f"\n  {text}")
    print(f"  token_units ({len(result.token_units)}): "
          f"{[(tu.surface, tu.lemma) for tu in result.token_units]}")
    print(f"  units       ({len(result.units)}): {[u.key for u in result.units]}")

    # ------------------------------------------------------------------
    # 5. Batch mode
    # ------------------------------------------------------------------
    print("\n" + "─" * 62)
    print("  5. BATCH MODE  (extract_batch)")
    print("─" * 62)

    utterances = [_make_utterance(t) for t in [
        "Das Wetter ist heute schön.",
        "Ich kaufe morgen ein neues Fahrrad.",
        "Sie kann leider nicht kommen.",
    ]]
    batch_results = extractor.extract_batch(utterances)
    for r in batch_results:
        print(f"\n  {r.utterance.text}")
        print(f"  → {[u.key for u in r.units]}")

    # ------------------------------------------------------------------
    # 6. Token-level metadata
    # ------------------------------------------------------------------
    print("\n" + "─" * 62)
    print("  6. TOKEN-LEVEL METADATA")
    print("─" * 62)

    text = "Das alte Haus gehört meiner Großmutter."
    result = extractor.extract(_make_utterance(text))
    print(f"\n  {text}")
    print(f"  {'surface':<14} {'lemma':<14} {'pos':<8} {'dep':<10} {'ent':<6} content")
    print(f"  {'─'*14} {'─'*14} {'─'*8} {'─'*10} {'─'*6} {'─'*7}")
    for tu in result.token_units:
        cw = "yes" if tu.is_content_word else "no"
        print(f"  {tu.surface:<14} {tu.lemma:<14} {tu.pos:<8} {tu.dep:<10} {tu.ent_type:<6} {cw}")

    # ------------------------------------------------------------------
    # 7. Proper noun / named-entity filtering
    # ------------------------------------------------------------------
    print("\n" + "─" * 62)
    print("  7. PROPER NOUN + NAMED-ENTITY FILTERING")
    print("─" * 62)

    noise_cases = [
        ("Thomas fährt nach Berlin.", ["fahren"],
         "PER + LOC filtered; verb kept"),
        ("Ich arbeite bei der BMW AG.", ["arbeiten"],
         "ORG filtered; verb kept"),
        ("♪ Danke schön ♪", ["schön"],
         "music-note garbage filtered; adjective kept"),
        ("Der deutsche Film ist interessant.", ["deutsch", "film", "interessant"],
         "MISC nationality adj kept; common noun kept"),
    ]

    for text, expected_keys, note in noise_cases:
        result = extractor.extract(_make_utterance(text))
        got = [u.key for u in result.units]
        ok = all(k in got for k in expected_keys)
        status = "OK" if ok else "MISMATCH"
        print(f"\n  [{status}] {text}")
        print(f"         note    : {note}")
        print(f"         units   : {got}")
        print(f"         expected: {expected_keys} (subset)")


if __name__ == "__main__":
    _demo()
