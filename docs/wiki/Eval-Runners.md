# Eval Runners

Each runner tests **ONE prompt version**; the experiment name is
`{model-slug}_{prompt-version}[_suffix]`. All runners share the
`main() -> main_with_args(argv)` pattern, `--dry-run` on anything that spends
money, and append to `reports/experiment_log.jsonl` on completion.

## Classification (`scripts/eval/run_classification_eval.py`)

The sorter-only task: doc-type classification (or LegalBench multi-class
`--prompt-mode task`). Trackers: `exact_match`, `failure`, `cost_total_usd`,
`cost_mean_usd`, `per_class_accuracy`, plus a bootstrap CI
(`exact_match_ci`).

```bash
python scripts/eval/run_classification_eval.py --dataset mailroom-cuad-contracts \
    --input-mode text --prompt-version sorter_v0

# LegalBench task mode: the row's own base_prompt is the user message, the
# versioned legalbench_task_v0 system prompt is constrained to --valid-classes.
# e.g. the hearsay task (binary Yes/No — does the evidence qualify as hearsay?
# 100 samples, 5 train / 95 test, 5 slices; dataset mailroom-lb-hearsay):
python scripts/eval/run_classification_eval.py --dataset mailroom-lb-hearsay \
    --prompt-mode task --valid-classes Yes,No --prompt-version legalbench_task_v0
```

## Run sink (read first)

**Primary sink: Langfuse + LangSmith + the repo experiment log.**
`run_langfuse_*_eval.py` are the primary eval runners — one per-document
Langfuse trace with numeric scores plus LangSmith LLM spans
(`LANGSMITH_TRACING=true`). Braintrust hosts the datasets (read-only) and its
experiment/span logging is OFF by default (`BRAINTRUST_LOGGING=disabled` in
`.env`), so the `run_*_eval.py` runners below skip `braintrust.Eval` and run
the same local scoring loop (manifest resume, experiment log). Opt back into
Braintrust logging per run with `BRAINTRUST_LOGGING=enabled`.

## Hierarchical doc-class (`scripts/eval/run_langfuse_docclass_eval.py`)

The new sorter task (KANBAN-033): the EXTENDED primary classification — the
shared 6 doc classes plus `merger_agreement` (MAUD corpus) — scored with a
second-level `doc_subclass` where the data necessitates it (consideration
type for merger agreements from MAUD expert GT; record type for corporate
records, content-detected from EDGAR S-1 exhibits). Tertiary dropped by
design: MAUD categories + exhibit codes are dataset metadata.

```bash
python scripts/eval/run_langfuse_docclass_eval.py --dry-run
python scripts/eval/run_langfuse_docclass_eval.py --local-dumps data/maud/contracts.jsonl,data/s1_corporate_records/corporate-records.jsonl \
    --stratified 120 --seed 42          # mixed surface: MAUD + CUAD + S-1
```

One sorter call per document (`sorter_docclass_v0`, extended schema); scores:
doc_type_accuracy, subclass_accuracy (rows without subclass GT unscored),
exact_match, confidence; per-class accuracy + subclass confusion +
failure insights (doc_type_miss / subclass_miss) in the repo log.

## Correspondence-only Enron (`scripts/eval/run_correspondence_eval.py`)

Correspondence-only sibling of the docclass eval (KANBAN-103): every row is
`expected=correspondence` from Hugging Face
`Lucius-Morningstar/enron-correspondence-dedup`. The sorter emits
`doc_type` + communication-function `doc_subclass` + `sentiment_label` /
`sentiment_score`, scored against the Hub `ground_truth` assortment.
Emails are short (default `--max-input-chars 20000`). Braintrust experiment
traces are ON by default (`--no-braintrust-logging` to opt out).

```bash
python scripts/eval/run_correspondence_eval.py --dry-run --stratified 200 --seed 42
python scripts/eval/run_correspondence_eval.py --stratified 200 --seed 42 \
  --experiment-name qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42
```

## Subtype (`scripts/eval/run_langfuse_subtype_eval.py` — primary; `run_subtype_eval.py` — local/resume)

Sorter-only subtype routing: one call per document decides the primary class
AND the contract-subtype family (25 CUAD families + `other`).
`--stratified N` samples evenly across classes. Trackers: `exact_match`,
`subtype_accuracy`, `subtype_accuracy_equiv` (defensible family swaps),
`confidence`, `failure_insights` (mode counts + per-failed-row reasoning),
`per_subtype`, `confusion_matrix`, bootstrap CIs.

