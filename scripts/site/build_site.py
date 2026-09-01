#!/usr/bin/env python3
"""Build the static GitHub Pages site that views the experiment log.

The site lives in ``docs/`` (served by GitHub Pages from the ``main`` branch
via Settings -> Pages -> "Deploy from a branch" -> ``main`` -> ``/docs`` —
no Actions runners involved). ``docs/data/`` is DERIVED, exactly like
``reports/experiment_log.md`` is derived from
``reports/experiment_log.jsonl``: this script regenerates the whole data
tree from the JSONL source of truth, so the site always reflects every
record, in order, with no stale or hand-edited data.

Layout produced:

    docs/data/meta.json          build info + dataset-level facts
    docs/data/index.json         one compact summary per run (index table)
    docs/data/runs/{id}.json     the full record per run (detail pages)

Usage:
    python scripts/site/build_site.py                              # rebuild docs/data
    python scripts/site/build_site.py --openrouter-csv \
        openrouter_activity_2026-08-11.csv                         # also attribute real
                                                                   # OpenRouter costs + averages
    python scripts/site/build_site.py --jsonl /tmp/log.jsonl \
        --out /tmp/site-data                                      # custom paths
    python scripts/site/build_site.py --check                      # verify data is current
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402 - allow src.* imports
from src.cost_models import estimate_for_record  # noqa: E402

# The eval runners read credentials from braintrust.env then .env — the site
# builder must do the same or the benchmarks fetch silently reports
# "OPENROUTER_API_KEY not set" despite a configured key.
try:  # noqa: E402
    from src.env_utils import load_env

    load_env()
except Exception:  # pragma: no cover - env loading is best-effort
    pass
DEFAULT_JSONL = REPO_ROOT / "reports" / "experiment_log.jsonl"
DEFAULT_OUT = REPO_ROOT / "docs" / "data"
REPO_URL = "https://github.com/Exios66/llm-entity-extraction"

# Models billed under the eval OpenRouter key that constitute eval traffic.
EVAL_MODELS = {
    "qwen/qwen3.7-flash-20260727": "chat",
    "openai/text-embedding-3-small": "embeddings",
}


def _parse_ts(value: str) -> dt.datetime:
    """Parse an ISO-ish timestamp; naive values are treated as UTC."""
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def load_openrouter_costs(csv_path: Path, records: list[dict],
                          key: str = "Laptop v3") -> dict:
    """Attribute OpenRouter activity-log generations to experiment runs.

    The activity CSV (Settings -> Activity Logs export) contains one row per
    LLM generation. Rows billed to the eval key (``api_key_name``) for the
    eval models are assigned to the experiment whose completion timestamp is
    the first run boundary at-or-after the generation time (runs are sorted
    by ``timestamp``, so every generation lands in exactly one window).
    Generations outside all windows are reported as ``unattributed``.

    Returns a dict with per-run cost data keyed by run id (1-based), export
    metadata, and aggregates; runs with no rows in the export window get
    ``{"covered": false}``.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"OpenRouter activity CSV not found: {csv_path}")
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("api_key_name") != key:
                continue
            model = row.get("model_permaslug")
            if model not in EVAL_MODELS:
                continue
            rows.append(row)
    rows.sort(key=lambda r: r.get("created_at", ""))

    ordered = sorted(records, key=lambda r: r.get("timestamp", ""))
    bounds = [(_parse_ts(r["timestamp"]), r) for r in ordered]
    times = [b[0] for b in bounds]

    def window_index(gen_time: dt.datetime) -> int | None:
        """First run boundary at-or-after the generation time."""
        if not times:
            return None
        lo, hi = 0, len(times)
        while lo < hi:
            mid = (lo + hi) // 2
            if times[mid] < gen_time:
                lo = mid + 1
            else:
                hi = mid
        if lo >= len(times):
            return None
        return lo

    per_run: dict[int, dict] = {}
    unattributed = {"rows": 0, "cost_total_usd": 0.0}
    for row in rows:
        try:
            gen_time = _parse_ts(row.get("created_at", ""))
        except ValueError:
            continue
        idx = window_index(gen_time)
        kind = EVAL_MODELS[row["model_permaslug"]]
        cost = float(row.get("cost_total") or 0) or 0.0
        if idx is None:
            unattributed["rows"] += 1
            unattributed["cost_total_usd"] += cost
            continue
        run_id = idx + 1  # 1-based as in index.json
        entry = per_run.setdefault(run_id, {
            "covered": True,
            "calls": {"chat": 0, "embeddings": 0},
            "tokens": {"prompt": 0, "completion": 0, "cached": 0},
            "cost_total_usd": 0.0,
        })
        entry["calls"][kind] += 1
        entry["tokens"]["prompt"] += int(row.get("tokens_prompt") or 0)
        entry["tokens"]["completion"] += int(row.get("tokens_completion") or 0)
        entry["tokens"]["cached"] += int(row.get("tokens_cached") or 0)
        entry["cost_total_usd"] += cost

    export_start = rows[0]["created_at"][:19] if rows else None
    export_end = rows[-1]["created_at"][:19] if rows else None
    all_tokens = sum(e["tokens"]["prompt"] + e["tokens"]["completion"]
                     for e in per_run.values())
    covered_cost = sum(e["cost_total_usd"] for e in per_run.values())
    per_task: dict[str, float] = {}
    per_prompt: dict[str, float] = {}
    for idx, (_, rec) in enumerate(bounds):
        entry = per_run.get(idx + 1)
        if not entry:
            continue
        task = rec.get("task", "")
        per_task[task] = per_task.get(task, 0.0) + entry["cost_total_usd"]
        prompt = (rec.get("prompt_version")
                  or " + ".join(str(v) for v in (rec.get("prompt_versions") or {}).values())
                  or "—")
        per_prompt[prompt] = per_prompt.get(prompt, 0.0) + entry["cost_total_usd"]

    # Per-document averages (headline docs = run n_rows).
    for run_id, entry in per_run.items():
        n_rows = next(rec[1]["n_rows"] for idx, rec in enumerate(bounds)
                      if idx + 1 == run_id) or 1
        entry["cost_avg_per_doc_usd"] = entry["cost_total_usd"] / n_rows
        entry["tokens_avg_per_doc"] = (
            entry["tokens"]["prompt"] + entry["tokens"]["completion"]) / n_rows
        entry["calls"]["total"] = entry["calls"]["chat"] + entry["calls"]["embeddings"]

    return {
        "source": str(csv_path.name),
        "api_key": key,
        "export": {"start": export_start, "end": export_end},
        "per_run": per_run,
        "unattributed": unattributed,
        "totals": {
            "calls": {
                "chat": sum(e["calls"]["chat"] for e in per_run.values()),
                "embeddings": sum(e["calls"]["embeddings"] for e in per_run.values()),
            },
            "tokens": all_tokens,
            "cost_total_usd": covered_cost,
        },
        "per_task": per_task,
        "per_prompt": per_prompt,
        "covered_runs": len(per_run),
        "total_runs": len(records),
    }


