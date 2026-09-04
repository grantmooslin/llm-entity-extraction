#!/usr/bin/env python3
"""Build revision-pinned mailroom-corpus eval dumps for the entity eval loop.

Bridges the published HF corpus (``Lucius-Morningstar/mailroom-corpus``) to
the flat local-dump shape the docclass runners consume
(``{filename, doc_text, expected, expected_subclass, expected_fields,
gt_fields, ...}``), at an explicit dataset revision so v7-era and v8-era
experiments are reproducible side by side (HUB-035).

    python scripts/datasets/build_mailroom_corpus_dumps.py \
        --revision bb57c5ad --label v7
    python scripts/datasets/build_mailroom_corpus_dumps.py \
        --revision <v8-sha> --label v8

Outputs (defaults):
    data/datasets/mailroom_corpus_<label>.jsonl          sorter dump (all rows)
    data/manifests/mailroom_corpus_<label>_<arm>.jsonl   per-specialist manifests
    data/manifests/mailroom_corpus_<label>.build.json    build manifest + sha256s

The GT scalar keys are derived from the ``ground_truth`` config at load time
(never hardcoded), so schema growth across corpus versions flows through
untouched. Join key is ``filename``; the ``ground_truth`` config is textless,
so ``doc_text`` comes from the ``default`` config (HUB-019 join contract).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.datasets._jsonl_safety import safe_jsonl_line  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DATASET_ID = "Lucius-Morningstar/mailroom-corpus"
DEFAULT_REVISION = "bb57c5ad"  # v7: docclass-merged-v0.1-working freeze (HUB-019)
IDENTITY_KEYS = ("filename", "expected", "expected_subclass", "split")
# package-internal config anchors to the file (data paths stay CWD-relative,
# matching every other runner in this package)
TAXONOMY_PATH = PACKAGE_ROOT / "config" / "taxonomy.yaml"

# canonical specialist families (taxonomy.yaml doc_classes + runner arms)
SPECIALIST_ARMS = {
    "contracts_specialist": frozenset({"contract", "merger_agreement"}),
    "insurance_claims_specialist": frozenset({"insurance_claim"}),
    "correspondence_specialist": frozenset({"correspondence"}),
    "corporate_records_specialist": frozenset({"corporate_record"}),
}


def class_schema_keys() -> dict[str, frozenset[str]]:
    """doc_class -> extraction field keys, from the repo taxonomy.

    ``expected_fields`` must stay schema-clean: the specialist runners score
    the union of its keys, so provenance/identity GT columns (document_id,
    annotation_method, expected_specialist, ...) must never leak in.
    """
    import yaml

    taxonomy = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    out: dict[str, frozenset[str]] = {}
    for node in taxonomy.get("doc_classes") or []:
        key = node.get("key")
        if key:
            out[key] = frozenset((node.get("field_types") or {}).keys())
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """KANBAN-088-safe writer: shared helper strips line-boundary hazards."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(safe_jsonl_line(row, sort_keys=True) + "\n")


def load_split_configs(revision: str, dataset_id: str):
    """Load (default, ground_truth) per split at the pinned revision.

    Pulls the staged parquet shards via ``huggingface_hub`` (already a
    workspace dependency — no ``datasets`` requirement) and returns plain
    row dicts, so tests can monkeypatch this function with list fixtures.
    """
    from huggingface_hub import snapshot_download
    import pyarrow.parquet as pq

    snapshot = Path(snapshot_download(
        dataset_id, repo_type="dataset", revision=revision,
        allow_patterns=["parquet/*/*.parquet"],
    ))

    def _read(split_dir: str) -> list[dict]:
        rows: list[dict] = []
        for shard in sorted((snapshot / split_dir).glob("*.parquet")):
            rows.extend(pq.read_table(shard).to_pylist())
        return rows

    out = {}
    for split in ("train", "test"):
        out[split] = (_read(f"parquet/default/{split}"),
                      _read(f"parquet/ground_truth/{split}"))
    return out


