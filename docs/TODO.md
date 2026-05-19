# TODO.md

Bugs and pending work, ordered so that earlier items unblock later items. "Blocks: …" lists downstream work that depends on the fix.

Status legend: 🔴 will fail / data risk · 🟠 correctness / reliability · 🟡 tech debt · 🟢 polish

---

## P0 — Foundational. Do before anything else.

### 0a-1. ✅ SRS payload now carries prompt_text + answer_text — RESOLVED 2026-05-19
Backend half of the SRS-UI rewrite. `review_service.get_due_cards` returns `prompt_text` and `answer_text` for every card. For passive cards, prompt = German display, answer = English gloss. For active cards, swapped. Grammar rules use `title` / `short_explanation` (no LLM). Word + phrase glosses come from `llm_service.translate_item_gloss`, cached permanently. Hole 0a's audit test now passes (renamed to a regression guard).

### 0a-2. ✅ Frontend SRS review UI rewrite — RESOLVED 2026-05-19
Hole 0a closed entirely. Changes:
  - **New endpoint** `POST /api/v1/srs/review/{card_id}/produce` with body `{answer: str}` → response `{card_id, correct, expected, submitted, feedback}`. Validates ownership + that the card is active; rejects passive (400 passive_card) and grammar_rule (400 grammar_rule). Routes through normal `apply_progression` so SM-2 advances the same way as self-graded answers.
  - **New `llm_service.evaluate_production`** with tool_use schema returning `{correct, feedback, corrected_form}`. Not cached (high-cardinality user input). MOCK_LLM-aware.
  - **Fast path** in `review_service.submit_production_answer`: normalized exact match skips the LLM entirely.
  - **Frontend `SRSReviewPage`** now uses `prompt_text` as the front and `answer_text` on the back. Passive direction unchanged (self-graded). Active direction shows a text input + "Submit" button + "I don't know" button. **Self-grade is no longer exposed for active cards.** Feedback panel shows the canonical target, what the user typed, and the LLM's verdict.
  - **Frontend types**: `SRSReviewCard` extended with `prompt_text` + `answer_text`; new `SRSProductionResult`. `api/srs.ts` gained `submitProductionAnswer`.

Known limitations: production correctness check evaluates only "did the user produce the target item correctly" — not full sentence grammar correction. Inflection tolerance comes from the LLM's judgement (mock mode does substring match).

### ~0a. 🔴 Active SRS review doesn't actually test production~ — superseded
The original #0a is now split into the two items above. The first half (backend payload) ships. The UI rewrite (#0a-2) is the next leg.

Original problem statement preserved below for context:
**File:** `youglish-app/frontend/src/components/SRSReviewPage.tsx:272–367`
**Problem:** Both passive and active cards display the German word as the prompt. The "reveal" for an active card shows the same German word again. The user is asked "Can you use this naturally in a sentence?" and self-grades. There is no production test (no input field, no LLM evaluation, no translation cue) and no recognition test (no hidden gloss). The entire SRS loop is currently a self-report dialog.
**Fix (active):** show the English translation (or example sentence with the target redacted) as the prompt; expose a text input; route the answer through `llm_service.guided_evaluate` (or a dedicated `srs_evaluate_production`); use the eval result to drive correct/incorrect.
**Fix (passive):** show the English gloss as the prompt, German as the reveal — closer to a traditional Anki front/back card.
**Fix (data):** `srs_cards` rows and the `/srs/due` payload need a `prompt_text` (English gloss) field — currently the schema only carries `display_text` (German). Add via `word_table.gloss_en` or a per-item LLM-cache translation lookup.
**Blocks:** literally everything downstream of "user learns a word." Today the entire SRS UI is a self-grading checkbox.

### 0b. ✅ Active SRS card creation on status_marked_learning — RESOLVED 2026-05-19
`_RULES["status_marked_learning"]` ships with both `passive_srs="create"` and `active_srs="create"`. Marking a word "learning" now schedules BOTH directions. The active card is created at `interval_days=1.0, reps=0` (same defaults as the passive card — the design note about "a few days out" was dropped; `_update_srs` schedules at NOW() and the SRS due-feed handles ordering by `due_date` not by passive-vs-active class). Active production credit is gated: `active_delta=0`, `times_used_correctly_delta=0` — creating a card is exposure, not evidence. Re-marking is idempotent (`INSERT … ON CONFLICT (user_id, item_id, item_type, direction) DO NOTHING`). Regression-guarded in `test_progression.py`:
  - `test_status_marked_learning_creates_active_card`
  - `test_status_marked_learning_does_not_increment_active_level`
  - `test_status_marked_learning_does_not_increment_times_used_correctly`
  - `test_status_marked_learning_does_not_duplicate_cards`

### 1. ✅ Dead `srs_service.py` endpoints — RESOLVED 2026-05-19
File `services/srs_service.py` deleted along with the three legacy router endpoints (`POST /check-answer`, `/magic-sentences`, `/cloze-questions`) and the six Pydantic models that only those endpoints used (`CheckAnswerRequest`, `MagicSentencesRequest`, `SentenceResult`, `MagicSentencesResponse`, `ClozeQuestionsRequest`, `ClozeQuestionResult`). Pre-deletion grep across backend + frontend confirmed zero call sites. The `/api/v1/srs/*` namespace now only exposes the real endpoints (`/due`, `/review/{card_id}`).

### 2. ✅ Atomicity gap in `routers/words.py` status update — RESOLVED 2026-05-19
Implemented Approach A: `progression_service.apply_progression` gained a keyword-only `status_override: str | None = None` parameter. When provided, the status flip happens inside the existing transaction alongside level deltas, SRS card writes, and auto-promotion. The router now makes a single `apply_progression(..., status_override=body.status)` call. `word_service.upsert_word_status` and its private validation constants were deleted (no other callers). `WordStatusUpdate.status` was tightened to `Literal["unknown","learning","known"]` so Pydantic returns 422 for bad values.

### 3. 🟡 Replace `os.chdir()` import hacks (downgraded: module-level, not per-request)
**Files:** `youglish-app/backend/services/matcher_service.py:22–35`, `subtitle-scraper/pipeline.py:24–30`
**Problem:** Both mutate process-global `os.getcwd()` + `sys.path` to load `phrase_finder.py`. The mutation is **module-level** (runs once on import) and `try/finally` restores both, so concurrent-request impact is minimal. Still ugly: any future import-time exception inside `phrase_finder` could land the process with the wrong cwd if `finally` doesn't fully execute, and the pattern blocks moving `phrase_finder.py` somewhere sensible.
**Fix:** `importlib.util.spec_from_file_location("phrase_finder", str(_PROJECT_ROOT / "subtitle-scraper" / "phrase_finder.py"))`. Cleaner: move `phrase_finder.py` to a real package under `src/app/extraction/`.
**Blocks:** restructuring `subtitle-scraper/` directory.

---

## P1 — Correctness gaps that bite as soon as anyone uses the affected feature.

### 4a. ✅ Notification correctness — RESOLVED 2026-05-19
**Files:** `routers/notifications.py` (rewritten), `subtitle-scraper/pipeline.py:_mark_request`

Two correctness bugs closed:
  - **Lost on disconnect** — fixed. The SSE handler now yields each row first and only runs `UPDATE … SET seen = TRUE` AFTER the yield resumes. Disconnect mid-stream → un-yielded rows stay unseen for re-delivery. The fetch+yield loop is extracted into a module-level `_yield_unseen(pool, user_id)` async generator so it's directly testable.
  - **No failure notifications** — fixed. `_mark_request` now emits a `request_failed` notification (`payload={"reason": error}`) whenever it sets `status='failed'`. All six failure call sites get the notification automatically — they already pass an `error` string. No changes needed at call sites.

### 4b. 🟡 Notification transport refactor — NOT YET DONE
Remaining items intentionally deferred:
  - **3s polling regardless of load.** Switch to Postgres `LISTEN/NOTIFY` — writer (`_notify_user`) issues a `NOTIFY user_notifications, payload` after the INSERT; handler does `await conn.add_listener(...)` and blocks until either disconnect or event. Cuts idle DB load by ~99%.
  - **Unbounded growth.** Add periodic job to drop `seen=true AND created_at < NOW() - INTERVAL '30 days'`.
