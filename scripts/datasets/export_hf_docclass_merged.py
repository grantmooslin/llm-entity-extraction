#!/usr/bin/env python3
"""Export Lucius-Morningstar/docclass-merged (HF) to local JSONL for eval runners.

Joins the ``default`` config (doc_text) with ``ground_truth`` (labels + GT
fields) into the combined row shape used by ``run_langfuse_docclass_eval.py``
and ``run_langfuse_docclass_specialist_eval.py``.

Usage:
    python scripts/datasets/export_hf_docclass_merged.py --dry-run
    python scripts/datasets/export_hf_docclass_merged.py \\
        --out data/datasets/docclass_merged_v5.jsonl
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets._jsonl_safety import safe_jsonl_line

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_ID = "Lucius-Morningstar/docclass-merged"

INSURANCE_GT_KEYS = (
    "claim_number", "policy_number", "insurer", "insured_party",
    "claim_type", "date_of_loss", "date_filed", "claimed_amount",
    "adjuster", "damages_description", "coverage_determination",
    "denial_reasons", "supporting_documents",
)

CLAUSE_GT_KEYS = ("cuad_clause_labels", "maud_clause_labels")


def _coerce_gt_value(raw):
    """Parse list-like GT strings from the Hub into Python values."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                try:
                    return ast.literal_eval(s)
                except (SyntaxError, ValueError):
                    return raw
        return raw
    return raw


def _build_gt_fields(row: dict) -> dict:
    gf: dict = {}
    for key in INSURANCE_GT_KEYS + CLAUSE_GT_KEYS:
        if key in row and row[key] not in (None, ""):
            gf[key] = _coerce_gt_value(row[key])
    return gf


def export_jsonl(out_path: Path) -> dict:
    from datasets import load_dataset

    blind_train = load_dataset(DATASET_ID, "default", split="train")
    blind_test = load_dataset(DATASET_ID, "default", split="test")
    gt_train = load_dataset(DATASET_ID, "ground_truth", split="train")
    gt_test = load_dataset(DATASET_ID, "ground_truth", split="test")

    gt_by_name: dict[str, dict] = {}
    for ds in (gt_train, gt_test):
        for row in ds:
            gt_by_name[row["filename"]] = dict(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    n = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for ds in (blind_train, blind_test):
            for row in ds:
                fn = row["filename"]
                gt = gt_by_name.get(fn)
                if gt is None:
                    continue
                expected = str(gt["expected"])
                counts[expected] = counts.get(expected, 0) + 1
                metadata = row.get("metadata")
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}
                metadata = dict(metadata or {})
                rec = {
                    "filename": fn,
                    "doc_text": row["doc_text"],
                    "prompt": row.get("prompt") or "",
                    "expected": expected,
                    "expected_subclass": gt.get("expected_subclass") or "",
                    "split": gt.get("split") or row.get("split") or "",
                    "gt_fields": _build_gt_fields(gt),
                    "metadata": metadata,
                }
                fh.write(safe_jsonl_line(rec) + "\n")
                n += 1
    return {"rows": n, "by_class": counts, "path": str(out_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "data/datasets/docclass_merged_v5.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        from datasets import load_dataset
        gt = load_dataset(DATASET_ID, "ground_truth")
        n = sum(len(gt[s]) for s in gt)
        print(f"Dry run: would export {n} rows -> {args.out}")
        return 0
    stats = export_jsonl(args.out)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
