"""Add client_error_log table for frontend ErrorBoundary reports

Revision ID: 028
Revises: 027
Create Date: 2026-05-20

Stores best-effort error reports POSTed by the frontend ErrorBoundary so
production crashes are observable without a third-party monitoring service.

  - user_id is nullable: reports are accepted from unauthenticated callers
    (crashes can happen pre-login or after token expiry).
  - Field length caps are enforced at the API layer (Pydantic), not the
    column type, so we can adjust limits without a schema change.
  - Index on (created_at) for time-windowed queries when triaging incidents.
"""
from alembic import op


revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE client_error_log (
            error_id        SERIAL       PRIMARY KEY,
            user_id         UUID         NULL REFERENCES users(user_id) ON DELETE SET NULL,
            message         TEXT         NOT NULL,
            stack           TEXT         NULL,
            component_stack TEXT         NULL,
            url             TEXT         NULL,
            user_agent      TEXT         NULL,
            release         TEXT         NULL,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX ix_client_error_log_created_at
            ON client_error_log (created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_client_error_log_created_at")
    op.execute("DROP TABLE IF EXISTS client_error_log")
