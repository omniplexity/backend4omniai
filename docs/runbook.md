# Runbook

## Startup (Local Dev)

1. Ensure `backend/.env` matches `backend/.env.example`.
2. Apply migrations: `alembic upgrade head` (or set `RUN_MIGRATIONS=true` in the container).
3. Launch backend: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
4. Frontend deploy: use the separate frontend repo; point its `BACKEND_BASE_URL` to the tunnel/external URL.
5. Confirm `/healthz` and `/admin/users` behave with admin session.

## Kubernetes Startup (Docker Desktop)

1. Ensure Docker Desktop Kubernetes is running (`kubectl get nodes` shows `docker-desktop` Ready).
2. Replace all `REPLACE_ME` values in `deploy/k8s/secrets.yaml` (or create the secret manually).
3. Apply manifests: `deploy/k8s/apply.sh` (or `deploy/k8s/apply.ps1` on Windows).
4. Verify: `kubectl -n omniai rollout status deployment/omniai-backend`.
5. Note: migrations run automatically in the backend init container.
6. Optional helper: `scripts/create-k8s-secrets.ps1` creates the secret from environment variables.

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
