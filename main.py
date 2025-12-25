import os
import time
import hmac
import json
import uuid
import hashlib
import sqlite3
import secrets
import re
from datetime import datetime, timedelta
from collections import defaultdict, deque
from threading import Lock
from typing import Any, Literal

import requests
from fastapi import FastAPI, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from services.logging_utils import (
    configure_logging,
    request_id_ctx,
    user_id_ctx,
    path_ctx,
    method_ctx,
    client_ip_ctx,
)
from services.tool_registry import TOOL_REGISTRY

app = FastAPI()
logger = configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

# CORS SETTINGS - update origins as needed
# -----------------------------------------------------------
raw_origins = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://omniplexity.github.io,https://rossie-chargeful-plentifully.ngrok-free.dev"
    ).split(",")
    if origin.strip()
]

# Allow an "*" entry in ALLOWED_ORIGINS but still echo the caller's Origin
# header so credentialed requests are permitted. Browsers reject credentials
# when ACAO is "*".
allowed_origins: list[str] = []
allow_origin_regex: str | None = None

for origin in raw_origins:
    cleaned = origin.rstrip("/")
    if cleaned == "*":
        allow_origin_regex = r"https?://.*"
        continue
    allowed_origins.append(cleaned)

# Always allow localhost/127.0.0.1 on any port for dev, unless a broader regex is already provided.
if allow_origin_regex is None:
    allow_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------
# AUTH / USER STORE
# -----------------------------------------------------------
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "app.db"))
AUTH_SECRET = os.environ.get("AUTH_SECRET", "change-me")
SESSION_COOKIE = "omni_session"
SESSION_HOURS = float(os.environ.get("SESSION_HOURS", "8"))
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() in ("1", "true", "yes")
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "120"))
RATE_LIMIT_EXEMPT_PATHS = {"/metrics"}

DEFAULT_THEME_MODE = os.environ.get("DEFAULT_THEME_MODE", "light")
DEFAULT_GRADIENT_START = os.environ.get("DEFAULT_GRADIENT_START", "#0b84ff")
DEFAULT_GRADIENT_END = os.environ.get("DEFAULT_GRADIENT_END", "#0c9eff")
DEFAULT_GRADIENT_ANGLE = int(os.environ.get("DEFAULT_GRADIENT_ANGLE", "140"))

SD_WEBUI_URL = os.environ.get("SD_WEBUI_URL", "").strip()
SD_WEBUI_TIMEOUT = float(os.environ.get("SD_WEBUI_TIMEOUT", "120"))
SD_WEBUI_STEPS = int(os.environ.get("SD_WEBUI_STEPS", "30"))
SD_WEBUI_CFG_SCALE = float(os.environ.get("SD_WEBUI_CFG_SCALE", "7"))
SD_WEBUI_WIDTH = int(os.environ.get("SD_WEBUI_WIDTH", "512"))
SD_WEBUI_HEIGHT = int(os.environ.get("SD_WEBUI_HEIGHT", "512"))
SD_WEBUI_SAMPLER = os.environ.get("SD_WEBUI_SAMPLER", "Euler a")

DEFAULT_ALLOWED_TOOLS = {
    name.strip()
    for name in os.environ.get("DEFAULT_ALLOWED_TOOLS", "web_search").split(",")
    if name.strip()
}

