"""
main.py — Test whether yt-dlp can extract the category of a YouTube video.

Usage:
    python main.py <url_or_id> [<url_or_id> ...]
    python main.py --debug <url_or_id>
    python main.py --dump-raw <url_or_id>
"""

import argparse
import json
import re
import sys

try:
    import yt_dlp
except ImportError:
    print("ERROR: yt-dlp is not installed. Run: pip install yt-dlp", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YOUTUBE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')

# Metadata keys that may carry category-like information, in priority order.
CATEGORY_KEYS = [
    ("categories", "strong"),   # list of strings — most reliable
    ("genre",      "strong"),   # single string  — also reliable
    ("tags",       "weak"),     # list of strings — user-supplied, noisy
]


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------

def normalize_input_to_url(raw: str) -> str:
    """
    Accept either a full YouTube URL or a bare 11-char video ID.
    Returns a canonical watch URL.
    """
    raw = raw.strip()
    if YOUTUBE_ID_RE.match(raw):
        return f"https://www.youtube.com/watch?v={raw}"
    return raw


# ---------------------------------------------------------------------------
# yt-dlp extraction
# ---------------------------------------------------------------------------

def extract_info_with_ytdlp(url: str, debug: bool = False) -> dict | None:
    """
    Use the yt-dlp Python API to fetch video metadata without downloading media.

    Returns the info dict on success, None on failure.
    """
    ydl_opts = {
        "skip_download": True,
        "quiet": not debug,
        "no_warnings": not debug,
        "extract_flat": False,   # we need full metadata, not just playlist stubs
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except yt_dlp.utils.DownloadError as exc:
        print(f"  [yt-dlp] DownloadError: {exc}", file=sys.stderr)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"  [yt-dlp] Unexpected error: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Category extraction and assessment
# ---------------------------------------------------------------------------

def find_category_candidates(info: dict) -> list[dict]:
    """
    Inspect the yt-dlp info dict for category-like fields.

    Returns a list of dicts:
        {"key": str, "value": any, "reliability": "strong" | "weak"}
    Only includes keys that are present and non-empty.
    """
    candidates = []
    for key, reliability in CATEGORY_KEYS:
        value = info.get(key)
        if value is None:
            continue
        # Normalise to a consistent shape for display
        if isinstance(value, list):
            if len(value) == 0:
                continue
        elif isinstance(value, str):
            if value.strip() == "":
                continue
        candidates.append({"key": key, "reliability": reliability, "value": value})
    return candidates


def assess_reliability(candidates: list[dict]) -> str:
    """
    Return a human-readable reliability label for the overall result.

    "strong"  — at least one strong-signal field was found
    "weak"    — only weak-signal fields were found
    "none"    — nothing useful
    """
    if not candidates:
        return "none"
    if any(c["reliability"] == "strong" for c in candidates):
        return "strong"
    return "weak"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _format_value(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def print_result(
    raw_input: str,
    info: dict | None,
    candidates: list[dict],
    debug: bool,
    dump_raw: bool,
) -> None:
    """Print a structured result block for one video."""
    sep = "-" * 60
    print(sep)
    print(f"  Input   : {raw_input}")

    if info is None:
        print("  Status  : FAILED — could not extract metadata")
        print(sep)
        return

    video_id = info.get("id", "unknown")
    title    = info.get("title", "(no title)")
    url      = info.get("webpage_url", "")

    print(f"  Video ID: {video_id}")
    print(f"  Title   : {title}")
    if url:
        print(f"  URL     : {url}")

    reliability = assess_reliability(candidates)
    print(f"  Category reliability: {reliability.upper()}")

    if candidates:
        print("  Category-like fields found:")
        for c in candidates:
            label = f"[{c['reliability']}]"
            print(f"    {label:8s} {c['key']:12s} = {_format_value(c['value'])}")
    else:
        print("  No category-like fields found.")

    if debug:
        top_keys = sorted(info.keys())
        print(f"  Top-level metadata keys ({len(top_keys)}):")
        for k in top_keys:
            print(f"    {k}")

    if dump_raw:
        try:
            raw_json = json.dumps(info, indent=2, default=str)
            print("  Raw metadata:")
            print(raw_json)
        except Exception as exc:  # noqa: BLE001
            print(f"  Could not serialise raw metadata: {exc}")

    print(sep)


def print_summary(results: list[dict]) -> None:
    """Print aggregate counts at the end."""
    total        = len(results)
    strong_count = sum(1 for r in results if r["reliability"] == "strong")
    weak_count   = sum(1 for r in results if r["reliability"] == "weak")
    none_count   = sum(1 for r in results if r["reliability"] == "none")
    failed_count = sum(1 for r in results if r["reliability"] == "failed")

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total videos checked     : {total}")
    print(f"  Strong category signal   : {strong_count}")
    print(f"  Weak signal only         : {weak_count}")
    print(f"  No useful fields         : {none_count}")
    print(f"  Failed to fetch          : {failed_count}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test yt-dlp category extraction for YouTube videos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
            "  python main.py dQw4w9WgXcQ\n"
            "  python main.py --debug dQw4w9WgXcQ jNQXAC9IVRw\n"
            "  python main.py --dump-raw dQw4w9WgXcQ\n"
        ),
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="URL_OR_ID",
        help="One or more YouTube video URLs or 11-character video IDs.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print all top-level metadata keys returned by yt-dlp.",
    )
    parser.add_argument(
        "--dump-raw",
        action="store_true",
        help="Print the full raw metadata JSON for each video.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    print(f"Checking {len(args.inputs)} video(s) with yt-dlp...\n")

    summary_rows: list[dict] = []

    for raw_input in args.inputs:
        url = normalize_input_to_url(raw_input)
        print(f"Fetching: {url}")

        info       = extract_info_with_ytdlp(url, debug=args.debug)
        candidates = find_category_candidates(info) if info else []

        if info is None:
            reliability = "failed"
        else:
            reliability = assess_reliability(candidates)

        print_result(raw_input, info, candidates, debug=args.debug, dump_raw=args.dump_raw)

        summary_rows.append({
            "input":       raw_input,
            "reliability": reliability,
        })

    print_summary(summary_rows)


if __name__ == "__main__":
    main()
