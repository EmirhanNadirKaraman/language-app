"""
Tests for the subtitle-scraper channel loading.

Pins two invariants after the 2026-05-20 flat-file removal (TODO #7):
  1. `load_channels(cursor)` returns rows from the `channel` table only.
  2. No code under `subtitle-scraper/` reads the deleted flat files
     (`channels.json`, `merged_channels.json`, `subscribed_channels.txt`).
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

SCRAPER_DIR = Path(__file__).resolve().parents[1] / "subtitle-scraper"
LEGACY_FILES = ("channels.json", "merged_channels.json", "subscribed_channels.txt")


@pytest.fixture(scope="module")
def pipeline_module():
    """Import subtitle-scraper/pipeline.py without running its main().

    phrase_finder resolves its data path from __file__, so no cwd hack is
    needed — adding the scraper dir to sys.path is enough.
    """
    scraper = str(SCRAPER_DIR)
    if scraper not in sys.path:
        sys.path.insert(0, scraper)
    try:
        sys.modules.pop("pipeline", None)
        module = importlib.import_module("pipeline")
        yield module
    finally:
        try:
            sys.path.remove(scraper)
        except ValueError:
            pass
        sys.modules.pop("pipeline", None)


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params: tuple | None = None

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params

    def fetchall(self):
        return self._rows


def test_load_channels_reads_db_rows(pipeline_module):
    rows = [
        ("UCabc", "Kurzgesagt", "de"),
        ("UCdef", None, "de"),
        ("UCghi", "English Channel", "en"),
    ]
    cursor = _FakeCursor(rows)
    result = pipeline_module.load_channels(cursor)

    assert result == [
        {"id": "UCabc", "name": "Kurzgesagt", "language": "de"},
        {"id": "UCdef", "name": "UCdef", "language": "de"},  # NULL name falls back to id
        {"id": "UCghi", "name": "English Channel", "language": "en"},
    ]
    assert "FROM channel" in cursor.last_sql
    assert "active = TRUE" in cursor.last_sql


def test_load_channels_empty_db(pipeline_module):
    cursor = _FakeCursor([])
    assert pipeline_module.load_channels(cursor) == []


def test_load_channels_without_language_filter_omits_where_language(pipeline_module):
    """Default call (no language arg) keeps the pre-existing SQL shape —
    no `language = %s` clause, no params. Locks back-compat for every
    call site that passed only the cursor."""
    cursor = _FakeCursor([])
    pipeline_module.load_channels(cursor)
    assert "language = " not in cursor.last_sql
    assert cursor.last_params is None


def test_load_channels_with_language_filters_query(pipeline_module):
    """`language='es'` appends `AND language = %s` and passes the code as
    a bind parameter (no string interpolation — guards against the SQL-
    injection-by-accident an f-string would invite)."""
    cursor = _FakeCursor([("UCx", "Spanish Channel", "es")])
    result = pipeline_module.load_channels(cursor, language="es")

    assert result == [{"id": "UCx", "name": "Spanish Channel", "language": "es"}]
    assert "active = TRUE" in cursor.last_sql
    assert "language = %s" in cursor.last_sql
    assert cursor.last_params == ("es",)


def test_no_scraper_code_reads_legacy_flat_files():
    """No Python file under subtitle-scraper/ should reference the deleted
    flat channel files. seed_data/channels.json is the only allowed seed."""
    offenders: list[tuple[Path, int, str]] = []
    pattern = re.compile(r"(channels\.json|merged_channels\.json|subscribed_channels\.txt)")
    for py in SCRAPER_DIR.rglob("*.py"):
        if "__pycache__" in py.parts or "transcript_cache" in py.parts:
            continue
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            m = pattern.search(line)
            if not m:
                continue
            # Allow the bundled seed at seed_data/channels.json.
            if "seed_data" in line and m.group(1) == "channels.json":
                continue
            offenders.append((py.relative_to(SCRAPER_DIR), lineno, line.strip()))
    assert not offenders, (
        "Found legacy flat-file references in subtitle-scraper/:\n  "
        + "\n  ".join(f"{p}:{ln}: {src}" for p, ln, src in offenders)
    )


def test_legacy_flat_files_absent():
    for name in LEGACY_FILES:
        assert not (SCRAPER_DIR / name).exists(), f"{name} should be deleted"


def test_seed_file_present():
    seed = SCRAPER_DIR / "seed_data" / "channels.json"
    assert seed.exists()
    import json
    data = json.loads(seed.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0
    assert {"id", "name", "language"}.issubset(set(data[0].keys()))
