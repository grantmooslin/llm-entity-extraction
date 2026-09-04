#!/usr/bin/env python3
"""Build docclass-merged **v5**: the four-class parent + CMS DE-SynPUF
``insurance_claim`` rows appended from the dedicated claims dataset.

KANBAN-084 (2026-08-23 human directive): the pilot sample for the Mailroom
visualizer needs every doc type present in the family, and the family gains
its fifth class here. Sources:

* v4 base  : ``Lucius-Morningstar/mailroom-corpus`` @ ``407bf55c993a006689aa1b6e03e57c428c852e98``
             (datasets-server parquet shards, sha256-pinned below)
* claims   : ``Lucius-Morningstar/cms-desynpuf-insurance-claims``
             (produced by Exios66/claims-data-eda; rendered EOBs with a
             verbatim-GT contract aligned to mailroom's InsuranceClaimExtraction)

Fusion laws honored:

* **Single-sourced splits** — ``assign_split`` is IMPORTED from
  ``build_docclass_merged`` (md5(filename)%10==0 -> test). The claims repo
  keyed its own train/test placement on record_id (filename minus ".txt"),
  which differs on 65/400 rows; at fusion the FAMILY rule wins and the delta
  is disclosed on the dataset card.
* **No GT in the blind surface** — claims rows carry a nested
  ``metadata.ground_truth`` dict (13 InsuranceClaimExtraction answer keys).
  Those keys are PROMOTED to row-level ``gt_fields`` here and stripped from
  metadata before any normalization, so the blind config can never leak them.
* **Cast-safe metadata** — the house ``normalize_metadata_rows`` union/str
  rules apply unchanged.
* **Determinism** — corpus order contract(CUAD) -> merger_agreement(MAUD) ->
  corporate_record(S-1) -> correspondence(Enron) -> insurance_claim(SynPUF),
  filename-sorted within each corpus; rebuild is byte-identical.

Usage:
    python scripts/datasets/build_docclass_v5.py \
        --source-dir /tmp/docclass_pilot --out data/datasets/docclass_merged_v5.jsonl
    python scripts/datasets/build_docclass_v5.py --dry-run --source-dir ...
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
from scripts.datasets._jsonl_safety import safe_jsonl_line

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets.build_docclass_merged import (  # noqa: E402
    assign_split,
    normalize_contract_subclass,
    normalize_metadata_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

PARENT_REPO = "Lucius-Morningstar/mailroom-corpus"
CLAIMS_REPO = "Lucius-Morningstar/cms-desynpuf-insurance-claims"
PARENT_SHA = "407bf55c993a006689aa1b6e03e57c428c852e98"

# sha256 prefixes recorded at download time (2026-08-23, datasets-server
# refs/convert/parquet + claims main-branch layout). The loader REFUSES to
# build from unverified bytes (golden rule 3, hf-dataset-publishing).
EXPECTED_SHARDS: dict[str, tuple[int, str]] = {
    # name: (exact size, sha256 prefix)
    "default_train.parquet": (18462051, "64f330c0d3efd5ed"),
    "default_test.parquet": (2182626, "855eec2c68f2e109"),
    "gt_train.parquet": (22442, "0588066eaf0f1af8"),
    "gt_test.parquet": (7267, "091455b302668d0f"),
    "claims_train.parquet": (158005, "7a0fbb3f79928d01"),
    "claims_test.parquet": (22544, "8a0f51545868afd8"),
}

# The 13 InsuranceClaimExtraction answer keys promoted from claims
# metadata.ground_truth into the widened ground-truth surface.
CLAIM_GT_KEYS: tuple[str, ...] = (
    "claim_number", "policy_number", "insurer", "insured_party",
    "claim_type", "date_of_loss", "date_filed", "claimed_amount",
    "adjuster", "damages_description", "coverage_determination",
    "denial_reasons", "supporting_documents",
)

# Clause-level GT surfaces (KANBAN-084 directive addendum 2026-08-23):
# critical for entity-extraction scoring on contract / merger_agreement rows.
CUAD_ANNOTATIONS = Path("data/cuad_pdfs/CUAD_v1.json")
MAUD_CLASSIFICATION = Path("data/maud/classification.jsonl")
CLAUSE_GT_KEYS: tuple[str, ...] = ("cuad_clause_labels", "maud_clause_labels")


def _norm_key(s: str) -> str:
    """Aggressive key normalization: alnum-lowercase only."""
    import re as _re
    return _re.sub(r"[^a-z0-9]", "", s.lower())


def load_cuad_clause_gt(repo_root: Path | None = None) -> dict[str, dict]:
    """title-norm -> clause-name -> [{text, start}] from the official CUAD
    annotation JSON (same source masterlabels.csv renders)."""
    path = (repo_root or REPO_ROOT) / CUAD_ANNOTATIONS
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        d = json.load(fh)
    for c in d.get("data", []):
        qas: dict[str, list] = {}
        for qa in c["paragraphs"][0].get("qas", []):
            nm = qa["id"].split("__", 1)[1]
            qas[nm] = [{"text": a.get("text") or "",
                        "start": a.get("answer_start")}
                       for a in qa.get("answers", [])]
        out[_norm_key(c["title"])] = {"clauses": qas}
    return out


def load_maud_clause_gt(repo_root: Path | None = None) -> dict[str, dict]:
    """contract_id ('contract_N') -> task -> gold label payload from MAUD's
    classification dump (category / answer / valid classes / label idx)."""
    path = (repo_root or REPO_ROOT) / MAUD_CLASSIFICATION
    import re as _re

    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            m = _re.match(r"maud_(contract_\d+)_\d+", r.get("filename") or "")
            if not m:
                continue
            md = r.get("metadata") or {}
            task = str(md.get("task") or "")
            out.setdefault(m.group(1), {})[task] = {
                "category": str(md.get("category") or ""),
                "answer": str(md.get("answer") or ""),
                "valid_classes": [str(x) for x in (md.get("valid_classes") or [])],
                "label_idx": md.get("label_idx"),
                "excerpt_chars": len(r.get("doc_text") or ""),
            }
    return out


def attach_clause_gt(merged: list[dict], cuad_gt: dict[str, dict],
                     maud_gt: dict[str, dict]) -> dict[str, int]:
    """Attach ``gt_fields['cuad_clause_labels']`` / ['maud_clause_labels']
    (compact JSON strings) to contract / merger rows respectively. Returns
    join stats for the build log."""
    stats = {"cuad_total": 0, "cuad_joined": 0,
             "maud_total": 0, "maud_joined": 0}
    for r in merged:
        gf = r.setdefault("gt_fields", {})
        gf.setdefault("cuad_clause_labels", None)
        gf.setdefault("maud_clause_labels", None)
        if r.get("expected") == "contract":
            stats["cuad_total"] += 1
            md = r.get("metadata") or {}
            stem = _norm_key(str(md.get("pdf_path") or "").rsplit("/", 1)[-1])
            hit = cuad_gt.get(stem)
            if hit is None:
                # fallback: the stored filename stem (mangled variants)
                stem2 = _norm_key(str(r["filename"]).rsplit(".", 1)[0])
                hit = cuad_gt.get(stem2)
            if hit is not None:
                gf["cuad_clause_labels"] = json.dumps(
                    hit["clauses"], sort_keys=True, ensure_ascii=False)  # KANBAN-088-EXEMPT: field value; row-level write_jsonl() sanitizes
                stats["cuad_joined"] += 1
        elif r.get("expected") == "merger_agreement":
            stats["maud_total"] += 1
            cid = str((r.get("metadata") or {}).get("contract") or "")
            tasks = maud_gt.get(cid)
            if tasks:
                gf["maud_clause_labels"] = json.dumps(
                    tasks, sort_keys=True, ensure_ascii=False)  # KANBAN-088-EXEMPT: field value; row-level write_jsonl() sanitizes
                stats["maud_joined"] += 1
    return stats


def verify_shards(source_dir: Path) -> None:
    """Refuse to build unless every pinned shard is byte-present."""
    missing: list[str] = []
    bad: list[str] = []
    for name, (size, sha_prefix) in EXPECTED_SHARDS.items():
        path = source_dir / name
        if not path.exists():
            missing.append(name)
            continue
        blob = path.read_bytes()
        if len(blob) != size:
            bad.append(f"{name}: size {len(blob)} != {size}")
            continue
        if not hashlib.sha256(blob).hexdigest().startswith(sha_prefix):
            bad.append(f"{name}: sha256 mismatch vs {sha_prefix}")
    if missing or bad:
        raise SystemExit(
            "Source shards failed verification — refusing to build.\n"
            f"  missing: {missing}\n  mismatched: {bad}\n"
            "Re-download via the datasets-server /parquet URLs for "
            f"{PARENT_REPO} (@{PARENT_SHA[:12]}) and {CLAIMS_REPO}."
        )


def _read_parquet_rows(path: Path) -> list[dict]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    cols = {name: table.column(name).to_pylist() for name in table.column_names}
    n = table.num_rows
    return [{k: v[i] for k, v in cols.items()} for i in range(n)]


def load_parent_default(source_dir: Path) -> list[dict]:
    """Blind-side parent rows (filename/doc_text/prompt/split/metadata)."""
    rows: list[dict] = []
    for split in ("train", "test"):
        for r in _read_parquet_rows(source_dir / f"default_{split}.parquet"):
            rows.append({
                "filename": r["filename"],
                "doc_text": r["doc_text"],
                "prompt": r.get("prompt") or "",
                "split": r.get("split") or split,
                "metadata": r.get("metadata") if isinstance(r.get("metadata"), dict) else {},
            })
    return rows


def load_parent_gt(source_dir: Path) -> dict[str, dict]:
    """filename -> GT key map (expected / expected_subclass / enrichment)."""
    gt: dict[str, dict] = {}
    for split in ("train", "test"):
        for r in _read_parquet_rows(source_dir / f"gt_{split}.parquet"):
            fn = r["filename"]
            assert fn not in gt, f"duplicate GT filename: {fn}"
            gt[fn] = {
                "expected": r["expected"],
                "expected_subclass": r["expected_subclass"],
                "label_evidence": r.get("label_evidence"),
                "content_topic": r.get("content_topic"),
                "topic_evidence": r.get("topic_evidence"),
                "sentiment_score": r.get("sentiment_score"),
                "sentiment_label": r.get("sentiment_label"),
                "sentiment_evidence": r.get("sentiment_evidence"),
            }
    return gt


def load_claims(source_dir: Path) -> list[dict]:
    """Claims rows with GT promoted OUT of metadata into ``gt_fields``."""
    rows: list[dict] = []
    seen_splits: Counter = Counter()
    for split_file in ("claims_train.parquet", "claims_test.parquet"):
        for r in _read_parquet_rows(source_dir / split_file):
            md = r["metadata"]
            if isinstance(md, str):
                md = json.loads(md)
            md = dict(md or {})
            gt_raw = md.pop("ground_truth", None) or {}
            # Family split rule WINS over the source's record_id-keyed files.
            fn = r["filename"]
            fam_split = assign_split(fn)
            src_split = "train" if split_file.endswith("train.parquet") else "test"
            seen_splits[(src_split, fam_split)] += 1
            rows.append({
                "filename": fn,
                "doc_text": r["doc_text"],
                "prompt": r.get("prompt") or "",
                "expected": str(r.get("expected") or "insurance_claim"),
                "expected_subclass": str(r.get("expected_subclass") or ""),
                "split": fam_split,
                "gt_fields": {k: gt_raw.get(k) for k in CLAIM_GT_KEYS},
                "metadata": md,
            })
    moved = sum(v for (src, fam), v in seen_splits.items() if src != fam)
    print(f"  claims: split recomputed under the family rule "
          f"(moved vs source placement: {moved}/400)")
    return rows


def build_v5(parent_blind: list[dict], parent_gt: dict[str, dict],
             claims: list[dict]) -> list[dict]:
    """Fuse into the v5 row list (legacy combined shape + gt_fields)."""
    merged: list[dict] = []
    for r in sorted(parent_blind, key=lambda x: x["filename"]):
        gt = parent_gt.get(r["filename"])
        assert gt is not None, (
            f"parent blind row without GT join partner: {r['filename']}")
        merged.append({
            "filename": r["filename"],
            "doc_text": r["doc_text"],
            "prompt": r["prompt"],
            "expected": gt["expected"],
            # KANBAN-084: canonicalize CUAD's duplicate grouping-folder
            # spellings ('Affiliate Agreement' -> 'Affiliate_Agreements',
            # 'Endorsement Agreement' -> 'Endorsement') at construction.
            "expected_subclass": normalize_contract_subclass(
                gt["expected_subclass"]),
            "gt_fields": {k: gt[k] for k in (
                "label_evidence", "content_topic", "topic_evidence",
                "sentiment_score", "sentiment_label", "sentiment_evidence")},
            "split": r["split"],
            "metadata": r["metadata"],
        })
    merged.extend(sorted(claims, key=lambda x: x["filename"]))

    filenames = [r["filename"] for r in merged]
    assert len(filenames) == len(set(filenames)), "duplicate filenames post-fusion"
    # Every row must carry a non-empty subclass + legal split + text.
    bad = [r["filename"] for r in merged
           if not (r.get("expected_subclass") or "").strip()
           or r.get("split") not in ("train", "test")
           or not (r.get("doc_text") or "").strip()]
    assert not bad, f"{len(bad)} rows fail the schema guard: {bad[:5]}"
    return merged


def write_jsonl(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(safe_jsonl_line(r) + "\n")


def census(rows: list[dict]) -> str:
    types = Counter(r["expected"] for r in rows)
    strata = Counter((r["expected"], r["expected_subclass"]) for r in rows)
    lines = [f"rows={len(rows)} doc_types={dict(types)} strata={len(strata)}"]
    for (dt, sub), n in sorted(strata.items()):
        lines.append(f"  {dt}/{sub}: {n}")
    return "\n".join(lines)


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True,
                        help="Directory holding the six sha-pinned source shards")
    parser.add_argument("--out", type=Path,
                        default=Path("data/datasets/docclass_merged_v5.jsonl"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    verify_shards(args.source_dir)
    print(f"All {len(EXPECTED_SHARDS)} source shards verified against pins.")

    parent_blind = load_parent_default(args.source_dir)
    parent_gt = load_parent_gt(args.source_dir)
    claims = load_claims(args.source_dir)
    print(f"  parent blind rows: {len(parent_blind)} | parent GT joins: {len(parent_gt)}"
          f" | claims rows: {len(claims)}")

    merged = build_v5(parent_blind, parent_gt, claims)
    cuad_gt = load_cuad_clause_gt()
    maud_gt = load_maud_clause_gt()
    stats = attach_clause_gt(merged, cuad_gt, maud_gt)
    print(f"  clause GT joins: CUAD {stats['cuad_joined']}/{stats['cuad_total']}"
          f" contracts | MAUD {stats['maud_joined']}/{stats['maud_total']} mergers")
    print("v5 census:")
    print(census(merged))
    # KANBAN-084 canon guard: no legacy duplicate spellings may survive.
    canon = {r["filename"] for r in merged
             if normalize_contract_subclass(r["expected_subclass"])
             != r["expected_subclass"]}
    assert not canon, (
        "canon guard tripped — un-normalized subclasses survived: "
        f"{sorted(canon)[:5]}")
    if len(merged) != 1210:
        print(f"WARNING: expected 1210 rows (810 parent + 400 claims), "
              f"got {len(merged)}", file=sys.stderr)
    if args.dry_run:
        print("\nDry run: no file written.")
        return 0

    write_jsonl(merged, args.out)
    print(f"\nWrote {len(merged)} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_with_args(sys.argv[1:]))
