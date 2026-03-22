# Free Chat → Progression Integration

## Goal

When a user sends a message in a free chat session, automatically detect vocabulary items from their active learning list that appear in the message and advance the appropriate progression tracks. The user does not need to explicitly flag words — exposure credit is awarded server-side based on detected language and token matching.

## Scope in

- Server-side token matching: after each user message, extract alphabetic tokens (lowercased) and match against word_table (surface form OR lemma) for items the user is tracking with status `!= 'known'`
- Language detection determines the event:
  - `language_detected = 'de'` → `free_chat_used_correctly`: both passive and active tracks advance
  - `language_detected = 'mixed'` → `free_chat_mixed_lang`: passive track only
  - `language_detected = 'en'` → no progression event (user was not practicing German)
- Progression events are awaited (primary knowledge-state changes, not fire-and-forget)
- Analytics events are fire-and-forget

## Scope out

- Phrase item matching (only `item_type='word'` is matched)
- Matching against items with status `known` (already mastered)
- LLM-driven token identification (matching is pure regex + DB join, no LLM involvement)
- Non-German free chat sessions (the feature is German-only; `language='de'` is hardcoded in the match call)
