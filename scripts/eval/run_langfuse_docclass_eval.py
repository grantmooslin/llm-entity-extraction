#!/usr/bin/env python3
"""LANGFUSE/PHOENIX doc-class evaluation — the hierarchical sorter task.

Runs the sorter over the EXTENDED primary classification (KANBAN-033): the
shared 6 doc classes PLUS ``merger_agreement`` (MAUD corpus), scoring BOTH
the primary ``doc_type`` and the second-level ``doc_subclass`` dimension
(consideration type for merger agreements — MAUD expert GT; record type for
corporate records — content-detected from the document). The tertiary level
is absent by design (human directive: only where the data necessitates it).

Datasets (each row carries ``expected`` doc_type + ``metadata.expected_subclass``):
- ``mailroom-maud-contracts``        — 152 MAUD merger agreements
- ``mailroom-cuad-contracts-full``   — the 510 CUAD contracts (subclass = CUAD subtype)
- ``mailroom-s1-corporate-records``  — EDGAR S-1 corporate-record exhibits

Local JSONL dumps (the reliable path while Braintrust row uploads are
org-capped) are loaded with ``--local-dumps`` — the flat shape the streamers'
``--local-dump`` writes (``{filename, doc_text, expected, expected_subclass,
metadata}``). The two loaders produce identical row shapes, so the eval loop
is byte-for-byte the same either way.

One sorter call per document; deterministic logic scorers
(doc_type_accuracy, subclass_accuracy, exact_match, confidence); manifest
resume; append-only repo experiment log; Arize Phoenix tracing by default
(Langfuse fallback).

Usage:
    python scripts/eval/run_langfuse_docclass_eval.py --dry-run
    python scripts/eval/run_langfuse_docclass_eval.py \\
        --datasets mailroom-maud-contracts,mailroom-cuad-contracts-full \\
        --stratified 120 --seed 42
    python scripts/eval/run_langfuse_docclass_eval.py \\
        --local-dumps data/maud/contracts.jsonl,data/s1_corporate_records/corporate-records.jsonl
    python scripts/eval/run_langfuse_docclass_eval.py --sample 5 --seed 42

Vision-primary mode (KANBAN-033 vision arm): ``--input-mode vision-primary``
classifies each document from its page images FIRST (the
``sorter_docclass_vision_v0`` prompt), and falls back to the text pass
(``doc_text``) when the vision pass cannot produce a label — no page images
for the row, a vision call error, or the model's own UNREADABLE/invalid
output. ``--pdf-dir`` points at a local PDF mirror whose files are matched to
rows by filename stem (e.g. the CUAD corpus tree under ``data/cuad_pdfs``);
rows without a matching PDF skip straight to text. ``--vision-pages all``
sends every rendered page in one call (the full-document read);
``--vision-pages first`` sends only page 1 (cheap pilot). The auto-switch
rule mirrors the classification runner: vision modes default the prompt to
``sorter_docclass_vision_v0`` unless ``--prompt-version`` is explicit.

    python scripts/eval/run_langfuse_docclass_eval.py \\
        --local-dumps data/datasets/docclass_merged.jsonl \\
        --input-mode vision-primary --pdf-dir data/cuad_pdfs \\
        --vision-pages first --sample 6 --seed 42
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.sorter_agent import (  # noqa: E402
    DOC_SUBCLASS_UNKNOWN,
    DOCCLASS_CLASS_KEYS,
    DOCCLASS_CLASSES,
    DOCCLASS_PILOT_CLASSES,
    DOCCLASS_PILOT_CLASS_KEYS,
    DOCCLASS_PILOT_SCHEMA,
    DOCCLASS_SCHEMA,
    SorterAgent,
    SUBCLASS_DIMENSIONS,
    equivalent_doc_subclasses,
    normalize_doc_subclass,
    normalize_subtype,
)
from scripts.eval.run_subtype_eval import _reasoning_span  # noqa: E402
from src.braintrust_config import load_braintrust_config  # noqa: E402
from src.braintrust_utils import load_braintrust_dataset  # noqa: E402
from src.env_utils import require_env  # noqa: E402
from src.evaluation import (  # noqa: E402
    ManifestStore,
    call_with_rate_limit_retry,
    dataset_fingerprint,
    resolve_concurrency,
    validate_dataset,
)
from src.experiment_log import default_jsonl_path, default_md_path  # noqa: E402
from src.tracing import resolve_tracer  # noqa: E402
from src.prompts import list_prompts  # noqa: E402

_CONFIG = load_braintrust_config()
DEFAULT_DATASETS = "mailroom-maud-contracts,mailroom-cuad-contracts-full,mailroom-s1-corporate-records"
DEFAULT_LOCAL_DUMP = "data/datasets/docclass_merged.jsonl"
DEFAULT_PROMPT = "sorter_docclass_v7"


class EvalResultShim:
    """Minimal braintrust.EvalResult-compatible row for the shared logger."""

    def __init__(self, input, output, error=None):
        self.input = input
        self.output = output
        self.error = error


class EvalRunShim:
    """Minimal braintrust.Eval-result-compatible container."""

    def __init__(self, results: list):
        self.results = results


def load_docclass_dataset(dataset_names: list[str], project: str, project_id: str,
                          local_dumps: list[Path] | None = None) -> list[dict]:
    """Load rows from Braintrust datasets and/or local JSONL dumps.

    Every returned row carries ``{doc_text, filename, expected, metadata,
    expected_subclass}`` where ``expected`` is the doc_type key and
    ``expected_subclass`` the second-level key (None when the class has no
    subclass dimension — e.g. correspondence).
    """
    rows: list[dict] = []
    valid = set(DOCCLASS_CLASS_KEYS) | set(DOCCLASS_PILOT_CLASS_KEYS)
    for name in dataset_names:
        dataset = load_braintrust_dataset(project, name, valid=valid, project_id=project_id)
        for d in dataset:
            d["expected_subclass"] = (d.get("metadata") or {}).get("expected_subclass")
            d["source_dataset"] = name
        rows.extend(dataset)
        print(f"  {name}: {len(dataset)} rows")
    for path in (local_dumps or []):
        if not path.exists():
            print(f"WARNING: local dump not found: {path}", file=sys.stderr)
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                expected = str(row.get("expected") or "").strip()
                if expected not in valid:
                    continue
                doc_text = str(row.get("doc_text") or "")
                if not doc_text.strip():
                    continue
                metadata = dict(row.get("metadata") or {})
                rows.append({
                    "doc_text": doc_text,
                    "prompt": str(row.get("prompt") or ""),
                    "filename": str(row.get("filename") or f"row_{len(rows) + 1}"),
                    "expected": expected,
                    "metadata": metadata,
                    "expected_subclass": row.get("expected_subclass") or metadata.get("expected_subclass"),
                    "gt_fields": dict(row.get("gt_fields") or {}),
                    "split": row.get("split"),
                    "source_dataset": str(path),
                })
        print(f"  {path}: local dump loaded")
    return rows


def stratified_sample(dataset: list[dict], n: int, seed: int) -> list[dict]:
    """Evenly distribute the sample across expected doc_type classes."""
    import random

    rng = random.Random(seed)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for d in dataset:
        by_class[d["expected"]].append(d)
    per_class = max(1, n // max(1, len(by_class)))
    picked: list[dict] = []
    for cls in sorted(by_class):
        picked.extend(rng.sample(by_class[cls], min(per_class, len(by_class[cls]))))
    if len(picked) < n:
        rest = [d for d in dataset if d not in picked]
        picked.extend(rng.sample(rest, min(n - len(picked), len(rest))))
    return picked[:n]


def random_sample(dataset: list[dict], n: int, seed: int) -> list[dict]:
    """Seeded random sample (mirrors run_subtype_eval.py semantics)."""
    import random

    return random.Random(seed).sample(dataset, min(n, len(dataset)))


def filter_by_filename_manifest(dataset: list[dict], manifest_path: Path) -> list[dict]:
    """Keep rows whose filename appears in a prior sample manifest (order preserved)."""
    wanted: list[str] = []
    with manifest_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            fn = row.get("filename")
            if fn:
                wanted.append(str(fn))
    by_name = {d["filename"]: d for d in dataset}
    missing = [fn for fn in wanted if fn not in by_name]
    if missing:
        raise SystemExit(
            f"filename manifest references {len(missing)} rows absent from the "
            f"loaded corpus (first: {missing[0]!r})"
        )
    return [by_name[fn] for fn in wanted]


def write_sample_manifest(dataset: list[dict], manifest_path: Path) -> None:
    """Persist the exact stratified/sample draw for cross-arm same-surface A/B."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as fh:
        for row in dataset:
            fh.write(json.dumps({
                "filename": row["filename"],
                "expected": row["expected"],
                "expected_subclass": row.get("expected_subclass"),
            }, ensure_ascii=False) + "\n")


