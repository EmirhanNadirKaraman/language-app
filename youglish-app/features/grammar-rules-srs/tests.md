# Grammar Rules as SRS Items — Expected Behavior for Testing

## Happy path

- `PUT /words/grammar_rule/{rule_id}/status` with `{"status": "learning"}` returns an `HTTP 200` with a `WordKnowledgeRead` body containing `item_type='grammar_rule'`, `status='learning'`
- After the PUT, a passive SRS card exists in `srs_cards` with:
  - `item_type = 'grammar_rule'`
  - `direction = 'passive'`
  - `due_date = NOW`
  - `interval_days = 1.0`, `ease_factor = 2.5`, `repetitions = 0`
- After the PUT, `GET /srs/due?language=de` returns a card for the grammar rule
- The returned card has `display_text = grammar_rule_table.title` (e.g. "Separable Verbs (Trennbare Verben)")
- The returned card has `item_type = 'grammar_rule'` and `direction = 'passive'`
- Submitting a correct answer for the grammar rule card advances its passive SRS schedule (SM-2)

## Edge cases

- `PUT` with `{"status": "known"}` → grammar rule is excluded from `GET /srs/due` (status filter)
- `PUT` with `{"status": "unknown"}` → no SRS card created (`status_marked_unknown` has no SRS action), knowledge row exists with status='unknown'
- Calling `PUT` twice with `status='learning'` → idempotent: same knowledge row, no duplicate SRS card
- Grammar rule card appears only for the correct language (a German rule is not returned when querying `language='fr'`)
- An invalid `item_type` path param (e.g. `PUT /words/video/{id}/status`) returns 422

## Non-goals (what the feature should NOT do)

- Must NOT create an active SRS card for grammar rules (`status_marked_learning` only creates passive)
- Must NOT surface grammar rules in `GET /srs/due` for a different language than the rule's `language` column
- Must NOT fail loudly on the frontend when the PUT fails — button stays available for retry
