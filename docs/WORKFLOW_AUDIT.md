# Workflow audit — learning a single word, end to end

Traces every step from "user encounters word for the first time" through "word counted as mastered." Each step lists what *does* happen in code today and any **HOLE** found.

Path under audit:
```
Discovery → Lookup → Mark → Exposure → Auto-promotion →
First SRS appearance → Passive review loop → Active production →
Active review loop → Mastery
```

---

## Step 0 — Prerequisite: the word must already exist in `word_table`

`word_service.lookup_word_by_text` ([word_service.py:8](../youglish-app/backend/services/word_service.py)) does `WHERE w.word ILIKE $1 AND w.language = $3 LIMIT 1`. The frontend `WordStatusPicker` shows **"Not in vocabulary"** ([WordStatusPicker.tsx:41](../youglish-app/frontend/src/components/WordStatusPicker.tsx)) when this returns null and offers no alternative — the user cannot mark a word they just heard if the scraper has never indexed it.

The scraper inserts surface forms (not just lemmas) into `word_table` ([subtitle-scraper/pipeline.py:341](../subtitle-scraper/pipeline.py)) so common inflections are usually present, but:

✅ **HOLE 1 (RESOLVED 2026-05-20, W2).** New `POST /api/v1/words/learn-anyway` (body `{text, language}`) creates a sparse `word_table` row (`pos='X'`, `lemma=text`) and atomically marks the user's relationship as `'learning'` via `apply_progression(..., status_marked_learning, status_override='learning')`. Idempotent on the `(word, language, pos)` unique key. Frontend `WordStatusPicker` shows "Not in vocabulary yet" + "Learn this anyway" button when the lookup returns null; on click `useWordStatus.learnAnyway` re-runs the lookup so the picker re-renders with the new `'learning'` state. Both passive and active SRS cards are created (#0b rule).
✅ **HOLE 2 (RESOLVED 2026-05-20, W3).** `GET /api/v1/words/by-text` now returns `{status, item, candidates[]}`. Multi-row surface forms surface all candidates (cap 10, sorted: exact case-insensitive `word` match first, then lemma asc, then word_id asc). Each candidate carries `pos` plus the user's per-row `current_status` / `passive_level` / `active_level` / due-dates so the picker can label competing meanings. `WordStatusPicker` renders a chooser; `useWordStatus.selectCandidate(c)` promotes the chosen item to `lookup` and fires the deferred `recordTranscriptClick` against the now-known `word_id` — exposure never attaches to the wrong meaning. Non-interactive callers use the new `pickSingleOrFirst()` helper for back-compat.

---

## Step 1 — Discovery: user clicks a word in a subtitle

Frontend flow:
1. `SubtitleDisplay` renders clickable tokens.
2. Click → `useWordStatus.lookupWord(word, language)` → `GET /api/v1/words/by-text`.
3. Same click also fires `recordTranscriptClick(token, word_id)` → `POST /api/v1/words/word/{word_id}/transcript-click` (fire-and-forget from the hook).

Backend: `routers/words.py:34` calls **awaited** `progression_service.apply_progression(..., "transcript_clicked")`. Per `_RULES["transcript_clicked"]` ([progression_service.py:119](../youglish-app/backend/services/progression_service.py)):
- `passive_delta = 1`, `times_seen_delta = 1`
- `passive_srs = "create"` — inserts an `srs_cards` row with direction=passive, due_date=NOW, interval=1day, ease=2.5, repetitions=0 (no-op if already exists).
- Active card is **not** created.

✅ **HOLE 3 (RESOLVED 2026-05-20, T1.1).** `recordTranscriptClick` now throws on non-2xx and `useWordStatus.selectWord` surfaces the failure via `console.warn('recordTranscriptClick failed', err)`. Still non-blocking for the picker UI, but no longer silently swallowed.

✅ **HOLE 4 (RESOLVED 2026-05-20, T1.1).** Frontend now sends `sentence_id` on every transcript click (`PlayerView` from `sentences[sentenceIdx].sentence_id`, `TranscriptPanel` from the clicked row). Backend dedups via `INSERT … ON CONFLICT DO NOTHING` against unique partial index `uq_word_usage_events_transcript_dedup` on `(user_id, item_id, item_type, sentence_id, event_day)` (migration 026, with `event_day` a UTC-date generated column). Same word, same sentence, same day → 204 no-op. Different sentence / different day / different user / different word still counts.