def _fmt(value: float) -> str:
    """Format a score like the markdown log does (4 decimals)."""
    return f"{value:.4f}"


def load_records(path: Path) -> list[dict]:
    """Read every experiment record from the JSONL log (append-only source)."""
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:  # pragma: no cover
            print(f"Skipping malformed line in {path}: {exc}", file=sys.stderr)
    return records


def headline_score(record: dict) -> dict:
    """Derive the headline score card for a run, mirroring the md index.

    Returns a dict with the score, its human label, and a 0-1 ratio for
    progress-bar rendering; empty dict when the task has no headline metric.
    """
    scores = record.get("scores") or {}
    task = record.get("task")
    if task == "contract_entity_extraction":
        value = scores.get("overall_extraction_score")
        if isinstance(value, (int, float)):
            return {"label": "extraction", "value": value}
    if task == "chained_sorter_extractor":
        sorter = scores.get("sorter") or {}
        extractor = scores.get("extractor") or {}
        extractor_value = extractor.get("overall_extraction_score")
        if isinstance(extractor_value, (int, float)):
            detail = f"extractor {_fmt(extractor_value)}"
            sorter_value = sorter.get("exact_match")
            if isinstance(sorter_value, (int, float)):
                detail += f" · sorter doc_type {_fmt(sorter_value)}"
            return {
                "label": "extractor score",
                "value": extractor_value,
                "detail": detail,
            }
    if task == "subtype_classification":
        sorter = scores.get("sorter") or {}
        doc_type = sorter.get("exact_match")
        strict = sorter.get("subtype_accuracy")
        equiv = sorter.get("subtype_accuracy_equiv")
        if isinstance(strict, (int, float)) and isinstance(doc_type, (int, float)):
            detail = f"doc_type {_fmt(doc_type)} · strict {_fmt(strict)}"
            if isinstance(equiv, (int, float)):
                detail += f" · equiv {_fmt(equiv)}"
            return {
                "label": "subtype strict",
                "value": strict,
                "detail": detail,
            }
    if task == "sorter_classification":
        value = scores.get("exact_match")
        if isinstance(value, (int, float)):
            detail = f"failure {_fmt(scores.get('failure') or 0)}"
            per_class = scores.get("per_class_accuracy") or {}
            if per_class:
                detail += " · " + " ".join(
                    f"{k} {_fmt(v)}" for k, v in sorted(per_class.items())[:4])
            return {"label": "classification", "value": value, "detail": detail}
    if task == "legalbench_binary_answer":
        value = scores.get("accuracy")
        if isinstance(value, (int, float)):
            detail = (
                f"macro {_fmt(scores.get('macro_category_accuracy') or 0)}"
                f" · yes-F1 {_fmt(scores.get('yes_f1') or 0)}"
                f" · cal {_fmt(scores.get('calibration_error') or 0)}"
            )
            return {"label": "QA accuracy", "value": value, "detail": detail}
    if task == "legalbench_multiclass_classification":
        value = scores.get("accuracy")
        if isinstance(value, (int, float)):
            detail = f"strict {_fmt(value)} · equiv {_fmt(scores.get('accuracy_equiv') or 0)}"
            return {"label": "family accuracy", "value": value, "detail": detail}
    if task == "correspondence_classification":
        exact = scores.get("correspondence_exact")
        subclass = scores.get("subclass_accuracy")
        sentiment = scores.get("sentiment_label_accuracy")
        if isinstance(exact, (int, float)):
            detail = f"subclass {_fmt(subclass)} · sentiment {_fmt(sentiment)}"
            return {"label": "correspondence exact", "value": exact, "detail": detail}
        if isinstance(subclass, (int, float)):
            return {"label": "subclass", "value": subclass}
    return {}


