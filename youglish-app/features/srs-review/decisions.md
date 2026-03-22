# SRS Review — Decisions

## Display text is resolved at query time, not stored on the card

`review_service.get_due_cards()` joins `word_table`, `phrase_table`, and `grammar_rule_table` at query time to build `display_text`. The `srs_cards` table itself does not store the text. This means the display is always up-to-date if the item is renamed, and avoids stale denormalized data.

## SM-2 scheduling is fully owned by `progression_service`

`review_service.submit_answer()` maps `(direction, correct)` to a progression event name and calls `progression_service.apply_progression()`. The SM-2 logic (interval calculation, ease factor adjustment, `due_date` update) lives exclusively in `progression_service._update_srs()`. `review_service` has no scheduling logic.

Event mapping:
- passive + correct   → `passive_review_correct`
- passive + incorrect → `passive_review_incorrect`
- active  + correct   → `active_review_correct`
- active  + incorrect → `active_review_incorrect`

## The backend returns only `{card_id, success}`

The submit-answer response carries no scheduling metadata (no new interval, no new due date). The client does not display or use scheduling data after answering. Advancing to the next card is entirely client-side.

## Items with status `known` are excluded from due cards

`get_due_cards()` filters `uwk.status != 'known'`. A user who has been promoted to `known` via thresholds or manual marking will not be quizzed on that item. This is intentional — `known` items are out of the active learning rotation.

## Cards are ordered by `due_date ASC`

The most overdue cards are shown first so chronic gaps are addressed before newer cards.

## Language filtering goes through the item join, not a column on `srs_cards`

There is no `language` column on `srs_cards`. Language filtering is enforced by the `WHERE wt.language = $3` (and equivalent for phrase/grammar_rule) in the join. Cards whose item has no row in the language's table are excluded by the IS NOT NULL guard.

## Session limit: frontend requests 30, backend cap is 100

The frontend hardcodes `limit=30` in `getDueCards()`. The router enforces `1 ≤ limit ≤ 100`. This is a soft cap — sessions longer than 30 require reloading.

## Analytics are fire-and-forget

`submit_answer()` records a usage event inside `asyncio.create_task()`. A logging failure must never fail a review answer.

## "Skip" does not call the backend

The Skip button calls the frontend `advance()` function directly, which moves to the next card without submitting. No server call is made. The skipped card remains due and will reappear on the next reload.

## Legacy endpoints are dead code

`routers/srs.py` still exposes `/check-answer`, `/magic-sentences`, and `/cloze-questions`. These route to `srs_service.py`, which references tables that do not exist in the current migration chain. They will fail at runtime if called. They are not part of this feature and should be removed when convenient.
