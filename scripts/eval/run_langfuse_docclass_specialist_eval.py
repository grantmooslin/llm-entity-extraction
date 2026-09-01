#!/usr/bin/env python3
"""LANGFUSE/PHOENIX docclass specialist extraction — contracts + insurance arms.

Runs ``ContractsSpecialist`` or ``InsuranceClaimsSpecialist`` over the
docclass-merged v5 local JSONL (``gt_fields`` from HF ground_truth config),
scores against CUAD clause labels (contracts) or insurance scalar GT
(insurance_claim rows), and appends ONE record to the repo experiment log.

Designed for same-surface A/B: pin the exact row list with
``--filename-manifest`` (export from ``run_langfuse_docclass_eval.py
--export-sample-manifest``) so every arm sees identical filenames.

Usage:
    python scripts/eval/run_langfuse_docclass_specialist_eval.py --dry-run \\
        --agent contracts_specialist \\
        --prompt-version contracts_specialist_docclass_v0 \\
        --local-dumps data/datasets/docclass_merged_v5.jsonl \\
        --filename-manifest data/manifests/docclass_ab120_s42_filenames.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.specialist_agents import ContractsSpecialist, InsuranceClaimsSpecialist  # noqa: E402
from scripts.eval.run_extraction_eval import (  # noqa: E402
    load_expected_fields,
    print_extraction_summary,
)
from scripts.eval.run_langfuse_docclass_eval import (  # noqa: E402
    filter_by_filename_manifest,
    load_docclass_dataset,
    stratified_sample,
    write_sample_manifest,
)
from src.braintrust_config import load_braintrust_config  # noqa: E402
from src.env_utils import require_env  # noqa: E402
from src.evaluation import (  # noqa: E402
    ManifestStore,
    call_with_rate_limit_retry,
    dataset_fingerprint,
    resolve_concurrency,
)
from src.experiment_log import append_experiment, append_markdown, default_jsonl_path, default_md_path  # noqa: E402
from src.field_scoring import get_field_types, score_category_presence, score_extraction  # noqa: E402
from src.metrics import extraction_diagnostics  # noqa: E402
from src.prompts import list_prompts  # noqa: E402
from src.tracing import resolve_tracer  # noqa: E402

_CONFIG = load_braintrust_config()
DEFAULT_LOCAL_DUMP = "data/datasets/docclass_merged_v5.jsonl"
CONTRACT_DOC_TYPES = frozenset({"contract", "merger_agreement"})
INSURANCE_DOC_TYPE = "insurance_claim"

INSURANCE_FIELD_KEYS = (
    "claim_number", "policy_number", "insurer", "insured_party",
    "claim_type", "date_of_loss", "date_filed", "claimed_amount",
    "adjuster", "damages_description", "coverage_determination",
    "denial_reasons", "supporting_documents",
)


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


def cuad_labels_to_clause_list(raw) -> list[dict]:
    """Convert v5 ``cuad_clause_labels`` dict to CUAD clause QA list shape."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        return []
    clauses: list[dict] = []
    for category, spans in raw.items():
        for span in spans or []:
            text = span.get("text") if isinstance(span, dict) else span
            text = str(text or "").strip()
            if text:
                clauses.append({
                    "question": f'Highlight the parts related to "{category}"',
                    "answer": text,
                })
    return clauses


def enrich_contract_rows(rows: list[dict]) -> list[dict]:
    """Attach ``expected_fields`` / ``expected_presence`` from v5 CUAD GT."""
    for row in rows:
        gf = row.get("gt_fields") or {}
        row["clause_labels"] = cuad_labels_to_clause_list(gf.get("cuad_clause_labels"))
        metadata = dict(row.get("metadata") or {})
        row["metadata"] = metadata
        if not metadata.get("category") and row.get("expected_subclass"):
            metadata["category"] = row["expected_subclass"]
    return load_expected_fields(rows)


def enrich_insurance_rows(rows: list[dict]) -> list[dict]:
    """Attach ``expected_fields`` from v5 insurance scalar GT."""
    for row in rows:
        gf = row.get("gt_fields") or {}
        expected: dict = {}
        for key in INSURANCE_FIELD_KEYS:
            val = gf.get(key)
            if val not in (None, "", []):
                expected[key] = val
        row["expected_fields"] = expected
    return rows