def breakdown(record: dict) -> dict:
    """Per-task metric breakdown shown in the dashboard (no per-doc data)."""
    task = record.get("task")
    scores = record.get("scores") or {}
    if task == "contract_entity_extraction":
        diagnostics = scores.get("diagnostics") or {}
        return {
            "overall_extraction_score": scores.get("overall_extraction_score"),
            "field_presence": scores.get("field_presence"),
            "schema_valid": scores.get("schema_valid"),
            "per_field": scores.get("per_field") or {},
            "field_exact_rate": diagnostics.get("field_exact_rate"),
            "list_f1": diagnostics.get("list_f1"),
            "date_mae_days": diagnostics.get("date_mae_days"),
            "date_r2": diagnostics.get("date_r2"),
            "duration_mae_days": diagnostics.get("duration_mae_days"),
            "duration_r2": diagnostics.get("duration_r2"),
        }
    if task == "chained_sorter_extractor":
        sorter = scores.get("sorter") or {}
        extractor = scores.get("extractor") or {}
        return {
            "sorter": {
                "exact_match": sorter.get("exact_match"),
                "subtype_accuracy": sorter.get("subtype_accuracy"),
                "confidence": sorter.get("confidence"),
            },
            "extractor": {
                "overall_extraction_score": extractor.get("overall_extraction_score"),
                "field_presence": extractor.get("field_presence"),
                "overall_verified_precision": extractor.get("overall_verified_precision"),
                "category_presence": extractor.get("category_presence"),
            },
        }
    if task == "subtype_classification":
        sorter = scores.get("sorter") or {}
        failures = sorter.get("failure_insights") or {}
        return {
            "doc_type_accuracy": sorter.get("exact_match"),
            "subtype_accuracy": sorter.get("subtype_accuracy"),
            "subtype_accuracy_equiv": sorter.get("subtype_accuracy_equiv"),
            "confidence": sorter.get("confidence"),
            "n_failed": failures.get("n_failed"),
            "mode_counts": failures.get("mode_counts") or {},
        }
    if task == "legalbench_binary_answer":
        return {
            "accuracy": scores.get("accuracy"),
            "macro_category_accuracy": scores.get("macro_category_accuracy"),
            "yes_f1": scores.get("yes_f1"),
            "confidence_mean": scores.get("confidence_mean"),
            "calibration_error": scores.get("calibration_error"),
            "n_questions": scores.get("n_questions"),
            "n_yes": scores.get("n_yes"),
            "n_no": scores.get("n_no"),
        }
    if task == "legalbench_multiclass_classification":
        return {
            "accuracy": scores.get("accuracy"),
            "accuracy_equiv": scores.get("accuracy_equiv"),
            "macro_f1": scores.get("macro_f1"),
            "confidence_mean": scores.get("confidence_mean"),
            "calibration_error": scores.get("calibration_error"),
            "n_documents": scores.get("n_documents"),
        }
    if task == "correspondence_classification":
        failures = (scores.get("sorter") or {}).get("failure_insights") or {}
        return {
            "doc_type_accuracy": scores.get("doc_type_accuracy"),
            "subclass_accuracy": scores.get("subclass_accuracy"),
            "sentiment_label_accuracy": scores.get("sentiment_label_accuracy"),
            "sentiment_score_mae": scores.get("sentiment_score_mae"),
            "correspondence_exact": scores.get("correspondence_exact"),
            "confidence": scores.get("confidence"),
            "n_failed": failures.get("n_failed"),
            "mode_counts": failures.get("mode_counts") or {},
        }
    return {}


def prompt_string(record: dict) -> str:
    """Human prompt label: record field first, else sorter+extractor pair."""
    prompt = record.get("prompt_version")
    if not prompt and isinstance(record.get("prompt_versions"), dict):
        prompt = " + ".join(str(v) for v in record["prompt_versions"].values())
    return prompt or "—"


def wilson_ci(p: float | None, n: int | None, z: float = 1.96) -> dict | None:
    """Wilson score interval for a proportion (95% by default).

    Sample-size-aware: the interval narrows with n, so a 5-document run gets
    a wide interval while a 509-document run gets a tight one. Used to
    quantify how much a score could vary by chance, and to flag deltas
    between runs of different sizes as not statistically meaningful.
    """
    if p is None or not n:
        return None
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {
        "lo": max(0.0, center - half),
        "hi": min(1.0, center + half),
        "half_pp": half * 100,
    }


def _record_ci(record: dict) -> dict | None:
    """Bootstrap CI for a run's headline: prefer the runner-computed *_ci,
    else resample the per-document scores stored in results[], else Wilson
    (the historical fallback). Never fabricate precision on n=1 runs."""
    scores = record.get("scores") or {}
    task = record.get("task", "")
    ci_keys = {
        "contract_entity_extraction": ["overall_extraction_score_ci"],
        "chained_sorter_extractor": ["extractor", "overall_extraction_score_ci"],
        "subtype_classification": ["sorter", "subtype_accuracy_ci"],
        "sorter_classification": ["exact_match_ci"],
        "legalbench_binary_answer": ["accuracy_ci"],
        "legalbench_multiclass_classification": ["accuracy_ci"],
    }
    keys = ci_keys.get(task)
    if keys:
        node = scores
        for key in keys:
            node = (node or {}).get(key)
            if not isinstance(node, dict):
                node = None
                break
        if isinstance(node, dict) and node.get("lo") is not None:
            return node

    values = _results_values(record)
    if values is not None:
        try:
            from src.bootstrap import bootstrap_ci

            ci = bootstrap_ci(values, seed=42)
            if ci:
                ci["source"] = "results-bootstrap"
                return ci
        except ImportError:  # pragma: no cover
            pass
    headline = headline_score(record)
    if headline and headline.get("value") is not None:
        wilson = wilson_ci(headline["value"], record.get("n_rows"))
        if wilson:
            wilson["source"] = "wilson"
            return wilson
    return None


