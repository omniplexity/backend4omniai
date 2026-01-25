#!/usr/bin/env python3
"""Bootstrap an admin user via the /admin/bootstrap endpoint.

Usage:
  python scripts/bootstrap_admin.py --base-url https://your-ngrok-url --username admin --password strongpass --bootstrap-token token

Environment fallbacks:
  OMNIAI_BASE_URL, OMNIAI_USERNAME, OMNIAI_PASSWORD, OMNIAI_BOOTSTRAP_TOKEN, OMNIAI_ORIGIN_SECRET
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OmniAI admin bootstrap")
    parser.add_argument("--base-url", default=os.getenv("OMNIAI_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--username", default=os.getenv("OMNIAI_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("OMNIAI_PASSWORD", "adminpass"))
    parser.add_argument("--bootstrap-token", default=os.getenv("OMNIAI_BOOTSTRAP_TOKEN"))
    parser.add_argument("--origin-secret", default=os.getenv("OMNIAI_ORIGIN_SECRET"))
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


def main() -> None:
    args = parse_args()

    if not args.bootstrap_token:
        exit_with("Missing bootstrap token (use --bootstrap-token or OMNIAI_BOOTSTRAP_TOKEN)")

    headers: dict[str, str] = {"X-Bootstrap-Token": args.bootstrap_token}
    if args.origin_secret:
        headers["X-Origin-Secret"] = args.origin_secret

    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=10.0, headers=headers)

    try:
        response = client.post(
            "/admin/bootstrap",
            json={"username": args.username, "password": args.password},
        )
    except Exception as exc:
        exit_with(f"Request failed: {exc}")

    if response.status_code == 200:
        if not args.quiet:
            print("Admin bootstrap succeeded")
        return

    data = safe_json(response)
    code = data.get("code")
    if response.status_code == 403 and code == "BOOTSTRAP_DISABLED":
        if not args.quiet:
            print("Admin already exists; bootstrap skipped")
        return

    exit_with(f"Admin bootstrap failed: HTTP {response.status_code} {response.text}")


if __name__ == "__main__":
    main()