**Blocks nothing user-visible** (correctness is fixed in 4a). Purely a cost/scale concern.

### 5. 🟠 Reading SRS works but has no frontend, and duplicates main SRS schedule
**Files:** `youglish-app/backend/services/reading_service.py`, `routers/reading.py`, frontend (missing `ReadingReviewPage`)
**Problem (correction):** migration 010 isn't a separate `reading_review` table — it adds `review_count` + `next_review_at` columns to `reading_selections`. Backend IS implemented (`record_review`, `get_due_selections`, `POST /reading/selections/{id}/review`). Two real bugs:
  - **No frontend session UI consumes `GET /api/v1/reading/selections/due`.** The endpoint exists but no page loops through due selections. Only `SelectionReviewPanel` (per-book browsing) is wired.
  - **Two SRS schedules for the same item.** When `find_catalog_item` matches, both `srs_cards.passive` (SM-2 interval) and `reading_selections.next_review_at` (fixed [1,2,4,7,14,30] days) advance independently for the same word. They diverge after the first review. User sees the same word due in two places, neither aware of the other.
  - **`mastered` outcome doesn't mark catalog item as `known`.** `reading_service.record_review("mastered")` clears `next_review_at` but fires no progression event, so `user_word_knowledge.status` stays `learning`.
**Fix:**
  - Add `ReadingReviewPage.tsx` that consumes the existing due endpoint, mirrors `SRSReviewPage` UX, and posts to `/reading/selections/{id}/review`.
  - Decide who owns the schedule: drop the main passive card on save when `find_catalog_item` matches, OR drop the reading-selection schedule and route everything through `srs_cards`. The former is simpler given the UUID vs int PK mismatch.
  - Add `status_marked_known` firing on `record_review("mastered")` when there's a catalog match.
**Blocks:** book reading actually contributing to long-term retention.

### 5a. ✅ Insights filter — RESOLVED 2026-05-18
**File:** `youglish-app/backend/services/usage_events_service.py:59`
Added `'transcript'` to the context IN clause. Subtitle-clicked unknown words now surface in the "Keeps coming up" insight card. Regression-guarded by tests in both `test_audit_holes.py` and `test_insights.py`.

### 5b. ✅ Free-chat matching + guided target selection now handle phrases — RESOLVED 2026-05-19
**Files:** `chat_service.match_learning_words`, `guided_chat_service.get_next_target`, `matcher_service.match_sentence` (fix)

Implemented Path A (reuse existing phrase_finder). Three pieces:
  1. **Matcher fix** — `matcher_service.match_sentence` now does `nlp(sentence)` before passing to `extract_german_logic`. Lands 5 long-broken `test_matcher` tests green as a bonus. Pre-existing failure count drops from 8 → 3.
  2. **Free chat** — `match_learning_words` calls `matcher_service.match_sentence_with_ids` and intersects matched `phrase_id`s with `user_word_knowledge` rows where `item_type='phrase'` and `status != 'known'`. Returned alongside word matches in the same polymorphic shape; `routers/chat.py` iterates unchanged.
  3. **Guided target** — `get_next_target` rewritten so each of the three priority tiers considers both words and phrases (LEFT JOIN to word_table + phrase_table with item_type-aware CASE; Priority 3 UNION ALL over both catalogs).

`get_target_by_id` already supported phrases — untouched.

### 5c. ✅ Unified enrichment dispatcher — RESOLVED 2026-05-19
**Files:** `services/grammar_service.py`, `services/recommendation_service.py`, `services/insights_service.py`

Three pieces:
  1. **New** `grammar_service.enrich_grammar_rules(pool, user_id, rule_ids, language)` — joins `grammar_rule_table` + `user_word_knowledge` + `srs_cards` (passive direction). Display = `title`; secondary = `rule_type`.
  2. **New** `recommendation_service.enrich_by_type(pool, user_id, items, language)` — accepts list of `(item_type, item_id)` pairs, buckets by type, fans out via `asyncio.gather` to the three per-type enrichers, returns a dict keyed by `(item_type, item_id)` to prevent collisions across SERIAL primary keys.
  3. **Refactored** `recommend_items` and `insights_service._build_card` to use the dispatcher. The duplicated per-type dispatch is gone; grammar rules now flow through both paths.

