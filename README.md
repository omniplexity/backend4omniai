# OmniAI

Privacy-first AI chat platform with local backend and static GitHub Pages frontend.

## Repository Structure

```
OmniAI/                     # Root of monorepo
├── backend/                # Canonical FastAPI backend
│   ├── api/               # API routers (/api/* legacy, /api/v1/* canonical)
│   ├── auth/              # Authentication (invite-only, sessions, CSRF)
│   ├── config/            # Settings (get_settings())
│   ├── core/              # Middleware, exceptions, logging
│   ├── db/                # Database (SQLite default, PostgreSQL ready)
│   ├── providers/         # LLM providers (LM Studio, Ollama, OpenAI compat)
│   ├── services/          # Business logic
│   ├── agents/           # Agent implementations
│   ├── tests/             # 40+ tests
│   ├── main.py            # FastAPI app entrypoint
│   └── Dockerfile
├── OmniAI-frontend/       # Static SPA (GitHub Pages)
│   ├── src/               # TypeScript/Preact source
│   ├── public/            # Runtime assets
│   ├── scripts/           # Build scripts
│   ├── tests/e2e/         # Playwright tests
│   └── vite.config.ts     # Build config
├── deploy/                # Deployment configurations
│   ├── docker-compose.yml # Full stack (postgres, redis, backend, ngrok)
│   ├── caddy/             # Caddy reverse proxy
│   ├── nginx/             # Nginx config
│   ├── traefik/           # Traefik config
│   └── helm/              # Kubernetes Helm charts
├── contracts/              # OpenAPI spec, JSON schemas
└── docs/                  # Architecture docs
    └── archive/           # Archived documentation
```

## Quick Start

### Backend

```powershell
# Install deps
python -m pip install -r backend\requirements.txt

# Setup database (SQLite by default)
python backend\scripts\run_migrations.py upgrade

# Run development server
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Health check:** `GET http://127.0.0.1:8000/health`

### Frontend

```powershell
cd OmniAI-frontend
npm install
npm run build   # Outputs to dist/ and root
```

**Note:** Frontend is designed for GitHub Pages. Build output serves from `omniplexity/omniplexity.github.io` repo.

### Docker Compose (Full Stack)

```powershell
cd deploy
docker compose up -d   # postgres + redis + backend + optional ngrok
```

## Environment Variables

| File | Purpose |
|------|---------|
| `backend/.env` | Backend secrets (DB password, session keys) |
| `deploy/.env.development` | Docker dev settings |
| `deploy/.env.production` | Docker prod settings |

**Never commit secrets to the frontend or any repository.**

## API Endpoints

### Canonical (`/v1/*`)
- `GET /v1/meta` - API metadata & auth status
- `GET /v1/conversations` - List conversations
- `POST /v1/conversations` - Create conversation
- `POST /v1/chat` - Send message (SSE streaming)
- `GET /v1/providers` - List LLM providers
- `GET /v1/memory` - List memory entries

### Legacy (`/api/*` - Deprecated)
- `/api/auth/*` - Authentication
- `/api/health` - Health check
- `/api/providers` - Provider info

## Security Constraints

- **Invite-only registration** - New users need invite codes
- **HttpOnly Secure cookies** - Session tokens never exposed to JS
- **CSRF protection** - All state-changing requests require CSRF token
- **Rate limiting** - Per-IP and per-user limits
- **No provider secrets in frontend** - All provider calls go through backend
- **CORS allowlist** - Strict origin checking

## Testing

```powershell
# Backend tests (40+ tests)
cd backend
python -m pytest

# Frontend build
cd OmniAI-frontend
npm run build

# Frontend e2e tests
cd OmniAI-frontend
npm run test
```

## Deployment

- **Frontend:** GitHub Pages (static build output)
- **Backend:** Local server via Docker Compose or Kubernetes
- **Tunnel:** Ngrok or Cloudflare tunnel for external access
- **Reverse Proxy:** Caddy, Nginx, or Traefik (see `deploy/`)

## Documentation

- [AGENTS.md](AGENTS.md) - Agent architecture
- [v1scope.md](v1scope.md) - v1 constraints and requirements
- [DEPLOY.md](DEPLOY.md) - Deployment guide
- `deploy/README.md` - Docker Compose options
- `OmniAI-frontend/README.md` - Frontend development
