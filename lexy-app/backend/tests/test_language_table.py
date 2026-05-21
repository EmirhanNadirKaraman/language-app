"""
Regression guard on the `language_table` row set.

`language_table` is not created in any tracked Alembic migration — it
existed in the schema before Alembic adoption and survives there as
out-of-band state. Migration 030 (Stage 0 of the second-language plan)
defensively re-asserts the 'es' row via INSERT ... ON CONFLICT DO NOTHING.

These tests pin two contracts:
  1. After `alembic upgrade head`, the prod-baseline language rows are
     present (de + es). Catches a fresh-DB setup that forgot the seeding
     or a future migration that accidentally removed them.
  2. The 'es' row carries the column shape the migration documents,
     matching the Romance-sibling defaults (iso_code='spa', is_learnable).
"""
from __future__ import annotations


REQUIRED_LANGUAGES = {"de", "es"}


async def test_language_table_contains_required_languages(db_pool):
    rows = await db_pool.fetch("SELECT language FROM language_table")
    present = {r["language"] for r in rows}
    missing = REQUIRED_LANGUAGES - present
    assert not missing, (
        f"language_table is missing required rows: {sorted(missing)}. "
        f"Stage 0 migration 030 should have seeded them."
    )


async def test_spanish_row_shape(db_pool):
    row = await db_pool.fetchrow(
        "SELECT language, iso_code, is_learnable, is_interface_language "
        "FROM language_table WHERE language = 'es'"
    )
    assert row is not None, "Spanish row missing — migration 030 didn't apply?"
    # iso_code stored as CHAR(3) — strip whitespace before comparing.
    assert row["iso_code"].strip() == "spa"
    assert row["is_learnable"] is True
    # UI is English-only for now; Spanish is a learnable target, not an
    # interface language.
    assert row["is_interface_language"] is False