def _results_values(record: dict) -> list | None:
    """Per-document score arrays for the headline tracker, by task."""
    results = record.get("results") or []
    task = record.get("task", "")
    if task in ("contract_entity_extraction", "legalbench_binary_answer",
                "legalbench_multiclass_classification", "sorter_classification"):
        if task == "contract_entity_extraction":
            return [r.get("overall_score") for r in results if r.get("overall_score") is not None]
        return [1.0 if r.get("correct") else 0.0 for r in results if r.get("status") == "ok"]
    if task == "chained_sorter_extractor":
        return [r.get("extractor_scores", {}).get("overall_score")
                for r in results if r.get("extractor_scores", {}).get("overall_score") is not None]
    if task == "subtype_classification":
        return [1.0 if r.get("sorter", {}).get("subtype_ok") else 0.0
                for r in results if "subtype_ok" in (r.get("sorter") or {})]
    if task == "correspondence_classification":
        return [1.0 if r.get("sorter", {}).get("correspondence_exact") else 0.0
                for r in results if "correspondence_exact" in (r.get("sorter") or {})]
    return None


def _sample_key(record: dict) -> str:
    """Same-surface identity: dataset fingerprint + seed + sample size. Deltas
    are only meaningful between runs sharing a key (issue #1 guardrail)."""
    ds = record.get("data_source") or {}
    fp = str(ds.get("dataset_fingerprint") or "?")
    seed = str(ds.get("seed") or ds.get("sample_seed") or "?")
    n = str(ds.get("n_samples") or record.get("n_rows") or "?")
    return f"{fp}:{seed}:{n}"


def summarize(record: dict, run_id: int, best_by_task: dict[str, float],
              surface_best: dict[str, float]) -> dict:
    """Compact index-row summary used by the site's index table."""
    tokens = record.get("tokens") or {}
    if "total" in tokens:
        total_tokens = (tokens["total"] or {}).get("total_tokens")
        cost_total = (tokens["total"] or {}).get("cost_total_usd")
    else:
        total_tokens = tokens.get("total_tokens")
        cost_total = tokens.get("cost_total_usd")
    # Issue #1 cost scoring: every run gets a deterministic token x price
    # estimate (usage payloads carry no cost field); the OpenRouter-CSV
    # "billed" figure, when covered, remains the ground truth to prefer.
    cost_estimate = estimate_for_record(record)
    data_source = record.get("data_source") or {}
    headline = headline_score(record)
    task = record.get("task", "")
    # Issue #1 same-surface guardrail: the delta is computed against the best
    # run on the SAME dataset fingerprint + seed + sample size, never against
    # a differently-sampled run (that is how the v0.13.0 "regression" got
    # misread). When no same-surface run exists, delta stays null.
    sample_key = _sample_key(record)
    delta = None
    best = best_by_task.get(task)
    surface = surface_best.get((task, sample_key))
    if headline and surface is not None:
        delta = (headline["value"] - surface) * 100  # percentage points
    return {
        "id": run_id,
        "experiment_name": record.get("experiment_name", ""),
        "task": task,
        "model": record.get("model", ""),
        "prompts": prompt_string(record),
        "headline": headline,
        "ci95": _record_ci(record),
        "breakdown": breakdown(record),
        "n_rows": record.get("n_rows"),
        "n_ok": record.get("n_ok"),
        "n_error": record.get("n_error") or 0,
        "total_tokens": total_tokens,
        "cost_usd": tokens.get("cost_usd") if tokens else None,
        "cost_total_usd": cost_total,
        "cost_estimated_usd": cost_estimate.get("cost_estimated_usd"),
        "cost_estimated_per_doc_usd": cost_estimate.get("per_doc_usd"),
        "cost_price_source": cost_estimate.get("price_source") and
            {"model": cost_estimate.get("model"),
             "in_per_1m": cost_estimate["price_source"][0],
             "out_per_1m": cost_estimate["price_source"][1]},
        "fingerprint": data_source.get("dataset_fingerprint"),
        "seed": data_source.get("seed"),
        "sample_key": sample_key,
        "global_best_pp": ((headline["value"] - best) * 100
                           if headline and best is not None else None),
        "delta_best_pp": delta,
        "timestamp": record.get("timestamp"),
        "git": record.get("git"),
        "data_source_project": data_source.get("project"),
        "data_source_n_samples": data_source.get("n_samples"),
        "seed": data_source.get("seed"),
    }


# ---------------------------------------------------------------------------
# Scoring guide — canonical explanations mirrored from docs/SCORING.md.
# Rendered verbatim as the reference card on the site index. Keep in sync with
# docs/SCORING.md; the live repo file remains the source of truth.
# ---------------------------------------------------------------------------

BANDS = [
    {"min": 0.85, "label": "Strong", "cls": "good",
     "meaning": "High confidence result; only minor field/family-level misses."},
    {"min": 0.60, "label": "Moderate", "cls": "warn",
     "meaning": "Material misses (this range overlaps the repo's ambiguous band "
                "[0.5, 0.85] that triggers a judge review pass)."},
    {"min": 0.0, "label": "Weak", "cls": "bad",
     "meaning": "Poor result; the model is missing or misclassifying core content."},
]

