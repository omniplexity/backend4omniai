# OmniAI WebUI Runbook

## Local Development

### Backend Setup
1. Install Python 3.12+
2. `pip install -r backend/requirements.txt`
3. Set up environment variables in `.env` (see `.env.example`)
4. Initialize database: `alembic -c backend/alembic.ini upgrade head`
5. Run backend: `python backend/devserver.py`

### Frontend Setup
1. Serve frontend locally: `cd frontend && python -m http.server 5173`
2. Open http://localhost:5173 in browser
3. Set backend URL in UI to `http://127.0.0.1:8787` (or your tunnel URL)

## Production Deployment

### Prerequisites
- Cloudflare account with domain
- GitHub repository with Pages enabled
- Backend server (can be local with tunnel)

### Backend Deployment
1. **Environment Setup**:
   - Copy `backend/.env.example` to `backend/.env`
   - Set production secrets:
     ```
     SECRET_KEY=your-256-bit-secret-here
     CSRF_SECRET=your-csrf-secret-here
     ADMIN_BOOTSTRAP_TOKEN=one-time-admin-token
     ORIGIN_LOCK_ENABLED=true
     ORIGIN_LOCK_SECRET=shared-secret-with-tunnel
     COOKIE_SECURE=true
     COOKIE_SAMESITE=None
     CORS_ORIGINS=["https://omniplexity.github.io","https://your-custom-domain.com"]
     HOST=127.0.0.1  # Keep 127.0.0.1, use tunnel for external access
     ```

2. **Database Migration**:
   ```bash
   cd backend
   alembic upgrade head
   ```

3. **Start Backend**:
   ```bash
   cd backend
   python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8787
   ```

### Cloudflare Tunnel Setup (Recommended)
1. **Install cloudflared**: Follow https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/

2. **Login and Create Tunnel**:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create omniplexity-backend
   ```

3. **Configure Tunnel**:
   - Copy `deploy/cloudflared/config.yml.example` to `deploy/cloudflared/config.yml`
   - Update:
     - `tunnel`: Your tunnel ID from step 2
     - `credentials-file`: Path to credentials file
     - `hostname`: Your subdomain (e.g., api.omniplexity.dev)
     - `X-Origin-Secret`: Must match `ORIGIN_LOCK_SECRET` in .env

4. **DNS Setup**:
   - In Cloudflare dashboard, add CNAME record: `api.omniplexity.dev -> tunnel-id.cfargotunnel.com`

5. **Run Tunnel**:
   ```bash
   cd deploy/cloudflared
   # Windows
   .\run.ps1
   # Linux/Mac
   chmod +x run.sh && ./run.sh
   ```

### Frontend (GitHub Pages)
1. **Deploy**:
   - Commit frontend/ directory
   - Go to GitHub repo Settings > Pages
   - Set source to "Deploy from a branch"
   - Branch: `main`, Folder: `/frontend`
   - Site URL: https://omniplexity.github.io (or custom domain)

2. **Custom Domain** (optional):
   - Add CNAME file to frontend/: `your-domain.com`
   - Configure DNS: `your-domain.com CNAME omniplexity.github.io`
   - Update CORS_ORIGINS in backend .env

### Security Checklist
- [ ] All secrets changed from defaults
- [ ] ORIGIN_LOCK_ENABLED=true
- [ ] COOKIE_SECURE=true and COOKIE_SAMESITE=None
- [ ] HTTPS enabled everywhere
- [ ] CORS_ORIGINS restricted to your domains
- [ ] Admin bootstrap token used and removed

### Rotating Secrets
1. **Generate new secrets**:
   ```bash
   python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
   python -c "import secrets; print('CSRF_SECRET=' + secrets.token_hex(16))"
   python -c "import secrets; print('ORIGIN_LOCK_SECRET=' + secrets.token_urlsafe(32))"
   ```

2. **Update .env** with new values

3. **Update tunnel config** (`deploy/cloudflared/config.yml`) with new ORIGIN_LOCK_SECRET:
   ```yaml
   originRequest:
     setRequestHeader:
       - X-Origin-Secret: "new-shared-secret-here"
   ```

4. **Restart backend and tunnel safely**:
   - Stop backend (Ctrl+C if running)
   - Stop tunnel (kill cloudflared process)
   - Start tunnel first: `cd deploy/cloudflared && ./run.ps1` (or run.sh)
   - Start backend: `cd backend && python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8787`

5. **Clear browser cookies** (users will need to re-login)

### Operational Guardrails
- **Never bind to 0.0.0.0**: Always use `HOST=127.0.0.1` in .env. External access only via tunnel/reverse proxy with origin lock enabled.
- **Backup/Restore SQLite**:
  - Backup: `sqlite3 backend/data/omniplexity.db ".backup backup-$(date +%Y%m%d).db"`
  - Restore: `sqlite3 backend/data/omniplexity.db ".restore backup-20231201.db"`
  - Store backups securely, ideally encrypted.
- **Log Retention and Rotation**:
  - Backend logs to stdout/stderr; use your system logger (journald, syslog) for rotation.
  - For production, configure log rotation to prevent disk filling.
  - Audit logs in database; consider periodic export/cleanup if volume is high.
- **Session Revocation**:
  - To revoke a user's sessions: Delete from `sessions` table where `user_id = ?`
  - Or, change SECRET_KEY to invalidate all sessions (requires user re-login).

### Health Checks and Monitoring
- **GET /health**: Constant-time health check without DB verification. Always returns `{"status": "healthy"}` if the service is running. Use for load balancer health checks and uptime monitoring.
- **GET /health/deep**: Deep health check with DB connectivity verification. Returns DB status and latency_ms. Protected by origin lock - requires `X-Origin-Secret` header for external access. Use for internal monitoring and alerting on DB connectivity issues.

## Troubleshooting

### Cookie Issues with GitHub Pages
- Ensure backend has `cookie_secure=true` and `cookie_samesite=None`
- Frontend must be served over HTTPS (GitHub Pages provides this)
- Backend CORS must include `https://omniplexity.github.io` with `allow_credentials=true`

