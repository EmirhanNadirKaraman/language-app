"""Make content_request uniqueness per-user instead of global

Revision ID: 029
Revises: 028
Create Date: 2026-05-21

Background
----------
Migration 018 declared ``UNIQUE (request_type, content_id)`` on
``content_request``. The router used ``ON CONFLICT DO UPDATE`` to handle
re-submits, but because uniqueness was global, a second user submitting the
same channel/video collided with the first user's row. The router preserved
the existing ``user_id`` on conflict, so:

  * User B's POST returned a row owned by User A.
  * User B's ``GET /content-requests`` (filtered by user_id) saw nothing.
  * If User A's row was failed, User B's submit reset it on A's row — A
    received the eventual ``channel_done`` notification, B got nothing.

Each user should get their own tracking row. The scraper already keys
notifications by ``content_request.request_id`` (via ``_notify_user``), so
once each user has a distinct row, notifications flow to the right user
without further changes.

What this migration does
------------------------
- Drops the global ``UNIQUE (request_type, content_id)`` constraint.
- Adds ``UNIQUE (user_id, request_type, content_id)``.

Backfill
--------
No row migration needed: the old constraint is a strict superset of the new
one (any data that satisfied "global unique" also satisfies "per-user
unique"), so existing rows remain valid.

Trade-off (accepted)
--------------------
With per-user rows, two users requesting the same channel can each enqueue
a row in ``pending``; the scraper processes them serially and ends up
scraping that channel twice. The duplicate work is wasted CPU only — the
downstream ``video`` / ``sentence`` inserts are idempotent via their own
``ON CONFLICT DO NOTHING`` clauses, so no data is corrupted. Adding work
deduplication is out of scope for this migration.
"""
from alembic import op


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


# Postgres auto-generates the constraint name when the column-list form
# `UNIQUE (request_type, content_id)` is used inline in CREATE TABLE.
_OLD_CONSTRAINT = "content_request_request_type_content_id_key"
_NEW_CONSTRAINT = "content_request_user_id_request_type_content_id_key"


def upgrade() -> None:
    op.execute(
        f'ALTER TABLE content_request DROP CONSTRAINT IF EXISTS "{_OLD_CONSTRAINT}"'
    )
    op.execute(
        f'ALTER TABLE content_request '
        f'ADD CONSTRAINT "{_NEW_CONSTRAINT}" '
        f'UNIQUE (user_id, request_type, content_id)'
    )


def downgrade() -> None:
    # Restoring the global constraint will fail loudly if two users have
    # submitted the same (request_type, content_id) under the new world —
    # that's the intended signal, not a bug. Resolve duplicates manually
    # before downgrading.
    op.execute(
        f'ALTER TABLE content_request DROP CONSTRAINT IF EXISTS "{_NEW_CONSTRAINT}"'
    )
    op.execute(
        f'ALTER TABLE content_request '
        f'ADD CONSTRAINT "{_OLD_CONSTRAINT}" '
        f'UNIQUE (request_type, content_id)'
    )