SCORING_GUIDE = {
    "bands": BANDS,
    "general": (
        "All scores are deterministic and computed locally — no LLM grading. "
        "The markdown log, manifests, and this site all read the same numbers. "
        "Compare runs only on the SAME sample (same dataset, seed, and size): "
        "accuracy deltas across different samples are meaningless."
    ),
    "tasks": {
        "contract_entity_extraction": {
            "headline": {"key": "overall_extraction_score", "label": "Overall extraction"},
            "summary": "How faithfully the contracts-specialist extracted every expected "
                       "field from the contract text, per field's declared type.",
            "formula": ("mean of the per-field content scores over expected fields with a "
                        "non-null ground-truth value"),
            "conveys": ("End-to-end extraction quality: dates/money exact, names fuzzy-"
                        "matched, clauses containment-scored, entity lists bipartite-"
                        "matched against ground truth."),
            "components": [
                {"key": "overall_extraction_score", "label": "Overall extraction",
                 "calculation": "mean of per-field content scores",
                 "meaning": "Composite content accuracy across all expected fields."},
                {"key": "field_presence", "label": "Field presence",
                 "calculation": "share of expected fields the model populated (non-null/non-empty)",
                 "meaning": "Did the model produce a value at all, regardless of correctness?"},
                {"key": "schema_valid", "label": "Schema valid",
                 "calculation": "1.0 iff output is parseable, schema-conformant JSON",
                 "meaning": "Output-contract conformance — 0 means the row was unusable."},
                {"key": "per_field", "label": "Per-field scores",
                 "calculation": ("type-aware: date/money exact; name fuzzy (Jaro-Winkler + "
                                 "token-set); free_text SQuAD token F1; entity_list optimal "
                                 "bipartite matching at 0.6 threshold; containment = "
                                 "expected-token coverage"),
                 "meaning": "Where exactly quality is gained or lost."},
            ],
        },
        "chained_sorter_extractor": {
            "headline": {"key": "extractor.overall_extraction_score",
                         "label": "Extractor score"},
            "summary": "The full sorter → specialist chain: the sorter classifies the "
                       "document, then the specialist extracts with that context.",
            "formula": ("headline = the specialist's overall_extraction_score (same "
                        "composite as the extraction task); the sorter's doc-type match "
                        "is shown alongside"),
            "conveys": "End-to-end pipeline quality — both stages must work.",
            "components": [
                {"key": "sorter.exact_match", "label": "Sorter doc-type match",
                 "calculation": "1.0 iff doc_type == 'contract'",
                 "meaning": "The sorter sent the document down the contract path."},
                {"key": "sorter.subtype_accuracy", "label": "Sorter subtype accuracy",
                 "calculation": "1.0 iff doc_type AND normalized contract subtype match the CUAD folder",
                 "meaning": "Contract-family routing quality."},
                {"key": "extractor.overall_extraction_score", "label": "Extractor overall",
                 "calculation": "mean of per-field content scores (see extraction task)",
                 "meaning": "Field extraction quality given the sorter's context."},
                {"key": "extractor.overall_verified_precision", "label": "Verified precision",
                 "calculation": ("factuality guard: share of predicted items that match a "
                                 "GT label OR are grounded in the document (token coverage "
                                 "≥ 0.7)"),
                 "meaning": "Truthfulness — how much of the output is real, not hallucinated."},
                {"key": "extractor.category_presence", "label": "Category presence",
                 "calculation": "share of the document's applicable CUAD presence-categories covered",
                 "meaning": "Did the extraction cover the labeled clauses that must appear?"},
                {"key": "extractor.field_presence", "label": "Field presence",
                 "calculation": "share of expected fields populated",
                 "meaning": "Completeness of output fields."},
            ],
        },
        "subtype_classification": {
            "headline": {"key": "sorter.subtype_accuracy", "label": "Subtype accuracy (strict)"},
            "summary": "The sorter-only task: one call per document that decides the "
                       "primary class (contract or not) AND the contract-subtype family.",
            "formula": ("headline = strict subtype accuracy: share of rows whose normalized "
                        "predicted subtype exactly equals the CUAD ground-truth folder"),
            "conveys": "Routing quality: strict is the discriminating signal; equiv allows "
                       "defensible family swaps (reseller↔distributor, maintenance↔license, "
                       "development↔license, affiliate↔joint_venture).",
            "components": [
                {"key": "doc_type_accuracy", "label": "Doc-type accuracy (exact_match)",
                 "calculation": "share of rows where doc_type == 'contract'",
                 "meaning": "Primary-class correctness (every CUAD row is a contract)."},
                {"key": "subtype_accuracy", "label": "Subtype strict",
                 "calculation": "share of rows where normalized subtype == CUAD folder exactly",
                 "meaning": "Exact family-level routing."},
                {"key": "subtype_accuracy_equiv", "label": "Subtype equiv",
                 "calculation": "strict OR defensible equivalent family",
                 "meaning": "How often the model routed to a legally-defensible family."},
                {"key": "confidence", "label": "Confidence",
                 "calculation": "mean of the model's reported per-row confidence",
                 "meaning": "Calibration signal — how sure the model claims to be."},
                {"key": "n_failed", "label": "Failed rows",
                 "calculation": "rows with subtype_ok == false, broken down by failure mode",
                 "meaning": ("modes: family_confusion (wrong family), function_over_form "
                             "(doc_type miss), other_fallback (fell to 'other'), "
                             "equivalent_family (recovered by equivalence)")},
            ],
        },
        "legalbench_binary_answer": {
            "headline": {"key": "accuracy", "label": "QA accuracy"},
            "summary": ("LegalBench suite (llm-mailroom/src/legalbench/) — CUAD contract-QA "
                        "binary-answer task: yes/no questions over contracts with "
                        "evidence spans, scored against the CUAD annotations."),
            "formula": "headline = share of questions answered correctly (predicted yes/no == annotation)",
            "conveys": "Contract-comprehension accuracy on a large, real legal QA corpus.",
            "components": [
                {"key": "accuracy", "label": "Accuracy",
                 "calculation": "share of questions with predicted == expected",
                 "meaning": "Headline comprehension quality."},
                {"key": "macro_category_accuracy", "label": "Macro category accuracy",
                 "calculation": "mean of per-clause-category accuracies (41 categories)",
                 "meaning": "Whether any clause family is disproportionately hard."},
                {"key": "yes_f1", "label": "Yes-class F1",
                 "calculation": "F1 for answering 'yes' (precision/recall over yes predictions vs yes labels)",
                 "meaning": "False-positive tendency on affirmative answers."},
                {"key": "confidence_mean", "label": "Confidence mean",
                 "calculation": "mean of the model's reported per-question confidence",
                 "meaning": "Calibration signal."},
                {"key": "calibration_error", "label": "Calibration error (ECE)",
                 "calculation": "expected calibration error over confidence/outcome pairs",
                 "meaning": "How well confidence matches observed correctness."},
            ],
        },
        "legalbench_multiclass_classification": {
            "headline": {"key": "accuracy", "label": "Family accuracy (strict)"},
            "summary": ("LegalBench suite (llm-mailroom/src/legalbench/) — CUAD contract-family "
                        "classification: assign one of the 25 contract families (+ other) "
                        "to each contract, scored against the family derived from the "
                        "CUAD folder/title taxonomy."),
            "formula": ("headline = strict family accuracy; equiv additionally accepts "
                        "defensible family swaps (same SUBTYPE_EQUIVALENCES as the sorter)"),
            "conveys": "Multiclass legal-routing accuracy with a defensible-equivalence lens.",
            "components": [
                {"key": "accuracy", "label": "Strict accuracy",
                 "calculation": "share of documents whose family key matches exactly",
                 "meaning": "Exact family-level routing."},
                {"key": "accuracy_equiv", "label": "Equiv accuracy",
                 "calculation": "strict OR defensible equivalent family",
                 "meaning": "Routing to a legally-defensible family."},
                {"key": "macro_f1", "label": "Macro F1",
                 "calculation": "mean one-vs-rest F1 over families with labels present",
                 "meaning": "Class balance-adjusted quality."},
                {"key": "confidence_mean", "label": "Confidence mean",
                 "calculation": "mean of the model's reported per-document confidence",
                 "meaning": "Calibration signal."},
            ],
        },
    },
    "references": {
        "scoring_md": f"{REPO_URL}/blob/main/docs/SCORING.md",
        "agents_md": f"{REPO_URL}/blob/main/AGENTS.md",
    },
}


