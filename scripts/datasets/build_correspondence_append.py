#!/usr/bin/env python3
"""Build the KANBAN-105 correspondence append for docclass-merged v6.

Draws ``--n`` NEW stratified correspondence rows from the deduplicated Enron
corpus (``Lucius-Morningstar/enron-correspondence-dedup`` ground_truth config)
for fusion into ``docclass-merged`` v6 — the primary-doc-class rebalance
(correspondence was 110/1210 = 9.1% of v5).

Draw law (KANBAN-084 pilot law, deterministic + rebuild-stable):

* pool   : every dedup GT row whose ``expected`` is ``correspondence`` and
           whose ``filename`` is NOT already in the parent (v5) corpus;
* strata : ``expected_subclass``;
* order  : within a stratum candidates are ordered by ``sha256(filename)``
           ascending (content-addressed — decorrelates from the md5-keyed
           family split rule, same trick as the v4 fusion + pilot draw);
* quota  : ``--quota`` (default 30) per stratum, ``min(quota, available)``;
* fill   : any shortfall (tiny strata, e.g. attorney_demand n=3) redistributes
           round-robin over sorted strata with remaining surplus, one slot per
           pass, until ``--n`` rows are drawn or the pool exhausts.

Labeler verification pass (the "3-labeler" gate): the shared Enron
labelers are IMPORTED (never forked) from ``--enron-scripts`` and re-run on
every drawn row — ``correspondence_subclasses.label_correspondence``,
``content_topics.label_content_topic``, ``sentiment_scorer.sentiment_for_row``
— and must reproduce the Hub GT exactly (subclass + topic + sentiment label
and score). Rows where the labeler disagrees with the Hub GT are acceptable
ONLY when the filename carries a documented GT override (KANBAN-103
phrase-lexicon false-positive patches); any other mismatch aborts the build.

The KANBAN-103 override file is applied to the drawn rows' ``expected_subclass``
(the Hub GT files were already patched; the repo-side file is the auditable
source — hits are counted and must match).

Inputs (staging; see the KANBAN-105 card):
    --parent-gt-dir  dir with the docclass-merged v5 ground_truth parquet
                     shards (train + test)
    --dedup-gt       enron-correspondence-dedup ground_truth JSONL files
                     (train + test, comma-separated)
    --blind          dedup BLIND JSONL files (train + test, comma-separated) —
                     streamed and filtered, never fully materialized
    --overrides      filename-keyed GT override JSONL (default: the repo's
                     KANBAN-103 file)

Output: one JSONL row per drawn document in the docclass-merged row shape
``{filename, doc_text, prompt, expected, expected_subclass, split, gt_fields,
metadata}`` — the fusion input consumed by ``build_docclass_v6.py``.

Usage:
    python scripts/datasets/build_correspondence_append.py --dry-run ...
    python scripts/datasets/build_correspondence_append.py ...
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# KANBAN-088: shared JSONL line-boundary safety (Hub worker splits rows on
# U+2028/U+2029/NEL; see scripts/datasets/_jsonl_safety.py).
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from scripts.datasets._jsonl_safety import safe_jsonl_line  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.datasets.build_docclass_merged import (  # noqa: E402
    normalize_contract_subclass,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENRON_SCRIPTS = Path.home() / "Enron-Evaluation-Environment" / "scripts"
DEFAULT_OVERRIDES = (
    REPO_ROOT / "data" / "gt" / "enron_correspondence_label_overrides.jsonl"
)
DEFAULT_OUT = Path("data/datasets/correspondence_append_v6.jsonl")

SENTIMENT_LABELS = ("negative", "neutral", "positive")


def load_module(path: Path, name: str):
    """Import a shared labeler module by path (imported, never forked)."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"module not found: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def existing_filenames(parent_gt_dir: Path) -> set[str]:
    """Every filename in the parent (v5) ground_truth parquet shards."""
    import pyarrow.parquet as pq

    names: set[str] = set()
    for shard in sorted(parent_gt_dir.glob("*.parquet")):
        names.update(pq.read_table(shard).column("filename").to_pylist())
    return names


