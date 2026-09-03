#!/usr/bin/env python3
"""SORTER-ONLY evaluation: contract subtype (subclass) classification.

Each row is ONE contract PDF (full text from the Braintrust dataset). The
sorter classifies it EXACTLY ONCE (``SorterAgent.classify_json`` — one LLM
call per PDF) into the 25 CUAD contract families plus "other". The expected
subtype is the contract's CUAD folder (``metadata.category``, e.g.
"License_Agreements"), normalized to the canonical key (``license``) — the
same ground truth the chained eval uses for ``subtype_accuracy``.

This isolates the sorter's subtype signal from the extraction pipeline: no
specialist, no handoff context — just 50 PDFs, one classification each, scored
for doc_type accuracy, exact subtype accuracy, mean confidence, and a
per-subtype breakdown with an expected x predicted confusion matrix.

Scores registered on the Braintrust experiment:
  sorter_exact_match       (doc_type == contract)
  sorter_subtype_accuracy  (normalized subtype == expected subtype)
  sorter_confidence        (the model's reported confidence)

The composite output carries the full sorter result per row; every scorer is
a trivial local lookup. A JSONL manifest checkpoints completed rows and the
repo experiment log is updated automatically.

Usage:
    python scripts/eval/run_subtype_eval.py --dry-run
    python scripts/eval/run_subtype_eval.py                    # all 50 contracts
    python scripts/eval/run_subtype_eval.py --sample 10 --seed 42
    python scripts/eval/run_subtype_eval.py --sorter-prompt-version sorter_v3
    python scripts/eval/run_subtype_eval.py --manifest data/manifests/subtype_50.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from braintrust.integrations.langchain import setup_langchain  # noqa: E402

import braintrust  # noqa: E402

from agents.sorter_agent import (  # noqa: E402
    SUBTYPE_UNKNOWN,
    SorterAgent,
    equivalent_subtypes,
    normalize_subtype,
)
from src.braintrust_config import load_braintrust_config  # noqa: E402
from src.braintrust_logging import (  # noqa: E402
    braintrust_logging_enabled,
    langsmith_enabled,
)
from src.braintrust_utils import load_braintrust_dataset  # noqa: E402
from src.env_utils import (  # noqa: E402
    add_research_funding_flag,
    assert_production_run,
    require_env,
    resolve_openrouter_key,
)
from src.evaluation import ManifestStore, dataset_fingerprint, utc_now, validate_dataset  # noqa: E402
from src.eval_shims import run_local_eval  # noqa: E402
from src.experiment_log import (  # noqa: E402
    append_experiment,
    append_markdown,
    default_jsonl_path,
    default_md_path,
    git_snapshot,
    mean,
    tokens_summary,
)
from src.prompts import list_prompts  # noqa: E402
from src.serving_meta import (  # noqa: E402
    build_serving_block,
    call_latency_stats,
)

_CONFIG = load_braintrust_config()
DEFAULT_DATASET = "mailroom-cuad-contracts"


def stratified_sample(dataset: list[dict], n: int, seed: int) -> list[dict]:
    """Sample ``n`` rows EVENLY distributed across the expected subtypes.

    Every subtype with any rows is guaranteed at least one slot when
    ``n >= num_subtypes``; the remaining budget is split as evenly as possible
    with the surplus going to the largest classes. Within each class the pick
    is seeded-random for representativeness.

    Returns the sampled rows (possibly fewer than ``n`` when some classes are
    too small to fill their allocation).
    """
    if n > len(dataset):
        raise ValueError(f"stratified sample {n} exceeds dataset size {len(dataset)}")
    groups: dict[str, list[dict]] = defaultdict(list)
    for d in dataset:
        groups[d["expected_subtype"]].append(d)
    rng = random.Random(seed)
    selected: list[dict] = []
    remaining = n
    if remaining >= len(groups):
        # Guarantee every subtype at least one row.
        for key in sorted(groups):
            pick = rng.choice(groups[key])
            groups[key].remove(pick)
            selected.append(pick)
            remaining -= 1
    base, rem = divmod(remaining, max(1, len(groups)))
    order = sorted(groups, key=lambda k: len(groups[k]), reverse=True)
    for i, key in enumerate(order):
        alloc = base + (1 if i < rem else 0)
        pool = groups[key]
        if pool:
            selected.extend(rng.sample(pool, min(alloc, len(pool))))
    return selected


# classify_failure comes from the llm-dojo-scoring package (failure-mode
# taxonomy is package-owned now; the local contract — a failed-row sorter dict
# → insight-relevant mode — is preserved; callers guard ``subtype_ok`` first).
from llm_dojo_scoring.failure_modes import classify_failure  # noqa: E402


def _reasoning_span(result: dict, *, failed: bool) -> str:
    """Keep the model's full classification reasoning on FAILED rows (the
    insight-bearing ones) and a bounded excerpt on successes."""
    reasoning = str(result.get("reasoning") or "")
    return reasoning[:4000] if failed else reasoning[:500]


def main() -> int:
    return main_with_args(sys.argv[1:])


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=_CONFIG.project_name, help="Braintrust project name")
    parser.add_argument("--project-id", default=_CONFIG.project_id, help="Braintrust project id")
    parser.add_argument("--dataset-project", default=_CONFIG.dataset_project, help="Project holding the dataset")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Braintrust dataset to evaluate")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N contracts")
    parser.add_argument("--sample", type=int, default=0, help="Random sample of N contracts")
    parser.add_argument("--stratified", type=int, default=0,
                        help="STRATIFIED sample of N contracts: evenly distributed across every "
                             "expected subtype (each class gets floor(N/classes) with the "
                             "surplus to the largest classes; every class represented when "
                             "N >= class count). Takes precedence over --sample/--limit.")
    parser.add_argument("--seed", type=int, default=42, help="Seed for --sample/--stratified")
    parser.add_argument("--model", default=_CONFIG.model, help=f"Model (default: {_CONFIG.model})")
    parser.add_argument("--sorter-prompt-version", default="sorter_v3",
                        help="Sorter prompt version (classifies doc_type + contract_subtype)")
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=4096,
                        help="Max output tokens for the sorter's classification call")
    parser.add_argument("--reasoning-effort", default="medium",
                        help="Reasoning effort for the classification call "
                             "(default: medium — the sorter must weigh operative "
                             "clauses across 25 near-synonymous families)")
    parser.add_argument("--max-input-chars", type=int, default=100_000,
                        help="Hard safety cap on document text fed to the sorter "
                             "(head+tail window when exceeded)")
    parser.add_argument("--max-concurrency", type=int, default=4, help="Concurrent API calls")
    parser.add_argument("--experiment-name", default=None,
                        help="Experiment name (default: {model-slug}_{prompt-version}_subtype)")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="JSONL checkpoint manifest for resuming an interrupted run")
    parser.add_argument("--bt-scores", choices=("none", "overall", "full"), default="overall",
                        help="Braintrust scorer registration (default: the sorter tracker set)")
    parser.add_argument("--experiment-log", type=Path, default=None,
                        help="JSONL experiment log path (default: $EXPERIMENT_LOG_PATH)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Resolve config, load dataset, print the plan without running")
    add_research_funding_flag(parser)
    args = parser.parse_args(argv)

    openrouter_key = resolve_openrouter_key(args.research_funding_key)
    (braintrust_key,) = require_env("BRAINTRUST_API_KEY")
    bt_enabled = braintrust_logging_enabled()

    available = list_prompts()
    if args.sorter_prompt_version not in available:
        parser.error(f"Unknown prompt version {args.sorter_prompt_version!r}. Available: {available}")

    experiment_name = args.experiment_name or (
        f"{args.model.split('/')[-1]}_{args.sorter_prompt_version}_subtype"
    )

    dataset = load_braintrust_dataset(args.dataset_project, args.dataset,
                                      project_id=_CONFIG.project_id)
    total_rows = len(dataset)
    for d in dataset:
        d["expected_subtype"] = normalize_subtype((d.get("metadata") or {}).get("category"))
    if args.stratified:
        dataset = stratified_sample(dataset, args.stratified, args.seed)
        print(f"Stratified {len(dataset)} contracts evenly across subtypes "
              f"(requested {args.stratified}, seed {args.seed})")
    elif args.sample:
        dataset = random.Random(args.seed).sample(dataset, min(args.sample, len(dataset)))
    elif args.limit:
        dataset = dataset[: args.limit]
    if not dataset:
        parser.error("No contracts found in the dataset.")
    assert_production_run(args.research_funding_key, dry_run=args.dry_run,
                          selected_rows=len(dataset), total_rows=total_rows)

    # Expected subtype = the contract's CUAD folder (metadata.category),
    # normalized to the canonical subtype key.
    for d in dataset:
        d["expected_subtype"] = normalize_subtype((d.get("metadata") or {}).get("category"))
    unknown = [d for d in dataset if d["expected_subtype"] == SUBTYPE_UNKNOWN]
    if unknown:
        print(f"WARNING: {len(unknown)} rows have unnormalized CUAD folders:", file=sys.stderr)
        for d in unknown[:5]:
            print(f"  {(d.get('metadata') or {}).get('category')!r}", file=sys.stderr)
    validate_dataset(dataset)

    by_subtype = Counter(d["expected_subtype"] for d in dataset)
    print(f"{len(dataset)} contracts across {len(by_subtype)} subtypes:")
    print(f"  {dict(by_subtype)}")

    log_path = args.experiment_log or default_jsonl_path()
    md_log_path = default_md_path()

    manifest = None
    if args.manifest:
        manifest = ManifestStore(args.manifest, {
            "experiment_name": experiment_name,
            "dataset": args.dataset,
            "dataset_size": len(dataset),
            "dataset_fingerprint": dataset_fingerprint(dataset),
            "model": args.model,
            "sorter_prompt_version": args.sorter_prompt_version,
        })
        manifest.initialize()

    if args.dry_run:
        how = (f"stratified {args.stratified} (even across subtypes, seed {args.seed})"
               if args.stratified else
               f"sample {args.sample} (seed {args.seed})" if args.sample else
               f"limit {args.limit}" if args.limit else "all")
        print(f"Dry run: {len(dataset)} contracts ({how}) -> experiment '{experiment_name}'")
        print(f"  sorter={args.sorter_prompt_version} model={args.model}")
        return 0

    if bt_enabled:
        setup_langchain(api_key=braintrust_key, project_id=args.project_id, project_name=args.project)
    else:
        print("Braintrust experiment logging DISABLED (BRAINTRUST_LOGGING=disabled) — "
              "results sink to the repo experiment log"
              + (" and LangSmith (LANGSMITH_TRACING=true)" if langsmith_enabled() else "")
              + "; use the run_langfuse_*_eval.py runner for Langfuse traces.")

    # Run-window clock for the record's serving.timing block (KANBAN-106).
    started_at = utc_now()
    run_started_monotonic = time.monotonic()

    usage_by_index: dict[int, dict] = {}
    elapsed_by_index: dict[int, float] = {}

    @braintrust.traced
    def classify(input_data: dict) -> dict:
        """Classify ONE PDF's contract subtype (exactly one sorter call)."""
        filename = input_data["filename"]
        expected_subtype = input_data["expected_subtype"]

        if manifest:
            cached = manifest.get_completed(filename)
            if cached:
                braintrust.current_span().log(metadata={"cached": True, "filename": filename})
                return cached.get("scores", {}).get("composite") or {
                    "sorter": {}, "error": "cached incomplete"}

        sorter = SorterAgent(model=args.model, api_key=openrouter_key,
                             prompt_version=args.sorter_prompt_version)
        sorter._max_input_chars = args.max_input_chars
        sorter._max_tokens = args.max_tokens
        sorter._reasoning_effort = args.reasoning_effort
        row_started = time.monotonic()
        try:
            result = sorter.classify_json(input_data["doc_text"])
        except Exception as exc:  # noqa: BLE001 - one bad row must not abort
            result = {"doc_type": "correspondence", "contract_subtype": SUBTYPE_UNKNOWN,
                      "confidence": 0.0, "reasoning": f"error: {exc}"}
        elapsed_by_index[input_data["index"]] = time.monotonic() - row_started
        usage_by_index[input_data["index"]] = sorter._last_usage or {}

        doc_type = str(result.get("doc_type", "correspondence")).strip().lower()
        subtype = normalize_subtype(result.get("contract_subtype"))
        try:
            confidence = float(result.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        doc_type_ok = doc_type == "contract"
        subtype_ok = doc_type_ok and subtype == expected_subtype
        subtype_ok_equiv = doc_type_ok and equivalent_subtypes(subtype, expected_subtype)

        composite = {
            "sorter": {
                "doc_type": doc_type,
                "contract_subtype": subtype,
                "expected_subtype": expected_subtype,
                "confidence": confidence,
                "reasoning": _reasoning_span(result, failed=not subtype_ok),
                "doc_type_ok": doc_type_ok,
                "subtype_ok": subtype_ok,
                # Family-level correctness: the subtype may be a defensible
                # equivalent of the CUAD-folder key (e.g. reseller/distributor,
                # maintenance/license) — still a correct routing decision.
                "subtype_ok_equiv": subtype_ok_equiv,
                # Insight classification for failed rows (see classify_failure).
                "failure_mode": classify_failure({
                    "doc_type_ok": doc_type_ok,
                    "contract_subtype": subtype,
                    "subtype_ok_equiv": subtype_ok_equiv,
                }) if not subtype_ok else None,
                "truncated": sorter._last_truncated,
            },
        }

        span_meta = {
            "filename": filename,
            "sorter": composite["sorter"],
            "composite": composite,
            "sorter_usage": sorter._last_usage or {},
        }
        if manifest:
            manifest.append({"filename": filename, "status": "completed", "tag": "OK",
                             "predicted": {"doc_type": doc_type,
                                           "contract_subtype": subtype},
                             "error": "",
                             "expected_subtype": expected_subtype,
                             "scores": span_meta})

        braintrust.current_span().log(metadata=span_meta)
        return composite

    # ------------------------------------------------------------------
    # Braintrust scorers — trivial lookups on the composite
    # ------------------------------------------------------------------

    def sorter_exact_match(output: dict, expected) -> float:
        """SORTER: did the sorter classify the document as contract?"""
        return 1.0 if ((output or {}).get("sorter") or {}).get("doc_type_ok") else 0.0

    def sorter_subtype_accuracy(output: dict, expected) -> float:
        """SORTER: did the contract_subtype EXACTLY match the document's CUAD type?"""
        return 1.0 if ((output or {}).get("sorter") or {}).get("subtype_ok") else 0.0

    def sorter_subtype_accuracy_equiv(output: dict, expected) -> float:
        """SORTER: family-level correctness — exact match OR a defensible
        equivalent of the CUAD type (reseller/distributor, maintenance/
        license, development/license, affiliate/joint_venture)."""
        return 1.0 if ((output or {}).get("sorter") or {}).get("subtype_ok_equiv") else 0.0

    def sorter_confidence(output: dict, expected) -> float:
        """SORTER: the model's classification confidence."""
        return float(((output or {}).get("sorter") or {}).get("confidence") or 0.0)

    if args.bt_scores == "none":
        bt_scorers = []
    elif args.bt_scores == "overall":
        bt_scorers = [sorter_exact_match, sorter_subtype_accuracy,
                      sorter_subtype_accuracy_equiv, sorter_confidence]
    else:
        bt_scorers = [sorter_exact_match, sorter_subtype_accuracy,
                      sorter_subtype_accuracy_equiv, sorter_confidence]

    def _report_eval(evaluator, result, verbose, jsonl):
        failures = [r for r in result.results if r.error]
        for failure_ in failures:
            print(f"ERROR {failure_.input['filename']}: {failure_.error}", file=sys.stderr)
        return not failures

    def _report_run(results, verbose, jsonl):
        return all(results)

    if bt_enabled:
        result = braintrust.Eval(
            args.project,
            data=lambda: [
                {"input": {"index": i, "filename": d["filename"], "expected": d["expected"],
                           "doc_text": d["doc_text"], "expected_subtype": d["expected_subtype"]},
                 "expected": {"doc_type": d["expected"],
                              "expected_subtype": d["expected_subtype"]},
                 "filename": d["filename"]}
                for i, d in enumerate(dataset)
            ],
            task=classify,
            scores=bt_scorers,
            max_concurrency=args.max_concurrency,
            reporter=braintrust.Reporter("subtype-classification",
                                         report_eval=_report_eval, report_run=_report_run),
            project_id=args.project_id,
            experiment_name=experiment_name,
            metadata={
                "sorter_prompt": args.sorter_prompt_version,
                "model": args.model,
                "reasoning_effort": args.reasoning_effort,
                "max_input_chars": args.max_input_chars,
                "task": "subtype_classification",
                "ground_truth": "cuad_folder",
                "ground_truth_mode": "cuad_type_aware",
                "dataset": f"{args.dataset_project}/{args.dataset}",
                "dataset_size": len(dataset),
                "dataset_fingerprint": dataset_fingerprint(dataset),
                "bt_scores": args.bt_scores,
            },
            description=(f"{args.model} | sorter {args.sorter_prompt_version} | "
                         f"contract subtype only | {len(dataset)} PDFs"),
        )
    else:
        rows = [
            {"input": {"index": i, "filename": d["filename"], "expected": d["expected"],
                       "doc_text": d["doc_text"], "expected_subtype": d["expected_subtype"]},
             "expected": {"doc_type": d["expected"],
                          "expected_subtype": d["expected_subtype"]},
             "filename": d["filename"]}
            for i, d in enumerate(dataset)
        ]
        result = run_local_eval(classify, rows, args.max_concurrency)

    log_experiment_to_repo(result, dataset, args, experiment_name,
                           usage_by_index, log_path, md_log_path,
                           tracing_backend="braintrust" if bt_enabled else "none",
                           tracing_meta=None if bt_enabled else {
                               "braintrust_logging": False,
                               "langsmith": langsmith_enabled(),
                               "hint": "run_langfuse_*_eval.py for Langfuse traces",
                           },
                           started_at=started_at,
                           run_duration_s=time.monotonic() - run_started_monotonic,
                           elapsed_by_index=elapsed_by_index)
    if bt_enabled:
        braintrust.flush()
    return 0


def log_experiment_to_repo(result, dataset, args, experiment_name,
                           usage, log_path, md_log_path,
                           tracing_backend: str = "braintrust",
                           tracing_meta: dict | None = None,
                           *, started_at: str | None = None,
                           run_duration_s: float | None = None,
                           elapsed_by_index: dict | None = None) -> None:
    """Append ONE experiment-log record for the subtype-only run.

    ``tracing_backend`` names where the run was traced (``braintrust`` default,
    ``langfuse`` for the mirror runner); ``tracing_meta`` carries backend
    specifics (project/environment) into the record's parameters.

    ``started_at`` / ``run_duration_s`` / ``elapsed_by_index`` feed the
    record's ``serving.timing`` block (KANBAN-106): the wall-clock run window
    plus per-call latencies for the cost-comparison lens (OpenRouter vs a
    Modal-hosted vLLM Qwen3-8B deployment).
    """
    rows = [r for r in result.results if r.error is None and isinstance(r.output, dict)]
    ok = [r.output for r in rows if isinstance(r.output, dict)]

    def _mean(key: str) -> float | None:
        values = [float((o.get("sorter") or {}).get(key))
                  for o in ok if (o.get("sorter") or {}).get(key) is not None]
        return round(mean(values), 4) if values else None

    expected_by_filename = {d["filename"]: d["expected_subtype"] for d in dataset}
    per_subtype: dict[str, dict] = defaultdict(lambda: {"correct": 0, "equiv": 0, "total": 0})
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        filename = r.input.get("filename") if isinstance(r.input, dict) else ""
        expected = expected_by_filename.get(filename, "?")
        sorter = (r.output or {}).get("sorter") or {}
        predicted = sorter.get("contract_subtype") or SUBTYPE_UNKNOWN
        per_subtype[expected]["total"] += 1
        if sorter.get("subtype_ok"):
            per_subtype[expected]["correct"] += 1
        if sorter.get("subtype_ok_equiv"):
            per_subtype[expected]["equiv"] += 1
        confusion[expected][predicted] += 1

    def _bootstrap_ci(values):
        from src.bootstrap import bootstrap_ci as _bci
        return _bci(values)

    per_row = []
    for r in result.results:
        output = r.output if isinstance(r.output, dict) else {}
        index = r.input.get("index", -1) if isinstance(r.input, dict) else -1
        per_row.append({
            "filename": r.input.get("filename") if isinstance(r.input, dict) else "",
            "status": "error" if r.error is not None else "completed",
            "error": r.error,
            "sorter": (output.get("sorter") or {}),
            "sorter_tokens": usage.get(index) or {},
        })

    # Failure insights: every failed row with its full reasoning, failure
    # mode, equivalence status, and the aggregate mode distribution — the
    # model's own explanation of why it picked what it picked.
    failures = []
    mode_counts: dict[str, int] = defaultdict(int)
    for row in per_row:
        sorter = row.get("sorter") or {}
        if sorter.get("subtype_ok"):
            continue
        mode = sorter.get("failure_mode") or "family_confusion"
        mode_counts[mode] += 1
        failures.append({
            "filename": row["filename"],
            "expected": sorter.get("expected_subtype"),
            "predicted": sorter.get("contract_subtype"),
            "doc_type": sorter.get("doc_type"),
            "confidence": sorter.get("confidence"),
            "mode": mode,
            "equiv_recovered": bool(sorter.get("subtype_ok_equiv")),
            "reasoning": sorter.get("reasoning") or "",
        })

    _tokens = tokens_summary(list(usage.values()), model=args.model)

    record = {
        "type": "experiment",
        "task": "subtype_classification",
        "experiment_name": experiment_name,
        "git": git_snapshot(),
        "model": args.model,
        "prompt_versions": {"sorter": args.sorter_prompt_version},
        "serving": build_serving_block(
            model=args.model,
            prompt_versions={"sorter": args.sorter_prompt_version},
            dataset_fingerprint=dataset_fingerprint(dataset),
            tokens=_tokens,
            started_at=started_at,
            finished_at=utc_now() if started_at else None,
            duration_s=run_duration_s,
            call_latency=call_latency_stats(elapsed_by_index),
        ),
        "data_source": {
            "project": f"{args.dataset_project}/{args.dataset}",
            "ground_truth": "cuad_folder",
            "ground_truth_mode": "cuad_type_aware",
            "dataset_fingerprint": dataset_fingerprint(dataset),
            "n_samples": len(dataset),
            "sample_requested": args.sample,
            "stratified": args.stratified,
            "limit": args.limit,
            "seed": args.seed,
        },
        "parameters": {
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "reasoning_effort": args.reasoning_effort,
            "max_input_chars": args.max_input_chars,
            "max_concurrency": args.max_concurrency,
            "bt_scores": getattr(args, "bt_scores", "none"),
            "manifest": str(args.manifest) if args.manifest else None,
            "tracing_backend": tracing_backend,
            **({"tracing": tracing_meta} if tracing_meta else {}),
        },
        "tokens": {"sorter": _tokens, "total": _tokens},
        "scores": {
            "sorter": {
                "exact_match": _mean("doc_type_ok"),
                "exact_match_ci": _bootstrap_ci([(o.get("sorter") or {}).get("doc_type_ok") for o in ok]),
                "subtype_accuracy": _mean("subtype_ok"),
                "subtype_accuracy_ci": _bootstrap_ci([(o.get("sorter") or {}).get("subtype_ok") for o in ok]),
                "subtype_accuracy_equiv": _mean("subtype_ok_equiv"),
                "confidence": _mean("confidence"),
                "equiv_recovered": [s.get("contract_subtype")
                                    for o in ok
                                    if (s := (o.get("sorter") or {}))
                                    and s.get("subtype_ok_equiv")
                                    and not s.get("subtype_ok")],
                "failure_insights": {
                    "mode_counts": dict(sorted(mode_counts.items())),
                    "n_failed": len(failures),
                    "failures": failures,
                },
                "per_subtype": {
                    k: {"accuracy": round(v["correct"] / v["total"], 4) if v["total"] else None,
                        "accuracy_equiv": round(v["equiv"] / v["total"], 4) if v["total"] else None,
                        "correct": v["correct"], "equiv": v["equiv"], "total": v["total"]}
                    for k, v in sorted(per_subtype.items())
                },
                "confusion_matrix": {k: dict(v) for k, v in sorted(confusion.items())},
            },
        },
        "n_rows": len(result.results),
        "n_ok": len(ok),
        "results": per_row,
    }
    jsonl_path = append_experiment(record, log_path)
    append_markdown(record, md_log_path)
    print(f"\nExperiment logged to {jsonl_path}")


if __name__ == "__main__":
    raise SystemExit(main())
