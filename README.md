# OmniPlexity — Local AI WebUI (OmniAI)

<p align="center">
  <img alt="OmniPlexity" src="https://img.shields.io/badge/OmniPlexity-Local%20AI%20WebUI-6A1B9A?style=for-the-badge" />
</p>

<p align="center">
  <b>A production-grade, invite-only, ChatGPT-style WebUI hosted on GitHub Pages — backed by your local AI stack.</b><br/>
  <sub>Static frontend on <code>omniplexity.github.io</code> • Secure local backend via tunnel • Pluggable providers (LM Studio / Ollama / OpenAI-compat)</sub>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#quickstart">Quickstart</a> •
  <a href="#deployment">Deployment</a> •
  <a href="#security-model">Security</a> •
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

## Why OmniAI?

OmniAI is a **secure, invite-only AI chat interface** that looks and feels like modern AI apps, while keeping **all secrets and model traffic on your machine**. The frontend is a static SPA deployed via **GitHub Pages**, and the backend is a **local FastAPI gateway** that proxies to your providers (LM Studio, Ollama, OpenAI-compatible endpoints) with **streaming**, **cancel**, **retry**, **history**, and **audit logs**.

---

## Features

### UX (Chat UI Parity)
- ✅ ChatGPT-style **threaded conversations**
- ✅ **Streaming** responses via SSE
- ✅ **Cancel** generation (best-effort)
- ✅ **Retry** last user message
- ✅ Sidebar: **search / rename / delete** conversations
- ✅ Model + provider selection with persistence
- ✅ Send from blank state (backend auto-creates conversations)
- ✅ Markdown rendering + code copy

### Backend (Production-first)
- ✅ **Invite-only registration**
- ✅ **Session auth** with HttpOnly cookies
- ✅ **CSRF protection** for state-changing requests
- ✅ **Admin bootstrap** + admin endpoints
- ✅ **Audit logging** (includes proxy IP support behind tunnels)
- ✅ **Origin lock** middleware (tunnel-only external access)
- ✅ **Strict CORS allowlist** for GitHub Pages
- ✅ **Rate limiting** + quota enforcement (daily limits)

### Providers
- ✅ LM Studio (OpenAI-compatible)
- ✅ Ollama (native API)
- ✅ Generic OpenAI-compatible endpoints
- ✅ Clean provider interface:
  - `list_models()`, `chat_stream()`, `chat_once()`, `healthcheck()`, `capabilities()`

---

## Architecture

┌────────────────────────────────────────────────────────────────────┐
│ GitHub Pages (Static SPA) │
│ https://omniplexity.github.io │
│ - login / sessions (cookie-based) │
│ - chat UI (SSE streaming) │
│ - settings: provider, model, temperature, etc. │
└───────────────▲────────────────────────────────────────────────────┘
│ HTTPS (credentials included) + CORS allowlist
│
┌───────────────┴────────────────────────────────────────────────────┐
│ Local Backend (FastAPI) │
│ 127.0.0.1:8787 │
│ - auth (invite-only, sessions, CSRF) │
│ - chat API (SSE, cancel, retry) │
│ - providers registry │
│ - sqlite persistence + alembic migrations │
│ - origin lock (tunnel secret) │
└───────────────▲────────────────────────────────────────────────────┘
│
│ Provider calls (local / remote, secrets stay local)
▼
LM Studio (OpenAI-compat) Ollama (native) OpenAI-compat endpoints

yaml
Copy code

---

## Repo Layout

frontend/ # Static SPA (Vite + React)
index.html
public/ # runtime-config.json, favicons, 404.html
src/ # React app + styles

backend/ # Local FastAPI server
app/
api/ # routes
auth/ # session auth + csrf + audit
db/ # models + repos + sessions + engine
providers/ # provider interface + implementations
services/ # chat orchestration + generation manager
main.py # app wiring + middleware
migrations/ # alembic migrations
alembic.ini
docs/
docs/runbook.md # ops + deployment + troubleshooting
deploy/
cloudflared/ # tunnel configs + scripts

yaml
Copy code

---

## Quickstart (Local Dev)