`enrich_items` kept its signature (it's the word-only backend of the dispatcher) — docstring updated to point at `enrich_by_type` for mixed-type callers.

### 5d. ✅ Status change rules — RESOLVED 2026-05-18
**File:** `progression_service.py:_RULES`

All three sub-issues closed in this session:
  - **`status_marked_known`**: stopped fabricating active progress. `active_delta=0`, `active_srs=None`, `passive_srs="correct"` only. Active mastery only grows from real production events (`guided_counted`, `free_chat_used_correctly`, `active_review_correct`).
  - **`status_marked_unknown`**: now `passive_srs="incorrect"`, `active_srs="incorrect"`. Resets existing cards via SM-2 incorrect branch (interval=1 day, ease-0.15, reps=0). Never *creates* a missing active card — `_update_srs` line ~333 documents that `action="incorrect"` is a no-op when the card doesn't exist. Levels intentionally untouched.
  - **`passive_review_correct`**: `passive_delta=1` added. A controlled review is at least as strong evidence as a subtitle click. The "Understood" progress dots now grow from successful reviews.

See `progression_service.py:_RULES` docstrings and §5e below for the manual-known backfill question.

### 5e. 🟡 Backfill: pre-2026-05-18 manual-known users have inflated active progress
**Tables:** `user_word_knowledge.active_level`, `user_word_knowledge.times_used_correctly`, `srs_cards` (direction='active')
**Problem:** Before #5d's status_marked_known fix, every manual "Known" click bumped `active_level +1`, `times_used_correctly +1`, and either created or advanced the active SRS card via the SM-2 correct branch. Users who frontloaded their vocab by marking things known therefore have phantom active mastery that doesn't reflect actual production.
**Identification:** rows in `word_usage_events` with `context='status_change' AND outcome='correct'` are manual-known events (per `routers/words.py:85` outcome mapping). Counting them per (user_id, item_id) gives the inflation count.
**Possible backfill (manual, do not auto-run):**
```sql
-- Compute inflation
WITH inflation AS (
  SELECT user_id, item_id, item_type, COUNT(*) AS n
    FROM word_usage_events
   WHERE context = 'status_change' AND outcome = 'correct'
   GROUP BY user_id, item_id, item_type
)
-- Apply (review carefully before running)
UPDATE user_word_knowledge uwk SET
    active_level         = GREATEST(uwk.active_level         - i.n, 0),
    times_used_correctly = GREATEST(uwk.times_used_correctly - i.n, 0)
  FROM inflation i
 WHERE uwk.user_id   = i.user_id
   AND uwk.item_id   = i.item_id
   AND uwk.item_type = i.item_type;
-- Active SRS cards: hard to compute precise reset (a card may also have had real
-- production advances mixed in). Safest is to leave existing cards alone; the
-- status='known' filter excludes them from /srs/due anyway.
```
**Recommendation:** ship forward-only. Inflation is small per user (1 per known click) and isn't load-bearing — `status='known'` is the field that drives downstream filtering. Backfill only if analytics depending on `active_level` shows skew.

### 6. 🟠 `users.settings` JSONB hides channel/genre preferences
**File:** `youglish-app/backend/services/settings_service.py`
**Problem:** Memory entry `project_db_migration_todo.md` flags two remaining JSON-in-DB problems — channel preferences are one. Filtering recommendations by followed channels means JSON queries on every call.
**Fix:** Promote `followed_channels`, `followed_genres`, `excluded_categories` into proper join tables (`user_followed_channel`, `user_followed_genre`). Migrate existing JSON rows. Keep `settings` JSONB for genuinely freeform prefs (colour scheme overrides, etc.).
**Blocks:** efficient recommendation filtering, audit/admin views on what users follow.

### 7. 🟠 Channel flat files vs. DB
**Files:** `subtitle-scraper/channels.json`, `merged_channels.json`, `subscribed_channels.txt`, `seed_channels.py`, `pipeline.py`
**Problem:** Both flat files and `channel` table coexist. New channels added today may go to either depending on which path is touched.
**Fix:**
1. Run `seed_channels.py --dry-run` then for real to confirm DB has everything.
2. `git rm` the three flat files.
3. Make `pipeline.py:load_channels()` DB-only (remove file fallbacks).
4. Add `subtitle-scraper/add_channel.py` CLI or wire it into the existing `content-requests` flow.
**Blocks:** any "manage channels via UI" feature, multi-machine deploys.

### 8. ✅ books.py LLM repair exception specificity — RESOLVED 2026-05-19
`routers/books.py:359` (batch repair loop) now catches `(anthropic.APIError, asyncpg.PostgresError)` as the expected failure mode (logged at WARNING). A second narrower `except Exception:` block remains as a defensive top-level guard so a bug in `repair_block_by_id` doesn't lose all already-repaired blocks in the batch — that one is logged via `logger.exception()` to capture the full trace.

### 8b. (was original problem statement)
**File:** `youglish-app/backend/routers/books.py:352–354`
**Problem:** `except Exception` catches logic bugs alongside transient LLM errors. Counts them all as "errors" but doesn't surface anything actionable.
**Fix:** Catch specific exceptions (`anthropic.APIError`, `anthropic.RateLimitError`, `asyncpg.PostgresError`). Re-raise on logic errors. Keep retry/skip for the LLM/network class.
**Blocks:** debugging book-import failures, useful telemetry on LLM error rates.

### 9. ✅ Preference-load error surfacing — RESOLVED 2026-05-19
`api/settings.ts` migrated to use `assertOkJson` from `_http.ts`, so 401s flow into the shared auth:expired handler. `usePreferences` gained an `error: string \| null` field; on failure it keeps the in-flight `prefs` instead of resetting to defaults. 4 new Vitest tests lock the contract.

### 9b. (was original #9 problem statement, kept for context)
**File:** `youglish-app/frontend/src/hooks/usePreferences.ts:24` and similar `.catch(() => {})` patterns across hooks
**Problem:** If `getPreferences` fails (auth expired, server down), the UI sees empty defaults silently. Dark mode resets, channel filters disappear. User assumes their settings were lost.
**Fix:** Distinguish "not authenticated" from real errors. Bubble real errors to a top-level error toast. Don't reset preferences state on failure — keep last-known.
**Blocks:** "user trust" — even a single mysterious settings reset trains users to mistrust the app.

### 10. ✅ `useSearch` language hardcode — RESOLVED 2026-05-19
`useSearch` now accepts `language: string = 'de'` as a parameter. `HomePage` reads `recLanguage` from the outlet context and passes `recLanguage || 'de'` in. When the user changes their recommendation language in Settings, search results follow.

---

## P2 — Production-readiness. Block deploys, not local dev.

### 11. ✅ CORS env-driven — RESOLVED 2026-05-19
`backend/main.py` now reads `CORS_ORIGINS` env var (comma-separated, whitespace-tolerant, empty entries dropped, falls back to `http://localhost:5173` when unset). `.env.example` documents the variable. Verified by `tests/test_deploy_readiness.py` (parser unit tests + middleware integration tests).

### 12. ✅ LLM rate limiting — RESOLVED 2026-05-19
In-memory sliding-window limiter in `services/rate_limiter.py`. 30 req/min, 400 req/hour per user. Wired via `core/deps.rate_limit_llm` into 10 LLM-backed routes (SRS production, chat sessions/messages/complete/guided, reading translate/explain, insights prep/examples/grammar, book llm-repair single + batch). `GET /api/v1/srs/due` intentionally exempt (cached glosses). Frontend `_http.ts` maps 429 detail to friendly messages.

Known limit: in-memory, per-process. Multi-worker deployments need Redis. Documented in the module docstring; `check_and_record` signature shaped to allow a Redis backend swap behind the same call site.

### 13. ✅ JWT expired vs malformed — RESOLVED 2026-05-19
`core/deps.py` now catches `jwt.ExpiredSignatureError` first → 401 with `detail="token_expired"` and `WWW-Authenticate: Bearer error="invalid_token", error_description="token expired"` header. Other `jwt.InvalidTokenError` cases keep the generic `detail="Invalid token"` response. Frontend `_http.ts` reacts to the distinguished detail by dispatching `auth:expired` with `reason="expired"` vs `"unauthorized"`.

### 14. ✅ Global frontend 401 handler — RESOLVED 2026-05-19
New `frontend/src/api/_http.ts` exports a shared `assertOk(res)` that on 401 clears `auth_token` + `auth_email` from localStorage and dispatches a `CustomEvent('auth:expired', { detail: { reason } })` where reason is `'expired'` (when backend sends `detail='token_expired'`) or `'unauthorized'` (generic 401). Layout in `App.tsx` listens for the event and resets React token state + navigates to `/`. `reading.ts` migrated to the shared helper as the first consumer. Other api files can adopt incrementally — even before they do, ANY route that goes through `_http.ts` will trigger the handler.

### 15. 🟡 Print statements instead of logging in scraper/scripts
**Files:** `subtitle-scraper/pipeline.py`, `subtitle-scraper/backfill_*.py`, `scripts/*`, `ilp/optimal_set_finder.py`
**Problem:** `print()` everywhere, no log levels, no structured output, hard to ship to a log aggregator.
**Fix:** Switch to `logging.getLogger(__name__)`. Configure a root logger in each entrypoint. Keep `print()` only for genuinely user-facing CLI output.

### 16. ✅ Lifespan broad excepts — RESOLVED 2026-05-19
`main.py` lifespan's three seed paths (phrase, grammar, content-request resume) now narrow to known types first (`asyncpg.PostgresError`, `FileNotFoundError`, `ImportError`, `OSError` as appropriate per site) and log them as a WARNING with `exc_info=True`. A defensive `except Exception:` remains as a final guard per site — intentionally broad because **startup must NEVER crash on a seed failure** — but now logged via `logger.exception()` so the full trace lands in production logs. Module-level `logger = logging.getLogger(__name__)` added; the per-site `import logging` repeats are gone.

### 16b. (was original problem statement)
**File:** `youglish-app/backend/main.py:39, 50, 64`
**Problem:** Phrase seed / grammar seed / pending-requests resume each `except Exception` and log-and-continue. Intentional ("non-fatal seeding"), but failure modes are invisible in production until someone reads logs.
**Fix:** Keep the broad catch but emit a structured warning (and ideally a notification or metric). Tighten to specific exceptions where the cause is known.

---

## P3 — Architectural debt. Doesn't break things, but every new feature pays the tax.

### 17. 🟡 Root pipeline modules vs `src/app/` duplication
**Files:** root `pipeline.py`, `eligibility.py`, `exposure_counter.py`, `learning_units.py`, `onboarding.py`, `subtitle_*.py`, `utterance_*.py`, `user_knowledge.py`, `word_knowledge.py` — and their twins under `src/app/`
**Problem:** Two copies of essentially the same logic, in different shapes. Pipeline tests run against root; `src/app/` is unused. Anyone editing one will forget the other.
**Fix (pick one):**
- (a) Finish the refactor: make `src/app/` the source of truth, change root files to thin `from app.x import *` shims, update `subtitle-scraper/pipeline.py` imports, delete shims after one release.
- (b) Abort the refactor: `git rm -r src/app/`, document root as the home, update `conftest.py` to drop `src` from sys.path.
**Recommendation:** (b). The refactor is not load-bearing and bit-rots while incomplete.
**Blocks:** restructuring pipeline modules without 2x the churn.

### 18. 🟡 Hardcoded language config in scraper
**File:** `subtitle-scraper/pipeline.py:36–60` (`LANG_MODEL_MAP`, `LANG_TRANSCRIPT_CODES`, `NO_MORPH_LANGS`)
**Problem:** Adding a new language requires editing three dicts + installing a spaCy model + restarting the scraper.
**Fix:** Move to a `language_config` table (or a YAML file checked into the repo): `(code, spacy_model, transcript_codes[], has_morphology, active)`. Load on scraper start.

### 19. 🟡 Phrase extraction is German-only
**File:** `subtitle-scraper/phrase_finder.py`, called from `subtitle-scraper/pipeline.py:376`
**Problem:** `extract_german_logic(doc)` is hard-wired. Any non-German content gets no phrases extracted.
**Fix:** Add `extract_phrases(doc, language)` dispatcher. Even no-op stubs for other languages would let the pipeline run cleanly.
**Blocks:** opening the app to a second language.

### 20. ✅ Dark mode theme system — RESOLVED 2026-05-19
**What landed**

CSS variable tokens declared in `src/index.css` on `:root` (light) with a `[data-theme="dark"]` block that overrides them. `App.tsx` Layout writes `document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'` on every prefs change. `SettingsPanel`'s dark-mode toggle also writes the attribute immediately (no 600ms save round-trip wait).

**Token set (in `index.css`):**
```
--color-bg / -surface / -surface-muted / -surface-sunken / -input-bg
--color-text / -text-strong / -text-muted / -text-subtle
--color-border / -border-accent / -border-subtle / -input-border
--color-primary / -primary-text / -primary-soft / -primary-on-soft
--color-success / -success-bg / -success-border
--color-warning / -warning-bg / -warning-border
--color-danger / -danger-bg / -danger-border
--shadow-card
```

Word-status colors (known/learning/unknown) stay user-configurable via `prefs.*_word_color` — explicitly out of the theme system.

**Component refactor (88 of the 104 audit-counted ternaries removed; 5 remain, all driving the `data-theme` attribute itself).**

| Component | Before → After |
|---|---|
| `NotificationToast.tsx` | dropped `darkMode` prop; all 4 ternaries → `var(--color-*)` |
| `ContentRequestPage.tsx` | dropped `darkMode` prop; all 10 ternaries → vars |
| `BookLibraryPage.tsx` | dropped `darkMode` prop; converted local `th` theme object to var(--...) strings |
| `BookReaderPage.tsx` | dropped `darkMode` prop; kept local `dk` state for the in-reader Dark/Light toggle; wrapped reader with `<div data-theme={dk ? 'dark' : 'light'}>` so the toggle creates a SCOPED override without touching the rest of the app. All inner ternaries → vars. `navBtnStyle` and `topBtnStyle` helpers no longer take `dk`. |
| `SelectionPanel.tsx` | dropped `dk` prop (forwarded from BookReaderPage); all 20 ternaries → vars. `llmBtnStyle` helper no longer takes `dk`. |
| `SelectionReviewPanel.tsx` | dropped `dk` prop; all 6 ternaries → vars |
| `SettingsPanel.tsx` | kept `darkMode` LOCAL STATE (drives the checkbox + auto-save), but converted all 27 styling ternaries to vars. Toggle handler now sets `document.documentElement.dataset.theme` immediately so the UI flips without waiting for the save round-trip. Inline `:hover` background flips on suggestion list dropped (not worth porting; can return as a real `:hover` CSS rule later). |
| `App.tsx` | Layout effect: `document.body.style.background` → `document.documentElement.dataset.theme`. NavLink chip + nlReview styles → vars. Main container background/color → vars. HomePage Free Chat / Guided Practice buttons untouched (already light-mode-only; no dark variants). |

**Files NOT touched** (intentionally — no `darkMode` usage):
all other components (`PlayerView`, `SearchBar`, `RecommendationsPanel`, `RecommendationCards`, `InsightsSection`, `PrepView`, `GuidedChatPage`, `MessageInput`, `GrammarRulePanel`, `ReminderBanner`, `FreeChatPage`, `ChatWindow`, `TargetCard`, `TurnFeedbackChip`, `LoginForm`, `SearchBar`, `ResultCard`, `ReadingStatsPanel`, `WordStatusPicker`, `TranscriptPanel`, `SubtitleDisplay`, `PlayerControls`, `YoutubeEmbed`, `SessionSummaryCard`, `ErrorBoundary`, `FollowedChannelsSection`, `PlaylistPanel`, `SRSReviewPage`, `BookReaderPage` sub-components). These were already light-only (no dark variants existed) — converting them to use theme vars would CHANGE behavior in dark mode (currently they stay light-on-light). Future work: audit each, opt-in to var(--color-*) where dark mode should apply.

**Behaviour preserved:**
  - Settings dark-mode toggle still persists via 600ms debounced save.
  - BookReaderPage's local Dark/Light button still works as a per-reader override.
  - Word-status colors still come from `prefs.*_word_color` and are user-customisable.
  - Status pill semantic colors (pending/done/failed in ContentRequestPage, success/warning/danger badges, mistake/recent/freq insight tags) stay fixed across themes.
  - No new theme settings model — `users.settings.dark_mode` JSONB still the single source.

**Tests added** (`src/test/theme.test.tsx`, 4 tests):
1. NotificationToast dismiss button uses `var(--color-text-muted)`.
2. ContentRequestPage container uses `var(--color-surface)` + `var(--color-text)`.
3. ContentRequestPage input uses `var(--color-input-bg)` + `var(--color-input-border)`.
4. SettingsPanel dark-mode toggle flips `document.documentElement.dataset.theme` between `'light'` and `'dark'` (no 600ms wait).

**Validation:** `npx tsc --noEmit` clean. `npx vitest run` → 90/90. `npm run build` clean (414.80 kB JS / 115.97 kB gz, CSS grew 2 kB → 4 kB from the new variable declarations).

**Future work** (out of this scope):
- ~~Convert components currently not touched (light-only across the board) to use the variable set so dark mode is consistent everywhere.~~ **RESOLVED 2026-05-19 in #20b below.**
- Add proper `:hover` / `:focus-visible` styling via CSS classes — inline styles can't express pseudo-classes, which is why some hover behaviour was dropped in this pass.
- Consider syncing `--color-primary` etc. with `prefs.*_word_color` so users can theme their accent palette too.

### 20b. ✅ Dark-mode coverage for remaining light-only components — RESOLVED 2026-05-19
Follow-up pass to #20a. Converts the 22 components called out as still light-only so dark mode is now visually complete across the entire app.

**Components converted to var(--color-*) tokens** (containers, text, borders, inputs, hover/active states):
  - `App.tsx` Layout — main bg/text (already done in #20a; double-checked).
  - `PlayerView.tsx` — outer panel, view-toggle tab bar.
  - `PlayerControls.tsx` — bottom bar + 5 nav buttons (input-border + surface tokens).
  - `SubtitleDisplay.tsx` — single `color: '#1a3a6c'` text → `var(--color-text-strong)`.
  - `TranscriptPanel.tsx` — sentence rows + active sentence highlight + "Loading transcript…" placeholder.
  - `WordStatusPicker.tsx` — picker chrome bg/border/text. Status pills (`#e53935` Unknown / `#fb8c00` Learning / `#43a047` Known) intentionally kept fixed — semantic colors.
  - `SearchBar.tsx` — input chip area, suggestions dropdown, phrase badge.
  - `LoginForm.tsx` — inputs, ghost/outline/primary buttons, close ✕.
  - `ReminderBanner.tsx` — banner bg/border/text use warning tokens.
  - `FreeChatPage.tsx` — outer panel + header bg now uses var(--color-primary) for a real surface in both modes.
  - `ChatWindow.tsx` — user-bubble + assistant-bubble surfaces.
  - `TargetCard.tsx` — header strip uses var(--color-primary-soft).
  - `MessageInput.tsx` — textarea + send button bg/border/text.
  - `RecommendationsPanel.tsx` — container + controls + ReadingUnitsDueCard.
  - `RecommendationCards.tsx` — Item/Video/Sentence card surfaces, secondary text, PrefButton non-active state.
  - `FollowedChannelsSection.tsx` — section header + empty state.
  - `ReadingStatsPanel.tsx` — container + legend chip colors.
  - `InsightsSection.tsx` — primary item button surface, secondary chip surface. Card border + accent kept fixed (semantic: mistake = pink, freq = blue).
  - `PrepView.tsx` — item header chip, grammar-explanation accordion, examples surface, templates surface, linked-grammar-rule chips.
  - `GuidedChatPage.tsx` — outer panel, header (kept semantic warning/success colors for the target-progress state), hint panel, End Session secondary button.
  - `SessionSummaryCard.tsx` — corrective-note highlight strip, feedback row label/text. `TargetBadge` and `QualityPill` semantic palettes kept fixed.
  - `ErrorBoundary.tsx` — fallback panel bg/border/text + Reload button.
  - `PlaylistPanel.tsx` — outer container, BuildView input style, suggestion dropdown, target chips, Generate button, ResultView coverage bar + PlaylistVideoCard surface + Watch button.
  - `SRSReviewPage.tsx` — outer container, language `<select>`, Reload button, progress bar, feedback panel (success/warning surface + Continue button uses `var(--color-primary)`), review card surface, passive/active buttons (use semantic danger/success/primary tokens with surface fallbacks for the disabled state), Skip link.

**Intentionally left unchanged** (semantic colors that must stay recognisable across themes):
  - **Status pills** in `ContentRequestPage.STATUS_STYLES`, `WordStatusPicker` STATUSES, `SessionSummaryCard.TargetBadge` / `QualityPill`, `SelectionReviewPanel` Mastered/Due badges, `RecommendationCards.REASON_STYLES` and reason-tag variants, `InsightsSection` mistake-vs-freq border + accent. These all rely on color to convey meaning quickly (red = bad, green = good, blue = info, orange = warning).
  - **Word-status colors** (known/learning/unknown) — user-configurable via `prefs.*_word_color`. Out of theme system by design.
  - **PrefButton activeColor** (Follow/Like/Dislike on video cards) — passed in by parent at the call site to encode the action's meaning (`#1a237e` follow / `#2e7d32` like / `#c62828` dislike).
  - **YouTube thumbnail backdrops** — `background: '#000'` kept literal so the lazy-loading poster fades in on the same surface in both themes.
  - **LLM-result tints** in `SelectionPanel.llmBtnStyle` — passed-in accent (`#1565c0` translate / `#2e7d32` explain) is the function signature; the wrapping bg now uses `var(--color-surface-muted)` for the disabled state.
  - **SubtitleDisplay highlight `<mark>` background `#fff176`** — search-term highlight; light yellow works on both light and dark text and is recognisable as a highlight.
  - **`ResultCard.tsx`** — dead code (no importers, confirmed in #27g audit). Not converted.

**Tests added** (`src/test/theme.test.tsx`, 4 new tests on top of the existing 4 from #20a):
1. `PlayerControls` button uses `var(--color-surface)` + `var(--color-input-border)`.
2. `LoginForm` primary submit uses `var(--color-primary)` + `var(--color-primary-text)`.
3. `MessageInput` textarea uses `var(--color-input-bg)` + `var(--color-text)`.
4. `ReminderBanner` background uses `var(--color-warning-bg)`.

Existing `TranscriptPanel.test.tsx` updated: `borderLeft` assertion now matches the `var(--color-primary)` literal (jsdom can't compute CSS vars; `toHaveStyle` shorthand resolution fails, so we use `style.borderLeft` + `toContain` directly).

**Validation:** `npx tsc --noEmit` clean. `npx vitest run` → 94/94 (was 90; +4 new). `npm run build` clean (421 kB JS / 116 kB gz, +6 kB from the larger inline-style strings — `var(--color-*)` is longer than `'#ffffff'`).

**Visual caveats:**
- The `:hover` flip on `SearchBar`'s suggestion list and `SettingsPanel`'s TagInput dropdown still doesn't dark-mode-correctly — both used inline `onMouseEnter`/`onMouseLeave` handlers that referenced `darkMode`. Those were already dropped in #20a; not regressed here. Re-introducing via real CSS `:hover` rules is a future task.
- The `ChatWindow` user bubble was previously `#1a237e` (bright purple-blue) on light mode; in dark mode it now reads from `var(--color-primary)` which resolves to `#7986cb` (a lighter purple). This is intentional — pure `#1a237e` is unreadable as a bubble background on a dark surface. Side effect: the bubble is slightly lighter on a light background than before. If this looks off, change `--color-primary` in the light declaration block.

### 21. 🟡 No memoization / re-render hotspots
**Files:** `usePlayerSentences.ts`, `RecommendationCards.tsx`, `BookReaderPage.tsx`, `SearchBar.tsx`
**Problem:** Sentence parsing, recommendation rendering, and book-page rendering happen on every keystroke / state change.
**Fix:** `useMemo` parsed sentences, `React.memo` card components keyed by `item_id`, debounce search input.

### 22. ✅ Frontend error boundary — RESOLVED 2026-05-19
New `components/ErrorBoundary.tsx`. Wraps `<Outlet />` in `App.tsx` (navbar + Layout chrome stay outside the boundary so the user can navigate away after a route crash). Fallback UI: "Something went wrong." + Reload button (`window.location.reload`). Component-stack logged to `console.error` for now. 3 Vitest cases: passthrough, fallback on throw, Reload click invokes reload.

### 22b. (was original #22 problem statement, kept for context)
**File:** `youglish-app/frontend/src/App.tsx`
**Problem:** A render error in any deep component white-screens the whole app.
**Fix:** Wrap `<Outlet />` (or each route element) in an `ErrorBoundary` that shows a fallback + reload button + sends to backend logging endpoint.

### 23. ✅ settings_service exception specificity — RESOLVED 2026-05-19
`services/settings_service.py:_coerce_settings` (fallback `dict(value)` for unknown DB return types) now catches only `(TypeError, ValueError)` — the actual exceptions `dict()` raises for non-iterable / malformed inputs. Anything else (e.g. real DB or system-level error) bubbles up so it's diagnosable.

### 23b. (was original problem statement)
**File:** `youglish-app/backend/services/settings_service.py:49–54`
**Problem:** Bare `except Exception` after `JSONDecodeError`. Hides DB errors, permission errors, type errors.
**Fix:** Catch only `json.JSONDecodeError` and `asyncpg.PostgresError`. Let everything else propagate.

### 24. 🟡 LLM cache concurrent-miss thundering herd
**File:** `youglish-app/backend/services/llm_cache_service.py:86–97`
**Problem:** If N requests for the same prompt arrive in parallel, all miss the cache and all call Anthropic. `INSERT … ON CONFLICT DO NOTHING` saves storage but not compute.
**Fix:** Use `pg_advisory_lock(hash(cache_key))` around compute-and-insert, OR an in-memory `asyncio.Lock` keyed by `cache_key`. The latter is simpler and good enough for single-process.
**Blocks:** cost predictability during traffic spikes.

### 25. 🟢 Word-status data duplicated across services
**Files:** several services do their own `SELECT … FROM user_word_knowledge WHERE …`
**Problem:** No single `word_service.get_knowledge(user_id, item_id, item_type)`. Refactors are painful.
**Fix:** Extract a single accessor and route all reads through it.

---

## P4 — Polish. Pleasant to do, not load-bearing.

### 26. 🟢 Accessibility
- Add `aria-label`, `role`, keyboard navigation on WordStatusPicker modal, SRSReviewPage buttons, SelectionPanel
- Alt text on book thumbnails + YouTube thumbnails
- Focus management when modals open/close

### 27a. ✅ Mobile responsive infrastructure — RESOLVED 2026-05-19
Foundation pieces only — no component restyling yet (#27b–f cover that).
  - `index.html` viewport meta updated to `width=device-width, initial-scale=1, viewport-fit=cover` (the `viewport-fit=cover` is what lets a future Capacitor iOS wrap paint behind the notch).
  - `src/index.css` gains `--bp-sm: 480px`, `--bp-md: 768px`, `--safe-top`, `--safe-bottom` design-token variables, plus `html { -webkit-text-size-adjust: 100% }` and `body { font-size: 16px }` to block iOS Safari's input-focus zoom.
  - New `src/hooks/useViewport.ts` returns `{ isMobile }` driven by `window.matchMedia('(max-width: 768px)')`. SSR/test-safe (defaults to non-mobile when `matchMedia` is unavailable). Subscribes via `addEventListener('change', ...)` with legacy `addListener` fallback. 5 Vitest tests.
  - `App.tsx` Layout container is the proof-of-concept consumer: tighter side gutters on mobile (12px/8px vs 24px/16px) and `paddingTop: calc(... + var(--safe-top))` so the notch case is wired in.
  - **Caveat for #27b onward:** CSS variables can't be used inside `@media` query conditions. The breakpoint literal `768px` must be duplicated at every `@media (max-width: 768px)` site (and similarly `480px` for `--bp-sm`). The variables exist for JS consumption + design-token reference only.

### 27b. ✅ PlayerView / YoutubeEmbed / SubtitleDisplay / PlayerControls — RESOLVED 2026-05-19
The main video-learning surface now renders correctly on phone:
  - **YoutubeEmbed**: switched from the `paddingTop: 56.25%` ratio hack to `aspectRatio: '16 / 9'` on a `width: 100%` container. Same responsive behaviour, cleaner CSS.
  - **SubtitleDisplay**: replaced `height: 200px` (clipped on mobile / large fonts) with `minHeight: 200px`. Font size went from a fixed `38px` to `clamp(20px, 5vw, 38px)` — fluid scaling, no JS branch needed. Padding also went fluid via `clamp()`. iOS Safari 14.5+ supports both.
  - **PlayerControls**: added `minWidth/minHeight: 44px` belt-and-braces alongside the existing `width/height: 44px` (so a future refactor can't drop the touch target). Outer container gained `flexWrap: 'wrap'` + `gap: 8px` so the sentence counter falls below the buttons on narrow phones instead of overflowing.
  - **PlayerView**: container was already vertical-stack + `width: 100% / maxWidth: 100%` — no change needed.
  - **No prop-drilling**: each component handles its own responsive concern via CSS (`clamp`, `flexWrap`, `aspectRatio`). `useViewport` not used in this stage because CSS sufficed.

### 27c. ✅ TranscriptPanel + WordStatusPicker — RESOLVED 2026-05-19
Main HomePage / video-learning surface is now fully mobile-friendly (PlayerView half = #27b, transcript half = #27c).
  - **TranscriptPanel**: sentence rows now `minHeight: 44px` + `padding: 10px clamp(10px, 3vw, 16px)` (finger-tappable on phone, no horizontal overflow). Font: `clamp(14px, 3.5vw, 16px)`. Added `overflowWrap: anywhere` + `wordBreak: break-word` so long German compound words wrap instead of overflowing.
  - **WordStatusPicker**: all 3 status buttons (Unknown / Learning / Known) gained `minWidth/minHeight: 44px`. Status button row gained `flexWrap: 'wrap'` so all three stay visible on 320px phones instead of overflowing. Close `×` button widened to 44×44 with flex centering. Side padding became `clamp(10px, 3vw, 16px)`.
  - **No prop drilling**, no `useViewport`. Pure CSS (`clamp` + `flexWrap` + `minHeight`).

### 27e. ✅ SRSReviewPage + GuidedChatPage mobile — RESOLVED 2026-05-19
Daily review + chat surfaces are now mobile-safe. Critical iOS guards in place.
  - **SRS active-production input** (`<input>` from #0a-2): `fontSize: 16px` (iOS Safari focus-zoom blocker — non-negotiable), `minHeight: 44px`, `box-sizing: border-box`.
  - **All SRS review buttons** (passive grade pair, active I-don't-know + Submit, Continue, Reload, Language select): `minHeight: 44px`, font bumped from 13px to 14px for legibility, `touchAction: 'manipulation'`. Button rows gain `flexWrap: 'wrap'` with `flex: 1 1 140px` so they fit one row when there's space and stack on truly narrow phones.
  - **SRS card containers**: padding fluid via `clamp(20px, 5vw, 28px) clamp(16px, 5vw, 24px)`. Prompt text uses `clamp(24px, 7vw, 32px)`. Answer / feedback containers gain `overflowWrap: anywhere` + `wordBreak: break-word` so long German wraps cleanly.
  - **SRS outer container**: `padding: clamp(12px, 4vw, 20px)`.
  - **SRS close `×`**: 44×44 flex-centered button (was bare unstyled text).
  - **MessageInput textarea** (chat input): `fontSize: 16px` (iOS guard), `minWidth: 0` so it doesn't push the Send button out on narrow screens.
  - **MessageInput Send button**: `minHeight: 44px`, `minWidth: 64px`, `touchAction: 'manipulation'`.
  - **GuidedChat header close**: 44×44 flex-centered.
  - **End Session / Need-a-hint buttons** in GuidedChat: `minHeight: 36px` (secondary actions, kept smaller than 44 to not visually dominate the target/hint row but still tappable). Font bumped from 11px to 13px.
  - **HintPanel inline link button**: `minHeight: 32px`, font 13px.
  - **Behaviour unchanged**: passive reveal/self-grade, active produce + I-don't-know, hint level state machine, summary card, language switch.

### 27d. ✅ BookReaderPage mobile — RESOLVED 2026-05-19
PDF/book reading surface now usable on phone.
  - **Content area** switches from horizontal flex (`1 1 55%` + `0 0 42%`) to vertical column on mobile via `useViewport()`. Right-side panels (Scan image, SelectionPanel, SelectionReviewPanel) and the Edit-mode annotation+image split all stack below the reader instead of fighting for ≤375px of width. Each stacked panel gets `maxHeight: 50vh` + `overflowY: auto` so the reader stays the primary content.
  - **Page input** (page-number entry) bumped from `fontSize: 13px` to `fontSize: 16px` — iOS Safari focus-zoom blocker. Also gained `minHeight: 44px`.
  - **Page nav arrows** (◀ / ▶ via `navBtnStyle`): now 44×44 with `touchAction: 'manipulation'` and font 14→16px.
  - **Top-bar chrome buttons** (`topBtnStyle` — Saved, Edit, Dark/Light, Scan): bumped to `minHeight: 36px`, padding `5px 12px` → `7px 12px`, font 12→13px. Top bar still flex-wraps as before.
  - **Back button**: `minHeight: 44px`.
  - **Mode toggle** (Page / Sentence): `minHeight: 36px`, padding bumped, font 12→13px.
  - **Reader padding**: fixed `24px` → `clamp(12px, 4vw, 24px)` so 320px viewports keep more content.
  - **Top-bar side padding**: fixed `16px` → `clamp(10px, 3vw, 16px)`.
  - **Behaviour preserved**: token selection / Page-vs-Sentence mode / scan image overlay / Edit annotation split / SelectionPanel / SelectionReviewPanel / page navigation — all unchanged.

### 27f. ✅ ContentRequestPage + SettingsPanel mobile — RESOLVED 2026-05-19
Last non-reader mobile surfaces are now phone-safe.

**ContentRequestPage:**
  - Container padding fixed `24px` → `clamp(16px, 4vw, 24px)`. Container gains `overflowWrap: anywhere` so long channel IDs / errors wrap inside the 640px max-width.
  - Content-ID input: `fontSize 14px → 16px` (iOS focus-zoom guard), `minHeight: 44px`, padding bumped to `10px 12px`.
  - Channel/Video toggle row: `flexWrap: wrap` added. Each button `minHeight: 36px`, padding `7px 20px → 8px 20px`, font 13→14px, `touchAction: manipulation`.
  - Submit button: `minHeight: 44px`, font 14px (unchanged), padding 9→10px vertical.
  - Close `×`: 44×44 flex-centered, `aria-label="Close"`.
  - Request-list row content column: `flex: '1 1 200px'` so type + ID + error wrap to a new line on narrow phones instead of overflowing the status pill.

**SettingsPanel:**
  - Container padding fixed `20px 24px` → `clamp(14px, 4vw, 24px)`.
  - Shared `input` style helper (used by both reps number inputs): `fontSize 14px → 16px` (iOS guard), `minHeight: 44px`, padding bumped.
  - TagInput text field: `fontSize 13px → 16px` (iOS guard).
  - TagInput preset chip buttons: `minHeight: 32px`, padding `3px 10px → 6px 12px`, font 12→13px.
  - Color picker inputs: height `36px → 44px` (44×44).
  - Close `×`: 44×44 flex-centered.

**Behaviour preserved**: submit flow, debounced auto-save, tag add/remove, dark mode toggle, language/genre/channel preferences, color updates.

### 27g. ✅ Global mobile touch-target + input audit — RESOLVED 2026-05-19
Closing pass over every interactive surface that #27a–f didn't touch.

**Inputs/selects/textareas bumped to fontSize: 16px (iOS focus-zoom guard):**
  - `LoginForm.tsx`: email + password inputs (13 → 16px, +44px minHeight)
  - `PlaylistPanel.tsx`: BuildView shared `inputStyle` (13 → 16px, +44px minHeight; covers language select, word search, max-videos number input)
  - `BookLibraryPage.tsx`: title input + language select (13 → 16px, +44px minHeight)
  - `RecommendationsPanel.tsx`: language select (13 → 16px, +44px minHeight)
  - `SelectionPanel.tsx`: note textarea (13 → 16px)

**Primary CTAs bumped to minHeight: 44px:**
  - `App.tsx` HomePage: Free Chat / Guided Practice buttons
  - `LoginForm.tsx`: Sign-in / Create submit
  - `PlaylistPanel.tsx`: Generate playlist, Add word
  - `BookLibraryPage.tsx`: Upload
  - `PrepView.tsx`: Start Guided Practice
  - `SessionSummaryCard.tsx`: See next recommended item

**Close × buttons bumped to 44×44:**
  - `LoginForm.tsx` cancel
  - `PlaylistPanel.tsx`
  - `BookLibraryPage.tsx`
  - `RecommendationsPanel.tsx`
  - `ReminderBanner.tsx` dismiss
  - `NotificationToast.tsx` dismiss
  - `FreeChatPage.tsx`

**Sidebar close × kept at 36×36 (documented):**
  - `SelectionPanel.tsx` / `SelectionReviewPanel.tsx` — fixed-width 340px sidebars, 44 would crowd header pill + count badge.
  - `GrammarRulePanel.tsx` — inline expansion panel.

**Secondary actions bumped to minHeight: 36px:**
  - `App.tsx` Layout: NavLink chips (top-nav row across every page)
  - `LoginForm.tsx` Sign-in toggle button (outlineBtn)
  - `ReminderBanner.tsx`: "For You →"
  - `RecommendationsPanel.tsx`: Refresh button, Reading Units "Open Books" link
  - `RecommendationCards.tsx`: ActionButton (Watch/Practice/Search/Dismiss/Mark Learning)
  - `BookLibraryPage.tsx`: Read / Delete / Confirm / Cancel
  - `PlaylistPanel.tsx`: Back, Add recommended words, Watch (in video card)
  - `PrepView.tsx`: Back, Generate examples, linked grammar rule chips
  - `SessionSummaryCard.tsx`: Practice again, Back to home
  - `SelectionPanel.tsx`: LLM Translate/Explain (40px in sidebar), Save/Clear (40px in sidebar)
  - `SelectionReviewPanel.tsx`: review chip buttons (Got it / Not quite / ★)
  - `GrammarRulePanel.tsx`: Learn more / Add to study
  - `InsightsSection.tsx`: secondary chip buttons (≥32px)

**Container padding made fluid where wide-margin panels were on small screens:**
  - `PlaylistPanel.tsx`: `16px 20px` → `clamp(14px, 4vw, 20px)`
  - `RecommendationsPanel.tsx`: `16px 20px` → `clamp(14px, 4vw, 20px)`

**Components intentionally left unchanged:**
  - `ChatWindow.tsx`, `TargetCard.tsx`, `TurnFeedbackChip.tsx`, `ReadingStatsPanel.tsx`, `icons.tsx`: display-only, no interactive surfaces.
  - `FollowedChannelsSection.tsx`: relays into `VideoRecommendationCard` (already in `RecommendationCards.tsx`).
  - `ResultCard.tsx`: dead code (no importers — verified via grep). Flagged for removal in a future cleanup pass.
  - `RecommendationCards.tsx` `PrefButton` (Follow/Like/Dislike chips on video cards): kept at ~22px because they render three-up across an already dense 220-280px card. They're discoverability hints; primary watch CTA covers the load-bearing tap.
  - `BookLibraryPage.tsx` Sort chips (`Newest / A→Z / …`): kept at ~22px to avoid pushing the sort row to multiple lines on mobile. They're tertiary controls; users can still tap them, just precisely.

**Other guards added:**
  - All bumped controls have `touchAction: 'manipulation'` to skip iOS Safari's 300ms double-tap-zoom delay.
  - `LoginForm.tsx`: signed-in header row gained `flexWrap: 'wrap'` so long email addresses don't push "Sign out" off-screen.
  - `BookLibraryPage.tsx` Actions column: `flexWrap: 'wrap'` so Confirm/Cancel can drop below the row label on narrow phones.
  - `SessionSummaryCard.tsx` secondary CTA row: `flexWrap: 'wrap'`.

### 27h. ✅ PWA shell (manifest + service worker + offline page) — RESOLVED 2026-05-19
First half of iOS "Add to Home Screen" / Capacitor prep (Path A in #34).

**Files added:**
  - `frontend/public/manifest.webmanifest` — `name`, `short_name: "YouGlish"`, `start_url: /`, `scope: /`, `display: standalone`, `orientation: portrait`, `theme_color: #1a237e`, `background_color: #ffffff`. Icon list references only `/favicon.svg` (the one icon asset that exists). 192×192 / 512×512 / apple-touch-icon are intentionally not referenced — see TODO below.
  - `frontend/public/sw.js` — conservative shell SW. Strategy: precache shell (`/`, `/index.html`, `/manifest.webmanifest`, `/favicon.svg`, `/offline.html`) on install; navigation = network-first → cached shell → offline.html; `/assets/*` = cache-first (Vite filenames are content-hashed so collisions are impossible); `/api/*`, cross-origin, and non-GET = bypassed (lets SSE notifications work, lets POSTs hit network). `skipWaiting` + `clients.claim` so updates roll out fast. `CACHE_VERSION = 'v1'` constant for future invalidation.
  - `frontend/public/offline.html` — minimal standalone page, theme-coloured, 44×44 Retry button.

**Files modified:**
  - `frontend/index.html` — added `<link rel="manifest">`, `<meta name="theme-color">`, `mobile-web-app-capable` / `apple-mobile-web-app-capable` / `apple-mobile-web-app-title="YouGlish"` / `apple-mobile-web-app-status-bar-style="default"`. Title bumped from `frontend` → `YouGlish — Language Learning`. Inline comment documents the missing apple-touch-icon. `viewport-fit=cover` from #27a preserved.
  - `frontend/src/main.tsx` — production-only registration. Guarded by `import.meta.env.PROD && 'serviceWorker' in navigator`. Registers on `window.load` to avoid blocking first paint. Failure logged via `console.warn`, never throws.

**Dev vs prod:** The SW only registers on production bundles, so `npm run dev` is unaffected — Vite's HMR keeps working without a SW intercepting navigations. To test the SW locally: `npm run build && npm run preview`.

**Icons:** ✅ **RESOLVED 2026-05-19** in #27i below. 192×192 + 512×512 PWA icons and 180×180 apple-touch-icon now present.

**Constraints honoured:**
  - No backend changes.
  - No dark-mode refactor.
  - No Capacitor work.
  - `/api/*` and SSE never cached.
  - No missing icon files referenced.

### 27i. ✅ PNG icon set for PWA — RESOLVED 2026-05-19
Closes the PWA stage: Lighthouse PWA audit's "no maskable/png icon" warning is gone, iOS home-screen icon is real (no longer a page screenshot).

**Source asset:** `frontend/public/favicon.svg` — the existing 48×46 stylized purple/blue lightning bolt. Aspect 48:46 ≈ 1.043, close to square; the SVG content already centers the glyph in its viewBox.

**Pipeline (single bash sequence, no committed scripts):**
1. `rsvg-convert -w 820 public/favicon.svg -o /tmp/fav-large.png` → renders the SVG at 820×786 PNG preserving aspect.
2. `sips -p 1024 1024 --padColor FFFFFF /tmp/fav-large.png` → pads to 1024×1024 with solid white background and ~10% safe-zone padding around the glyph (102px horizontal, 119px vertical of white margin around the source render).
3. `sips -z 512 512 / 192 192 / 180 180` → three copies resampled to the target sizes.

**Files added (all binaries, in `frontend/public/`):**
  - `icons/icon-192.png` — 192×192, 16 KB
  - `icons/icon-512.png` — 512×512, 93 KB
  - `apple-touch-icon.png` — 180×180, 14 KB

**Files modified:**
  - `frontend/public/manifest.webmanifest` — `icons[]` now lists the 192 + 512 PNGs first (both `purpose: "any"`) with the SVG kept as a fallback for browsers that prefer vector icons.
  - `frontend/index.html` — added `<link rel="apple-touch-icon" href="/apple-touch-icon.png" />` and removed the inline comment that warned of the missing asset.

**Maskable note:** The icons are NOT marked `purpose: "any maskable"`. The safe zone is ~10% per side which is enough for iOS rounded-corner masking but is below the Android adaptive-icon minimum (18% per side / inner 80% diameter circle). The glyph is also a non-symmetric blob, so adaptive cropping would mangle it. To add maskable support later: regenerate with `sips -p 1280 1280` (≈20% padding on a 1024 source) and add a separate `maskable` icon entry.

**Visual caveats:**
  - Solid white background — looks crisp on light home-screen wallpapers, neutral on dark ones. Not branded.
  - On iOS dark mode the icon still uses the white background (iOS doesn't honour `prefers-color-scheme` for home-screen icons).
  - Glyph is the same purple/blue gradient as the in-app favicon — visually consistent with the loaded app.

### 27. 🟢 Mobile responsiveness (remaining stages)
**Memory note:** explicitly deferred until end-to-end loop works. Don't start until #1–#10 are done.
- `@media` queries for PlayerView, BookReaderPage, modals
- Tighten the 900px max-width container
- Touch-target audit (44px minimum)

### 28. 🟢 Clean `index.css` and `App.css`
**Files:** `youglish-app/frontend/src/index.css`, `App.css`
**Problem:** Mostly commented-out Panda-CSS skeleton and Vite template leftovers.
**Fix:** Delete the dead bits; keep only what's used.

### 29. 🟢 Add an end-to-end test
**Files:** none yet
**Problem:** No test covers register → search → mark word → SRS due → review → progression. Each piece works but the seams aren't verified.
**Fix:** One pytest-asyncio test against a throwaway Postgres + httpx AsyncClient that walks the full loop.

### 30. 🟢 Documentation / ERD
**Files:** none
**Problem:** 25+ migrations, no schema diagram. New contributors guess relationships.
**Fix:** Generate ERD via `eralchemy` or hand-draw. Drop a `docs/SCHEMA.md` linking each table to its owning service.

### 31. 🟢 Two-pass extractor thresholds
**File:** `pdf_text_extraction/config.py:220–311`
**Problem:** Magic numbers (245.0 brightness, 15.0 chars/pt) untested on diverse PDF sources.
**Fix:** Add a small validation harness against a labelled set of "real text", "ghost text", "scanned text" pages.

### 32. ✅ `getStoredEmail` contract — RESOLVED 2026-05-19
Grep confirmed only one caller (`LoginForm.tsx:30`) and it already null-handles via `?? 'Signed in'`. Tightened the function's docstring to make the contract explicit ("Callers MUST handle null — do not assert non-null"). No behaviour change needed.

### 32b. (was original #32 problem statement, kept for context)
**File:** `youglish-app/frontend/src/auth.ts`
**Problem:** `getStoredEmail()` can return `null` but several callers don't check.
**Fix:** Tighten the return type, add a guard.

### 33. 🟢 `pyfile` `pytest.ini` ignores legacy tests
**File:** `conftest.py`
**Problem:** `tests/legacy/*` glob-ignored — no one has looked at them in a while.
**Fix:** Either restore them as canary tests or delete them.

---

## Major future direction

### 34. 📱 iOS mobile support — HIGH PRIORITY FUTURE WORK
Owner-stated goal: the user wants to use this app on their phone. This is **load-bearing** for the project's long-term direction — language learning happens in pockets of time, and the desktop-only constraint blocks the main use case.

Three viable paths, ordered by effort:

**Path A — PWA (smallest lift).** Add `manifest.json`, service worker, install-to-home-screen support. Users add to home screen → app behaves nearly-native. Limitations on iOS Safari: no push notifications (only since iOS 16.4 with caveats), limited background processing, no App Store presence. Good first step regardless of which other path comes later.

**Path B — Capacitor wrapper (recommended).** Wrap the existing React/Vite frontend in a Capacitor native shell, deploy to App Store. Reuses 95%+ of the existing frontend code. Native APIs (camera, push, deep links, biometrics) accessible via Capacitor plugins. Build pipeline: `npm run build` → `npx cap sync ios` → open in Xcode → archive → submit. The right balance of effort vs platform integration.

**Path C — React Native rewrite.** Best performance, fully native UI primitives, but means rewriting every component (no JSX-DOM, no CSS, different navigation). Months of work for incremental UX gain over Capacitor.

**Path D — Native Swift.** Full rewrite. Cleanest iOS UX, biggest implementation cost. Unless we hit a Capacitor ceiling, not worth it.

**Prerequisites before any of A–D:**
- **#27 mobile responsiveness** — the current layout is desktop-only (`maxWidth: '900px'`, fixed font sizes, no media queries). This MUST land first. Even Capacitor / PWA would deploy a broken UI on phone-sized viewports today.
- **#20 dark mode theme system** — the inline `dk ? '#xxx' : '#yyy'` pattern across 35+ components becomes painful when also factoring in iOS dark-mode (which can change at runtime). A CSS-variable-based theme unblocks both.
- **Auth + SSE on mobile** — the SSE notification stream (`/notifications/stream`) holds a long-lived connection. On iOS, that gets killed when the app backgrounds. Either move to APNs push (requires backend + Apple developer account) or accept that notifications only deliver when the app is open. Capacitor's `@capacitor/push-notifications` is the bridge.
- **Backend deployable** — done as of 2026-05-19 (#11 CORS + deploy-readiness bundle). The backend can now run anywhere CORS_ORIGINS allows.

**Concrete recommended sequence when this work begins:**
1. **Mobile responsive web** (#27): media queries, fluid typography, touch targets ≥44px, viewport meta. Makes the existing site usable on phone Safari today.
2. **Theme system** (#20): CSS variables + `[data-theme="dark"]`. Removes the inline-color pattern.
3. **PWA shell** (Path A): manifest, service worker, install prompt. Users can install to home screen immediately.
4. **Capacitor wrap** (Path B): when the PWA experience proves the UX is right, wrap and submit to App Store.
5. **APNs push notifications**: replace the SSE-only fallback for in-app alerts (#4b's LISTEN/NOTIFY also matters here).

**Non-obvious things to plan for early:**
- App Store review prep: privacy policy, account-deletion flow, age rating.
- iOS dark-mode honors system setting at runtime — the `dark_mode` preference would need to flip to "system / light / dark" tristate.
- Token refresh: currently JWT lasts 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES = 60*24*7` in `core/security.py`). On mobile, expiry mid-session needs to be handled gracefully — `_http.ts` already dispatches `auth:expired` (TODO #14), but the LoginForm flow may need rethinking for a native shell.
- Offline mode for review: SRS due cards could be cached client-side so the user can review on the subway. Major feature, scope it separately.

**Status:** Not started. Captured here so it doesn't get lost in conversation context.

---

## Suggested execution order

1. **#0a, #0b** — the SRS review UI is currently a self-grading checkbox. Until it actually tests recall/production, every other progression metric is built on noise. Fix the review UX first, then add `active_srs="create"` to `status_marked_learning` so cards exist to be reviewed.
2. **#1, #5d** — clean up dead `srs_service` endpoints; fix the inconsistent progression rule table. Both touch the state machine; bundle them.
3. **#2, #5a, #5b** — close the silent gaps: atomicity in `routers/words.py:update_status`, transcript clicks into the insights filter, phrases into chat matching + guided target selection.
4. **#4, #5** — make notifications reliable (yield before mark-seen, fire on failure, switch to LISTEN/NOTIFY). Build `ReadingReviewPage` so the reading SRS endpoints have a UI. Resolve the double-schedule issue (#5) by picking one schedule per item.
5. **#6, #7** — get `users.settings` channel prefs and the scraper flat files out of the JSON-in-DB gray zone.
6. **#11, #12, #13, #14** — deploy gates (CORS, rate limit, JWT error shape, frontend 401 handler).
7. **#17, #20** — pay down the structural debt before #27 (mobile) doubles the work.
8. **#3** — opportunistically replace the `os.chdir` import hacks during a `subtitle-scraper/` reorganisation.
9. Everything else as it comes up.