✅ **HOLE 5 (RESOLVED 2026-05-18).** `usage_events_service.most_frequent_unknown_items` now includes `'transcript'` in its context filter. Subtitle-clicked unknown words surface in the "Keeps coming up" insight card. Regression-guarded by `test_audit_holes.py::test_transcript_context_in_frequent_unknowns_aggregation` and `test_insights.py::test_frequent_unknowns_includes_transcript_clicks`.

---

## Step 2 — Marking status (Unknown / Learning / Known)

Two sequential calls in `routers/words.py:58`:
1. `word_service.upsert_word_status` writes `status` only (does not touch levels).
2. `progression_service.apply_progression(..., status_marked_{learning|known|unknown})`.

Each call is its own transaction.

✅ **HOLE 6 (RESOLVED 2026-05-19).** `apply_progression` gained a `status_override` parameter; status + levels + SRS now happen in one transaction. `word_service.upsert_word_status` was deleted. Router makes a single atomic call.

✅ **HOLE 7 (RESOLVED 2026-05-18).** `status_marked_unknown` now sets `passive_srs="incorrect"` and `active_srs="incorrect"` — both run the SM-2 incorrect branch on existing cards (interval=1 day, ease-0.15, reps=0). `action="incorrect"` is a no-op when the card is missing (see `_update_srs` line ~333), so this never fabricates a new active card. Levels are intentionally untouched.

✅ **HOLE 8 (RESOLVED 2026-05-18).** Originally: `status_marked_known` gave `active_delta=1` — too generous (fabricated mastery on a confidence click) and inconsistent with the threshold (1 < 3). Resolution: design clarified — manual known is *confidence*, not production evidence. New rule sets `passive_srs="correct"` only; `active_delta=0`, `active_srs=None`, `times_used_correctly_delta=0`. Active mastery now only grows from real production events. See `progression_service.py:_RULES["status_marked_known"]` docstring for the documented choices.

---

## Step 3 — Auto-promotion to "learning"

In `_maybe_promote` ([progression_service.py:217](../youglish-app/backend/services/progression_service.py)):
```
if active_level >= active_threshold and status != 'known': → known
elif passive_level >= passive_threshold and status == 'learning': → known   (Hole 9 fix)
elif passive_level >= passive_threshold and status == 'unknown':  → learning
```

With default `passive_threshold = 5` (line 60) and `transcript_clicked` adding 1 per click, a user must click the same word 5 times before it auto-promotes from unknown → learning. The next passive event past threshold then promotes learning → known.

✅ **HOLE 9 (RESOLVED 2026-05-19).** A second passive-promotion branch in `_maybe_promote` covers `learning → known` at the same per-user `passive_reps_for_known` threshold that already gates `unknown → learning`. Both transitions share the setting (the name "reps for known" was always the intent; the threshold was just only half-applied). Active level and active SRS are untouched by the passive promotion — passive mastery is recognition mastery, not production. Regression-guarded in `test_progression.py`:
  - `test_passive_mastery_promotes_learning_to_known`
  - `test_passive_below_threshold_keeps_learning`
  - `test_passive_promotion_does_not_touch_active_level`
  - `test_passive_promotion_does_not_advance_active_srs`
  - `test_passive_promotion_known_status_is_sticky`

---

## Step 4 — First SRS appearance

`review_service.get_due_cards` ([review_service.py:46](../youglish-app/backend/services/review_service.py)) filter:
```
WHERE sc.due_date <= NOW()
  AND (uwk.status IS NULL OR uwk.status != 'known')
  AND <one of the three item tables has a matching row in this language>
```

That `<…>` requirement is a **soft join** to `word_table` / `phrase_table` / `grammar_rule_table` for the language. If the item moved language, was deleted, or never had a row in the requested language, the card silently disappears from the queue.

