## Production Readiness Checklist

1. **CORS allowlist** – `CORS_ORIGINS` must enumerate trusted frontends (GitHub Pages origin, webhook tunnels). No wildcards.
2. **CSRF enforcement** – `omni_csrf` cookie + `X-CSRF-Token` header enabled; origin/referrer validation matches allowlist.
3. **Admin bootstrap** – At least one admin account exists; keep admin invite codes under review.
4. **Backups** – Database snapshots daily, retain 30+ days, test restore quarterly.
5. **Logging & retention** – Structured logs include `request_id`, `user_id`, `stream_id`. Rotate weekly, archive 30 days.
6. **Quotas** – `user_quotas` or defaults configured for paid tiers; monitor `quota_blocks_total` metric.
7. **Deployment readiness** – `.env` matches `.env.example`; secrets rotated; provider URLs reachable from backend.
8. **Monitoring** – Health checks (`/healthz`), SSE pings, SSE duration metrics, and admin metrics endpoint (if enabled) integrated into dashboards or alerts.
