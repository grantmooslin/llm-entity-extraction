#!/usr/bin/env python3
"""Download the full CUAD v1 contract corpus into a local subdirectory.

The Atticus Project CUAD v1 (https://huggingface.co/datasets/theatticusproject/cuad,
CC BY 4.0) is the canonical contract-understanding corpus: 510 real SEC-exhibit
contract PDFs across 29 agreement categories. This script downloads ALL of them
into ``data/cuad_pdfs/`` (or any ``--out-dir``), preserving the CUAD folder
structure so ``category_of()`` still works on the local copy:

    data/cuad_pdfs/CUAD_v1/full_contract_pdf/Part_I/License_Agreements/foo.pdf

It also downloads ``CUAD_v1.json`` (the clause QA ground truth) by default so
the corpus is fully self-contained offline.

Unlike ``stream_cuad_to_bt.py`` (which streams PDFs to temp files, renders
them, and uploads to Braintrust), this script KEEPS the PDFs on disk — the
input to ``scripts/eval/run_classification_eval.py --pdf-dir`` and friends.

Downloads are resumable: an existing non-empty file is skipped unless
``--overwrite`` is given; interrupted runs can simply be re-run.

Usage:
    python scripts/datasets/download_cuad_pdfs.py                  # all 510 PDFs + CUAD_v1.json
    python scripts/datasets/download_cuad_pdfs.py --dry-run        # preview only
    python scripts/datasets/download_cuad_pdfs.py --limit 12       # first 12 PDFs (pilot)
    python scripts/datasets/download_cuad_pdfs.py --category Franchise
    python scripts/datasets/download_cuad_pdfs.py --out-dir data/cuad_pdfs --skip-json
    python scripts/datasets/download_cuad_pdfs.py --overwrite      # re-download everything
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests

HF_TREE_URL = "https://huggingface.co/api/datasets/theatticusproject/cuad/tree/main/CUAD_v1/full_contract_pdf"
HF_RAW_URL = "https://huggingface.co/datasets/theatticusproject/cuad/resolve/main/"
CUAD_JSON_URL = (
    "https://huggingface.co/datasets/theatticusproject/cuad/resolve/main/"
    "CUAD_v1/CUAD_v1.json"
)
_USER_AGENT = "mailroom-cuad-downloader/1.0 (research sampling)"
DEFAULT_OUT_DIR = Path("data/cuad_pdfs")

# The local root below which the CUAD_v1 tree is mirrored.
_CUAD_ROOT_PARTS = ("CUAD_v1", "full_contract_pdf")


def list_pdf_paths() -> list[str]:
    """List every contract PDF path in the CUAD corpus (recursive HF tree API)."""
    resp = requests.get(HF_TREE_URL, params={"recursive": "true"},
                        headers={"User-Agent": _USER_AGENT}, timeout=120)
    resp.raise_for_status()
    entries = resp.json()
    pdfs = [e["path"] for e in entries if e.get("path", "").lower().endswith(".pdf")]
    return sorted(pdfs)


def category_of(pdf_path: str) -> str:
    """Extract the agreement category from the path (e.g. 'Franchise')."""
    parts = Path(pdf_path).parts
    return parts[-2] if len(parts) >= 2 else "unknown"


def local_dest(pdf_path: str, out_dir: Path) -> Path:
    """Map a HF repo path to the local file, stripping the CUAD tree root so
    ``data/cuad_pdfs/License_Agreements/foo.pdf`` mirrors the repo layout."""
    parts = Path(pdf_path).parts
    while parts and parts[0] in _CUAD_ROOT_PARTS:
        parts = parts[1:]
    return out_dir.joinpath(*parts)


def download_file(url: str, dest: Path, *, chunk_size: int = 1 << 20) -> int:
    """Stream ``url`` to ``dest`` (creating parent dirs), returning byte count."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    if part.exists():
        part.unlink()
    resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=600,
                        stream=True)
    resp.raise_for_status()
    total = int(resp.headers.get("Content-Length", 0))
    written = 0
    with part.open("wb") as fh:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            fh.write(chunk)
            written += len(chunk)
            if total:
                print(f"\r  {written / 1e6:,.1f} / {total / 1e6:,.1f} MB "
                      f"({written / total * 100:.0f}%)", end="", flush=True)
    print()
    os.replace(part, dest)
    return written


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help=f"Local directory to mirror the corpus into (default: {DEFAULT_OUT_DIR})")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only the first N PDFs (0 = all 510)")
    parser.add_argument("--category", default=None,
                        help="Only PDFs in this agreement category (e.g. Franchise, IP, License_Agreements)")
    parser.add_argument("--skip-json", action="store_true",
                        help="Do not download CUAD_v1.json clause QA annotations")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-download files that already exist")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be downloaded without touching the network")
    args = parser.parse_args(argv)

    print("Listing CUAD contract PDFs from Hugging Face...")
    pdf_paths = list_pdf_paths()
    if args.category:
        pdf_paths = [p for p in pdf_paths if category_of(p) == args.category]
        print(f"Category '{args.category}': {len(pdf_paths)} PDFs")
    if args.limit:
        pdf_paths = pdf_paths[: args.limit]
        print(f"Limited to {len(pdf_paths)} PDFs")
    if not pdf_paths:
        parser.error("No PDFs matched.")

    def plan(pdf_path: str) -> tuple[Path, bool]:
        dest = local_dest(pdf_path, args.out_dir)
        return dest, args.overwrite or not (dest.exists() and dest.stat().st_size > 0)

    planned = [(p, *plan(p)) for p in pdf_paths]
    to_download = [(p, dest) for p, dest, needed in planned if needed]
    print(f"\n{len(pdf_paths)} PDFs in corpus, {len(to_download)} need downloading "
          f"({len(planned) - len(to_download)} already present)")

    if args.dry_run:
        print(f"\nDry run: would download {len(to_download)} PDFs into {args.out_dir}/")
        for pdf_path, dest in to_download[:10]:
            print(f"  {pdf_path}  ->  {dest}")
        if len(to_download) > 10:
            print(f"  ... and {len(to_download) - 10} more")
        return 0

    total_bytes = 0
    failed: list[str] = []
    for i, (pdf_path, dest) in enumerate(to_download, start=1):
        try:
            print(f"[{i}/{len(to_download)}] {pdf_path}")
            # quote() the repo path: '#' in CUAD filenames ('Amendment #3 …')
            # would otherwise truncate the URL as a fragment (404) — KANBAN-105
            total_bytes += download_file(
                HF_RAW_URL + urllib.parse.quote(pdf_path), dest)
        except Exception as exc:  # noqa: BLE001 - one bad download must not abort the run
            failed.append(f"{pdf_path}: {type(exc).__name__}: {exc}")
            continue
    print(f"\nDownloaded {len(to_download) - len(failed)}/{len(to_download)} PDFs "
          f"({total_bytes / 1e6:,.1f} MB) into {args.out_dir}")

    if not args.skip_json:
        json_dest = args.out_dir / "CUAD_v1.json"
        if args.overwrite or not (json_dest.exists() and json_dest.stat().st_size > 0):
            print("Downloading CUAD_v1.json clause QA annotations...")
            try:
                total_bytes += download_file(CUAD_JSON_URL, json_dest)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"CUAD_v1.json: {type(exc).__name__}: {exc}")
        else:
            print(f"CUAD_v1.json already present: {json_dest}")

    if failed:
        print("Failures:", *failed[:10], sep="\n  ")
        return 1
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
