# Runbook

## Startup

1. Ensure `.env` matches `.env.example` and points to production database.
2. Apply migrations: `alembic upgrade head`.
3. Launch backend: `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
4. Frontend deploy: build static assets (if using bundler) and host on GitHub Pages; point runtime `API_BASE_URL` to tunnel/external URL.
5. Confirm `/healthz` and `/admin/users` behave with admin session.

## Backup & Recovery

- **Database** – Snapshot `data/omniai.db` nightly or rely on Postgres backups. Keep three generations.
- **Restore** – Replace database file, run `alembic history` to confirm, restart service.
- **Quotas** – `usage_counters` reset daily; if state corrupt, truncate entries for target date and reinitialize via script (e.g., `DELETE FROM usage_counters WHERE date = 'YYYY-MM-DD'`).

## Quota Operations

- To adjust limits, use `/admin/users/{id}` patch with `messages_per_day`/`tokens_per_day`.
- Check `usage_counters` to see current consumption; admin UI percentages reflect these values.
- Use `quota_blocks_total` (metrics) to detect hitting limits.

## Admin Response

- **Disable user** – Set status `disabled` via `/admin/users/{id}`; sessions deleted automatically.
- **Audit review** – Use `/admin/audit` filtered by action/date to investigate suspicious activity.
- **Invite issuance** – Create with `/admin/invites`.
- **Metrics snapshot** – (Phase B) view `/admin/metrics` for stream counts, quotas, SSE pings.

## Logging & Retention

- Logs are structured: include `request_id`, `user_id`, `stream_id`, `event`.
- Rotate logs weekly and retain 30 days; compress older archives.
