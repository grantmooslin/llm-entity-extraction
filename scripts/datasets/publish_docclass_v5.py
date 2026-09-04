#!/usr/bin/env python3
"""Publish docclass-merged **v5** to the Hub — the KANBAN-084 widened
dataset: four-class parent + CMS DE-SynPUF insurance_claim rows +
clause-level answer keys (CUAD annotations / MAUD classification gold).

Evolution discipline (family law):

* sharded parquet under ``parquet/<config>/<split>/`` OVERWRITES the v4
  shards in place (same names, so the card YAML globs stay valid);
* the legacy combined ``docclass_merged.jsonl`` STAYS in-tree untouched
  (pinned consumers keep working; it still describes v4 rows);
* ``manifest.txt`` is replaced with the v5 lineage record;
* the README card evolves surgically: same structure, updated counts,
  claims provenance, clause-GT section, honest gaps.

Usage:
    python scripts/datasets/publish_docclass_v5.py \
        --v5 data/datasets/docclass_merged_v5.jsonl --stage /tmp/v5_stage
    python scripts/datasets/publish_docclass_v5.py --v5 ... --stage ... --publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets.build_docclass_merged import normalize_metadata_rows  # noqa: E402
from scripts.datasets.build_docclass_pilot import GT_SCALAR_KEYS  # noqa: E402
from scripts.datasets.build_docclass_v5 import CLAIM_GT_KEYS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_ID = "Lucius-Morningstar/mailroom-corpus"
LEGACY_JSONL = "docclass_merged.jsonl"

GT_COLUMNS: list[str] = (
    ["filename", "expected", "expected_subclass"]          # keys (split added below)
    + [k for k in GT_SCALAR_KEYS if k not in ("cuad_clause_labels",
                                              "maud_clause_labels")]
    + ["cuad_clause_labels", "maud_clause_labels"]
)


def _gt_row(r: dict) -> dict:
    out = {"filename": r["filename"], "expected": r["expected"],
           "expected_subclass": r["expected_subclass"],
           "split": r["split"]}
    gf = r.get("gt_fields") or {}
    for k in GT_SCALAR_KEYS:
        v = gf.get(k)
        # explicit-schema coercion: every string-typed column receives
        # strings-or-None only (claimed_amount rides as its string form;
        # sentiment_score keeps its dedicated float64 column)
        out[k] = None if v is None else str(v)
    return out


def _blind_row(r: dict) -> dict:
    return {"filename": r["filename"], "doc_text": r["doc_text"],
            "prompt": r.get("prompt") or "",
            "metadata": dict(r.get("metadata") or {})}


def load_v5(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    assert len(rows) == 1210, f"expected 1210 v5 rows, got {len(rows)}"
    return rows


def stage_parquet(stage: Path, rows: list[dict]) -> dict[tuple[str, str], int]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    blind = [_blind_row(r) for r in rows]
    normalize_metadata_rows(blind)

    # explicit nullable-union GT schema: ALL strings-or-null, matching the
    # parent's own storage convention (even sentiment_score rides as string);
    # clause payloads are compact JSON strings.
    gt_names = GT_COLUMNS + ["split"]
    gt_schema = pa.schema([(k, pa.string()) for k in gt_names])

    counts = {}
    for split in ("train", "test"):
        subset_b = [r for r, src in zip(blind, rows) if src["split"] == split]
        subset_g = [_gt_row(r) for r in rows if r["split"] == split]
        bdir = stage / "parquet" / "default" / split
        gdir = stage / "parquet" / "ground_truth" / split
        bdir.mkdir(parents=True, exist_ok=True)
        gdir.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(subset_b),
                       bdir / f"{split}-00000-of-00001.parquet")
        pq.write_table(pa.Table.from_pylist(subset_g, schema=gt_schema),
                       gdir / f"{split}-00000-of-00001.parquet")
        counts[("default", split)] = len(subset_b)
        counts[("ground_truth", split)] = len(subset_g)
    return counts


MANIFEST = """docclass-merged manifest — schema v5 (KANBAN-084)
==================================================
built_utc        : {built}
schema_version   : 5
rows_total       : {rows} ({types})
rows_by_config   : default train={bt} test={btest}; ground_truth train={gt} test={gtest}
strata           : {strata} (expected x expected_subclass)
v4_base_revision : 407bf55c993a006689aa1b6e03e57c428c852e98
v5_additions     : insurance_claim class (+400 rows, 4 subtypes) from
                   Lucius-Morningstar/cms-desynpuf-insurance-claims;
                   clause-level GT columns (cuad_clause_labels /
                   maud_clause_labels) in the ground_truth config only.
