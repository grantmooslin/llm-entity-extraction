#!/usr/bin/env python3
"""Correspondence-only docclass eval (KANBAN-103) — Enron emails from HF.

Primary + secondary classification over correspondence entries only, plus a
sentiment polarity pair aligned to the Hub ``ground_truth`` assortment:

    predicted.doc_type           <->  expected              (always correspondence)
    predicted.doc_subclass       <->  expected_subclass     (8 communication types)
    predicted.sentiment_label    <->  sentiment_label       (negative/neutral/positive)
    predicted.sentiment_score    <->  sentiment_score       ([-1, 1])

Source: ``Lucius-Morningstar/enron-correspondence-dedup`` (agent-blind
``default`` joined to ``ground_truth`` on ``filename``). Emails are short, so
the default input cap is 20k chars and concurrency can run higher than CUAD.

Braintrust experiment/span logging is ON by default for this runner (the
human asked for BT traces); pass ``--no-braintrust-logging`` to sink only to
the repo experiment log. Phoenix/Langfuse tracing still attaches when those
keys resolve.

Usage:
    python scripts/eval/run_correspondence_eval.py --dry-run
    python scripts/eval/run_correspondence_eval.py --dry-run --stratified 200 --seed 42
    python scripts/eval/run_correspondence_eval.py --local-dumps data/datasets/enron_corr.jsonl \\
        --stratified 200 --seed 42 --dry-run
    python scripts/eval/run_correspondence_eval.py --stratified 200 --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from braintrust.integrations.langchain import setup_langchain  # noqa: E402

import braintrust  # noqa: E402

from agents.sorter_agent import (  # noqa: E402
    CORRESPONDENCE_EVAL_SCHEMA,
    DOCCLASS_CLASSES,
    DOC_SUBCLASS_UNKNOWN,
    SENTIMENT_SCORE_BAND,
    SorterAgent,
    equivalent_doc_subclasses,
    normalize_doc_subclass,
)
from scripts.datasets.load_enron_correspondence import (  # noqa: E402
    DEFAULT_REPO,
    attach_blind_text,
    load_gt_rows,
    load_local_jsonl,
)
from scripts.eval.run_subtype_eval import _reasoning_span  # noqa: E402
from src.braintrust_config import load_braintrust_config  # noqa: E402
from src.braintrust_logging import langsmith_enabled  # noqa: E402
from src.correspondence_eval import (  # noqa: E402
    CORRESPONDENCE_DOC_TYPE,
    append_missing_by_subclass,
    apply_gt_overrides,
    merge_eval_rows,
    read_filename_manifest,
    read_gt_overrides,
    score_sentiment,
    stratified_by_subclass,
)
from src.dojo_compat import classify_failure  # noqa: E402
from src.env_utils import get_env, load_env, require_env  # noqa: E402
from src.eval_shims import run_local_eval  # noqa: E402
from src.evaluation import (  # noqa: E402
    ManifestStore,
    dataset_fingerprint,
    resolve_concurrency,
    validate_dataset,
)
from src.experiment_log import default_jsonl_path, default_md_path  # noqa: E402
from src.prompts import list_prompts  # noqa: E402
from src.tracing import resolve_tracer  # noqa: E402

_CONFIG = load_braintrust_config()
DEFAULT_PROMPT = "sorter_docclass_correspondence_v0"
DEFAULT_STRATIFIED = 200
RESERVED_EXPERIMENT_NAME = "qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42"


class EvalResultShim:
    """Minimal braintrust.EvalResult-compatible row for the shared logger."""

    def __init__(self, input, output, error=None, expected=None):
        self.input = input
        self.output = output
        self.error = error
        self.expected = expected


class EvalRunShim:
    """Minimal braintrust.Eval-result-compatible container."""

    def __init__(self, results: list):
        self.results = results


def _enable_braintrust_logging(enabled: bool) -> bool:
    """Honor the runner flag; this eval defaults Braintrust traces ON."""
    os.environ["BRAINTRUST_LOGGING"] = "enabled" if enabled else "disabled"
    return enabled


def publish_prompt_to_braintrust(
    project_name: str, version: str, model: str,
) -> None:
    """Upsert one registered prompt version into a Braintrust project library."""
    from src.prompts import get_prompt

    braintrust.login()
    project = braintrust.projects.create(name=project_name)
    project.prompts.create(
        name=version,
        slug=version.replace("_", "-"),
        description=(
            f"KANBAN-103 correspondence sorter {version} "
            f"(doc_type + communication-function subclass + sentiment)"
        ),
        messages=[{"role": "system", "content": get_prompt(version)}],
        model=model,
        if_exists="replace",
        metadata={
            "kanban": "103",
            "prompt_version": version,
            "task": "correspondence_classification",
        },
        tags=["correspondence", "docclass", "kanban-103"],
    )
    result = project.publish()
    print(f"Published Braintrust prompt '{version}' -> project '{project_name}'"
          f"{'' if result is None else f' ({result})'}")


def write_sample_manifest(dataset: list[dict], manifest_path: Path) -> None:
    """Persist the exact stratified draw for same-surface A/B reruns."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as fh:
        for row in dataset:
            fh.write(json.dumps({
                "filename": row["filename"],
                "expected": row["expected"],
                "expected_subclass": row.get("expected_subclass"),
                "sentiment_label": row.get("sentiment_label"),
                "sentiment_score": row.get("sentiment_score"),
            }, ensure_ascii=False) + "\n")  # KANBAN-088-EXEMPT: json.dumps always escapes control chars (no raw newlines); UTF-8 output only


