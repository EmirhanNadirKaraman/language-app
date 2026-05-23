"""
TODO #35 — subtitle-track selection prefers the original audio language.

Two units under test in subtitle-scraper/pipeline.py:
  get_original_audio_language(video_id)
      Reads yt-dlp info["language"], normalizes to a base code, returns it
      only when we have a spaCy model for it (else None).
  get_transcript(video_id, language=None)  [auto-detect branch]
      Floats the original-audio language to the front of the search order so
      its manual subtitle track wins over an alphabetically-earlier one
      (the old English-first bias).

No network: yt-dlp and fetch_with_retries are monkeypatched. The scraper
pipeline is loaded by explicit file path (root has a shadowing pipeline.py).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRAPER = Path(__file__).resolve().parent.parent / "subtitle-scraper"


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# phrase_finder first so pipeline's `from phrase_finder import ...` reuses it.
_load("phrase_finder", _SCRAPER / "phrase_finder.py")


@pytest.fixture
def pipeline():
    saved = list(sys.path)
    try:
        return _load("subtitle_scraper_pipeline", _SCRAPER / "pipeline.py")
    finally:
        sys.path[:] = saved


class _FakeYDL:
    """Context-manager stand-in for yt_dlp.YoutubeDL returning a fixed info."""
    def __init__(self, info):
        self._info = info

    def __call__(self, opts):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        return self._info


# ---------------------------------------------------------------------------
# get_original_audio_language
# ---------------------------------------------------------------------------

def test_audio_language_plain_code(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline.yt_dlp, "YoutubeDL", _FakeYDL({"language": "es"}))
    assert pipeline.get_original_audio_language("vid") == "es"


def test_audio_language_normalizes_region_suffix(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline.yt_dlp, "YoutubeDL", _FakeYDL({"language": "es-419"}))
    assert pipeline.get_original_audio_language("vid") == "es"
    monkeypatch.setattr(pipeline.yt_dlp, "YoutubeDL", _FakeYDL({"language": "en-US"}))
    assert pipeline.get_original_audio_language("vid") == "en"


def test_audio_language_unknown_code_returns_none(pipeline, monkeypatch):
    # 'xx' has no spaCy model in LANG_MODEL_MAP → None (caller uses fixed order).
    monkeypatch.setattr(pipeline.yt_dlp, "YoutubeDL", _FakeYDL({"language": "xx"}))
    assert pipeline.get_original_audio_language("vid") is None


def test_audio_language_missing_returns_none(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline.yt_dlp, "YoutubeDL", _FakeYDL({}))
    assert pipeline.get_original_audio_language("vid") is None


def test_audio_language_extract_error_returns_none(pipeline, monkeypatch):
    class _Boom:
        def __call__(self, opts): return self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, *a, **k): raise RuntimeError("network")
    monkeypatch.setattr(pipeline.yt_dlp, "YoutubeDL", _Boom())
    assert pipeline.get_original_audio_language("vid") is None


# ---------------------------------------------------------------------------
# get_transcript auto-detect ordering
# ---------------------------------------------------------------------------

# LANG_TRANSCRIPT_CODES groups don't all start with the bare code
# (e.g. 'en' → ['en-GB', 'en', 'en-US']). Resolve the language from the
# first code's base so the fakes don't depend on the exact ordering inside
# each group.
def _lang_of(codes):
    return codes[0].split("-")[0]


def test_auto_detect_tries_original_audio_language_first(pipeline, monkeypatch):
    """Spanish-audio video that ALSO has English manual subs: the es codes
    must be tried before en, so it tags 'es' not 'en'."""
    monkeypatch.setattr(pipeline, "get_original_audio_language", lambda vid: "es")

    tried: list[str] = []

    def fake_fetch(video_id, codes):
        lang = _lang_of(codes)
        tried.append(lang)
        if lang == "es":
            return ([{"text": "Hola, ¿qué tal estáis hoy amigos míos?", "start": 0.0, "duration": 1.0}],
                    "es", "manual")
        # en would also succeed, but we should never reach it
        return ([{"text": "Hello there everyone, welcome back", "start": 0.0, "duration": 1.0}],
                "en", "manual")

    monkeypatch.setattr(pipeline, "fetch_with_retries", fake_fetch)

    snippets, detected, actual_code, source = pipeline.get_transcript("vid")
    assert detected == "es"
    assert tried[0] == "es", f"es must be tried first; order was {tried}"


def test_auto_detect_falls_back_when_audio_language_has_no_subs(pipeline, monkeypatch):
    """Audio is es but the video only has an English manual track. es is
    tried first (no subs → ValueError), then the search continues and tags
    en. (Auto-generated-es fallback is a separate, documented tier — not
    implemented here.)"""
    monkeypatch.setattr(pipeline, "get_original_audio_language", lambda vid: "es")

    tried: list[str] = []

    def fake_fetch(video_id, codes):
        lang = _lang_of(codes)
        tried.append(lang)
        if lang == "es":
            raise ValueError("no es manual subs")
        if lang == "en":
            return ([{"text": "Hello there everyone, welcome back to the channel", "start": 0.0, "duration": 1.0}],
                    "en", "manual")
        raise ValueError("no subs")

    monkeypatch.setattr(pipeline, "fetch_with_retries", fake_fetch)

    snippets, detected, actual_code, source = pipeline.get_transcript("vid")
    assert tried[0] == "es", "es still attempted first"
    assert detected == "en", "falls back to the available English manual track"


def test_auto_detect_no_audio_signal_uses_fixed_order(pipeline, monkeypatch):
    """When the audio language is undetectable, behaviour is the pre-#35
    fixed order (English first in LANG_TRANSCRIPT_CODES)."""
    monkeypatch.setattr(pipeline, "get_original_audio_language", lambda vid: None)

    tried: list[str] = []

    def fake_fetch(video_id, codes):
        lang = _lang_of(codes)
        tried.append(lang)
        if lang == "en":
            return ([{"text": "Hello there, this is a test sentence in English", "start": 0.0, "duration": 1.0}],
                    "en", "manual")
        raise ValueError("no subs")

    monkeypatch.setattr(pipeline, "fetch_with_retries", fake_fetch)

    snippets, detected, actual_code, source = pipeline.get_transcript("vid")
    assert tried[0] == "en", "fixed order: English is first in LANG_TRANSCRIPT_CODES"
    assert detected == "en"


def test_explicit_language_path_ignores_audio_probe(pipeline, monkeypatch):
    """When a language is explicitly requested (channel loop --language es),
    the audio probe is NOT consulted — the seed language is authoritative.
    Guards the path that produced the 248 good UNED videos."""
    probe_called = {"n": 0}

    def probe(vid):
        probe_called["n"] += 1
        return "en"
    monkeypatch.setattr(pipeline, "get_original_audio_language", probe)

    def fake_fetch(video_id, codes):
        return ([{"text": "Hola mundo", "start": 0.0, "duration": 1.0}], "es", "manual")
    monkeypatch.setattr(pipeline, "fetch_with_retries", fake_fetch)

    snippets, detected, actual_code, source = pipeline.get_transcript("vid", "es")
    assert detected == "es"
    assert probe_called["n"] == 0, "explicit language must not probe audio language"