🕳 **HOLE 10 (orphaned cards).** Nothing deletes an `srs_cards` row when its underlying `word_table` row goes away (e.g. content cleanup). The card persists forever, just never surfaces. Low risk operationally but it complicates queue-size statistics.

✅ **HOLE 11 (RESOLVED — confirmed 2026-05-20, W6).** Since #0b (2026-05-19), `status_marked_learning` sets BOTH `passive_srs="create"` and `active_srs="create"`, so every learning click schedules both directions. The W2 `learn-anyway` path and the reading `save_selection` path both route through this rule. W6 audit (`srs_backfill_service.find_missing_active_cards`) reports zero pre-#0b stragglers in the current dev DB. A safety-net backfill script (`scripts/backfill_missing_active_srs.py --apply`) is available for any future edge case.

---

## Step 5 — Passive review loop

Frontend: `SRSReviewPage` ([SRSReviewPage.tsx:27](../youglish-app/frontend/src/components/SRSReviewPage.tsx)).

Card UI shows: direction badge, the **German display text**, a question ("Do you recognise and understand this?"), level dots, and a "Show answer buttons" button followed by "I didn't know it" / "I knew it ✓".

✅ **HOLE 12 (RESOLVED 2026-05-20, T1.2).** `review_service.get_due_cards` now assigns `prompt_text = gloss, answer_text = display_text` for both directions. Passive card front shows the English gloss; reveal shows the German `display_text`; self-grade flow unchanged. Active card unchanged (still typed-input + `evaluate_production`). Both directions share the same prompt/answer mapping; only the grading mode differs. Grammar rule cards now use `prompt = short_explanation, answer = title` as the natural consequence of the uniform mapping.

🕳 **HOLE 13 (no dark mode).** Hardcoded colors: `background: '#fafafa'`, `border: '#e8eaf6'`. Renders illegibly in dark mode.

✅ **HOLE 14 (RESOLVED 2026-05-20, W5).** Skip now calls `POST /api/v1/srs/review/{card_id}/skip` → `review_service.skip_card` which moves `due_date` forward by `SKIP_DEFER_DAYS` (1 day). Touches ONLY `due_date` — no progression event fires, no usage event recorded, no level/interval/ease/repetitions change. The skipped card disappears from `/srs/due` until tomorrow.

On answer submit (`handleAnswer` → `submitReviewAnswer` → `routers/srs.py:38` → `review_service.submit_answer` → `progression_service.apply_progression("passive_review_correct" | "passive_review_incorrect")`):
- Correct: passive SM-2 advance, interval ×= ease, ease += 0.05 (cap 3.0), reps += 1. **No level/status change** — the rule sets only `passive_srs`. So passively reviewing correctly does **not** increment `passive_level`. The user's progress dots in `WordStatusPicker` ("Understood" row) don't grow from SRS reviews.

✅ **HOLE 15 (RESOLVED 2026-05-18).** `passive_review_correct` now has `passive_delta=1` — consistent with `transcript_clicked` and `free_chat_matched`. The "Understood" dots grow from successful reviews too.

---

## Step 6 — Active production paths

Three ways to get active credit (`active_delta` and/or `active_srs="correct"`):
1. **Guided chat** target_used + target_counted → `guided_counted` rule (active_delta=1, active_srs=correct).
2. **Free chat** with `language_detected == 'de'` → `free_chat_used_correctly` (active_delta=1, active_srs=correct). Matched server-side by `chat_service.match_learning_words`.
3. **SRS active review correct** → `active_review_correct` (active_delta=1, active_srs=correct).
4. **Explicit "Known" click** → `status_marked_known` (active_delta=1, active_srs=correct).

Holes:

🕳 **HOLE 16 (chicken-and-egg for active SRS).** As noted in Hole 11, you can't get an active SRS card without first producing the word. Guided chat closes this: `guided_chat_service.get_next_target` ([guided_chat_service.py:17](../youglish-app/backend/services/guided_chat_service.py)) Priority 2 picks a `learning` word with no active card. That's the only built-in path from "learning" to active production for words that never appear in a free chat.

