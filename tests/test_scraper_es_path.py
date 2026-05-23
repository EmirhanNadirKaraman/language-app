"""
Stage 4 of second-language plan (2026-05-21).

End-to-end smoke test of the subtitle scraper's `populate()` against a
Spanish fixture transcript. Pins: Spanish ingestion produces Spanish
word/sentence rows and NEVER reaches `extract_german_logic` (the
German-specific extractor stays untouched).

Updated 2026-05-23 (#36): Spanish phrase extraction shipped a first slice
(reflexives + allowlisted verb+prep). This fixture deliberately contains no
such patterns, so it still writes zero phrase rows — that assertion is now
fixture-dependent, not a blanket "Spanish never extracts phrases" invariant.
The positive Spanish extract→insert path is covered in
tests/test_spanish_phrase_extractor.py.

Strategy: narrow function-level test against `subtitle-scraper/pipeline.py`
with a fake psycopg2-shaped cursor that records every `execute()` /
`mogrify()` call. A real spaCy Spanish pipeline (`es_core_news_sm`) is
loaded via spacy.load — skipped if the model isn't installed (CI hosts
that haven't run `python -m spacy download es_core_news_sm` yet).

No live network, no real DB. The German regression path stays covered
by the existing tests/test_phrase_dispatcher.py + lexy-app/backend
tests/test_matcher.py suites; we just add one mirror assertion here
that the German pipeline does invoke extract_german_logic for the
same shape of input.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


# Repo layout — load scraper modules by explicit file path so the root
# `pipeline.py` (legacy in-memory pipeline) doesn't shadow the scraper one.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRAPER = _REPO_ROOT / "subtitle-scraper"


def _load_by_path(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# phrase_finder loaded first so the scraper pipeline's `from phrase_finder
# import extract_phrases` finds the cached module under the same key.
pf = _load_by_path("phrase_finder", _SCRAPER / "phrase_finder.py")


def _load_scraper_pipeline():
    """Stage 1 helper — snapshot/restore sys.path so the scraper's
    module-init insert doesn't leak across other tests."""
    if "subtitle_scraper_pipeline" in sys.modules:
        return sys.modules["subtitle_scraper_pipeline"]
    saved = list(sys.path)
    try:
        return _load_by_path("subtitle_scraper_pipeline", _SCRAPER / "pipeline.py")
    finally:
        sys.path[:] = saved


# ---------------------------------------------------------------------------
# Fake psycopg2 cursor
# ---------------------------------------------------------------------------

class _FakeCursor:
    """Minimal psycopg2-cursor stand-in for populate().

    Records all execute() calls so the test can assert on shape; mogrify()
    returns a bytes representation of (template, args) so the
    cursor.mogrify(...) + cursor.execute(b"INSERT ... " + args_str) pattern
    in populate() rounds back to readable strings. fetchone() / fetchall()
    are scripted via the `responses` dict.
    """

    def __init__(self, *, sentence_ids: list[int], word_rows: list[tuple]):
        # execute() history: list of (sql, params) pairs.
        self.executes: list[tuple] = []
        # mogrify history: list of (template, args) pairs. Useful when the
        # rows are concatenated into a single INSERT.
        self.mogrified: list[tuple] = []
        # Scripted fetch responses.
        self._sentence_ids = [(sid,) for sid in sentence_ids]
        self._word_rows = word_rows
        # Track whether the "video exists?" SELECT was issued so the next
        # fetchone() returns the right answer.
        self._next_fetchone: list = []
        self._fetchall_queue: list[list] = []

    # --- driver hooks --------------------------------------------------

    def execute(self, sql, params=None):
        self.executes.append((sql, params))
        sql_text = sql.decode() if isinstance(sql, (bytes, bytearray)) else sql
        if isinstance(sql_text, str):
            if sql_text.startswith("SELECT 1 FROM video"):
                # video does NOT yet exist → fetchone() returns None
                self._next_fetchone.append(None)
            elif "RETURNING sentence_id" in sql_text:
                # populate calls cursor.fetchall() right after; queue rows.
                self._fetchall_queue.append(self._sentence_ids)
            elif "FROM word_table WHERE language" in sql_text:
                # word_to_sentence lookup; return the word_id map rows.
                self._fetchall_queue.append(self._word_rows)
            elif "RETURNING rule_id" in sql_text:
                # grammar_rule insert returns a fresh id.
                self._next_fetchone.append((len(self.executes),))

    def mogrify(self, template, args):
        self.mogrified.append((template, args))
        # Render args into the template so the resulting bytes are
        # inspectable. We don't need quote-perfect SQL, just a marker that
        # contains the row tuple's values.
        rendered = template
        if isinstance(rendered, str):
            rendered = rendered.encode()
        return rendered + b" :: " + repr(args).encode()

    def fetchone(self):
        if self._next_fetchone:
            return self._next_fetchone.pop(0)
        return None

    def fetchall(self):
        if self._fetchall_queue:
            return self._fetchall_queue.pop(0)
        return []


