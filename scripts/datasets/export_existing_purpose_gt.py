#!/usr/bin/env python3
"""Export the EXISTING purpose/gist GT labels for the incremental labeler pass.

KANBAN-105: after docclass-merged v6 is published, llm-mailroom's
``sync_hf_ground_truth.py`` must label ONLY the NEW rows (240 correspondence +
200 insurance) — re-labeling the ~488 rows the 2026-08-30 purpose-GT push
already covered would spend duplicate LLM calls and could churn stable labels.

This script seeds the mailroom labeler's ``--resume`` surface:
``<mailroom>/data/hf_gt/ground_truth_preview.csv`` (filename, intent,
subject_matter, keywords) + ``label_run.json`` provenance (mode "real" — the
labels come from the real-mode Hub push ``5d69bccae172`` / HEAD relabel
``1d4753578d91``, not from a mock). With that in place:

    PYTHONPATH=src python src/scripts/sync_hf_ground_truth.py --real --resume --push

resumes the 488 existing labels without LLM calls and labels only the new
purpose-class rows, then pushes the enriched ground_truth revision.

Usage:
    python scripts/datasets/export_existing_purpose_gt.py \
        --parent-gt-dir /path/to/parquet/ground_truth \
        --mailroom-dir ../llm-mailroom
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELED_CLASSES = ("corporate_record", "correspondence", "insurance_claim")


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-gt-dir", type=Path, required=True,
                        help="dir with the docclass-merged ground_truth "
                             "parquet shards (the purpose GT lives on train)")
    parser.add_argument("--mailroom-dir", type=Path, required=True,
                        help="llm-mailroom clone root (data/hf_gt/ seeded)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    import pyarrow.parquet as pq

    out_dir = args.mailroom_dir / "data" / "hf_gt"
    rows_out = []
    for shard in sorted(args.parent_gt_dir.glob("**/*.parquet")):
        table = pq.read_table(shard)
        cols = set(table.column_names)
        if not {"intent", "subject_matter", "keywords"} <= cols:
            print(f"  {shard.name}: no purpose-GT columns — skipped")
            continue
        for i in range(table.num_rows):
            expected = str(table.column("expected")[i].as_py())
            if expected not in LABELED_CLASSES:
                continue
            intent = table.column("intent")[i].as_py()
            if not intent:
                continue  # unlabeled rows are the labeler's job, not ours
            rows_out.append({
                "filename": str(table.column("filename")[i].as_py()),
                "intent": str(intent),
                "subject_matter": str(table.column("subject_matter")[i].as_py()
                                      or ""),
                "keywords": str(table.column("keywords")[i].as_py() or "[]"),
                "expected": expected,
            })
    by_class: dict[str, int] = {}
    for r in rows_out:
        by_class[r["expected"]] = by_class.get(r["expected"], 0) + 1
    print(f"existing purpose-GT labels: {len(rows_out)} ({by_class})")
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "ground_truth_preview.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["filename", "intent", "subject_matter", "keywords"])
        writer.writeheader()
        for r in rows_out:
            writer.writerow({k: r[k] for k in writer.fieldnames})
    provenance = {
        "mode": "real",
        "labeled": len(rows_out),
        "updated": datetime.now(timezone.utc).isoformat(),
        "note": ("seeded by llm-entity-extraction "
                 "scripts/datasets/export_existing_purpose_gt.py from the "
                 "2026-08-30 real-mode Hub push (5d69bccae172 / relabel "
                 "1d4753578d91) — labels are real, extracted not invented"),
    }
    (out_dir / "label_run.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows_out)} labels -> {csv_path}")
    print(f"Provenance -> {out_dir / 'label_run.json'} (mode: real)")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
