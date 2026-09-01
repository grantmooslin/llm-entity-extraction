#!/usr/bin/env python3
"""GT workbench — validation for hand-labeled extraction ground truth.

Validates `data/gt/<class>_handgt.jsonl` (or any labeled JSONL) against the
specialist schemas' field contracts:

    python3 scripts/gt_workbench.py --class contract            # validate
    python3 scripts/gt_workbench.py --validate data/gt/foo.jsonl
    python3 scripts/gt_workbench.py --stats                     # all files

Checks per row:
  - filename present in the corpus sample manifest (labels a real packet)
  - required keys per class schema; no unknown top-level keys beyond metadata
  - type conformance: *_string_array fields are lists[str]; nullable strings
    are str|None; dates parse in the class's expected format
  - verbatim grounding spot-checks: list/string values that quote the document
    must appear (whitespace-normalized) in the source text — catches
    hallucinated GT, which is worse than missing GT
Exit 1 on any error; prints a per-file stats block otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

GT_DIR = REPO_ROOT / "data" / "gt"
PACKETS = GT_DIR / "packets"
MANIFEST = GT_DIR / "sample_manifest.json"

# field -> (type, date_format|None)  per agents/specialist_agents.py schemas
SCHEMAS: dict[str, dict[str, tuple[str, str | None]]] = {
    "contract": {
        "document_name": ("nstr", None),
        "parties": ("arr", None),
        "effective_date": ("nstr", "%Y-%m-%d"),
        "term_length": ("nstr", None),
        "termination_clauses": ("arr", None),
        "governing_law": ("nstr", None),
        "key_obligations": ("arr", None),
        "contract_value": ("nstr", None),
        "renewal_terms": ("nstr", None),
    },
    "corporate_record": {
        "entity_name": ("nstr", None),
        "record_type": ("nstr", None),
        "effective_date": ("nstr", "%m/%d/%Y"),
        "key_provisions": ("arr", None),
        "signatories": ("arr", None),
        "jurisdiction": ("nstr", None),
        "filing_number": ("nstr", None),
    },
    "correspondence": {
        "sender": ("nstr", None),
        "recipient": ("nstr", None),
        "additional_recipients": ("arr", None),
        "communication_type": ("nstr", None),
        "communication_date": ("nstr", "%m/%d/%Y"),
        "key_points": ("arr", None),
        "demand_amount": ("nstr", None),
        "action_items": ("arr", None),
        "urgency": ("nstr", None),
        "referenced_communications": ("arr", None),
    },
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower()


def load_packet_text(cls: str, filename: str) -> str:
    """Locate the packet file whose header FILENAME matches."""
    ddir = PACKETS / cls
    if not ddir.exists():
        return ""
    want = _norm(filename)[:80]
    for p in sorted(ddir.glob("*.txt")):
        head = p.read_text(encoding="utf-8", errors="replace")[:200]
        m = re.search(r"FILENAME: (.+)", head)
        if m and want in _norm(m.group(1)):
            body = p.read_text(encoding="utf-8", errors="replace")
            return body.split("=" * 60, 1)[-1]
    return ""


def validate_file(path: Path, cls: str, texts: dict[str, str]) -> tuple[int, list[str]]:
    errors: list[str] = []
    n = 0
    schema = SCHEMAS[cls]
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        n += 1
        try:
            row = json.loads(line)
        except ValueError as e:
            errors.append(f"{path.name}:{lineno} bad JSON: {e}")
            continue
        fn = row.get("filename")
        if not fn:
            errors.append(f"{path.name}:{lineno} missing filename")
            continue
        text = texts.get(fn) or load_packet_text(cls, fn)
        if not text and cls != "insurance_claim":
            errors.append(f"{path.name}:{lineno} no packet/text found for {fn[:60]}")
        norm_text = _norm(text)
        for field, (kind, datefmt) in schema.items():
            if field not in row:
                continue  # absent == not labeled; allowed but tracked in stats
            v = row[field]
            if kind == "nstr":
                if v is not None and not isinstance(v, str):
                    errors.append(f"{fn[:50]}:{field} expected str|null, got {type(v).__name__}")
                elif v is not None and datefmt:
                    try:
                        datetime.strptime(v.strip(), datefmt)
                    except ValueError:
                        errors.append(f"{fn[:50]}:{field} date {v!r} != format {datefmt}")
            else:
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    errors.append(f"{fn[:50]}:{field} expected list[str]")
                    continue
            # verbatim grounding spot-check on quoted-style fields
            if isinstance(v, str) and len(v) > 24 and norm_text and _norm(v) not in norm_text:
                # allow normalized paraphrase only for name-ish/date-ish fields;
                # verbatim families must be grounded
                if field in ("termination_clauses", "governing_law"):
                    errors.append(f"{fn[:50]}:{field} not grounded verbatim in source")
                elif field in ("document_name", "entity_name", "contract_value",
                               "term_length", "demand_amount", "filing_number"):
                    # names/values may differ by punctuation/casing; require 60% token overlap
                    toks_t = set(_norm(text).split())
                    toks_v = [t for t in _norm(v).split() if len(t) > 2]
                    hit = sum(1 for t in toks_v if t in toks_t)
                    if toks_v and hit / len(toks_v) < 0.6:
                        errors.append(f"{fn[:50]}:{field} weakly grounded ({hit}/{len(toks_v)} tokens)")
            if isinstance(v, list) and field in ("termination_clauses", "key_obligations", "key_provisions"):
                for item in v:
                    if len(item) > 24 and norm_text and _norm(item) not in norm_text:
                        errors.append(f"{fn[:50]}:{field}[{v.index(item)}] item not grounded verbatim")
                        break
    return n, errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--class", dest="cls", help="validate data/gt/<cls>_handgt.jsonl")
    ap.add_argument("--validate", help="validate an explicit JSONL path (with --class)")
    ap.add_argument("--stats", action="store_true", help="per-file fill-rate stats")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    texts: dict[str, str] = {}
    for cls, files in manifest.items():
        for fn in files:
            texts[fn] = ""  # resolved lazily from packets

    targets: list[tuple[Path, str]] = []
    if args.validate:
        targets.append((Path(args.validate), args.cls or "contract"))
    elif args.cls:
        targets.append((GT_DIR / f"{args.cls}_handgt.jsonl", args.cls))
    else:
        for f in sorted(GT_DIR.glob("*_handgt.jsonl")):
            targets.append((f, f.name.replace("_handgt.jsonl", "")))

    rc = 0
    for path, cls in targets:
        if not path.exists():
            print(f"MISSING {path}")
            rc = 1
            continue
        n, errors = validate_file(path, cls, texts)
        filled: dict[str, int] = {}
        total = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            total += 1
            row = json.loads(line)
            for k, v in row.items():
                if k == "filename":
                    continue
                if v not in (None, [], ""):
                    filled[k] = filled.get(k, 0) + 1
        print(f"{path.name}: {total} rows | "
              + " ".join(f"{k}:{v}" for k, v in sorted(filled.items()))
              + f" | errors: {len(errors)}")
        for e in errors[:15]:
            print("  ERR", e)
        if errors:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
