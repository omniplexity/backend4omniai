# OmniAI Deployment Guide

## Overview

This guide covers deploying OmniAI with:
- **Frontend**: GitHub Pages (static hosting) at `omniplexity.github.io`
- **Backend**: Docker Desktop with ngrok tunnel

---

## Prerequisites

- Docker Desktop installed and running
- ngrok account with authtoken
- GitHub access to both repositories

---

## Step 1: Deploy Frontend to GitHub Pages

The frontend has already been built and pushed. It will be live at:
**https://omniplexity.github.io**

### To update the frontend in the future:

```bash
cd OmniAI-frontend
npm run build
git add -A
git commit -m "Deploy: Update built assets"
git push origin main
```

GitHub Pages will automatically update within a few minutes.

---

## Step 2: Configure Backend Environment

### 2.1 Create the .env file

Navigate to `OmniAI-backend/backend/` and create a `.env` file:

```bash
cd OmniAI-backend/backend
copy .env.example .env
```

### 2.2 Edit the .env file

Open `.env` in your editor and set these required values:

```env
# =============================================================================
# SERVER
# =============================================================================
ENVIRONMENT=development
HOST=0.0.0.0
PORT=8000
DEBUG=false
LOG_LEVEL=INFO

# =============================================================================
# SECURITY
# =============================================================================
# Generate a secure random key:
# python -c "import secrets; print(secrets.token_urlsafe(64))"
SECRET_KEY=your-secure-secret-key-here

# CORS - Must include your GitHub Pages domain
CORS_ORIGINS=https://omniplexity.github.io,https://rossie-chargeful-plentifully.ngrok-free.dev

# Rate limiting
RATE_LIMIT_RPM=200

# Max request body size
MAX_REQUEST_BYTES=10485760
VOICE_MAX_REQUEST_BYTES=26214400

# =============================================================================
# AUTHENTICATION
# =============================================================================
SESSION_COOKIE_NAME=omni_session
SESSION_TTL_SECONDS=604800
COOKIE_SECURE=true
COOKIE_SAMESITE=none
COOKIE_DOMAIN=

CSRF_HEADER_NAME=X-CSRF-Token
CSRF_COOKIE_NAME=omni_csrf
INVITE_REQUIRED=true

# Bootstrap admin (enable for first-time setup)
BOOTSTRAP_ADMIN_ENABLED=true
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_PASSWORD=your-secure-admin-password

# =============================================================================
# DATABASE
# =============================================================================
# Docker Compose uses PostgreSQL automatically
DATABASE_URL=sqlite:///./data/omniai.db
DATABASE_URL_POSTGRES=postgresql://omniai:omniai_secure_2024@postgres:5432/omniai

# =============================================================================
# MEDIA
# =============================================================================
MEDIA_STORAGE_PATH=./data/uploads

# =============================================================================
# PROVIDERS
# =============================================================================
PROVIDER_DEFAULT=lmstudio
PROVIDERS_ENABLED=lmstudio
PROVIDER_TIMEOUT_SECONDS=60
PROVIDER_MAX_RETRIES=3
SSE_PING_INTERVAL_SECONDS=30
READINESS_CHECK_PROVIDERS=false

# LM Studio running on host machine
LMSTUDIO_BASE_URL=http://host.docker.internal:1234
OLLAMA_BASE_URL=http://127.0.0.1:11434

# =============================================================================
# EMBEDDINGS
# =============================================================================
EMBEDDINGS_ENABLED=false
EMBEDDINGS_MODEL=
EMBEDDINGS_PROVIDER_PREFERENCE=openai_compat,ollama,lmstudio

# =============================================================================
# VOICE
# =============================================================================
VOICE_PROVIDER_PREFERENCE=whisper,openai_compat
VOICE_WHISPER_MODEL=base
VOICE_WHISPER_DEVICE=cpu
VOICE_OPENAI_AUDIO_MODEL=whisper-1

# =============================================================================
# REDIS
# =============================================================================
REDIS_URL=redis://redis:6379/0

# =============================================================================
# NGROK (for docker-compose.yml)
# =============================================================================
NGROK_DOMAIN=rossie-chargeful-plentifully.ngrok-free.dev
NGROK_AUTHTOKEN=your-ngrok-authtoken-here
```

**Important:** Replace these placeholders:
- `your-secure-secret-key-here` - Generate with: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- `your-secure-admin-password` - Your chosen admin password
- `your-ngrok-authtoken-here` - Your ngrok authtoken from https://dashboard.ngrok.com

