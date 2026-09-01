# `scripts/` — ops, evals, reporting, site, releases

Every script is `#!/usr/bin/env python3`, runs from the repo root, exposes
`main_with_args(argv)` (testable), and anything that spends LLM money offers
`--dry-run`.

## `scripts/` root

| Script | Purpose |
|---|---|
| `release.py` | semver release automation: `--bump <patch|minor|major> --note "<summary>"` converts `[Unreleased]` -> `[vX.Y.Z]`, bumps `pyproject.toml`, prints commit/tag/sync commands; `--check` validates state (version == changelog header, site data, tests, render audit); `--dry-run` previews |

## `scripts/datasets/` — sync the corpora into Braintrust datasets

| Script | Purpose |
|---|---|
| `stream_cuad_to_bt.py` | CUAD corpus -> Braintrust dataset (`--text-only`, `--dry-run`, `--limit`) |
| `download_cuad_pdfs.py` | keep the CUAD PDF corpus locally (`--out-dir`, `--category`, resumable) |
| `stream_legalbench_to_bt.py` | LegalBench MAUD v1 (Zenodo; legacy Braintrust path): contracts + per-question suite |
| `stream_maud_to_bt.py` | MAUD v1 as a UTILIZED dataset (Zenodo/HF mirror): 152 merger agreements (GT `merger_agreement` + consideration-type subclass from MAUD expert GT) + 25,827-row per-question suite (22 families / 7 categories as metadata); `--local-dump` is the reliable path while Braintrust row uploads are capped |
| `stream_s1_exhibits.py` | EDGAR S-1 corporate-record exhibits (EX-3.x/4.x/21.x/24.x/25.x) via SEC full-text search + filing indexes; content-detected record-type subclass; exhibit code stays as metadata; SEC fair-access throttle + retry; `--local-dump` |
| `stream_legalbench_tasks_to_bt.py` | LegalBench multi-class task suites -> Braintrust (one `mailroom-lb-<task>` dataset per task, e.g. `--tasks hearsay`; deterministic row ids => reruns upsert) |
| `build_contracteval_testset.py` | build the ContractEval CUAD test split (KANBAN-052) into `data/contracteval/`: 4,182 (contract, question) pairs / 102 contracts / 41 categories from the Atticus `test.json` (the HF `cuad-qa` source); positives = 1,244 (the paper's hardcoded false-rate denominator); `--dry-run`, resumable download cache |
| `load_enron_correspondence.py` | join HF `Lucius-Morningstar/enron-correspondence-dedup` agent-blind `default` + `ground_truth` on `filename` (correspondence-only); `--dry-run` prints subclass/sentiment counts; `--write` dumps joined JSONL |

## `scripts/eda/`

`explore_cuad.py` — full-corpus CUAD EDA -> `data/eda/{report.md, findings.md, figures/01–10}` (reproducible from the repo root).

`explore_pipeline_sources.py` — full EDA suites on the post-CUAD pipeline sources (KANBAN-045): per-source `data/eda/<source>/{report.md, findings.md, figures/}` for **MAUD** (`--source maud`: 152 merger agreements + the 25,827-row per-question suite), **S-1 corporate records** (`--source s1`: 15 EDGAR exhibits), the **merged doc-class surface** (`--source docclass`: 676 rows) and **LegalBench** (`--source legalbench`: hearsay + 10 CUAD subtasks). `--source all` (default), `--no-figures`, `--out <dir>`. Regeneration is byte-identical (pinned by `tests/test_pipeline_sources_eda.py`).

`monte_carlo_corpus.py` / `monte_carlo_ensemble.py` / `monte_carlo_prompt_ablation.py` /
`monte_carlo_failures.py` / `monte_carlo_exemplars.py` / `monte_carlo_verify.py` —
the **Monte Carlo simulation suite** (KANBAN-048, ported from the
RVL-CDIP-classifier per issue #17): zero-spend what-if analysis over the joint
reasoning corpus (`reports/monte_carlo/corpus.jsonl`, built by
`monte_carlo_corpus.py` from the experiment log + manifests). Scenarios:
committee voting accuracy(K) + confidence-gated escalation Pareto
(`monte_carlo_ensemble.py`), paired-bootstrap prompt-ablation gate
(`monte_carlo_prompt_ablation.py`), retry/fallback failure simulation at
1K/25K/320K (`monte_carlo_failures.py`), near-miss exemplar mining for
confusion pairs (`monte_carlo_exemplars.py`), and the spend-minimal
verification recipe (`monte_carlo_verify.py`, dry-run default). Shared helpers
in `src/monte_carlo.py`; outputs under `reports/monte_carlo/` (corpus.jsonl
gitignored — rebuild with the corpus script).

## `scripts/eval/` — the runners (see wiki: Eval-Runners)

Every runner: `main_with_args(argv)`, `--dry-run`, resumable `--manifest`,
experiment-log append. Names are `{model-slug}_{prompt-version}[_suffix]`.

| Script | Purpose |
|---|---|
| `run_classification_eval.py` | one prompt version; `--input-mode auto/text/vision`, `--prompt-mode sorter/task`, `--valid-classes`, local PDFs |
| `run_subtype_eval.py` | sorter-only contract-subtype eval (one call per PDF; strict + equiv accuracy) |
| `run_extraction_eval.py` | contracts specialist vs CUAD ground truth; `--bt-scores`, `--judge`, `--chunked` |
| `run_chained_eval.py` | sorter -> extractor end-to-end; `--handoff-scope none|subtype|ground_truth` ablation |
| `run_binary_class_eval.py` | binary question precision/recall/F1 |
| `run_multiclass_eval.py` | all-class eval with per-class accuracy |
| `run_model_matrix.py` | model x prompt grid on one surface |
| `evaluate_prompt_version.py` | A/B two prompt versions on the same dataset (bootstrap delta CI) |
| `run_annotation_queue.py` | HITL annotation queues (llm-dojo mirror): `build`/`status` on low-performing extraction traces + failed sorter classifications |
| `run_langfuse_subtype_eval.py` | **primary-sink mirror** of `run_subtype_eval` (per-doc Langfuse traces + scores, LangSmith spans) |
| `run_langfuse_chained_eval.py` | **primary-sink mirror** of the chained eval (per-agent spans + task scores) |
| `run_langfuse_extraction_eval.py` | **primary-sink mirror** of the extraction eval (`--chunked` supported) |
| `run_langfuse_classification_eval.py` | **Langfuse mirror** of the classification eval (`--prompt-mode task` for LegalBench tasks) |
| `run_langfuse_docclass_eval.py` | **hierarchical doc-class eval** (KANBAN-033/101): extended **8-class** primary dimension + doc_subclass second level; default `sorter_docclass_v7` on `data/datasets/docclass_merged.jsonl` (1,210 rows); Phoenix/Langfuse sink |
| `run_correspondence_eval.py` | **correspondence-only Enron eval** (KANBAN-103): `doc_type` + communication-function `doc_subclass` + `sentiment_label`/`sentiment_score` on `Lucius-Morningstar/enron-correspondence-dedup`; default `--stratified 200 --seed 42`; `--include-all-attorney-demand` + `--extra-dumps` restore every attorney_demand example (Hub n=3 + full-corpus `sanders-r/ecogas/26.` dropped by dedup); `--gt-overrides` applies filename-keyed Hub GT patches (`data/gt/enron_correspondence_label_overrides.jsonl`); Braintrust traces ON; prompts `sorter_docclass_correspondence_v0`/`v1`/`v2`; `--publish-prompt` upserts the version into the Braintrust project library |
| `run_langfuse_contracteval_eval.py` | **directly-mirrored ContractEval benchmark** (KANBAN-052, arXiv 2508.03080): one (contract, question) call per row over the CUAD test split, faithful full-context (`--max-input-chars 0`), ContractEval's exact rubric (F1/F2/Jaccard/false-nr + per-category) scored upstream (`llm-dojo-scoring` v0.4.0 `contracteval` kind); `task: contracteval` experiment-log record |
| `sync_langfuse_datasets.py` | mirror Braintrust datasets into Langfuse datasets (deterministic item ids => upsert); `--maud`/`--s1` mirror the streamer local dumps |
| `sync_langfuse_prompts.py` | mirror versioned prompts into Langfuse (idempotent; `--env-file` adds projects) |
| `sync_langfuse_datasets.py` | mirror Braintrust datasets into Langfuse datasets (deterministic item ids => upsert) |
| `sync_braintrust_prompts.py` | mirror versioned prompts (incl. docclass) into Braintrust prompt registry (`--env-file braintrust-sandbox.env`) |
| `sync_braintrust_datasets.py` | upload eval/testing datasets to Braintrust (`--all` = hearsay + CUAD text + docclass HF + Enron) |

## `scripts/reporting/`

| Script | Purpose |
|---|---|
| `render_experiment_log.py` | JSONL -> markdown log (rebuilds `reports/experiment_log.md`) |
| `report_generator.py` | markdown experiment report from Braintrust (needs `BRAINTRUST_API_KEY`) |
| `confusion_matrix.py` | PNG + CSV confusion matrix from Braintrust |
| `score_extraction_manifest.py` | post-hoc extraction scoring from a manifest (offline) |
| `rescore_manifests.py` | re-score extraction manifests with the CURRENT scorer (scorer-drift immune; `--auto-50`) |
| `judge_experiment.py` | post-hoc JudgeAgent review of failed classifications |
| `backfill_subtype_reasoning.py` | one-time enrichment: full failure reasoning from Braintrust spans |
| `backfill_cost_estimates.py` | documented one-time backfill: stamp `cost_estimated_usd` on historical records (`--dry-run` first) |
| `run_contracteval_mapping.py` | benchmark stored ONE-PASS extraction runs vs ContractEval Table III (offline, KANBAN-051) |
| `run_contracteval_report.py` | benchmark directly-mirrored `contracteval` runs vs the full 19-model Table III + per-category (offline, KANBAN-052) |
| `export_experiment_results.py` | regenerate the per-task performance workbooks + codebooks (Google-Sheets-friendly): `Sorter_Experiment_Results.xlsx` (114 cols, Eval Results + Codebook sheets) + `Sorter_Experiment_Codebook.csv` from `subtype_classification` runs, `Entity_Extraction_Results.xlsx` (141 cols) + `Entity_Extraction_Codebook.csv` from `contract_entity_extraction` runs. `--task {sorter,extraction,all}`, `--outdir`, `--log`. Mirrors the reference format byte-for-byte (headers/order, percent/date formats, freeze panes, autofilter, per-subtype ordering). |

## `scripts/site/`

`build_site.py` — rebuild `docs/data/` (index.json, meta.json, runs/,
trends.json, prompts.json, board.json, memos.json) for the GH Pages site;
`--check` verifies freshness; `--openrouter-csv`/`--benchmarks-key` attach
real billed costs / live OpenRouter benchmark data.