claims_split_note: source placement keyed md5(record_id)%10; fused under the
                   family rule md5(filename)%10 (moved {moved}/400 rows).
clause_gt_joins  : CUAD {cuad_joined}/{cuad_total} contracts (official
                   annotation JSON = masterlabels.csv source; 13753/13753
                   answers verified at exact char offsets vs stored text);
                   MAUD {maud_joined}/{maud_total} mergers (22-task gold
                   labels w/ categories + valid classes).
legacy_files     : {legacy_jsonl} retained UNTOUCHED (describes v4; kept for
                   pinned consumers). Parquet shards supersede it.
builder          : scripts/datasets/build_docclass_v5.py @ Exios66/llm-entity-extraction
"""


def stage_sidecars(stage: Path, rows: list[dict],
                   counts: dict[tuple[str, str], int], moved: int,
                   clause_stats: dict[str, int]) -> None:
    types = Counter(r["expected"] for r in rows)
    strata = Counter((r["expected"], r["expected_subclass"]) for r in rows)
    text = MANIFEST.format(
        built=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        rows=len(rows), types=dict(sorted(types.items())),
        bt=counts[("default", "train")], btest=counts[("default", "test")],
        gt=counts[("ground_truth", "train")],
        gtest=counts[("ground_truth", "test")],
        strata=len(strata), moved=moved,
        cuad_joined=clause_stats["cuad_joined"],
        cuad_total=clause_stats["cuad_total"],
        maud_joined=clause_stats["maud_joined"],
        maud_total=clause_stats["maud_total"],
        legacy_jsonl=LEGACY_JSONL)
    (stage / "manifest.txt").write_text(text, encoding="utf-8")


def render_card(rows: list[dict], moved: int,
                clause_stats: dict[str, int]) -> str:
    """Surgical evolution of the live v4 card (fetched fresh at build time).
    Regex-anchored edits with count==1 assertions — never positional slicing."""
    import re as _re
    import subprocess

    r = subprocess.run(["curl", "-sL", "--max-time", "60",
                        f"https://huggingface.co/datasets/{REPO_ID}/raw/main/README.md"],
                       capture_output=True, text=True, timeout=90)
    card = r.stdout
    assert card.startswith("---"), "could not fetch the live parent card"

    # 1) tags gain insurance (first tag block only)
    card, n = _re.subn(r"(tags:\n- legal\n)", r"\1- insurance\n",
                       card, count=1)
    assert n == 1, "tag anchor"
    # 2) pretty_name -> v5
    card, n = _re.subn(
        r'pretty_name: "Docclass Merged Corpus \(Contracts \+ Merger Agreements '
        r'\+ Corporate Records \+ Correspondence\)"',
        'pretty_name: "Docclass Merged Corpus v5 (Contracts + Merger Agreements '
        '+ Corporate Records + Correspondence + Insurance Claims)"',
        card, count=1)
    assert n == 1, "pretty_name anchor"
    # 3) headline counts
    card, n = _re.subn(
        r"Single flat document-classification surface: \*\*810 legal documents\*\* across\nfour corpora, one row per document:",
        f"Single flat document-classification surface: **{len(rows):,} legal documents** across\nfive corpora, one row per document (schema v5):",
        card, count=1)
    assert n == 1, "headline anchor"
    # 4) corpus table: insert the claims row after the Enron row's TRUE end.
    #    Long cells wrap across physical lines; each wrapped line carries
    #    pipes, the final one ends with '|'. GREEDY continuation so we span
    #    the whole logical row, then insert a clean new table row after it.
    m = _re.search(r"\| \*\*Enron correspondence sample\*\*[^\n]*\n(?:[^\n|]*\|[^\n]*\n)*",
                   card)
    assert m, "enron table row anchor"
    enron_row = m.group(0)
    claims_row = ("| **CMS DE-SynPUF rendered EOBs** | **400** | `insurance_claim` "
                  "| [Lucius-Morningstar/cms-desynpuf-insurance-claims]"
                  "(https://huggingface.co/datasets/"
                  "Lucius-Morningstar/cms-desynpuf-insurance-claims) "
                  "(CMS DE-SynPUF Sample 1 via Exios66/claims-data-eda) |\n")
    card = card.replace(enron_row, enron_row + claims_row, 1)
    # at this stage the ONLY occurrence is the inserted table row
    assert card.count("`insurance_claim`") == 1, "claims row insert"
    # 5) v5 provenance + clause-GT section before the Two-config section
    marker = "## ⚠️ Two-config layout"
    assert marker in card, "two-config anchor"
    v5_section = f"""## Schema v5 additions (KANBAN-084, 2026-08-23)