def filter_by_filename_manifest(dataset: list[dict], manifest_path: Path) -> list[dict]:
    """Keep rows whose filename appears in a prior sample manifest."""
    wanted = read_filename_manifest(manifest_path)
    by_name = {d["filename"]: d for d in dataset}
    missing = [fn for fn in wanted if fn not in by_name]
    if missing:
        raise SystemExit(
            f"filename manifest references {len(missing)} rows absent from the "
            f"loaded corpus (first: {missing[0]!r})"
        )
    return [by_name[fn] for fn in wanted]


def main() -> int:
    return main_with_args(sys.argv[1:])


def main_with_args(argv: list[str]) -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=_CONFIG.project_name)
    parser.add_argument("--project-id", default=_CONFIG.project_id)
    parser.add_argument("--hf-repo", default=DEFAULT_REPO,
                        help=f"Hugging Face dataset repo (default: {DEFAULT_REPO})")
    parser.add_argument("--split", choices=("train", "test", "all"), default="all")
    parser.add_argument("--local-dumps", default="",
                        help="Comma-separated joined JSONL dumps (skips Hub load)")
    parser.add_argument("--stratified", type=int, default=DEFAULT_STRATIFIED,
                        help="Subclass-stratified sample size (default: 200)")
    parser.add_argument("--sample", type=int, default=0,
                        help="Random sample of N rows (overrides --stratified when set)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--filename-manifest", type=Path, default=None)
    parser.add_argument(
        "--include-all-attorney-demand",
        action="store_true",
        help="After the draw, append every remaining attorney_demand row "
             "from the loaded corpus (Hub n=3; extras via --extra-dumps).",
    )
    parser.add_argument(
        "--extra-dumps",
        default="",
        help="Comma-separated joined JSONL dumps merged AFTER the Hub/local "
             "draw (first filename wins). Used to restore full-corpus "
             "attorney_demand rows the dedup dump dropped.",
    )
    parser.add_argument(
        "--gt-overrides",
        type=Path,
        default=None,
        help="JSONL of filename → GT patches (expected_subclass, …) applied "
             "after the draw. Corrects Hub labels without a republish.",
    )
    parser.add_argument("--export-sample-manifest", type=Path, default=None)
    parser.add_argument("--model", default=_CONFIG.model)
    parser.add_argument("--prompt-version", default=DEFAULT_PROMPT)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--max-input-chars", type=int, default=20_000,
                        help="Emails are short; default 20k (CUAD uses 100k)")
    parser.add_argument("--max-concurrency", type=int, default=None)
    parser.add_argument("--experiment-name", default=None)
    parser.add_argument("--manifest", type=Path,
                        default=Path("data/manifests/correspondence_eval.jsonl"))
    parser.add_argument("--experiment-log", type=Path, default=None)
    parser.add_argument("--lf-project", default=None)
    parser.add_argument("--lf-environment", default=None)
    parser.add_argument("--lf-trace-name", default="correspondence_classification")
    parser.add_argument("--braintrust-logging", action=argparse.BooleanOptionalAction,
                        default=True,
                        help="Capture Braintrust experiment traces (default: on)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--publish-prompt", action=argparse.BooleanOptionalAction, default=True,
        help="Upsert the selected prompt version into the Braintrust project "
             "prompt library (default: on when Braintrust logging is on; "
             "--no-publish-prompt to skip).",
    )
    args = parser.parse_args(argv)

    (openrouter_key,) = require_env("OPENROUTER_API_KEY")
    bt_enabled = _enable_braintrust_logging(args.braintrust_logging)
    if bt_enabled:
        require_env("BRAINTRUST_API_KEY")

    available = list_prompts()
    if args.prompt_version not in available:
        parser.error(f"Unknown prompt version {args.prompt_version!r}. Available: {available}")

    experiment_name = args.experiment_name or (
        f"{args.model.split('/')[-1]}_{args.prompt_version}_enron{args.stratified or args.sample or 'all'}_s{args.seed}"
    )

    splits = ("train", "test") if args.split == "all" else (args.split,)
    local_dumps = [Path(p.strip()) for p in args.local_dumps.split(",") if p.strip()]
    extra_dumps = [Path(p.strip()) for p in args.extra_dumps.split(",") if p.strip()]
    args.extra_dump_paths = extra_dumps

    if local_dumps:
        dataset: list[dict] = []
        for path in local_dumps:
            if not path.exists():
                parser.error(f"local dump not found: {path}")
            loaded = load_local_jsonl(path)
            print(f"  {path}: {len(loaded)} correspondence rows")
            dataset.extend(loaded)
        full_local = list(dataset)
    else:
        token = get_env("HF_TOKEN") or os.environ.get("HF_TOKEN") or None
        print(f"Loading GT from {args.hf_repo} splits={splits}")
        gt_rows = load_gt_rows(args.hf_repo, token=token, splits=splits)
        gt_rows = [r for r in gt_rows
                   if str(r.get("expected") or "").strip() == CORRESPONDENCE_DOC_TYPE]
        print(f"  GT correspondence rows: {len(gt_rows)}")
        print(f"  subclass: {dict(Counter(r.get('expected_subclass') for r in gt_rows))}")
        print(f"  sentiment: {dict(Counter(r.get('sentiment_label') for r in gt_rows))}")
        # Stratify on GT first (no body), then join only the selected filenames
        # so the blind stream does not materialize 247k emails.
        staged = [{
            "filename": str(r.get("filename") or ""),
            "expected": str(r.get("expected") or CORRESPONDENCE_DOC_TYPE),
            "expected_subclass": r.get("expected_subclass"),
            "sentiment_label": r.get("sentiment_label"),
            "sentiment_score": r.get("sentiment_score"),
            "_gt": r,
        } for r in gt_rows if r.get("filename")]
        full_staged = list(staged)
        if args.filename_manifest:
            staged = filter_by_filename_manifest(staged, args.filename_manifest)
            print(f"Loaded {len(staged)} GT rows from filename manifest "
                  f"{args.filename_manifest}")
        elif args.sample:
            import random
            staged = random.Random(args.seed).sample(staged, min(args.sample, len(staged)))
        elif args.stratified:
            staged = stratified_by_subclass(staged, args.stratified, args.seed)
            print(f"Stratified {len(staged)} rows evenly across expected_subclass "
                  f"(requested {args.stratified}, seed {args.seed})")
        elif args.limit:
            staged = staged[: args.limit]
        if args.include_all_attorney_demand:
            before = len(staged)
            staged = append_missing_by_subclass(
                staged, full_staged, "attorney_demand")
            added = len(staged) - before
            print(f"  include-all-attorney-demand: appended {added} Hub "
                  f"attorney_demand row(s) (now {len(staged)})")
        wanted = {s["filename"] for s in staged}
        print(f"  joining blind text for {len(wanted)} filenames…")
        dataset = attach_blind_text(
            [s["_gt"] for s in staged], args.hf_repo, token=token, splits=splits,
        )
        by_name = {d["filename"]: d for d in dataset}
        ordered = [by_name[s["filename"]] for s in staged if s["filename"] in by_name]
        missing = [s["filename"] for s in staged if s["filename"] not in by_name]
        if missing:
            print(f"WARNING: {len(missing)} selected filenames had no blind text "
                  f"(first: {missing[0]!r})", file=sys.stderr)
        dataset = ordered

    if args.filename_manifest and local_dumps:
        dataset = filter_by_filename_manifest(dataset, args.filename_manifest)
        print(f"Loaded {len(dataset)} rows from filename manifest "
              f"{args.filename_manifest}")
    elif local_dumps:
        if args.sample:
            import random
            dataset = random.Random(args.seed).sample(dataset, min(args.sample, len(dataset)))
        elif args.stratified:
            dataset = stratified_by_subclass(dataset, args.stratified, args.seed)
            print(f"Stratified {len(dataset)} rows evenly across expected_subclass "
                  f"(requested {args.stratified}, seed {args.seed})")
        elif args.limit:
            dataset = dataset[: args.limit]
        if args.include_all_attorney_demand:
            before = len(dataset)
            dataset = append_missing_by_subclass(
                dataset, full_local, "attorney_demand")
            added = len(dataset) - before
            print(f"  include-all-attorney-demand: appended {added} local "
                  f"attorney_demand row(s) (now {len(dataset)})")

    if extra_dumps:
        extras: list[dict] = []
        for path in extra_dumps:
            if not path.exists():
                parser.error(f"extra dump not found: {path}")
            loaded = load_local_jsonl(path)
            print(f"  extra dump {path}: {len(loaded)} correspondence rows")
            extras.extend(loaded)
        before = len(dataset)
        dataset = merge_eval_rows(dataset, extras)
        print(f"  merged extra dumps: +{len(dataset) - before} new row(s) "
              f"(now {len(dataset)})")

    if args.gt_overrides:
        if not args.gt_overrides.exists():
            parser.error(f"gt-overrides file not found: {args.gt_overrides}")
        overrides = read_gt_overrides(args.gt_overrides)
        before_sub = Counter(d.get("expected_subclass") for d in dataset)
        dataset = apply_gt_overrides(dataset, overrides)
        after_sub = Counter(d.get("expected_subclass") for d in dataset)
        n_hit = sum(1 for d in dataset if d.get("filename") in overrides)
        print(f"  gt-overrides {args.gt_overrides}: {len(overrides)} patches, "
              f"{n_hit} row(s) in sample")
        if before_sub != after_sub:
            print(f"  subclass GT after overrides: {dict(after_sub)}")

    if args.export_sample_manifest:
        write_sample_manifest(dataset, args.export_sample_manifest)
        print(f"Wrote sample manifest ({len(dataset)} rows) -> "
              f"{args.export_sample_manifest}")
    if not dataset:
        parser.error("No correspondence rows loaded.")

    args.max_concurrency = resolve_concurrency(len(dataset), args.max_concurrency)
    print(f"  concurrency: {args.max_concurrency} workers "
          f"(auto-scaled for {len(dataset)} rows)")

    class_counts = Counter(d["expected"] for d in dataset)
    subclass_counts = Counter(d.get("expected_subclass") for d in dataset)
    sentiment_counts = Counter(d.get("sentiment_label") for d in dataset)
    print(f"doc_type distribution: {dict(class_counts)}")
    print(f"subclass GT distribution: {dict(subclass_counts)}")
    print(f"sentiment GT distribution: {dict(sentiment_counts)}")
    validate_dataset(dataset, valid={CORRESPONDENCE_DOC_TYPE})

    log_path = args.experiment_log or default_jsonl_path()
    md_log_path = default_md_path()

    if args.publish_prompt:
        require_env("BRAINTRUST_API_KEY")
        publish_prompt_to_braintrust(
            args.project, args.prompt_version, args.model)

    if args.dry_run:
        how = (
            f"filename manifest {args.filename_manifest} ({len(dataset)} rows)"
            if args.filename_manifest else
            f"stratified {args.stratified} (even across subclass, seed {args.seed})"
            if args.stratified and not args.sample else
            f"sample {args.sample} (seed {args.seed})" if args.sample else
            f"limit {args.limit}" if args.limit else "all"
        )
        print(f"Dry run: {len(dataset)} correspondence rows ({how}) -> "
              f"experiment '{experiment_name}'")
        if args.include_all_attorney_demand:
            n_atty = sum(1 for d in dataset
                         if d.get("expected_subclass") == "attorney_demand")
            print(f"  include-all-attorney-demand: {n_atty} attorney_demand "
                  f"row(s) in sample")
        if extra_dumps:
            print(f"  extra-dumps: {', '.join(str(p) for p in extra_dumps)}")
        print(f"  sorter={args.prompt_version} model={args.model}")
        print(f"  predicted fields: doc_type, doc_subclass, sentiment_label, "
              f"sentiment_score")
        print(f"  GT fields: expected, expected_subclass, sentiment_label, "
              f"sentiment_score")
        print(f"  braintrust_logging={'enabled' if bt_enabled else 'disabled'} "
              f"max_input_chars={args.max_input_chars}")
        print(f"  reserved production name: {RESERVED_EXPERIMENT_NAME}")
        return 0

    tracer, tracing_backend, tracing_meta = resolve_tracer(
        session_id=experiment_name,
        trace_name=args.lf_trace_name,
        tags=[f"prompt:{args.prompt_version}", args.model.split("/")[-1],
              "task:correspondence"],
        lf_project=args.lf_project,
        lf_environment=args.lf_environment,
    )

    manifest = None
    if args.manifest:
        manifest = ManifestStore(args.manifest, {
            "experiment_name": experiment_name,
            "hf_repo": args.hf_repo,
            "dataset_size": len(dataset),
            "dataset_fingerprint": dataset_fingerprint(dataset),
            "model": args.model,
            "prompt_version": args.prompt_version,
            "tracing_backend": "braintrust" if bt_enabled else tracing_backend,
        })
        manifest.initialize()

    if bt_enabled:
        setup_langchain(api_key=os.environ.get("BRAINTRUST_API_KEY") or _CONFIG.api_key,
                        project_id=args.project_id, project_name=args.project)
        print(f"Braintrust experiment logging ENABLED — traces -> "
              f"project '{args.project}' experiment '{experiment_name}'")
    else:
        print("Braintrust experiment logging DISABLED — results sink to the "
              "repo experiment log"
              + (" and LangSmith" if langsmith_enabled() else "")
              + f"; tracing_backend={tracing_backend}")

    usage_by_index: dict[int, dict] = {}

    def classify(input_data: dict) -> dict:
        """Classify ONE correspondence row (one sorter call)."""
        filename = input_data["filename"]
        expected_doc_type = input_data["expected"]
        expected_subclass = input_data.get("expected_subclass")
        expected_sent_label = input_data.get("expected_sentiment_label")
        expected_sent_score = input_data.get("expected_sentiment_score")

        if manifest:
            cached = manifest.get_completed(filename)
            if cached:
                return cached.get("scores", {}).get("composite") or {
                    "sorter": {}, "error": "cached incomplete"}

        sorter = SorterAgent(
            model=args.model,
            api_key=openrouter_key,
            prompt_version=args.prompt_version,
            doc_classes=DOCCLASS_CLASSES,
            schema=CORRESPONDENCE_EVAL_SCHEMA,
        )
        sorter._max_input_chars = args.max_input_chars
        sorter._max_tokens = args.max_tokens
        sorter._reasoning_effort = args.reasoning_effort

        try:
            result = sorter.classify_json(
                input_data["doc_text"], correspondence_focus=True)
        except Exception as exc:  # noqa: BLE001
            result = {
                "doc_type": CORRESPONDENCE_DOC_TYPE,
                "contract_subtype": None,
                "doc_subclass": None,
                "sentiment_score": None,
                "sentiment_label": None,
                "confidence": 0.0,
                "reasoning": f"error: {exc}",
            }
        usage_by_index[input_data["index"]] = sorter._last_usage or {}

        doc_type = str(result.get("doc_type") or CORRESPONDENCE_DOC_TYPE).strip().lower()
        doc_type_ok = doc_type == expected_doc_type
        predicted_subclass = normalize_doc_subclass(
            result.get("doc_subclass"), doc_type)
        expected_subclass_canon = normalize_doc_subclass(
            expected_subclass, expected_doc_type)
        subclass_ok = (
            predicted_subclass == expected_subclass_canon
            if expected_subclass else None
        )
        subclass_ok_equiv = (
            doc_type_ok and expected_subclass_canon is not None
            and equivalent_doc_subclasses(
                predicted_subclass, expected_subclass_canon, doc_type)
        ) if expected_subclass else None
        exact = doc_type_ok and (subclass_ok if expected_subclass else True)
        sent = score_sentiment(
            result.get("sentiment_score"), result.get("sentiment_label"),
            expected_sent_score, expected_sent_label,
        )
        correspondence_exact = bool(
            exact and sent.get("sentiment_label_ok")
        )
        try:
            confidence = float(result.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        composite = {
            "sorter": {
                "doc_type": doc_type,
                "doc_subclass": predicted_subclass,
                "expected_doc_type": expected_doc_type,
                "expected_subclass": expected_subclass,
                "expected_subclass_canon": expected_subclass_canon,
                "confidence": confidence,
                "reasoning": _reasoning_span(result, failed=not correspondence_exact),
                "doc_type_ok": doc_type_ok,
                "subclass_ok": subclass_ok,
                "subclass_ok_equiv": subclass_ok_equiv,
                "exact_match": exact,
                "sentiment_label": sent["sentiment_label"],
                "expected_sentiment_label": sent["expected_sentiment_label"],
                "sentiment_score": sent["sentiment_score"],
                "expected_sentiment_score": sent["expected_sentiment_score"],
                "sentiment_label_ok": sent["sentiment_label_ok"],
                "sentiment_score_ok": sent["sentiment_score_ok"],
                "sentiment_score_mae": sent["sentiment_score_mae"],
                "correspondence_exact": correspondence_exact,
                "failure_mode": classify_failure(
                    doc_type_ok, subclass_ok, predicted_subclass),
                "truncated": sorter._last_truncated,
            },
        }
        if manifest:
            manifest.append({
                "filename": filename,
                "status": "completed",
                "tag": "OK",
                "predicted": {
                    "doc_type": doc_type,
                    "doc_subclass": predicted_subclass,
                    "sentiment_label": sent["sentiment_label"],
                    "sentiment_score": sent["sentiment_score"],
                },
                "expected": {
                    "expected": expected_doc_type,
                    "expected_subclass": expected_subclass,
                    "sentiment_label": expected_sent_label,
                    "sentiment_score": expected_sent_score,
                },
                "error": "",
                "scores": {"composite": composite},
            })
        if bt_enabled:
            try:
                braintrust.current_span().log(metadata={
                    "filename": filename,
                    "sorter": composite["sorter"],
                    "composite": composite,
                })
            except Exception:  # noqa: BLE001 — span may be absent on local path
                pass
        return composite

    def sorter_doc_type(output: dict, expected) -> float:
        return 1.0 if ((output or {}).get("sorter") or {}).get("doc_type_ok") else 0.0

    def sorter_subclass(output: dict, expected) -> float:
        return 1.0 if ((output or {}).get("sorter") or {}).get("subclass_ok") else 0.0

    def _report_eval(evaluator, result, verbose, jsonl):
        failures = [r for r in result.results if r.error]
        for failure_ in failures:
            print(f"ERROR {failure_.input['filename']}: {failure_.error}", file=sys.stderr)
        return not failures

    def _report_run(results, verbose, jsonl):
        return all(results)

    rows_for_eval = [
        {
            "input": {
                "index": i,
                "filename": d["filename"],
                "expected": d["expected"],
                "doc_text": d["doc_text"],
                "expected_subclass": d.get("expected_subclass"),
                "expected_sentiment_label": d.get("sentiment_label"),
                "expected_sentiment_score": d.get("sentiment_score"),
            },
            "expected": {
                "doc_type": d["expected"],
                "expected_subclass": d.get("expected_subclass"),
                "sentiment_label": d.get("sentiment_label"),
                "sentiment_score": d.get("sentiment_score"),
            },
            "filename": d["filename"],
        }
        for i, d in enumerate(dataset)
    ]

    if bt_enabled:
        result = braintrust.Eval(
            args.project,
            data=lambda: rows_for_eval,
            task=classify,
            # Braintrust live scorers: doc_type + subclass only (human
            # directive 2026-08-30). Sentiment / exact / confidence stay
            # post-hoc in the experiment-log record + report_generator.
            scores=[
                sorter_doc_type,
                sorter_subclass,
            ],
            max_concurrency=args.max_concurrency,
            reporter=braintrust.Reporter(
                "correspondence-classification",
                report_eval=_report_eval, report_run=_report_run),
            project_id=args.project_id,
            experiment_name=experiment_name,
            metadata={
                "sorter_prompt": args.prompt_version,
                "model": args.model,
                "task": "correspondence_classification",
                "hf_repo": args.hf_repo,
                "dataset_size": len(dataset),
                "dataset_fingerprint": dataset_fingerprint(dataset),
                "stratified": args.stratified,
                "seed": args.seed,
                "include_all_attorney_demand": args.include_all_attorney_demand,
                "extra_dumps": [str(p) for p in extra_dumps],
                "ground_truth": "expected + expected_subclass + sentiment_label + sentiment_score",
                "braintrust_scorers": ["sorter_doc_type", "sorter_subclass"],
            },
            description=(
                f"{args.model} | {args.prompt_version} | Enron correspondence "
                f"| {len(dataset)} emails | subclass + sentiment"
            ),
        )
    else:
        result = run_local_eval(classify, rows_for_eval, args.max_concurrency)

    tracer.flush()
    tracer.shutdown()
    log_experiment_to_repo(
        result, dataset, args, experiment_name,
        usage_by_index, log_path, md_log_path,
        tracing_backend="braintrust" if bt_enabled else tracing_backend,
        tracing_meta=tracing_meta,
    )
    if bt_enabled:
        braintrust.flush()
    print(f"\nExperiment logged to {log_path}")
    return 0


def log_experiment_to_repo(result, dataset, args, experiment_name,
                           usage, log_path, md_log_path,
                           tracing_backend: str = "braintrust",
                           tracing_meta: dict | None = None) -> None:
    """Append ONE experiment-log record for the correspondence run."""
    from statistics import mean

    from src.bootstrap import bootstrap_ci
    from src.experiment_log import append_experiment, append_markdown, git_snapshot, tokens_summary
    from src.score_emitter import build_emitter, emit_docclass_run_scores

    rows = [r for r in result.results if r.error is None and isinstance(r.output, dict)]
    ok = [r.output for r in rows if isinstance(r.output, dict)]

    def _mean(key: str) -> float | None:
        values = [float((o.get("sorter") or {}).get(key))
                  for o in ok if (o.get("sorter") or {}).get(key) is not None]
        return round(mean(values), 4) if values else None

    def _ci(key: str) -> dict | None:
        values = [float((o.get("sorter") or {}).get(key))
                  for o in ok if (o.get("sorter") or {}).get(key) is not None]
        return bootstrap_ci(values)

    per_subclass: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    per_sentiment: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    subclass_confusion: dict[str, Counter] = defaultdict(Counter)
    sentiment_confusion: dict[str, Counter] = defaultdict(Counter)
    failure_insights = []
    mode_counts: Counter = Counter()
    per_row = []
    maes: list[float] = []

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
        if r.error is not None:
            continue
        if expected_subclass:
            predicted = sorter.get("doc_subclass") or DOC_SUBCLASS_UNKNOWN
            subclass_confusion[expected_subclass][predicted] += 1
            per_subclass[expected_subclass]["total"] += 1
            if sorter.get("subclass_ok"):
                per_subclass[expected_subclass]["correct"] += 1
        exp_sent = sorter.get("expected_sentiment_label")
        if exp_sent:
            pred_sent = sorter.get("sentiment_label") or "unknown"
            sentiment_confusion[exp_sent][pred_sent] += 1
            per_sentiment[exp_sent]["total"] += 1
            if sorter.get("sentiment_label_ok"):
                per_sentiment[exp_sent]["correct"] += 1
        if sorter.get("sentiment_score_mae") is not None:
            maes.append(float(sorter["sentiment_score_mae"]))
        if not sorter.get("correspondence_exact"):
            mode = sorter.get("failure_mode") or "unknown"
            if sorter.get("exact_match") and not sorter.get("sentiment_label_ok"):
                mode = "sentiment_miss"
            mode_counts[mode] += 1
            failure_insights.append({
                "filename": filename,
                "expected": {
                    "doc_type": expected_doc_type,
                    "doc_subclass": expected_subclass,
                    "sentiment_label": sorter.get("expected_sentiment_label"),
                    "sentiment_score": sorter.get("expected_sentiment_score"),
                },
                "predicted": {
                    "doc_type": sorter.get("doc_type"),
                    "doc_subclass": sorter.get("doc_subclass"),
                    "sentiment_label": sorter.get("sentiment_label"),
                    "sentiment_score": sorter.get("sentiment_score"),
                },
                "failure_mode": mode,
                "reasoning": sorter.get("reasoning"),
            })

    scores = {
        "doc_type_accuracy": _mean("doc_type_ok"),
        "doc_type_accuracy_ci": _ci("doc_type_ok"),
        "subclass_accuracy": _mean("subclass_ok"),
        "subclass_accuracy_ci": _ci("subclass_ok"),
        "subclass_accuracy_equiv": _mean("subclass_ok_equiv"),
        "exact_match": _mean("exact_match"),
        "exact_match_ci": _ci("exact_match"),
        "sentiment_label_accuracy": _mean("sentiment_label_ok"),
        "sentiment_label_accuracy_ci": _ci("sentiment_label_ok"),
        "sentiment_score_ok": _mean("sentiment_score_ok"),
        "sentiment_score_mae": round(mean(maes), 4) if maes else None,
        "sentiment_score_band": SENTIMENT_SCORE_BAND,
        "correspondence_exact": _mean("correspondence_exact"),
        "correspondence_exact_ci": _ci("correspondence_exact"),
        "confidence": _mean("confidence"),
        "n_rows": len(rows),
        "n_errors": len(result.results) - len(rows),
        "per_subclass_accuracy": {
            k: round(v["correct"] / v["total"], 4) if v["total"] else None
            for k, v in sorted(per_subclass.items())
        },
        "per_subclass_support": {k: v["total"] for k, v in sorted(per_subclass.items())},
        "per_sentiment_accuracy": {
            k: round(v["correct"] / v["total"], 4) if v["total"] else None
            for k, v in sorted(per_sentiment.items())
        },
        "per_sentiment_support": {k: v["total"] for k, v in sorted(per_sentiment.items())},
        "subclass_confusion": {k: dict(v) for k, v in sorted(subclass_confusion.items())},
        "sentiment_confusion": {k: dict(v) for k, v in sorted(sentiment_confusion.items())},
        "sorter": {
            "failure_insights": {
                "mode_counts": dict(mode_counts),
                "n_failed": len(failure_insights),
                "failures": failure_insights[:200],
            },
        },
    }

    emitter = build_emitter()
    emit_docclass_run_scores(emitter, experiment_name, scores)

    record = {
        "type": "experiment",
        "experiment_name": experiment_name,
        "task": "correspondence_classification",
        "model": args.model,
        "prompt_versions": {"sorter": args.prompt_version},
        "data_source": {
            "hf_repo": args.hf_repo,
            "ground_truth": "expected + expected_subclass + sentiment_label + sentiment_score",
            "ground_truth_mode": "enron_correspondence_dedup_gt_join",
            "dataset_fingerprint": dataset_fingerprint(dataset),
            "n_samples": len(dataset),
            "sample_requested": args.sample,
            "stratified": args.stratified,
            "limit": args.limit,
            "seed": args.seed,
            "split": args.split,
            "include_all_attorney_demand": args.include_all_attorney_demand,
            "extra_dumps": [str(p) for p in getattr(args, "extra_dump_paths", [])],
            "filename_manifest": str(args.filename_manifest or ""),
        },
        "parameters": {
            "hf_repo": args.hf_repo,
            "split": args.split,
            "sample": args.sample,
            "stratified": args.stratified,
            "seed": args.seed,
            "include_all_attorney_demand": args.include_all_attorney_demand,
            "max_input_chars": args.max_input_chars,
            "max_tokens": args.max_tokens,
            "reasoning_effort": args.reasoning_effort,
            "temperature": args.temperature,
            "max_concurrency": args.max_concurrency,
            "braintrust_logging": args.braintrust_logging,
            "tracing_backend": tracing_backend,
            "tracing_meta": tracing_meta or {},
            "sentiment_score_band": SENTIMENT_SCORE_BAND,
        },
        "scores": scores,
        "per_row": per_row,
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