def load_model_tool_allowlist() -> dict[str, set[str]]:
    raw = os.environ.get("MODEL_TOOL_ALLOWLIST", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid MODEL_TOOL_ALLOWLIST JSON; ignoring")
        return {}
    mapping: dict[str, set[str]] = {}
    if isinstance(parsed, dict):
        for model_name, tools in parsed.items():
            if isinstance(tools, list):
                mapping[model_name] = {str(t) for t in tools}
    return mapping

MODEL_TOOL_ALLOWLIST = load_model_tool_allowlist()

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()

    # Conversation threads (per user) and messages
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES threads(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_threads_user_id ON threads(user_id);")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            theme_mode TEXT NOT NULL,
            gradient_start TEXT NOT NULL,
            gradient_end TEXT NOT NULL,
            gradient_angle INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_tools (
            user_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, tool_name),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tool_name TEXT NOT NULL,
            input TEXT,
            status TEXT NOT NULL,
            duration_ms REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    cur.execute("SELECT COUNT(*) AS c FROM users")
    count = cur.fetchone()["c"]
    if count == 0:
        admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@example.com")
        admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "change-this")
        add_user(conn, admin_email, admin_password, True)
        logger.info("bootstrap_admin_created", extra={"event": "bootstrap"})
    conn.close()

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 600_000)
    return f"pbkdf2${salt}${dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, hex_hash = stored.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 600_000)
        return hmac.compare_digest(dk.hex(), hex_hash)
    except Exception:
        return False