### 1) Backend setup
```bash
python -m venv .venv
# Windows:
#   .\.venv\Scripts\Activate.ps1
# macOS/Linux:
#   source .venv/bin/activate

pip install -r backend/requirements.txt
alembic -c backend/alembic.ini upgrade head

# Run dev server (works from any working directory)
python backend/devserver.py
Backend defaults to:

http://127.0.0.1:8787

SQLite DB at data/omniplexity.db (repo-root)

2) Frontend local test
bash
Copy code
cd frontend
npm install
npm run dev
# open http://localhost:5173
Deployment (GitHub Pages + Tunnel)
1) GitHub Pages
In GitHub repo settings:

Settings → Pages

Source: GitHub Actions

Your site becomes:

https://omniplexity.github.io

2) Expose backend securely (Cloudflare Tunnel recommended)
Generate secrets:

bash
Copy code
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python -c "import secrets; print('CSRF_SECRET=' + secrets.token_hex(16))"
python -c "import secrets; print('ORIGIN_LOCK_SECRET=' + secrets.token_urlsafe(32))"
Configure .env (backend only; never commit):

env
Copy code
# Required for cross-site cookies from GitHub Pages → tunnel
COOKIE_SECURE=true
COOKIE_SAMESITE=None

# CORS allowlist
CORS_ORIGINS=["https://omniplexity.github.io"]

# Origin lock
ORIGIN_LOCK_ENABLED=true
ORIGIN_LOCK_SECRET=your_generated_secret

# Auth secrets
SECRET_KEY=...
CSRF_SECRET=...

# Providers
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
OLLAMA_BASE_URL=http://127.0.0.1:11434
OPENAI_COMPAT_BASE_URL=
OPENAI_API_KEY=
Run backend (bind localhost only):

bash
Copy code
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8787
Run tunnel:

bash
Copy code
cd deploy/cloudflared
# Windows
.\run.ps1
# macOS/Linux
chmod +x run.sh && ./run.sh
Update frontend runtime-config to the tunnel URL if you want a fixed default:

frontend/public/runtime-config.json

Security Model
Frontend is static: no secrets, no direct provider calls.

Backend holds all secrets in .env only.

Sessions: HttpOnly cookies; CSRF required for state-changing requests.

CORS: strict allowlist (https://omniplexity.github.io) + credentials enabled.

Origin Lock: external access requires X-Origin-Secret injected by the tunnel.

Rate limiting + quotas: mitigates abuse (per IP/user) + daily usage caps.

Audit logs: admin/auth actions recorded with proxy-aware IP capture.

Core Endpoints (High Level)
Auth:

POST /auth/register (invite-only)

POST /auth/login

POST /auth/logout (CSRF required)

GET /auth/me

Admin:

POST /admin/bootstrap

POST /admin/invites (CSRF + admin)

GET /admin/invites (admin)

...users/quota/audit... (admin)

Chat:

POST /conversations (CSRF)

GET /conversations

PATCH /conversations/{id} (CSRF)

DELETE /conversations/{id} (CSRF)

GET /conversations/{id}/messages

POST /conversations/{id}/stream (SSE)

POST /chat/cancel/{generation_id}

POST /chat/retry

Health:

GET /health (constant-time)

GET /health/deep (origin-lock protected)

GET /version

Troubleshooting
Login works locally but fails on GitHub Pages
Set in backend .env:

COOKIE_SECURE=true

COOKIE_SAMESITE=None
And ensure tunnel URL is HTTPS.

CORS errors / cookies not sent
Frontend requests must use credentials: "include"

Backend must have exact origin:

CORS_ORIGINS=["https://omniplexity.github.io"]

Origin lock blocks everything
Confirm tunnel injects X-Origin-Secret

Confirm backend .env has matching ORIGIN_LOCK_SECRET

/health and /version are allowed without secret (monitoring)

Database errors after pulling new changes
bash
Copy code
alembic -c backend/alembic.ini upgrade head
Roadmap
Multi-instance scaling (Redis for cancel/rate-limit state)

Optional Postgres backend via adapter

Admin UI polish + metrics dashboard

Provider capability surfacing (context length, tools, vision)

License
TBD

<p align="center"> <sub>OmniPlexity: your local models, your rules, modern UX.</sub> </p> ```