def build_dump_rows(split_configs: dict, schema_keys: dict[str, frozenset[str]] | None = None) -> list[dict]:
    """Join default+ground_truth on filename into flat eval rows."""
    rows: list[dict] = []
    for split, (blind, truth) in sorted(split_configs.items()):
        by_name = {b.get("filename"): b for b in blind}
        for gt in truth:
            name = gt.get("filename")
            blind_row = by_name.get(name)
            if blind_row is None:
                print(f"WARN: gt row {name!r} has no default-config match; skipped",
                      file=sys.stderr)
                continue
            gt_fields = {
                k: v for k, v in gt.items()
                if k not in IDENTITY_KEYS and v not in (None, "", [])
            }
            allowed = schema_keys.get(gt.get("expected")) if schema_keys else None
            expected_fields = {
                k: v for k, v in gt_fields.items()
                if (allowed is not None and k in allowed)
                or (allowed is None and not k.startswith("source_")
                    and k != "content_sha256")
            }
            doc_text = str(blind_row.get("doc_text") or "")
            if not doc_text.strip():
                print(f"WARN: {name!r} empty doc_text; skipped", file=sys.stderr)
                continue
            rows.append({
                "filename": name,
                "doc_text": doc_text,
                "expected": gt.get("expected"),
                "expected_subclass": gt.get("expected_subclass") or "",
                "expected_fields": expected_fields,
                "gt_fields": gt_fields,
                # default-config provenance/stratification metadata rides along
                # so the dump is a complete representation of BOTH configs
                "metadata": blind_row.get("metadata") or {},
                "split": split,
            })
    return rows


def main_with_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default=DEFAULT_REVISION,
                        help=f"HF revision (sha or tag) of {DATASET_ID} "
                             f"(default: {DEFAULT_REVISION} = v7 freeze)")
    parser.add_argument("--label", required=True,
                        help="Short corpus-era label, e.g. v7 / v8 (used in filenames)")
    parser.add_argument("--dataset", default=DATASET_ID)
    parser.add_argument("--out-dir", default="data/datasets")
    parser.add_argument("--manifest-dir", default="data/manifests")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap rows per split (smoke builds only)")
    args = parser.parse_args(argv)

    split_configs = load_split_configs(args.revision, args.dataset)
    if args.limit:
        split_configs = {
            split: (blind[: args.limit], truth[: args.limit])
            for split, (blind, truth) in split_configs.items()
        }
    rows = build_dump_rows(split_configs, class_schema_keys())
    if not rows:
        parser.error("no rows built — check the revision/config join")

    # CWD-relative like every other runner path (the package root IS the cwd
    # for documented runs) — keeps tmp_path-based tests hermetic.
    out_dir = Path(args.out_dir)
    manifest_dir = Path(args.manifest_dir)
    dump_path = out_dir / f"mailroom_corpus_{args.label}.jsonl"
    write_jsonl(dump_path, rows)

    files = [{"path": str(dump_path),
              "rows": len(rows),
              "sha256": sha256_file(dump_path)}]
    for arm, doc_types in sorted(SPECIALIST_ARMS.items()):
        arm_rows = [r for r in rows if r["expected"] in doc_types]
        if not arm_rows:
            print(f"NOTE: no rows for arm {arm} at this revision", file=sys.stderr)
            continue
        arm_path = manifest_dir / f"mailroom_corpus_{args.label}_{arm}.jsonl"
        write_jsonl(arm_path, arm_rows)
        files.append({"path": str(arm_path),
                      "rows": len(arm_rows),
                      "sha256": sha256_file(arm_path)})

    by_class: dict[str, int] = {}
    for row in rows:
        by_class[row["expected"]] = by_class.get(row["expected"], 0) + 1
    build_manifest = {
        "dataset": args.dataset,
        "revision": args.revision,
        "label": args.label,
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows_total": len(rows),
        "rows_by_class": dict(sorted(by_class.items())),
        "files": files,
        "schema": "flat local-dump shape (sorter runner contract, HUB-035)",
    }
    manifest_path = manifest_dir / f"mailroom_corpus_{args.label}.build.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(build_manifest, indent=2) + "\n",
                             encoding="utf-8")

    print(f"dump:  {dump_path} ({len(rows)} rows)")
    for entry in files[1:]:
        print(f"arm:   {entry['path']} ({entry['rows']} rows)")
    print(f"build: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main_with_args())