def load_overrides(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for row in read_jsonl(path):
        fn = str(row.get("filename") or "").strip()
        if fn:
            out[fn] = row
    return out


def load_pool(dedup_gt_files: list[Path], exclude: set[str]) -> list[dict]:
    """Correspondence pool rows not already present in the parent corpus."""
    pool = []
    seen = set()
    for path in dedup_gt_files:
        for row in read_jsonl(path):
            fn = str(row.get("filename") or "").strip()
            if not fn or fn in seen:
                continue
            seen.add(fn)
            if fn in exclude:
                continue
            if str(row.get("expected") or "").strip() != "correspondence":
                continue
            pool.append(row)
    return pool


def sha256_key(filename: str) -> str:
    return hashlib.sha256(filename.encode("utf-8")).hexdigest()


def compose_doc_text(subject, text):
    """Mirror of src.correspondence_eval.compose_doc_text (kept local: this
    builder runs in minimal environments without the langchain stack; a test
    pin asserts byte-equality with the canonical helper)."""
    subject = str(subject or "").strip()
    body = str(text or "").strip()
    if subject and body:
        return f"Subject: {subject}\n\n{body}"
    return body or subject


def stratified_draw(pool: list[dict], n: int, quota: int) -> list[dict]:
    """Pilot-law draw: sha256 order within stratum, quota + round-robin fill."""
    strata: dict[str, list[dict]] = defaultdict(list)
    for row in pool:
        strata[str(row.get("expected_subclass") or "other")].append(row)
    for key in strata:
        strata[key].sort(key=lambda r: sha256_key(str(r["filename"])))
    taken: set[str] = set()
    drawn: list[dict] = []
    for key in sorted(strata):
        for row in strata[key][:quota]:
            taken.add(str(row["filename"]))
            drawn.append(row)
    # round-robin shortfall fill over sorted strata (deterministic)
    cursors = {key: min(quota, len(strata[key])) for key in strata}
    while len(drawn) < n:
        progressed = False
        for key in sorted(strata):
            if len(drawn) >= n:
                break
            while cursors[key] < len(strata[key]):
                row = strata[key][cursors[key]]
                cursors[key] += 1
                if str(row["filename"]) not in taken:
                    taken.add(str(row["filename"]))
                    drawn.append(row)
                    progressed = True
                    break
        if not progressed:
            break
    return drawn


def _iter_lines(source: str):
    """Yield lines from a local path OR an http(s) URL (streamed, no temp file)."""
    if source.startswith("http://") or source.startswith("https://"):
        import httpx

        with httpx.stream("GET", source, timeout=120, follow_redirects=True) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                yield line
    else:
        with open(source, encoding="utf-8") as fh:
            yield from fh


def stream_filter_blind(blind_sources: list[str], wanted: set[str]) -> dict[str, dict]:
    """Stream the (large) blind JSONLs and keep only the selected rows."""
    got: dict[str, dict] = {}
    for source in blind_sources:
        for line in _iter_lines(source):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            fn = str(row.get("filename") or "").strip()
            if fn in wanted and fn not in got:
                got[fn] = row
            if len(got) == len(wanted):
                return got
    return got


def build_rows(drawn: list[dict], blind: dict[str, dict],
               overrides: dict[str, dict], sample_method: str) -> tuple[list[dict], dict]:
    """Fusion-shape rows for the drawn documents (doc_text composed)."""
    rows = []
    stats = {"override_hits": 0, "missing_blind": 0}
    for gt in sorted(drawn, key=lambda r: str(r["filename"])):
        fn = str(gt["filename"])
        source = blind.get(fn)
        if source is None:
            stats["missing_blind"] += 1
            continue
        row = dict(overrides.get(fn) or {})
        if row:
            stats["override_hits"] += 1
        subclass = str(row.get("expected_subclass")
                       or gt.get("expected_subclass") or "").strip()
        subclass = normalize_contract_subclass(subclass)
        doc_text = compose_doc_text(source.get("subject"), source.get("text"))
        md = dict(source.get("metadata") or {})
        md["source_dataset"] = "Lucius-Morningstar/enron-correspondence-dedup"
        md["sample_method"] = sample_method
        rows.append({
            "filename": fn,
            "doc_text": doc_text,
            "prompt": "",
            "expected": "correspondence",
            "expected_subclass": subclass,
            "split": str(gt.get("split") or ""),
            "gt_fields": {
                "label_evidence": str(row.get("label_evidence")
                                      or gt.get("label_evidence") or ""),
                "content_topic": str(gt.get("content_topic") or ""),
                "topic_evidence": str(gt.get("topic_evidence") or ""),
                "sentiment_score": gt.get("sentiment_score"),
                "sentiment_label": str(gt.get("sentiment_label") or ""),
                "sentiment_evidence": str(gt.get("sentiment_evidence") or ""),
            },
            "metadata": md,
        })
    return rows, stats


def verify_labelers(rows: list[dict], blind: dict[str, dict],
                    overrides: dict[str, dict],
                    enron_scripts: Path) -> dict:
    """Re-run the three shared labelers on every drawn row; compare to GT.

    The Hub GT was produced by these exact modules at publish time (then
    patched by the KANBAN-103 overrides). A verified draw means the labelers
    reproduce every non-overridden row's subclass/topic/sentiment exactly.
    """
    sub_mod = load_module(enron_scripts / "correspondence_subclasses.py",
                          "enron_correspondence_subclasses")
    topic_mod = load_module(enron_scripts / "content_topics.py",
                            "enron_content_topics")
    sent_mod = load_module(enron_scripts / "sentiment_scorer.py",
                           "enron_sentiment_scorer")
    stats: Counter = Counter()
    mismatches = []
    for row in rows:
        source = blind.get(str(row["filename"])) or {}
        view = {"subject": source.get("subject") or "",
                "body": source.get("text") or "", "parseable": True}
        label_sub, _ = sub_mod.label_correspondence(view)
        topic, _ = topic_mod.label_content_topic(view)
        score, label, _ = sent_mod.sentiment_for_row(view)
        gf = row["gt_fields"]
        expected_sub = str(row["expected_subclass"])
        overridden = str(row["filename"]) in overrides
        checks = {
            "subclass": label_sub == expected_sub,
            "topic": topic == gf["content_topic"],
            "sentiment_label": label == gf["sentiment_label"],
            "sentiment_score": abs(float(score) - float(gf["sentiment_score"])) < 1e-9,
        }
        for name, ok in checks.items():
            stats[f"{name}_match" if ok else f"{name}_mismatch"] += 1
            if not ok:
                stats[f"{name}_mismatch_overridden" if overridden
                      else f"{name}_mismatch_unexplained"] += 1
                if len(mismatches) < 20:
                    mismatches.append({
                        "filename": row["filename"], "field": name,
                        "labeler": str(label_sub if name == "subclass" else
                                       (topic if name == "topic" else score)),
                        "gt": str(expected_sub if name == "subclass" else
                                  (gf["content_topic"] if name == "topic"
                                   else gf["sentiment_score"])),
                        "overridden": overridden,
                    })
    return {"counts": dict(stats), "mismatches": mismatches}


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-gt-dir", type=Path, required=True,
                        help="dir holding the docclass-merged v5 ground_truth "
                             "parquet shards (train/test)")
    parser.add_argument("--dedup-gt", required=True,
                        help="comma-separated enron-correspondence-dedup "
                             "ground_truth JSONL files (train + test)")
    parser.add_argument("--blind", required=True,
                        help="comma-separated dedup BLIND JSONL files "
                             "(train + test); streamed, filtered in-flight")
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--enron-scripts", type=Path, default=DEFAULT_ENRON_SCRIPTS,
                        help="dir holding the shared labelers "
                             "(imported, never forked)")
    parser.add_argument("--n", type=int, default=240, help="rows to draw")
    parser.add_argument("--quota", type=int, default=30,
                        help="per-stratum quota before round-robin fill")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true",
                        help="draw + verify, print the plan, write nothing")
    args = parser.parse_args(argv)

    exclude = existing_filenames(args.parent_gt_dir)
    print(f"parent filenames (exclusion set): {len(exclude):,}")
    pool = load_pool([Path(p.strip()) for p in args.dedup_gt.split(",") if p.strip()],
                     exclude)
    print(f"dedup pool after exclusion: {len(pool):,} correspondence rows")
    sub_counts = Counter(str(r.get("expected_subclass") or "other") for r in pool)
    print(f"pool subclasses: {dict(sorted(sub_counts.items()))}")

    drawn = stratified_draw(pool, args.n, args.quota)
    print(f"drawn: {len(drawn)} rows "
          f"({dict(sorted(Counter(str(r['expected_subclass']) for r in drawn).items()))})")
    if len(drawn) < args.n:
        parser.error(f"pool exhausted at {len(drawn)} < {args.n} — raise the pool "
                     f"or lower --n")

    blind_files = [p.strip() for p in args.blind.split(",") if p.strip()]
    wanted = {str(r["filename"]) for r in drawn}
    blind = stream_filter_blind(blind_files, wanted)
    print(f"blind rows retrieved: {len(blind)}/{len(wanted)}")
    if len(blind) < len(wanted):
        parser.error(f"{len(wanted) - len(blind)} drawn filenames missing from the "
                     f"blind files — GT/blind join must be 1:1")

    overrides = load_overrides(args.overrides)
    sample_method = (f"stratified sha256(filename) deterministic draw of {len(drawn)} "
                     f"from {len(pool)} (KANBAN-105 v6 append; quota {args.quota})")
    rows, stats = build_rows(drawn, blind, overrides, sample_method)
    print(f"rows built: {len(rows)} | override hits: {stats['override_hits']} "
          f"| missing blind: {stats['missing_blind']}")

    verification = verify_labelers(rows, blind, overrides, args.enron_scripts)
    print("3-labeler verification pass:")
    for key in sorted(verification["counts"]):
        print(f"  {key}: {verification['counts'][key]}")
    unexplained = {k: v for k, v in verification["counts"].items()
                   if k.endswith("_mismatch_unexplained") and v}
    if unexplained:
        print(json.dumps(verification["mismatches"], indent=1))
        parser.error(f"labeler verification FAILED — unexplained mismatches: "
                     f"{unexplained} (labelers must reproduce the Hub GT)")
    print("  verification GREEN (mismatches limited to documented overrides)")

    splits = Counter(r["split"] for r in rows)
    print(f"split coverage: {dict(splits)}")
    if args.dry_run:
        print(f"\nDry run: would write {len(rows)} rows -> {args.out}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(safe_jsonl_line(row) + "\n")
    print(f"\nWrote {len(rows)} rows -> {args.out}")
    return 0


def main() -> int:
    return main_with_args(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
