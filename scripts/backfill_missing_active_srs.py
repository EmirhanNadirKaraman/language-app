"""
W6 / Hole 11+16 — backfill missing active SRS cards.

One-shot remedial script. Items marked `status='learning'` before #0b
(2026-05-19) created only the passive SRS card. This script finds those
rows and inserts the missing active card with the same defaults
`progression_service._update_srs("create")` would produce.

Usage
-----
Dry-run (the default — only prints the count, no writes):

    python scripts/backfill_missing_active_srs.py

Apply (writes the missing rows):

    python scripts/backfill_missing_active_srs.py --apply

Idempotent. Re-running with --apply does nothing on the second pass.

Reads DB credentials from the project `.env` via the same names the
backend uses: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
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
sys.path.insert(0, str(_REPO_ROOT / "lexy-app"))

import asyncpg  # noqa: E402

from backend.services.srs_backfill_service import (  # noqa: E402
    backfill_missing_active_cards,
    find_missing_active_cards,
)

logger = logging.getLogger("backfill_active_srs")


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
        rows = await find_missing_active_cards(pool)
        logger.info("Audit: %d learning items missing active SRS cards", len(rows))
        if rows and sample > 0:
            logger.info("Sample (first %d):", min(sample, len(rows)))
            for r in rows[:sample]:
                logger.info("  user=%s item_id=%s item_type=%s",
                            r["user_id"], r["item_id"], r["item_type"])
        if apply:
            result = await backfill_missing_active_cards(pool, apply=True)
            logger.info("APPLY: inserted %d active SRS card(s)", result["inserted"])
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
        help="Actually insert the missing active SRS cards. Without this flag the script is read-only.",
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