✅ **HOLE 17 (RESOLVED 2026-05-19).** `get_next_target` now considers `phrase_table` at all three priority tiers (due active card, learning without active card, random fallback). Grammar rules remain out of scope here — they're passive-only and don't have a "production" target meaning. The polymorphic return shape `{item_id, item_type, word, lemma}` is unchanged.

✅ **HOLE 18 (RESOLVED 2026-05-19).** `chat_service.match_learning_words` now delegates phrase detection to `matcher_service.match_sentence_with_ids` (spaCy-based extractor handles inflection, separable verbs, reflexives) and returns polymorphic matches the existing free_chat progression handles unchanged.

🕳 **HOLE 19 (language detection blind to per-message context).** `llm_service.evaluate_and_reply` returns one `language_detected` per turn. If the user types `"Yesterday I bought Brot at the bakery"`, the LLM has to choose "en" or "mixed" — if it picks "en" the matched German word `Brot` gets no credit at all. If "mixed", credit goes through `free_chat_mixed_lang` (passive_delta=1, no active). That latter is reasonable but depends entirely on the LLM's classification of an ambiguous sentence.

🕳 **HOLE 20 (free chat language is hardcoded `'de'`).** `chat.py:175` calls `match_learning_words(pool, user_id, body.content, "de")`. So free chat in any other language gives no credit. The whole free-chat progression assumes the user is practising German.

---

## Step 7 — Active SRS review

Same `SRSReviewPage` component. Direction badge says "Production", question changes to "Can you use this naturally in a sentence?". On reveal, an extra row shows `Target: <German word>` ([SRSReviewPage.tsx:240](../youglish-app/frontend/src/components/SRSReviewPage.tsx)).

🕳 **HOLE 21 (active review does not test production).** Just like Hole 12, the card shows the German word as the prompt. The user is asked self-report whether they could produce it. No translation or cue prompt, no input field, no LLM-judged sentence. The whole "active" track is currently self-graded recognition.

Suggested fix: pivot active reviews to use `llm_service.evaluate_and_reply` (the guided-chat eval) on a one-shot user input field. Or at minimum show the English translation as the prompt and the German as the reveal.

🕳 **HOLE 22 (no active-direction display_text resolution).** The card payload doesn't include a translation field. The schema has no place for it. Adding production-style review requires schema or LLM-cache work first.

---

## Step 8 — Reading-selection branch (parallel SRS)

Reading mode has its **own** SRS schedule on `reading_selections.next_review_at` (added by migration 010 — note: the migration filename says `reading_review` but it actually adds two columns to `reading_selections`, no separate table).

Flow:
1. User selects multi-word span → `POST /api/v1/books/{doc_id}/selections` → `reading_service.save_selection`.
2. `reading.py:156` calls `find_catalog_item` then `apply_progression(..., "status_marked_learning")` — pulls the unit into the main progression too.
3. `GET /api/v1/reading/selections/due` returns selections with `next_review_at <= NOW()`.
4. `POST /api/v1/reading/selections/{id}/review` updates the reading SRS *and* fires `passive_review_correct|incorrect` into main progression.

🕳 **HOLE 23 (double SRS schedule — accepted, not closed).** Two schedules still exist: `srs_cards.passive` (SM-2, interval × ease) and `reading_selections.next_review_at` (fixed `[1,2,4,7,14,30]` days). After #5 (2026-05-20) the reading review UI exists and posts review outcomes that DO mirror onto the catalog SRS card via `apply_progression`, but each side keeps its own schedule — they diverge after the first review. The UX policy chose to live with this: the reading queue is book-context-rich, the main SRS queue is vocab-only; the same word can be due in both queues and that's fine because each surface answers a different question. Reconciliation (UUID-vs-SERIAL PK bridge, or dropping one side) is deferred to a separate card if duplication starts confusing users.

