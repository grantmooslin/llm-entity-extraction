"""Repository-local experiment log.

Every eval run appends ONE JSON record (plus a human-readable markdown
section) to ``reports/experiment_log.jsonl`` / ``reports/experiment_log.md``,
so the repo carries a complete, append-only history of every experiment:
model, prompt version, data source, all run parameters, token usage, every
score, and every per-row result.

The markdown sections are rendered as tables (never raw JSON dumps): run
metadata, data source, parameters, token usage, every score with per-field
breakdowns, the per-document results table, the full document-x-field scoring
matrix, entity-list F1, the factuality audit, CUAD category presence,
expected-vs-predicted confusion matrices, and the model's raw per-document
outputs. ``render_full_log`` additionally produces a title + experiment index
for the whole history; ``scripts/reporting/render_experiment_log.py`` rebuilds
``reports/experiment_log.md`` from the JSONL.

Paths are overridable via the ``EXPERIMENT_LOG_PATH`` /
``EXPERIMENT_LOG_MD_PATH`` env vars (or the ``--experiment-log`` CLI flag in
the eval runners); tests redirect them to a tmp dir. The log is deliberately
append-only — one line per experiment — and never overwritten.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Scoring-layer helpers (append/git snapshot/mean/tokens) live in the
# llm-dojo-scoring package (src/experiment_log.py keeps the markdown
# renderers — the report layer — local). Re-exported so every import site in
# this repo (and llm-mailroom's `pip install -e .` imports) keeps working.
from llm_dojo_scoring.cost import tokens_summary  # noqa: F401
from llm_dojo_scoring.experiment import (  # noqa: F401
    append_experiment,
    git_snapshot,
    mean,
)

# Post-hoc judge judgments live per experiment in data/judgments/<name>.jsonl;
# the renderer includes a Judge agent review section for records that have one.
JUDGMENTS_DIR = Path(__file__).resolve().parent.parent / "data" / "judgments"

JSONL_ENV = "EXPERIMENT_LOG_PATH"
MD_ENV = "EXPERIMENT_LOG_MD_PATH"
DEFAULT_JSONL = "reports/experiment_log.jsonl"
DEFAULT_MD = "reports/experiment_log.md"


def default_jsonl_path() -> Path:
    """Resolve the JSONL log path from env (or the repo default)."""
    return Path(os.environ.get(JSONL_ENV, DEFAULT_JSONL))


def default_md_path() -> Path:
    """Resolve the markdown log path from env (or the repo default)."""
    return Path(os.environ.get(MD_ENV, DEFAULT_MD))


def _fmt(value: Any, max_len: int | None = None) -> str:
    """Format a log value for markdown tables: floats to 4dp, bools to marks."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "✓" if value else "✗"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".") if value else "0.0"
        return text
    if isinstance(value, dict):
        text = " · ".join(f"{k}: {v}" for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        text = ", ".join(str(v) for v in value) if value else "—"
    else:
        text = str(value)
    if max_len and len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a markdown table (headers + string rows)."""
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _kv_table(rows: list[tuple[str, str]]) -> list[str]:
    return _md_table(["Key", "Value"], [[k, v] for k, v in rows if v not in ("", "—")])


def _contracteval_kpis_lines(kpis: dict) -> list[str]:
    """Render the run-level ContractEval-rubric KPIs (``scores.contracteval_kpis``,
    src/contracteval.py::run_kpis) as grouped tables:

    - **Correctness (ContractEval rubric)** — pooled confusion over the
      per-CUAD-category synthesized answers: accuracy, precision/recall, F1,
      the recall-weighted F2, and the "no related clause" / false-"no related
      clause" rates (the tracking axes for a one-pass extractor — precision
      is structurally 1.0, so recall / F2 / false-nr discriminate).
    - **Output effectiveness** — mean/median token-set Jaccard over the
      positive (document, category) pairs (ContractEval's ``Evaluation.py``).
    - **Semantic coverage bands** — best predicted-span containment against
      the GT label per positive pair: verbatim (ContractEval's rule) and the
      >=0.7/0.5/0.3 bands, separating paraphrase penalty from missing
      extraction.
    """
    lines: list[str] = []

    rows: list[tuple[str, str]] = []
    for key, label in (
        ("n_pairs", "Pairs (docs × categories)"),
        ("n_positive", "Positive pairs (GT category present)"),
        ("accuracy", "Accuracy"),
        ("precision", "Precision"),
        ("recall", "Recall"),
        ("f1", "F1"),
        ("f2", "F2 (recall-weighted)"),
        ("no_related_rate", "No-related-clause rate"),
        ("false_no_related_rate", "False no-related-clause rate"),
        ("n_docs", "Docs scored"),
        ("n_unjoined", "Docs unjoined (GT)"),
    ):
        if kpis.get(key) is not None:
            rows.append((label, _fmt(kpis[key])))
    if rows:
        lines.append("**ContractEval-rubric KPIs (KANBAN-054) — pooled confusion over the synthesized per-category answers; TP = every GT label span verbatim-contained; precision is structurally 1.0 for a one-pass extractor — recall / F2 / false-nr / Jaccard are the discriminating axes**")
        lines.append("")
        lines.extend(_md_table(["Metric", "Value"], rows))
        lines.append("")

    j_rows: list[tuple[str, str]] = []
    for key, label in (("jaccard_mean", "Jaccard (mean)"),
                       ("jaccard_median", "Jaccard (median)")):
        if kpis.get(key) is not None:
            j_rows.append((label, _fmt(kpis[key])))
    if j_rows:
        lines.append("**Output effectiveness — token-set Jaccard over positive pairs (ContractEval Evaluation.py)**")
        lines.append("")
        lines.extend(_md_table(["Metric", "Value"], j_rows))
        lines.append("")

    semantic = kpis.get("semantic") or {}
    if semantic:
        s_rows = [["Verbatim", _fmt(semantic.get("verbatim"))],
                  [">= 0.7", _fmt(semantic.get("ge0_7"))],
                  [">= 0.5", _fmt(semantic.get("ge0_5"))],
                  [">= 0.3", _fmt(semantic.get("ge0_3"))]]
        lines.append(f"**Semantic coverage bands — best predicted-span containment vs GT label (n_pos {semantic.get('n_pos', 0)})**")
        lines.append("")
        lines.extend(_md_table(["Containment", "Share"], s_rows))
        lines.append("")
    return lines


def _nested_scores_tables(scores: dict, heading: str) -> list[str]:
    """Render scalar scores inline and nested score dicts as their own tables.

    Returns lines for: a main ``Score | Value`` table of the run-level scalars
    (when present), then one breakdown table per nested dict (per_field,
    entity_list_f1, ...), scalars first so the headline numbers lead.
    """
    lines: list[str] = []
    scalar: list[tuple[str, str]] = []
    nested: list[tuple[str, dict]] = []
    for key, value in scores.items():
        if key == "diagnostics":
            continue  # rendered by _diagnostics_lines, not flattened here
        if key == "contracteval_kpis":
            continue  # rendered by _contracteval_kpis_lines, not flattened here
        if isinstance(value, dict):
            nested.append((key, value))
        else:
            scalar.append((key, _fmt(value)))
    if scalar:
        lines.extend(_md_table(["Score", "Value"], scalar))
        lines.append("")
    for key, value in nested:
        sub = _md_table(["Field", "Score"],
                        [[k, _fmt(v)] for k, v in sorted(value.items())])
        lines.append(f"**{heading} — {key}**")
        lines.append("")
        lines.extend(sub)
        lines.append("")
    return lines


def _diagnostics_lines(diagnostics: dict) -> list[str]:
    """Render the run-level extraction diagnostics (``src/metrics.py``) as
    grouped tables, each with its own scientific reading:

    - **List quality** — raw (not GT-coverage) precision/recall/F1 over the
      entity-list bipartite match: macro over ``key_obligations`` plus the
      span-pooled micro numbers, and the per-field raw ratios.
    - **Regression error** — mean/median absolute error (MAE) and
      coefficient of determination (R²) for dates, durations and money
      amounts vs the ground truth (master-labels answers preferred), with
      the pair counts each number rests on, plus per-field buckets.
    - **Span-count drift** — symmetric MAE of the item-count delta and its
      signed mean (positive = systematic over-extraction).
    - **Error decomposition** — share of scored (doc, field) pairs at
      exact / partial / miss, with per-field rates + population share.
    """
    lines: list[str] = []

    def _kv(key: str, label: str) -> None:
        if diagnostics.get(key) is not None:
            _rows.append((label, _fmt(diagnostics[key])))

    # 1. List quality -----------------------------------------------------
    _rows: list[tuple[str, str]] = []
    for key, label in (
        ("list_precision", "Precision (macro, key_obligations)"),
        ("list_recall", "Recall (macro)"),
        ("list_f1", "F1 (macro)"),
        ("list_micro_precision", "Precision (micro, span-pooled)"),
        ("list_micro_recall", "Recall (micro)"),
        ("list_micro_f1", "F1 (micro)"),
    ):
        _kv(key, label)
    if diagnostics.get("list_micro_n_predicted") is not None:
        _rows.append(("Pooled items (predicted/expected/matched)",
                      f"{_fmt(diagnostics['list_micro_n_predicted'])} / "
                      f"{_fmt(diagnostics['list_micro_n_expected'])} / "
                      f"{_fmt(diagnostics['list_micro_matched'])}"))
    if _rows:
        lines.append("**List quality — raw precision/recall/F1 (bipartite match ≥ 0.6); GT-coverage fields score recall-of-labels, these are the raw matched-item ratios**")
        lines.append("")
        lines.extend(_md_table(["Metric", "Value"], _rows))
        lines.append("")
        per_field = sorted(set(
            (diagnostics.get("entity_list_precision") or {}).keys()) | set(
            (diagnostics.get("entity_list_recall") or {}).keys()) | set(
            (diagnostics.get("entity_list_raw_f1") or {}).keys()))
        if per_field:
            lines.extend(_md_table(
                ["Field", "Precision", "Recall", "F1 (raw)"],
                [[f,
                  _fmt((diagnostics.get("entity_list_precision") or {}).get(f)),
                  _fmt((diagnostics.get("entity_list_recall") or {}).get(f)),
                  _fmt((diagnostics.get("entity_list_raw_f1") or {}).get(f))]
                 for f in per_field]))
            lines.append("")

    # 2. Regression error -------------------------------------------------
    domains = (
        ("Date", "date_mae_days", "date_median_ae_days", "date_r2", "date_n_pairs"),
        ("Duration", "duration_mae_days", "duration_median_ae_days",
         "duration_r2", "duration_n_pairs"),
        ("Money", "money_mae_usd", "money_median_ae_usd", None, "money_n_pairs"),
    )
    reg_rows: list[list[str]] = []
    for label, mae, med, r2, n in domains:
        if diagnostics.get(mae) is None:
            continue
        reg_rows.append([label,
                         _fmt(diagnostics[mae]),
                         _fmt(diagnostics.get(med)),
                         _fmt(diagnostics.get(r2)),
                         _fmt(diagnostics.get(n))])
    if reg_rows:
        lines.append("**Regression error vs ground truth** — MAE/R² computed only over (predicted, expected) pairs where both sides parse; R² = 1 − SS_res/SS_tot (1.0 perfect, 0.0 = predicting the mean, negative = worse than the mean); n pairs shows the evidence behind each row")
        lines.append("")
        lines.extend(_md_table(["Domain", "MAE", "Median AE", "R²", "n pairs"], reg_rows))
        lines.append("")
        per_field = sorted(set(
            (diagnostics.get("date_mae_per_field") or {}).keys()) | set(
            (diagnostics.get("duration_mae_per_field") or {}).keys()) | set(
            (diagnostics.get("money_mae_per_field") or {}).keys()))
        if per_field:
            rows = []
            for field in per_field:
                for domain, mae_key, r2_key in (
                        ("date", "date_mae_per_field", "date_r2_per_field"),
                        ("duration", "duration_mae_per_field", "duration_r2_per_field"),
                        ("money", "money_mae_per_field", None)):
                    mae_val = (diagnostics.get(mae_key) or {}).get(field)
                    if mae_val is None:
                        continue
                    r2_val = (diagnostics.get(r2_key) or {}).get(field) if r2_key else None
                    rows.append([field, domain, _fmt(mae_val), _fmt(r2_val)])
            lines.extend(_md_table(["Field", "Domain", "MAE", "R²"], rows))
            lines.append("")

    # 3. Span-count drift -------------------------------------------------
    _rows = []
    for key, label in (
        ("span_count_mae", "MAE (items per document)"),
        ("span_count_signed_mean", "Signed mean (positive = over-extraction)"),
        ("span_count_n_docs", "Documents"),
    ):
        _kv(key, label)
    if _rows:
        lines.append("**Span-count drift (list fields)** — how far the model's item counts drift from the annotator's, in items")
        lines.append("")
        lines.extend(_md_table(["Metric", "Value"], _rows))
        lines.append("")
        fields = sorted(set(
            (diagnostics.get("span_count_mae_per_field") or {}).keys()) | set(
            (diagnostics.get("span_count_signed_mean_per_field") or {}).keys()))
        if fields:
            lines.extend(_md_table(
                ["Field", "MAE", "Signed mean"],
                [[f,
                  _fmt((diagnostics.get("span_count_mae_per_field") or {}).get(f)),
                  _fmt((diagnostics.get("span_count_signed_mean_per_field") or {}).get(f))]
                 for f in fields]))
            lines.append("")

    # 4. Error decomposition ----------------------------------------------
    _rows = []
    for key, label in (
        ("field_exact_rate", "Exact (score = 1.0)"),
        ("field_partial_rate", "Partial (0 < score < 1)"),
        ("field_miss_rate", "Miss (score = 0.0)"),
        ("n_fields_scored", "Scored (doc, field) pairs"),
    ):
        _kv(key, label)
    if _rows:
        lines.append("**Field-level error decomposition** — per-field content scores binned into exact / partial / miss")
        lines.append("")
        lines.extend(_md_table(["Band", "Share"], _rows))
        lines.append("")
        decomposition = diagnostics.get("error_decomposition") or {}
        presence = diagnostics.get("field_presence_per_field") or {}
        if decomposition:
            lines.extend(_md_table(
                ["Field", "exact", "partial", "miss", "presence"],
                [[f,
                  _fmt((d or {}).get("exact_rate")),
                  _fmt((d or {}).get("partial_rate")),
                  _fmt((d or {}).get("miss_rate")),
                  _fmt(presence.get(f))]
                 for f, d in sorted(decomposition.items())]))
            lines.append("")

    if not lines:
        return lines
    lines.insert(0, "### Run-level diagnostics")
    lines.insert(1, "")
    return lines


def _confusion_matrix_lines(
    title: str, matrix: dict[str, dict[str, int]], classes: list[str],
) -> list[str]:
    """Render an expected-vs-predicted confusion matrix (diagonal bolded)."""
    lines = [f"**{title}**", "",
             "| expected \\ predicted | " + " | ".join(classes) + " |",
             "|" + "---|" * (len(classes) + 1)]
    for expected in classes:
        row = matrix.get(expected, {})
        cells = []
        for predicted in classes:
            count = row.get(predicted, 0)
            cells.append(f"**{count}**" if expected == predicted and count else str(count))
        lines.append("| " + expected + " | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _row_extractor_scores(results: list[dict]) -> list[dict]:
    """Unwrap chained rows' nested ``extractor_scores`` into top-level shape.

    Chained runs (sorter -> extractor) store every extractor score inside
    ``row["extractor_scores"]``; this returns those dicts so the shared
    scoring-calculation tables (field matrix, F1, audit, category presence)
    render for both extraction-only and chained records.
    """
    out = []
    for row in results:
        nested = row.get("extractor_scores")
        out.append(nested if isinstance(nested, dict) else row)
    return out


def _field_score_matrix(results: list[dict], bucket: str, title: str) -> list[str]:
    """Render a rows-as-documents x columns-as-fields score matrix.

    The cell is each document's score for that field; the final column is the
    per-field mean. This is the full per-document scoring calculation in one
    table.
    """
    fields: list[str] = []
    for row in results:
        values = row.get(bucket) or {}
        for field in values:
            if field not in fields:
                fields.append(field)
    if not fields:
        return []
    fields.sort()
    headers = ["Field"] + [f"d{i + 1}" for i in range(len(results))] + ["mean"]
    rows: list[list[str]] = []
    for field in fields:
        cells = []
        values = []
        for row in results:
            value = (row.get(bucket) or {}).get(field)
            cells.append(_fmt(value))
            if isinstance(value, (int, float)):
                values.append(float(value))
        cells.append(_fmt(mean(values)))
        rows.append([field] + cells)
    lines = [f"**{title}**", ""]
    lines.extend(_md_table(headers, rows))
    lines.append("")
    return lines


def _audit_summary_lines(results: list[dict]) -> list[str]:
    """Aggregate the per-row factuality audit into one per-field table."""
    fields: list[str] = []
    totals: dict[str, dict] = {}
    for row in results:
        for field, audit in (row.get("entity_list_audit") or {}).items():
            if field not in totals:
                totals[field] = {"n_predicted": 0, "matched_gt": 0,
                                 "verified_in_doc": 0, "hallucinated": 0,
                                 "verified_precision": []}
                fields.append(field)
            b = totals[field]
            b["n_predicted"] += int(audit.get("n_predicted") or 0)
            b["matched_gt"] += int(audit.get("matched_gt") or 0)
            b["verified_in_doc"] += int(audit.get("verified_in_doc") or 0)
            b["hallucinated"] += int(audit.get("hallucinated") or 0)
            if audit.get("verified_precision") is not None:
                b["verified_precision"].append(float(audit["verified_precision"]))
    if not fields:
        return []
    fields.sort()
    lines = ["**Factuality audit (aggregated over documents)**", "",
             "| field | n_predicted | matched_gt | verified_in_doc | hallucinated | "
             "verified_precision | hallucination_rate |",
             "|---|---|---|---|---|---|---|"]
    for field in fields:
        b = totals[field]
        lines.append(f"| {field} | {b['n_predicted']} | {b['matched_gt']} | "
                     f"{b['verified_in_doc']} | {b['hallucinated']} | "
                     f"{_fmt(mean(b['verified_precision']))} | "
                     f"{_fmt(1.0 - mean(b['verified_precision']) if b['verified_precision'] else None)} |")
    lines.append("")
    return lines


def _category_presence_lines(results: list[dict]) -> list[str]:
    """Aggregate per-row CUAD YES/NO category presence into one table."""
    per_category: dict[str, dict] = {}
    for row in results:
        for category, detail in (row.get("category_presence_detail") or {}).items():
            if not isinstance(detail, dict):
                continue
            bucket = per_category.setdefault(
                category, {"expected": 0, "matched": 0, "field": detail.get("field", "")})
            if detail.get("expected"):
                bucket["expected"] += 1
            if detail.get("matched"):
                bucket["matched"] += 1
    if not per_category:
        return []
    lines = ["**CUAD category presence (aggregated over documents)**", "",
             "| category | field | expected (docs) | matched (docs) | presence |",
             "|---|---|---|---|---|"]
    for category, bucket in sorted(per_category.items()):
        presence = bucket["matched"] / bucket["expected"] if bucket["expected"] else None
        lines.append(f"| {category} | {bucket['field']} | {bucket['expected']} | "
                     f"{bucket['matched']} | {_fmt(presence)} |")
    lines.append("")
    return lines


def _confusion_from_pairs(
    pairs: list[tuple[str, str]], title: str,
) -> list[str]:
    """Build and render a confusion matrix from (expected, predicted) pairs."""
    classes = sorted({e for e, _ in pairs} | {p for _, p in pairs if p})
    matrix: dict[str, dict[str, int]] = {c: {c2: 0 for c2 in classes} for c in classes}
    for expected, predicted in pairs:
        if not predicted:
            continue
        if expected not in matrix:
            matrix[expected] = {c2: 0 for c2 in classes}
        if predicted not in matrix[expected]:
            matrix[expected][predicted] = 0
        matrix[expected][predicted] += 1
    return _confusion_matrix_lines(title, matrix, classes)


def _load_judgments(experiment_name: str) -> list[dict]:
    """Load the post-hoc judge judgments for an experiment, if any."""
    path = JUDGMENTS_DIR / f"{experiment_name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in open(path) if line.strip()]


def experiment_markdown(record: dict) -> str:
    """Render a readable, fully-expanded section for one experiment record.

    The section covers: run metadata, data source, parameters, token usage,
    every score (with per-field breakdowns), the per-document results table,
    the full per-document x per-field scoring matrix, entity-list F1, the
    factuality audit, CUAD category presence, confusion matrices (expected vs
    predicted), and the model's raw outputs per document — all as tables, no
    raw JSON dumps.
    """
    lines: list[str] = []
    name = record.get("experiment_name") or record.get("name") or "experiment"
    task = record.get("task", "")
    lines.append(f"## {name}" + (f"  ({task})" if task else ""))
    lines.append("")

    # ---------------------------------------------------------------- metadata
    meta: list[tuple[str, str]] = []
    if record.get("timestamp"):
        meta.append(("Timestamp", _fmt(record["timestamp"])))
    if record.get("model"):
        meta.append(("Model", record["model"]))
    for key in ("prompt_version", "prompt_versions"):
        if record.get(key):
            meta.append(("Prompt version", _fmt(record[key], max_len=200)))
    if record.get("git"):
        git = record["git"]
        dirty = " (dirty tree)" if git.get("dirty") else ""
        meta.append(("Git commit", f"`{git.get('commit') or '?'}`{dirty}"))
    for key, label in (("n_rows", "Rows"), ("n_ok", "Completed"), ("n_error", "Errors")):
        if record.get(key) is not None:
            meta.append((label, _fmt(record[key])))
    if meta:
        lines.append("### Run metadata")
        lines.append("")
        lines.extend(_kv_table(meta))
        lines.append("")

    # ------------------------------------------------------------ data source
    data_source = record.get("data_source") or {}
    if data_source:
        lines.append("### Data source")
        lines.append("")
        lines.extend(_kv_table([(k, _fmt(v, max_len=160)) for k, v in data_source.items()]))
        lines.append("")

    # -------------------------------------------------------------- parameters
    parameters = record.get("parameters") or {}
    if parameters:
        lines.append("### Parameters")
        lines.append("")
        lines.extend(_kv_table([(k, _fmt(v)) for k, v in parameters.items()]))
        lines.append("")

    # ----------------------------------------------------------------- tokens
    tokens = record.get("tokens") or {}
    if tokens:
        lines.append("### Token usage")
        lines.append("")
        stages = []
        if all(k in tokens for k in ("sorter", "extractor", "total")):
            stages = ["sorter", "extractor", "total"]
        elif all(k in tokens for k in ("sorter", "extractor")):
            stages = ["sorter", "extractor"]
        else:
            stages = [None]
        header = (["Stage"] + ["Prompt", "Completion", "Total", "Mean cost $", "Total cost $"])
        table_rows = []
        for stage in stages:
            bucket = tokens if stage is None else tokens[stage]
            if not isinstance(bucket, dict):
                continue
            label = "all" if stage is None else stage
            table_rows.append([
                label,
                _fmt(bucket.get("prompt_tokens")),
                _fmt(bucket.get("completion_tokens")),
                _fmt(bucket.get("total_tokens")),
                _fmt(bucket.get("cost_usd")),
                _fmt(bucket.get("cost_total_usd")),
            ])
        lines.extend(_md_table(header, table_rows))
        lines.append("")

    # ----------------------------------------------------------------- scores
    scores = record.get("scores") or {}
    if scores:
        lines.append("### Scores")
        lines.append("")
        if "sorter" in scores and "extractor" in scores:
            for stage in ("sorter", "extractor"):
                if isinstance(scores[stage], dict):
                    lines.extend(_nested_scores_tables(scores[stage], f"**Scores — {stage}**"))
        else:
            lines.extend(_nested_scores_tables(scores, "Scores"))
        lines.append("")

    # ---------------------------------------------------------- diagnostics
    # Run-level extraction diagnostics (list quality, MAE/R² vs ground
    # truth, span-count drift, error decomposition) — src/metrics.py.
    if task == "contract_entity_extraction":
        diagnostics = scores.get("diagnostics")
        if isinstance(diagnostics, dict) and diagnostics:
            lines.extend(_diagnostics_lines(diagnostics))
            lines.append("")
        # ContractEval-rubric KPIs (F1/F2/Jaccard/false-nr + semantic bands) —
        # src/contracteval.py::run_kpis (KANBAN-054).
        kpis = scores.get("contracteval_kpis")
        if isinstance(kpis, dict) and kpis:
            lines.extend(_contracteval_kpis_lines(kpis))
            lines.append("")

    # -------------------------------------------------- docclass subclass depth
    # Per-subclass accuracy (the second-level dimension, with support counts),
    # equivalence recovery, and the input-mode split (text/vision/fallback) —
    # the docclass mirror of the subtype surface's per-class + equiv reporting.
    if task in ("docclass_classification", "correspondence_classification"):
        per_sub = scores.get("per_subclass_accuracy")
        support = scores.get("per_subclass_support")
        if isinstance(per_sub, dict) and per_sub:
            lines.append("### Per-subclass accuracy (second-level dimension)")
            lines.append("")
            lines.extend(_md_table(
                ["subclass", "accuracy", "support (rows with GT)"],
                [[k, _fmt(per_sub[k]), support.get(k) if isinstance(support, dict) else None]
                 for k in sorted(per_sub)],
            ))
            lines.append("")
        equiv = scores.get("subclass_accuracy_equiv")
        if equiv is not None:
            lines.append(f"- subclass_accuracy_equiv: {equiv} — strict subclass OR a "
                         f"defensible equivalent family (mixed_cash_stock ↔ "
                         f"mixed_cash_stock_election); equiv-recovered rows: "
                         f"{', '.join(scores.get('equiv_recovered') or []) or 'none'}")
            lines.append("")
        mode_counts = scores.get("input_mode_counts")
        if isinstance(mode_counts, dict) and mode_counts:
            lines.append(f"- input-mode split: {', '.join(f'{k} {v}' for k, v in mode_counts.items())}")
            lines.append("")
        if task == "correspondence_classification":
            per_sent = scores.get("per_sentiment_accuracy")
            sent_support = scores.get("per_sentiment_support")
            if isinstance(per_sent, dict) and per_sent:
                lines.append("### Per-sentiment-label accuracy")
                lines.append("")
                lines.extend(_md_table(
                    ["sentiment_label", "accuracy", "support"],
                    [[k, _fmt(per_sent[k]),
                      sent_support.get(k) if isinstance(sent_support, dict) else None]
                     for k in sorted(per_sent)],
                ))
                lines.append("")
            if scores.get("sentiment_score_mae") is not None:
                lines.append(
                    f"- sentiment_score_mae: {_fmt(scores.get('sentiment_score_mae'))} "
                    f"(band {_fmt(scores.get('sentiment_score_band'))}; "
                    f"sentiment_score_ok {_fmt(scores.get('sentiment_score_ok'))})"
                )
                lines.append("")

    # ----------------------------------------------------------------- results
    results = record.get("results") or []
    if results:
        lines.append("### Per-document results")
        lines.append("")
        first = results[0]
        if task == "correspondence_classification":
            header = ["#", "Document", "Status", "doc_type", "subclass",
                      "expected subclass", "doc_type ok", "subclass ok",
                      "sent. label", "expected sent.", "sent. ok",
                      "sent. score", "sent. MAE", "confidence",
                      "failure mode", "error"]
            rows = []
            for i, row in enumerate(results):
                sorter = row.get("sorter") or {}
                rows.append([
                    f"d{i + 1}",
                    _fmt(row.get("filename"), max_len=90),
                    row.get("status", "—"),
                    _fmt(sorter.get("doc_type")),
                    _fmt(sorter.get("doc_subclass")),
                    _fmt(sorter.get("expected_subclass")),
                    _fmt(sorter.get("doc_type_ok")),
                    _fmt(sorter.get("subclass_ok")),
                    _fmt(sorter.get("sentiment_label")),
                    _fmt(sorter.get("expected_sentiment_label")),
                    _fmt(sorter.get("sentiment_label_ok")),
                    _fmt(sorter.get("sentiment_score")),
                    _fmt(sorter.get("sentiment_score_mae")),
                    _fmt(sorter.get("confidence")),
                    _fmt(sorter.get("failure_mode")),
                    _fmt(row.get("error")),
                ])
        elif task == "docclass_classification":
            # Hierarchical doc-class shape: the second-level doc_subclass
            # dimension is scored + rendered per document (KANBAN-033).
            header = ["#", "Document", "Status", "doc_type", "subclass",
                      "expected subclass", "doc_type ok", "subclass ok",
                      "subclass ok equiv", "input mode", "confidence",
                      "failure mode", "error"]
            rows = []
            for i, row in enumerate(results):
                sorter = row.get("sorter") or {}
                rows.append([
                    f"d{i + 1}",
                    _fmt(row.get("filename"), max_len=90),
                    row.get("status", "—"),
                    _fmt(sorter.get("doc_type")),
                    _fmt(sorter.get("doc_subclass")),
                    _fmt(sorter.get("expected_subclass")),
                    _fmt(sorter.get("doc_type_ok")),
                    _fmt(sorter.get("subclass_ok")),
                    _fmt(sorter.get("subclass_ok_equiv")),
                    _fmt(sorter.get("input_mode")),
                    _fmt(sorter.get("confidence")),
                    _fmt(sorter.get("failure_mode")),
                    _fmt(row.get("error")),
                ])
        elif task == "subtype_classification" or (
                "sorter" in first and "extractor_scores" not in first):
            # Sorter-only subtype classification shape.
            header = ["#", "Document", "Status", "doc_type", "subtype",
                      "expected subtype", "doc_type ok", "subtype ok",
                      "equiv ok", "confidence", "failure mode", "error"]
            rows = []
            for i, row in enumerate(results):
                sorter = row.get("sorter") or {}
                rows.append([
                    f"d{i + 1}",
                    _fmt(row.get("filename"), max_len=90),
                    row.get("status", "—"),
                    _fmt(sorter.get("doc_type")),
                    _fmt(sorter.get("contract_subtype")),
                    _fmt(sorter.get("expected_subtype")),
                    _fmt(sorter.get("doc_type_ok")),
                    _fmt(sorter.get("subtype_ok")),
                    _fmt(sorter.get("subtype_ok_equiv")),
                    _fmt(sorter.get("confidence")),
                    _fmt(sorter.get("failure_mode")),
                    _fmt(row.get("error")),
                ])
        elif "sorter" in first and "extractor_scores" in first:
            header = ["#", "Document", "Status", "doc_type", "subtype",
                      "subtype ok", "confidence", "extraction score",
                      "field presence", "error"]
            rows = []
            for i, row in enumerate(results):
                sorter = row.get("sorter") or {}
                extractor = row.get("extractor_scores") or {}
                rows.append([
                    f"d{i + 1}",
                    _fmt(row.get("filename"), max_len=90),
                    row.get("status", "—"),
                    _fmt(sorter.get("doc_type")),
                    _fmt(sorter.get("contract_subtype")),
                    _fmt(sorter.get("subtype_ok")),
                    _fmt(sorter.get("confidence")),
                    _fmt(extractor.get("overall_score")),
                    _fmt(extractor.get("field_presence")),
                    _fmt(row.get("error")),
                ])
        elif "expected" in first or (
                "predicted" in first and not isinstance(first.get("predicted"), dict)):
            header = ["#", "Document", "Status", "Expected", "Predicted",
                      "Correct", "Cost $", "Error"]
            rows = []
            for i, row in enumerate(results):
                rows.append([
                    f"d{i + 1}",
                    _fmt(row.get("filename"), max_len=90),
                    row.get("status", "—"),
                    _fmt(row.get("expected")),
                    _fmt(row.get("predicted")),
                    _fmt(row.get("correct")),
                    _fmt(row.get("cost_usd")),
                    _fmt(row.get("error")),
                ])
        else:
            header = ["#", "Document", "Status", "Overall", "Field presence",
                      "Schema valid", "Category presence", "Ambiguous", "Error"]
            rows = []
            for i, row in enumerate(results):
                rows.append([
                    f"d{i + 1}",
                    _fmt(row.get("filename"), max_len=90),
                    row.get("status", "—"),
                    _fmt(row.get("overall_score")),
                    _fmt(row.get("field_presence")),
                    _fmt(row.get("schema_valid")),
                    _fmt(row.get("category_presence")),
                    _fmt(row.get("ambiguous_fields") or None),
                    _fmt(row.get("error")),
                ])
        lines.extend(_md_table(header, rows))
        lines.append("")

        # ------------------------------------------- full scoring calculations
        if "sorter" in first and "extractor_scores" in first:
            score_rows = _row_extractor_scores(results)
        else:
            score_rows = results
        if any("field_scores" in row for row in score_rows):
            lines.extend(_field_score_matrix(score_rows, "field_scores",
                                             "Per-field content scores (document x field)"))
        if any("entity_list_f1" in row for row in score_rows):
            lines.extend(_field_score_matrix(score_rows, "entity_list_f1",
                                             "Entity-list F1 / ground-truth coverage (document x field)"))
        if any("entity_list_audit" in row for row in score_rows):
            lines.extend(_audit_summary_lines(score_rows))
        if any("category_presence_detail" in row for row in score_rows):
            lines.extend(_category_presence_lines(score_rows))

        # ------------------------------------------------- confusion matrices
        if "expected" in first and "predicted" in first:
            pairs = [(str(row.get("expected")), str(row.get("predicted")))
                     for row in results
                     if row.get("expected") is not None and row.get("predicted")]
            if pairs:
                lines.extend(_confusion_from_pairs(pairs, "Confusion matrix (expected x predicted)"))

        sorter_pairs = [
            (str((row.get("sorter") or {}).get("expected_subtype")),
             str((row.get("sorter") or {}).get("contract_subtype")))
            for row in results if row.get("sorter")
        ]
        if sorter_pairs and any(e for e, _ in sorter_pairs):
            lines.extend(_confusion_from_pairs(
                sorter_pairs, "Sorter contract-subtype confusion matrix (expected x predicted)"))

        # ------------------------------------------------------- model outputs
        if "sorter" in first:
            lines.append("### Sorter outputs")
            lines.append("")
            lines.extend(_md_table(
                ["#", "doc_type", "subtype", "expected subtype", "confidence",
                 "doc_type ok", "subtype ok", "reasoning"],
                [[f"d{i + 1}",
                  _fmt((row.get("sorter") or {}).get("doc_type")),
                  _fmt((row.get("sorter") or {}).get("contract_subtype")),
                  _fmt((row.get("sorter") or {}).get("expected_subtype")),
                  _fmt((row.get("sorter") or {}).get("confidence")),
                  _fmt((row.get("sorter") or {}).get("doc_type_ok")),
                  _fmt((row.get("sorter") or {}).get("subtype_ok")),
                  _fmt((row.get("sorter") or {}).get("reasoning"), max_len=180)]
                 for i, row in enumerate(results)]))
            lines.append("")
            lines.append("### Predicted extractions (specialist output per document)")
            lines.append("")
            lines.extend(_md_table(
                ["#", "Field", "Extracted value"],
                [[f"d{i + 1}", field, _fmt(value, max_len=220)]
                 for i, row in enumerate(results)
                 for field, value in ((row.get("extractor_scores") or {}).get("predicted") or {}).items()]))
            lines.append("")
        elif isinstance(first.get("predicted"), dict):
            lines.append("### Predicted extractions (specialist output per document)")
            lines.append("")
            lines.extend(_md_table(
                ["#", "Field", "Extracted value"],
                [[f"d{i + 1}", field, _fmt(value, max_len=220)]
                 for i, row in enumerate(results)
                 for field, value in (row.get("predicted") or {}).items()]))
            lines.append("")
        elif "predicted" in first:
            lines.append("### Predicted outputs")
            lines.append("")
            lines.extend(_md_table(
                ["#", "Expected", "Predicted", "Correct"],
                [[f"d{i + 1}",
                  _fmt(row.get("expected")),
                  _fmt(row.get("predicted")),
                  _fmt(row.get("correct"))]
                 for i, row in enumerate(results)]))
            lines.append("")

    # ------------------------------------------- subtype accuracy by class
    if task == "subtype_classification":
        per_subtype = (record.get("scores") or {}).get("sorter", {}).get("per_subtype") or {}
        if per_subtype:
            lines.append("### Subtype classification accuracy by class")
            lines.append("")
            lines.extend(_md_table(
                ["Subtype", "Correct", "Correct (equiv)", "Total",
                 "Accuracy", "Accuracy (equiv)"],
                [[_fmt(k), _fmt(v.get("correct")), _fmt(v.get("equiv")),
                  _fmt(v.get("total")), _fmt(v.get("accuracy")),
                  _fmt(v.get("accuracy_equiv"))]
                 for k, v in sorted(per_subtype.items())]))
            lines.append("")

        # -------------------------------- failed-classification insights
        insights = (record.get("scores") or {}).get("sorter", {}).get("failure_insights") or {}
        failures = insights.get("failures") or []
        if failures:
            lines.append("### Failed classification insights")
            lines.append("")
            lines.append("The model's own reasoning on every failed row — the "
                         "evidence it cited for the wrong family, and the failure "
                         "mode that explains WHY it missed:")
            lines.append("")
            mode_counts = insights.get("mode_counts") or {}
            if mode_counts:
                lines.extend(_md_table(
                    ["Failure mode", "Count"],
                    [[_fmt(k), _fmt(v)] for k, v in sorted(mode_counts.items())]))
                lines.append("")
            for i, f in enumerate(failures):
                lines.append(f"**{i + 1}. {_fmt(f.get('filename'), max_len=110)}** — "
                             f"expected `{f.get('expected')}` vs predicted "
                             f"`{f.get('predicted')}` "
                             f"({f.get('doc_type')}, conf {_fmt(f.get('confidence'))}) "
                             f"— mode: `{f.get('mode')}`"
                             f"{' — RECOVERED by family equivalence' if f.get('equiv_recovered') else ''}")
                lines.append("")
                lines.append(f"> {_fmt(f.get('reasoning'), max_len=4000)}")
                lines.append("")

    # --------------------------------------- judge agent review (post hoc)
    judgments = _load_judgments(name)
    if judgments:
        lines.append("### Judge agent review (post hoc)")
        lines.append("")
        lines.append("The offline JudgeAgent audited every failed classification "
                     "against the source document — is the sorter's pick the best "
                     "fit for THIS document, independent of the CUAD folder?")
        lines.append("")
        summary: dict[str, int] = {}
        for entry in judgments:
            label = (entry.get("judgment") or {}).get("classification_correct", "?")
            summary[label] = summary.get(label, 0) + 1
        lines.extend(_md_table(["Judgment", "Count"],
                               [[_fmt(k), _fmt(v)] for k, v in sorted(summary.items())]))
        lines.append("")
        for i, entry in enumerate(judgments):
            judgment = entry.get("judgment") or {}
            lines.append(f"**{i + 1}. {_fmt(entry.get('filename'), max_len=110)}** — "
                         f"expected `{entry.get('expected_subtype')}` vs predicted "
                         f"`{entry.get('predicted_subtype')}` — judge: "
                         f"**{_fmt(judgment.get('classification_correct'))}** "
                         f"(quality {_fmt(judgment.get('classification_quality'))})")
            lines.append("")
            if judgment.get("reasoning"):
                lines.append(f"> {_fmt(judgment.get('reasoning'), max_len=2000)}")
                lines.append("")

    return "\n".join(lines)


def render_full_log(records: list[dict], title: str = "Experiment Log") -> str:
    """Render the whole experiment history as one readable markdown document.

    A title, a generated-at stamp, and an index table of every experiment
    precede the per-experiment sections (``experiment_markdown``). Used by
    ``scripts/reporting/render_experiment_log.py`` to rebuild the markdown log
    from the append-only JSONL source of truth.
    """
    from datetime import datetime, timezone as _tz

    lines = [f"# {title}", "",
             f"_Generated from `reports/experiment_log.jsonl` on "
             f"{datetime.now(_tz.utc).isoformat()} — append-only, one section per run._",
             ""]

    index_rows: list[list[str]] = []
    for i, record in enumerate(records, start=1):
        scores = record.get("scores") or {}
        headline = None
        if isinstance(scores.get("overall_extraction_score"), (int, float)):
            headline = f"extraction {scores['overall_extraction_score']:.4f}"
        elif isinstance(scores.get("exact_match"), (int, float)):
            headline = f"exact_match {scores['exact_match']:.4f}"
        elif isinstance(scores.get("extractor"), dict) and isinstance(
                scores["extractor"].get("overall_extraction_score"), (int, float)):
            headline = (f"sorter {_fmt(scores.get('sorter', {}).get('exact_match'))} / "
                        f"extractor {scores['extractor']['overall_extraction_score']:.4f}")
        elif isinstance(scores.get("accuracy"), (int, float)):
            # LegalBench suite tasks (legalbench/ in llm-mailroom).
            detail = ""
            if isinstance(scores.get("macro_f1"), (int, float)):
                detail = f" · macro-F1 {_fmt(scores['macro_f1'])}"
            elif isinstance(scores.get("macro_category_accuracy"), (int, float)):
                detail = f" · macro {_fmt(scores['macro_category_accuracy'])}"
            elif isinstance(scores.get("accuracy_equiv"), (int, float)):
                detail = f" · equiv {_fmt(scores['accuracy_equiv'])}"
            headline = f"accuracy {scores['accuracy']:.4f}{detail}"
        prompt = record.get("prompt_version")
        if not prompt and isinstance(record.get("prompt_versions"), dict):
            prompt = " + ".join(str(v) for v in record["prompt_versions"].values())
        tokens = record.get("tokens") or {}
        total_tokens = (tokens.get("total") or {}).get("total_tokens") if "total" in tokens \
            else tokens.get("total_tokens")
        index_rows.append([
            str(i),
            record.get("experiment_name", ""),
            record.get("task", ""),
            record.get("model", ""),
            _fmt(prompt),
            headline or "—",
            _fmt(record.get("n_rows")),
            _fmt(total_tokens),
        ])
    lines.append("## Index")
    lines.append("")
    lines.extend(_md_table(["#", "Experiment", "Task", "Model", "Prompt(s)",
                            "Headline score", "Rows", "Total tokens"], index_rows))
    lines.append("")
    lines.append("---")
    lines.append("")
    for record in records:
        lines.append(experiment_markdown(record))
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def append_markdown(record: dict, path: Path | None = None) -> Path:
    """Append a human-readable section to the markdown experiment log."""
    path = Path(path or default_md_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(experiment_markdown(record))
        if not str(record.get("experiment_name", "")).endswith("\n"):
            fh.write("\n")
    return path