def build_meta(records: list[dict], jsonl_path: Path, out_dir: Path) -> dict:
    """Dataset-level facts shown in the site header/footer."""
    tasks: dict[str, int] = {}
    models: dict[str, int] = {}
    prompts: dict[str, int] = {}
    n_rows = n_ok = n_error = total_tokens = 0
    surfaces: set[str] = set()
    for record in records:
        task = record.get("task", "")
        tasks[task] = tasks.get(task, 0) + 1
        surfaces.add(_sample_key(record))
        model = record.get("model", "")
        models[model] = models.get(model, 0) + 1
        prompt = prompt_string(record)
        prompts[prompt] = prompts.get(prompt, 0) + 1
        n_rows += record.get("n_rows") or 0
        n_ok += record.get("n_ok") or 0
        n_error += record.get("n_error") or 0
        tokens = record.get("tokens") or {}
        if "total" in tokens:
            total_tokens += (tokens["total"] or {}).get("total_tokens") or 0
        else:
            total_tokens += tokens.get("total_tokens") or 0
    best_by_task: dict[str, dict] = {}
    for i, record in enumerate(records, start=1):
        headline = headline_score(record)
        if not headline:
            continue
        task = record.get("task", "")
        current = best_by_task.get(task)
        if current is None or headline["value"] > current["value"]:
            best_by_task[task] = {
                "run_id": i,
                "value": headline["value"],
                "label": headline["label"],
            }

    values_by_task: dict[str, list[tuple[int, float]]] = {}
    for i, record in enumerate(records, start=1):
        headline = headline_score(record)
        if headline:
            values_by_task.setdefault(record.get("task", ""), []).append(
                (i, headline["value"]))
    task_aggregates: dict[str, dict] = {}
    for task, pairs in values_by_task.items():
        values = sorted(v for _, v in pairs)
        n = len(values)
        median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
        best_pair = max(pairs, key=lambda p: p[1])
        worst_pair = min(pairs, key=lambda p: p[1])
        task_aggregates[task] = {
            "runs": n,
            "best": {"run_id": best_pair[0], "value": best_pair[1]},
            "median": median,
            "worst": {"run_id": worst_pair[0], "value": worst_pair[1]},
            "documents": sum(r.get("n_rows") or 0 for r in records if r.get("task") == task),
            "tokens": sum(
                ((r.get("tokens") or {}).get("total") or {}).get("total_tokens")
                if "total" in (r.get("tokens") or {})
                else (r.get("tokens") or {}).get("total_tokens") or 0
                for r in records if r.get("task") == task),
        }

    return {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "surfaces": sorted(surfaces),
        "source": str(jsonl_path.relative_to(REPO_ROOT)),
        "repo_url": REPO_URL,
        "run_count": len(records),
        "tasks": tasks,
        "models": models,
        "prompts": prompts,
        "n_rows": n_rows,
        "n_ok": n_ok,
        "n_error": n_error,
        "total_tokens": total_tokens,
        "best_per_task": best_by_task,
        "task_aggregates": task_aggregates,
        "scoring_guide": SCORING_GUIDE,
    }


