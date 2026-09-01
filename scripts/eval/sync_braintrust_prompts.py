#!/usr/bin/env python3
"""Sync every registered prompt version into a Braintrust project's prompt registry.

Mirrors the Langfuse twin (``scripts/eval/sync_langfuse_prompts.py``): the
version keys in ``src/prompts.py`` (including docclass variants merged from
``src/prompts_docclass.py``) are the source of truth; this script upserts
each as a completion prompt whose ``slug`` equals the version key.

Usage:
    python scripts/eval/sync_braintrust_prompts.py --dry-run
    python scripts/eval/sync_braintrust_prompts.py \\
        --env-file braintrust-sandbox.env
    python scripts/eval/sync_braintrust_prompts.py \\
        --env-file braintrust.env --env-file braintrust-sandbox.env

Idempotency: when the remote prompt's latest completion content already equals
the local constant, the row is skipped; only new or changed versions are
written via ``PUT /v1/prompt`` (create-or-replace).

Run after every prompt iteration when the sandbox (or another Braintrust
project) should stay in sync for eval testing.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.braintrust_config import load_braintrust_config  # noqa: E402
from src.braintrust_utils import (  # noqa: E402
    completion_prompt_content,
    get_prompt_by_slug,
    upsert_completion_prompt,
)
from src.env_utils import BRAINTRUST_SANDBOX_ENV_FILE, resolve_env_file  # noqa: E402
from src.prompts import PROMPT_VERSIONS  # noqa: E402

DEFAULT_ENV_FILES = [str(BRAINTRUST_SANDBOX_ENV_FILE)]


def _load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=True)
    except ImportError:
        pass


def _sync_project(env_file: Path, prompts: dict[str, str], dry_run: bool) -> dict:
    if not env_file.exists():
        return {"project": str(env_file), "missing_env": True}

    _load_env_file(env_file)
    cfg = load_braintrust_config(env_file)
    api_key = os.environ.get("BRAINTRUST_API_KEY") or cfg.api_key
    if not api_key or not cfg.project_id:
        return {
            "project": cfg.project_name,
            "skipped_env": True,
            "created": 0,
            "unchanged": 0,
            "total": len(prompts),
        }

    created: list[str] = []
    unchanged: list[str] = []
    for name, content in prompts.items():
        existing = get_prompt_by_slug(api_key, cfg.project_id, name, cfg.api_base)
        if completion_prompt_content(existing) == content:
            unchanged.append(name)
            continue
        if dry_run:
            created.append(name)
            continue
        upsert_completion_prompt(
            api_key,
            cfg.project_id,
            name,
            content,
            name=name,
            description=f"llm-entity-extraction prompt version {name}",
            api_base=cfg.api_base,
        )
        created.append(name)

    return {
        "project": cfg.project_name,
        "project_id": cfg.project_id,
        "created": len(created),
        "unchanged": len(unchanged),
        "total": len(prompts),
        "created_names": created,
        "unchanged_names": unchanged,
    }


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        action="append",
        default=[],
        help="Braintrust env file with project id + API key (repeatable). "
             f"Defaults to {DEFAULT_ENV_FILES}",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would sync without writing")
    args = parser.parse_args(argv)

    env_files = [
        resolve_env_file(p, default=BRAINTRUST_SANDBOX_ENV_FILE)
        for p in (args.env_file or DEFAULT_ENV_FILES)
    ]
    prompts = dict(PROMPT_VERSIONS)
    print(f"Syncing {len(prompts)} prompt versions from src/prompts.py "
          f"(incl. docclass via prompts_docclass)")
    for env_file in env_files:
        if not env_file.exists():
            print(f"  [warn] {env_file} not found — skipped "
                  f"(copy from braintrust-sandbox.env.example)")
            continue
        report = _sync_project(env_file, prompts, args.dry_run)
        if report.get("missing_env"):
            continue
        if report.get("skipped_env"):
            print(f"  [warn] {env_file}: no Braintrust project id / API key — skipped")
            continue
        mode = "would upsert" if args.dry_run else "upserted"
        print(f"  {report['project']} ({report['project_id']}): "
              f"{mode} {report['created']}, unchanged {report['unchanged']} "
              f"(of {report['total']})")
        if args.dry_run and report["created_names"]:
            preview = ", ".join(report["created_names"][:8])
            if len(report["created_names"]) > 8:
                preview += "..."
            print(f"    {preview}")
    return 0


def main() -> None:
    sys.exit(main_with_args(sys.argv[1:]))


if __name__ == "__main__":
    main()
