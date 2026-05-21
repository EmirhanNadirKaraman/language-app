---
name: Phase 2 passive/active progression
description: Progression service design, rule table, and wiring for passive vs active knowledge tracks
type: project
---

Passive/active knowledge distinction is now explicit and consistent. The single source of truth is `progression_service.py`.

**Why:** User wanted no duplicated progression logic across chat, transcript, and SRS code. All knowledge-state changes must funnel through one place.

**How to apply:** Any new feature that should update knowledge levels (transcript clicks, free chat matching, SRS reviews) adds a new entry to `_RULES` in `progression_service.py` and calls `apply_progression()`. Do NOT write progression logic in routers or other services.

## Files

- `backend/services/progression_service.py` — `_RULES` dict, `compute_delta(event)` (pure function), `apply_progression(pool, user_id, item_id, item_type, event)` (DB write)
- `backend/tests/test_progression.py` — 8 unit tests (pure), 16 integration tests
- `backend/services/guided_chat_service.py` — now delegates entirely to progression_service; `update_progress(target_used, target_counted)` maps to event strings
- `backend/routers/words.py` — awaits `progression_service.apply_progression` on status changes (NOT fire-and-forget — progression is primary)
- `backend/routers/chat.py` — always calls `update_progress` now (even when target_used=False, to penalize SRS)

## Rule table (implemented events)

| Event | passive_delta | active_delta | passive SRS | active SRS |
|-------|---|---|---|---|
| guided_counted | +1 | +1 | correct | correct |
| guided_used | +1 | 0 | correct | — |
| guided_not_used | 0 | 0 | — | incorrect |
| status_marked_learning | +1 | 0 | create | — |
| status_marked_known | +3 | +1 | correct | correct |
| status_marked_unknown | 0 | 0 | — | — |

## Thresholds
- `PASSIVE_PROMOTION_THRESHOLD = 5` → 'unknown' auto-promotes to 'learning'
- `ACTIVE_MASTERY_THRESHOLD = 3` → any status auto-promotes to 'known'

## Deferred events (add entries to _RULES when ready)
- transcript_seen, transcript_clicked (no endpoint exists)
- free_chat_matched, free_chat_used_correctly, free_chat_mixed_lang (word_matches always [])
- passive_review_correct/incorrect, active_review_correct/incorrect (old SRS uses different tables)

## Schema
No migration needed — passive_level, active_level, times_seen, times_used_correctly, srs_cards.direction='passive'/'active' all already existed.
