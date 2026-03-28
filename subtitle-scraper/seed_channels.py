"""
seed_channels.py

One-time script to populate the `channel` table from the existing flat files:
  - merged_channels.json  — full channel list with id, name, language
  - subscribed_channels.txt — raw channel IDs (no name/language yet)

Run from the subtitle-scraper directory after migration 015 has been applied:
    python seed_channels.py
    python seed_channels.py --dry-run
"""

import argparse
import json
import os
from pathlib import Path

import psycopg2
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


def load_merged_channels() -> list[dict]:
    path = Path(__file__).parent / "merged_channels.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # Flat list: [{id, name, language}, ...]
    if isinstance(data, list):
        return data
    # Dict keyed by language: {lang: [{id, name, language}, ...]}
    result = []
    for entries in data.values():
        result.extend(entries)
    return result


def load_subscribed_ids() -> list[str]:
    path = Path(__file__).parent / "subscribed_channels.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def seed(dry_run: bool = False) -> None:
    conn = connect()
    cursor = conn.cursor()

    # ── merged_channels.json ──────────────────────────────────────────────────
    merged = load_merged_channels()
    print(f"merged_channels.json: {len(merged)} channels")

    merged_inserted = 0
    merged_skipped = 0
    for ch in merged:
        channel_id   = ch.get("id", "").strip()
        channel_name = (ch.get("name") or "").strip()
        language     = ch.get("language") or None
        if not channel_id:
            continue
        if not dry_run:
            cursor.execute(
                """
                INSERT INTO channel (youtube_channel_id, channel_name, language)
                VALUES (%s, %s, %s)
                ON CONFLICT (youtube_channel_id) DO UPDATE
                    SET channel_name = EXCLUDED.channel_name,
                        language     = COALESCE(channel.language, EXCLUDED.language)
                """,
                (channel_id, channel_name, language),
            )
            if cursor.rowcount:
                merged_inserted += 1
            else:
                merged_skipped += 1
        else:
            print(f"  [dry] upsert channel {channel_id!r} ({channel_name!r}, {language})")

    # ── subscribed_channels.txt ───────────────────────────────────────────────
    subscribed = load_subscribed_ids()
    print(f"subscribed_channels.txt: {len(subscribed)} channel IDs")

    sub_inserted = 0
    for channel_id in subscribed:
        if not dry_run:
            cursor.execute(
                """
                INSERT INTO channel (youtube_channel_id)
                VALUES (%s)
                ON CONFLICT (youtube_channel_id) DO NOTHING
                """,
                (channel_id,),
            )
            if cursor.rowcount:
                sub_inserted += 1
        else:
            print(f"  [dry] insert channel_id {channel_id!r} (name/language unknown)")

    if not dry_run:
        conn.commit()
        print(f"\nDone.")
        print(f"  merged_channels: {merged_inserted} upserted, {merged_skipped} already present")
        print(f"  subscribed_only: {sub_inserted} new rows (no name/language yet)")
    else:
        print("\nDry run complete — nothing written.")

    cursor.close()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed channel table from flat files.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    seed(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
