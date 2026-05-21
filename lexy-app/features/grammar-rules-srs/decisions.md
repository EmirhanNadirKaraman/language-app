# Grammar Rules as SRS Items — Decisions

## `item_type='grammar_rule'` is a first-class citizen in the progression system

`user_word_knowledge` and `srs_cards` both store `item_type` as a free-form string. Grammar rules use `item_type='grammar_rule'` and flow through the same `apply_progression()` function as words and phrases. No separate tables or special-cased logic were needed.

## Only passive direction is created

`status_marked_learning` calls `_update_srs(..., direction="passive", action="create")`. No active SRS card is created for grammar rules. This is intentional: "active production" of a grammar rule (as opposed to recognizing and applying it) is not a well-defined self-assessment task. The passive direction ("do you recognize and understand this rule?") is appropriate.

## `display_text` comes from `grammar_rule_table.title` at review time

`review_service.get_due_cards()` resolves display text with a CASE WHEN join. For `item_type='grammar_rule'`, it joins `grammar_rule_table` on `rule_id = item_id AND language = $language`. The title (e.g. "Separable Verbs (Trennbare Verben)") becomes the card face. This means if a rule title is updated, the next review session reflects the new title automatically.

## `status='known'` excludes the rule from the review queue

Grammar rules obey the same `uwk.status != 'known'` filter as words and phrases in `get_due_cards()`. A user who has been auto-promoted past the passive threshold will stop seeing the rule in their review queue.

## "Add to study" is idempotent at the DB level

`PUT /words/grammar_rule/{id}/status` calls `word_service.upsert_word_status()` which does an INSERT...ON CONFLICT UPDATE. Pressing "Add to study" multiple times does not create duplicate knowledge rows or SRS cards (`ON CONFLICT DO NOTHING` on `srs_cards`).

## Button fires `setItemStatus(token, 'grammar_rule', rule.rule_id, 'learning')`

The frontend reuses the generic `setItemStatus` function from `api/words.ts`. No grammar-rule-specific API endpoint is needed — the existing `PUT /{item_type}/{item_id}/status` route handles it via the `Literal["word", "phrase", "grammar_rule"]` path param.

## Failure is silent; button remains for retry

A network or server error during "Add to study" does not surface an error to the user. The `adding` state clears and the button remains clickable. This matches the fire-and-forget UX philosophy used for other lightweight status changes.