def select_agent_rows(dataset: list[dict], agent: str) -> list[dict]:
    """Keep rows routed to the requested specialist."""
    if agent == "contracts_specialist":
        return [d for d in dataset if d["expected"] in CONTRACT_DOC_TYPES]
    if agent == "insurance_claims_specialist":
        return [d for d in dataset if d["expected"] == INSURANCE_DOC_TYPE]
    raise ValueError(f"Unknown agent {agent!r}")


def main() -> int:
    return main_with_args(sys.argv[1:])


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True,
                        choices=["contracts_specialist", "insurance_claims_specialist"],
                        help="Which specialist to run")
    parser.add_argument("--local-dumps", default=DEFAULT_LOCAL_DUMP,
                        help=f"Local docclass-merged JSONL (default: {DEFAULT_LOCAL_DUMP})")
    parser.add_argument("--filename-manifest", type=Path, default=None,
                        help="JSONL of {filename,...} — reuse an exact prior sample")
    parser.add_argument("--export-sample-manifest", type=Path, default=None,
                        help="After sampling, write the exact row list to this JSONL")
    parser.add_argument("--stratified", type=int, default=0,
                        help="STRATIFIED sample of N rows (only when no filename manifest)")
    parser.add_argument("--sample", type=int, default=0, help="Random sample of N rows")
    parser.add_argument("--seed", type=int, default=42, help="Seed for --sample/--stratified")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N rows")
    parser.add_argument("--model", default=_CONFIG.model, help=f"Model (default: {_CONFIG.model})")
    parser.add_argument("--prompt-version", required=True,
                        help="Docclass specialist prompt version key")
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=32768, help="Max output tokens")
    parser.add_argument("--reasoning-effort", default="none",
                        help="Reasoning effort for the extraction call")
    parser.add_argument("--max-input-chars", type=int, default=150_000,
                        help="Hard safety cap on document text fed to the model")
    parser.add_argument("--chunked", action="store_true",
                        help="Chunked extraction pass (contracts arm only)")
    parser.add_argument("--chunk-chars", type=int, default=90_000)
    parser.add_argument("--chunk-overlap", type=int, default=8_000)
    parser.add_argument("--max-concurrency", type=int, default=None)
    parser.add_argument("--experiment-name", default=None)
    parser.add_argument("--manifest", type=Path,
                        default=Path("data/manifests/docclass_specialist_langfuse.jsonl"))
    parser.add_argument("--lf-project", default=None)
    parser.add_argument("--lf-environment", default=None)
    parser.add_argument("--lf-trace-name", default="docclass_specialist_extraction")
    parser.add_argument("--experiment-log", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    (openrouter_key,) = require_env("OPENROUTER_API_KEY")
    require_env("BRAINTRUST_API_KEY")

    available = list_prompts()
    if args.prompt_version not in available:
        parser.error(f"Unknown prompt version {args.prompt_version!r}. Available: {available}")

    experiment_name = args.experiment_name or (
        f"{args.model.split('/')[-1]}_{args.prompt_version}_docclass_specialist_langfuse"
    )

    local_dumps = [Path(p.strip()) for p in args.local_dumps.split(",") if p.strip()]
    print(f"Loading local dumps: {local_dumps}")
    dataset = load_docclass_dataset([], _CONFIG.dataset_project or _CONFIG.project_name,
                                    project_id=_CONFIG.project_id, local_dumps=local_dumps)

    if args.filename_manifest:
        dataset = filter_by_filename_manifest(dataset, args.filename_manifest)
        print(f"Loaded {len(dataset)} rows from filename manifest {args.filename_manifest}")
    elif args.stratified:
        dataset = stratified_sample(dataset, args.stratified, args.seed)
        print(f"Stratified {len(dataset)} rows (seed {args.seed})")
    elif args.sample:
        import random
        dataset = random.Random(args.seed).sample(dataset, min(args.sample, len(dataset)))
    elif args.limit:
        dataset = dataset[: args.limit]

    if args.export_sample_manifest:
        write_sample_manifest(dataset, args.export_sample_manifest)

    dataset = select_agent_rows(dataset, args.agent)
    if not dataset:
        parser.error(f"No rows for agent {args.agent!r} after filtering.")

    if args.agent == "contracts_specialist":
        dataset = enrich_contract_rows(dataset)
        doc_class = "contract"
        with_truth = [d for d in dataset if d.get("expected_fields")]
    else:
        dataset = enrich_insurance_rows(dataset)
        doc_class = INSURANCE_DOC_TYPE
        with_truth = [d for d in dataset if d.get("expected_fields")]

    if not with_truth:
        parser.error(f"No rows carry ground truth for agent {args.agent!r}.")

    field_types = get_field_types(doc_class)
    scored_fields = sorted({f for d in with_truth for f in d["expected_fields"]})

    log_path = args.experiment_log or default_jsonl_path()
    md_log_path = default_md_path()

    if args.dry_run:
        print(f"Dry run: {len(with_truth)}/{len(dataset)} scored rows -> '{experiment_name}'")
        print(f"  agent={args.agent} prompt={args.prompt_version} model={args.model}")
        print(f"  fields scored: {scored_fields[:12]}{'...' if len(scored_fields) > 12 else ''}")
        if args.agent == "contracts_specialist" and not args.chunked:
            print("  WARNING: --chunked off — long-contract extraction may truncate")
        return 0

    tracer, tracing_backend, tracing_meta = resolve_tracer(
        session_id=experiment_name,
        trace_name=args.lf_trace_name,
        tags=[f"agent:{args.agent}", f"prompt:{args.prompt_version}",
              args.model.split("/")[-1]],
        lf_project=args.lf_project,
        lf_environment=args.lf_environment,
    )

    manifest = None
    if args.manifest:
        manifest = ManifestStore(args.manifest, {
            "experiment_name": experiment_name,
            "agent": args.agent,
            "dataset_size": len(with_truth),
            "dataset_fingerprint": dataset_fingerprint(with_truth),
            "model": args.model,
            "prompt_version": args.prompt_version,
            "tracing_backend": tracing_backend,
        })
        manifest.initialize()

    usage_by_index: dict[int, dict] = {}
    agent_obs_name = args.agent

    def extract_one(input_data: dict) -> EvalResultShim:
        filename = input_data["filename"]
        expected_fields = input_data["expected_fields"]
        doc_text = input_data["doc_text"]

        if manifest:
            cached = manifest.get_completed(filename)
            if cached:
                return EvalResultShim(
                    input_data,
                    cached.get("scores", {}).get("composite") or {"error": "cached incomplete"},
                )

        with tracer.trace_document(
            filename, input_data["expected"],
            {"agent": args.agent, "prompt_version": args.prompt_version, "model": args.model},
        ) as trace_handle:
            with tracer.agent_observation(
                agent_obs_name,
                {"prompt_version": args.prompt_version, "model": args.model,
                 "reasoning_effort": args.reasoning_effort},
            ) as specialist_handle:
                if args.agent == "contracts_specialist":
                    specialist = ContractsSpecialist(
                        model=args.model, api_key=openrouter_key,
                        prompt_version=args.prompt_version,
                        callbacks=[specialist_handle.handler] if specialist_handle.handler else None)
                else:
                    specialist = InsuranceClaimsSpecialist(
                        model=args.model, api_key=openrouter_key,
                        prompt_version=args.prompt_version,
                        callbacks=[specialist_handle.handler] if specialist_handle.handler else None)
                specialist._max_input_chars = args.max_input_chars
                specialist._max_tokens = args.max_tokens
                specialist._reasoning_effort = args.reasoning_effort

                try:
                    if args.agent == "contracts_specialist" and args.chunked:
                        predicted = specialist.extract_chunked(
                            doc_text, args.chunk_chars, args.chunk_overlap)
                    else:
                        predicted = specialist.extract(doc_text)
                except Exception as exc:  # noqa: BLE001
                    composite = {"predicted": {}, "error": str(exc), "schema_valid": 0.0,
                                 "overall_score": 0.0, "field_presence": 0.0,
                                 "field_scores": {}, "ambiguous_fields": []}
                    if manifest:
                        manifest.append({"filename": filename, "status": "error",
                                         "predicted": {}, "error": str(exc),
                                         "expected_fields": expected_fields,
                                         "scores": {"composite": composite}})
                    return EvalResultShim(input_data, composite)

                usage_by_index[input_data["index"]] = specialist._last_usage or {}

                if predicted.get("_parse_error"):
                    composite = {"predicted": {}, "error": "parse error", "schema_valid": 0.0,
                                 "overall_score": 0.0, "field_presence": 0.0,
                                 "field_scores": {}, "ambiguous_fields": []}
                    if manifest:
                        manifest.append({"filename": filename, "status": "error",
                                         "predicted": {}, "error": "parse error",
                                         "expected_fields": expected_fields,
                                         "scores": {"composite": composite}})
                    return EvalResultShim(input_data, composite)

                result = score_extraction(doc_class, field_types, predicted, expected_fields,
                                          doc_text=doc_text)
                populated = sum(
                    1 for key, value in expected_fields.items()
                    if predicted.get(key) not in (None, "", [])
                )
                field_presence = populated / len(expected_fields) if expected_fields else 0.0
                category_presence = None
                presence_detail = None
                if args.agent == "contracts_specialist":
                    category_presence, presence_detail = score_category_presence(
                        predicted, input_data.get("expected_presence") or {}, field_types)

                composite = {
                    "predicted": predicted,
                    "overall_score": result.overall_score or 0.0,
                    "field_presence": field_presence,
                    "schema_valid": 1.0,
                    "field_scores": result.field_scores,
                    "category_presence": category_presence,
                    "category_presence_detail": presence_detail,
                    "entity_list_f1": {k: v.score for k, v in result.entity_list_scores.items()},
                    "entity_list_scores": {
                        k: {"precision": v.precision, "recall": v.recall, "f1": v.f1,
                            "matched": v.matched,
                            "n_predicted": v.matched + v.unmatched_predicted,
                            "n_expected": v.matched + v.unmatched_expected}
                        for k, v in result.entity_list_scores.items()
                    },
                    "entity_list_audit": result.entity_list_audit,
                    "overall_verified_precision": result.overall_verified_precision or 0.0,
                    "ambiguous_fields": result.ambiguous_fields,
                    "truncated": bool(specialist._last_truncated),
                    "chunked": bool(args.chunked),
                }

                specialist_handle.set_output({
                    "overall_score": composite["overall_score"],
                    "field_presence": field_presence,
                    "overall_verified_precision": composite["overall_verified_precision"],
                })
                specialist_handle.score("overall_extraction_score", composite["overall_score"])
                specialist_handle.score("field_presence", field_presence)
                specialist_handle.score("overall_verified_precision",
                                        composite["overall_verified_precision"])
                if category_presence is not None:
                    specialist_handle.score("category_presence", category_presence)

            trace_handle.set_output(composite)
            if manifest:
                manifest.append({"filename": filename, "status": "completed", "tag": "OK",
                                 "predicted": predicted, "error": "",
                                 "expected_fields": expected_fields,
                                 "scores": {"composite": composite}})

        return EvalResultShim(input_data, composite)

    rows = [
        {"index": i, "filename": d["filename"], "expected": d["expected"],
         "doc_text": d["doc_text"], "expected_fields": d["expected_fields"],
         "expected_presence": d.get("expected_presence") or {},
         "doc_category": d.get("doc_category")}
        for i, d in enumerate(with_truth)
    ]
    args.max_concurrency = resolve_concurrency(len(rows), args.max_concurrency)
    results: list[EvalResultShim] = [None] * len(rows)  # type: ignore[list-item]
    retry_stats: dict = {"rate_limit_retries": 0}
    with ThreadPoolExecutor(max_workers=args.max_concurrency) as pool:
        futures = {
            pool.submit(call_with_rate_limit_retry, extract_one, row, stats=retry_stats): i
            for i, row in enumerate(rows)
        }
        for future, i in futures.items():
            try:
                results[i] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[i] = EvalResultShim(rows[i], None, str(exc))

    tracer.flush()
    tracer.shutdown()

    run = EvalRunShim(results)
    print_extraction_summary(run, scored_fields)
    log_docclass_specialist_run(
        run, with_truth, args, experiment_name, usage_by_index,
        log_path, md_log_path, field_types, tracing_backend, tracing_meta,
        n_routed=len(dataset),
    )
    if retry_stats["rate_limit_retries"]:
        print(f"  rate-limit retries: {retry_stats['rate_limit_retries']}", file=sys.stderr)
    print(f"\nExperiment logged to {log_path}")
    return 0


def log_docclass_specialist_run(
    result, dataset, args, experiment_name, usage, log_path, md_log_path,
    field_types, tracing_backend, tracing_meta, n_routed: int,
) -> None:
    """Append ONE docclass specialist experiment-log record."""
    from src.experiment_log import git_snapshot, tokens_summary

    ok_outputs = [r.output for r in result.results
                  if r.error is None and isinstance(r.output, dict)]
    per_row = []
    for r in result.results:
        output = r.output if isinstance(r.output, dict) else {}
        index = r.input.get("index", -1) if isinstance(r.input, dict) else -1
        per_row.append({
            "filename": r.input.get("filename") if isinstance(r.input, dict) else "",
            "status": "error" if r.error else "completed",
            "error": r.error,
            "overall_score": output.get("overall_score"),
            "field_scores": output.get("field_scores") or {},
            "predicted": output.get("predicted") or {},
            "tokens": usage.get(index) or {},
        })

    def _mean(key: str) -> float | None:
        vals = [float(o.get(key) or 0.0) for o in ok_outputs if o.get(key) is not None]
        return round(mean(vals), 4) if vals else None

    expected_by_index = {i: d.get("expected_fields") or {} for i, d in enumerate(dataset)}
    diag_rows = []
    for r in result.results:
        if r.error is not None:
            continue
        output = r.output if isinstance(r.output, dict) else {}
        if output.get("error"):
            continue
        index = r.input.get("index", -1) if isinstance(r.input, dict) else -1
        diag_rows.append({
            "filename": r.input.get("filename") if isinstance(r.input, dict) else "",
            "predicted": output.get("predicted") or {},
            "expected_fields": expected_by_index.get(index) or {},
            "field_scores": output.get("field_scores") or {},
            "entity_list_scores": output.get("entity_list_scores") or {},
        })
    diagnostics = extraction_diagnostics(diag_rows, field_types) if diag_rows else {}

    scores = {
        "overall_extraction_score": _mean("overall_score"),
        "field_presence": _mean("field_presence"),
        "overall_verified_precision": _mean("overall_verified_precision"),
        "category_presence": _mean("category_presence"),
        "n_rows": len(ok_outputs),
        "n_errors": len(result.results) - len(ok_outputs),
        "n_routed": n_routed,
        "diagnostics": diagnostics,
    }

    record = {
        "type": "experiment",
        "experiment_name": experiment_name,
        "task": "docclass_specialist_extraction",
        "model": args.model,
        "prompt_versions": {args.agent: args.prompt_version},
        "data_source": {
            "local_dumps": args.local_dumps,
            "agent": args.agent,
            "ground_truth": "docclass_merged_v5_gt_fields",
            "dataset_fingerprint": dataset_fingerprint(dataset),
            "n_samples": len(dataset),
            "n_routed": n_routed,
            "filename_manifest": str(args.filename_manifest) if args.filename_manifest else None,
            "seed": args.seed,
            "stratified": args.stratified,
        },
        "parameters": {
            "agent": args.agent,
            "prompt_version": args.prompt_version,
            "chunked": args.chunked,
            "max_input_chars": args.max_input_chars,
            "max_tokens": args.max_tokens,
            "reasoning_effort": args.reasoning_effort,
            "temperature": args.temperature,
            "tracing_backend": tracing_backend,
            "tracing_meta": tracing_meta or {},
        },
        "scores": scores,
        "per_row": per_row,
        "results": per_row,
        "tokens": {"extractor": tokens_summary(list(usage.values()), model=args.model),
                   "total": tokens_summary(list(usage.values()), model=args.model)},
        "git": git_snapshot(),
    }
    jsonl_path = append_experiment(record, log_path)
    append_markdown(record, md_log_path)
    print(f"\nExperiment logged to {jsonl_path}")


if __name__ == "__main__":
    raise SystemExit(main())
