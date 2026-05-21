# Maintenance jobs

Scheduled and ad-hoc database hygiene scripts. Each entry has the manual
command first, then platform-specific scheduler snippets. Add new entries
here when a new maintenance script ships.

---

## Orphan SRS card cleanup (Hole 10)

An `srs_cards` row becomes orphaned when no matching
`user_word_knowledge` row exists for its `(user_id, item_id, item_type)`.
Such rows never surface in `/srs/due` (the review query left-joins on
user_word_knowledge) but they keep occupying disk and skew queue-size
metrics. Sources: catalog cleanups, manual SQL fixes, future migrations
that drop stale rows from the polymorphic catalogs.

**Status on dev DB (W12 audit, 2026-05-20): 0 orphans.** No urgent
backfill needed; this is preventive hygiene.

### Script

[`scripts/cleanup_orphan_srs_cards.py`](../scripts/cleanup_orphan_srs_cards.py)
delegates to `services/srs_cleanup_service.cleanup_orphan_srs_cards(apply: bool)`.
Idempotent. Pure SQL — touches only `srs_cards`; never reads or writes
`user_word_knowledge`, the catalog tables, or any progression state.

### Manual run

Dry-run (default — prints the orphan count + a sample, no writes):

```bash
set -a && source .env && set +a
python scripts/cleanup_orphan_srs_cards.py
```

Apply (deletes the orphan rows):

```bash
set -a && source .env && set +a
python scripts/cleanup_orphan_srs_cards.py --apply
```

`--sample N` controls how many sample orphan rows are logged before the
delete (default 5; pass `--sample 0` to suppress).

### Recommended schedule

**Weekly `--apply` at a quiet hour (e.g. Monday 04:30 UTC).** Reasoning:

- The cleanup is idempotent and pure SQL — re-running costs nothing
  when there are zero orphans.
- Dry-run-forever provides no operational benefit beyond the first
  run. The script already prints the orphan count before deleting, so
  weekly logs serve as the audit trail.
- Daily is overkill — orphans only appear when a catalog cleanup
  happens upstream, which is rare.

If you'd rather start conservative, the same schedule on dry-run is
fine — flip to `--apply` once you've seen a couple of logs go by.

### Platform snippets

These are templates — adjust the working dir, Python path, and env
loading to match your deploy.

**Render cron job** (in `render.yaml`):

```yaml
services:
  - type: cron
    name: cleanup-orphan-srs
    runtime: python
    schedule: "30 4 * * 1"   # Monday 04:30 UTC
    buildCommand: pip install -r lexy-app/backend/requirements.txt
    startCommand: python scripts/cleanup_orphan_srs_cards.py --apply
    envVars:
      - fromGroup: db-secrets   # reuses the same DB_* vars as `web`
```

**Heroku Scheduler** (configured in dashboard, not Procfile):

```
Frequency: Every day at … → "Monday 04:30 UTC"  (Scheduler does not
                            offer "weekly" directly; pick a day-of-week
                            wrapper or use Heroku Scheduler Add-on
                            "every 24h" + an in-script weekday guard)
Command:   python scripts/cleanup_orphan_srs_cards.py --apply
Dyno size: Standard-1X is fine — script is read-then-delete, finishes
           in <10s on small DBs.
```

**Plain cron** (host running the backend):

```cron
30 4 * * 1 cd /path/to/language-app && \
  set -a && . ./.env && set +a && \
  /usr/bin/python3 scripts/cleanup_orphan_srs_cards.py --apply \
  >> /var/log/lexy/orphan-srs.log 2>&1
```

### Verifying the schedule

After a run, check the log for a line like:

```
INFO cleanup_orphan_srs: Audit: 0 orphan SRS card(s)
INFO cleanup_orphan_srs: APPLY: deleted 0 orphan SRS card(s)
```

On a healthy DB the count stays at 0. A non-zero count for several
weeks running points at an upstream issue (catalog cleanup that
doesn't cascade properly) — investigate `srs_cleanup_service.find_orphan_srs_cards`
output before assuming it's normal.
