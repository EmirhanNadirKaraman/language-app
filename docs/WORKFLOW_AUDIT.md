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

🕳 **HOLE 1 (UX dead-end).** Clicking a never-scraped word leaves the user with no path forward. There is no "I want to learn this anyway" affordance. The user must paste it into AddContent → wait for the scraper. Most users won't.
🕳 **HOLE 2 (ambiguity).** `LIMIT 1` on `ILIKE` picks an arbitrary row when two `word_table` entries share the surface but differ in POS/lemma (German is full of this: *die Bank* the bench vs. the bank). The user might mark the wrong meaning.

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

🕳 **HOLE 3 (silent state divergence).** `record_transcript_click` is fired from `useWordStatus` with no `await`/no error handling on the frontend side. If the call fails (network, auth), the user sees no feedback; the click counter on the backend silently misses.

🕳 **HOLE 4 (deduplication).** Every click within the same video session increments `passive_level`. A user dragging the seek bar through a sentence can artificially inflate passive_level by clicking the same word 10 times. No per-session debouncing.

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
elif passive_level >= passive_threshold and status == 'unknown': → learning
```

With default `passive_threshold = 5` (line 60) and `transcript_clicked` adding 1 per click, a user must click the same word 5 times before it auto-promotes from unknown → learning. Reasonable.

🕳 **HOLE 9 (no path from `learning` → upper bound on passive).** Once status flips to `learning`, no further auto-promotion is possible without active events. A user could review the word correctly 100 times passively in SRS and the status would stay `learning` forever. The only paths to `known` are:
- explicit user click on "Known",
- `active_level ≥ 3` from `guided_counted` / `free_chat_used_correctly` / `active_review_correct` / `status_marked_known`.

That's by design — production drives mastery, not recognition — but it should be **surfaced in the UI**. Today the user sees passive level 12 with a "learning" badge and no clear next step.

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

🕳 **HOLE 11 (no active card creation path other than success).** `_RULES["transcript_clicked"]` and `status_marked_learning` both do `passive_srs="create"` — only the passive card. Active cards are only created when an event already produced a correct outcome (`guided_counted`, `status_marked_known`, `free_chat_used_correctly`, `active_review_correct`). A user who only marks words as `learning` and never opens guided chat will **never** have an active card scheduled — meaning the SRS review page will only ever test recognition for them. Production gets no scheduled practice.

---

## Step 5 — Passive review loop

Frontend: `SRSReviewPage` ([SRSReviewPage.tsx:27](../youglish-app/frontend/src/components/SRSReviewPage.tsx)).

Card UI shows: direction badge, the **German display text**, a question ("Do you recognise and understand this?"), level dots, and a "Show answer buttons" button followed by "I didn't know it" / "I knew it ✓".

🕳 **HOLE 12 (passive review doesn't actually test recognition).** The card *shows the German word up front*. There is no English translation hidden behind the reveal — the user reads "Auto" and asked themselves "do I recognise this?". Self-report, no recall test. Should show the gloss / example sentence and require the user to surface meaning before pressing "I knew it".

🕳 **HOLE 13 (no dark mode).** Hardcoded colors: `background: '#fafafa'`, `border: '#e8eaf6'`. Renders illegibly in dark mode.

🕳 **HOLE 14 (skip ≠ defer).** "Skip →" advances the local index but doesn't tell the backend. The card stays due. Next session it reappears at the same position. No "see again later" / "bury for today" affordance.

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

🕳 **HOLE 23 (double SRS schedule).** Now there are two schedules: one on `srs_cards.passive` (interval grows by ease factor) and one on `reading_selections` (fixed intervals `[1,2,4,7,14,30]` days). They diverge fast. The user can be due on one and not the other for the same item. Two review interfaces (SRSReviewPage, the future reading-review UI) need to coordinate; currently neither acknowledges the other.

🕳 **HOLE 24 (mastered ≠ known).** `record_review("mastered")` sets `reading_selections.status='mastered'` and clears next_review_at. **No progression event fires.** The catalog item is *not* marked as `known` in `user_word_knowledge`. So the user thinks they're done with the word in the reading view, but it's still scheduled in main SRS. Either fire `status_marked_known` here, or make the UI explicit.

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

🕳 **HOLE 26 (no de-mastery path).** If the user later marks the word back to `learning` or `unknown`, `status_marked_learning` rule has `passive_delta=1, passive_srs='create'`. It does NOT reset `passive_level` or `active_level`. So a word de-mastered from "Known → Learning" still has active_level=10. The SRS card's interval also isn't reset. Reviewing it brings up the original interval. Either reset on this transition, or never auto-promote back to `known` via Hole 8's `active_delta=1` partial logic.

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

🕳 **HOLE 32 (no idempotency on transcript clicks).** Same word, same video, same playback position can be clicked 10×; backend dutifully increments `times_seen` and `passive_level` 10×. Should de-dupe by `(user_id, item_id, sentence_id, day)` or similar.

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
