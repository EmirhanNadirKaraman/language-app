# youtube_category_test

A small standalone project that uses **yt-dlp** to test whether category
metadata can be reliably extracted from YouTube videos — without the YouTube
Data API and without downloading any media.

---

## What it does

1. Accepts one or more YouTube video URLs or bare video IDs from the command line.
2. Uses the yt-dlp Python library to fetch video metadata only.
3. Inspects the metadata for category-like fields (`categories`, `genre`, `tags`).
4. Prints a structured result for each video showing what was found and how
   reliable the signal is.
5. Prints a summary at the end.

---

## Setup

This project shares the virtual environment at the repo root.

```bash
# From the repo root, activate the shared venv and install/update deps:
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

```bash
# Single video by URL
python main.py https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Single video by ID
python main.py dQw4w9WgXcQ

# Multiple videos at once
python main.py dQw4w9WgXcQ jNQXAC9IVRw

# Show all top-level metadata keys returned by yt-dlp
python main.py --debug dQw4w9WgXcQ

# Dump the full raw metadata JSON
python main.py --dump-raw dQw4w9WgXcQ
```

---

## Example output

```
Checking 1 video(s) with yt-dlp...

Fetching: https://www.youtube.com/watch?v=dQw4w9WgXcQ
------------------------------------------------------------
  Input   : dQw4w9WgXcQ
  Video ID: dQw4w9WgXcQ
  Title   : Rick Astley - Never Gonna Give You Up (Official Music Video)
  URL     : https://www.youtube.com/watch?v=dQw4w9WgXcQ
  Category reliability: STRONG
  Category-like fields found:
    [strong]  categories   = Music
    [strong]  genre        = Music
    [weak]    tags         = rick astley, never gonna give you up, ...
------------------------------------------------------------

============================================================
SUMMARY
============================================================
  Total videos checked     : 1
  Strong category signal   : 1
  Weak signal only         : 0
  No useful fields         : 0
  Failed to fetch          : 0
============================================================
```

---

## Reliability levels

| Level  | Meaning |
|--------|---------|
| strong | `categories` or `genre` was present — these are set by the uploader and are generally trustworthy |
| weak   | Only `tags` were found — user-supplied and noisy |
| none   | No category-like fields returned at all |
| failed | yt-dlp could not fetch metadata (private video, network error, etc.) |

---

## Important disclaimer

**yt-dlp is an unofficial tool.** It works by scraping and reverse-engineering
YouTube's internal APIs. This means:

- The fields it returns (including `categories` and `genre`) may change or
  disappear without notice if YouTube changes its internals.
- Some videos may return `categories` consistently while others do not,
  depending on how the uploader configured them.
- This approach does not require an API key but is also not covered by any
  service-level agreement.
- Always pin a specific yt-dlp version in production and test after upgrades.
