# Grammar Rules as SRS Items

## Goal

Allow users to add grammar rules to their study queue directly from the PrepView grammar rule panel. A grammar rule then enters the same SRS pipeline as words and phrases: it gets a passive SRS card, appears in the flashcard review queue, and can be promoted to `known` status through the normal progression thresholds.

## Scope in

- "Add to study" button in `GrammarRulePanel` sets `status='learning'` for the grammar rule item via `PUT /api/v1/words/grammar_rule/{rule_id}/status`
- `status_marked_learning` progression event:
  - Creates a passive SRS card for the grammar rule
  - Increments `passive_level` by 1, `times_seen` by 1
- Grammar rules appear in `GET /srs/due` with `display_text = grammar_rule_table.title`
- Grammar rules participate in **passive direction only** (recognition: "do you know this rule?")
- On success: button replaced by "Added to study ✓" confirmation
- On failure: silent; button remains for retry

## Scope out

- Active SRS direction for grammar rules (production of a grammar rule is not semantically defined)
- Auto-adding grammar rules when a linked phrase is studied
- Status badge or progress indicator for grammar rules in the prep view
- Bulk-adding multiple grammar rules at once
