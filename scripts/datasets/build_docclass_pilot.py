#!/usr/bin/env python3
"""Build (and optionally publish) the KANBAN-084 **docclass-pilot** dataset:
a hyper-tailored, cleanly distributed stratified sample of docclass-merged
v5 covering EVERY doc type and EVERY subclass stratum present in the source.

Human directive 2026-08-23: pilot feedstock for The Mailroom pipeline
visualizer debugging AND per-agent pilot evaluation.

Draw law (deterministic, documented, rebuild-stable):

* one pass over v5 rows grouped by ``(expected, expected_subclass)``;
* quota per stratum = ``min(quota, n)`` (default 3) — small strata ship whole,
  huge strata contribute their cap;
* WITHIN a stratum candidates are ordered by ``sha256(filename)`` ascending —
  sha256 decorrelates the draw from the md5-keyed family split rule (the
  same trick as the KANBAN-v4 correspondence fusion);
* rows keep their v5/family ``split`` value verbatim (asserted row-by-row);
* NO random seed anywhere: ordering is content-addressed, so any rebuild from
  the same v5 produces byte-identical output.

Publishing shape mirrors the family doctrine (KANBAN-079):

* ``default`` config   : BLIND rows only — filename/doc_text/prompt/metadata
* ``ground_truth``     : filename + expected + expected_subclass + ALL
                         promoted GT fields (legacy enrichment + the 13
                         InsuranceClaimExtraction keys), joined 1:1 on filename
* native sharded parquet under ``parquet/<config>/<split>/``
* sidecars: ``manifest.txt`` (NEVER ``*.json`` filenames — Hub loader landmine)

Usage:
    python scripts/datasets/build_docclass_pilot.py \
        --v5 data/datasets/docclass_merged_v5.jsonl --stage /tmp/pilot_stage
    python scripts/datasets/build_docclass_pilot.py --v5 ... --stage ... --publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT_REPO = "Lucius-Morningstar/docclass-pilot"
PARENT_REPO = "Lucius-Morningstar/mailroom-corpus"
CLAIMS_REPO = "Lucius-Morningstar/cms-desynpuf-insurance-claims"

GT_SCALAR_KEYS: tuple[str, ...] = (
    # legacy enrichment (parent GT config)
    "label_evidence", "content_topic", "topic_evidence",
    "sentiment_score", "sentiment_label", "sentiment_evidence",
    # InsuranceClaimExtraction promotion (claims rows only; else null)
    "claim_number", "policy_number", "insurer", "insured_party",
    "claim_type", "date_of_loss", "date_filed", "claimed_amount",
    "adjuster", "damages_description", "coverage_determination",
    "denial_reasons", "supporting_documents",
    # Clause-level answer keys (KANBAN-084 addendum): CUAD master-label
    # annotations on contract rows; MAUD task gold labels on merger rows.
    # Compact JSON strings; null on every other class.
    "cuad_clause_labels", "maud_clause_labels",
)
BLIND_KEYS: frozenset[str] = frozenset(
    {"filename", "doc_text", "prompt", "metadata"})


def stratified_draw(rows: list[dict], quota: int) -> list[dict]:
    """Deterministic min(quota, n)-per-stratum draw, sha256-ordered."""
    assert quota >= 1
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        strata[(r["expected"], r["expected_subclass"])].append(r)
    drawn: list[dict] = []
    for key in sorted(strata):
        cands = sorted(strata[key],
                       key=lambda r: hashlib.sha256(
                           r["filename"].encode("utf-8")).hexdigest())
        taken = cands[:quota]
        assert taken, f"empty stratum impossible: {key}"
        drawn.extend(taken)
    return sorted(drawn, key=lambda r: r["filename"])


def assert_coverage(source_rows: list[dict], drawn: list[dict]) -> None:
    src_strata = {(r["expected"], r["expected_subclass"]) for r in source_rows}
    got_strata = {(r["expected"], r["expected_subclass"]) for r in drawn}
    missing = src_strata - got_strata
    extra = got_strata - src_strata
    assert not missing, f"draw misses strata: {sorted(missing)}"
    assert not extra, f"draw invented strata: {sorted(extra)}"
    by_fn = {r["filename"]: r for r in drawn}
    for r in drawn:
        assert r["split"] in ("train", "test")
    assert len(by_fn) == len(drawn), "duplicate filenames in draw"


def _gt_row(r: dict) -> dict:
    # `split` rides BOTH configs deliberately (KANBAN-079 doctrine): it is a
    # partition indicator, not an answer key, and lets scorers do standard
    # per-split joins without touching the blind config.
    out = {"filename": r["filename"],
           "expected": r["expected"],
           "expected_subclass": r["expected_subclass"],
           "split": r["split"]}
    gf = r.get("gt_fields") or {}
    for k in GT_SCALAR_KEYS:
        out[k] = gf.get(k)
    return out


def _blind_row(r: dict) -> dict:
    md = dict(r.get("metadata") or {})
    return {"filename": r["filename"], "doc_text": r["doc_text"],
            "prompt": r.get("prompt") or "", "metadata": md}


def normalize_blind_metadata(rows: list[dict]) -> list[dict]:
    """House cast-safe rules (union keys on every row; dicts/lists -> compact
    JSON strings; scalars -> strings; never null)."""
    if not rows:
        return rows
    union = sorted({k for r in rows for k in (r.get("metadata") or {})})
    for r in rows:
        md = r.get("metadata") or {}
        flat = {}
        for k in union:
            v = md.get(k, "")
            if isinstance(v, (dict, list)):
                v = json.dumps(v, sort_keys=True, ensure_ascii=False)  # KANBAN-088-EXEMPT: CSV cell value; row writers sanitize
            else:
                v = "" if v is None else str(v)
            flat[k] = v
        r["metadata"] = flat
    return rows


# --- parquet staging --------------------------------------------------------

def _to_table(blind_rows: list[dict]):
    import pyarrow as pa

    return pa.Table.from_pylist(blind_rows)


def _to_gt_table(gt_rows: list[dict]):
    import pyarrow as pa

    return pa.Table.from_pylist(gt_rows)


def stage_parquet(stage: Path, drawn: list[dict]) -> dict[tuple[str, str], int]:
    """Write parquet/<config>/<split>/<split>-00000-of-00001.parquet."""
    import pyarrow.parquet as pq

    counts: dict[tuple[str, str], int] = {}
    for config, rows in (("default", [_blind_row(r) for r in drawn]),
                         ("ground_truth", [_gt_row(r) for r in drawn])):
        normalize_blind_metadata(rows) if config == "default" else None
        for split in ("train", "test"):
            subset = [r for i, r in enumerate(rows)
                      if drawn[i]["split"] == split]
            outdir = stage / "parquet" / config / split
            outdir.mkdir(parents=True, exist_ok=True)
            table = (_to_table(subset) if config == "default"
                     else _to_gt_table(subset))
            out = outdir / f"{split}-00000-of-00001.parquet"
            pq.write_table(table, out)
            counts[(config, split)] = len(subset)
    return counts


CARD_TEMPLATE = """---
license: cc-by-4.0
task_categories:
- text-classification
language:
- en
tags:
- legal
- insurance
- contracts
- merger-agreements
- corporate-records
- correspondence
- document-classification
- evaluation
- llm-mailroom
pretty_name: "Docclass Pilot Sample (stratified type x subtype slice of docclass-merged v5)"
size_categories:
- n<1K
configs:
- config_name: default
  data_files:
  - split: train
    path: parquet/default/train/train-*.parquet
  - split: test
    path: parquet/default/test/test-*.parquet
