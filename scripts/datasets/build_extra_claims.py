#!/usr/bin/env python3
"""Build the KANBAN-105 insurance append for docclass-merged v6.

Re-renders NEW ``insurance_claim`` EOB documents from the CMS DE-SynPUF
Sample-1 corpus (via the ``claims-data-eda`` pipeline) and emits ``--take``
rows not already present in the parent corpus — the insurance-class boost
(400 v5 rows -> 600 in v6) with the verbatim GT contract intact.

Pipeline (stages are resumable; each prints its own census):

1. ``acquire``  — the 8 DE-SynPUF ZIPs downloaded with the claims repo's own
   ``acquire_synpuf.download`` (sha-manifested; CMS + Wayback sources).
   NOTE: the claims repo's ``extract()`` step is deliberately NOT run —
   extracted CSVs (~8 GB) exceed this machine's free disk. See ``index``.
2. ``index``    — stream the CSV members DIRECTLY out of the ZIPs
   (``zipfile`` in-memory decompression; no CSV ever touches disk) through
   the claims repo's own normalizers — ``build_corpus_index.claim_event`` /
   ``carrier_claim_event`` / ``pde_event`` — appending to
   ``data/cms/index.jsonl.gz``; the three beneficiary summaries merge into
   ``data/cms/beneficiaries.jsonl.gz``. Row semantics are byte-identical to
   ``build_corpus_index.py``; only the file source is a zip member stream.
3. ``sample``   — run the claims repo's ``build_pipeline_dump.py`` verbatim in
   a subprocess under ``PYTHONHASHSEED=0`` (its stratum seeding uses
   ``hash(key)``, which is process-randomized otherwise — pinning the env
   makes the draw deterministic and rebuild-stable) with ``--n``/``--seed``.
4. ``filter``   — drop every row whose ``record_id`` is already in the parent
   (v5) corpus, then take the first ``--take`` new rows in the file's
   deterministic selection order. The original 400 v5 claims stay untouched.
5. ``verify``   — re-assert the verbatim GT contract per emitted row (every
   scalar GT value occurs literally in ``doc_text``; ``render_eob.render``
   already asserts at build time — this is the belt-and-braces pass).

Usage:
    python scripts/datasets/build_extra_claims.py --dry-run ...
    python scripts/datasets/build_extra_claims.py --skip-acquire ...
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path

# KANBAN-088: shared JSONL line-boundary safety (Hub worker splits rows on
# U+2028/U+2029/NEL; see scripts/datasets/_jsonl_safety.py).
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from scripts.datasets._jsonl_safety import safe_jsonl_line  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path("data/datasets/insurance_append_v6.jsonl")

BENE_ZIPS = [
    "DE1_0_2008_Beneficiary_Summary_File_Sample_1.zip",
    "DE1_0_2009_Beneficiary_Summary_File_Sample_1.zip",
    "DE1_0_2010_Beneficiary_Summary_File_Sample_1.zip",
]
CLAIM_ZIPS = [
    ("inpatient", "DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.zip"),
    ("outpatient", "DE1_0_2008_to_2010_Outpatient_Claims_Sample_1.zip"),
    ("carrier", "DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.zip"),
    ("carrier", "DE1_0_2008_to_2010_Carrier_Claims_Sample_1B.zip"),
    ("pde", "DE1_0_2008_to_2010_Prescription_Drug_Events_Sample_1.zip"),
]

# beneficiary merge field lists — mirrors build_corpus_index.build_beneficiaries
CC_KEYS = [
    "ALZHDMTA", "CHF", "CHRNKIDN", "CNCR", "COPD", "DEPRESSN",
    "DIABETES", "ISCHMCHT", "OSTEOPRS", "RA_OA", "STRKETIA",
]
STATIC_FIELDS = ["BENE_SEX_IDENT_CD", "BENE_RACE_CD", "BENE_ESRD_IND",
                 "SP_STATE_CODE", "BENE_COUNTY_CD"]
YEARLY_MONEY = ["MEDREIMB_IP", "BENRES_IP", "PPPYMT_IP", "MEDREIMB_OP",
                "BENRES_OP", "PPPYMT_OP", "MEDREIMB_CAR", "BENRES_CAR",
                "PPPYMT_CAR"]
YEARS = [2008, 2009, 2010]


def zip_csv_rows(zip_path: Path, suffix: str = ".csv"):
    """Stream dict rows from the first .csv member of a zip (no extraction)."""
    with zipfile.ZipFile(zip_path) as zf:
        member = next(n for n in zf.namelist()
                      if n.lower().endswith(suffix) and not n.endswith("/"))
        with zf.open(member) as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            for row in reader:
                yield {k.strip('"'): (v or "").strip() for k, v in row.items()}


def stage_acquire(claims_repo: Path) -> None:
    """Download the 8 ZIPs with the claims repo's own acquirer (no extract)."""
    sys.path.insert(0, str(claims_repo / "scripts"))
    import acquire_synpuf  # noqa: E402  (claims-data-eda scripts/, imported)

    # KANBAN-105 documented deviation: the claims repo pins the two carrier
    # ZIPs (and the PDE first candidate) to Wayback timestamps, but Wayback is
    # unreachable from this machine (session-verified twice). The CMS CDN
    # serves the identical archives (probe HTTP 200; the acquirer zip-tests
    # every download before accepting it) — appended as LAST-RESORT candidates
    # so the claims repo's own priority order still wins whenever it can.
    extra_urls = {
        "DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.zip":
            [f"http://downloads.cms.gov/files/"
             f"DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.zip"],
        "DE1_0_2008_to_2010_Carrier_Claims_Sample_1B.zip":
            [f"http://downloads.cms.gov/files/"
             f"DE1_0_2008_to_2010_Carrier_Claims_Sample_1B.zip"],
    }

    raw = claims_repo / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for name, urls in acquire_synpuf.FILES.items():
        dest = raw / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  [skip] {name}")
            continue
        print(f"  [get ] {name}", flush=True)
        try:
            acquire_synpuf.download(list(urls) + extra_urls.get(name, []), dest)
        except Exception as exc:  # noqa: BLE001 - a dead source must not kill
            # the run: the 2010 bene summary (Wayback-only) degrades to the
            # documented nearest-year fallback; claim ZIPs have no fallback
            print(f"  !! FAILED {name}: {exc}", flush=True)
            failed.append(name)
    if failed:
        print(f"  acquire failures (tolerated): {failed}", flush=True)