✅ **HOLE 24 (RESOLVED 2026-05-20).** `routers/reading.py:review_selection` now fires `apply_progression(..., "status_marked_known", status_override="known")` for `mastered` outcomes that match a catalog item (`find_catalog_item` returns a word/phrase). The user_word_knowledge row's status flips to `'known'` atomically inside the standard progression transaction. Policy: reading "Mastered" is manual known *confidence*, NOT active production evidence — `status_marked_known` has `active_delta=0`, `times_used_correctly_delta=0`, `active_srs=None`, so no active mastery is fabricated. Regression-guarded in `test_reading_progression.py` (`test_review_mastered_marks_catalog_item_known`, `test_review_mastered_does_not_inflate_active`, `test_review_mastered_advances_passive_card_via_status_marked_known`, `test_review_mastered_unmatched_succeeds`).

🕳 **HOLE 25 (no frontend for reading review).** `/api/v1/reading/selections/due` exists but there is no `ReadingReviewPage` component in the frontend. The endpoint is dead from a user perspective until UI is built. (The `SelectionReviewPanel` per-book browsing component exists but doesn't drive a session loop.)

---

## Step 9 — Mastery and beyond

A word is "mastered" by reaching `status='known'`, which happens when:
- user clicks Known, or
- `active_level ≥ ACTIVE_MASTERY_THRESHOLD` (3 by default, configurable via `users.settings.active_reps_for_known`).

Once known:
- `review_service.get_due_cards` filters it out (`uwk.status != 'known'`). Cards stop showing up.
- Recommendation engine de-prioritises it (priority signals do not reward `known` items).
- Insight cards skip it (filtered by status).

✅ **HOLE 26 (RESOLVED 2026-05-19).** Manual demotion is now an explicit branch inside `apply_progression`. When `status_override` lowers the prior status (known → learning, known → unknown, or learning → unknown), the additive rule is bypassed and `_apply_demotion` runs:

- **known → learning**: `passive_level := 1`, `active_level := 0`, both SRS cards `reset` (force `due_date = NOW() + 1 day`, `interval_days = 1`, `repetitions = 0`, `ease_factor` preserved on existing cards). The `reset` action is new (defined in `_update_srs`) — it differs from `incorrect` by creating missing cards and by not penalising ease. So a missing active card (e.g. the user reached `known` via the manual confidence click only) gets created so production practice resumes.
- **known → unknown**: `passive_level := 0`, `active_level := 0`, both SRS cards `incorrect` (existing cards penalised to 1 day, ease −0.15; missing cards remain missing — the documented `action='incorrect'` no-op).
- **learning → unknown**: same as known → unknown.

`times_seen` and `times_used_correctly` are NEVER touched by demotion — they record what happened, not what the user thinks. `_maybe_promote` is NOT called from the demotion branch: the chosen targets (passive ≤ 1, active = 0) can't cross thresholds, and even at threshold=1 the demotion is the user's explicit override.

Transition detection uses a pure helper `_is_demotion(prior_status, new_status)` over the `unknown < learning < known` rank — unit-testable without a DB. Upgrades and same-status calls fall through to the existing additive path (unchanged: `unknown → learning` still applies `status_marked_learning` deltas; `learning → known` still preserves levels).

Regression-guarded by 24 new tests in `test_progression.py` (8 unit + 16 integration), covering each transition + grammar_rule guard + post-demotion climb-back-to-known via production events.

🕳 **HOLE 27 (silent forgetting).** There is no scheduled "did the user forget this?" check. Once an item is `known`, no event can autonomously knock it back to `learning`. Mastery is one-way unless the user manually reclassifies.

---

## Step 10 — Notifications about asynchronous work

When a user requests a new channel via `AddContentPage`:
1. `POST /api/v1/content-requests` inserts a row, spawns `python subtitle-scraper/pipeline.py --requests-only` ([content_requests.py:21](../youglish-app/backend/routers/content_requests.py)).
2. Scraper processes; on completion calls `_notify_user(... "channel_done" | "video_done", payload)` ([subtitle-scraper/pipeline.py:382](../subtitle-scraper/pipeline.py)).
3. Frontend `useNotifications` consumes SSE from `/api/v1/notifications/stream`.

✅ **HOLE 28 (RESOLVED 2026-05-19).** Per-row, mark-after-yield ordering. The SSE generator now yields each row first and only runs the `UPDATE ... SET seen = TRUE` AFTER the yield resumes. Disconnect mid-stream leaves un-yielded rows unseen for re-delivery. (Was: batch mark-before-yield.)

Old version for reference:
```
ids = [r["notification_id"] for r in rows]
await conn.execute("UPDATE notification SET seen = TRUE WHERE notification_id = ANY(...)")
for row in rows: yield f"data: {data}\n\n"
```
If the connection drops between UPDATE and yield, the notification is marked delivered but never reaches the browser. The user never sees their channel finished. Fix: yield first, mark seen after the consumer ack — or use Postgres `LISTEN/NOTIFY` instead of polling.

🕳 **HOLE 29 (3-second polling load).** Every connected user runs a `SELECT … FROM notification WHERE seen = FALSE` every 3 seconds even when idle. With N users you get N queries every 3s. Switch to `LISTEN/NOTIFY` (one persistent connection per user, no polling), or back off to 30s when no events.

✅ **HOLE 30 (RESOLVED 2026-05-19).** `_mark_request` now emits a `request_failed` notification (with `{"reason": error}` payload) whenever it sets `status='failed'`. All six failure call sites are covered automatically — they already pass an `error` string.

🕳 **HOLE 31 (notification table grows forever).** No retention policy. After 6 months you have years of `seen=true` rows.

---

## Step 11 — Auth lifecycle holes (orthogonal but affects every step)

- `core/deps.py` catches all `jwt.InvalidTokenError` the same way → 401 with no error type. Frontend can't tell expired from malformed; expiry mid-session manifests as inscrutable failures (and per Hole 9 in TODO, the frontend then silently swallows the 401 in `usePreferences.ts:24`-style catches).
- No frontend fetch wrapper that detects 401 and forces logout/redirect — each `api/*.ts` handles errors independently.

---

## Cross-step holes (data quality)

✅ **HOLE 32 (RESOLVED 2026-05-20, T1.1).** Same fix as Hole 4 above — unique partial index on `(user_id, item_id, item_type, sentence_id, event_day)` enforces per-sentence, per-day idempotency at the DB level.

🕳 **HOLE 33 (no global "last reviewed at" on `user_word_knowledge`).** `srs_cards.last_review` exists per direction, but `user_word_knowledge.last_seen` is updated on every event whether or not it's a real interaction. Mixes "saw in subtitle" with "actively answered SRS". Insights downstream can't tell.

🕳 **HOLE 34 (recommendation `score_by_id` keyed by item_id without item_type).** `recommendation_service.rank_videos` uses `score_by_id: dict[int, float]` but `_fetch_coverage` only fetches `word_to_sentence` (word coverage). Fine today — but if phrases are added to coverage, two items with the same int id and different types will collide. Add `(item_id, item_type)` tuple keys before extending coverage.

---

## Summary — the loop that almost works

What works:
- Discovery → click → passive level grows → auto-promotes to `learning` → passive SRS card created → due dates honored → SM-2 advances → status filters keep the queue tidy.
- Reading saves → catalog map → main-progression `status_marked_learning` (correct integration!).
- Free chat language-detected match → progression. Guided chat per-turn evaluation → progression.

What doesn't, in priority order:
1. **Active review (Hole 21) is fake** — it just shows the German word and asks the user to grade themselves. The entire "Production" side of SRS is currently a self-report dialog, not a test.
2. **Passive review (Hole 12) is also self-report** — same shape problem in the recognition direction.
3. **No path to schedule active practice** for learning words other than entering guided chat manually (Hole 11, 16, 17).
4. **Reading SRS is parallel and uncoordinated** with main SRS (Hole 23, 24, 25).
5. **Notification delivery is unreliable** (Hole 28) and silent on failure (Hole 30).
6. **Transcript-clicked words don't surface in insights** (Hole 5).
7. **Phrases get second-class treatment** in free chat matching, guided chat target selection, and recommendation enrichment (Hole 17, 18; `enrich_items` in recommendation_service has a TODO comment confirming this).
8. **Status-change atomicity** across the two router calls (Hole 6).
9. **Empty `status_marked_unknown` rule** and partial `status_marked_known` (Hole 7, 8).

These are the holes to close before claiming "end-to-end word learning works."
