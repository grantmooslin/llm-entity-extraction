#!/usr/bin/env python3
"""Publish docclass-merged **v6** to the Hub — the KANBAN-105 rebalance:
v5 parent + 240 new Enron correspondence rows + the KANBAN-105 original-files
addendum (700 upstream originals under ``files/``). The +200 insurance_claim
boost is DEFERRED to a follow-up v6 revision (its claims-data-eda staging was
lost to a tmp cleanup; the rebuild is a documented card residue) — the
publisher is composition-aware and publishes whatever the fused dump holds.

Evolution discipline (family law, mirror of ``publish_docclass_v5.py``):

* sharded parquet under ``parquet/<config>/<split>/`` OVERWRITES the v5
  shards in place (same names, so the card YAML globs stay valid);
* the legacy combined ``docclass_merged.jsonl`` STAYS in-tree untouched
  (pinned consumers keep working; it still describes v4 rows);
* ``manifest.txt`` is replaced with the v6 lineage record;
* the README card evolves surgically: regex-anchored edits with count==1
  assertions — never positional slicing;
* the ground_truth config gains the ``intent`` / ``subject_matter`` /
  ``keywords`` columns on BOTH splits (the llm-mailroom purpose-GT push of
  2026-08-30 filled them on train only; new append rows carry them EMPTY
  until the incremental labeler pass fills them in a follow-up revision —
  every purpose-class row is gradable after that pass).

Usage:
    python scripts/datasets/publish_docclass_v6.py --v6 data/datasets/docclass_merged_v6.jsonl --stage /tmp/v6_stage
    python scripts/datasets/publish_docclass_v6.py --v6 ... --stage ... --publish
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets.build_docclass_merged import normalize_metadata_rows  # noqa: E402
from scripts.datasets.build_docclass_pilot import GT_SCALAR_KEYS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_ID = "Lucius-Morningstar/docclass-merged"
LEGACY_JSONL = "docclass_merged.jsonl"
V5_BASE_REVISION = "1d4753578d91aae09033b359bc32dc1b431e4c20"
PARENT_ROWS = 1210
PARENT_CORR_ROWS = 110
PARENT_INS_ROWS = 400

# the purpose/gist trio rides the GT config (the llm-mailroom labeler pushes
# it; new append rows are empty until the incremental pass)
PURPOSE_GT_KEYS: tuple[str, ...] = ("intent", "subject_matter", "keywords")

# composition-aware append counts — derived from the fused dump itself so the
# publisher can never mislabel what it is publishing (rev 1: ins_n == 0)
def corr_n(rows: list[dict]) -> int:
    return sum(1 for r in rows if r["expected"] == "correspondence") \
        - PARENT_CORR_ROWS


def ins_n(rows: list[dict]) -> int:
    return sum(1 for r in rows if r["expected"] == "insurance_claim") \
        - PARENT_INS_ROWS


def expected_total(rows: list[dict]) -> int:
    return PARENT_ROWS + corr_n(rows) + ins_n(rows)


# v6 blind-surface repair: label-equivalent keys the v4-era flat dump rode in
# metadata (duplicated by the top-level fields / the GT config columns; no
# repo consumer reads them from Hub blind metadata) — stripped at publish.
REPAIRABLE_BLIND_KEYS = {"expected_doc_type", "expected_subclass"}

# hard leaks: answer payloads that must NEVER ride in metadata — their
# presence means a real builder bug, refused (not repaired)
HARD_LEAK_KEYS = {"ground_truth", "intent", "subject_matter", "keywords",
                  "expected"}

GT_COLUMNS: list[str] = (
    ["filename", "expected", "expected_subclass"]          # keys (split added below)
    + [k for k in GT_SCALAR_KEYS if k not in ("cuad_clause_labels",
                                              "maud_clause_labels")]
    + ["cuad_clause_labels", "maud_clause_labels"]
    + list(PURPOSE_GT_KEYS)
)


def load_v6(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    # blind-surface GT leak guard FIRST (fail fast regardless of row count):
    # no answer payloads may ride in metadata (label-equivalent duplicates are
    # repaired separately by strip_blind_labels, refused here if impossible)
    for r in rows:
        leaked = HARD_LEAK_KEYS & set(r.get("metadata") or {})
        assert not leaked, f"{r['filename']}: GT keys leaked into metadata: {leaked}"
    if len(rows) != expected_total(rows):
        raise AssertionError(
            f"expected {expected_total(rows)} v6 rows "
            f"(parent {PARENT_ROWS} + corr {corr_n(rows)} + ins {ins_n(rows)}), "
            f"got {len(rows)}")
    return rows


def strip_blind_labels(rows: list[dict]) -> int:
    """v6 blind-surface repair: drop the label-equivalent metadata keys.

    The v4-era flat dump rode ``expected_doc_type`` / ``expected_subclass``
    inside metadata and the v5 publisher carried them onto the blind config
    verbatim — contradicting the card's own "NO label columns" contract. v6
    strips them (the GT config remains the sole label surface; no repo
    consumer reads the Hub blind metadata labels — the BT/Langfuse mirrors
    take labels from the GT config / top-level fields). Returns the count.
    """
    stripped = 0
    for r in rows:
        md = r.get("metadata") or {}
        hit = REPAIRABLE_BLIND_KEYS & set(md)
        if hit:
            for k in hit:
                md.pop(k)
            stripped += 1
        r["metadata"] = md
    if stripped:
        print(f"blind-surface repair: stripped {sorted(REPAIRABLE_BLIND_KEYS)} "
              f"from metadata on {stripped}/{len(rows)} rows")
    return stripped


def _blind_row(r: dict) -> dict:
    return {"filename": r["filename"], "doc_text": r["doc_text"],
            "prompt": r.get("prompt") or "",
            "metadata": dict(r.get("metadata") or {})}


def _gt_row(r: dict) -> dict:
    out = {"filename": r["filename"], "expected": r["expected"],
           "expected_subclass": r["expected_subclass"],
           "split": r["split"]}
    gf = r.get("gt_fields") or {}
    for k in GT_COLUMNS[3:]:
        v = gf.get(k)
        # explicit-schema coercion: every string-typed column receives
        # strings-or-None only (sentiment_score keeps its dedicated float
        # column in the local dump; the Hub GT config rides strings-or-null,
        # matching the v5 storage convention)
        out[k] = None if v is None else str(v)
    return out


def stage_parquet(stage: Path, rows: list[dict]) -> dict[tuple[str, str], int]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    blind = [_blind_row(r) for r in rows]
    normalize_metadata_rows(blind)

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


MANIFEST = """docclass-merged manifest — schema v6 (KANBAN-105)
=================================================
built_utc        : {built}
schema_version   : 6
rows_total       : {rows} ({types})
rows_by_config   : default train={bt} test={btest}; ground_truth train={gt} test={gtest}
strata           : {strata} (expected x expected_subclass)
v5_base_revision : {v5_base}
v6_additions     : +{corr_n} correspondence rows (stratified sha256-filename draw
                   of {corr_n} from {pool_n:,} dedup GT rows after excluding the 110
                   existing; 3-labeler verification pass GREEN — subclass/topic/
                   sentiment reproduce the Hub GT on every row; KANBAN-103 overrides
                   honored, {corr_overrides} override hits) from
                   Lucius-Morningstar/enron-correspondence-dedup;
{ins_segment}original_files   : {files_n} upstream originals under files/ ({files_bytes_mb} MB) —
                   FILE-COMPLETE CORPUS: every row carries its original
                   (contract {files_contract} CUAD source PDFs,
                   merger_agreement {files_merger} MAUD contract_N.txt,
                   corporate_record {files_corporate} EDGAR exhibit originals,
                   correspondence {files_corr} CMU maildir raw RFC822 messages
                   via Enron-Evaluation-Environment,
                   insurance_claim {files_ins} rendered EOB documents via
                   Exios66/claims-data-eda — the render IS the original).
                   metadata.original_file carries the Hub-relative path on
                   EVERY row. Sha256 per file: original_files_mapping.jsonl
                   sidecar.
