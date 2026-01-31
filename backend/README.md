# OmniAI Backend

Privacy-first AI chat backend for LM Studio, Ollama, and OpenAI-compatible endpoints. This repo is Kubernetes-first; local dev remains supported.

## Architecture

```
backend/
├── app/
│   ├── api/           # HTTP route handlers
│   ├── auth/          # Authentication & authorization (Phase 2)
│   ├── config/        # Pydantic Settings configuration
│   ├── core/          # Logging, errors, middleware
│   ├── db/            # Database models & repositories (Phase 2)
│   ├── providers/     # AI provider interfaces (Phase 2)
│   ├── services/      # Business logic (Phase 3)
│   └── main.py        # FastAPI application
├── tests/             # Pytest test suite
├── .env.example       # Environment template
├── pyproject.toml     # Project config & tooling
├── requirements.txt   # Production dependencies
└── requirements-dev.txt # Development dependencies
```

## Phase 1 Features

- ✅ FastAPI application skeleton
- ✅ Pydantic Settings configuration (`.env` support)
- ✅ Structured JSON logging with request IDs
- ✅ Global error handling with stable error codes (no stack traces)
- ✅ Error responses include `{error: {code, message, request_id, details?}}`
- ✅ Health check endpoints (`/healthz`, `/readyz`)
- ✅ CORS middleware (strict allowlist, credentials enabled)
- ✅ Request size limit middleware (Content-Length based)
- ✅ Provider interface definitions
- ✅ Database model definitions
- ✅ Pytest test suite (11 tests)

## Quick Start

### Prerequisites

- Python 3.11+
- pip or uv

### Windows (PowerShell)

```powershell
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies (dev includes test/lint tools)
pip install -r requirements-dev.txt

# Copy environment template
Copy-Item .env.example .env

# Run development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### macOS / Linux

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (dev includes test/lint tools)
pip install -r requirements-dev.txt

# Copy environment template
cp .env.example .env

# Run development server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Verify Installation

```bash
# Health check
curl http://127.0.0.1:8000/healthz

# Expected response:
# {"status":"ok","version":"0.1.0","timestamp":"...","debug":false}
```

## Kubernetes (Docker Desktop)

Use the manifests in `deploy/k8s` from the repo root to run the backend in the cluster. An init container runs migrations (`alembic upgrade head`) before the backend starts.

## Development

### Run Tests

```bash
pytest -v
```

### Lint Code

```bash
ruff check app tests
ruff format app tests
```

### Type Check (optional)

```bash
mypy app
```

## Configuration

All configuration is via environment variables. See `.env.example` for available options.

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DEBUG` | `false` | Enable debug mode (shows docs) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE` | - | Optional log file path |
| `SECRET_KEY` | - | **Required for production** |
| `CORS_ORIGINS` | `https://omniplexity.github.io` | Allowed CORS origins (comma-separated) |
| `MAX_REQUEST_BYTES` | `1048576` | Max request body size (1MB default) |
| `DATABASE_URL` | `sqlite:///./data/omniai.db` | Database connection URL |
| `READINESS_CHECK_PROVIDERS` | `false` | If true, `/readyz` checks provider health |

## API Endpoints

### Phase 1

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness probe (`{"status":"ok","version":"0.1.0",...}`) |
| GET | `/readyz` | Readiness probe with dependency checks |
| GET | `/docs` | OpenAPI docs (debug mode only) |

## Error Response Format

All errors return a consistent JSON structure:

```json
{
  "error": {
    "code": "E1000",
    "message": "Human-readable message",
    "request_id": "uuid-here",
    "details": {}
  }
}
```

Error codes follow the pattern:

- `E1xxx` - General errors (validation, not found, rate limit)
- `E2xxx` - Authentication errors
- `E3xxx` - Authorization errors
- `E4xxx` - Provider errors
- `E5xxx` - Resource errors

## Security

- CORS restricted to explicit allowlist with credentials enabled
- Request size limits enforced via Content-Length header
- No stack traces in error responses
- Structured error codes for reliable client handling
- Request IDs on all requests/responses for tracing
- Backend binds to 0.0.0.0 inside containers; expose it only through the configured tunnel/reverse proxy.

## Next Phases

- **Phase 2**: Authentication (sessions, CSRF, Argon2id), Database (SQLite), Provider implementations
- **Phase 3**: Chat API, streaming (SSE), conversations, audit logging
- **Phase 4**: Frontend integration, deployment configs
