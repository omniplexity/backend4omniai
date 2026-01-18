# OmniAI Docker Deployment

Production Docker Compose setup: FastAPI backend + ngrok tunnel sidecar.

## Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────┐
│       ngrok Edge Network        │
│  (TLS termination, URL routing) │
└───────────────┬─────────────────┘
                │
    ┌───────────▼───────────┐
    │    ngrok sidecar      │◄── Injects X-Origin-Secret header
    │    (tunnel client)    │    (via --request-header-add)
    └───────────┬───────────┘
                │ Docker internal network
    ┌───────────▼───────────┐
    │   backend container   │◄── Validates X-Origin-Secret
    │   FastAPI + Uvicorn   │    (OriginLockMiddleware)
    │   SQLite: /app/data   │
    └───────────────────────┘
```

**Security:**
- Backend binds to `0.0.0.0` inside container (required for Docker networking)
- No ports published to host - backend unreachable except via tunnel
- Origin lock rejects requests missing valid `X-Origin-Secret` header
- ngrok automatically injects the header on all requests

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- ngrok account (free tier works): https://ngrok.com/

## Quick Start

### 1. Get ngrok Auth Token

1. Sign up at https://ngrok.com/
2. Go to https://dashboard.ngrok.com/get-started/your-authtoken
3. Copy your auth token

### 2. Configure Environment

**Windows PowerShell:**
```powershell
cd deploy\docker
copy .env.example .env
notepad .env
```

**macOS / Linux:**
```bash
cd deploy/docker
cp .env.example .env
nano .env
```

Fill in:
- `NGROK_AUTHTOKEN` - your ngrok auth token
- `SECRET_KEY` - generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `CSRF_SECRET` - generate with `python -c "import secrets; print(secrets.token_hex(16))"`
- `ORIGIN_LOCK_SECRET` - generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- `ADMIN_BOOTSTRAP_TOKEN` - generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### 3. Start Services

```bash
docker compose up -d
```

### 4. Get Your Tunnel URL

```bash
# Check ngrok logs for the URL
docker compose logs ngrok

# Or visit the ngrok web interface
# http://localhost:4040
```

Look for a line like:
```
url=https://xxxx-xx-xx-xx-xx.ngrok-free.app
```

### 5. Update CORS Origins

Add your ngrok URL to `.env`:
```env
CORS_ORIGINS=["https://omniplexity.github.io","https://xxxx-xx-xx-xx-xx.ngrok-free.app"]
```

Then restart:
```bash
docker compose restart backend
```

### 6. Test

```bash
curl https://xxxx-xx-xx-xx-xx.ngrok-free.app/health
# Should return: {"status":"healthy"}
```

## Commands Reference

| Action | Command |
|--------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Logs (all) | `docker compose logs -f` |
| Logs (backend) | `docker compose logs -f backend` |
| Logs (ngrok) | `docker compose logs -f ngrok` |
| Rebuild | `docker compose build --no-cache backend` |
| Restart | `docker compose restart` |
| Get tunnel URL | `docker compose logs ngrok \| grep url=` |

## ngrok Web Interface

The ngrok web interface is available at http://localhost:4040 when running.

It shows:
- Current tunnel URL
- Request/response inspector
- Replay requests for debugging

## Troubleshooting

### Cookies not being set (401 after login)

Checklist:
- [ ] `COOKIE_SECURE=true` in `.env`
- [ ] `COOKIE_SAMESITE=None` in `.env`
- [ ] Frontend served over HTTPS
- [ ] `CORS_ORIGINS` includes your ngrok URL
- [ ] Browser allows third-party cookies

### Origin lock returning 403

The ngrok container automatically injects `X-Origin-Secret` header. If you're getting 403:
- [ ] Check `ORIGIN_LOCK_SECRET` is set in `.env`
- [ ] Restart ngrok container: `docker compose restart ngrok`

### ngrok URL keeps changing

Free ngrok URLs change on restart. Options:
1. **Free**: Update `CORS_ORIGINS` each time and restart backend
2. **Paid**: Use ngrok reserved domains for a stable URL

### LLM providers unreachable

For services on Docker host:
```env
LMSTUDIO_BASE_URL=http://host.docker.internal:1234/v1
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## Security Checklist

- [ ] `ORIGIN_LOCK_ENABLED=true`
- [ ] `ORIGIN_LOCK_SECRET` is set
- [ ] `COOKIE_SECURE=true`
- [ ] `COOKIE_SAMESITE=None`
- [ ] `CORS_ORIGINS` contains only your domains
- [ ] `.env` not in git

## Data Persistence

SQLite database persists at `../../data/omniplexity.db` (relative to `deploy/docker/`).

**Backup:**
```bash
cp ../../data/omniplexity.db ../../data/backup-$(date +%Y%m%d).db
```

## Reserved Domain (Paid ngrok)

For a stable URL, upgrade to ngrok paid plan and reserve a domain:

1. Reserve domain in ngrok dashboard
2. Update docker-compose.yml ngrok command:
```yaml
command:
  - "http"
  - "http://backend:8787"
  - "--domain=your-reserved-domain.ngrok.app"
  - "--request-header-add=X-Origin-Secret:${ORIGIN_LOCK_SECRET}"
```
