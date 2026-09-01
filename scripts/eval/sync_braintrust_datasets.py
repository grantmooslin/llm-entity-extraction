#!/usr/bin/env python3
"""Sync eval/testing datasets into a Braintrust project (sandbox by default).

Mirrors the Langfuse dataset twin (``scripts/eval/sync_langfuse_datasets.py``)
but writes to Braintrust via ``upload_text_dataset`` (deterministic row ids =>
upsert on rerun). Targets the iterative-improvement + testing corpora used by
the docclass and evaluation runners:

- LegalBench task suites (``mailroom-lb-<task>``)
- CUAD contracts text corpus (``mailroom-cuad-contracts``)
- Merged docclass corpus from HF (``mailroom-docclass``)
- Enron correspondence dedup corpus (``mailroom-enron-correspondence``)

Usage:
    python scripts/eval/sync_braintrust_datasets.py --dry-run
    python scripts/eval/sync_braintrust_datasets.py --env-file braintrust-sandbox.env
    python scripts/eval/sync_braintrust_datasets.py --all --env-file braintrust-sandbox.env
    python scripts/eval/sync_braintrust_datasets.py --tasks hearsay --test
    python scripts/eval/sync_braintrust_datasets.py --docclass --enron --cuad

``--all`` syncs the default eval bundle: hearsay train, CUAD text-only (510
rows), HF docclass-merged, and a **stratified-200** Enron correspondence
sample (seed 42; pass ``--enron-full`` with ``--enron`` for the ~247k corpus).

Prerequisites: ``pip install -r requirements/datasets.txt`` (and evals batch
for Braintrust SDK) for network-backed exports.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets.stream_legalbench_tasks_to_bt import (  # noqa: E402
    build_records,
    fetch_hf_split,
    load_task,
    normalize_hf_rows,
    valid_classes_for,
)
from src.braintrust_config import load_braintrust_config  # noqa: E402
from src.braintrust_utils import upload_text_dataset  # noqa: E402
from src.env_utils import BRAINTRUST_SANDBOX_ENV_FILE, resolve_env_file  # noqa: E402

DEFAULT_ENV_FILE = str(BRAINTRUST_SANDBOX_ENV_FILE)
DATASET_PREFIX = "mailroom-lb"
DEFAULT_ALL_TASKS = "hearsay"
CUAD_DATASET = "mailroom-cuad-contracts"
DOCCLASS_DATASET = "mailroom-docclass"
ENRON_DATASET = "mailroom-enron-correspondence"


def _load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(path, override=True)
    except ImportError:
        pass


def _flat_row_to_record(row: dict) -> dict:
    """Convert a streamer/local-dump flat row into an upload_text_dataset record."""
    metadata = dict(row.get("metadata") or {})
    expected = row.get("expected") or ""
    expected_subclass = row.get("expected_subclass")
    input_data = {
        "doc_text": row.get("doc_text", ""),
        "filename": row.get("filename", ""),
        "prompt": row.get("prompt", ""),
        "metadata": {
            **metadata,
            "expected_doc_type": expected,
            "expected_subclass": expected_subclass,
        },
    }
    expected_obj: dict = {"doc_type": expected}
    if expected_subclass:
        expected_obj["expected_subclass"] = expected_subclass
    for key in ("sentiment_label", "sentiment_score", "content_topic"):
        if row.get(key) not in (None, ""):
            expected_obj[key] = row[key]
    gt_fields = row.get("gt_fields")
    if isinstance(gt_fields, dict) and gt_fields:
        expected_obj["expected_fields"] = gt_fields
    return {"input": input_data, "expected": expected_obj, "metadata": metadata}


def _records_from_local_dump(path: Path) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(_flat_row_to_record(json.loads(line)))
    return records


def _upload_records(
    records: list[dict],
    *,
    cfg,
    api_key: str,
    dataset_name: str,
    description: str,
    dry_run: bool,
) -> dict:
    if dry_run:
        return {"inserted": len(records), "failed": 0, "dry_run": True}
    return upload_text_dataset(
        records,
        cfg.project_id,
        dataset_name,
        api_key,
        description=description,
        metadata={"source": "sync_braintrust_datasets.py"},
    )


def _sync_legalbench_tasks(
    cfg,
    api_key: str,
    tasks: list[str],
    *,
    with_test: bool,
    dry_run: bool,
) -> tuple[int, int]:
    total_inserted = total_failed = 0
    for task in tasks:
        meta = load_task(task, include_prompt=True)
        records = build_records(meta)
        if not records:
            print(f"  {task}: no train records; skipping")
            continue
        train_name = f"{DATASET_PREFIX}-{task}"
        summary = _upload_records(
            records,
            cfg=cfg,
            api_key=api_key,
            dataset_name=train_name,
            description=f"LegalBench task {task} (train)",
            dry_run=dry_run,
        )
        total_inserted += summary.get("inserted", 0)
        total_failed += summary.get("failed", 0)
        print(f"  {task}: {summary.get('inserted', len(records))} train rows -> {train_name}"
              + (" (would)" if dry_run else ""))

        if with_test:
            test_raw = fetch_hf_split(task, "test")
            test_rows = normalize_hf_rows(test_raw)
            if not test_rows:
                print(f"    {task}: no test rows on HF; skipping")
                continue
            test_meta = {
                **meta,
                "rows": test_rows,
                "valid_classes": valid_classes_for(test_rows, meta["task_type"]),
            }
            test_records = build_records(test_meta)
            test_name = f"{DATASET_PREFIX}-{task}-test"
            summary = _upload_records(
                test_records,
                cfg=cfg,
                api_key=api_key,
                dataset_name=test_name,
                description=f"LegalBench task {task} (test)",
                dry_run=dry_run,
            )
            total_inserted += summary.get("inserted", 0)
            total_failed += summary.get("failed", 0)
            print(f"    {task}: {summary.get('inserted', len(test_records))} test rows -> {test_name}"
                  + (" (would)" if dry_run else ""))
    return total_inserted, total_failed


def _sync_cuad_text(cfg, api_key: str, *, dry_run: bool) -> tuple[int, int]:
    """Delegate to the CUAD streamer (text-only, full corpus)."""
    repo_root = Path(__file__).resolve().parents[2]
    streamer = repo_root / "scripts/datasets/stream_cuad_to_bt.py"
    cmd = [
        sys.executable,
        str(streamer),
        "--text-only",
        "--project-id",
        cfg.project_id,
        "--dataset",
        CUAD_DATASET,
    ]
    if dry_run:
        cmd.append("--dry-run")
    print(f"  CUAD: running {' '.join(cmd[-4:])} ...")
    env = os.environ.copy()
    env["BRAINTRUST_API_KEY"] = api_key
    subprocess.run(cmd, cwd=repo_root, env=env, check=True)
    if dry_run:
        return 0, 0
    return -1, 0  # streamer prints its own counts


def _sync_docclass_hf(cfg, api_key: str, *, out_path: Path, dry_run: bool) -> tuple[int, int]:
    from scripts.datasets.export_hf_docclass_merged import export_jsonl

    if dry_run:
        from datasets import load_dataset
        gt = load_dataset("Lucius-Morningstar/docclass-merged", "ground_truth")
        n = sum(len(gt[s]) for s in gt)
        print(f"  docclass: would export {n} HF rows -> {DOCCLASS_DATASET}")
        return n, 0

    stats = export_jsonl(out_path)
    records = _records_from_local_dump(out_path)
    summary = _upload_records(
        records,
        cfg=cfg,
        api_key=api_key,
        dataset_name=DOCCLASS_DATASET,
        description="Merged docclass corpus (Lucius-Morningstar/docclass-merged)",
        dry_run=False,
    )
    print(f"  docclass: {summary['inserted']} rows -> {DOCCLASS_DATASET} "
          f"(exported {stats['rows']} from HF)")
    return summary.get("inserted", 0), summary.get("failed", 0)


def _sync_enron(
    cfg,
    api_key: str,
    *,
    dry_run: bool,
    full: bool = False,
    stratified: int = 200,
    seed: int = 42,
) -> tuple[int, int]:
    from scripts.datasets.load_enron_correspondence import attach_blind_text, load_gt_rows
    from src.correspondence_eval import stratified_by_subclass

    load_env_token = os.environ.get("HF_TOKEN") or None
    gt = load_gt_rows("Lucius-Morningstar/enron-correspondence-dedup", token=load_env_token,
                      splits=("train", "test"))
    if not full:
        gt = stratified_by_subclass(gt, n=stratified, seed=seed)
        label = f"stratified-{stratified} seed {seed}"
    else:
        label = "full corpus"
    if dry_run:
        print(f"  enron: would sync {len(gt)} rows ({label}) -> {ENRON_DATASET}")
        return len(gt), 0
    rows = attach_blind_text(gt, "Lucius-Morningstar/enron-correspondence-dedup",
                             token=load_env_token, splits=("train", "test"))
    records = [_flat_row_to_record(row) for row in rows]
    summary = _upload_records(
        records,
        cfg=cfg,
        api_key=api_key,
        dataset_name=ENRON_DATASET,
        description=f"Enron correspondence dedup ({label}, blind+GT join)",
        dry_run=False,
    )
    print(f"  enron: {summary['inserted']} rows -> {ENRON_DATASET} ({label})")
    return summary.get("inserted", 0), summary.get("failed", 0)


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", action="append", default=[],
                        help=f"Braintrust env file (default: {DEFAULT_ENV_FILE})")
    parser.add_argument("--tasks", default=None,
                        help="Comma-separated LegalBench tasks (e.g. hearsay). "
                             "Used with --all default bundle when --tasks omitted.")
    parser.add_argument("--test", action="store_true",
                        help="Also mirror each task's TEST split")
    parser.add_argument("--cuad", action="store_true",
                        help=f"Sync CUAD text corpus -> {CUAD_DATASET}")
    parser.add_argument("--docclass", action="store_true",
                        help=f"Export HF docclass-merged -> {DOCCLASS_DATASET}")
    parser.add_argument("--enron", action="store_true",
                        help=f"Sync Enron correspondence eval sample -> {ENRON_DATASET} "
                             f"(default: stratified 200, seed 42)")
    parser.add_argument("--enron-full", action="store_true",
                        help="Upload the FULL Enron dedup corpus (~247k rows) instead of "
                             "the stratified testing sample")
    parser.add_argument("--enron-stratified", type=int, default=200,
                        help="Stratified sample size for --enron (default: 200)")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for Enron stratified sample (default: 42)")
    parser.add_argument("--all", action="store_true",
                        help="Sync the default eval bundle (hearsay, CUAD text, "
                             "docclass HF, Enron correspondence)")
    parser.add_argument("--docclass-out", type=Path,
                        default=Path("data/datasets/docclass_merged_v5.jsonl"),
                        help="Local path for the HF docclass export cache")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing to Braintrust")
    args = parser.parse_args(argv)

    sync_cuad = args.cuad
    sync_docclass = args.docclass
    sync_enron = args.enron
    if args.all:
        sync_cuad = sync_docclass = sync_enron = True
        if not args.tasks:
            args.tasks = DEFAULT_ALL_TASKS

    sync_tasks = bool(args.tasks)
    if not any((sync_tasks, sync_cuad, sync_docclass, sync_enron)):
        parser.error("Specify at least one of --tasks, --cuad, --docclass, --enron, or --all")

    env_files = [
        resolve_env_file(p, default=BRAINTRUST_SANDBOX_ENV_FILE)
        for p in (args.env_file or [DEFAULT_ENV_FILE])
    ]
    for env_file in env_files:
        if not env_file.exists():
            print(f"[warn] {env_file} not found — skipped")
            continue
        _load_env_file(env_file)
        cfg = load_braintrust_config(env_file)
        api_key = os.environ.get("BRAINTRUST_API_KEY") or cfg.api_key
        if not api_key or not cfg.project_id:
            print(f"[warn] {env_file}: missing BRAINTRUST_API_KEY or project id — skipped")
            continue

        print(f"Syncing datasets -> {cfg.project_name} ({cfg.project_id})"
              + (" (dry-run)" if args.dry_run else ""))
        total_inserted = total_failed = 0

        if sync_tasks and args.tasks:
            tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]
            print(f"LegalBench tasks: {tasks}" + (" + test" if args.test else ""))
            ins, fail = _sync_legalbench_tasks(cfg, api_key, tasks,
                                               with_test=args.test, dry_run=args.dry_run)
            if ins >= 0:
                total_inserted += ins
                total_failed += fail

        if sync_cuad:
            print("CUAD text-only corpus:")
            ins, fail = _sync_cuad_text(cfg, api_key, dry_run=args.dry_run)
            if ins >= 0:
                total_inserted += ins
                total_failed += fail

        if sync_docclass:
            print("Docclass merged (HF):")
            ins, fail = _sync_docclass_hf(cfg, api_key, out_path=args.docclass_out,
                                          dry_run=args.dry_run)
            total_inserted += max(ins, 0)
            total_failed += fail

        if sync_enron:
            print("Enron correspondence:")
            ins, fail = _sync_enron(
                cfg, api_key, dry_run=args.dry_run, full=args.enron_full,
                stratified=args.enron_stratified, seed=args.seed,
            )
            total_inserted += ins
            total_failed += fail

        if total_inserted >= 0 and not args.dry_run:
            print(f"Done: {total_inserted} rows inserted, {total_failed} failed")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
