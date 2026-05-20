"""
#24-followup migration regression tests.

Locks in: concurrent same-key requests through migrated LLM call sites
invoke the underlying provider exactly once, even under high concurrency.

Strategy:
  - Monkeypatch `_MOCK = False` so the real cache pathway runs.
  - Monkeypatch the underlying provider call (`_client.messages.create`
    for llm_service + reading_llm_service, `_call_llm` for book_llm_service)
    with a counter+event stub.
  - Use a unique cache key per test (uuid in the input) so prior runs don't
    contaminate.
  - Fire N concurrent callers, hold the stub in `event.wait()` until all
    callers have queued on the per-key lock, then release.
  - Assert provider was called exactly once and all callers got the same
    result.

Also covers: evaluate_production stays uncached (high-cardinality user input).
"""
import asyncio
import uuid

import pytest

from backend.services import (
    book_llm_service,
    llm_cache_service,
    llm_service,
    reading_llm_service,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_locks_between_tests():
    llm_cache_service.reset_for_tests()
    yield
    llm_cache_service.reset_for_tests()


def _unique_de_word() -> str:
    """A 'word' that's certain to miss the cache because the suffix is uuid."""
    return f"testword_{uuid.uuid4().hex[:10]}"


class _StubBlock:
    """A fake Anthropic tool_use response block. `input` is set per call."""
    type = "tool_use"

    def __init__(self, payload: dict):
        self.input = payload


class _StubResp:
    def __init__(self, payload: dict):
        self.content = [_StubBlock(payload)]


def _gated_stub(payload: dict, gate: asyncio.Event, counter: dict):
    """Build an async stub for `_client.messages.create` that:
      - increments counter['n'] on each call
      - awaits gate before returning, so callers queue on the lock
      - returns a fake tool_use response with `payload`
    """
    async def _stub(**_kwargs):
        counter["n"] += 1
        await gate.wait()
        return _StubResp(payload)
    return _stub


# ---------------------------------------------------------------------------
# translate_item_gloss (llm_service)
# ---------------------------------------------------------------------------

async def test_translate_item_gloss_concurrent_same_key_one_provider_call(
    db_pool, monkeypatch,
):
    monkeypatch.setattr(llm_service, "_MOCK", False)

    counter = {"n": 0}
    gate = asyncio.Event()
    monkeypatch.setattr(
        llm_service._client.messages, "create",
        _gated_stub({"gloss": "stub"}, gate, counter),
    )

    word = _unique_de_word()

    async def _caller():
        return await llm_service.translate_item_gloss(
            word, "word", "de", pool=db_pool,
        )

    tasks = [asyncio.create_task(_caller()) for _ in range(10)]
    await asyncio.sleep(0.05)
    gate.set()
    results = await asyncio.gather(*tasks)

    assert counter["n"] == 1, (
        f"translate_item_gloss must call provider exactly once across "
        f"10 concurrent same-key callers; got {counter['n']}"
    )
    assert all(r == "stub" for r in results)


# ---------------------------------------------------------------------------
# reading_llm_service.translate_sentence
# ---------------------------------------------------------------------------

async def test_reading_translate_concurrent_same_key_one_provider_call(
    db_pool, monkeypatch,
):
    monkeypatch.setattr(reading_llm_service, "_MOCK", False)

    counter = {"n": 0}
    gate = asyncio.Event()
    monkeypatch.setattr(
        reading_llm_service._client.messages, "create",
        _gated_stub({"translation": "stub translation"}, gate, counter),
    )

    sentence = f"Unique reading sentence {uuid.uuid4().hex[:10]}."

    async def _caller():
        return await reading_llm_service.translate_sentence(
            sentence, "de", pool=db_pool,
        )

    tasks = [asyncio.create_task(_caller()) for _ in range(10)]
    await asyncio.sleep(0.05)
    gate.set()
    results = await asyncio.gather(*tasks)

    assert counter["n"] == 1
    assert all(r == "stub translation" for r in results)


# ---------------------------------------------------------------------------
# reading_llm_service.explain_in_context
# ---------------------------------------------------------------------------

async def test_reading_explain_concurrent_same_key_one_provider_call(
    db_pool, monkeypatch,
):
    monkeypatch.setattr(reading_llm_service, "_MOCK", False)

    counter = {"n": 0}
    gate = asyncio.Event()
    monkeypatch.setattr(
        reading_llm_service._client.messages, "create",
        _gated_stub({"explanation": "stub explanation"}, gate, counter),
    )

    suffix   = uuid.uuid4().hex[:10]
    sentence = f"Eine Beispielsatz mit {suffix}."
    selected = suffix

    async def _caller():
        return await reading_llm_service.explain_in_context(
            selected, sentence, "de", pool=db_pool,
        )

    tasks = [asyncio.create_task(_caller()) for _ in range(10)]
    await asyncio.sleep(0.05)
    gate.set()
    results = await asyncio.gather(*tasks)

    assert counter["n"] == 1
    assert all(r == "stub explanation" for r in results)


# ---------------------------------------------------------------------------
# book_llm_service.repair_block — different stub shape (no _client)
# ---------------------------------------------------------------------------

async def test_book_repair_concurrent_same_key_one_provider_call(
    db_pool, monkeypatch,
):
    """book_llm_service.repair_block goes through `_call_llm` (its own helper),
    not the shared `_client.messages.create`. Stub at that layer."""
    counter = {"n": 0}
    gate = asyncio.Event()

    async def _stub_call_llm(_user_message: str) -> str:
        counter["n"] += 1
        await gate.wait()
        return "corrected by stub"

    monkeypatch.setattr(book_llm_service, "_call_llm", _stub_call_llm)

    block = {
        "block_id": 1,
        "ocr_text": f"raw OCR garble {uuid.uuid4().hex[:10]}",
        "clean_text": "",
    }

    async def _caller():
        return await book_llm_service.repair_block(db_pool, block)

    tasks = [asyncio.create_task(_caller()) for _ in range(10)]
    await asyncio.sleep(0.05)
    gate.set()
    results = await asyncio.gather(*tasks)

    assert counter["n"] == 1, (
        f"repair_block must call _call_llm exactly once across "
        f"10 concurrent same-key callers; got {counter['n']}"
    )
    assert all(r == "corrected by stub" for r in results)


# ---------------------------------------------------------------------------
# Negative test: evaluate_production stays uncached
# ---------------------------------------------------------------------------

async def test_evaluate_production_remains_uncached(db_pool, monkeypatch):
    """Per llm_service.evaluate_production docstring: 'Not cached — input is
    user-supplied and high-cardinality.' Two consecutive identical calls must
    BOTH invoke the provider — proving the migration didn't accidentally pull
    this path into the cache."""
    monkeypatch.setattr(llm_service, "_MOCK", False)

    counter = {"n": 0}

    async def _stub(**_kwargs):
        counter["n"] += 1
        return _StubResp({
            "correct":        True,
            "feedback":       "ok",
            "corrected_form": "Hund",
        })

    monkeypatch.setattr(llm_service._client.messages, "create", _stub)

    await llm_service.evaluate_production("Hund", "hund", "Hund", "de")
    await llm_service.evaluate_production("Hund", "hund", "Hund", "de")

    assert counter["n"] == 2, (
        "evaluate_production must NOT cache — provider should be called once "
        f"per request; got {counter['n']} calls for 2 identical requests"
    )


# ---------------------------------------------------------------------------
# Existing cache-hit behaviour still works through get_or_compute
# ---------------------------------------------------------------------------

async def test_translate_item_gloss_second_call_skips_provider(
    db_pool, monkeypatch,
):
    """After a successful first call populates the cache, the second call
    for the same input must skip the provider entirely. Regression guard
    against the migration accidentally bypassing the cache check."""
    monkeypatch.setattr(llm_service, "_MOCK", False)

    counter = {"n": 0}

    async def _stub(**_kwargs):
        counter["n"] += 1
        return _StubResp({"gloss": "first call"})

    monkeypatch.setattr(llm_service._client.messages, "create", _stub)

    word = _unique_de_word()

    r1 = await llm_service.translate_item_gloss(word, "word", "de", pool=db_pool)
    r2 = await llm_service.translate_item_gloss(word, "word", "de", pool=db_pool)

    assert counter["n"] == 1, f"second call should hit the cache; got {counter['n']} provider calls"
    assert r1 == r2 == "first call"