def main() -> int:
    return main_with_args(sys.argv[1:])


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL,
                        help=f"JSONL experiment log (default: {DEFAULT_JSONL})")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"Site data output dir (default: {DEFAULT_OUT})")
    parser.add_argument("--openrouter-csv", type=Path, default=None,
                        help="OpenRouter activity-log CSV (Settings -> Activity Logs). "
                             "When given, per-run costs and averages are attributed from it")
    parser.add_argument("--openrouter-key", default="Laptop v3",
                        help="api_key_name in the CSV that carries eval traffic "
                             "(default: 'Laptop v3')")
    parser.add_argument("--benchmarks-key", default=None,
                        help="OpenRouter API key for the Benchmarks view (default: "
                             "$OPENROUTER_API_KEY; benchmarks.json is written with "
                             "available=false when absent or unreachable — the site "
                             "still renders with a rebuild hint)")
    parser.add_argument("--check", action="store_true",
                        help="Verify docs/data matches the JSONL; exit 1 if stale")
    args = parser.parse_args(argv)

    records = load_records(args.jsonl)
    if not records:
        parser.error(f"No experiment records found in {args.jsonl}.")

    if args.check:
        index_path = args.out / "index.json"
        meta_path = args.out / "meta.json"
        if not index_path.exists() or not meta_path.exists():
            print("Site data is missing; run build_site.py to regenerate.")
            return 1
        current = json.loads(index_path.read_text(encoding="utf-8"))
        if len(current) != len(records):
            print(f"Site data is stale: {len(current)} runs in site, "
                  f"{len(records)} in {args.jsonl}.")
            return 1
        # KANBAN-094: index length alone misses orphaned run files (a tree
        # built from a longer/merged view); compare file count too.
        n_files = len(list((args.out / "runs").glob("*.json")))
        if n_files != len(records):
            print(f"Site data is stale: {n_files} run files on disk, "
                  f"{len(records)} in {args.jsonl}.")
            return 1
        print(f"Site data is current ({len(current)} runs).")
        return 0

    costs = None
    if args.openrouter_csv:
        costs = load_openrouter_costs(args.openrouter_csv, records, args.openrouter_key)
        print(f"OpenRouter costs attributed from {args.openrouter_csv.name}: "
              f"{costs['covered_runs']}/{costs['total_runs']} runs covered, "
              f"${costs['totals']['cost_total_usd']:.4f} total.")

    runs_dir = args.out / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    best_values: dict[str, float] = {}
    surface_best: dict[tuple[str, str], float] = {}
    for i, record in enumerate(records, start=1):
        headline = headline_score(record)
        if headline:
            task = record.get("task", "")
            best_values[task] = max(headline["value"],
                                    best_values.get(task, float("-inf")))
            key = (task, _sample_key(record))
            surface_best[key] = max(headline["value"],
                                    surface_best.get(key, float("-inf")))
    summaries = []
    for index, record in enumerate(records, start=1):
        (runs_dir / f"{index:03d}.json").write_text(
            json.dumps(record, indent=1), encoding="utf-8")
        summary = summarize(record, index, best_values, surface_best)
        if costs:
            summary["cost"] = costs["per_run"].get(index, {"covered": False})
        summaries.append(summary)
    # KANBAN-094: the derived tree must be exactly {001..N}. An append-only
    # log only grows, but a RECONCILED log can shrink below a previously
    # built tree — prune any run file the current source of truth doesn't
    # claim, or stale SPA pages linger and break the deep-link invariant.
    expected_names = {f"{i:03d}.json" for i in range(1, len(records) + 1)}
    pruned = sorted(p.name for p in runs_dir.glob("*.json")
                    if p.name not in expected_names)
    for name in pruned:
        (runs_dir / name).unlink()
    if pruned:
        print(f"Pruned {len(pruned)} stale run file(s): {', '.join(pruned)}")
    (args.out / "index.json").write_text(
        json.dumps(summaries, indent=1), encoding="utf-8")
    meta = build_meta(records, args.jsonl, args.out)
    if costs:
        meta["costs"] = costs
    (args.out / "meta.json").write_text(
        json.dumps(meta, indent=1), encoding="utf-8")
    (args.out / "trends.json").write_text(
        json.dumps(build_trends(records, summaries), indent=1), encoding="utf-8")
    prompts = build_prompts()
    (args.out / "prompts.json").write_text(
        json.dumps(prompts, indent=1), encoding="utf-8")
    (args.out / "benchmarks.json").write_text(
        json.dumps(build_benchmarks(args.benchmarks_key), indent=1), encoding="utf-8")
    (args.out / "memos.json").write_text(
        json.dumps(build_memos(), indent=1), encoding="utf-8")
    (args.out / "board.json").write_text(
        json.dumps(build_board(), indent=1), encoding="utf-8")
    print(f"Site data rebuilt: {len(records)} records -> {args.out} "
          f"({len(prompts)} prompts, {len(meta.get('surfaces', []))} surfaces)")
    return 0


