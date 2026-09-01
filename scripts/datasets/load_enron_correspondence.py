#!/usr/bin/env python3
"""Load the Enron correspondence-dedup Hub dataset (KANBAN-103).

Joins the agent-blind ``default`` config (filename/subject/text) to the
``ground_truth`` config on ``filename``. Filters to ``expected=correspondence``.
Does NOT leak GT columns into the text the sorter sees.

Usage:
    python scripts/datasets/load_enron_correspondence.py --dry-run
    python scripts/datasets/load_enron_correspondence.py --write \\
        --out data/datasets/enron_correspondence_eval.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.correspondence_eval import (  # noqa: E402
    compose_doc_text,
    join_blind_and_gt,
)
from src.env_utils import get_env, load_env  # noqa: E402

DEFAULT_REPO = "Lucius-Morningstar/enron-correspondence-dedup"
DEFAULT_OUT = Path("data/datasets/enron_correspondence_eval.jsonl")
GT_FILES = ("ground_truth/train.jsonl", "ground_truth/test.jsonl")
BLIND_FILES = ("blind/train.jsonl", "blind/test.jsonl")


def _require_hub():
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is required to load the Enron correspondence "
            "dataset. Install the datasets extra: "
            "pip install -r requirements/datasets.txt"
        ) from exc
    return hf_hub_download


def download_hub_jsonl(repo_id: str, filename: str, *, token: str | None) -> Path:
    """Download one Hub JSONL file and return the local cache path."""
    hf_hub_download = _require_hub()
    path = hf_hub_download(
        repo_id=repo_id,
        repo_type="dataset",
        filename=filename,
        token=token or None,
    )
    return Path(path)


def iter_jsonl(path: Path):
    """Yield JSON objects from a JSONL file, skipping blanks."""
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_gt_rows(repo_id: str, *, token: str | None,
                 splits: tuple[str, ...] = ("train", "test")) -> list[dict]:
    """Load every ground_truth row (no email body — small enough to hold)."""
    rows: list[dict] = []
    for split in splits:
        path = download_hub_jsonl(repo_id, f"ground_truth/{split}.jsonl", token=token)
        rows.extend(iter_jsonl(path))
    return rows


def attach_blind_text(
    gt_rows: list[dict],
    repo_id: str,
    *,
    token: str | None,
    splits: tuple[str, ...] = ("train", "test"),
) -> list[dict]:
    """Stream blind JSONL and attach subject/text for the requested filenames.

    Only the selected GT filenames are kept — the full blind dump is streamed,
    never materialized. Rows with empty subject+body are dropped.
    """
    wanted = {str(r.get("filename") or "") for r in gt_rows}
    wanted.discard("")
    found: dict[str, dict] = {}
    for split in splits:
        path = download_hub_jsonl(repo_id, f"blind/{split}.jsonl", token=token)
        for row in iter_jsonl(path):
            filename = str(row.get("filename") or "")
            if filename not in wanted or filename in found:
                continue
            found[filename] = row
            if len(found) >= len(wanted):
                break
        if len(found) >= len(wanted):
            break
    return join_blind_and_gt(list(found.values()), gt_rows, correspondence_only=True)


def load_enron_correspondence(
    repo_id: str = DEFAULT_REPO,
    *,
    token: str | None = None,
    splits: tuple[str, ...] = ("train", "test"),
    selected_filenames: set[str] | None = None,
) -> list[dict]:
    """Load correspondence-only eval rows (joined blind + GT).

    When ``selected_filenames`` is set, only those GT rows are joined (used
    after a subclass-stratified draw so the blind stream stops early).
    """
    load_env()
    token = token or get_env("HF_TOKEN") or os.environ.get("HF_TOKEN") or None
    gt = load_gt_rows(repo_id, token=token, splits=splits)
    if selected_filenames is not None:
        gt = [r for r in gt if str(r.get("filename") or "") in selected_filenames]
    return attach_blind_text(gt, repo_id, token=token, splits=splits)


def load_local_jsonl(path: Path) -> list[dict]:
    """Load a previously written joined dump (or a hand-built fixture)."""
    rows: list[dict] = []
    for raw in iter_jsonl(path):
        expected = str(raw.get("expected") or "").strip()
        if expected and expected != "correspondence":
            continue
        text = raw.get("doc_text") or compose_doc_text(raw.get("subject"), raw.get("text"))
        if not str(text).strip():
            continue
        rows.append({
            "filename": str(raw.get("filename") or f"row_{len(rows) + 1}"),
            "doc_text": text,
            "subject": str(raw.get("subject") or ""),
            "expected": expected or "correspondence",
            "expected_subclass": raw.get("expected_subclass"),
            "sentiment_score": raw.get("sentiment_score"),
            "sentiment_label": raw.get("sentiment_label"),
            "content_topic": raw.get("content_topic"),
            "label_evidence": raw.get("label_evidence"),
            "sentiment_evidence": raw.get("sentiment_evidence"),
            "split": raw.get("split"),
            "metadata": dict(raw.get("metadata") or {}),
        })
    return rows


def write_joined_jsonl(rows: list[dict], path: Path) -> None:
    """Write joined eval rows as JSONL (gitignored under data/datasets/)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--split", choices=("train", "test", "all"), default="all")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--write", action="store_true",
                        help="Write the joined JSONL to --out")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load GT only and print subclass/sentiment counts")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    load_env()
    token = get_env("HF_TOKEN") or os.environ.get("HF_TOKEN") or None
    splits = ("train", "test") if args.split == "all" else (args.split,)
    print(f"Loading GT from {args.repo} splits={splits}")
    gt = load_gt_rows(args.repo, token=token, splits=splits)
    if args.limit:
        gt = gt[: args.limit]
    print(f"  GT rows: {len(gt)}")
    print(f"  expected: {dict(Counter(r.get('expected') for r in gt))}")
    print(f"  subclass: {dict(Counter(r.get('expected_subclass') for r in gt))}")
    print(f"  sentiment: {dict(Counter(r.get('sentiment_label') for r in gt))}")
    if args.dry_run:
        print("Dry run: skipping blind-text join.")
        return 0
    rows = attach_blind_text(gt, args.repo, token=token, splits=splits)
    print(f"  joined correspondence rows: {len(rows)}")
    if args.write:
        write_joined_jsonl(rows, args.out)
        print(f"  wrote {args.out}")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
