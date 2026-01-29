## Threat Model

### Assets

- User data (messages, titles, metadata)
- User credentials, sessions, CSRF tokens
- Provider API keys/configurations
- Admin control surface (user management, quotas, invites, audit)

### Adversaries

| Actor | Motivation | Capabilities |
|---|---|---|
| Malicious user | Escalate privileges, exfiltrate other users' data | Valid session, frontend access, SSE interactions |
| Network attacker | Tamper with SSE stream, hijack sessions | MITM w/o HTTPS (mitigated via cookies + CSRF) |
| Insider/operator error | Misconfigure providers, quotas, backups | Admin dashboard access, database access |

### Controls

1. **Authentication & CSRF** – Session cookie with SameSite/Lax, CSRF double-submit (header + cookie), and middleware ensuring origins match allowlist.
2. **Authorization** – Require admin role for `/admin/*`, `ActiveStreamManager` checks owner before cancellation, disabled accounts cannot stream.
3. **Data protection** – SSE streams never expose raw stack traces; errors standardized. Backend `.env` keeps secrets out of codebase.
4. **Quota enforcement** – Prevent abuse via message/token limits with observable metrics (`quota_blocks_total`), callable in admin metrics.
5. **Auditing** – Log actions (`log_audit`) and expose via admin UI/export. Audit filters allow quick review.
6. **Provider safety** – Timeout/retry wrappers, SSE ping keep-alives to avoid idle hangs.
7. **Observability** – Structured logs include `request_id`, `user_id`, `stream_id`. Metrics and admin metrics endpoint (Phase B) will provide operational health.
