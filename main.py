import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
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

    response = requests.post(lm_studio_url, json=payload, timeout=timeout_seconds)
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
async def chat(request: ChatRequest):
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
async def chat_root_alias(request: ChatRequest):
    return await chat(request)


@app.get("/api/models", response_model=ModelsResponse)
async def get_models():
    models = list_lm_studio_models()
    return ModelsResponse(models=models)