---

## Step 3: Start the Backend with Docker Desktop

### 3.1 Open Docker Desktop
Ensure Docker Desktop is running.

### 3.2 Start the services

```bash
cd OmniAI-backend

# Start backend + database + ngrok tunnel
docker compose --profile tunnel up -d
```

This will start:
- PostgreSQL database
- Redis cache
- FastAPI backend (port 8000)
- ngrok tunnel (public HTTPS URL)

### 3.3 Check service status

```bash
# View all running containers
docker compose ps

# View logs
docker compose logs -f

# Check health
curl http://localhost:8000/health
```

### 3.4 Verify ngrok tunnel

Once running, your backend will be accessible at:
**https://rossie-chargeful-plentifully.ngrok-free.dev**

You can verify by visiting:
```
https://rossie-chargeful-plentifully.ngrok-free.dev/health
```

---

## Step 4: First-Time Setup

### 4.1 Access the frontend

Open your browser to:
**https://omniplexity.github.io**

### 4.2 Create the admin account

1. Click "Sign Up" tab
2. Enter the bootstrap admin credentials you set in `.env`:
   - Email: `admin@example.com`
   - Username: `admin`
   - Password: (your bootstrap password)
   - Invite code: `admin` (or any value if invite_required is false)

3. After login, disable bootstrap mode in `.env`:
   ```env
   BOOTSTRAP_ADMIN_ENABLED=false
   ```
4. Restart the backend: `docker compose restart backend`

---

## Step 5: Verify Full Deployment

### Check these URLs:

| Service | URL | Expected Result |
|---------|-----|-----------------|
| Frontend | https://omniplexity.github.io | Login page loads |
| Backend Health | https://rossie-chargeful-plentifully.ngrok-free.dev/health | `{"status":"ok"}` |
| Backend API | https://rossie-chargeful-plentifully.ngrok-free.dev/api/auth/check | `{"authenticated":false}` |

### Test login:

1. Go to https://omniplexity.github.io
2. Enter your admin username and password
3. You should be logged in successfully

---

## Useful Commands

```bash
# Start all services with ngrok
cd OmniAI-backend
docker compose --profile tunnel up -d

# Stop all services
docker compose down

# Restart backend only
docker compose restart backend

# View logs
docker compose logs -f backend
docker compose logs -f ngrok

# Update backend after code changes
git pull
docker compose up -d --build backend

# Shell into backend container
docker compose exec backend sh

# Database migrations (inside container)
docker compose exec backend alembic upgrade head
```

---

## Troubleshooting

### CORS errors in browser
- Ensure `CORS_ORIGINS` in `.env` includes both:
  - `https://omniplexity.github.io`
  - Your ngrok domain
- Restart backend: `docker compose restart backend`

### Cannot connect to backend
- Check ngrok tunnel: `docker compose logs ngrok`
- Verify backend health: `curl http://localhost:8000/health`
- Check ngrok authtoken is set correctly in `.env`

### Database connection errors
- Ensure PostgreSQL is healthy: `docker compose ps`
- Check logs: `docker compose logs postgres`

### Login not working
- Check browser console for errors
- Verify cookies are being set (check Application > Cookies in DevTools)
- Ensure `COOKIE_SAMESITE=none` and `COOKIE_SECURE=true` for cross-site cookies

---

## Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│   GitHub Pages      │         │   Docker Desktop    │
│   (Static Frontend) │◄────────┤   (Backend Stack)   │
│                     │  HTTPS  │                     │
│ omniplexity.github  │         │ ┌───────────────┐   │
│     .io             │         │ │   FastAPI     │   │
└─────────────────────┘         │ │   Backend     │   │
                                │ │   :8000       │   │
                                │ └───────┬───────┘   │
                                │         │           │
                                │ ┌───────▼───────┐   │
                                │ │     ngrok     │   │
                                │ │    Tunnel     │   │
                                │ └───────┬───────┘   │
                                │         │           │
                                │    Public HTTPS     │
                                │    ngrok-free.dev   │
                                └─────────────────────┘
```

---

## Next Steps

1. ✅ Set up your `.env` file with real values
2. ✅ Start Docker Desktop
3. ✅ Run `docker compose --profile tunnel up -d`
4. ✅ Visit https://omniplexity.github.io
5. ✅ Log in with your admin credentials

Happy deploying! 🚀
