#!/usr/bin/env python3
"""Build docclass-merged **v6**: the v5 parent + KANBAN-105 rebalance appends.

Human directive 2026-08-30: the merged corpus is contracts-concentrated
(contract 509 + merger_agreement 152 = 54.6% of the 1,210 v5 rows) — fuse

* ``+240 correspondence`` rows (deterministic sha256-within-stratum draw from
  ``Lucius-Morningstar/enron-correspondence-dedup``, 3-labeler verification
  pass green, KANBAN-103 overrides honored) — staging JSONL from
  ``build_correspondence_append.py``;
* ``+200 insurance_claim`` rows (DE-SynPUF Sample-1 re-render via
  claims-data-eda, verbatim GT contract, existing record_ids excluded) —
  staging JSONL from ``build_extra_claims.py`` (EMPTY/pending in revision 1 —
  the claims staging was lost to a tmp cleanup; the rebuild is a documented
  card residue);

for a 1,650-row v6 when complete (rev 1 ships 1,450: parent + correspondence
+ the original-files addendum; contracts fall to 35.1%).

Fusion laws honored (imported from ``build_docclass_merged`` — never forked):

* **Corpus order** — deterministic rank by primary doc_type
  (contract → merger_agreement → corporate_record → correspondence →
  insurance_claim), filename-sorted within each rank; parent rows and new
  append rows interleave by filename inside their rank, so rebuilds are
  byte-identical.
* **Family split rule** — every append row's ``split`` is re-asserted against
  ``assign_split(filename)`` (the same md5 90/10 law every family dataset
  uses); parent splits pass through verbatim.
* **Subclass canon** — ``normalize_contract_subclass`` applied to every row;
  the canon guard refuses un-normalized survivors.
* **Cast-safe metadata** — ``normalize_metadata_rows`` union/str rules over
  ALL rows (parent + appends), so the Hub loader never sees a partial schema.
* **Purpose/gist GT preservation** — the parent GT parquet's
  ``intent`` / ``subject_matter`` / ``keywords`` columns (present on the
  train shard since the llm-mailroom purpose-GT push; absent on test) ride
  into ``gt_fields`` verbatim, column-presence-checked per shard. New append
  rows carry them as null until the incremental labeler pass fills them.

Usage:
    python scripts/datasets/build_docclass_v6.py --dry-run
    python scripts/datasets/build_docclass_v6.py \
        --parent-blind-dir .../parquet/default --parent-gt-dir .../parquet/ground_truth
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

# KANBAN-088: shared JSONL line-boundary safety (Hub worker splits rows on
# U+2028/U+2029/NEL; see scripts/datasets/_jsonl_safety.py).
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from scripts.datasets._jsonl_safety import safe_jsonl_line  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets.build_docclass_merged import (  # noqa: E402
    assign_split,
    normalize_contract_subclass,
    normalize_metadata_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORR_APPEND = Path("data/datasets/correspondence_append_v6.jsonl")
DEFAULT_INS_APPEND = Path("data/datasets/insurance_append_v6.jsonl")
DEFAULT_OUT = Path("data/datasets/docclass_merged_v6.jsonl")
EXPECTED_V6_ROWS = 1650

# doc_type -> corpus rank (deterministic fusion order; mirrors the v5 corpus
# order contract CUAD -> MAUD -> S-1 -> Enron -> DE-SynPUF)
CORPUS_RANK = {
    "contract": 0,
    "merger_agreement": 1,
    "corporate_record": 2,
    "correspondence": 3,
    "insurance_claim": 4,
}

# gt_fields keys preserved from the parent GT parquet (column-presence-checked
# per shard — the purpose/gist trio exists only where the labeler pushed it)
PARENT_GT_KEYS = (
    "label_evidence", "content_topic", "topic_evidence",
    "sentiment_score", "sentiment_label", "sentiment_evidence",
    "claim_number", "policy_number", "insurer", "insured_party",
    "claim_type", "date_of_loss", "date_filed", "claimed_amount",
    "adjuster", "damages_description", "coverage_determination",
    "denial_reasons", "supporting_documents",
    "cuad_clause_labels", "maud_clause_labels",
    "intent", "subject_matter", "keywords",
)


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_parent(blind_dir: Path, gt_dir: Path) -> list[dict]:
    """v5 parent rows: blind parquet shards joined to GT on filename 1:1."""
    import pyarrow.parquet as pq

    blind: dict[str, dict] = {}
    for shard in sorted(blind_dir.glob("**/*.parquet")):
        table = pq.read_table(shard)
        names = table.column("filename").to_pylist()
        for i, fn in enumerate(names):
            md = table.column("metadata")[i].as_py()
            blind[str(fn)] = {
                "filename": str(fn),
                "doc_text": str(table.column("doc_text")[i].as_py() or ""),
                "prompt": str(table.column("prompt")[i].as_py() or ""),
                "split": "unassigned",  # GT join fills the family split
                "metadata": md if isinstance(md, dict) else {},
            }
    gt: dict[str, dict] = {}
    gt_columns: dict[str, list[str]] = {}
    for shard in sorted(gt_dir.glob("**/*.parquet")):
        table = pq.read_table(shard)
        cols = set(table.column_names)
        gt_columns[shard.name] = sorted(cols & set(PARENT_GT_KEYS))
        for i, fn in enumerate(table.column("filename").to_pylist()):
            fn = str(fn)
            assert fn not in gt, f"duplicate parent GT filename: {fn}"
            gt[fn] = {
                "expected": str(table.column("expected")[i].as_py() or "").strip(),
                "expected_subclass": str(
                    table.column("expected_subclass")[i].as_py() or "").strip(),
                "split": str(table.column("split")[i].as_py() or "").strip(),
                "gt_fields": {k: table.column(k)[i].as_py()
                              for k in PARENT_GT_KEYS if k in cols},
            }
    rows = []
    for fn, b in blind.items():
        g = gt.get(fn)
        assert g is not None, f"parent blind row without GT join partner: {fn}"
        rows.append({**b, "expected": g["expected"],
                     "expected_subclass": normalize_contract_subclass(
                         g["expected_subclass"]),
                     "split": g["split"] or assign_split(fn),
                     "gt_fields": g["gt_fields"]})
    missing_gt = [fn for fn in gt if fn not in blind]
    assert not missing_gt, f"{len(missing_gt)} GT rows without blind join partner"
    print(f"parent: {len(rows)} rows | GT shard column coverage: "
          f"{ {k: len(v) for k, v in gt_columns.items()} }")
    return rows


def load_append(path: Path, expected_class: str) -> list[dict]:
    """KANBAN-105 append rows, split-rule re-asserted + canon-normalized."""
    from scripts.datasets.build_docclass_v5 import CLAIM_GT_KEYS

    rows = []
    for r in read_jsonl(path):
        assert r.get("expected") == expected_class, \
            f"{path}: expected {expected_class}, got {r.get('expected')!r}"
        want = assign_split(str(r["filename"]))
        assert r.get("split") == want, \
            f"{r['filename']}: append split {r.get('split')!r} != family rule {want!r}"
        r["expected_subclass"] = normalize_contract_subclass(
            str(r.get("expected_subclass") or ""))
        r.setdefault("prompt", "")
        r.setdefault("gt_fields", {})
        r.setdefault("metadata", {})
        if expected_class == "insurance_claim":
            # v5 promotion law: the 13 InsuranceClaimExtraction answer keys
            # live in gt_fields and NEVER in the blind-side metadata.
            gt_raw = r["metadata"].pop("ground_truth", None) or {}
            gf = r.setdefault("gt_fields", {})
            for key in CLAIM_GT_KEYS:
                gf.setdefault(key, gt_raw.get(key))
        rows.append(r)
    print(f"append {path.name}: {len(rows)} {expected_class} rows "
          f"({dict(sorted(Counter(r['expected_subclass'] for r in rows).items()))})")
    return rows


def load_original_files(path: Path) -> dict[str, str]:
    """filename -> Hub-relative original-file path (attach_original_files.py)."""
    mapping = {}
    for r in read_jsonl(path):
        mapping[str(r["filename"])] = str(r["original_file"])
    return mapping


def build_v6(parent: list[dict], corr_append: list[dict],
             ins_append: list[dict]) -> list[dict]:
    """Fuse parent + appends under the corpus-order + determinism laws."""
    merged = []
    for r in parent + corr_append + ins_append:
        rank = CORPUS_RANK.get(str(r.get("expected") or ""))
        assert rank is not None, f"unknown doc_type {r.get('expected')!r}"
        merged.append((rank, str(r["filename"]), r))
    merged.sort(key=lambda t: (t[0], t[1]))
    rows = [t[2] for t in merged]

    filenames = [r["filename"] for r in rows]
    assert len(filenames) == len(set(filenames)), "duplicate filenames post-fusion"
    bad = [r["filename"] for r in rows
           if not (r.get("expected_subclass") or "").strip()
           or r.get("split") not in ("train", "test")
           or not (r.get("doc_text") or "").strip()]
    assert not bad, f"{len(bad)} rows fail the schema guard: {bad[:5]}"
    canon = [r["filename"] for r in rows
             if normalize_contract_subclass(r["expected_subclass"])
             != r["expected_subclass"]]
    assert not canon, f"canon guard tripped: {sorted(canon)[:5]}"
    return rows


def census(rows: list[dict]) -> str:
    types = Counter(r["expected"] for r in rows)
    lines = [f"rows={len(rows)} doc_types={dict(sorted(types.items()))} "
             f"strata={len({(r['expected'], r['expected_subclass']) for r in rows})}"]
    for (dt, sub), n in sorted(Counter((r["expected"], r["expected_subclass"])
                                       for r in rows).items()):
        lines.append(f"  {dt}/{sub}: {n}")
    return "\n".join(lines)


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-blind-dir", type=Path, required=True,
                        help="dir with the v5 default config parquet shards")
    parser.add_argument("--parent-gt-dir", type=Path, required=True,
                        help="dir with the v5 ground_truth parquet shards")
    parser.add_argument("--correspondence-append", type=Path,
                        default=DEFAULT_CORR_APPEND)
    parser.add_argument("--insurance-append", type=Path, default=DEFAULT_INS_APPEND)
    parser.add_argument("--original-files-mapping", type=Path, default=None,
                        help="original_files_mapping.jsonl from "
                             "attach_original_files.py (optional; adds the "
                             "cast-safe metadata.original_file column)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    parent = load_parent(args.parent_blind_dir, args.parent_gt_dir)
    corr = load_append(args.correspondence_append, "correspondence")
    # rev 1: the insurance append is OPTIONAL — an absent staging file means
    # the +200 claims boost has not landed yet (documented KANBAN-105 residue)
    ins = (load_append(args.insurance_append, "insurance_claim")
           if args.insurance_append.exists() else [])

    merged = build_v6(parent, corr, ins)
    if args.original_files_mapping:
        mapping = load_original_files(args.original_files_mapping)
        # cast-safe law: EVERY row carries the key — the mapping from
        # attach_original_files.py now covers all five classes (file-complete
        # corpus, KANBAN-105 human directive); "" survives only as the
        # defensive fallback for an unmapped filename.
        # Applied BEFORE normalize_metadata_rows so the key joins the union.
        hits = 0
        for r in merged:
            v = mapping.get(r["filename"], "")
            r["metadata"]["original_file"] = v
            hits += bool(v)
        print(f"original_file mapped: {hits}/{len(merged)} rows "
              f"(mapping {len(mapping)} entries; '' elsewhere)")
    else:
        print("no --original-files-mapping: rows carry no original_file column")
    merged = normalize_metadata_rows(merged)
    print("\nv6 census:")
    print(census(merged))
    expected = len(parent) + len(corr) + len(ins)
    if len(merged) != expected:
        print(f"WARNING: fused {len(merged)} rows != inputs "
              f"({len(parent)} parent + {len(corr)} corr + {len(ins)} ins)",
              file=sys.stderr)
    if len(ins) == 0:
        print(f"NOTE: insurance append is EMPTY — this revision publishes "
              f"{len(merged)} rows; the +200 claims boost (final v6 target "
              f"{EXPECTED_V6_ROWS}) is a documented follow-up revision "
              f"(KANBAN-105 residue)", file=sys.stderr)
    purpose_labeled = sum(1 for r in merged
                          if (r.get("gt_fields") or {}).get("intent"))
    print(f"purpose/gist GT (intent) present on {purpose_labeled} rows "
          f"(new append rows fill in via the incremental labeler pass)")

    if args.dry_run:
        print(f"\nDry run: would write {len(merged)} rows -> {args.out}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in merged:
            fh.write(safe_jsonl_line(row) + "\n")
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    print(f"\nWrote {len(merged)} rows -> {args.out} (sha256 {digest[:16]}…)")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