class _FakeConnection:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def es_nlp():
    """Load the Spanish spaCy model. Skip the whole module if it isn't
    installed on this host — Stage 0 docs/MAINTENANCE.md documents the
    install command."""
    spacy = pytest.importorskip("spacy")
    try:
        return spacy.load("es_core_news_sm")
    except OSError as exc:
        pytest.skip(f"es_core_news_sm not installed on this host: {exc}")


@pytest.fixture
def es_transcript():
    """A two-sentence Spanish fixture. Short enough to keep the test
    fast; rich enough to exercise word + sentence + (no-op) phrase
    insertion paths."""
    return [
        {"start": 0.0, "duration": 2.0, "text": "Hola, estoy aprendiendo español."},
        {"start": 2.0, "duration": 2.5, "text": "Quiero practicar todos los días."},
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_spanish_ingest_writes_spanish_words(es_nlp, es_transcript):
    """word_table inserts for a Spanish transcript carry language='es'."""
    scraper = _load_scraper_pipeline()
    cursor = _FakeCursor(sentence_ids=[101, 102], word_rows=[])
    conn = _FakeConnection()

    scraper.populate(
        cursor=cursor, connection=conn, db_words=set(),
        video_id="es_smoke_1", title="Smoke", thumbnail_url="thumb.jpg",
        transcript=es_transcript, language="es", dialect="es-ES",
        nlp=es_nlp, sentence_types={},
        category="other", channel_id=None, transcript_source="auto",
    )

    # populate() uses the same "(%s,%s,%s,%s,%s)" mogrify template for
    # sentence rows AND word rows. Sentence rows have a float start_time
    # at slot 1; word rows have the language code at slot 1. Filter on
    # that — only word rows carry strings in every slot.
    word_args = [args for (_, args) in cursor.mogrified
                 if isinstance(args, tuple) and len(args) == 5
                 and isinstance(args[1], str)]
    assert word_args, "No word_table inserts recorded"
    languages = {args[1] for args in word_args}
    assert languages == {"es"}, f"Expected only 'es' language, got {languages}"
    # Sanity: at least one expected Spanish surface form lands.
    surfaces = {args[0].lower() for args in word_args}
    assert "hola" in surfaces or "español" in surfaces or "practicar" in surfaces, (
        f"None of the expected Spanish tokens landed; saw {surfaces!r}"
    )


def test_spanish_ingest_writes_spanish_sentences(es_nlp, es_transcript):
    """sentence rows arrive via INSERT INTO sentence ... RETURNING sentence_id,
    one mogrify() per row. Each tuple's first slot is the video_id; the
    sentence rows themselves carry the transcript text."""
    scraper = _load_scraper_pipeline()
    cursor = _FakeCursor(sentence_ids=[10, 11], word_rows=[])
    conn = _FakeConnection()

    scraper.populate(
        cursor=cursor, connection=conn, db_words=set(),
        video_id="es_smoke_2", title="Smoke", thumbnail_url="thumb.jpg",
        transcript=es_transcript, language="es", dialect="es-ES",
        nlp=es_nlp, sentence_types={},
    )

    # The video row insert is one of the early execute()s — its tuple
    # has 9 fields including language at slot 4.
    video_inserts = [params for (sql, params) in cursor.executes
                     if isinstance(sql, str) and sql.startswith("INSERT INTO video")]
    assert video_inserts, "video INSERT not recorded"
    assert video_inserts[0][4] == "es", (
        f"video.language should be 'es' but got {video_inserts[0][4]!r}"
    )

    # Sentence rows. mogrify template "(%s,%s,%s,%s,%s)" matches sentences.
    sentence_args = [args for (template, args) in cursor.mogrified
                     if isinstance(template, str) and template == "(%s,%s,%s,%s,%s)"]
    # Filter for the sentence-shape ones — populate() uses the same template
    # for word INSERTs too, but the second positional differs (float start_time
    # for sentences vs language str for words).
    sentence_shaped = [a for a in sentence_args if isinstance(a[1], (int, float))]
    assert len(sentence_shaped) == 2, (
        f"Expected 2 sentence rows, got {len(sentence_shaped)}"
    )
    contents = {a[3] for a in sentence_shaped}
    assert any("español" in c for c in contents)
    assert any("practicar" in c for c in contents)


def test_spanish_ingest_inserts_no_phrases(es_nlp, es_transcript, monkeypatch):
    """This fixture has no first-slice phrase patterns (no reflexives /
    allowlisted verb+prep), so no phrase_blueprint / sentence_to_phrase rows
    are written and the dispatcher is only ever called with 'es'. Guards
    against spurious extraction on plain Spanish; the positive case lives in
    tests/test_spanish_phrase_extractor.py (#36)."""
    scraper = _load_scraper_pipeline()
    cursor = _FakeCursor(sentence_ids=[1, 2], word_rows=[])
    conn = _FakeConnection()

    extract_calls: list[str] = []
    orig_extract = pf.extract_phrases

    def spy(doc, language, overrides=None):
        extract_calls.append(language)
        return orig_extract(doc, language, overrides)

    monkeypatch.setattr(scraper, "extract_phrases", spy)

    scraper.populate(
        cursor=cursor, connection=conn, db_words=set(),
        video_id="es_smoke_3", title="Smoke", thumbnail_url="thumb.jpg",
        transcript=es_transcript, language="es", dialect="es-ES",
        nlp=es_nlp, sentence_types={},
    )

    # extract_phrases was reached at the insert_phrases call — but only
    # with the session/scraper language.
    assert all(c == "es" for c in extract_calls), (
        f"extract_phrases called with non-es language(s): {extract_calls}"
    )

    # No phrase_blueprint / sentence_to_phrase SQL was issued.
    sqls = [sql.decode() if isinstance(sql, (bytes, bytearray)) else sql
            for (sql, _) in cursor.executes]
    assert not any("phrase_blueprint" in s for s in sqls), (
        "phrase_blueprint INSERT must not run for Spanish ingest"
    )
    assert not any("sentence_to_phrase" in s for s in sqls), (
        "sentence_to_phrase INSERT must not run for Spanish ingest"
    )


def test_spanish_ingest_does_not_call_german_extractor(es_nlp, es_transcript, monkeypatch):
    """The strong dispatcher contract: Spanish ingest never reaches
    extract_german_logic. Pre-Stage-1 the function was the only entry
    point; post-Stage-1 it's reachable only via extract_phrases('de')."""
    scraper = _load_scraper_pipeline()
    cursor = _FakeCursor(sentence_ids=[1, 2], word_rows=[])
    conn = _FakeConnection()

    calls = {"n": 0}
    orig = pf.extract_german_logic

    def spy(doc, overrides=None):
        calls["n"] += 1
        return orig(doc, overrides)

    monkeypatch.setattr(pf, "extract_german_logic", spy)
    # _LANGUAGE_EXTRACTORS holds a direct reference captured at import — patch it too.
    monkeypatch.setitem(pf._LANGUAGE_EXTRACTORS, "de", spy)

    scraper.populate(
        cursor=cursor, connection=conn, db_words=set(),
        video_id="es_smoke_4", title="Smoke", thumbnail_url="thumb.jpg",
        transcript=es_transcript, language="es", dialect="es-ES",
        nlp=es_nlp, sentence_types={},
    )

    assert calls["n"] == 0, (
        f"extract_german_logic was called {calls['n']} time(s) during Spanish "
        f"ingest — the Stage 1 dispatcher contract was violated"
    )


def test_german_path_still_calls_extract_german_logic(monkeypatch):
    """Mirror assertion: when language='de' the dispatcher DOES reach
    extract_german_logic. Guards against the regression where a refactor
    accidentally short-circuits both branches.

    Uses the German spaCy model that phrase_finder already loaded at
    import time (no extra install)."""
    scraper = _load_scraper_pipeline()
    cursor = _FakeCursor(sentence_ids=[1, 2], word_rows=[])
    conn = _FakeConnection()

    calls = {"n": 0}
    orig = pf.extract_german_logic

    def spy(doc, overrides=None):
        calls["n"] += 1
        return orig(doc, overrides)

    monkeypatch.setattr(pf, "extract_german_logic", spy)
    monkeypatch.setitem(pf._LANGUAGE_EXTRACTORS, "de", spy)

    de_transcript = [
        {"start": 0.0, "duration": 2.0, "text": "Ich lerne Deutsch."},
        {"start": 2.0, "duration": 2.5, "text": "Ich lade meine Freunde ein."},
    ]
    scraper.populate(
        cursor=cursor, connection=conn, db_words=set(),
        video_id="de_smoke_1", title="Smoke", thumbnail_url="thumb.jpg",
        transcript=de_transcript, language="de", dialect="de-DE",
        nlp=pf.nlp,  # phrase_finder loaded de_core_news_sm at import
        sentence_types={},
    )

    assert calls["n"] >= 1, (
        "extract_german_logic should be invoked at least once for a German "
        "ingest — Stage 1 German path appears broken"
    )
