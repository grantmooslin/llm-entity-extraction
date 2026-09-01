#!/usr/bin/env python3
"""Patch Enron correspondence Hub GT rows from a local override JSONL.

KANBAN-103: the official ``correspondence_subclasses.py`` labeler fires on
any demand-marker phrase in the writer's own text. That tags FYI news,
IT outages, "please draft a demand letter", and hypothetical counsel notes
as ``demand`` / ``attorney_demand``. This script applies filename-keyed
corrections to the Hub ``ground_truth`` JSONL files and uploads a sidecar
``ground_truth/overrides.jsonl`` so the correction is auditable.

Usage:
    python scripts/datasets/publish_enron_gt_overrides.py --dry-run
    python scripts/datasets/publish_enron_gt_overrides.py --publish
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets._jsonl_safety import safe_jsonl_line  # noqa: E402
from scripts.datasets.load_enron_correspondence import (  # noqa: E402
    DEFAULT_REPO,
    download_hub_jsonl,
)
from src.correspondence_eval import read_gt_overrides  # noqa: E402
from src.env_utils import load_env  # noqa: E402

DEFAULT_OVERRIDES = (
    Path(__file__).resolve().parents[2]
    / "data" / "gt" / "enron_correspondence_label_overrides.jsonl"
)
GT_FILES = ("ground_truth/train.jsonl", "ground_truth/test.jsonl")
SIDECAR = "ground_truth/overrides.jsonl"


def patch_gt_file(src: Path, dest: Path, overrides: dict[str, dict]) -> int:
    """Rewrite ``src`` JSONL to ``dest``, applying overrides. Return hits."""
    hits = 0
    with src.open(encoding="utf-8") as fh, dest.open("w", encoding="utf-8") as out:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue
            row = json.loads(raw)
            filename = str(row.get("filename") or "")
            patch = overrides.get(filename)
            if patch:
                row.update(patch)
                hits += 1
            out.write(safe_jsonl_line(row) + "\n")
    return hits


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--out-dir", type=Path,
                        default=Path("data/hf_export/enron_gt_overrides"))
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.overrides.exists():
        parser.error(f"overrides file not found: {args.overrides}")
    overrides = read_gt_overrides(args.overrides)
    token = os.environ.get("HF_TOKEN") or None
    args.out_dir.mkdir(parents=True, exist_ok=True)

    total_hits = 0
    for name in GT_FILES:
        local = download_hub_jsonl(args.repo, name, token=token)
        dest = args.out_dir / Path(name).name
        hits = patch_gt_file(local, dest, overrides)
        total_hits += hits
        print(f"{name}: patched {hits} / {len(overrides)} override keys -> {dest}")

    sidecar = args.out_dir / "overrides.jsonl"
    sidecar.write_text(args.overrides.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"sidecar copy -> {sidecar} ({len(overrides)} rows, {total_hits} Hub hits)")

    if args.dry_run or not args.publish:
        print("Dry run / no --publish: Hub untouched.")
        return 0

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.upload_file(
        path_or_fileobj=str(sidecar),
        path_in_repo=SIDECAR,
        repo_id=args.repo,
        repo_type="dataset",
        commit_message="KANBAN-103: correspondence GT overrides (phrase-lexicon false demands)",
    )
    for name in GT_FILES:
        dest = args.out_dir / Path(name).name
        api.upload_file(
            path_or_fileobj=str(dest),
            path_in_repo=name,
            repo_id=args.repo,
            repo_type="dataset",
            commit_message="KANBAN-103: patch demand/attorney_demand phrase-lexicon false positives",
        )
        print(f"uploaded {name}")
    print(f"published overrides + patched GT to {args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