### SSE Streaming Issues
- Check browser network tab for connection errors
- Ensure backend is reachable from frontend
- Check browser console for JavaScript errors

### Authentication Issues
- Clear browser cookies and localStorage
- Check backend logs for authentication errors
- Verify CSRF tokens are being sent correctly

## Backup/Restore

### Database Backup
```bash
sqlite3 backend/data/omniplexity.db .backup backup.db
```

### Database Restore
```bash
sqlite3 backend/data/omniplexity.db < backup.sql
```

## Docker Compose (Always-On) Deployment

For production deployments with automatic restarts, use the Docker Compose setup in `deploy/docker/`.

### Architecture

- **backend container**: FastAPI/Uvicorn, runs migrations on start, binds to `0.0.0.0:8787` inside container
- **ngrok sidecar**: Waits for backend healthy, proxies `http://backend:8787`, injects `X-Origin-Secret` header
- **No host ports published**: Backend only reachable via tunnel
- **SQLite persistence**: Database stored in Docker volume mounted at `/app/data`
- **Container hardening**: backend runs as non-root, drops Linux caps, read-only root FS, tmpfs `/tmp`

### Quick Start

1. Get ngrok auth token from https://dashboard.ngrok.com/get-started/your-authtoken

2. Configure environment:

**Windows PowerShell:**
```powershell
cd deploy\docker
copy .env.example .env
notepad .env  # Add NGROK_AUTHTOKEN and generate secrets
docker compose up -d
```

**macOS / Linux:**
```bash
cd deploy/docker
cp .env.example .env
nano .env  # Add NGROK_AUTHTOKEN and generate secrets
docker compose up -d
```

3. Get tunnel URL: `docker compose logs ngrok` or visit http://localhost:4040

4. Add ngrok URL to `CORS_ORIGINS` in `.env` and restart: `docker compose restart backend`

### Production Checklist

```env
NGROK_AUTHTOKEN=<your-token>
ORIGIN_LOCK_ENABLED=true
ORIGIN_LOCK_SECRET=<generated-secret>
COOKIE_SECURE=true
COOKIE_SAMESITE=None
CORS_ORIGINS=["https://omniplexity.github.io","https://your-ngrok-url.ngrok-free.app"]
```

### Commands

```bash
docker compose up -d          # Start
docker compose down           # Stop
docker compose logs -f        # All logs
docker compose logs ngrok     # Get tunnel URL
docker compose ps             # Status
docker compose restart        # Restart
docker compose build backend  # Rebuild after code changes
```

### Optional Runtime Knobs

```env
RUN_MIGRATIONS=1        # set to 0/false to skip Alembic on startup
UVICORN_WORKERS=1       # keep at 1 unless you know multi-workers are safe
UVICORN_LOG_LEVEL=info  # debug/info/warning/error
```

### Memory (Chroma Vector Store)

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

### Troubleshooting

| Issue | Check |
|-------|-------|
| Cookies not set | `COOKIE_SECURE=true`, `COOKIE_SAMESITE=None` |
| Origin lock 403 | `ORIGIN_LOCK_SECRET` is set, restart ngrok |
| ngrok not starting | `NGROK_AUTHTOKEN` is set correctly |
| LLM unreachable | Use `host.docker.internal` for host services |

See [deploy/docker/README.md](deploy/docker/README.md) for full documentation.
