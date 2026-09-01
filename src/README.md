# `src/` — core modules

Everything the eval loop builds on. The package is importable from anywhere
(`pip install -e .`).

| Module | Responsibility |
|---|---|
| `dojo_config.py` | wires `config/taxonomy.yaml` into the **`llm_dojo_scoring`** package `Settings` at import (field-scoring thresholds incl. `embedding_enabled`, cost table dict→list conversion, type coercion, `load_env()` first; `LLM_DOJO_SCORING_CONFIG` external-YAML escape hatch) |
| `dojo_compat.py` | docclass failure-mode classifier `classify_failure(doc_type_ok, subclass_ok, predicted_subclass)` (positional-boolean contract, `None` on success) against the package's row-dict `classify_docclass_failure` |
| `bootstrap.py` | re-export shim → `llm_dojo_scoring.bootstrap` (percentile-bootstrap 95% CIs + two-sample delta significance) |
| `cost_models.py` | re-export shim → `llm_dojo_scoring.cost` (verified per-model token prices + deterministic cost estimation: `estimate_cost`, `estimate_for_record`, `tokens_summary`) |
| `prompts.py` | ALL prompts, versioned in `PROMPT_VERSIONS`; `get_prompt(version)`, `list_prompts()`. The version key IS the experiment identity |
| `prompts_archive.py` | FROZEN archive of superseded contract-specialist prompt versions (v1..v16, the pre-documentation lineage) — imported back into `prompts.py` so every version key stays resolvable; NEVER edit an archived constant (a change = a new version key) |
| `experiment_log.py` | append-only JSONL + markdown renderer (`append_experiment`, `experiment_markdown`, `render_full_log`, `tokens_summary(model=)` — the append/git-snapshot/mean/tokens core re-exports `llm_dojo_scoring.experiment` + `.cost`; the markdown renderers stay local) |
| `correspondence_eval.py` | Enron correspondence eval primitives (KANBAN-103): blind↔GT join, subclass-stratified sample, `append_missing_by_subclass` / `merge_eval_rows` (take-all attorney_demand + extra dumps), sentiment scoring, predicted↔GT field alignment |
| `field_scoring.py` | re-export shim → `llm_dojo_scoring.field_scoring` (field-type-aware content scorer + factuality audit + ambiguous band + embedding rescue; keeps the one-arg `get_field_types(doc_class)` taxonomy resolver) |
| `scorers.py` | re-export shim → `llm_dojo_scoring.classification` (`exact_match`, `failure`, `normalize_label`, binary/multiclass helpers) + the local `cost` scorer and name registry (`build_scorers`, `per_class_stats`, `macro_accuracy`) |
| `metrics.py` | re-export shim → `llm_dojo_scoring.diagnostics` (run-level extraction diagnostics `scores.diagnostics`: raw list P/R/F1, date/duration/money MAE + R², span-count drift, error decomposition; keeps the `master=` keyword via a resolver closure) |
| `monte_carlo.py` | zero-spend robustness simulation primitives over the joint reasoning corpus (committee voting, confidence-gated escalation, paired-bootstrap ablation, failure-pipeline sim, exemplar mining — KANBAN-048) |
| `evaluation.py` | dataset validation, `dataset_fingerprint`, `ManifestStore` (resumable JSONL checkpoints), adaptive `resolve_concurrency`, `call_with_rate_limit_retry` |
| `cuad_ground_truth.py` | CUAD 41-category catalog -> expected fields + presence + `build_subtype_handoff()` |
| `taxonomy.py` | loads `config/taxonomy.yaml` (doc classes, field types, agent->model mapping, thresholds) |
| `classifier.py` | label/confidence/reasoning parsers (RVL-CDIP style), `classify_image` |
| `braintrust_config.py` | loads `braintrust.env` / `.env` (org, project, model, api base) |
| `braintrust_utils.py` | Braintrust HTTP: list/fetch experiments, load/upload datasets, attachments |
| `braintrust_logging.py` | `BRAINTRUST_LOGGING` gate (default `disabled`): when off, the `run_*_eval.py` runners skip `setup_langchain` + `braintrust.Eval` entirely |
| `eval_shims.py` | `run_local_eval()` — the shared local scoring loop used when `BRAINTRUST_LOGGING=disabled` (thread pool + manifest resume + experiment-log append) |
| `langfuse_config.py` / `langfuse_tracing.py` | Langfuse mirror: project config + per-document tracer (`agent_observation`) |
| `tracing.py` | `resolve_tracer()` — the run-sink resolver: Langfuse PRIMARY (llm-dojo), local Arize Phoenix server as fallback; returns `(tracer, tracing_backend, tracing_meta)` |
| `phoenix_tracing.py` | local Arize Phoenix OpenTelemetry tracer (OTLP, SQLite store, discard-by-delete) |
| `llm_chain.py` | LangChain chain factory for the eval loops |
| `master_labels.py` | curated master ground-truth CSV loader (`master_clauses.csv`) for the MAE diagnostics; degrades to `{}` when absent |
| `image_utils.py` | PDF/TIFF -> 1024x1024 grayscale PNG helpers |
| `env_utils.py` | dotenv loading + required-var validation; the shared `config/environments/` path constants (`ENV_DIR`, `BRAINTRUST_ENV_FILE`, `DOTENV_FILE`, `LANGFUSE_ENV_FILE`) + `resolve_env_file()`; `resolve_openrouter_key()` / `assert_production_run()` / `add_research_funding_flag()` (the research-funding gate) |
| `openrouter_utils.py` | OpenRouter base URLs, message builders, prompt splitting |