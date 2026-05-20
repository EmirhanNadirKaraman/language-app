"""
Hole 10 — orphan SRS card cleanup (one-shot maintenance).

An `srs_cards` row is orphaned when no `user_word_knowledge` row exists for
`(user_id, item_id, item_type)`. Such rows never surface in `/srs/due` but
do cost disk space.

Usage
-----
Dry-run (the default — only prints the count, no writes):

    python scripts/cleanup_orphan_srs_cards.py

Apply (deletes the orphan rows):

    python scripts/cleanup_orphan_srs_cards.py --apply

Idempotent. Re-running with --apply yields `deleted == 0`.

Reads DB credentials from environment variables (`DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, `DB_PORT`), same as the backend. Source `.env`
before running:

    set -a && source .env && set +a && python scripts/cleanup_orphan_srs_cards.py
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Make `backend.*` importable when running this script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "youglish-app"))

import asyncpg  # noqa: E402

from backend.services.srs_cleanup_service import (  # noqa: E402
    cleanup_orphan_srs_cards,
    find_orphan_srs_cards,
)

logger = logging.getLogger("cleanup_orphan_srs")


async def _open_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        min_size=1,
        max_size=2,
    )


async def main(apply: bool, sample: int) -> int:
    pool = await _open_pool()
    try:
        rows = await find_orphan_srs_cards(pool)
        logger.info("Audit: %d orphan SRS card(s)", len(rows))
        if rows and sample > 0:
            logger.info("Sample (first %d):", min(sample, len(rows)))
            for r in rows[:sample]:
                logger.info(
                    "  card_id=%s user=%s item_id=%s item_type=%s direction=%s",
                    r["card_id"], r["user_id"], r["item_id"], r["item_type"], r["direction"],
                )
        if apply:
            result = await cleanup_orphan_srs_cards(pool, apply=True)
            logger.info("APPLY: deleted %d orphan SRS card(s)", result["deleted"])
        else:
            logger.info("Dry-run — no writes. Re-run with --apply to commit.")
        return len(rows)
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete orphan SRS cards. Without this flag the script is read-only.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=5,
        help="Print up to N sample rows from the audit (default 5).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    sys.exit(0 if asyncio.run(main(args.apply, args.sample)) >= 0 else 1)
