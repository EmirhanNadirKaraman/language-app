"""
Per-worker email namespacing for parallel pytest-xdist runs.

The cleanup fixture in conftest deletes users whose email matches the per-worker
pattern, so each worker can only touch the rows it created. Tests must build
emails with `make_test_email()` instead of the raw `test+{uuid}@example.com`
pattern they used in the serial-only era.

When tests run without xdist (no PYTEST_XDIST_WORKER env var), the worker ID
collapses to "main", and the cleanup pattern still matches every email this
module produces — so serial runs are unchanged.
"""
import os
import uuid


def worker_id() -> str:
    """Return the pytest-xdist worker id, or 'main' when running serially."""
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


def make_test_email() -> str:
    """A unique test user email tagged with the current worker id.

    Format: `test+{worker_id}_{10-char hex}@example.com`
    """
    return f"test+{worker_id()}_{uuid.uuid4().hex[:10]}@example.com"


def cleanup_pattern() -> str:
    """SQL LIKE pattern that matches only this worker's test emails."""
    return f"test+{worker_id()}_%@example.com"