```bash
python scripts/eval/run_langfuse_subtype_eval.py --dataset mailroom-cuad-contracts-full \
    --stratified 250 --seed 42 --sorter-prompt-version sorter_v11     # primary (Langfuse + LangSmith)
python scripts/eval/run_subtype_eval.py --dataset mailroom-cuad-contracts-full \
    --stratified 200 --seed 42 --sorter-prompt-version sorter_v5      # local scoring, no Braintrust log
```

## Extraction (`scripts/eval/run_extraction_eval.py`)

The contracts-specialist entity extraction vs CUAD clause-QA ground truth.
Trackers: `overall_extraction_score`, `field_presence`, `schema_valid`,
`overall_verified_precision`, `category_presence`, `per_field`,
`entity_list_f1`, `hallucination_rate`, `overall_extraction_score_ci`.
Optional `--judge` runs the LLM judge on the ambiguous band and records the
**judge-calibration tracker** (`scores.judge_calibration`).

```bash
python scripts/eval/run_extraction_eval.py --dataset mailroom-cuad-contracts \
    --prompt-version contracts_specialist_v11 --judge
```

## Chained (`scripts/eval/run_chained_eval.py`)

Sorter → specialist end-to-end with the subtype handoff:
`--handoff-scope subtype` (default) cues the specialist with the PREDICTED
subtype's field groups; `none` reproduces the legacy handoff;
**`ground_truth`** is the error-propagation ablation — the specialist ALSO
extracts with the ground-truth-subtype cue, and `scores.ablation` splits
sorter routing loss from specialist error.

```bash
python scripts/eval/run_chained_eval.py --dataset mailroom-cuad-contracts-full \
    --sorter-prompt-version sorter_v6 --extractor-prompt-version contracts_specialist_v11
python scripts/eval/run_chained_eval.py ... --handoff-scope ground_truth   # ablation
```

## A/B (`scripts/eval/evaluate_prompt_version.py`)

Runs two prompt versions on the same dataset and reports the delta with a
**two-sample bootstrap CI + significance verdict** (a 5-doc 0.94-vs-0.88 gap
is a CI overlap, not a win).

```bash
python scripts/eval/evaluate_prompt_version.py --prompt-a sorter_v0 --prompt-b sorter_v1
```

## Cross-model matrix (`scripts/eval/run_model_matrix.py`)

Runs the SAME fixed sample (same dataset/seed/size — one surface) across a
model x prompt grid and prints a score (+CI) x cost matrix.

```bash
python scripts/eval/run_model_matrix.py --task subtype \
    --models qwen/qwen3.7-flash,deepseek/deepseek-v4-flash \
    --prompts sorter_v5,sorter_v6 --sample 10 --seed 42
```

## Langfuse mirrors (`scripts/eval/run_langfuse_*_eval.py`)

Same runners traced to the `llm-dojo` Langfuse project
(one trace per document, per-agent spans with task scores).
`run_langfuse_classification_eval.py` mirrors BOTH classification modes:
`--prompt-mode sorter` (one `sorter` observation per row) and
`--prompt-mode task` (one `legalbench_task` observation per row — the LegalBench
task surface, e.g. `mailroom-lb-hearsay`, traces into llm-dojo too):

```bash
python scripts/eval/run_langfuse_classification_eval.py --dataset mailroom-lb-hearsay \
    --prompt-mode task --valid-classes Yes,No --prompt-version legalbench_task_v0
```

## Datasets (`scripts/datasets/`)

- `stream_cuad_to_bt.py` — the CUAD corpus into Braintrust
  (`--text-only` / vision page images)
- `download_cuad_pdfs.py` — keep the CUAD PDF corpus locally
- `stream_legalbench_to_bt.py` / `stream_legalbench_tasks_to_bt.py` —
  LegalBench MAUD agreements + the multi-class task suites (one
  `mailroom-lb-<task>` dataset per task; synced rows carry deterministic ids,
  so reruns upsert in place — e.g. `--tasks hearsay` syncs the 5-row binary
  Yes/No hearsay train set and writes the per-task classes manifest
  `data/legalbench_classes.jsonl`)

## Reporting (`scripts/reporting/`)

- `render_experiment_log.py` — rebuild `reports/experiment_log.md` from the
  JSONL (the JSONL is the source of truth; never hand-edit the md)
- `report_generator.py` / `confusion_matrix.py` — Braintrust-fetching reports
- `score_extraction_manifest.py` — offline manifest scoring

## Site (`scripts/site/build_site.py`)

Rebuilds `docs/data/` (index.json, meta.json, runs/, trends.json,
prompts.json) — see [Site](Site).