* **New class**: `insurance_claim` (+400 rows, subtypes inpatient / outpatient / carrier / pde) from [cms-desynpuf-insurance-claims](https://huggingface.co/datasets/Lucius-Morningstar/cms-desynpuf-insurance-claims) — rendered EOBs with a verbatim GT contract aligned to llm-mailroom's InsuranceClaimExtraction. Synthetic data; PAID claims only (`coverage_determination` always "approved", `denial_reasons` always empty); `adjuster` always null; single line of business (health). CMS caveat: evaluation substrate, not epidemiology.
* **Split reconciliation**: the claims source keyed its own file placement on `md5(record_id)`; this dataset applies the FAMILY rule (`md5(filename) % 10 == 0 → test`) to every row — {moved}/400 claims rows changed placement vs the source repo. The `split` column here is authoritative.
* **Clause-level GT** (ground_truth config ONLY — never in the blind config):
  * `cuad_clause_labels` on contract rows: the official CUAD annotation set (machine-readable superset of masterlabels.csv) — {clause_stats['cuad_joined']}/{clause_stats['cuad_total']} contracts joined; **13,753/13,753 answer spans verified at exact char offsets** against the stored `doc_text`. Compact JSON: clause name → [{{text, start}}].
  * `maud_clause_labels` on merger_agreement rows: MAUD gold labels across its classification tasks (category / answer / valid_classes / label_idx) — {clause_stats['maud_joined']}/{clause_stats['maud_total']} contracts joined via contract id.
  * These are the scoring substrate for entity-extraction evaluation; treat them exactly like the other GT columns (separation of concerns, not encryption).

"""
    card = card.replace(marker, v5_section + marker, 1)
    return card


def publish(stage: Path) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo_id=REPO_ID, repo_type="dataset", exist_ok=True)
    api.upload_folder(folder_path=str(stage), repo_id=REPO_ID,
                      repo_type="dataset",
                      commit_message="KANBAN-084: schema v5 — +insurance_claim class (CMS DE-SynPUF) + clause-level GT (CUAD annotations / MAUD gold)")
    print(f"Published -> https://huggingface.co/datasets/{REPO_ID}")


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--moved-rows", type=int, default=65,
                        help="claims rows whose file-placement changed under "
                             "the family split rule (recorded in manifest)")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)

    rows = load_v5(args.v5)
    print(f"Loaded {len(rows)} v5 rows")

    # clause join stats recomputed from the artifact itself (artifact-derived)
    clause_stats = {"cuad_total": 0, "cuad_joined": 0,
                    "maud_total": 0, "maud_joined": 0}
    for r in rows:
        gf = r.get("gt_fields") or {}
        if r["expected"] == "contract":
            clause_stats["cuad_total"] += 1
            clause_stats["cuad_joined"] += bool(gf.get("cuad_clause_labels"))
        elif r["expected"] == "merger_agreement":
            clause_stats["maud_total"] += 1
            clause_stats["maud_joined"] += bool(gf.get("maud_clause_labels"))
    print("clause joins:", clause_stats)

    if args.stage.exists():
        shutil.rmtree(args.stage)
    args.stage.mkdir(parents=True)
    counts = stage_parquet(args.stage, rows)
    (args.stage / "README.md").write_text(
        render_card(rows, args.moved_rows, clause_stats), encoding="utf-8")
    stage_sidecars(args.stage, rows, counts, args.moved_rows, clause_stats)
    print("Staged:", {f"{a}/{b}": n for (a, b), n in sorted(counts.items())})

    if args.publish:
        publish(args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_with_args(sys.argv[1:]))