purpose_gt       : intent/subject_matter/keywords on {purpose_n} rows (the
                   llm-mailroom purpose-GT push of 2026-08-30 covers the v5 train
                   purpose-class rows); new append rows are EMPTY until the
                   incremental labeler pass fills them in a follow-up revision.
blind_repair     : v6 strips the label equivalents (expected_doc_type /
                   expected_subclass) that the v4-era flat dump rode inside
                   blind metadata and v5 carried onto the default config
                   verbatim — the default config is now truly agent-blind per
                   the card contract ("NO label columns"); labels live ONLY in
                   the ground_truth config. No repo consumer read the blind
                   metadata labels (mirrors take labels from the GT config /
                   top-level fields); {stripped_n} rows repaired.
family_split     : md5(filename) % 10 == 0 -> test; recomputed and asserted for
                   every append row at fusion.
legacy_files     : {legacy_jsonl} retained UNTOUCHED (describes v4; kept for
                   pinned consumers). Parquet shards supersede it.
builder          : scripts/datasets/build_docclass_v6.py @ Exios66/llm-entity-extraction
"""


def stage_original_files(stage: Path, files_dir: Path) -> dict:
    """Copy the staged original files into the Hub tree; return stats."""
    import os

    src = files_dir / "files"
    if not src.exists():
        return {"n": 0, "bytes": 0, "by_class": {}}
    dest = stage / "files"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    by_class: dict[str, int] = {}
    total = 0
    for path in dest.rglob("*"):
        if path.is_file():
            n = path.stat().st_size
            total += n
            rel = path.relative_to(dest)
            cls = rel.parts[0] if len(rel.parts) > 1 else "other"
            by_class[cls] = by_class.get(cls, 0) + 1
    mapping = files_dir / "original_files_mapping.jsonl"
    if mapping.exists():
        shutil.copy2(mapping, stage / "original_files_mapping.jsonl")
    return {"n": sum(by_class.values()), "bytes": total, "by_class": by_class}


def ins_manifest_segment(rows: list[dict]) -> str:
    """Manifest v6_additions insurance line — honest text for the actual
    composition (rev 1 publishes WITHOUT the +200 claims boost)."""
    n = ins_n(rows)
    if n > 0:
        subtypes = ", ".join(sorted(
            {r["expected_subclass"] for r in rows
             if r["expected"] == "insurance_claim"}))
        return (f"                   +{n} insurance_claim rows (DE-SynPUF Sample-1 "
                f"re-render via\n                   Exios66/claims-data-eda, verbatim GT "
                f"contract, existing 400\n                   record_ids excluded) — "
                f"subtypes {subtypes}.\n")
    return ("                   +0 insurance_claim rows THIS REVISION — the +200 "
            "boost is\n                   deferred to a follow-up v6 revision "
            "(claims-data-eda staging\n                   lost to tmp cleanup; card "
            "residue).\n")


def stage_sidecars(stage: Path, rows: list[dict],
                   counts: dict[tuple[str, str], int],
                   append_stats: dict, file_stats: dict) -> None:
    types = Counter(r["expected"] for r in rows)
    strata = Counter((r["expected"], r["expected_subclass"]) for r in rows)
    purpose_n = sum(1 for r in rows if (r.get("gt_fields") or {}).get("intent"))
    fb = file_stats.get("by_class", {})
    text = MANIFEST.format(
        built=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        rows=len(rows), types=dict(sorted(types.items())),
        bt=counts[("default", "train")], btest=counts[("default", "test")],
        gt=counts[("ground_truth", "train")],
        gtest=counts[("ground_truth", "test")],
        strata=len(strata), v5_base=V5_BASE_REVISION,
        corr_n=append_stats["corr_n"], pool_n=append_stats["pool_n"],
        corr_overrides=append_stats["corr_overrides"],
        ins_segment=ins_manifest_segment(rows),
        files_n=file_stats.get("n", 0),
        files_bytes_mb=file_stats.get("bytes", 0) // 1048576,
        files_contract=fb.get("contract", 0),
        files_merger=fb.get("merger_agreement", 0),
        files_corporate=fb.get("corporate_record", 0),
        files_corr=fb.get("correspondence", 0),
        files_ins=fb.get("insurance_claim", 0),
        purpose_n=purpose_n, legacy_jsonl=LEGACY_JSONL,
        stripped_n=append_stats["stripped_n"])
    (stage / "manifest.txt").write_text(text, encoding="utf-8")


def render_card(rows: list[dict], append_stats: dict, file_stats: dict) -> str:
    """Surgical evolution of the live card (fetched fresh at build time).

    Revision-idempotent: every scalar anchor tolerates BOTH the v5 card and a
    previously-published v6 rev (counts may already carry any revision's
    value), and the two KANBAN-105 sections are replaced whole when present
    (inserted only on the first v6 publish) — so revN re-renders cleanly.
    """
    corr_n = append_stats["corr_n"]
    ins_n = append_stats["ins_n"]
    r = __import__("subprocess").run(
        ["curl", "-sL", "--max-time", "60",
         f"https://huggingface.co/datasets/{REPO_ID}/raw/main/README.md"],
        capture_output=True, text=True, timeout=90)
    card = r.stdout
    assert card.startswith("---"), "could not fetch the live parent card"

    # 1) pretty_name -> v6 (v5 or a prior v6 rev)
    card, n = re.subn(r'pretty_name: "Docclass Merged Corpus v[56] \(([^)]+)\)"',
                      'pretty_name: "Docclass Merged Corpus v6 (\\1)"',
                      card, count=1)
    assert n == 1, "pretty_name anchor"
    # 2) headline counts
    card, n = re.subn(
        r"Single flat document-classification surface: \*\*[\d,]+ legal documents\*\* across\nfive corpora, one row per document \(schema v[56]\):",
        f"Single flat document-classification surface: **{len(rows):,} legal documents** across\nfive corpora, one row per document (schema v6):",
        card, count=1)
    assert n == 1, "headline anchor"
    # 3) corpus table rows (Enron 110/350 -> 350; claims 400 -> 400 + ins_n)
    card, n = re.subn(
        r"\| \*\*Enron correspondence sample\*\* \| \*\*[\d,]+\*\* \|",
        f"| **Enron correspondence sample** | **{PARENT_CORR_ROWS + corr_n}** |",
        card, count=1)
    assert n == 1, "enron row anchor"
    card, n = re.subn(
        r"\| \*\*CMS DE-SynPUF rendered EOBs\*\* \| \*\*[\d,]+\*\* \|",
        f"| **CMS DE-SynPUF rendered EOBs** | **{PARENT_INS_ROWS + ins_n}** |",
        card, count=1)
    assert n == 1, "claims row anchor"
    # 4) correspondence deep-dive heading count
    card, n = re.subn(
        r"### Enron correspondence sample — [\d,]+ rows \(`correspondence`\)",
        f"### Enron correspondence sample — {PARENT_CORR_ROWS + corr_n} rows (`correspondence`)",
        card, count=1)
    assert n == 1, "correspondence heading anchor"

    def upsert_section(card: str, heading: str, body: str,
                       insert_before: str) -> str:
        """Rev-idempotent section law: replace the section WHOLE when present
        (heading .. next '## ' heading or EOF); insert it before insert_before
        when absent. Never duplicates."""
        assert body.startswith(heading) and body.endswith("\n\n"), \
            f"section body malformed: {heading!r}"
        start = card.find(heading)
        if start >= 0:
            nxt = card.find("\n## ", start + 1)
            end = len(card) if nxt < 0 else nxt + 1
            return card[:start] + body + card[end:]
        marker_at = card.find(insert_before)
        assert marker_at >= 0, f"insert anchor missing: {insert_before!r}"
        return card[:marker_at] + body + card[marker_at:]

    # 5) v6 provenance section (replace-or-insert before the Two-config section)
    if ins_n > 0:
        insurance_bullet = (
            f"* **Insurance boost**: +{ins_n} rows ({PARENT_INS_ROWS} → {PARENT_INS_ROWS + ins_n}) — newly rendered EOBs from CMS DE-SynPUF Sample 1 via [Exios66/claims-data-eda](https://github.com/Exios66/claims-data-eda) with the verbatim GT contract asserted at render time; every existing record_id was excluded, so the original {PARENT_INS_ROWS} claims are untouched. Subtypes: {append_stats['ins_types']}. Same synthetic-data caveats as v5 (PAID claims only, `adjuster` null, health LOB).")
    else:
        insurance_bullet = (
            "* **Insurance boost**: DEFERRED to a follow-up v6 revision — the +200-row claims-data-eda re-render was interrupted (staging lost to a tmp cleanup) and is being rebuilt; this revision publishes the correspondence rebalance + original files without touching the 400 existing claims.")
    v6_section = f"""## Schema v6 additions (KANBAN-105, 2026-08-30)