def attach_pages_by_filename(dataset: list[dict], pdf_dir: Path) -> tuple[list[dict], int]:
    """Render local PDF pages and attach ``pages_b64`` to matching rows.

    Matches rows to PDFs by normalized filename stem (lowercased,
    non-alphanumerics stripped — CUAD row filenames are the PDF stems without
    the ``.pdf`` extension). Rendering mirrors ``load_local_pdfs`` in
    ``run_classification_eval.py`` (grayscale 1024x1024 PNGs, hard cap of 40
    pages per document). Returns ``(dataset, matched_count)``.
    """
    import base64

    from src.image_utils import pdf_to_png_bytes

    def _norm(name: str) -> str:
        import re

        return re.sub(r"[^a-z0-9]", "", Path(name).stem.lower())

    by_stem: dict[str, Path] = {}
    for path in sorted(pdf_dir.rglob("*.pdf")):
        by_stem.setdefault(_norm(path.name), path)

    matched = 0
    for d in dataset:
        if d.get("pages_b64"):
            continue
        pdf_path = by_stem.get(_norm(d.get("filename") or ""))
        if pdf_path is None:
            continue
        try:
            pdf_bytes = pdf_path.read_bytes()
            pages = []
            page_num = 0
            while True:
                try:
                    pages.append(pdf_to_png_bytes(pdf_bytes, page_num=page_num))
                    page_num += 1
                except (IndexError, ValueError):
                    break
                except Exception as exc:  # noqa: BLE001 - one bad page must not abort
                    print(f"WARNING: page {page_num + 1} of {pdf_path.name} failed: {exc}",
                          file=sys.stderr)
                    break
                if page_num >= 40:  # hard cap, same as the classification runner
                    break
            if pages:
                d["pages_b64"] = [base64.b64encode(p).decode("utf-8") for p in pages]
                d["page_count"] = len(pages)
                matched += 1
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not abort
            print(f"WARNING: could not render {pdf_path.name}: {exc}", file=sys.stderr)
    return dataset, matched


