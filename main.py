import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import requests
from services.tooling import web_search

app = FastAPI()

# CORS SETTINGS - update origins as needed
# -----------------------------------------------------------
allowed_origins = [
    "https://omniplexity.github.io",
    "https://rossie-chargeful-plentifully.ngrok-free.dev"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------
# REQUEST & RESPONSE MODELS
# -----------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    use_search: bool = False
    search_query: str | None = None

class ChatResponse(BaseModel):
    response: str

# -----------------------------------------------------------
# INTERNAL HELPERS
# -----------------------------------------------------------
def call_lm_studio(user_message: str) -> str:
    lm_studio_url = os.environ.get(
        "LM_STUDIO_URL",
        "http://10.0.0.198:11434/v1/chat/completions"
    )
    payload = {
        "model": os.environ.get(
            "LM_STUDIO_MODEL",
            "qwen3-vl-4b-thinking-1m"
        ),
        "messages": [{"role": "user", "content": user_message}],
        "stream": False
    }

    response = requests.post(lm_studio_url, json=payload, timeout=30)
    # If LM Studio itself errors (e.g., model not loaded), surface the error body
    try:
        response.raise_for_status()
    except Exception as exc:
        detail = response.text if response is not None else str(exc)
        raise HTTPException(status_code=502, detail=f"LM Studio upstream error: {detail}")

    data = response.json()
    choices = data.get("choices") or []
    reply_text = ""
    if choices:
        reply_text = choices[0].get("message", {}).get("content", "") or ""

    if reply_text == "":
        # Surface more debug info to the server logs
        print("WARNING: LM Studio returned no text. Raw data:", data)

    return reply_text

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
async def chat(request: ChatRequest):
    user_message = request.message

    # Optional tool use: prepend web search results if requested
    if request.use_search or request.search_query:
        try:
            query = request.search_query or request.message
            search_snippets = web_search(query, max_results=5)
            tool_context = "\n".join(
                f"- {item['title']} — {item['snippet']}" for item in search_snippets
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
        reply_text = call_lm_studio(user_message)
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
async def chat_root_alias(request: ChatRequest):
    return await chat(request)
