# Transcript Click → Progression — Expected Behavior for Testing

## Happy path

- `POST /words/word/{word_id}/transcript-click` returns 204 No Content
- After the call, `user_word_knowledge.passive_level` incremented by 1 for the given word
- After the call, `user_word_knowledge.times_seen` incremented by 1
- First click on a word with no existing passive SRS card → a passive SRS card is created with:
  - `interval_days = 1.0`
  - `ease_factor = 2.5`
  - `repetitions = 0`
  - `due_date = NOW` (immediately due)
- Second click on the same word (passive SRS card already exists) → `passive_level` increments again, but the SRS card's `interval_days`, `ease_factor`, `repetitions`, and `due_date` are **unchanged**

## Edge cases

- `word_id < 1` in the path returns 422 (FastAPI Path validation)
- Endpoint requires authentication; unauthenticated request returns 401
- If `user_word_knowledge` row does not yet exist for the user+word, one is created by the upsert in `apply_progression`

## Non-goals (what the feature should NOT do)

- Must NOT advance an existing passive SRS card (no SM-2 correct branch — action is "create", not "correct")
- Must NOT fail the word picker UI if this endpoint fails (fire-and-forget at the frontend layer)
- Must NOT fire for the `toggleWordStatus` (right-click) code path
- `transcript_seen` must NOT be fired by any current code path (it is explicitly deferred and commented out)
