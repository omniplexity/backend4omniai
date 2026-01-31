## Architecture Overview

OmniAI is divided into a backend service powering authenticated SSE chat flows and a static frontend hosted on GitHub Pages (in a separate repo). The backend (FastAPI) owns session cookies, CSRF protection, provider adapters (LM Studio, Ollama, OpenAI-compatible), quotas, and an admin surface. The frontend is vanilla JS, reads its `runtime-config.json` for the backend base URL, and renders SSE-driven conversations plus the admin console.

### Key Components

- **FastAPI backend** – Handles auth/session lifecycle, conversation persistence, provider registry, streaming SSE, cancel/retry, quotas, and admin APIs.
- **Database** – SQLite by default (`./data/omniai.db`), Postgres-ready via `DATABASE_URL`. Tables include `users`, `sessions`, `conversations`, `messages` (with `provider_meta`), `audit_log`, `user_quotas`, and `usage_counters`.
- **Admin APIs** – Role-gated endpoints expose users, usage, audit entries, invites, and metrics snapshots. Structured logging records `request_id`, `user_id`, and `stream_id`.
- **Frontend SPA** – Loads config, authenticates via session cookie/CSRF, renders conversations with virtualized scrolling, and exposes the admin panel for management actions.
- **Provider Adapters** – Must implement `BaseProvider`, `chat_stream`, list models, and emit `StreamChunk` with `finish_reason`. Keep-alive comment pings avoid idle disconnects.

### Data Flow

1. User logs in → FastAPI issues `omni_session` + `omni_csrf`.
2. Frontend selects conversation + provider model → POST `/chat/stream`.
3. `ChatService` validates quota/status, inserts user/assistant messages, registers `ActiveStream`, streams SSE events (meta/delta/final/error) with metrics.
4. SSE client renders messages, shows elapsed time, persists resume hints, and exposes cancel/retry flows.
5. Admin panel uses `/admin/*` endpoints to manage users, quotas, invites, usage, and audit logs.

### Operational Considerations

- Quotas are enforced per-user via `user_quotas` (limits) and `usage_counters` (daily aggregates). Reaching a limit raises `E2010`.
- Audit logs capture security-relevant actions (`login`, `invite_create`, `user_disable`, `user_quota_update`). Admin console can filter and export them.
- SSE streams include ping keep-alives, include `X-Request-ID` headers, and expose cancellation via `ActiveStreamManager`.
