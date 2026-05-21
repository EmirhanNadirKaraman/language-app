# Transcript Click → Progression — Decisions

## `passive_srs = "create"`, not `"correct"`

A click is not a review answer. The `passive_srs="create"` action inserts an SRS card with defaults if one does not already exist, but does NOT advance an existing card's interval. This preserves SM-2 scheduling integrity: if the user has already reviewed the word and it is due in 7 days, a click does not reschedule it to tomorrow. Using `"correct"` would have been semantically wrong.

## `passive_delta = 1` (same weight as other passive events)

All passive exposure events use `passive_delta=1`. Transcript clicks carry the same weight as other passive signals and do not get extra credit.

## Fire-and-forget at the frontend

`useWordStatus.selectWord()` calls `wordsApi.recordTranscriptClick(...).catch(() => {})`. The click recording is intentionally silent — a network failure must never block the word picker panel from opening.

## Fire-and-forget at the backend (analytics only)

The progression call (`apply_progression`) is `await`ed inside the endpoint handler (it is a primary knowledge-state change). The analytics `usage_events_service.record_event()` call is fire-and-forget inside `asyncio.create_task()`.

## Only fires for words found in the database

`selectWord()` checks `result?.word_id` before calling `recordTranscriptClick`. Words that return null from the lookup (not in `word_table`) do not generate a click event. There is no error, no fallback, and no UI indication.

## `toggleWordStatus` is an orthogonal code path

Right-clicking or using the keyboard shortcut to cycle word status (`unknown → learning → known`) does NOT call `recordTranscriptClick`. These two code paths are independent. Adding `transcript_clicked` to `toggleWordStatus` was deliberately rejected to avoid double-counting.

## `transcript_seen` is deferred

Automatically firing a progression event for every word visible in the subtitle panel was deferred. The required infrastructure (playback timing, per-word deduplication within a viewing session) does not yet exist. The event rule `transcript_seen` is commented out in `progression_service._RULES`.