def add_user(conn, email: str, password: str, is_admin: bool = False):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (email, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
        (email.lower().strip(), hash_password(password), 1 if is_admin else 0, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return cur.lastrowid

def get_user_by_email(conn, email: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    return cur.fetchone()

def get_user_by_id(conn, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()

def list_users(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, email, is_admin, created_at FROM users ORDER BY created_at DESC")
    return [dict(r) for r in cur.fetchall()]


def get_user_settings(conn, user_id: int):
    cur = conn.cursor()
    cur.execute(
        "SELECT theme_mode, gradient_start, gradient_end, gradient_angle FROM user_settings WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def upsert_user_settings(conn, user_id: int, settings: dict[str, Any]):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_settings (user_id, theme_mode, gradient_start, gradient_end, gradient_angle, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            theme_mode = excluded.theme_mode,
            gradient_start = excluded.gradient_start,
            gradient_end = excluded.gradient_end,
            gradient_angle = excluded.gradient_angle,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            settings["theme_mode"],
            settings["gradient_start"],
            settings["gradient_end"],
            settings["gradient_angle"],
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()


def list_user_tool_preferences(conn, user_id: int) -> dict[str, bool]:
    cur = conn.cursor()
    cur.execute("SELECT tool_name, enabled FROM user_tools WHERE user_id = ?", (user_id,))
    return {row["tool_name"]: bool(row["enabled"]) for row in cur.fetchall()}


def set_user_tool_preference(conn, user_id: int, tool_name: str, enabled: bool):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_tools (user_id, tool_name, enabled, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, tool_name)
        DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at
        """,
        (user_id, tool_name, 1 if enabled else 0, datetime.utcnow().isoformat()),
    )
    conn.commit()


def record_tool_usage(
    conn,
    user_id: int | None,
    tool_name: str,
    input_payload: dict[str, Any],
    status: str,
    duration_ms: float | None,
):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tool_usage (user_id, tool_name, input, status, duration_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            tool_name,
            json.dumps(input_payload, ensure_ascii=True),
            status,
            duration_ms,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()


def list_tool_usage(conn, limit: int = 50):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, user_id, tool_name, input, status, duration_ms, created_at
        FROM tool_usage
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (int(limit),),
    )
    return [dict(r) for r in cur.fetchall()]

# -----------------------------------------------------------
# THREADS / MESSAGES
# -----------------------------------------------------------
def ensure_thread_owner(conn, thread_id: int, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, title, created_at, updated_at FROM threads WHERE id = ?", (thread_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Thread not found")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return row

def create_thread(conn, user_id: int, title: str):
    now = datetime.utcnow().isoformat()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO threads (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, title.strip() or "New chat", now, now),
    )
    conn.commit()
    return cur.lastrowid

def list_threads(conn, user_id: int):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, created_at, updated_at
        FROM threads
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    return [dict(r) for r in cur.fetchall()]

def rename_thread(conn, thread_id: int, user_id: int, title: str):
    ensure_thread_owner(conn, thread_id, user_id)
    cur = conn.cursor()
    cur.execute(
        "UPDATE threads SET title = ?, updated_at = ? WHERE id = ?",
        (title.strip() or "Untitled chat", datetime.utcnow().isoformat(), thread_id),
    )
    conn.commit()

def delete_thread(conn, thread_id: int, user_id: int):
    ensure_thread_owner(conn, thread_id, user_id)
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
    cur.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
    conn.commit()

def list_thread_messages(conn, thread_id: int, user_id: int):
    ensure_thread_owner(conn, thread_id, user_id)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, role, content, created_at
        FROM messages
        WHERE thread_id = ?
        ORDER BY id ASC
        """,
        (thread_id,),
    )
    return [dict(r) for r in cur.fetchall()]

def append_message(conn, thread_id: int, user_id: int, role: str, content: str):
    ensure_thread_owner(conn, thread_id, user_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (thread_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (thread_id, user_id, role, content, datetime.utcnow().isoformat()),
    )
    cur.execute(
        "UPDATE threads SET updated_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), thread_id),
    )
    conn.commit()

def request_is_secure(request: Request) -> bool:
    """
    Determine whether the client connection is effectively HTTPS.
    Honors reverse-proxy X-Forwarded-Proto if present.
    """
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.lower() == "https"

def cookie_flags_for_request(request: Request):
    """
    Return kwargs for setting/deleting the session cookie with consistent flags.
    """
    secure_cookie = request_is_secure(request)
    same_site = "none" if secure_cookie else "lax"
    return {
        "httponly": True,
        "secure": secure_cookie,
        "samesite": same_site,
        "path": "/",
    }

def sign_session(user_id: int, is_admin: bool) -> str:
    exp = int((datetime.utcnow() + timedelta(hours=SESSION_HOURS)).timestamp())
    payload = f"{user_id}:{int(is_admin)}:{exp}"
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"

def verify_session(token: str):
    try:
        user_id_str, is_admin_str, exp_str, sig = token.split(":")
        payload = f"{user_id_str}:{is_admin_str}:{exp_str}"
        expected = hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        if datetime.utcnow().timestamp() > float(exp_str):
            return None
        return {"user_id": int(user_id_str), "is_admin": bool(int(is_admin_str))}
    except Exception:
        return None

def current_user(request: Request, required: bool = True):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        if required:
            raise HTTPException(status_code=401, detail="Not authenticated")
        return None
    claims = verify_session(token)
    if not claims:
        if required:
            raise HTTPException(status_code=401, detail="Session invalid")
        return None
    conn = get_db()
    user_row = get_user_by_id(conn, claims["user_id"])
    conn.close()
    if not user_row:
        if required:
            raise HTTPException(status_code=401, detail="User not found")
        return None
    return {"id": user_row["id"], "email": user_row["email"], "is_admin": bool(user_row["is_admin"])}

def require_user(request: Request):
    return current_user(request, required=True)

def require_admin(request: Request):
    user = current_user(request, required=True)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> tuple[bool, int | None]:
        now = time.time()
        with self._lock:
            events = self._events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.max_requests:
                retry_after = int(self.window_seconds - (now - events[0]))
                return False, max(retry_after, 1)
            events.append(now)
        return True, None


rate_limiter = None
if RATE_LIMIT_ENABLED:
    rate_limiter = SlidingWindowRateLimiter(RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def allowed_tools_for_model(model_name: str | None) -> set[str]:
    if not model_name:
        return DEFAULT_ALLOWED_TOOLS
    if model_name in MODEL_TOOL_ALLOWLIST:
        return MODEL_TOOL_ALLOWLIST[model_name]
    if "*" in MODEL_TOOL_ALLOWLIST:
        return MODEL_TOOL_ALLOWLIST["*"]
    return DEFAULT_ALLOWED_TOOLS


def is_valid_hex_color(value: str) -> bool:
    return bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", value or ""))


# -----------------------------------------------------------
# REQUEST CONTEXT + LOGGING + RATE LIMITING
# -----------------------------------------------------------
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = None
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id

    token_request = request_id_ctx.set(request_id)
    token_path = path_ctx.set(request.url.path)
    token_method = method_ctx.set(request.method)
    client_ip = get_client_ip(request)
    token_client_ip = client_ip_ctx.set(client_ip)

    claims = None
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        claims = verify_session(token)
    user_id = claims.get("user_id") if claims else None
    token_user = user_id_ctx.set(user_id)
    if user_id is not None:
        request.state.user_id = user_id

    try:
        if rate_limiter and request.method != "OPTIONS" and request.url.path not in RATE_LIMIT_EXEMPT_PATHS:
            key = f"user:{user_id}" if user_id is not None else f"ip:{client_ip or 'unknown'}"
            allowed, retry_after = rate_limiter.allow(key)
            if not allowed:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded", "request_id": request_id},
                    headers={"Retry-After": str(retry_after)},
                )
                return response

        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        status = response.status_code if response else 500
        logger.info(
            "request_complete",
            extra={
                "event": "http_request",
                "status": status,
                "latency_ms": round(duration_ms, 2),
                "path": request.url.path,
                "method": request.method,
                "client_ip": client_ip,
                "request_id": request_id,
                "user_id": user_id,
            },
        )
        if response is not None:
            response.headers["x-request-id"] = request_id
            origin = request.headers.get("origin")
            acao = response.headers.get("access-control-allow-origin")
            if origin and acao == "*":
                response.headers["access-control-allow-origin"] = origin

        request_id_ctx.reset(token_request)
        path_ctx.reset(token_path)
        method_ctx.reset(token_method)
        client_ip_ctx.reset(token_client_ip)
        user_id_ctx.reset(token_user)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    if exc.status_code >= 500:
        logger.error("http_exception", extra={"event": "error", "status": exc.status_code, "error": str(exc.detail)})
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("unhandled_exception", extra={"event": "error", "request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )

# -----------------------------------------------------------
# REQUEST & RESPONSE MODELS
# -----------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    use_search: bool = False
    search_query: str | None = None
    thread_id: int | None = Field(default=None, description="Associate this message with a conversation thread")
    model: str | None = Field(
        default=None,
        description="Override LM Studio model; falls back to LM_STUDIO_MODEL env"
    )
    system_prompt: str | None = Field(
        default=None,
        description="Optional system prompt to steer responses"
    )
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0)

class ChatResponse(BaseModel):
    response: str

class ModelsResponse(BaseModel):
    models: list[str]
    default_model: str | None = None

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    email: str
    is_admin: bool

class CreateUserRequest(BaseModel):
    email: str
    password: str
    is_admin: bool = False

class UserOut(BaseModel):
    id: int
    email: str
    is_admin: bool
    created_at: str

class ThreadOut(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str

class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    execution: str
    enabled: bool
    default_enabled: bool
    allowed_for_model: bool


class ToolToggleRequest(BaseModel):
    enabled: bool


class ToolCallRequest(BaseModel):
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None


class ToolCallResponse(BaseModel):
    result: dict[str, Any]


class UserSettingsRequest(BaseModel):
    theme_mode: Literal["light", "dark"] | None = None
    gradient_start: str | None = None
    gradient_end: str | None = None
    gradient_angle: int | None = Field(default=None, ge=0, le=360)


class UserSettingsResponse(BaseModel):
    theme_mode: str
    gradient_start: str
    gradient_end: str
    gradient_angle: int


class ToolUsageOut(BaseModel):
    id: int
    user_id: int | None = None
    tool_name: str
    input: str | None = None
    status: str
    duration_ms: float | None = None
    created_at: str


class ImageGenerateRequest(BaseModel):
    prompt: str
    model: str | None = None
    negative_prompt: str | None = None
    width: int | None = Field(default=None, ge=64, le=2048)
    height: int | None = Field(default=None, ge=64, le=2048)
    steps: int | None = Field(default=None, ge=1, le=150)
    cfg_scale: float | None = Field(default=None, ge=0.0, le=30.0)

# -----------------------------------------------------------
# INTERNAL HELPERS
# -----------------------------------------------------------
def call_lm_studio(
    user_message: str,
    model: str | None = None,
    system_prompt: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> str:
    lm_studio_url = os.environ.get(
        "LM_STUDIO_URL",
        "http://10.0.0.198:11434/v1/chat/completions"
    )
    # Allow slow-to-start models (e.g., large vision models) to complete by making the timeout configurable
    timeout_seconds = float(os.environ.get("LM_STUDIO_TIMEOUT", "120"))
    max_retries = int(os.environ.get("LM_STUDIO_RETRIES", "2"))

    selected_model = model or os.environ.get(
        "LM_STUDIO_MODEL",
        "qwen3-vl-4b-thinking-1m"
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": selected_model,
        "messages": messages,
        "stream": False
    }

    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(lm_studio_url, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            break
        except Exception as exc:
            if attempt >= max_retries:
                detail = response.text if 'response' in locals() and response is not None else str(exc)
                logger.error(
                    "lm_studio_request_failed",
                    extra={"event": "lm_studio", "error": detail, "model": selected_model},
                )
                raise HTTPException(status_code=502, detail=f"LM Studio upstream error: {detail}")
            time.sleep(0.5 * (attempt + 1))

    data = response.json()
    choices = data.get("choices") or []
    reply_text = ""
    if choices:
        reply_text = choices[0].get("message", {}).get("content", "") or ""

    if reply_text == "":
        logger.warning(
            "lm_studio_empty_response",
            extra={"event": "lm_studio", "model": selected_model},
        )

    return reply_text


def list_lm_studio_models() -> list[str]:
    """
    Query the LM Studio OpenAI-compatible /v1/models endpoint.
    """
    lm_studio_url = os.environ.get(
        "LM_STUDIO_URL",
        "http://10.0.0.198:11434/v1/chat/completions"
    )
    # Derive base /v1 prefix
    if "/v1/" in lm_studio_url:
        base = lm_studio_url.split("/v1/", 1)[0] + "/v1/models"
    else:
        base = lm_studio_url.rstrip("/") + "/v1/models"

    try:
        resp = requests.get(base, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        model_list = [m.get("id") for m in data.get("data", []) if m.get("id")]
        return model_list
    except Exception as exc:
        logger.error("lm_studio_model_list_failed", extra={"event": "lm_studio", "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"LM Studio model list failed: {str(exc)}")


def build_tool_info(tool, enabled: bool, model: str | None) -> ToolInfo:
    allowed = tool.name in allowed_tools_for_model(model)
    return ToolInfo(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema(),
        execution=tool.execution,
        enabled=enabled,
        default_enabled=tool.default_enabled,
        allowed_for_model=allowed,
    )


def ensure_tool_allowed(tool_name: str, user_id: int, model: str | None) -> None:
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    allowed = tool_name in allowed_tools_for_model(model)
    if not allowed:
        raise HTTPException(status_code=403, detail="Tool not allowed for this model")

    conn = get_db()
    prefs = list_user_tool_preferences(conn, user_id)
    conn.close()
    enabled = prefs.get(tool_name, tool.default_enabled)
    if not enabled:
        raise HTTPException(status_code=403, detail="Tool disabled for this user")


def execute_tool(tool_name: str, input_payload: dict[str, Any], user_id: int | None, model: str | None):
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if tool.execution != "in_process":
        raise HTTPException(status_code=501, detail="Tool execution via MCP Docker is not configured")

    try:
        payload = tool.input_model(**input_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid tool input: {str(exc)}")

    start = time.perf_counter()
    status = "ok"
    result: dict[str, Any] | None = None
    try:
        result = tool.invoke(payload)
        return result
    except Exception as exc:
        status = "error"
        logger.exception("tool_execution_failed", extra={"event": "tool", "tool": tool_name, "error": str(exc)})
        raise HTTPException(status_code=500, detail="Tool execution failed")
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        try:
            conn = get_db()
            record_tool_usage(conn, user_id, tool_name, input_payload, status, duration_ms)
            conn.close()
        except Exception as exc:
            logger.warning("tool_usage_log_failed", extra={"event": "tool", "tool": tool_name, "error": str(exc)})


def generate_stable_diffusion_images(payload: ImageGenerateRequest) -> list[str]:
    if not SD_WEBUI_URL:
        raise HTTPException(status_code=501, detail="Stable Diffusion backend not configured")

    url = SD_WEBUI_URL.rstrip("/") + "/sdapi/v1/txt2img"
    request_payload = {
        "prompt": payload.prompt,
        "steps": payload.steps or SD_WEBUI_STEPS,
        "cfg_scale": payload.cfg_scale or SD_WEBUI_CFG_SCALE,
        "width": payload.width or SD_WEBUI_WIDTH,
        "height": payload.height or SD_WEBUI_HEIGHT,
        "sampler_name": SD_WEBUI_SAMPLER,
    }
    if payload.negative_prompt:
        request_payload["negative_prompt"] = payload.negative_prompt
    if payload.model:
        request_payload["override_settings"] = {"sd_model_checkpoint": payload.model}

    try:
        response = requests.post(url, json=request_payload, timeout=SD_WEBUI_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.error("image_generation_failed", extra={"event": "image", "error": str(exc)})
        raise HTTPException(status_code=502, detail="Image generation failed")

    images = data.get("images") or []
    if not images:
        raise HTTPException(status_code=502, detail="Image generation returned no images")
    return images

# -----------------------------------------------------------
# HEALTH CHECK
# -----------------------------------------------------------
@app.get("/")
async def root():
    return {"status": "Backend is running"}

# -----------------------------------------------------------
# MAIN MODEL CHAT ENDPOINT
# -----------------------------------------------------------
@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user=Depends(require_user)):
    user_message = request.message
    thread_id = request.thread_id
    conn = None
    if thread_id is not None:
        conn = get_db()
        ensure_thread_owner(conn, thread_id, user["id"])

    # Optional tool use: prepend web search results if requested
    if request.use_search or request.search_query:
        try:
            query = request.search_query or request.message
            model_for_tools = request.model or os.environ.get("LM_STUDIO_MODEL")
            ensure_tool_allowed("web_search", user["id"], model_for_tools)
            tool_result = execute_tool(
                "web_search",
                {"query": query, "max_results": 5},
                user_id=user["id"],
                model=model_for_tools,
            )
            search_snippets = tool_result.get("results", [])
            tool_context = "\n".join(
                f"- {item['title']} - {item['snippet']}" for item in search_snippets
            )
            user_message = (
                f"{request.message}\n\n"
                f"Web search results for '{query}':\n{tool_context}\n"
                "Use these results to answer concisely."
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("web_search_failed", extra={"event": "tool", "tool": "web_search", "error": str(e)})
            # Continue without search context

    try:
        reply_text = call_lm_studio(
            user_message=user_message,
            model=request.model,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            top_p=request.top_p,
            max_tokens=request.max_tokens,
        )
        if thread_id is not None:
            append_message(conn, thread_id, user["id"], "user", request.message)
            append_message(conn, thread_id, user["id"], "assistant", reply_text)
            conn.close()
        return ChatResponse(response=reply_text)
    except HTTPException:
        # Already an HTTP-friendly error
        raise
    except Exception as e:
        logger.error("lm_studio_error", extra={"event": "lm_studio", "error": str(e)})
        if conn:
            conn.close()
        raise HTTPException(
            status_code=500,
            detail=f"LM Studio error: {str(e)}"
        )

# Convenience alias: POST / forwards to /api/chat to avoid 405s from misconfigured clients
@app.post("/", response_model=ChatResponse)
async def chat_root_alias(request: ChatRequest, user=Depends(require_user)):
    return await chat(request, user=user)


@app.get("/api/models", response_model=ModelsResponse)
async def get_models(user=Depends(require_user)):
    models = list_lm_studio_models()
    default_model = os.environ.get("LM_STUDIO_MODEL") or (models[0] if models else None)
    return ModelsResponse(models=models, default_model=default_model)

# -----------------------------------------------------------
# TOOLS
# -----------------------------------------------------------
@app.get("/api/tools", response_model=list[ToolInfo])
async def list_tools(model: str | None = None, user=Depends(require_user)):
    effective_model = model or os.environ.get("LM_STUDIO_MODEL")
    conn = get_db()
    prefs = list_user_tool_preferences(conn, user["id"])
    conn.close()
    tools: list[ToolInfo] = []
    for tool in TOOL_REGISTRY.list_tools():
        enabled = prefs.get(tool.name, tool.default_enabled)
        tools.append(build_tool_info(tool, enabled, effective_model))
    return tools


@app.patch("/api/tools/{tool_name}", response_model=ToolInfo)
async def update_tool(tool_name: str, payload: ToolToggleRequest, user=Depends(require_user)):
    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    conn = get_db()
    set_user_tool_preference(conn, user["id"], tool_name, payload.enabled)
    conn.close()
    return build_tool_info(tool, payload.enabled, os.environ.get("LM_STUDIO_MODEL"))


@app.post("/api/tools/execute", response_model=ToolCallResponse)
async def execute_tool_route(payload: ToolCallRequest, user=Depends(require_user)):
    model = payload.model or os.environ.get("LM_STUDIO_MODEL")
    ensure_tool_allowed(payload.name, user["id"], model)
    result = execute_tool(payload.name, payload.input, user_id=user["id"], model=model)
    return ToolCallResponse(result=result)


# -----------------------------------------------------------
# USER SETTINGS
# -----------------------------------------------------------
@app.get("/api/settings", response_model=UserSettingsResponse)
async def get_settings(user=Depends(require_user)):
    conn = get_db()
    settings = get_user_settings(conn, user["id"])
    conn.close()
    if not settings:
        settings = {
            "theme_mode": DEFAULT_THEME_MODE,
            "gradient_start": DEFAULT_GRADIENT_START,
            "gradient_end": DEFAULT_GRADIENT_END,
            "gradient_angle": DEFAULT_GRADIENT_ANGLE,
        }
    return UserSettingsResponse(**settings)


@app.put("/api/settings", response_model=UserSettingsResponse)
async def update_settings(payload: UserSettingsRequest, user=Depends(require_user)):
    updates = payload.model_dump(exclude_none=True) if hasattr(payload, "model_dump") else payload.dict(exclude_none=True)
    if "gradient_start" in updates and not is_valid_hex_color(updates["gradient_start"]):
        raise HTTPException(status_code=400, detail="Invalid gradient_start color")
    if "gradient_end" in updates and not is_valid_hex_color(updates["gradient_end"]):
        raise HTTPException(status_code=400, detail="Invalid gradient_end color")
    conn = get_db()
    current = get_user_settings(conn, user["id"]) or {
        "theme_mode": DEFAULT_THEME_MODE,
        "gradient_start": DEFAULT_GRADIENT_START,
        "gradient_end": DEFAULT_GRADIENT_END,
        "gradient_angle": DEFAULT_GRADIENT_ANGLE,
    }
    current.update(updates)
    upsert_user_settings(conn, user["id"], current)
    conn.close()
    return UserSettingsResponse(**current)

# -----------------------------------------------------------
# THREADS & MESSAGES
# -----------------------------------------------------------
@app.post("/api/threads", response_model=ThreadOut)
async def api_create_thread(payload: dict, user=Depends(require_user)):
    title = (payload.get("title") or "New chat") if isinstance(payload, dict) else "New chat"
    conn = get_db()
    thread_id = create_thread(conn, user["id"], title)
    row = ensure_thread_owner(conn, thread_id, user["id"])
    conn.close()
    return ThreadOut(**row)

@app.get("/api/threads", response_model=list[ThreadOut])
async def api_list_threads(user=Depends(require_user)):
    conn = get_db()
    rows = list_threads(conn, user["id"])
    conn.close()
    return [ThreadOut(**r) for r in rows]

@app.patch("/api/threads/{thread_id}", response_model=ThreadOut)
async def api_rename_thread(thread_id: int, payload: dict, user=Depends(require_user)):
    new_title = (payload.get("title") or "").strip() if isinstance(payload, dict) else ""
    if not new_title:
        raise HTTPException(status_code=400, detail="Title required")
    conn = get_db()
    rename_thread(conn, thread_id, user["id"], new_title)
    row = ensure_thread_owner(conn, thread_id, user["id"])
    conn.close()
    return ThreadOut(**row)

@app.delete("/api/threads/{thread_id}")
async def api_delete_thread(thread_id: int, user=Depends(require_user)):
    conn = get_db()
    delete_thread(conn, thread_id, user["id"])
    conn.close()
    return {"status": "deleted"}

@app.get("/api/threads/{thread_id}/messages", response_model=list[MessageOut])
async def api_get_thread_messages(thread_id: int, user=Depends(require_user)):
    conn = get_db()
    messages = list_thread_messages(conn, thread_id, user["id"])
    conn.close()
    return [MessageOut(**m) for m in messages]

# -----------------------------------------------------------
# AUTH ROUTES
# -----------------------------------------------------------
@app.post("/api/auth/login", response_model=LoginResponse)
async def auth_login(payload: LoginRequest, response: Response, request: Request):
    conn = get_db()
    user = get_user_by_email(conn, payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = sign_session(user["id"], bool(user["is_admin"]))
    cookie_args = cookie_flags_for_request(request)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_HOURS * 3600),
        **cookie_args,
    )
    conn.close()
    return LoginResponse(email=user["email"], is_admin=bool(user["is_admin"]))

@app.post("/api/auth/logout")
async def auth_logout(response: Response, request: Request):
    cookie_args = cookie_flags_for_request(request)
    response.delete_cookie(SESSION_COOKIE, **cookie_args)
    return {"status": "logged out"}

@app.get("/api/auth/me", response_model=LoginResponse)
async def auth_me(user=Depends(require_user)):
    return LoginResponse(email=user["email"], is_admin=user["is_admin"])

@app.post("/api/users", response_model=UserOut)
async def create_user(payload: CreateUserRequest, admin=Depends(require_admin)):
    conn = get_db()
    try:
        user_id = add_user(conn, payload.email, payload.password, payload.is_admin)
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="User already exists")
    user_row = get_user_by_id(conn, user_id)
    conn.close()
    return UserOut(
        id=user_row["id"],
        email=user_row["email"],
        is_admin=bool(user_row["is_admin"]),
        created_at=user_row["created_at"],
    )

@app.get("/api/users", response_model=list[UserOut])
async def list_users_route(admin=Depends(require_admin)):
    conn = get_db()
    users = list_users(conn)
    conn.close()
    return [UserOut(**u) for u in users]


@app.get("/api/admin/tool-usage", response_model=list[ToolUsageOut])
async def admin_tool_usage(limit: int = 50, admin=Depends(require_admin)):
    conn = get_db()
    usage = list_tool_usage(conn, limit=limit)
    conn.close()
    return [ToolUsageOut(**u) for u in usage]

# -----------------------------------------------------------
# IMAGE GENERATION (placeholder)
# -----------------------------------------------------------
@app.post("/api/image/generate")
async def generate_image(payload: ImageGenerateRequest, user=Depends(require_user)):
    images = generate_stable_diffusion_images(payload)
    return {"images": images}


# -----------------------------------------------------------
# METRICS
# -----------------------------------------------------------
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


# Ensure tables exist on import
init_db()
