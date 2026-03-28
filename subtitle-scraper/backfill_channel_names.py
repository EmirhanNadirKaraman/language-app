"""
backfill_channel_names.py

Fetches channel name and language for channels in the `channel` table
that have an empty channel_name. Uses yt-dlp — no API key required.

For each nameless channel it picks one of its existing videos from the
`video` table and extracts channel metadata from that video. If no video
exists yet, it falls back to fetching the channel page directly.

Usage:
    python backfill_channel_names.py
    python backfill_channel_names.py --dry-run
    python backfill_channel_names.py --limit 50
"""

import argparse
import os
import time
from pathlib import Path

import psycopg2
import yt_dlp
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


def connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def fetch_channel_info_via_video(video_id: str) -> dict | None:
    """Extract channel_name from a known video_id using yt-dlp."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {"skip_download": True, "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            name = (info.get("channel") or info.get("uploader") or "").strip()
            if name:
                return {"channel_name": name}
    except Exception as e:
        print(f"  [yt-dlp] video {video_id}: {e}")
    return None


def fetch_channel_info_via_channel_page(channel_id: str) -> dict | None:
    """Extract channel name directly from the channel page using yt-dlp."""
    url = f"https://www.youtube.com/channel/{channel_id}"
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlist_items": "1",  # only fetch enough to get channel metadata
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            name = (info.get("channel") or info.get("uploader") or info.get("title") or "").strip()
            if name:
                return {"channel_name": name}
    except Exception as e:
        print(f"  [yt-dlp] channel page {channel_id}: {e}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill empty channel names via yt-dlp.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, metavar="N")
    args = parser.parse_args()

    conn = connect()
    cursor = conn.cursor()

    query = "SELECT youtube_channel_id FROM channel WHERE channel_name = '' ORDER BY youtube_channel_id"
    if args.limit:
        query += f" LIMIT {args.limit}"
    cursor.execute(query)
    rows = cursor.fetchall()
    total = len(rows)

    if total == 0:
        print("No channels with empty names. Nothing to do.")
        conn.close()
        return

    print(f"Found {total} channel(s) with empty names.")
    if args.dry_run:
        print("DRY RUN — no changes will be written.\n")

    updated = 0
    failed = 0

    for i, (channel_id,) in enumerate(rows, start=1):
        print(f"[{i}/{total}] {channel_id} ...", end=" ", flush=True)

        # Try via an existing video first — cheaper and more reliable.
        cursor.execute(
            """
            SELECT v.video_id
              FROM video v
              JOIN channel ch ON ch.id = v.channel_id
             WHERE ch.youtube_channel_id = %s
             LIMIT 1
            """,
            (channel_id,),
        )
        video_row = cursor.fetchone()

        info = None
        if video_row:
            info = fetch_channel_info_via_video(video_row[0])
        if not info:
            info = fetch_channel_info_via_channel_page(channel_id)

        if info:
            print(info["channel_name"])
            if not args.dry_run:
                cursor.execute(
                    "UPDATE channel SET channel_name = %s WHERE youtube_channel_id = %s",
                    (info["channel_name"], channel_id),
                )
                conn.commit()
                updated += 1
        else:
            print("(not found)")
            failed += 1

        time.sleep(0.5)

    conn.close()

    if not args.dry_run:
        print(f"\nDone. Updated: {updated}, failed: {failed}")
    else:
        print("\nDry run complete.")


if __name__ == "__main__":
    main()