* **Correspondence rebalance**: +{corr_n} rows ({PARENT_CORR_ROWS} → {PARENT_CORR_ROWS + corr_n}) — deterministic `sha256(filename)` stratified draw from [`enron-correspondence-dedup`](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup) after excluding every existing filename; the shared Enron labelers (subclass / content-topic / sentiment) were RE-RUN on every drawn row as a verification pass and reproduce the Hub ground truth exactly; the KANBAN-103 phrase-lexicon GT overrides are honored. The dedup corpus carries no `attorney_demand` rows beyond the 3 already present (all in the v4 sample) — honest gap, not an omission.
{insurance_bullet}
* **Blind-surface repair**: the `default` (blind) config no longer carries the label equivalents `expected_doc_type` / `expected_subclass` inside `metadata` (a v4-era flat-dump artifact v5 shipped verbatim) — it now honors the card's "NO label columns" contract; labels live ONLY in the `ground_truth` config ({append_stats['stripped_n']} rows repaired).
* **Purpose/gist GT**: the ground_truth config now carries `intent` / `subject_matter` / `keywords` columns on BOTH splits (train rows labeled by the llm-mailroom purpose-GT push of 2026-08-30; new append rows are empty until the incremental labeler pass fills them in a follow-up revision — then every corporate_record / correspondence / insurance_claim row is gradable against the controlled `INTENT_LABELS` vocabularies).
* **Class balance after v6**: contract {sum(1 for r in rows if r['expected'] == 'contract')} ({sum(1 for r in rows if r['expected'] == 'contract') / len(rows):.1%}), insurance_claim {sum(1 for r in rows if r['expected'] == 'insurance_claim')} ({sum(1 for r in rows if r['expected'] == 'insurance_claim') / len(rows):.1%}), correspondence {sum(1 for r in rows if r['expected'] == 'correspondence')} ({sum(1 for r in rows if r['expected'] == 'correspondence') / len(rows):.1%}), merger_agreement {sum(1 for r in rows if r['expected'] == 'merger_agreement')}, corporate_record {sum(1 for r in rows if r['expected'] == 'corporate_record')}.