def build_trends(records: list[dict], summaries: list[dict]) -> dict:
    """Per-task series for the site's trend charts (issue #1 display).

    One entry per run: headline value + label, cost, prompt(s), model, the
    same-surface key, and per-run failure-mode counts (subtype runs) so the
    frontend can draw trend lines, the cost-vs-quality scatter, and the
    failure-mode stacked bars from ONE payload.
    """
    by_task: dict[str, list[dict]] = {}
    for i, (record, summary) in enumerate(zip(records, summaries), start=1):
        task = record.get("task", "")
        headline = summary.get("headline") or {}
        value = headline.get("value")
        if not isinstance(value, (int, float)):
            continue
        entry = {
            "id": i,
            "experiment_name": record.get("experiment_name", ""),
            "timestamp": record.get("timestamp"),
            "model": record.get("model", ""),
            "prompts": prompt_string(record),
            "headline_value": round(float(value), 4),
            "headline_label": headline.get("label", ""),
            "cost_total_usd": summary.get("cost_total_usd"),
            "cost_estimated_usd": summary.get("cost_estimated_usd"),
            "n_rows": record.get("n_rows"),
            "seed": summary.get("seed"),
            "sample_key": summary.get("sample_key"),
        }
        scores = record.get("scores") or {}
        if task == "subtype_classification":
            entry["mode_counts"] = (scores.get("sorter") or {}).get(
                "failure_insights", {}).get("mode_counts")
        elif task == "chained_sorter_extractor":
            entry["ablation"] = scores.get("ablation")
        elif task == "contract_entity_extraction":
            # ContractEval-rubric KPIs (KANBAN-054): F1/F2/Jaccard/false-nr +
            # the semantic coverage bands, charted over time per run.
            kpis = scores.get("contracteval_kpis") or {}
            semantic = kpis.get("semantic") or {}
            entry["f1"] = kpis.get("f1")
            entry["f2"] = kpis.get("f2")
            entry["jaccard_mean"] = kpis.get("jaccard_mean")
            entry["false_no_related_rate"] = kpis.get("false_no_related_rate")
            entry["recall"] = kpis.get("recall")
            entry["semantic_ge0_7"] = semantic.get("ge0_7")
            entry["semantic_verbatim"] = semantic.get("verbatim")
            entry["kpi_n_pairs"] = kpis.get("n_pairs")
        by_task.setdefault(task, []).append(entry)
    return {"tasks": by_task}


def _now_iso() -> str:
    """UTC timestamp for derived-data provenance."""
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def build_board() -> dict:
    """The agent Kanban board (MESSAGE_BOARD.md at the repo root) shipped to
    the site's board tab — the live work-progress board for the cross-repo
    project, rendered read-only for visual inspection."""
    path = REPO_ROOT / "governance" / "MESSAGE_BOARD.md"
    if not path.is_file():
        return {"markdown": "", "built_at": None}
    return {"markdown": path.read_text(encoding="utf-8"),
            "built_at": _now_iso()}


def build_memos() -> dict:
    """Research memos (docs/memos/*.md) shipped to the site's memos tab — the
    archive of findings for collaborators and presentation."""
    import re as _re

    memos_dir = REPO_ROOT / "docs" / "memos"
    out = []
    if not memos_dir.is_dir():
        return {"memos": []}
    for path in sorted(memos_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        title_match = _re.match(r"^#\\s+(.+)$", text, _re.M)
        out.append({
            "file": path.name,
            "title": title_match.group(1).strip() if title_match else path.stem,
            "markdown": text,
        })
    return {"memos": out}


def build_benchmarks(api_key: str | None = None) -> dict:
    """OpenRouter unified benchmarks (Artificial Analysis + Design Arena) for
    the site's Benchmarks tab — model-selection evidence for anyone choosing
    models to test in their eval pipelines.

    Best-effort: needs a valid OpenRouter API key (--benchmarks-key or
    $OPENROUTER_API_KEY); when absent/unreachable the view renders a rebuild
    hint instead of failing the build. Citation metadata (meta.as_of,
    source_url) is preserved per the OpenRouter skill's reporting guidance.
    """
    import os
    import urllib.error
    import urllib.request

    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {"available": False,
                "error": "OPENROUTER_API_KEY not set — rebuild with "
                         "--benchmarks-key or the env var to fetch live benchmarks",
                "data": [], "meta": {"version": "v1"}}
    url = "https://openrouter.ai/api/v1/benchmarks"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "User-Agent": "llm-entity-extraction/site-builder",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as exc:
        return {"available": False, "error": str(exc)[:300],
                "data": [], "meta": {"version": "v1"}}
    meta = payload.get("meta") or {}
    meta.setdefault("version", "v1")
    print(f"Benchmarks fetched: {len(payload.get('data') or [])} rows "
          f"(as_of {meta.get('as_of')}, source {meta.get('source')})")
    return {"available": True, "error": None,
            "data": payload.get("data") or [], "meta": meta}


def build_prompts() -> dict:
    """Emit every registered prompt version's full text (issue #1 prompt diff
    viewer). Versions whose text can't be resolved are skipped."""
    try:
        from src.prompts import PROMPT_VERSIONS, get_prompt
    except ImportError:  # pragma: no cover
        return {}
    out: dict[str, str] = {}
    for version in PROMPT_VERSIONS:
        try:
            text = get_prompt(version)
        except KeyError:
            continue
        if isinstance(text, str) and text.strip():
            out[version] = text
    return out


if __name__ == "__main__":
    raise SystemExit(main())
