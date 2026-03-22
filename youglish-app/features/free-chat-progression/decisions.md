# Free Chat → Progression — Decisions

## Free chat is German-only

The LLM system prompt is hardcoded to German. `match_learning_words()` is always called with `language='de'` regardless of any user preference. Extending to other languages would require per-session language routing.

## Token matching is regex-based, not NLP-based

`chat_service.match_learning_words()` tokenizes with `re.findall(r"[^\W\d_]+", text, re.UNICODE)` — it extracts alphabetic words, lowercases them, and deduplicates with a Python `set`. The DB query then checks `LOWER(wt.word) = ANY(tokens) OR LOWER(wt.lemma) = ANY(tokens)`. No NLP, no stemming beyond the lemma column.

## `known` items are excluded from matching

The query filters `uwk.status != 'known'`. A user gets no progression credit for words they have already mastered — there is nothing to advance.

## Two progression events, not three

`progression_service._RULES` defines three free-chat events: `free_chat_used_correctly`, `free_chat_mixed_lang`, and `free_chat_matched`. Only the first two are ever fired by the router. `free_chat_matched` (intended for when language context is unknown) is **defined but unreachable**. The current implementation's `language_detected in ("de", "mixed")` guard means English messages skip progression entirely and the "unknown language" case never arises. `free_chat_matched` is dead code in the rule table and should either be removed or documented as reserved.

## Progression events are awaited

Unlike analytics, progression calls (`apply_progression`) are `await`ed inside the message handler loop. They are primary knowledge-state changes and must not be silently lost.

## Analytics are fire-and-forget

Usage events for free chat are recorded inside `asyncio.create_task()`. A logging failure must never fail the chat response.

## Deduplication is in the DB layer

`match_learning_words()` uses `SELECT DISTINCT` so a word appearing multiple times in a single message results in exactly one progression event per item.
