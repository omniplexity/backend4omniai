# OmniAI Architecture

## Overview

OmniAI is a secure, invite-only AI chat web interface that proxies requests to local or remote LLM providers. It consists of a static frontend deployed on GitHub Pages and a local FastAPI backend that handles authentication, chat orchestration, and provider integration.

## High-Level Dataflow

```
┌────────────────────────────────────────────────────────────────────┐
│ GitHub Pages (Static SPA) │
│ https://omniplexity.github.io │
│ - HTML/CSS/JS chat interface │
│ - SSE streaming for responses │
│ - Session cookie auth │
└───────────────▲────────────────────────────────────────────────────┘
│ HTTPS (credentials included) + CORS allowlist
│
┌───────────────┴────────────────────────────────────────────────────┐
│ Local Backend (FastAPI/Uvicorn) │
│ 127.0.0.1:8787 │
│ - Authentication & authorization │
│ - Chat API with streaming │
│ - Provider registry │
│ - SQLite persistence │
│ - Rate limiting & quotas │
│ - Audit logging │
│ - Origin lock for tunnel protection │
└───────────────▲────────────────────────────────────────────────────┘
│
│ Provider API calls (HTTP/HTTPS)
▼
LM Studio (127.0.0.1:1234)  Ollama (127.0.0.1:11434)  OpenAI-compatible endpoints
```

## Component Architecture

### Frontend (Static SPA)
- **Technology**: Vanilla JavaScript, HTML, CSS
- **Deployment**: GitHub Pages (static hosting only)
- **Responsibilities**:
  - User interface for login, chat, admin panels
  - SSE event handling for streaming responses
  - LocalStorage for UI state
  - CSRF token management
  - No provider URLs or secrets

### Backend (FastAPI Application)
- **Technology**: Python 3.12+, FastAPI, Uvicorn, SQLAlchemy, SQLite
- **Architecture**: Modular with clean boundaries
- **Key Modules**:

#### API Layer (`backend/app/api/`)
- **Routers**: REST endpoints organized by domain
  - `auth.py`: Authentication (login, register, logout)
  - `conversations.py`: Conversation management
  - `chat.py`: Chat streaming and message handling
  - `messages.py`: Message CRUD operations
  - `admin.py`: Administrative functions
  - `providers.py`: Provider listing and health
  - `health.py`: Health checks

#### Authentication & Security (`backend/app/auth/`)
- **Sessions**: HttpOnly cookies with configurable SameSite
- **CSRF Protection**: HMAC-based tokens derived from session ID
- **Password Hashing**: Argon2id (bcrypt fallback)
- **Audit Logging**: All auth/admin actions logged with IP/user agent
- **Origin Lock**: Tunnel-only external access via shared secret

#### Database Layer (`backend/app/db/`)
- **ORM**: SQLAlchemy with Declarative Base
- **Migration**: Alembic for schema versioning
- **Models**:
  - `User`: User accounts with roles/status
  - `Session`: Authentication sessions
  - `Invite`: Registration invites
  - `Conversation`: Chat conversations
  - `Message`: Individual messages with token usage
  - `AuditLog`: Security event log
  - `UserQuota`: Per-user rate limits
  - `UserUsageDaily`: Daily usage tracking

#### Provider Abstraction (`backend/app/providers/`)
- **Interface**: Common `Provider` base class with required methods
- **Implementations**:
  - `LMStudioProvider`: Local LM Studio integration
  - `OllamaProvider`: Local Ollama integration
  - `OpenAICompatProvider`: Generic OpenAI-compatible API
- **Registry**: Singleton provider registry with lazy loading

#### Services Layer (`backend/app/services/`)
- **Chat Service**: Conversation and message management
- **Generation Manager**: Async task coordination for streaming
- **Quota Service**: Rate limiting and usage tracking
- **Rate Limit**: IP and user-based request throttling

#### Observability (`backend/app/observability/`)
- **Logging**: Structured JSON logs with request IDs
- **Request Middleware**: Automatic request ID injection
- **Error Handling**: Normalized error responses with correlation IDs

#### Configuration (`backend/app/config/`)
- **Settings**: Pydantic-based configuration with env file support
- **Environment Detection**: Automatic cookie security settings

### External Dependencies
- **Database**: SQLite (default) with Postgres upgrade path
- **HTTP Client**: httpx for async provider communication
- **Password Hashing**: passlib with argon2
- **Validation**: Pydantic for request/response models
- **CORS**: FastAPI CORSMiddleware with allowlist
- **Deployment**: Cloudflare Tunnel or ngrok for external access