# Docclass failure-mode classifier — src/dojo_compat keeps the runner's
# contract (positional booleans, None on correct rows); the package's
# classify_docclass_failure(row) takes a row dict and never returns None.
from src.dojo_compat import classify_failure  # noqa: E402


def main() -> int:
    return main_with_args(sys.argv[1:])


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=_CONFIG.project_name, help="Braintrust project name (dataset source)")
    parser.add_argument("--project-id", default=_CONFIG.project_id, help="Braintrust project id (dataset source)")
    parser.add_argument("--dataset-project", default=_CONFIG.dataset_project, help="Project holding the datasets")
    parser.add_argument("--datasets", default=DEFAULT_DATASETS,
                        help="Comma-separated Braintrust datasets to evaluate")
    parser.add_argument("--local-dumps", default=DEFAULT_LOCAL_DUMP,
                        help="Comma-separated local JSONL dumps (default: "
                             f"{DEFAULT_LOCAL_DUMP} — schema v5 merged corpus, 1,210 rows; "
                             "replaces Braintrust loading when set)")
    parser.add_argument("--input-mode", choices=["text", "vision", "vision-primary"],
                        default="text",
                        help="text: classify doc_text (default); vision: classify page "
                             "images ONLY (needs --pdf-dir matches); vision-primary: try "
                             "the vision pass FIRST, fall back to the text pass when the "
                             "vision pass cannot produce a label (no pages, call error, "
                             "UNREADABLE/invalid output)")
    parser.add_argument("--pdf-dir", type=Path, default=None,
                        help="Local PDF mirror (e.g. data/cuad_pdfs) whose pages are "
                             "rendered for the vision pass; rows are matched by filename "
                             "stem. Only used with --input-mode vision|vision-primary")
    parser.add_argument("--vision-pages", choices=["all", "first"], default="all",
                        help="all: send every rendered page in ONE vision call (full-"
                             "document read, default); first: send only page 1 (cheap pilot)")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N rows")
    parser.add_argument("--sample", type=int, default=0, help="Random sample of N rows")
    parser.add_argument("--stratified", type=int, default=0,
                        help="STRATIFIED sample of N rows: evenly distributed across doc_type classes")
    parser.add_argument("--seed", type=int, default=42, help="Seed for --sample/--stratified")
    parser.add_argument("--filename-manifest", type=Path, default=None,
                        help="JSONL of {filename,...} rows — reuse an exact prior "
                             "sample instead of re-drawing (--stratified/--sample)")
    parser.add_argument("--export-sample-manifest", type=Path, default=None,
                        help="After sampling, write the exact row list to this JSONL "
                             "(for cross-arm same-surface A/B)")
    parser.add_argument("--model", default=_CONFIG.model, help=f"Model (default: {_CONFIG.model})")
    parser.add_argument("--class-set", choices=["extended", "pilot"], default="extended",
                        help="Primary class universe: extended (6 shared + merger + insurance) "
                             "or pilot (the 5 classes the merged GT contains)")
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT,
                        help=f"Sorter prompt version (default: {DEFAULT_PROMPT})")
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=4096,
                        help="Max output tokens for the sorter's classification call")
    parser.add_argument("--reasoning-effort", default="medium",
                        help="Reasoning effort for the classification call (default: medium)")
    parser.add_argument("--max-input-chars", type=int, default=100_000,
                        help="Hard safety cap on document text fed to the sorter")
    parser.add_argument("--max-concurrency", type=int, default=None,
                        help="Concurrent API calls (default: AUTO — scales with the "
                             "sample size, 8..32 workers, until diminishing returns / "
                             "rate limits; pass N to pin)")
    parser.add_argument("--experiment-name", default=None,
                        help="Experiment name (default: {model-slug}_{prompt-version}_docclass_langfuse)")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifests/docclass_langfuse.jsonl"),
                        help="JSONL checkpoint manifest for resuming an interrupted run")
    parser.add_argument("--lf-project", default=None, help="Override the Langfuse project name")
    parser.add_argument("--lf-environment", default=None, help="Override the trace environment tag")
    parser.add_argument("--lf-trace-name", default="docclass_classification",
                        help="Langfuse trace name for each document")
    parser.add_argument("--experiment-log", type=Path, default=None,
                        help="JSONL experiment log path (default: $EXPERIMENT_LOG_PATH)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve config, load dataset, print the plan without running")
    args = parser.parse_args(argv)

    (openrouter_key,) = require_env("OPENROUTER_API_KEY")
    require_env("BRAINTRUST_API_KEY")  # still needed to load Braintrust datasets

    available = list_prompts()
    if args.prompt_version not in available:
        parser.error(f"Unknown prompt version {args.prompt_version!r}. Available: {available}")

    # Auto-switch rule (mirror of the classification runner): vision modes
    # default the prompt to the docclass VISION prompt; an explicit
    # --prompt-version always wins.
    if args.input_mode in ("vision", "vision-primary") \
            and args.prompt_version == DEFAULT_PROMPT:
        args.prompt_version = "sorter_docclass_vision_v1"
        print(f"  --input-mode {args.input_mode}: defaulting prompt to "
              f"{args.prompt_version}")

    experiment_name = args.experiment_name or (
        f"{args.model.split('/')[-1]}_{args.prompt_version}_docclass_langfuse"
    )

    dataset_names = [n.strip() for n in args.datasets.split(",") if n.strip()]
    local_dumps = None
    if args.local_dumps:
        local_dumps = [Path(p.strip()) for p in args.local_dumps.split(",") if p.strip()]
        dataset_names = []

    print(f"Loading datasets: {dataset_names or local_dumps}")
    dataset = load_docclass_dataset(dataset_names, args.dataset_project or args.project,
                                    project_id=_CONFIG.project_id, local_dumps=local_dumps)
    if args.input_mode in ("vision", "vision-primary"):
        if not args.pdf_dir:
            parser.error("--input-mode vision|vision-primary requires --pdf-dir "
                         "(a local PDF mirror matched to the rows by filename stem)")
        if not args.pdf_dir.exists():
            parser.error(f"--pdf-dir not found: {args.pdf_dir}")
        dataset, matched = attach_pages_by_filename(dataset, args.pdf_dir)
        print(f"  vision pages attached: {matched}/{len(dataset)} rows "
              f"({len(dataset) - matched} will use text fallback in vision-primary)")
    if args.filename_manifest:
        dataset = filter_by_filename_manifest(dataset, args.filename_manifest)
        print(f"Loaded {len(dataset)} rows from filename manifest "
              f"{args.filename_manifest}")
    elif args.stratified:
        dataset = stratified_sample(dataset, args.stratified, args.seed)
        print(f"Stratified {len(dataset)} rows evenly across doc_type "
              f"(requested {args.stratified}, seed {args.seed})")
    elif args.sample:
        dataset = random_sample(dataset, args.sample, args.seed)
    elif args.limit:
        dataset = dataset[: args.limit]
    if args.export_sample_manifest:
        write_sample_manifest(dataset, args.export_sample_manifest)
        print(f"Wrote sample manifest ({len(dataset)} rows) -> "
              f"{args.export_sample_manifest}")
    if not dataset:
        parser.error("No rows found in the datasets.")

    # Adaptive concurrency: scale the worker pool with the sample size until
    # diminishing returns / rate limits (explicit --max-concurrency N wins).
    args.max_concurrency = resolve_concurrency(len(dataset), args.max_concurrency)
    print(f"  concurrency: {args.max_concurrency} workers "
          f"(auto-scaled for {len(dataset)} rows)")

    class_counts = Counter(d["expected"] for d in dataset)
    subclass_counts = Counter(d["expected_subclass"] for d in dataset if d.get("expected_subclass"))
    print(f"doc_type distribution: {dict(class_counts)}")
    if subclass_counts:
        print(f"subclass GT distribution (where present): {dict(subclass_counts)}")
    validate_dataset(dataset, valid=set(DOCCLASS_CLASS_KEYS))

    log_path = args.experiment_log or default_jsonl_path()
    md_log_path = default_md_path()

    if args.dry_run:
        how = (f"filename manifest {args.filename_manifest} ({len(dataset)} rows)"
               if args.filename_manifest else
               f"stratified {args.stratified} (even across doc_type, seed {args.seed})"
               if args.stratified else
               f"sample {args.sample} (seed {args.seed})" if args.sample else
               f"limit {args.limit}" if args.limit else "all")
        _classes = (DOCCLASS_PILOT_CLASS_KEYS if args.class_set == "pilot"
                    else DOCCLASS_CLASS_KEYS)
        print(f"Dry run: {len(dataset)} rows ({how}) -> experiment '{experiment_name}'")
        print(f"  sorter={args.prompt_version} model={args.model} class_set={args.class_set} "
              f"classes={_classes}")
        print(f"  input_mode={args.input_mode} vision_pages={args.vision_pages} "
              f"tracing=langfuse-primary (phoenix fallback) "
              f"session={experiment_name} trace_name={args.lf_trace_name}")
        return 0

    # ------------------------------------------------------------------
    # Tracer — Langfuse PRIMARY, local Arize Phoenix server as fallback
    # (human directive 2026-08-16; resolver in src/tracing.py). Resolved
    # BEFORE the manifest so the checkpoint header records the real backend.
    # ------------------------------------------------------------------
    tracer, tracing_backend, tracing_meta = resolve_tracer(
        session_id=experiment_name,
        trace_name=args.lf_trace_name,
        tags=[f"prompt:{args.prompt_version}", args.model.split("/")[-1]],
        lf_project=args.lf_project,
        lf_environment=args.lf_environment,
    )
    if tracing_backend == "langfuse":
        if tracer.disabled:
            print("WARNING: Langfuse tracing is DISABLED (missing LANGFUSE keys "
                  "in langfuse.env) — the run proceeds untraced; results still "
                  "land in the repo experiment log.", file=sys.stderr)
        else:
            print(f"Tracing to Langfuse project '{tracing_meta['project']}' "
                  f"(environment '{tracing_meta['environment']}') at {tracing_meta['base_url']}")
    else:
        if tracer.disabled:
            print("WARNING: Phoenix tracing is DISABLED — the run proceeds "
                  "untraced; results still land in the repo experiment log.",
                  file=sys.stderr)
        else:
            print(f"Tracing to Arize Phoenix (local OpenTelemetry, "
                  f"endpoint={tracing_meta['endpoint']}) "
                  f"— Langfuse fallback (keys unavailable)")

    manifest = None
    if args.manifest:
        manifest = ManifestStore(args.manifest, {
            "experiment_name": experiment_name,
            "datasets": args.datasets,
            "dataset_size": len(dataset),
            "dataset_fingerprint": dataset_fingerprint(dataset),
            "model": args.model,
            "prompt_version": args.prompt_version,
            "input_mode": args.input_mode,
            "tracing_backend": tracing_backend,
        })
        manifest.initialize()

    usage_by_index: dict[int, dict] = {}

    def classify_one(input_data: dict) -> EvalResultShim:
        """Classify ONE document (exactly one sorter call, extended schema)."""
        index = input_data["index"]
        filename = input_data["filename"]
        expected_doc_type = input_data["expected"]
        expected_subclass = input_data.get("expected_subclass") or None

        if manifest:
            cached = manifest.get_completed(filename)
            if cached:
                return EvalResultShim(
                    input_data,
                    cached.get("scores", {}).get("composite") or {"sorter": {}, "error": "cached incomplete"},
                )

        trace_meta = {
            "datasets": args.datasets,
            "prompt_version": args.prompt_version,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "input_mode": args.input_mode,
        }
        with tracer.trace_document(filename, expected_doc_type, trace_meta) as handle:
            sorter = SorterAgent(model=args.model, api_key=openrouter_key,
                                 prompt_version=args.prompt_version,
                                 doc_classes=(DOCCLASS_PILOT_CLASSES if args.class_set == "pilot"
                                              else DOCCLASS_CLASSES),
                                 schema=(DOCCLASS_PILOT_SCHEMA if args.class_set == "pilot"
                                         else DOCCLASS_SCHEMA),
                                 callbacks=[handle.handler] if handle.handler else None)
            sorter._max_input_chars = args.max_input_chars
            sorter._max_tokens = args.max_tokens
            sorter._reasoning_effort = args.reasoning_effort

            input_mode_used = args.input_mode
            fallback_reason = None
            vision_usage = None
            try:
                if args.input_mode == "text":
                    result = sorter.classify_json(input_data["doc_text"])
                else:
                    pages = input_data.get("pages_b64") or []
                    vision_attempted = bool(pages)
                    if args.input_mode == "vision-primary" and not pages:
                        # No page images for the row -> text pass carries it.
                        fallback_reason = "no_pages"
                        result = sorter.classify_json(input_data["doc_text"])
                        input_mode_used = "text_fallback"
                    elif args.input_mode == "vision" and not pages:
                        result = {"doc_type": "correspondence", "contract_subtype": None,
                                  "doc_subclass": None, "confidence": 0.0,
                                  "reasoning": "no page images", "unreadable": True,
                                  "invalid_label": False}
                    elif args.vision_pages == "all":
                        result = sorter.classify_document(pages)
                    else:
                        # Cheap pilot: page 1 only (one image per document).
                        result = sorter.classify_image(
                            pages[0], image_format=input_data.get("image_format", "png"))
                    if vision_attempted:
                        vision_usage = sorter._last_usage or {}
                        if args.input_mode == "vision-primary" \
                                and (result.get("unreadable") or result.get("invalid_label")
                                     or result.get("doc_type") is None):
                            fallback_reason = (
                                "unreadable" if result.get("unreadable")
                                else "invalid_label" if result.get("invalid_label")
                                else "no_label")
                            result = sorter.classify_json(input_data["doc_text"])
                            input_mode_used = "text_fallback"
                        elif args.input_mode == "vision-primary":
                            input_mode_used = "vision"
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort
                if args.input_mode == "vision-primary":
                    # Vision call failed -> text fallback carries the row.
                    fallback_reason = f"vision_error:{type(exc).__name__}"
                    try:
                        result = sorter.classify_json(input_data["doc_text"])
                    except Exception as text_exc:  # noqa: BLE001
                        result = {"doc_type": "correspondence", "contract_subtype": None,
                                  "doc_subclass": None, "confidence": 0.0,
                                  "reasoning": f"error: {text_exc}"}
                    input_mode_used = "text_fallback"
                else:
                    result = {"doc_type": "correspondence", "contract_subtype": None,
                              "doc_subclass": None, "confidence": 0.0,
                              "reasoning": f"error: {exc}"}

            # Usage accounting: count the vision call AND the fallback text call.
            usage_by_index[index] = sorter._last_usage or {}
            if vision_usage and input_mode_used == "text_fallback":
                merged = dict(usage_by_index[index])
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    merged[key] = (merged.get(key) or 0) + (vision_usage.get(key) or 0)
                usage_by_index[index] = merged

            doc_type = str(result.get("doc_type", "correspondence")).strip().lower()
            doc_type_ok = doc_type == expected_doc_type
            # Canonicalize BOTH sides before comparing: the model emits enum
            # keys while GT dialects vary by corpus (CUAD folder labels like
            # 'License_Agreements', snake_case keys, folder conventions such
            # as 'Joint Venture _ Filing'). contract rows score through the
            # contract_subtype dimension (normalize_subtype); every registered
            # doc_subclass dimension through normalize_doc_subclass.
            if doc_type == "contract":
                predicted_subclass = normalize_subtype(result.get("contract_subtype"))
                expected_subclass_canon = normalize_subtype(expected_subclass)
            elif doc_type in SUBCLASS_DIMENSIONS:
                predicted_subclass = normalize_doc_subclass(
                    result.get("doc_subclass"), doc_type)
                expected_subclass_canon = normalize_doc_subclass(expected_subclass, doc_type)
            else:
                predicted_subclass = None
                expected_subclass_canon = None
            # subclass_ok is None when the row carries no subclass GT (the
            # class has no second level) — those rows neither count for nor
            # against subclass_accuracy. GT 'other' stays a scoreable value.
            if expected_subclass and expected_subclass_canon is not None:
                subclass_ok = predicted_subclass == expected_subclass_canon
            else:
                subclass_ok = None
            # Equivalence-aware subclass: a defensible family read counts as a
            # hit (e.g. mixed_cash_stock <-> mixed_cash_stock_election), the
            # docclass mirror of subtype_accuracy_equiv.
            subclass_ok_equiv = (
                doc_type_ok and expected_subclass_canon is not None and equivalent_doc_subclasses(
                    predicted_subclass, expected_subclass_canon, doc_type)
            ) if expected_subclass and doc_type != "contract" else (
                doc_type_ok and predicted_subclass == expected_subclass_canon
            ) if expected_subclass else None
            exact = doc_type_ok and (subclass_ok if expected_subclass else True)
            try:
                confidence = float(result.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0

            composite = {
                "sorter": {
                    "doc_type": doc_type,
                    "contract_subtype": normalize_subtype(
                        result.get("contract_subtype") if doc_type == "contract" else None),
                    "doc_subclass": predicted_subclass,
                    "expected_doc_type": expected_doc_type,
                    "expected_subclass": expected_subclass,
                    "confidence": confidence,
                    "reasoning": _reasoning_span(result, failed=not exact),
                    "doc_type_ok": doc_type_ok,
                    "subclass_ok": subclass_ok,
                    "subclass_ok_equiv": subclass_ok_equiv,
                    "exact_match": exact,
                    "failure_mode": classify_failure(doc_type_ok, subclass_ok, predicted_subclass),
                    "truncated": sorter._last_truncated,
                    "input_mode": input_mode_used,
                    "fallback_reason": fallback_reason,
                },
            }

            handle.set_output(composite)
            handle.score("doc_type_accuracy", 1.0 if doc_type_ok else 0.0,
                         comment="predicted doc_type == expected")
            if expected_subclass:
                handle.score("subclass_accuracy", 1.0 if subclass_ok else 0.0,
                             comment="predicted doc_subclass == GT (rows without subclass GT are unscored)")
                handle.score("subclass_accuracy_equiv", 1.0 if subclass_ok_equiv else 0.0,
                             comment="subclass exact OR defensible equivalent family")
            handle.score("exact_match", 1.0 if exact else 0.0,
                         comment="doc_type AND subclass exact")
            handle.score("confidence", confidence, comment="model-reported confidence")

            if manifest:
                manifest.append({"filename": filename, "status": "completed", "tag": "OK",
                                 "predicted": {"doc_type": doc_type,
                                               "doc_subclass": predicted_subclass},
                                 "error": "",
                                 "expected_doc_type": expected_doc_type,
                                 "expected_subclass_canon": expected_subclass_canon,
                                 "expected_subclass": expected_subclass,
                                 "scores": {"composite": composite}})

        return EvalResultShim(input_data, composite)

    rows = [
        {"index": i, "filename": d["filename"], "expected": d["expected"],
         "doc_text": d["doc_text"], "expected_subclass": d.get("expected_subclass"),
         "pages_b64": d.get("pages_b64") or []}
        for i, d in enumerate(dataset)
    ]
    results: list[EvalResultShim] = [None] * len(rows)  # type: ignore[list-item]
    retry_stats: dict = {"rate_limit_retries": 0}
    with ThreadPoolExecutor(max_workers=args.max_concurrency) as pool:
        futures = {
            pool.submit(call_with_rate_limit_retry, classify_one, row,
                        stats=retry_stats): i
            for i, row in enumerate(rows)
        }
        for future, i in futures.items():
            try:
                results[i] = future.result()
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort
                results[i] = EvalResultShim(rows[i], None, str(exc))
    if retry_stats["rate_limit_retries"]:
        print(f"  rate-limit retries: {retry_stats['rate_limit_retries']} "
              f"(exponential backoff)", file=sys.stderr)
    failures = [r for r in results if r.error]
    for failure in failures:
        print(f"ERROR {failure.input['filename']}: {failure.error}", file=sys.stderr)

    tracer.flush()
    tracer.shutdown()

    # tracing_backend + tracing_meta come from the resolver (Langfuse
    # primary, local Phoenix fallback) — reuse the resolved values.
    log_experiment_to_repo(
        EvalRunShim(results), dataset, args, experiment_name,
        usage_by_index, log_path, md_log_path,
        tracing_backend=tracing_backend,
        tracing_meta=tracing_meta,
        extra_params={"rate_limit_retries": retry_stats.get("rate_limit_retries", 0)},
    )
    print(f"\nExperiment logged to {log_path}")
    return 0


def log_experiment_to_repo(result, dataset, args, experiment_name,
                           usage, log_path, md_log_path,
                           tracing_backend: str = "langfuse",
                           tracing_meta: dict | None = None,
                           extra_params: dict | None = None) -> None:
    """Append ONE experiment-log record for the docclass run."""
    from statistics import mean

    from src.experiment_log import append_experiment, append_markdown, git_snapshot, tokens_summary

    rows = [r for r in result.results if r.error is None and isinstance(r.output, dict)]
    ok = [r.output for r in rows if isinstance(r.output, dict)]

    def _mean(key: str) -> float | None:
        values = [float((o.get("sorter") or {}).get(key))
                  for o in ok if (o.get("sorter") or {}).get(key) is not None]
        return round(mean(values), 4) if values else None

    def _ci(key: str) -> dict | None:
        """Percentile-bootstrap 95% CI over the per-document binary scores —
        the docclass mirror of the subtype surface's exact_match_ci."""
        from src.bootstrap import bootstrap_ci

        values = [float((o.get("sorter") or {}).get(key))
                  for o in ok if (o.get("sorter") or {}).get(key) is not None]
        return bootstrap_ci(values)

    doc_type_acc = _mean("doc_type_ok")
    subclass_acc = _mean("subclass_ok")
    subclass_acc_equiv = _mean("subclass_ok_equiv")
    exact_match = _mean("exact_match")
    confidence = _mean("confidence")

    # Per-class accuracy (doc_type level) + per-subclass accuracy (the
    # second-level dimension, with support counts) + subclass confusion.
    per_class: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    per_subclass: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    subclass_confusion: dict[str, Counter] = defaultdict(Counter)
    failure_insights = []
    mode_counts: Counter = Counter()
    equiv_recovered: list[str] = []
    input_mode_counts: Counter = Counter()
    per_row = []
    for r in result.results:
        output = r.output if isinstance(r.output, dict) else {}
        sorter = output.get("sorter") or {}
        index = r.input.get("index", -1) if isinstance(r.input, dict) else -1
        filename = r.input.get("filename") if isinstance(r.input, dict) else ""
        expected_doc_type = r.input.get("expected") if isinstance(r.input, dict) else "?"
        expected_subclass = r.input.get("expected_subclass") if isinstance(r.input, dict) else None
        per_row.append({
            "filename": filename,
            "status": "error" if r.error is not None else "completed",
            "error": r.error,
            "sorter": sorter,
            "sorter_tokens": usage.get(index) or {},
        })
        if r.error is None:
            input_mode_counts[sorter.get("input_mode") or "text"] += 1
            per_class[expected_doc_type]["total"] += 1
            if sorter.get("doc_type_ok"):
                per_class[expected_doc_type]["correct"] += 1
            if expected_subclass:
                predicted = sorter.get("doc_subclass") or DOC_SUBCLASS_UNKNOWN
                subclass_confusion[expected_subclass][predicted] += 1
                per_subclass[expected_subclass]["total"] += 1
                if sorter.get("subclass_ok"):
                    per_subclass[expected_subclass]["correct"] += 1
                # Equivalence recovery: subclass wrong strictly but a
                # defensible family read (mixed <-> election) — named rows.
                if not sorter.get("subclass_ok") and sorter.get("subclass_ok_equiv"):
                    equiv_recovered.append(filename)
            if not sorter.get("exact_match"):
                mode = sorter.get("failure_mode") or "unknown"
                mode_counts[mode] += 1
                failure_insights.append({
                    "filename": filename,
                    "expected": {"doc_type": expected_doc_type,
                                 "doc_subclass": expected_subclass},
                    "predicted": {"doc_type": sorter.get("doc_type"),
                                  "doc_subclass": sorter.get("doc_subclass")},
                    "failure_mode": mode,
                    "reasoning": sorter.get("reasoning"),
                })

    scores = {
        "doc_type_accuracy": doc_type_acc,
        "doc_type_accuracy_ci": _ci("doc_type_ok"),
        "subclass_accuracy": subclass_acc,
        "subclass_accuracy_ci": _ci("subclass_ok"),
        "subclass_accuracy_equiv": subclass_acc_equiv,
        "exact_match": exact_match,
        "exact_match_ci": _ci("exact_match"),
        "confidence": confidence,
        "n_rows": len(rows),
        "n_errors": len(result.results) - len(rows),
        "per_class_accuracy": {k: round(v["correct"] / v["total"], 4) if v["total"] else None
                               for k, v in sorted(per_class.items())},
        "per_subclass_accuracy": {k: round(v["correct"] / v["total"], 4) if v["total"] else None
                                  for k, v in sorted(per_subclass.items())},
        "per_subclass_support": {k: v["total"] for k, v in sorted(per_subclass.items())},
        "subclass_confusion": {k: dict(v) for k, v in sorted(subclass_confusion.items())},
        "equiv_recovered": equiv_recovered,
        "input_mode_counts": dict(input_mode_counts),
        "sorter": {
            "failure_insights": {
                "mode_counts": dict(mode_counts),
                "n_failed": len(failure_insights),
                "failures": failure_insights[:200],
            },
        },
    }

    from src.score_emitter import build_emitter, emit_docclass_run_scores  # noqa: E402

    emitter = build_emitter()
    emit_docclass_run_scores(emitter, experiment_name, scores)

    record = {
        "type": "experiment",
        "experiment_name": experiment_name,
        "task": "docclass_classification",
        "model": args.model,
        "prompt_versions": {"sorter": args.prompt_version},
        "data_source": {
            "datasets": args.datasets,
            "ground_truth": "doc_type + doc_subclass",
            "ground_truth_mode": "maud_consideration_gt / s1_record_type / cuad_subtype",
            "dataset_fingerprint": dataset_fingerprint(dataset),
            "n_samples": len(dataset),
            "sample_requested": args.sample,
            "stratified": args.stratified,
            "limit": args.limit,
            "seed": args.seed,
        },
        "parameters": {
            "datasets": args.datasets,
            "sample": args.sample,
            "stratified": args.stratified,
            "seed": args.seed,
            "max_input_chars": args.max_input_chars,
            "max_tokens": args.max_tokens,
            "reasoning_effort": args.reasoning_effort,
            "temperature": args.temperature,
            "input_mode": args.input_mode,
            "vision_pages": args.vision_pages,
            "pdf_dir": str(args.pdf_dir) if args.pdf_dir else None,
            "max_concurrency": args.max_concurrency,
            "rate_limit_retries": (extra_params or {}).get("rate_limit_retries", 0),
            "tracing_backend": tracing_backend,
            "tracing_meta": tracing_meta or {},
        },
        "scores": scores,
        "per_row": per_row,
        # The renderer's per-document tables read `results` (the shared
        # experiment_markdown contract) — mirror per_row under both keys.
        "results": per_row,
        "tokens": {"sorter": tokens_summary(list(usage.values()), model=args.model),
                   "total": tokens_summary(list(usage.values()), model=args.model)},
        "git": git_snapshot(),
    }
    jsonl_path = append_experiment(record, log_path)
    append_markdown(record, md_log_path)
    print(f"\nExperiment logged to {jsonl_path}")


if __name__ == "__main__":
    raise SystemExit(main())
