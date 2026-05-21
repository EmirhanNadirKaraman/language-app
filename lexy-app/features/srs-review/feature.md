# SRS Review Frontend

## Goal

Give the user a lightweight spaced-repetition flashcard review session directly in the app. Due cards are fetched from the server, shown one at a time, and self-assessed. SM-2 scheduling updates happen on each answer so the card resurfaces at the right interval.

## Scope in

- Load up to 30 due cards per session, filtered by language and `due_date <= NOW`
- Item types supported: `word`, `phrase`, `grammar_rule`
- Two review directions: `passive` (recognition: "do you understand this?") and `active` (production: "can you use this naturally?")
- Self-assessment: "I knew it" / "I didn't know it"
- Per-card feedback screen after answering:
  - Green ✓ Correct or orange ✗ Incorrect
  - For active-direction cards: show "Target: {display_text}" so the user can check their answer
  - "Continue →" button advances to the next card
- Session complete screen showing how many cards were reviewed
- Empty state ("Nothing due right now") when no cards are due
- Language selector: user can switch language and reload
- "Reload" button to re-fetch due cards
- "Skip →" to advance past a card without recording an answer

## Scope out

- Audio or pronunciation playback
- Automatic card generation from content
- Hint/hint-level display during review
- Anki or CSV import/export
- Multi-language mixed sessions
- Editing or deleting SRS cards from the review screen