"""
    card = upsert_section(card, "## Schema v6 additions (KANBAN-105, 2026-08-30)",
                          v6_section, "## ⚠️ Two-config layout")
    # 6) original-files section (replace-or-insert before the v6 section)
    files_section = f"""## Original files (KANBAN-105 addendum, 2026-08-30)

The originals for ALL five classes ride along under `files/` — a
file-complete corpus for easy access (`metadata.original_file` carries the
Hub-relative path on EVERY row):

| doc_type | files | form | source |
|---|---|---|---|
| `contract` | {file_stats.get('by_class', {}).get('contract', 0)} | source PDFs (`metadata.pdf_path` layout) | [theatticusproject/cuad](https://huggingface.co/datasets/theatticusproject/cuad) (CC BY 4.0) |
| `merger_agreement` | {file_stats.get('by_class', {}).get('merger_agreement', 0)} | upstream `contract_N.txt` (MAUD ships no PDFs) | Zenodo [7500064](https://zenodo.org/records/7500064) (CC BY 4.0) |
| `corporate_record` | {file_stats.get('by_class', {}).get('corporate_record', 0)} | EDGAR exhibit originals (.htm) | SEC EDGAR via `metadata.exhibit_url` (public domain) |
| `correspondence` | {file_stats.get('by_class', {}).get('correspondence', 0)} | CMU maildir raw RFC822 messages (full headers — `doc_text` is the composed Subject+body) | [Enron-Evaluation-Environment](https://github.com/Exios66/Enron-Evaluation-Environment) `acquire_enron.py` (CMU `enron_mail_20150507`) |
| `insurance_claim` | {file_stats.get('by_class', {}).get('insurance_claim', 0)} | rendered EOB documents (.txt — the render IS the original) | [claims-data-eda](https://github.com/Exios66/claims-data-eda) `render_eob` |

Fetch one: `hf_hub_download("Lucius-Morningstar/docclass-merged",
"files/contract/Part_I/License_Agreements/<file>.pdf", repo_type="dataset")`.
Per-file sha256 + sizes: `original_files_mapping.jsonl` sidecar.

"""
    card = upsert_section(card, "## Original files (KANBAN-105 addendum, 2026-08-30)",
                          files_section,
                          "## Schema v6 additions (KANBAN-105, 2026-08-30)")
    return card


def publish(stage: Path, commit_message: str) -> None:
    import os

    from huggingface_hub import HfApi, constants as hf_constants

    # hub 1.x hardcodes a 10s httpx READ timeout (no env override) — large
    # multi-file PUTs to the CDN regularly exceed it. Patch the module
    # constant before any client construction (runtime-only, this process).
    hf_constants.DEFAULT_REQUEST_TIMEOUT = 600.0
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    api.create_repo(repo_id=REPO_ID, repo_type="dataset", exist_ok=True)
    api.upload_folder(folder_path=str(stage), repo_id=REPO_ID,
                      repo_type="dataset",
                      commit_message=commit_message)
    print(f"Published -> https://huggingface.co/datasets/{REPO_ID}")


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v6", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--pool-n", type=int, default=247413)
    parser.add_argument("--corr-overrides", type=int, default=0)
    parser.add_argument("--files-dir", type=Path, default=None,
                        help="staging root from attach_original_files.py "
                             "(files/ tree + original_files_mapping.jsonl)")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)

    rows = load_v6(args.v6)
    stripped_n = strip_blind_labels(rows)
    # FILE-COMPLETE CORPUS (KANBAN-105 human directive): every row must carry
    # its original file — all five classes stage under files/
    missing_files = [r["filename"] for r in rows
                     if not (r.get("metadata") or {}).get("original_file")]
    assert not missing_files, (
        f"{len(missing_files)} rows lack metadata.original_file — the corpus "
        f"must be file-complete, e.g. {missing_files[:3]}")
    print(f"Loaded {len(rows)} v6 rows")
    ins_types = ", ".join(
        sorted(k for k, n in Counter(r["expected_subclass"] for r in rows
                                     if r["expected"] == "insurance_claim").items()))
    append_stats = {"corr_n": corr_n(rows), "pool_n": args.pool_n,
                    "corr_overrides": args.corr_overrides,
                    "ins_n": ins_n(rows), "ins_types": ins_types,
                    "stripped_n": stripped_n}
    print(f"composition: parent {PARENT_ROWS} + corr {append_stats['corr_n']} "
          f"+ ins {append_stats['ins_n']}")

    if args.stage.exists():
        shutil.rmtree(args.stage)
    args.stage.mkdir(parents=True)
    counts = stage_parquet(args.stage, rows)
    file_stats = (stage_original_files(args.stage, args.files_dir)
                  if args.files_dir else {"n": 0, "bytes": 0, "by_class": {}})
    (args.stage / "README.md").write_text(
        render_card(rows, append_stats, file_stats), encoding="utf-8")
    stage_sidecars(args.stage, rows, counts, append_stats, file_stats)
    print("Staged:", {f"{a}/{b}": n for (a, b), n in sorted(counts.items())})
    print(f"Original files staged: {file_stats['n']} "
          f"({file_stats['bytes'] // 1048576} MB) {file_stats['by_class']}")

    if args.publish:
        revision = (f"rev2 (+{append_stats['ins_n']} insurance)" if ins_n(rows)
                    else "rev1 (correspondence + original files)")
        publish(args.stage,
                f"KANBAN-105: schema v6 {revision} — {len(rows)} rows, "
                f"{file_stats['n']} upstream originals, purpose-gist GT columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_with_args(sys.argv[1:]))
