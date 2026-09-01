#!/usr/bin/env python3
"""Generate a markdown experiment report from Braintrust or the local log.

Fetches the scored task rows of an experiment and writes
``reports/report_<experiment>.md`` containing:

- run metadata (prompt version, model, dataset, experiment id)
- aggregate exact-match + failure counts
- per-class accuracy table
- confusion matrix table (expected x predicted)
- the misclassification ledger: every wrong row with filename, expected,
  predicted, confidence, and reasoning (capped via ``--max-misses``)

Correspondence runs (KANBAN-103) also accept ``--from-log`` so the report
uses the repo experiment log (doc_type + subclass + sentiment scorers)
when Braintrust rows are composite dicts.

Usage:
    python scripts/reporting/report_generator.py --experiment qwen3.7-flash_sorter_v0
    python scripts/reporting/report_generator.py --experiment qwen3.7-flash_sorter_v0 \
        --output-dir reports --max-misses 50
    python scripts/reporting/report_generator.py \\
        --experiment qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42 \\
        --from-log
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.braintrust_config import load_braintrust_config
from src.braintrust_utils import fetch_experiment_rows, find_experiment_by_name, resolve_prompt_version
from src.env_utils import require_env
from src.experiment_log import default_jsonl_path
from src.scorers import ERROR_PREFIX, normalize_label
from src.taxonomy import doc_class_keys

_CONFIG = load_braintrust_config()


def _task_rows(rows: list[dict]) -> list[dict]:
    span_meta: dict[str, dict] = {}
    for row in rows:
        root = row.get("root_span_id") or row.get("span_id") or ""
        metadata = row.get("metadata") or {}
        if isinstance(metadata, dict) and (metadata.get("reasoning") or metadata.get("filename")):
            span_meta.setdefault(root, {}).update(metadata)

    tasks = []
    for row in rows:
        if row.get("expected") is None or row.get("output") is None:
            continue
        root = row.get("root_span_id") or row.get("span_id") or ""
        meta = dict(row.get("metadata") or {})
        meta.update(span_meta.get(root, {}))
        tasks.append({
            "expected": str(row["expected"]).lower(),
            "output": str(row["output"]),
            "input": row.get("input") or {},
            "metadata": meta,
            "metrics": row.get("metrics") or {},
        })
    return tasks


def _filename(input_data) -> str:
    if isinstance(input_data, dict):
        return str(input_data.get("filename") or "")
    return ""


def render_report(experiment_meta: dict, rows: list[dict]) -> str:
    tasks = _task_rows(rows)
    prompt_version = resolve_prompt_version(experiment_meta)
    experiment_id = experiment_meta.get("id", "?")
    classes = doc_class_keys()

    valid = [t for t in tasks if not t["output"].startswith(ERROR_PREFIX)]
    failed = [t for t in tasks if t["output"].startswith(ERROR_PREFIX)]
    correct = sum(1 for t in valid if normalize_label(t["output"]) == t["expected"])
    accuracy = correct / len(valid) if valid else 0.0

    # Per-class
    by_class: dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0})
    for t in valid:
        b = by_class[t["expected"]]
        b["n"] += 1
        b["correct"] += int(normalize_label(t["output"]) == t["expected"])

    # Confusion matrix
    matrix: dict[str, Counter] = {c: Counter() for c in classes}
    for t in valid:
        expected = t["expected"] if t["expected"] in matrix else "unknown"
        matrix[expected][normalize_label(t["output"])] += 1

    # Misclassification ledger
    misses = [
        t for t in valid if normalize_label(t["output"]) != t["expected"]
    ]
    misses.sort(key=lambda t: t["expected"])

    lines = [
        f"# Experiment report — {experiment_meta.get('name', '?')}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Run metadata",
        "",
        f"- experiment id: `{experiment_id}`",
        f"- prompt version: `{prompt_version}`",
        f"- model: `{experiment_meta.get('metadata', {}).get('model', '?')}`",
        f"- dataset: `{experiment_meta.get('metadata', {}).get('dataset', '?')}`",
        f"- dataset size: `{experiment_meta.get('metadata', {}).get('dataset_size', len(tasks))}`",
        "",
        "## Aggregate",
        "",
        f"- rows: **{len(tasks)}**",
        f"- exact_match: **{accuracy:.4f}** ({correct}/{len(valid)})",
        f"- failed rows: **{len(failed)}**",
        "",
        "## Per-class accuracy",
        "",
        "| class | correct | total | accuracy |",
        "|-------|---------|-------|----------|",
    ]
    for cls in classes:
        b = by_class.get(cls, {"n": 0, "correct": 0})
        acc = b["correct"] / b["n"] if b["n"] else "-"
        acc_str = f"{acc:.4f}" if isinstance(acc, float) else "-"
        lines.append(f"| {cls} | {b['correct']} | {b['n']} | {acc_str} |")

    lines += ["", "## Confusion matrix (expected \\ predicted)", "",
              "| expected \\ predicted | " + " | ".join(classes) + " |", "|" + "---|" * (len(classes) + 1)]
    for cls in classes:
        row = matrix[cls]
        lines.append("| " + cls + " | " + " | ".join(str(row.get(c, 0)) for c in classes) + " |")

    lines += ["", "## Misclassification ledger", ""]
    if not misses:
        lines.append("_No misclassifications._")
    else:
        lines.append(f"_{len(misses)} rows; showing up to 100._")
        lines.append("")
        lines.append("| expected | predicted | filename | confidence | reasoning |")
        lines.append("|----------|-----------|----------|------------|-----------|")
        for t in misses[:100]:
            meta = t["metadata"]
            conf = meta.get("confidence")
            conf_str = f"{conf:.3f}" if isinstance(conf, (int, float)) else "-"
            reasoning = str(meta.get("reasoning") or "")[:120].replace("|", "\\|")
            lines.append(f"| {t['expected']} | {normalize_label(t['output'])} | {_filename(t['input'])} | "
                         f"{conf_str} | {reasoning} |")

    lines.append("")
    return "\n".join(lines)


def load_log_record(experiment_name: str, log_path: Path | None = None) -> dict | None:
    """Return the last experiment-log record matching ``experiment_name``."""
    path = log_path or default_jsonl_path()
    if not path.exists():
        return None
    import json
    match = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("experiment_name") == experiment_name:
                match = rec
    return match


def render_correspondence_report(record: dict, *, max_misses: int = 100) -> str:
    """Render a correspondence (doc_type + subclass + sentiment) report.

    Reads the runner's experiment-log record so predicted fields stay locked
    to the Hub GT assortment (``expected`` / ``expected_subclass`` /
    ``sentiment_label`` / ``sentiment_score``).
    """
    scores = record.get("scores") or {}
    prompts = record.get("prompt_versions") or {}
    data = record.get("data_source") or {}
    params = record.get("parameters") or {}
    tokens = (record.get("tokens") or {}).get("total") or {}
    git = record.get("git") or {}
    fi = ((scores.get("sorter") or {}).get("failure_insights") or {})
    failures = list(fi.get("failures") or [])
    per_sub = scores.get("per_subclass_accuracy") or {}
    sub_n = scores.get("per_subclass_support") or {}
    per_sent = scores.get("per_sentiment_accuracy") or {}
    sent_n = scores.get("per_sentiment_support") or {}
    sub_conf = scores.get("subclass_confusion") or {}
    sent_conf = scores.get("sentiment_confusion") or {}

    def _pct(value) -> str:
        if value is None:
            return "—"
        return f"{float(value):.4f}"

    lines = [
        f"# Experiment report — {record.get('experiment_name', '?')}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Run metadata",
        "",
        f"- task: `{record.get('task', 'correspondence_classification')}`",
        f"- prompt version: `{prompts.get('sorter', '?')}`",
        f"- model: `{record.get('model', '?')}`",
        f"- hf_repo: `{data.get('hf_repo', '?')}`",
        f"- dataset size: `{data.get('n_samples', scores.get('n_rows', '?'))}`",
        f"- stratified / seed: `{data.get('stratified')} / {data.get('seed')}`",
        f"- braintrust_logging: `{params.get('braintrust_logging')}`",
        f"- git: `{git.get('commit', '?')}`",
        f"- ground truth: `{data.get('ground_truth', 'expected + expected_subclass + sentiment_*')}`",
        "",
        "## Aggregate scorers",
        "",
        f"- rows: **{scores.get('n_rows', 0)}** (errors: {scores.get('n_errors', 0)})",
        f"- doc_type_accuracy: **{_pct(scores.get('doc_type_accuracy'))}**",
        f"- subclass_accuracy: **{_pct(scores.get('subclass_accuracy'))}** "
        f"(equiv {_pct(scores.get('subclass_accuracy_equiv'))})",
        f"- exact_match (doc_type ∧ subclass): **{_pct(scores.get('exact_match'))}**",
        f"- sentiment_label_accuracy: **{_pct(scores.get('sentiment_label_accuracy'))}**",
        f"- sentiment_score_ok (band {scores.get('sentiment_score_band', 0.25)}): "
        f"**{_pct(scores.get('sentiment_score_ok'))}**",
        f"- sentiment_score_mae: **{_pct(scores.get('sentiment_score_mae'))}**",
        f"- correspondence_exact (type ∧ subclass ∧ sentiment label): "
        f"**{_pct(scores.get('correspondence_exact'))}**",
        f"- confidence: **{_pct(scores.get('confidence'))}**",
        "",
        "## Tokens / cost",
        "",
        f"- prompt tokens: `{tokens.get('prompt_tokens', '—')}`",
        f"- completion tokens: `{tokens.get('completion_tokens', '—')}`",
        f"- total cost: `{tokens.get('total_cost', tokens.get('cost', '—'))}`",
        "",
        "## Per-subclass accuracy",
        "",
        "| subclass | accuracy | support |",
        "|----------|----------|---------|",
    ]
    for key in sorted(per_sub):
        lines.append(f"| {key} | {_pct(per_sub[key])} | {sub_n.get(key, '—')} |")

    sub_labels = sorted({*sub_conf, *(c for row in sub_conf.values() for c in row)})
    if sub_labels:
        lines += ["", "## Subclass confusion (expected \\ predicted)", "",
                  "| expected \\ predicted | " + " | ".join(sub_labels) + " |",
                  "|" + "---|" * (len(sub_labels) + 1)]
        for exp in sub_labels:
            row = sub_conf.get(exp) or {}
            lines.append("| " + exp + " | " + " | ".join(str(row.get(c, 0)) for c in sub_labels) + " |")

    lines += [
        "",
        "## Per-sentiment-label accuracy",
        "",
        "| sentiment_label | accuracy | support |",
        "|-----------------|----------|---------|",
    ]
    for key in ("negative", "neutral", "positive"):
        if key in per_sent or key in sent_n:
            lines.append(f"| {key} | {_pct(per_sent.get(key))} | {sent_n.get(key, '—')} |")

    sent_labels = ["negative", "neutral", "positive"]
    if sent_conf:
        extra = sorted({c for row in sent_conf.values() for c in row} - set(sent_labels))
        sent_labels = sent_labels + extra
        lines += ["", "## Sentiment confusion (expected \\ predicted)", "",
                  "| expected \\ predicted | " + " | ".join(sent_labels) + " |",
                  "|" + "---|" * (len(sent_labels) + 1)]
        for exp in sent_labels:
            row = sent_conf.get(exp) or {}
            lines.append("| " + exp + " | " + " | ".join(str(row.get(c, 0)) for c in sent_labels) + " |")

    mode_counts = fi.get("mode_counts") or {}
    lines += [
        "",
        "## Failure insights",
        "",
        f"- n_failed: **{fi.get('n_failed', len(failures))}**",
        f"- mode_counts: `{mode_counts}`",
        "",
        "## Misclassification ledger",
        "",
    ]
    if not failures:
        lines.append("_No misclassifications._")
    else:
        shown = failures[:max_misses]
        lines.append(f"_{len(failures)} rows; showing {len(shown)}._")
        lines.append("")
        lines.append("| mode | filename | expected subclass | predicted subclass | "
                     "expected sent. | predicted sent. | reasoning |")
        lines.append("|------|----------|-------------------|--------------------|"
                     "-----------------|-----------------|-----------|")
        for item in shown:
            exp = item.get("expected") or {}
            pred = item.get("predicted") or {}
            reasoning = str(item.get("reasoning") or "").replace("|", "\\|")[:160]
            lines.append(
                f"| {item.get('failure_mode')} | {item.get('filename')} | "
                f"{exp.get('doc_subclass')} | {pred.get('doc_subclass')} | "
                f"{exp.get('sentiment_label')} | {pred.get('sentiment_label')} | "
                f"{reasoning} |"
            )
    lines.append("")
    return "\n".join(lines)


def _write_report(markdown: str, experiment_name: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = experiment_name.replace("/", "_")
    out = output_dir / f"report_{slug}.md"
    out.write_text(markdown, encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, help="Experiment name")
    parser.add_argument("--output-dir", type=Path, default=Path("reports"), help="Output directory")
    parser.add_argument("--max-misses", type=int, default=100, help="Max ledger rows in the report")
    parser.add_argument("--from-log", action="store_true",
                        help="Render from reports/experiment_log.jsonl (correspondence / local sink)")
    parser.add_argument("--experiment-log", type=Path, default=None,
                        help="Override experiment-log JSONL path for --from-log")
    args = parser.parse_args()

    if args.from_log:
        record = load_log_record(args.experiment, args.experiment_log)
        if not record:
            parser.error(f"No experiment-log record named {args.experiment!r}")
        if record.get("task") == "correspondence_classification":
            markdown = render_correspondence_report(record, max_misses=args.max_misses)
        else:
            parser.error(
                f"--from-log correspondence renderer does not cover task "
                f"{record.get('task')!r}; omit --from-log to fetch Braintrust"
            )
        out = _write_report(markdown, args.experiment, args.output_dir)
        print(f"Report written to {out} (from experiment log)")
        return 0

    (braintrust_key,) = require_env("BRAINTRUST_API_KEY")
    exp = find_experiment_by_name(braintrust_key, _CONFIG.project_id, args.experiment, _CONFIG.api_base)
    if not exp:
        parser.error(f"Experiment not found: {args.experiment!r}")

    rows = fetch_experiment_rows(braintrust_key, exp["id"], _CONFIG.api_base)
    if not rows:
        parser.error(f"No events in experiment {args.experiment!r}.")

    log_record = load_log_record(args.experiment, args.experiment_log)
    if log_record and log_record.get("task") == "correspondence_classification":
        markdown = render_correspondence_report(log_record, max_misses=args.max_misses)
        source = "experiment log (correspondence scorers)"
    else:
        markdown = render_report(exp, rows)
        source = "Braintrust rows"

    out = _write_report(markdown, args.experiment, args.output_dir)
    print(f"Report written to {out} ({source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
