# Transcript Click / Exposure → Progression Integration

## Goal

Passively record vocabulary exposure when a user clicks a word in the subtitle or transcript panel, feeding it into the passive progression track without interrupting the word picker UI. A click is a weak exposure signal — lighter than an SRS review answer.

## Scope in

- Left-clicking a word in the subtitle/transcript panel triggers a word lookup
- If the word is found in the database (`word_id` present in the response), a click is recorded fire-and-forget via `POST /words/word/{word_id}/transcript-click`
- The click fires the `transcript_clicked` progression event:
  - `passive_level` +1
  - `times_seen` +1
  - Passive SRS card **created** if one does not already exist (but NOT advanced)
- A failure in click recording must not affect the word picker UI

## Scope out

- `transcript_seen` events (automatic exposure for all visible words — deferred; too noisy without playback-timing infrastructure)
- Right-click / status toggle (`toggleWordStatus` — separate code path, does not fire transcript_clicked)
- Recording clicks for words not in the database (absent `word_id` = no click recorded, no error)
- Clicks on phrase items or grammar rules (endpoint is word-only: `/words/word/{word_id}/...`)