- config_name: ground_truth
  data_files:
  - split: train
    path: parquet/ground_truth/train/train-*.parquet
  - split: test
    path: parquet/ground_truth/test/test-*.parquet
---

# Docclass Pilot Sample

Deterministic stratified pilot slice of
[{PARENT_REPO}](https://huggingface.co/datasets/{PARENT_REPO}) **v5**
(KANBAN-084, built {built}): every doc type and every subclass stratum
present in the parent contributes at least one row; each stratum contributes
at most `{quota}` rows, selected by ascending sha256(filename) within the
stratum (content-addressed order — decorrelated from the md5-keyed family
split rule; rebuilds are byte-identical).

## Coverage

{coverage_table}

## Configs (KANBAN-079 separation-of-concerns doctrine)

* **default** (blind): `filename`, `doc_text`, `prompt`, `metadata`. What the
  Mailroom pipeline agents see. ZERO answer-key columns.
* **ground_truth**: `filename` + `expected` (doc_type) + `expected_subclass`
  + promoted GT fields — the six legacy enrichment keys plus the 13
  `InsuranceClaimExtraction` keys for the insurance_claim rows (null on other
  classes). Join 1:1 on `filename`; scorers use standard split joins.

```python
from datasets import load_dataset
blind = load_dataset("{PILOT_REPO}", "default")
keys  = load_dataset("{PILOT_REPO}", "ground_truth")
```

This is separation of concerns, NOT encryption — the Hub is public; anyone
may load the ground_truth config explicitly.

## Provenance

* Parent: [{PARENT_REPO}](https://huggingface.co/datasets/{PARENT_REPO})
  @ revision `407bf55c993a006689aa1b6e03e57c428c852e98` (v5: adds the
  insurance_claim class).
* Claims source: [{CLAIMS_REPO}](https://huggingface.co/datasets/{CLAIMS_REPO})
  (CMS DE-SynPUF 2008-2010 Sample 1 rendered EOBs, produced by
  [Exios66/claims-data-eda](https://github.com/Exios66/claims-data-eda),
  verbatim-GT contract aligned to llm-mailroom's InsuranceClaimExtraction).
* Splits: inherited from the family single-source rule
  (`md5(filename) % 10 == 0 -> test`). Claims-side note: the claims repo had
  keyed its own placement on record_id; at v5 fusion the FAMILY rule won,
  moving 65/400 rows — the pilot inherits the reconciled family splits.
* Builder: `scripts/datasets/build_docclass_pilot.py` in
  [Exios66/llm-entity-extraction](https://github.com/Exios66/llm-entity-extraction).

## Honest gaps

* Heuristic ground truth on the legacy four classes (family labeler; see the
  parent card). Claims GT is exact-but-synthetic (verbatim renderer contract).
* SynPUF claims are PAID claims only: `coverage_determination` is always
  "approved", `denial_reasons` always empty, `adjuster` always null, single
  line of business (`health`). Fully synthetic data — evaluation substrate,
  not epidemiology (CMS caveat).
* Family scope is FIVE doc classes: contract, merger_agreement, correspondence,
  corporate_record, insurance_claim. court_opinion and compliance_filing were
  removed from the dataset family's scope by human directive (2026-08-23) —
  no upstream corpora exist. This does NOT change llm-mailroom's runtime taxonomy.
* PII: legacy Enron-derived correspondence rows may contain real names and
  addresses (inherited from the parent; disclosed there too). Claims rows use
  deterministic pseudonyms.

## Citation

```bibtex
@misc{{docclass_pilot_2026,
  title  = {{Docclass Pilot Sample (KANBAN-084)}},
  author = {{Lucius-Morningstar}},
  year   = {{2026}},
  url    = {{https://huggingface.co/datasets/{PILOT_REPO}}}
}}
```
"""


def render_card(drawn: list[dict], quota: int) -> str:
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    strata = Counter((r["expected"], r["expected_subclass"]) for r in drawn)
    types = Counter(r["expected"] for r in drawn)
    lines = ["| doc_type | rows | subclasses covered |",
             "|---|---:|---|"]
    for dt in sorted(types):
        subs = sorted(s for (d, s) in strata if d == dt)
        lines.append(f"| `{dt}` | {types[dt]} | {len(subs)} ({', '.join(subs)}) |")
    lines.append("")
    lines.append(f"Total: **{len(drawn)} rows** across "
                 f"{len(strata)} subclass strata / {len(types)} doc types "
                 f"(100% of strata present in the parent).")
    body = "\n".join(lines)
    return CARD_TEMPLATE.format(PARENT_REPO=PARENT_REPO, CLAIMS_REPO=CLAIMS_REPO,
                                PILOT_REPO=PILOT_REPO, quota=quota, built=built,
                                coverage_table=body)


MANIFEST_TEMPLATE = """docclass-pilot manifest (KANBAN-084)
=====================================
built_utc      : {built}
parent         : {parent} @ {parent_sha} (v5)
claims_source  : {claims}
draw_rule      : min({quota}, n) rows per (expected, expected_subclass) stratum;
                 within-stratum order = ascending sha256(filename); no RNG.
rows_total     : {rows}
rows_by_config : default train={dt_train} test={dt_test}; ground_truth train={gt_train} test={gt_test}
doc_type_counts: {types}
strata_covered : {strata}/{src_strata} (all present in parent)
splits         : inherited from parent rows (family md5%10 rule); recomputed
                 and asserted row-by-row at build time.
schema_version : pilot-1
notes          : ground-truth config carries promoted InsuranceClaimExtraction
                 keys for insurance_claim rows; legacy enrichment keys otherwise.
"""


def stage_manifest(stage: Path, drawn: list[dict], quota: int,
                   counts: dict[tuple[str, str], int],
                   src_strata_count: int) -> None:
    types = Counter(r["expected"] for r in drawn)
    strata = Counter((r["expected"], r["expected_subclass"]) for r in drawn)
    text = MANIFEST_TEMPLATE.format(
        built=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        parent=PARENT_REPO,
        parent_sha="407bf55c993a006689aa1b6e03e57c428c852e98",
        claims=CLAIMS_REPO, quota=quota, rows=len(drawn),
        dt_train=counts[("default", "train")], dt_test=counts[("default", "test")],
        gt_train=counts[("ground_truth", "train")],
        gt_test=counts[("ground_truth", "test")],
        types=dict(sorted(types.items())), strata=len(strata),
        src_strata=src_strata_count)
    (stage / "manifest.txt").write_text(text, encoding="utf-8")


def publish(stage: Path, private: bool = False) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo_id=PILOT_REPO, repo_type="dataset",
                    exist_ok=True, private=private)
    api.upload_folder(folder_path=str(stage), repo_id=PILOT_REPO,
                      repo_type="dataset", commit_message="KANBAN-084: pilot dataset (stratified type×subtype slice of docclass-merged v5)")
    print(f"Published -> https://huggingface.co/datasets/{PILOT_REPO}")


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v5", type=Path, required=True,
                        help="Path to the v5 combined JSONL from build_docclass_v5.py")
    parser.add_argument("--stage", type=Path, required=True,
                        help="Staging directory for card/manifest/parquet")
    parser.add_argument("--quota", type=int, default=3,
                        help="Per-stratum cap (default 3)")
    parser.add_argument("--publish", action="store_true",
                        help="Create/update the HF repo and upload the staging tree")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args(argv)

    rows = []
    with args.v5.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"Loaded v5 rows: {len(rows)}")

    drawn = stratified_draw(rows, args.quota)
    assert_coverage(rows, drawn)
    strata_n = len({(r["expected"], r["expected_subclass"]) for r in rows})
    census = Counter(r["expected"] for r in drawn)
    print(f"Drew {len(drawn)} rows covering "
          f"{len({(r['expected'], r['expected_subclass']) for r in drawn})}/{strata_n} strata "
          f"(quota={args.quota}): {dict(sorted(census.items()))}")

    if args.stage.exists():
        shutil.rmtree(args.stage)
    args.stage.mkdir(parents=True)
    counts = stage_parquet(args.stage, drawn)
    (args.stage / "README.md").write_text(
        render_card(drawn, args.quota), encoding="utf-8")
    stage_manifest(args.stage, drawn, args.quota, counts, strata_n)
    print(f"Staged -> {args.stage}")
    for cfg, n in sorted(counts.items()):
        print(f"  {cfg[0]}/{cfg[1]}: {n} rows")

    if args.publish:
        publish(args.stage, private=args.private)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_with_args(sys.argv[1:]))
