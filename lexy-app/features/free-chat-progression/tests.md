# Free Chat → Progression — Expected Behavior for Testing

## Happy path

- A user message in German (`language_detected='de'`) that contains a learning-status word triggers `free_chat_used_correctly` for that word:
  - `passive_level` and `active_level` both increment
  - passive SRS card advances (SM-2 correct)
  - active SRS card advances (SM-2 correct)
- A user message in mixed language (`language_detected='mixed'`) triggers `free_chat_mixed_lang`:
  - `passive_level` increments only
  - passive SRS card advances
  - active SRS card is NOT touched
- A word matched by its lemma (not surface form) also triggers progression
- A word appearing multiple times in one message triggers exactly one progression event for that item

## Edge cases

- `language_detected='en'` **with** a target-language learning word present → `free_chat_mixed_lang` (passive credit only; active track untouched). Mixed-language crediting fix, 2026-05-23: a learner who writes "Yesterday I bought Brot" still produced the German word and earns passive credit even though the LLM labelled the whole message English. The message is ALWAYS scanned for target-language items; `language_detected` only gates whether active credit is also granted.
- `language_detected='en'` **with no** target-language learning word present → no `apply_progression` call is made
- A word with status `known` is NOT matched by `match_learning_words()` and receives no progression update
- Empty message (no alphabetic tokens) → `match_learning_words()` returns `[]`, no progression
- Message containing only numbers and punctuation → no matches, no progression
- `match_learning_words()` returns a deduplicated list even when the same word appears multiple times

## `match_learning_words` unit behavior

- Returns `item_id`, `item_type='word'`, and `word` for each match
- Matches on lowercased surface form OR lemma
- Excludes words with `status='known'`
- Returns an empty list for an empty or non-alphabetic text input

## Non-goals (what the feature should NOT do)

- Must NOT match phrase items (only `item_type='word'`)
- Must NOT advance active track for `mixed`-language messages
- Must NOT fire `free_chat_matched` (that event is defined but currently unreachable — tests should confirm it is NOT fired by the chat router)
- Must NOT fail the chat response if a progression or analytics call raises
