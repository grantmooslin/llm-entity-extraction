#!/usr/bin/env python3
"""Stage the ORIGINAL FILES for docclass-merged v6 (KANBAN-105 addendum).

The human directive (2026-08-30, extended in-session): EVERY document class
rides along in the docclass-merged ``files/`` tree — the text content already
carries the intent, but the corpus is file-complete for easy access.

Per-corpus originals (all five classes):

* ``contract``          — the 509 CUAD source PDFs. ``metadata.pdf_path``
  (``CUAD_v1/full_contract_pdf/<Part>/<Category>/<file>.pdf``) resolves under
  ``--cuad-dir`` (populated by ``scripts/datasets/download_cuad_pdfs.py``
  against ``theatticusproject/cuad``). Hub path:
  ``files/contract/<Part>/<Category>/<file>.pdf``.
* ``merger_agreement``  — the 152 MAUD upstream contracts. ``metadata.contract``
  (``contract_N``) resolves inside ``--maud-zip`` (Zenodo ``maud_v1.zip`` →
  ``data/contracts/contract_N.txt``; the upstream artifacts are plain-text
  contract files, not PDFs — MAUD ships no PDFs). Hub path:
  ``files/merger_agreement/contract_N.txt``.
* ``corporate_record``  — the 39 S-1 EDGAR exhibit originals.
  ``metadata.exhibit_url`` (``/Archives/edgar/data/...``) fetches from
  ``https://www.sec.gov`` with the house SEC-compliant identifying UA and a
  fair-access throttle (mirrors ``stream_s1_exhibits.py``). Hub path:
  ``files/corporate_record/<accession>/<basename>``.
* ``correspondence``    — the CMU maildir originals (raw RFC822 message files,
  fetched by ``~/Enron-Evaluation-Environment/scripts/acquire_enron.py`` —
  the human-named source repo for this corpus). The row filename IS the
  maildir path (``<custodian>/<folder>/<msg>.``); ``doc_text`` is the composed
  Subject+body, so the original carries the full headers. Hub path:
  ``files/correspondence/<custodian>/<folder>/<msg>.``.
* ``insurance_claim``   — the rendered EOB documents from
  ``Exios66/claims-data-eda`` (the render IS the original): each row's
  ``doc_text`` is the render output, staged verbatim. Hub path:
  ``files/insurance_claim/<record_id>.txt``.

Outputs (staging):
    <files-dir>/files/...           the original files, Hub-relative layout
    <files-dir>/original_files_mapping.jsonl
        {filename, original_file, original_file_sha256, original_file_bytes}
        — consumed by ``build_docclass_v6.py`` (cast-safe ``original_file``
        metadata column) and ``publish_docclass_v6.py`` (files tree upload).

Usage:
    python scripts/datasets/attach_original_files.py --dry-run ...
    python scripts/datasets/attach_original_files.py ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

# KANBAN-088: shared JSONL line-boundary safety (Hub worker splits rows on
# U+2028/U+2029/NEL; see scripts/datasets/_jsonl_safety.py).
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from scripts.datasets._jsonl_safety import safe_jsonl_line  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILES_DIR = Path("data/datasets/v6_original_files")
CUAD_PATH_PREFIX = "CUAD_v1/full_contract_pdf/"
EDGAR_ARCHIVE = "https://www.sec.gov"
EDGAR_UA = "llm-entity-extraction research contact@example.com"  # SEC-compliant plain form
EDGAR_THROTTLE_S = 0.5
DEFAULT_ENRON_DIR = Path.home() / "Enron-Evaluation-Environment"
DEFAULT_CORR_APPEND = Path("data/datasets/correspondence_append_v6.jsonl")
DEFAULT_INS_APPEND = Path("data/datasets/insurance_append_v6.jsonl")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_parent_rows(parent_blind_dir: Path, parent_gt_dir: Path) -> list[dict]:
    """(filename, expected, pdf_path/contract/exhibit_url, doc_text) per row.

    The blind config carries the provenance metadata + doc_text; ``expected``
    lives in the ground_truth config — join the two on filename (1:1 by
    family law).
    """
    import pyarrow.parquet as pq

    meta: dict[str, dict] = {}
    texts: dict[str, str] = {}
    for shard in sorted(parent_blind_dir.glob("**/*.parquet")):
        table = pq.read_table(shard)
        names = table.column("filename").to_pylist()
        for i, fn in enumerate(names):
            md = table.column("metadata")[i].as_py() or {}
            fn = str(fn)
            meta[fn] = md
            texts[fn] = str(table.column("doc_text")[i].as_py() or "")
    rows = []
    for shard in sorted(parent_gt_dir.glob("**/*.parquet")):
        table = pq.read_table(shard, columns=["filename", "expected"])
        for i in range(table.num_rows):
            fn = str(table.column("filename")[i].as_py())
            md = meta.get(fn) or {}
            rows.append({
                "filename": fn,
                "expected": str(table.column("expected")[i].as_py()),
                "doc_text": texts.get(fn, ""),
                "pdf_path": str(md.get("pdf_path") or ""),
                "contract": str(md.get("contract") or ""),
                "exhibit_url": str(md.get("exhibit_url") or ""),
                "accession": str(md.get("accession") or ""),
            })
    return rows


def stage_contract(row: dict, cuad_dir: Path, files_dir: Path) -> str | None:
    """CUAD source PDF -> files/contract/<Part>/<Category>/<file>.pdf.

    Resolves both layouts: ``download_cuad_pdfs.py`` strips the
    ``CUAD_v1/full_contract_pdf/`` tree root locally (mirror layout), while
    the full repo-relative layout is accepted for robustness. Resumable: an
    already-staged dest short-circuits (the /tmp source tree may be gone).
    """
    pdf_path = row["pdf_path"]
    if not pdf_path.startswith(CUAD_PATH_PREFIX):
        return None
    stem = pdf_path[len(CUAD_PATH_PREFIX):]
    rel = f"files/contract/{stem}"
    dest = files_dir / rel
    if dest.exists() and dest.stat().st_size > 0:
        return rel
    for candidate in (cuad_dir / stem, cuad_dir / pdf_path):
        if candidate.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(candidate, dest)
            return rel
    return None


def stage_merger(row: dict, maud_zip: Path, files_dir: Path) -> str | None:
    """MAUD upstream contract -> files/merger_agreement/contract_N.txt."""
    contract = row["contract"]
    if not contract.startswith("contract_"):
        return None
    member = f"data/contracts/{contract}.txt"
    rel = f"files/merger_agreement/{contract}.txt"
    dest = files_dir / rel
    if dest.exists():
        return rel
    with zipfile.ZipFile(maund_guard(maud_zip)) as zf:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(member))
        except KeyError:
            return None
    return rel


def maund_guard(maud_zip: Path) -> Path:
    if not maud_zip.exists():
        raise SystemExit(f"maud zip not found: {maud_zip} (Zenodo 7500064)")
    return maud_zip


def stage_corporate(row: dict, files_dir: Path) -> tuple[str | None, int]:
    """EDGAR exhibit original -> files/corporate_record/<accession>/<name>."""
    exhibit_url = row["exhibit_url"]
    if not exhibit_url.startswith("/Archives/"):
        return None, 0
    basename = exhibit_url.rsplit("/", 1)[-1]
    accession_dir = row["accession"] or "unknown"
    rel = f"files/corporate_record/{accession_dir}/{basename}"
    dest = files_dir / rel
    if dest.exists() and dest.stat().st_size > 0:
        return rel, 0
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        f"{EDGAR_ARCHIVE}{exhibit_url}",
        headers={"User-Agent": EDGAR_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())
    time.sleep(EDGAR_THROTTLE_S)  # SEC fair-access throttle
    return rel, 1


def stage_correspondence(row: dict, maildir: Path, files_dir: Path) -> str | None:
    """CMU maildir original -> files/correspondence/<custodian>/<folder>/<msg>.

    The row filename IS the maildir-relative path (``<custodian>/<folder>/<msg>.``);
    the raw RFC822 message carries the full headers (doc_text is only the
    composed Subject+body).
    """
    fn = row["filename"]
    src = maildir / fn
    if not src.is_file():
        return None
    rel = f"files/correspondence/{fn}"
    dest = files_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(src, dest)
    return rel


def stage_insurance(row: dict, files_dir: Path) -> str:
    """Rendered EOB document -> files/insurance_claim/<record_id>.txt.

    The render IS the original (claims-data-eda ``render_eob``): the row's
    ``doc_text`` is the render output, staged verbatim.
    """
    fn = row["filename"]
    rel = f"files/insurance_claim/{fn}"
    dest = files_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(row["doc_text"], encoding="utf-8")
    return rel


def read_append_rows(path: Path, expected_class: str) -> list[dict]:
    """Append-staging rows (filename, doc_text) for the two staged classes."""
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            assert r.get("expected") == expected_class, \
                f"{path}: expected {expected_class}, got {r.get('expected')!r}"
            rows.append(r)
    return rows


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-blind-dir", type=Path, required=True,
                        help="dir with the v5 default config parquet shards")
    parser.add_argument("--parent-gt-dir", type=Path, required=True,
                        help="dir with the v5 ground_truth parquet shards")
    parser.add_argument("--cuad-dir", type=Path,
                        default=Path("/tmp/opencode/cuad_pdfs"),
                        help="CUAD PDF tree (download_cuad_pdfs.py output)")
    parser.add_argument("--maud-zip", type=Path,
                        default=Path("/tmp/opencode/maud_v1.zip"))
    parser.add_argument("--enron-dir", type=Path, default=DEFAULT_ENRON_DIR,
                        help="Enron-Evaluation-Environment root (its "
                             "data/raw/maildir holds the CMU originals)")
    parser.add_argument("--correspondence-append", type=Path,
                        default=DEFAULT_CORR_APPEND,
                        help="correspondence append staging JSONL (new rows "
                             "beyond the parent)")
    parser.add_argument("--insurance-append", type=Path,
                        default=DEFAULT_INS_APPEND,
                        help="insurance append staging JSONL (new rows "
                             "beyond the parent)")
    parser.add_argument("--files-dir", type=Path, default=DEFAULT_FILES_DIR,
                        help="staging root for files/ + the mapping JSONL")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve all paths without copying/fetching")
    args = parser.parse_args(argv)

    files_dir: Path = args.files_dir
    rows = load_parent_rows(args.parent_blind_dir, args.parent_gt_dir)
    by_class: dict[str, list[dict]] = {}
    for r in rows:
        by_class.setdefault(r["expected"], []).append(r)
    print(f"parent rows: {len(rows)} "
          f"({ {k: len(v) for k, v in sorted(by_class.items())} })")

    mapping = []
    stats: dict[str, dict[str, int]] = {}
    seen_rel: set[str] = set()

    for doc_type, resolver in (("contract", "cuad"), ("merger_agreement", "maud")):
        n_ok = n_miss = 0
        for row in by_class.get(doc_type, []):
            if resolver == "cuad":
                rel = (None if args.dry_run else stage_contract(
                    row, args.cuad_dir, files_dir))
                if args.dry_run:
                    rel = (f"files/contract/{row['pdf_path'][len(CUAD_PATH_PREFIX):]}"
                           if row["pdf_path"].startswith(CUAD_PATH_PREFIX) else None)
            else:
                rel = (None if args.dry_run else stage_merger(
                    row, args.maud_zip, files_dir))
                if args.dry_run:
                    rel = (f"files/merger_agreement/{row['contract']}.txt"
                           if row["contract"].startswith("contract_") else None)
            if rel is None:
                n_miss += 1
                continue
            assert rel not in seen_rel, f"collision: {rel}"
            seen_rel.add(rel)
            mapping.append({"filename": row["filename"], "original_file": rel})
            n_ok += 1
        stats[doc_type] = {"attached": n_ok, "missing": n_miss}
        print(f"  {doc_type}: {n_ok} attached / {n_miss} missing")

    n_fetch = 0
    n_ok = n_miss = 0
    for row in by_class.get("corporate_record", []):
        if args.dry_run:
            ok = row["exhibit_url"].startswith("/Archives/")
            rel = (f"files/corporate_record/{row['accession'] or 'unknown'}/"
                   f"{row['exhibit_url'].rsplit('/', 1)[-1]}" if ok else None)
        else:
            rel, fetched = stage_corporate(row, files_dir)
            n_fetch += fetched
        if rel is None:
            n_miss += 1
            continue
        assert rel not in seen_rel, f"collision: {rel}"
        seen_rel.add(rel)
        mapping.append({"filename": row["filename"], "original_file": rel})
        n_ok += 1
    stats["corporate_record"] = {"attached": n_ok, "missing": n_miss,
                                 "fetched": n_fetch}
    print(f"  corporate_record: {n_ok} attached / {n_miss} missing "
          f"({n_fetch} fetched from EDGAR)")

    # correspondence — CMU maildir originals (Enron-Evaluation-Environment)
    maildir = args.enron_dir / "data" / "raw" / "maildir"
    n_ok = n_miss = 0
    corr_rows = by_class.get("correspondence", []) + read_append_rows(
        args.correspondence_append, "correspondence")
    for row in corr_rows:
        if args.dry_run:
            rel = f"files/correspondence/{row['filename']}"
        else:
            rel = stage_correspondence(row, maildir, files_dir)
        if rel is None:
            n_miss += 1
            continue
        assert rel not in seen_rel, f"collision: {rel}"
        seen_rel.add(rel)
        mapping.append({"filename": row["filename"], "original_file": rel})
        n_ok += 1
    stats["correspondence"] = {"attached": n_ok, "missing": n_miss}
    print(f"  correspondence: {n_ok} attached / {n_miss} missing "
          f"(CMU maildir originals under {maildir})")

    # insurance_claim — rendered EOB documents (claims-data-eda; the render
    # IS the original): parent rows from the blind parquet doc_text, append
    # rows from the claims pipeline staging JSONL
    n_ok = n_miss = 0
    ins_rows = by_class.get("insurance_claim", []) + read_append_rows(
        args.insurance_append, "insurance_claim")
    for row in ins_rows:
        rel = (f"files/insurance_claim/{row['filename']}"
               if args.dry_run or (row.get("doc_text") or "").strip()
               else None)
        if rel is None:
            n_miss += 1
            continue
        assert rel not in seen_rel, f"collision: {rel}"
        seen_rel.add(rel)
        mapping.append({"filename": row["filename"], "original_file": rel})
        if not args.dry_run:
            stage_insurance(row, files_dir)
        n_ok += 1
    stats["insurance_claim"] = {"attached": n_ok, "missing": n_miss}
    print(f"  insurance_claim: {n_ok} attached / {n_miss} missing "
          f"(rendered EOB documents)")

    # hash the staged files (skip on dry-run)
    if not args.dry_run:
        for m in mapping:
            path = files_dir / m["original_file"]
            m["original_file_sha256"] = sha256_file(path)
            m["original_file_bytes"] = path.stat().st_size

    total = sum(s["attached"] for s in stats.values())
    print(f"original files resolved: {total} "
          f"({ {k: s['attached'] for k, s in sorted(stats.items())} }) — "
          f"file-complete corpus (every row carries its original)")
    if n_miss or any(s.get("missing") for s in stats.values()):
        print("WARNING: missing files — every class must be present per the "
              "KANBAN-105 human directive", file=sys.stderr)
    if args.dry_run:
        print("\nDry run: nothing staged.")
        return 0

    out = files_dir / "original_files_mapping.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for m in sorted(mapping, key=lambda m: m["filename"]):
            fh.write(safe_jsonl_line(m) + "\n")
    print(f"Wrote {len(mapping)} mappings -> {out}")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
