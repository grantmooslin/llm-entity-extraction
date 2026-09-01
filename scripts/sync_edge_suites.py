#!/usr/bin/env python3
"""Sync edge suites into The-Mailroom's configured Langfuse environment.

Creates one dataset per suite (edge-<agent>) and upserts every item with a
deterministic id (suite_id), so re-runs refresh rather than duplicate.

Credentials come from The-Mailroom's .env (rotated pair) — NOT the upstream
langfuse.env (different project).

Usage:
    python3 scripts/sync_edge_suites.py \
        --env-file /Users/luciusjmorningstar/Downloads/The-Mailroom/.env
    python3 scripts/sync_edge_suites.py --env-file ... --dataset edge-contracts-specialist
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITES = REPO_ROOT / "data" / "gt" / "edge_suites"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env-file", required=True,
                    help="path to The-Mailroom .env (rotated Langfuse keys)")
    ap.add_argument("--dataset", default=None,
                    help="sync only this dataset name (edge-<agent>)")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(args.env_file, override=True)
    import os

    missing = [k for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
               if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing env vars after load: {', '.join(missing)}")

    from langfuse import Langfuse

    client = Langfuse(host=os.environ.get("LANGFUSE_HOST",
                                          "https://us.cloud.langfuse.com"))
    try:
        client.auth_check()
        print("auth OK")
    except Exception as exc:
        sys.exit(f"Langfuse rejected credentials: {str(exc)[:140]}")

    files = sorted(SUITES.glob("edge_*.jsonl"))
    if args.dataset:
        agent = args.dataset.replace("edge-", "")
        files = [SUITES / f"edge_{agent}.jsonl"]

    for path in files:
        agent = path.name.replace("edge_", "").replace(".jsonl", "")
        ds_name = f"edge-{agent}"
        items = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        client.create_dataset(
            name=ds_name,
            description=f"Durability matrix for {agent} "
                        f"(deterministic transforms; gen_edge_cases.py)",
            metadata={"generator": "scripts/gen_edge_cases.py"},
        )
        added = skipped = 0
        known = set()
        try:
            ds = client.get_dataset(ds_name)
            for it in getattr(ds, "items", []) or []:
                if getattr(it, "id", None):
                    known.add(it.id)
        except Exception:
            pass
        for it in items:
            if it["suite_id"] in known:
                skipped += 1
                continue
            client.create_dataset_item(
                dataset_name=ds_name,
                id=it["suite_id"],
                input={"filename": it["base_filename"], "doc_text": it["doc_text"]},
                expected_output=json.loads(json.dumps(it["expectations"])),
                metadata={"transform": it["transform"],
                          "base_filename": it["base_filename"],
                          "gt_fields": json.dumps(it.get("gt_fields", {}))[:4000]},
            )
            added += 1
        print(f"{ds_name}: {len(items)} items | +{added} added, {skipped} already present")

    client.flush()
    host = os.environ.get("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    print(f"datasets live at {host}/datasets (project from --env-file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