def _iso_date(raw):
    s = str(raw or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s or None


def _to_float(raw):
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(raw):
    v = _to_float(raw)
    return int(v) if v is not None else None


def _compact(obj):
    if isinstance(obj, dict):
        return {k: _compact(v) for k, v in obj.items()
                if v is not None and v != [] and v != {} and v != ""}
    if isinstance(obj, list):
        return [_compact(v) for v in obj]
    return obj


def stage_index(claims_repo: Path) -> None:
    """Stream-index beneficiaries + claim events straight from the ZIPs."""
    sys.path.insert(0, str(claims_repo / "scripts"))
    from build_corpus_index import (  # noqa: E402
        carrier_claim_event, claim_event, jopen, pde_event,
    )

    raw = claims_repo / "data" / "raw"
    cms = claims_repo / "data" / "cms"
    cms.mkdir(parents=True, exist_ok=True)

    bene_path = cms / "beneficiaries.jsonl.gz"
    if bene_path.exists():
        print("  [skip] beneficiaries.jsonl.gz exists")
    else:
        bene: dict[str, dict] = {}
        for year, zname in zip(YEARS, BENE_ZIPS):
            if not (raw / zname).exists():
                # documented deviation (KANBAN-105): a missing yearly bene file
                # degrades only demographics (join_beneficiary falls back to the
                # nearest year) — GT integrity is unaffected (no bene-derived GT)
                print(f"  !! {zname} missing — bene year {year} skipped "
                      f"(nearest-year fallback applies at render)", flush=True)
                continue
            n = 0
            for row in zip_csv_rows(raw / zname):
                bid = row["DESYNPUF_ID"]
                rec = bene.setdefault(bid, {
                    "bene_id": bid,
                    "birth_dt": _iso_date(row.get("BENE_BIRTH_DT")),
                    "death_dt": _iso_date(row.get("BENE_DEATH_DT")),
                    **{f.lower(): row.get(f) for f in STATIC_FIELDS},
                    "years": {},
                })
                dd = _iso_date(row.get("BENE_DEATH_DT"))
                if dd and not rec["death_dt"]:
                    rec["death_dt"] = dd
                rec["years"][year] = {
                    "cc": {k: _to_int(row.get(f"SP_{k}")) for k in CC_KEYS},
                    "money": {m: _to_float(row.get(m)) for m in YEARLY_MONEY},
                    "hi_mons": _to_int(row.get("BENE_HI_CVRAGE_TOT_MONS")),
                    "smi_mons": _to_int(row.get("BENE_SMI_CVRAGE_TOT_MONS")),
                    "hmo_mons": _to_int(row.get("BENE_HMO_CVRAGE_TOT_MONS")),
                    "plan_mos": _to_int(row.get("PLAN_CVRG_MOS_NUM")),
                }
                n += 1
            print(f"  bene {year}: {n:,} rows", flush=True)
        with jopen(bene_path, "wt") as fh:
            for bid in sorted(bene):
                fh.write(json.dumps(_compact(bene[bid]), sort_keys=True) + "\n")
        print(f"  wrote {len(bene):,} beneficiaries -> {bene_path}", flush=True)
        del bene

    index_path = cms / "index.jsonl.gz"
    state_path = cms / "kanban105_index_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    total = int(state.get("total", 0))
    with jopen(index_path, "at") as out:
        for label, zname in CLAIM_ZIPS:
            if state.get(zname):
                print(f"  [skip] {zname} indexed ({state[zname]:,} events)")
                continue
            if not (raw / zname).exists():
                # documented deviation (KANBAN-105): a missing claim ZIP (its
                # sources unreachable) drops only that event family — the
                # sampled claims shift to the reachable families; the verbatim
                # GT contract and the exclusion law are unaffected
                print(f"  !! {zname} missing — {label} events skipped "
                      f"(documented source outage)", flush=True)
                continue
            fn = {"inpatient": claim_event, "outpatient": claim_event}.get(label)
            n = 0
            for row in zip_csv_rows(raw / zname):
                ev = (fn(row, label, zname) if fn
                      else carrier_claim_event(row, zname) if label == "carrier"
                      else pde_event(row, zname))
                out.write(json.dumps(_compact(ev), sort_keys=True) + "\n")
                n += 1
            total += n
            state[zname] = n
            state["total"] = total
            state_path.write_text(json.dumps(state, indent=1))
            print(f"  {label}: {n:,} events from {zname}", flush=True)
    print(f"  index total: {total:,} claim events -> {index_path}")


def stage_sample(claims_repo: Path, n_total: int, seed: int) -> Path:
    """Run the claims repo's own stratified sampler under a pinned hash seed."""
    out = claims_repo / "data" / "cms" / "pipeline.jsonl"
    if out.exists():
        print(f"  [skip] {out.name} exists ({out.stat().st_size:,} bytes)")
        return out
    env = dict(os.environ, PYTHONHASHSEED="0")
    cmd = [sys.executable, "scripts/build_pipeline_dump.py",
           "--n", str(n_total), "--seed", str(seed)]
    print(f"  $ PYTHONHASHSEED=0 {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=claims_repo, env=env, check=True)
    return out


def existing_claim_ids(parent_gt_dir: Path) -> set[str]:
    """record_ids (filename minus .txt) of the parent corpus insurance rows."""
    import pyarrow.parquet as pq

    ids: set[str] = set()
    for shard in sorted(parent_gt_dir.glob("**/*.parquet")):
        table = pq.read_table(shard, columns=["filename", "expected"])
        for fn, exp in zip(table.column("filename").to_pylist(),
                           table.column("expected").to_pylist()):
            if str(exp) == "insurance_claim":
                ids.add(str(fn).removesuffix(".txt"))
    return ids


def verify_verbatim(row: dict) -> None:
    """Belt-and-braces re-assertion of the verbatim GT contract."""
    doc = row["doc_text"]
    gt = row["metadata"]["ground_truth"]
    for key in ("claim_number", "policy_number", "insurer", "insured_party",
                "claim_type"):
        assert str(gt[key]) in doc, f"verbatim contract violated for {key}"
    if gt["claimed_amount"] is not None:
        assert f"${gt['claimed_amount']:,.2f}" in doc, \
            "verbatim contract violated for claimed_amount"
    for d in (gt["date_of_loss"], gt["date_filed"]):
        if d:
            assert d in doc, f"verbatim contract violated for date {d}"


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-repo", type=Path,
                        default=Path.home() / "claims-data-eda",
                        help="claims-data-eda clone (scripts/ + data/ staging)")
    parser.add_argument("--parent-gt-dir", type=Path, required=True,
                        help="dir holding the docclass-merged v5 ground_truth "
                             "parquet shards (train/test)")
    parser.add_argument("--n-total", type=int, default=800,
                        help="sample size for the claims repo's draw (buffer "
                             "over --take; existing ids are excluded after)")
    parser.add_argument("--take", type=int, default=200, help="new rows to emit")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skip-acquire", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument("--skip-sample", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(args.claims_repo / "scripts"))

    if not args.skip_acquire:
        print("[1/4] acquire ...", flush=True)
        stage_acquire(args.claims_repo)
    if not args.skip_index:
        print("[2/4] index (zip-streamed) ...", flush=True)
        stage_index(args.claims_repo)
    if not args.skip_sample:
        print("[3/4] sample ...", flush=True)
        stage_sample(args.claims_repo, args.n_total, args.seed)

    print("[4/4] filter + emit ...", flush=True)
    existing = existing_claim_ids(args.parent_gt_dir)
    print(f"  parent insurance record_ids (exclusion set): {len(existing):,}")
    sample_path = args.claims_repo / "data" / "cms" / "pipeline.jsonl"
    # the claims repo's sampler already joins beneficiaries and renders each
    # event through render_eob.pipeline_row — these rows ARE the final shape
    all_rows = [json.loads(line) for line in
                sample_path.open(encoding="utf-8") if line.strip()]
    new_rows = [r for r in all_rows
                if str(r["metadata"]["record_id"]) not in existing]
    print(f"  sample {len(all_rows):,} rows -> {len(new_rows):,} new after exclusion")
    if len(new_rows) < args.take:
        parser.error(f"only {len(new_rows)} new rows available < --take "
                     f"{args.take} — raise --n-total")
    # subtype-balanced selection: the sampler's output is grouped by claim
    # type, so a first-N slice would take ONE family (measured: 200/200
    # carrier). The v5 parent is family-parity (100/100/100/100) — the +200
    # boost must round-robin across the subtypes (50/50/50/50) to preserve it.
    by_type: dict[str, list[dict]] = {}
    for r in new_rows:
        by_type.setdefault(r["expected_subclass"], []).append(r)
    subtypes = sorted(by_type)
    quota, extra = divmod(args.take, len(subtypes))
    balanced: list[dict] = []
    for i, sub in enumerate(subtypes):
        take = quota + (1 if i < extra else 0)
        balanced.extend(by_type[sub][:take])
    new_rows = balanced[:args.take]

    emitted = []
    type_counts: Counter = Counter()
    from scripts.datasets.build_docclass_merged import assign_split

    for row in new_rows:
        verify_verbatim(row)
        type_counts[row["expected_subclass"]] += 1
        # the claims dump carries no split — assert the family law at emit
        row["split"] = assign_split(str(row["filename"]))
        emitted.append(row)

    print(f"  emitted distribution: {dict(sorted(type_counts.items()))}")
    for t, n in type_counts.items():
        if n < 40:
            print(f"  WARNING: subtype {t} contributed only {n} rows "
                  f"(< 40) — check the exclusion overlap")
    if args.dry_run:
        print(f"\nDry run: would write {len(emitted)} rows -> {args.out}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in emitted:
            fh.write(safe_jsonl_line(row) + "\n")
    print(f"\nWrote {len(emitted)} rows -> {args.out}")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
