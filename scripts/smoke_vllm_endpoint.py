#!/usr/bin/env python
"""Smoke-test a vLLM (or any OpenAI-compatible) endpoint — KANBAN-096.

Verifies a Modal-deployed vLLM server is alive and actually completing:
  1. GET  {base}/models          -> lists the deployed model
  2. POST {base}/chat/completions with a tiny prompt, prints the reply

Exit code 0 = healthy; nonzero = something to fix before pointing the
pipeline at it.

Usage:
    python scripts/smoke_vllm_endpoint.py \
        --base-url https://<ws>--entity-vllm-serve.modal.run/v1 \
        --model Qwen/Qwen3-8B [--api-key tok-...]

Bearer precedence: --api-key > VLLM_API_KEY > OPENROUTER_API_KEY env.
"""

from __future__ import annotations

import argparse
import os
import sys

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        required=True,
        help="OpenAI-compatible base URL ending in /v1",
    )
    parser.add_argument("--model", required=True, help="model id the server serves")
    parser.add_argument("--api-key", default=None, help="bearer token (see precedence)")
    parser.add_argument(
        "--timeout", type=int, default=60, help="per-request timeout seconds"
    )
    args = parser.parse_args()

    api_key = (
        args.api_key
        or os.environ.get("VLLM_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    base = args.base_url.rstrip("/")

    # --- 1: model catalog -------------------------------------------------
    models_url = f"{base}/models"
    try:
        resp = requests.get(models_url, headers=headers, timeout=args.timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"FAIL: GET {models_url} -> {exc}")
        return 1
    listed = [m.get("id") for m in resp.json().get("data", [])]
    print(f"OK: /models -> {listed or '(empty list)'}")

    # --- 2: real completion -----------------------------------------------
    chat_url = f"{base}/chat/completions"
    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": "Reply with exactly: HOO"}],
        "max_tokens": 16,
        "temperature": 0.0,
    }
    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=args.timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"FAIL: POST {chat_url} -> {exc}")
        return 2

    body = resp.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        print(f"FAIL: unexpected completion shape: {body!r:.400}")
        return 3
    usage = body.get("usage", {})
    print(f"OK: completion -> {content!r}  usage={usage}")
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
