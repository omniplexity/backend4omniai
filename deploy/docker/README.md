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
    │    (tunnel client)    │    (via ngrok.yml traffic_policy add-headers)
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
- Backend runs as non-root, drops Linux capabilities, and uses a read-only root FS
- /tmp is mounted as tmpfs; SQLite data persists only in /app/data volume

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
docker compose --profile ngrok up -d --build
```

### 4. Get Your Tunnel URL

```bash
# Check ngrok logs for the URL
docker compose logs ngrok
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
docker compose restart api
```

### 6. Test

```bash
curl https://xxxx-xx-xx-xx-xx.ngrok-free.app/health
# Should return: {"status":"healthy"}
```

### 7. Bootstrap Admin (one-time)

Use the bootstrap token to create the first admin user (only works when no admin exists):

**Windows PowerShell:**
```powershell
$env:OMNIAI_BASE_URL="https://xxxx-xx-xx-xx-xx.ngrok-free.app"
$env:OMNIAI_BOOTSTRAP_TOKEN="<your bootstrap token>"
$env:OMNIAI_ORIGIN_SECRET="<your origin lock secret>"
python scripts\bootstrap_admin.py --username Omni --password "StrongPasswordHere"
```

**macOS / Linux:**
```bash
export OMNIAI_BASE_URL="https://xxxx-xx-xx-xx-xx.ngrok-free.app"
export OMNIAI_BOOTSTRAP_TOKEN="<your bootstrap token>"
export OMNIAI_ORIGIN_SECRET="<your origin lock secret>"
python scripts/bootstrap_admin.py --username Omni --password "StrongPasswordHere"
```

## Commands Reference

| Action | Command |
|--------|---------|
| Start | `docker compose --profile ngrok up -d --build` |
| Stop | `docker compose down` |
| Logs (all) | `docker compose logs -f` |
| Logs (backend) | `docker compose logs -f api` |
| Logs (ngrok) | `docker compose logs -f ngrok` |
| Rebuild | `docker compose build --no-cache api` |
| Restart | `docker compose restart` |
| Get tunnel URL | `docker compose logs ngrok \| grep url=` |

## Runtime Knobs (Optional)

You can tune the backend container with optional env vars in `.env`:

```env
RUN_MIGRATIONS=1        # set to 0/false to skip Alembic on startup
UVICORN_WORKERS=1       # keep at 1 unless you know multi-workers are safe
UVICORN_LOG_LEVEL=info  # debug/info/warning/error
```

## Memory (Chroma Vector Store)

```env
MEMORY_ENABLED=true
MEMORY_CHROMA_PATH=/app/data/chroma
MEMORY_COLLECTION=omni_memory
MEMORY_TOP_K=6
MEMORY_MIN_SCORE=0.2
MEMORY_MAX_CHARS=1200
MEMORY_AUTO_INGEST_USER_MESSAGES=true
MEMORY_AUTO_INGEST_ASSISTANT_MESSAGES=false
MEMORY_EMBEDDING_BACKEND=auto   # auto|hash|openai_compat
MEMORY_EMBEDDING_MODEL=text-embedding-3-small
MEMORY_EMBEDDING_BASE_URL=      # optional; defaults to OPENAI_COMPAT_BASE_URL
MEMORY_EMBEDDING_API_KEY=       # optional; defaults to OPENAI_API_KEY
```

## ngrok Web Interface

To inspect ngrok traffic, use `docker compose logs -f ngrok` or temporarily publish
the ngrok admin port if you need the web UI.

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

SQLite database persists in the Docker volume `data` mounted at `/app/data`.

**Backup:**
```bash
docker exec -it omniai-api sh -c "sqlite3 /app/data/omniplexity.db '.backup /app/data/backup.db'"
docker cp omniai-api:/app/data/backup.db ./backup.db
```

## Reserved Domain (Paid ngrok)

For a stable URL, upgrade to ngrok paid plan and reserve a domain:

1. Reserve domain in ngrok dashboard
2. Update `deploy/docker/ngrok.yml` to set the reserved domain and keep
   `request_header.add` for `X-Origin-Secret`.
