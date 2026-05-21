# Reading → Progression — Decisions

## Two parallel review systems that are loosely coupled

Reading has its own review schedule (`_REVIEW_INTERVALS_DAYS = [1, 2, 4, 7, 14, 30]` days). This is independent of the SM-2 schedule on `srs_cards`. A `got_it` in the reading review fires `passive_review_correct`, which advances the SM-2 passive card's interval according to SM-2 rules. The reading next_review_at and the SRS due_date advance independently according to their own schedules. They are not synchronized.

## `status_marked_learning` is reused for save (no bespoke event)

When a selection is saved and maps to a catalog item, `status_marked_learning` is fired. This event was chosen because it has exactly the right semantics: "I have seen this and want to practice it." It creates a passive SRS card and increments passive_level. Creating a separate `reading_saved` event would add complexity without behavioral benefit.

## `mastered` carries no progression signal

A `mastered` outcome means the reading item exits review rotation permanently. Firing a progression event at that point would be double-counting (the item has already accumulated passive credit through prior `got_it` reviews). The reading and SRS systems reach their own conclusions independently.

## `find_catalog_item` checks word_table first, then phrase_table

Single-word canonicals are looked up in `word_table` first. Only if not found there is `phrase_table` checked. The document's language (from `book_documents`) determines the language filter. Multi-word expressions not present in `phrase_table` return `None` and receive no main-system progression.

## Reading selections are NOT exposed through `/srs/due`

The reading review queue (`GET /reading/selections/due`) and the main SRS queue (`GET /srs/due`) are separate endpoints. Reading selections do not appear as SRS cards in the flashcard review UI. The two systems remain distinct UI experiences even though they share the underlying `srs_cards` table for the catalog items.

## Progression is awaited (not fire-and-forget)

Inside both `save_selection` and `review_selection`, `apply_progression()` is `await`ed. These are primary knowledge-state changes and must not be silently dropped.
