import os
import time
import hmac
import hashlib
import sqlite3
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
import requests
from services.tooling import web_search

app = FastAPI()

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

    cur.execute("SELECT COUNT(*) AS c FROM users")
    count = cur.fetchone()["c"]
    if count == 0:
        admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@example.com")
        admin_password = os.environ.get("DEFAULT_ADMIN_PASSWORD", "change-this")
        add_user(conn, admin_email, admin_password, True)
        print(f"Bootstrap admin created: {admin_email}")
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

def request_is_secure(request: Request) -> bool:
    """
    Determine whether the client connection is effectively HTTPS.
    Honors reverse-proxy X-Forwarded-Proto if present.
    """
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto.lower() == "https"

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

# -----------------------------------------------------------
# SIMPLE REQUEST LOGGING
# -----------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        path = request.url.path
        method = request.method
        status = getattr(response, "status_code", "unknown")
        print(f"{method} {path} -> {status} ({duration_ms:.1f} ms)")

# -----------------------------------------------------------
# REQUEST & RESPONSE MODELS
# -----------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    use_search: bool = False
    search_query: str | None = None
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
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(lm_studio_url, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            break
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                detail = response.text if 'response' in locals() and response is not None else str(exc)
                raise HTTPException(status_code=502, detail=f"LM Studio upstream error: {detail}")
            time.sleep(0.5 * (attempt + 1))

    data = response.json()
    choices = data.get("choices") or []
    reply_text = ""
    if choices:
        reply_text = choices[0].get("message", {}).get("content", "") or ""

    if reply_text == "":
        # Surface more debug info to the server logs
        print("WARNING: LM Studio returned no text. Raw data:", data)

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
        print("ERROR fetching LM Studio models:", str(exc))
        raise HTTPException(status_code=502, detail=f"LM Studio model list failed: {str(exc)}")

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

    # Optional tool use: prepend web search results if requested
    if request.use_search or request.search_query:
        try:
            query = request.search_query or request.message
            search_snippets = web_search(query, max_results=5)
            tool_context = "\n".join(
                f"- {item['title']} - {item['snippet']}" for item in search_snippets
            )
            user_message = (
                f"{request.message}\n\n"
                f"Web search results for '{query}':\n{tool_context}\n"
                "Use these results to answer concisely."
            )
        except Exception as e:
            print("WARNING: web search failed:", str(e))
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
        return ChatResponse(response=reply_text)
    except HTTPException:
        # Already an HTTP-friendly error
        raise
    except Exception as e:
        print("ERROR communicating with LM Studio:", str(e))
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
    secure_cookie = request_is_secure(request)
    # Browsers reject "Secure" cookies over http://localhost, so relax for local dev.
    same_site = "none" if secure_cookie else "lax"
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure_cookie,
        samesite=same_site,
        max_age=int(SESSION_HOURS * 3600),
    )
    conn.close()
    return LoginResponse(email=user["email"], is_admin=bool(user["is_admin"]))

@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
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