## Security Architecture

### Threat Mitigation

#### Authentication Bypass
- **HttpOnly Cookies**: Session tokens not accessible to JavaScript
- **Secure Cookies**: HTTPS-only in production
- **Session Expiry**: Automatic cleanup of expired sessions
- **Origin Lock**: External access requires tunnel header

#### CSRF Attacks
- **CSRF Tokens**: HMAC-derived tokens for state-changing requests
- **SameSite Cookies**: Lax/None based on deployment
- **Request Validation**: All POST/PATCH/DELETE require CSRF

#### Data Exposure
- **No Stack Traces**: Normalized error responses
- **Audit Logging**: All security-relevant actions tracked
- **Input Validation**: Pydantic models prevent injection
- **SQL Injection**: ORM prevents raw SQL injection

#### Denial of Service
- **Rate Limiting**: Per-IP and per-user request limits
- **Quota Enforcement**: Daily message/token limits
- **Request Size Limits**: Prevent oversized payloads
- **Timeout Handling**: Provider request timeouts prevent hanging

#### Man-in-the-Middle
- **HTTPS Everywhere**: GitHub Pages + tunnel enforce TLS
- **CORS Allowlist**: Strict origin validation
- **Header Validation**: Origin lock secret verification

### Data Flow Security

1. **Frontend Request**: JavaScript sends credentials-included request
2. **CORS Validation**: Backend checks origin against allowlist
3. **Origin Lock**: Tunnel header validated for external access
4. **Session Validation**: Cookie checked for valid session
5. **CSRF Validation**: Token verified for state-changing requests
6. **Rate Limit Check**: IP and user limits enforced
7. **Quota Check**: Daily usage limits validated
8. **Provider Call**: Secrets stay backend-only, requests proxied
9. **Response**: Sanitized data returned to frontend

## Deployment Architecture

### Local Development
- **Backend**: Direct Uvicorn on 127.0.0.1:8787
- **Frontend**: Local HTTP server on port 5173
- **Providers**: Local LM Studio/Ollama instances

### Production Deployment
- **Frontend**: GitHub Pages static hosting
- **Backend**: Local FastAPI server behind tunnel
- **External Access**: Cloudflare Tunnel (preferred) or ngrok
- **Database**: SQLite in repo-root data/ directory
- **Secrets**: .env file (not committed)

### Scaling Considerations
- **Database**: SQLite suitable for single-user deployment
- **Sessions**: In-memory (upgrade to Redis for multi-instance)
- **Rate Limits**: In-memory (upgrade to Redis for distributed)
- **Providers**: Local instances (no scaling needed)

## Error Handling

### Error Response Format
All API errors return consistent structure:
```json
{
  "code": "STABLE_ERROR_CODE",
  "message": "User-safe message",
  "request_id": "correlation-id",
  "detail": "Optional additional info"
}
```

### Error Codes
- `AUTH_REQUIRED`: Missing/invalid session
- `SESSION_EXPIRED`: Session timed out
- `CSRF_INVALID`: Invalid CSRF token
- `USER_INACTIVE`: Account disabled
- `INVALID_INVITE`: Bad invite code
- `USERNAME_EXISTS`: Duplicate username
- `CONVERSATION_NOT_FOUND`: Invalid conversation ID
- `MODEL_NOT_FOUND`: Provider model unavailable
- `PROVIDER_UNREACHABLE`: Provider offline
- `PROVIDER_TIMEOUT`: Request timed out
- `QUOTA_EXCEEDED`: Usage limit reached
- `RATE_LIMITED`: Too many requests
- `ADMIN_REQUIRED`: Insufficient privileges

## Monitoring & Observability

### Health Checks
- **GET /health**: Basic service health
- **GET /health/deep**: DB connectivity check (origin-lock protected)

### Logging
- **Structured JSON**: All logs include request IDs
- **Log Levels**: INFO for requests, ERROR for failures
- **Request Tracing**: Automatic request ID middleware

### Metrics (Future)
- Request latency
- Error rates
- Provider response times
- Daily usage statistics

## Future Architecture Extensions

### Multi-Instance Scaling
- Redis for session/cancel state
- Distributed rate limiting
- Database connection pooling

### Advanced Features
- Vision model support
- Tool/function calling
- Conversation branching
- Export/import functionality

### Enterprise Features
- LDAP/SSO integration
- Advanced audit features
- Compliance reporting
- Multi-tenant isolation