#!/usr/bin/env python3
"""Smoke test for end-to-end SSE streaming against a real provider (LM Studio).

Usage (PowerShell):
  python scripts/smoke_stream.py --base-url http://127.0.0.1:8787 --username admin --password adminpass

Environment fallbacks:
  OMNIAI_BASE_URL, OMNIAI_USERNAME, OMNIAI_PASSWORD, OMNIAI_BOOTSTRAP_TOKEN, OMNIAI_ORIGIN_SECRET
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OmniAI SSE smoke test (LM Studio)")
    parser.add_argument("--base-url", default=os.getenv("OMNIAI_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--username", default=os.getenv("OMNIAI_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("OMNIAI_PASSWORD", "adminpass"))
    parser.add_argument("--bootstrap-token", default=os.getenv("OMNIAI_BOOTSTRAP_TOKEN"))
    parser.add_argument("--origin-secret", default=os.getenv("OMNIAI_ORIGIN_SECRET"))
    parser.add_argument("--provider", default="lmstudio")
    parser.add_argument("--model", default=None)
    parser.add_argument("--message", default="Smoke test: hello from OmniAI")
    parser.add_argument("--stream-timeout", type=float, default=120.0)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def exit_with(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {}


def is_embedding_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return "embedding" in lowered or "embed" in lowered


def is_preferred_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return "instruct" in lowered or "chat" in lowered


def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    headers_base: dict[str, str] = {}
    if args.origin_secret:
        headers_base["X-Origin-Secret"] = args.origin_secret

    client = httpx.Client(base_url=base_url, headers=headers_base, timeout=10.0)

    try:
        health = client.get("/health")
    except Exception as exc:
        exit_with(f"Health check failed: {exc}")

    if health.status_code != 200:
        exit_with(f"Health check failed: HTTP {health.status_code} {health.text}")

    if args.bootstrap_token:
        bootstrap = client.post(
            "/admin/bootstrap",
            headers={**headers_base, "X-Bootstrap-Token": args.bootstrap_token},
            json={"username": args.username, "password": args.password},
        )
        if bootstrap.status_code == 200:
            if not args.quiet:
                print("Admin bootstrap succeeded")
        elif bootstrap.status_code == 403:
            code = safe_json(bootstrap).get("code")
            if code not in ("BOOTSTRAP_DISABLED",):
                exit_with(f"Admin bootstrap failed: {bootstrap.status_code} {bootstrap.text}")
        elif bootstrap.status_code == 409:
            pass
        else:
            exit_with(f"Admin bootstrap failed: {bootstrap.status_code} {bootstrap.text}")

    login = client.post("/auth/login", json={"username": args.username, "password": args.password})
    if login.status_code != 200:
        exit_with(f"Login failed: HTTP {login.status_code} {login.text}")

    login_data = safe_json(login)
    access_token = login_data.get("access_token")
    csrf_token = login_data.get("csrf_token")
    using_session = access_token is None

    def auth_headers(method: str) -> dict[str, str]:
        headers = dict(headers_base)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        if using_session and method.upper() in ("POST", "PATCH", "DELETE"):
            if not csrf_token:
                exit_with("Missing CSRF token for session-authenticated request")
            headers["X-CSRF-Token"] = csrf_token
        return headers

    health = client.get(f"/providers/{args.provider}/health", headers=auth_headers("GET"))
    if health.status_code != 200:
        exit_with(f"Provider health failed: HTTP {health.status_code} {health.text}")
    if not safe_json(health).get("ok"):
        exit_with(f"Provider health reported not ok: {health.text}")

    model = args.model
    if not model:
        models_response = client.get(f"/providers/{args.provider}/models", headers=auth_headers("GET"))
        if models_response.status_code != 200:
            exit_with(f"Provider models failed: HTTP {models_response.status_code} {models_response.text}")
        models = safe_json(models_response).get("models") or []
        if not models:
            exit_with("No models available from provider")
        preferred = []
        non_embedding = []
        for item in models:
            model_id = item.get("id")
            if not model_id:
                continue
            if is_preferred_chat_model(model_id):
                preferred.append(model_id)
            if not is_embedding_model(model_id):
                non_embedding.append(model_id)

        if preferred:
            model = preferred[0]
        elif non_embedding:
            model = non_embedding[0]
        else:
            model = models[0].get("id")
        if not model:
            exit_with("Model list missing id")

    if not args.quiet:
        print(f"Using provider={args.provider} model={model}")

    payload = {
        "message": {"role": "user", "content": args.message},
        "provider": args.provider,
        "model": model,
    }

    stream_timeout = httpx.Timeout(connect=10.0, read=args.stream_timeout, write=10.0, pool=10.0)

    assistant_text = ""
    conversation_id = None
    generation_id = None
    saw_delta = False
    saw_done = False
    current_event = "message"

    with client.stream(
        "POST",
        "/chat/stream",
        json=payload,
        headers=auth_headers("POST"),
        timeout=stream_timeout,
    ) as response:
        if response.status_code != 200:
            exit_with(f"Stream request failed: HTTP {response.status_code} {response.text}")
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            exit_with(f"Unexpected content-type: {content_type}")

        for line in response.iter_lines():
            if line is None:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
                continue
            if line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
                if data_str == "[DONE]":
                    saw_done = True
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if current_event == "meta":
                    conversation_id = data.get("conversation_id", conversation_id)
                    generation_id = data.get("generation_id", generation_id)
                elif current_event == "delta":
                    delta = data.get("delta") or data.get("text") or ""
                    if delta:
                        saw_delta = True
                        assistant_text += delta
                        if not args.quiet:
                            sys.stdout.write(delta)
                            sys.stdout.flush()
                elif current_event == "done":
                    saw_done = True
                    break
            if line == "":
                current_event = "message"

    if not args.quiet:
        print("")

    if not conversation_id:
        exit_with("No conversation_id received in stream meta")
    if not saw_delta:
        exit_with("No delta events received")
    if not saw_done:
        exit_with("Stream ended without done event")

    messages = client.get(f"/conversations/{conversation_id}/messages", headers=auth_headers("GET"))
    if messages.status_code != 200:
        exit_with(f"Failed to fetch messages: HTTP {messages.status_code} {messages.text}")
    items = safe_json(messages)
    if not isinstance(items, list):
        exit_with("Messages response is not a list")

    assistant_msgs = [m for m in items if m.get("role") == "assistant"]
    if not assistant_msgs:
        exit_with("No assistant messages persisted")

    persisted = assistant_msgs[-1].get("content", "")
    if assistant_text.strip() and assistant_text.strip() not in persisted.strip():
        exit_with("Persisted assistant message does not match streamed content")

    if not args.quiet:
        print("Smoke test passed")
        print(f"conversation_id={conversation_id} generation_id={generation_id}")
        print(f"assistant_chars={len(assistant_text)}")


if __name__ == "__main__":
    main()
