"""
subtitle_cleaner.py
-------------------
Text-level cleaning for raw subtitle content before downstream NLP processing.

Handles artifacts that real-world SRT and WebVTT files commonly carry that are
not addressed by SubtitleFragment.cleaned_text():

    ASS/SSA override tags   {\\an8} {\\b1} {\\pos(100,200)} {\\move(...)}
    WebVTT timestamp cues   <00:00:01.234> embedded inside cue text
    HTML entities           &amp; → & , &lt; → < , &nbsp; → space
    Non-standard whitespace \\xa0 \\u200b mid-file BOM (\\ufeff) etc.
    Stray SRT timestamps    00:01:23,456 surviving malformed block splits
    SRT arrow remnants      --> 00:01:23,456 in body text

Intentionally NOT handled here (already handled downstream):

    HTML italic/bold tags   <i> <b> <font ...>   — SubtitleFragment.cleaned_text()
    Bracket annotations     [Musik] (lacht)       — SubtitleFragment.cleaned_text()
    Leading dialogue dashes - Hallo               — needed raw for speaker detection
    Music note symbols      ♪ ♫                   — UtteranceQualityEvaluator

Usage::

    from subtitle_cleaner import SubtitleTextCleaner

    cleaner = SubtitleTextCleaner()
    cleaned = cleaner.clean(raw_line)

    if not SubtitleTextCleaner.has_alphabetic_content(cleaned):
        skip_fragment()  # nothing left after artifact removal
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Compiled patterns — module-level for performance
# ---------------------------------------------------------------------------

# ASS/SSA override blocks: {\\an8} {\\b1} {\\pos(100,200)} {\\move(...)}
# Curly braces never appear in normal subtitle text, so this is safe.
_ASS_TAG_RE = re.compile(r"\{[^}]*\}")

# WebVTT timestamp cue tags embedded in cue text: <00:00:01.234>
# These mark word-level timing in karaoke-style VTT; they carry no text.
_VTT_TIMESTAMP_TAG_RE = re.compile(r"<\d{1,2}:\d{2}:\d{2}\.\d{3}>")

# Stray SRT/VTT timestamp strings in body text: "00:01:23,456" or "00:01:23.456"
# Appears when a blank-line block separator is absent and the parser bleeds
# the next block's timestamp into the previous block's text.
_STRAY_TIMESTAMP_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}[,.]\d{3}\b")

# Leftover SRT arrow with timestamp ("-->") from malformed block splitting.
# Made specific (requires a following timestamp) to avoid removing "→" in text.
_SRT_ARROW_RE = re.compile(r"\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}")

# Non-standard whitespace characters:
#   \xa0   NO-BREAK SPACE      → replace with regular space
#   \u00ad SOFT HYPHEN         → remove (invisible rendering hint)
#   \u200b ZERO-WIDTH SPACE    → remove
#   \u200c ZERO-WIDTH NON-JOINER → remove
#   \u200d ZERO-WIDTH JOINER   → remove
#   \u2060 WORD JOINER         → remove
#   \ufeff BOM mid-file        → remove (start-of-file BOM handled by utf-8-sig codec)
_NBSP_RE = re.compile(r"\xa0")
_INVISIBLE_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SubtitleCleanerConfig:
    """
    Feature toggles for SubtitleTextCleaner.

    Each toggle corresponds to one class of artifact.  Set a flag to False
    to skip that cleaning step — useful for ablation or when a corpus is
    known not to contain that type of noise.

    Attributes:
        strip_ass_tags:
            Remove ASS/SSA override blocks such as {\\an8}, {\\b1}.
            Safe to enable for all corpora: curly braces do not appear in
            normal subtitle text.

        strip_vtt_timestamp_tags:
            Remove WebVTT in-cue timestamp tags such as <00:00:01.234>.
            Safe to enable: these are machine markers, never human text.

        decode_html_entities:
            Decode HTML character references to their Unicode equivalents.
            &amp; → &, &nbsp; → \\xa0 (then handled by normalize_whitespace).
            Safe to enable: decoding a non-entity string like "Tom & Jerry"
            produces "Tom & Jerry" unchanged.

        normalize_whitespace:
            Replace non-breaking spaces with regular spaces and remove
            invisible Unicode characters (ZWS, soft hyphen, BOM, etc.).

        strip_stray_timestamps:
            Remove isolated SRT timestamp strings and --> arrows from
            body text.  Only matches the specific HH:MM:SS,mmm format to
            avoid affecting legitimate time references in dialogue.
    """
    strip_ass_tags: bool = True
    strip_vtt_timestamp_tags: bool = True
    decode_html_entities: bool = True
    normalize_whitespace: bool = True
    strip_stray_timestamps: bool = True


# ---------------------------------------------------------------------------
# Cleaner
# ---------------------------------------------------------------------------

class SubtitleTextCleaner:
    """
    Applies a configurable pipeline of text-level cleaning steps to raw
    subtitle content.

    Each step is a separate method so individual transformations can be
    unit-tested in isolation and toggled via SubtitleCleanerConfig.

    The cleaner is stateless after construction and thread-safe.

    Cleaning order
    --------------
    1. Strip ASS/SSA tags           {\\b1} {\\an8} {\\pos(...)}
    2. Strip VTT timestamp tags     <00:00:01.234>
    3. Decode HTML entities         &amp; → &  (runs before whitespace
                                    normalization so &nbsp; → \\xa0 → space)
    4. Normalize whitespace         \\xa0 → space, zero-width chars → removed
    5. Strip stray timestamps       00:01:23,456 and --> remnants
    6. Collapse whitespace          multiple spaces → one  (always applied)
    """

    def __init__(self, config: Optional[SubtitleCleanerConfig] = None) -> None:
        self.config = config or SubtitleCleanerConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clean(self, text: str) -> str:
        """
        Apply all enabled cleaning steps to *text* and return the result.

        The returned string may be empty if the input consisted entirely of
        artifacts.  Callers should check has_alphabetic_content() before
        adding the result to the fragment list.

        Args:
            text: Raw subtitle text, possibly containing artifacts.

        Returns:
            Cleaned text with artifacts removed and whitespace normalised.
        """
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
        # Whitespace collapsing is always applied — it is cosmetic, not a
        # feature that needs toggling.
        return self._collapse_whitespace(t)

    @staticmethod
    def has_alphabetic_content(text: str) -> bool:
        """
        Return True if *text* contains at least one Unicode alphabetic character.

        Use this after clean() to decide whether the result is worth keeping
        as a subtitle fragment.  Text that reduces to pure symbols, numbers,
        or whitespace produces no learnable units and should be dropped.

        Examples that return False: "", "♪ ♫", "---", "123", "00:01:23,456"
        Examples that return True:  "Ja.", "[Musik]", "Das ist gut."
        """
        return any(c.isalpha() for c in text)

    # ------------------------------------------------------------------
    # Individual cleaning steps
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_ass_tags(text: str) -> str:
        """
        Remove ASS/SSA styling override blocks.

        Matches anything between {  } since curly braces do not appear in
        normal German subtitle text.  Common examples:

            {\\an8}             — alignment: top-centre
            {\\b1}              — bold on
            {\\i1}              — italic on
            {\\pos(100,200)}    — absolute position
            {\\move(x1,y1,x2,y2,t1,t2)}
            {\\c&H00FF00&}      — colour override
        """
        return _ASS_TAG_RE.sub("", text)

    @staticmethod
    def _strip_vtt_timestamp_tags(text: str) -> str:
        """
        Remove WebVTT timestamp cue tags embedded inside cue text.

        In karaoke-style VTT files each word is preceded by a timestamp
        cue like <00:00:01.234> to enable word-level highlighting.  These
        are machine markers with no textual content.

        Example:
            "<00:00:01.000>Das <00:00:01.400>ist <00:00:01.700>gut."
            → "Das ist gut."
        """
        return _VTT_TIMESTAMP_TAG_RE.sub("", text)

    @staticmethod
    def _decode_html_entities(text: str) -> str:
        """
        Decode HTML character references to their Unicode equivalents.

        Uses the standard library html.unescape() — no external dependency.

        Common cases in subtitle files:
            &amp;   → &     (ampersand in entity-encoding encoders)
            &lt;    → <
            &gt;    → >
            &apos;  → '
            &quot;  → "
            &nbsp;  → \\xa0 (non-breaking space; normalised in next step)
            &#160;  → \\xa0
            &#x27;  → '

        Strings without entities are returned unchanged.
        """
        return html.unescape(text)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """
        Replace non-standard whitespace characters with canonical forms.

        NO-BREAK SPACE (\\xa0)          → regular space
        SOFT HYPHEN (\\u00ad)            → removed (invisible, only a rendering hint)
        ZERO-WIDTH SPACE (\\u200b)       → removed
        ZERO-WIDTH NON-JOINER (\\u200c)  → removed
        ZERO-WIDTH JOINER (\\u200d)      → removed
        WORD JOINER (\\u2060)            → removed
        BOM mid-file (\\ufeff)           → removed

        The BOM at the very start of a file is stripped by the utf-8-sig
        codec.  This method handles the rare case where a BOM appears
        mid-stream, e.g. in a badly-concatenated subtitle file.
        """
        t = _NBSP_RE.sub(" ", text)
        t = _INVISIBLE_RE.sub("", t)
        return t

    @staticmethod
    def _strip_stray_timestamps(text: str) -> str:
        """
        Remove isolated SRT-format timestamp strings from body text.

        Stray timestamps appear when a blank-line block separator is absent
        and the block parser bleeds the next block's header into the
        previous block's text:

            "Das ist gut. 00:01:23,456 Das nächste."
            → "Das ist gut.  Das nächste."  (then collapsed to one space)

        Also removes leftover SRT arrows ("-->") with an immediately
        following timestamp — a slightly different malformation where the
        full timing line ends up in the text body.

        The timestamp pattern is made specific (HH:MM:SS followed by a
        separator and milliseconds) so it does not accidentally match
        legitimate time expressions like "um 8:30 Uhr".
        """
        t = _SRT_ARROW_RE.sub("", text)
        t = _STRAY_TIMESTAMP_RE.sub("", t)
        return t

    @staticmethod
    def _collapse_whitespace(text: str) -> str:
        """Collapse runs of spaces to a single space and strip both ends."""
        return re.sub(r" {2,}", " ", text).strip()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _demo() -> None:
    cases: list[tuple[str, str]] = [
        ("ASS positioning tag",
         "{\\an8}Das ist wirklich interessant."),
        ("ASS bold + italic",
         "{\\b1}{\\i1}Achtung, Spoiler!{\\i0}{\\b0}"),
        ("VTT timestamp cues (karaoke)",
         "<00:00:01.000>Das <00:00:01.400>ist <00:00:01.700>gut."),
        ("HTML entities",
         "Tom &amp; Jerry fahren nach &Ouml;sterreich."),
        ("Non-breaking space",
         "Das\xa0ist\xa0wirklich gut."),
        ("Zero-width space in word",
         "Viel\u200bleicht ist das so."),
        ("Stray timestamp in body",
         "Das war schön. 00:01:23,456 Und das auch."),
        ("SRT arrow remnant",
         "Wir warten --> 00:02:00,000 auf dich."),
        ("All combined",
         "{\\an8}<00:00:01.000>Tom &amp; Jerry\xa0fahren 00:01:23,456 zusammen."),
        ("No artifacts — passthrough",
         "Ich gehe morgen ins Kino."),
        ("Only ASS tag — becomes empty",
         "{\\an8}"),
    ]

    cleaner = SubtitleTextCleaner()
    print(f"\n  {'INPUT':<55}  CLEANED")
    print(f"  {'─' * 55}  {'─' * 45}")
    for label, raw in cases:
        cleaned = cleaner.clean(raw)
        has_alpha = SubtitleTextCleaner.has_alphabetic_content(cleaned)
        alpha_marker = "" if has_alpha else "  ← no alpha content"
        preview_raw = raw if len(raw) <= 53 else raw[:50] + "..."
        print(f"  {preview_raw:<55}  {cleaned!r}{alpha_marker}")


if __name__ == "__main__":
    _demo()
