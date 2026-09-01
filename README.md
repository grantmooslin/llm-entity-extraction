# llm-entity-extraction

A prompt experiment loop environment for legal document entity extraction: the
building block for the llm-mailroom agents. Each evaluation tests **one prompt
version at a time**, runs the agents on **LangChain**, and sinks runs to
**Arize Phoenix** (local OpenTelemetry-native tracing, Apache/Elastic-licensed) + a
fully expanded, append-only experiment log in the repo
(`reports/experiment_log.{jsonl,md}`). Braintrust hosts the eval datasets
(read-only) — its experiment/span logging is disabled by default
(`BRAINTRUST_LOGGING=disabled`) so runs never consume its plan quota. LangSmith
and Langfuse mirrors remain available for backward compatibility.

Modeled on the [RVL-CDIP-Classifier](https://github.com/Exios66/RVL-CDIP-Classifier)
repo's Braintrust evaluation pattern (vision classification of document page
images) and the [llm-mailroom](https://github.com/Exios66/llm-mailroom)
taxonomy/prompts.

## Contents

- [The sorter's three jobs](#the-sorters-three-jobs)
- [The pipeline under test](#the-pipeline-under-test)
- [Scoring (deterministic, field-type-aware)](#scoring-deterministic-field-type-aware)
- [Layout (repo map)](#layout)
- [Experiment log](#experiment-log)
- [Website](#website)
- [Setup](#setup)
- [Sync the HF corpora into Braintrust](#sync-the-hf-corpora-into-braintrust)
- [The loop (one prompt at a time)](#the-loop-one-prompt-at-a-time)
- [Adding a prompt version](#adding-a-prompt-version)
- [Tests](#tests)
- [Credits](#credits)
- [Docs & navigation](#docs--navigation)

## The sorter's three jobs

1. **Vision classification of the ACTUAL PDFs (RVL-CDIP pipeline)** — every
   eval row is ONE PDF with ALL of its pages: the streamer renders every page
   of the real CUAD contract PDFs into the dataset row, and the sorter sends
   **all pages of the document in a single vision call** (one classification
   per PDF, however large or small — no text files, no page-1 stubs). The
   ``sorter_vision_v0`` prompt (ordered check cascade + scratchpad +
   ``<label>/<confidence>/<reasoning>`` tag output) reads the entire agreement
   — recitals, sections, exhibits, signature pages — before deciding.
   Local PDFs are classified with a confidence-weighted **page vote**
   (``--vision-pages all``, the default).
2. **Multi-class LegalBench classification** — the sorter answers the
   LegalBench multi-class classification tasks (`cuad_*` Yes/No clause tasks,
   the 13k-row MAUD per-question suite, and 60+ more) via
   `--prompt-mode task` with the `legalbench_task_v0` prompt. Synced
   per-task datasets are named `mailroom-lb-<task>`; e.g. **hearsay** (binary
   Yes/No: does the evidence qualify as hearsay under the Federal Rules of
   Evidence — 100 samples, 5 train / 95 test, 5 slices: statement made
   in-court, non-assertive conduct, standard hearsay, non-verbal hearsay,
   not-introduced-to-prove-truth; CC BY 4.0) lives in `mailroom-lb-hearsay`
   and evaluates with `--valid-classes Yes,No`.
3. **Hierarchical doc-class classification** — the sorter classifies into the
   EXTENDED primary dimension (`sorter_docclass_v7`, champion): the shared 6 doc classes
   plus **`merger_agreement`** (the MAUD corpus class), with a second-level
   `doc_subclass` for the classes whose data necessitates it — consideration
   type for merger agreements (MAUD expert GT: all_cash / all_stock /
   mixed_cash_stock / mixed_cash_stock_election) and record type for
   corporate records (content-detected: bylaws, certificate of incorporation,
   powers of attorney, ...). The mixed eval surface
   (`run_langfuse_docclass_eval.py`) scores doc_type + subclass across
   `mailroom-maud-contracts`, `mailroom-cuad-contracts-full` and
   `mailroom-s1-corporate-records` (EDGAR S-1 exhibit corporate records).
   The tertiary level is deliberately absent — MAUD categories and EDGAR
   exhibit codes are dataset metadata, not classification dimensions.

The sorter receives **full documents** — either the full extracted text
(100k-char hard safety cap; past the cap the input becomes a HEAD + TAIL
window — opening portion plus the closing portion where term, termination,
renewal, governing law, and signatures live — truncation recorded on the span,
never a 50-token preview) or the complete PDF page set in one call.

## The pipeline under test

The eval loops exercise the same LangChain agents the mailroom runs:

| Agent | File | Role |
|---|---|---|
| `BaseAgent` | `agents/base_agent.py` | `ChatOpenAI` (OpenRouter) + structured output (JSON schema) + vision calls; `_last_usage` token/cost capture |
| `SorterAgent` | `agents/sorter_agent.py` | doc-type classification (text `classify_json` + image `classify_image`) plus the **contract subtype** dimension (25 CUAD contract families) |
| Specialists | `agents/specialist_agents.py` | per-doc-class field extraction (contract, corporate record, due diligence, correspondence, compliance filing, court opinion) + shared JSON schemas |
| `JudgeAgent` | `agents/judge_agent.py` | offline LLM-as-a-judge: classification / completeness / extraction correctness |

### Recommended production configuration (extraction)

Determined from the ko-vs-overall A/B on the 50-doc seed-42 surface
(`V16_PROPOSITION.md` §15.1, memo `contracts_specialist_v23.md`):

| Config | key_obligations (ko) | overall | cost / 50 docs | rows ok | ellipsis |
|---|---:|---:|---:|---:|---:|
| **overall arm** (`reasoning_effort=none`) | 0.8294 (v22) | **0.9512** | $0.039 | 50/0 | 19.5% |
| **ko arm** (`reasoning_effort=max`) | **0.8510** (v23×max) | 0.9363 | $0.103 (2.6×) | 50/0 | **18.7%** |
| *(rejected)* v19×max | 0.8840 | 0.9135 | $0.098 | 49/1 | 27.1% |

**Decision: split.** The default production config is the **overall arm**
(`reasoning_effort=none` — the extractor's default; the champion line is now
`contracts_specialist_v31`, 0.8737 @ full-509 corpus, chunked, seed 42). The
**ko arm** (`--reasoning-effort max`) is a documented opt-in for
compliance/covenant-heavy reviews where key_obligations recall is the
deliverable: `v23×max` (ko 0.8510, **0 parse errors**, lowest ellipsis 18.7%)
is the defensible ko config — **not** `v19×max` (ko peak 0.8840 but 1/50 parse
error, worst overall 0.9135, highest ellipsis 27.1%). Max reasoning buys
+2.2pp ko at 2.6× cost and −1.5pp overall — worth it only when
key_obligations fidelity outweighs the cost/overall tradeoff.

## Scoring (deterministic, field-type-aware)

<details>
<summary>Scoring internals — field types, diagnostics, task dispatcher, Monte Carlo</summary>

Exact-match-on-extraction treats every field identically, which is wrong. The
evaluations score each field by its type (`config/taxonomy.yaml →
field_scoring:`). The scoring definitions are **outsourced to the
`llm-dojo-scoring` package** (pinned `@v0.10.0`, shared with llm-mailroom) —
the local `src/field_scoring.py` / `metrics.py` / `scorers.py` /
`bootstrap.py` / `cost_models.py` are thin re-export shims, and
`src/dojo_config.py` wires the taxonomy into the package `Settings` at import
(see [`docs/SCORING.md`](docs/SCORING.md) §0 for the full map):

- `id` — normalize + exact match (docket/reference numbers)
- `date` — canonical ISO parse, then exact match ("March 3, 2024" == "03/03/2024")
- `money` — strip symbols, float compare within one cent; unparseable prose
  falls back to fuzzy matching
- `name` — Jaro-Winkler + token-set ratio on normalized text
- `free_text` — SQuAD-style token F1
- `entity_list` — optimal bipartite matching (Hungarian algorithm) over
  pairwise similarity, then precision/recall/F1

`name`/`free_text` also use embedding cosine similarity
(`sentence-transformers/all-MiniLM-L6-v2`, lazy, graceful degradation) as a
second signal when the string score is ambiguous (below the `embedding_rescue_below`
threshold). The embedder prefers the local model and falls back to OpenRouter
embeddings (`openai/text-embedding-3-small`) when sentence-transformers is not
installed or the model cannot load — so the rescue works with a plain
`pip install -r requirements.txt` too. Empty predictions/labels are never
rescued by embeddings: a blank answer stays a miss.

Ground truth follows the CUAD dataset card (`theatticusproject/cuad`): all 41
clause categories are modeled — 9 string-answer categories map to schema
fields; the 32 YES/NO categories are scored as content **and** as binary
presence expectations. Expected fields are **type-aware**: the CUAD folder the
contract came from decides which categories apply (`ground_truth_mode
"cuad_type_aware"`, `src/cuad_ground_truth.py`). A **factuality guard**
verifies every predicted list item against a label or the source document and
reports `verified_precision` / `hallucination_rate`.

Every extraction run ALSO carries run-level diagnostics (`scores.diagnostics`
in the experiment log, `src/metrics.py`), so a researcher can see not just
the composite score but WHY it is what it is:

- **Precision / recall / F1** — raw list-match ratios, macro over
  `key_obligations` plus span-pooled micro, and per-field (bipartite match).
- **Regression error (MAE)** — date/duration MAE in calendar days and money
  MAE in USD vs ground truth (mean + median, per-field buckets, pair counts),
  so a day-shifted date or $1-off amount counts as a near-miss, not a binary
  wrong answer.
- **R²** — coefficient of determination over the same parseable pairs: how
  much ground-truth variance the predictions explain (negative = worse than
  predicting the mean).
- **Span-count drift** — symmetric item-count MAE + signed mean per list
  field: systematic over- vs under-extraction in one number.
- **Error decomposition** — exact / partial / miss rates per field (+
  presence), the direct read on where content-score loss comes from.

The regression diagnostics parse the curated **master labels CSV**
(`src/master_labels.py`, default `../llm-mailroom/data/cuad/master_clauses.csv`
— normalized answers like `"5/8/14"`, `"2 years"`) and degrade gracefully to
the raw CUAD clause text when it is absent.

Beyond the CUAD extraction surface, the **task-aware scoring dispatcher**
(`llm_dojo_scoring.tasks`, `score_task()`) covers the additional document
hierarchy: **MAUD** merger-agreement doc_type + consideration-type subclass
(strict + equiv), **LegalBench** binary Yes/No (exact match + per-class +
P/R/F1), **multiclass** (macro/micro), **court opinions**, and **chained**
sorter→extractor composite scoring (default 0.25/0.75 weights). The **docclass
eval** (`run_langfuse_docclass_eval.py`) scores doc_type + doc_subclass across
the merged 676-row surface (CUAD + MAUD + S-1) with per-subclass accuracy,
equivalence-aware subclass scoring, bootstrap CIs, and input-mode splits; the
**subtype eval** reports strict + equivalence-aware family accuracy with
per-family tables and failure-mode insights; and the **Monte Carlo robustness
suite** (`src/monte_carlo.py`) adds zero-spend committee-voting / escalation /
paired-bootstrap-ablation / failure-pipeline / exemplar metrics over the joint
reasoning corpus. Every metric (with formulas and reading) is in
[`docs/SCORING.md`](docs/SCORING.md); the worked examples are in `docs/slides/`.

</details>

## Layout

The repo is a Python package (`pyproject.toml` — `pip install -e .` makes
`agents`, `src`, `config` importable from ANY codebase, e.g. llm-mailroom's
LangGraph). Every area has its own README — use them as the detailed map.

<details>
<summary>Repo map — top-level tree</summary>

```
agents/                  LangChain agents under test (see agents/README.md)
  base_agent.py          ChatOpenAI (OpenRouter) + structured output + vision calls
  sorter_agent.py        doc-type + contract-subtype classification (text + image)
  specialist_agents.py   per-class field extraction + shared JSON schemas
  judge_agent.py         LLM-as-a-judge (classification/completeness/correctness)
config/                  the control panel (see config/README.md)
  taxonomy.yaml          doc classes, field types, agent->model mapping, thresholds
src/                     core modules (see src/README.md)
  bootstrap.py           re-export shim -> llm_dojo_scoring.bootstrap (CIs + delta significance)
  braintrust_config.py   loads braintrust.env / .env (org, project, model, api base)
  braintrust_logging.py  BRAINTRUST_LOGGING gate: on/off Braintrust experiment sink
  braintrust_utils.py    Braintrust HTTP, dataset load/upload, experiment fetch
  classifier.py          label/confidence/reasoning parsers (RVL-CDIP style)
  cost_models.py         re-export shim -> llm_dojo_scoring.cost (prices + estimation)
  cuad_ground_truth.py   CUAD 41-category catalog -> expected fields + presence
  dojo_compat.py         docclass failure-mode classifier (positional-boolean contract)
  dojo_config.py         wires config/taxonomy.yaml into llm_dojo_scoring Settings
  env_utils.py           dotenv loading + required-var validation
  eval_shims.py          run_local_eval(): the shared local scoring loop when
                         BRAINTRUST_LOGGING=disabled (thread pool + manifest resume)
  evaluation.py          dataset validation, fingerprints, resumable manifests
  experiment_log.py      append-only repo experiment log (JSONL + markdown renderer)
  field_scoring.py       re-export shim -> llm_dojo_scoring.field_scoring
                         (field-type-aware content scoring + factuality audit)
  image_utils.py         PDF/TIFF -> 1024x1024 grayscale PNG helpers
  langfuse_config.py     Langfuse project config (llm-dojo by default)
  langfuse_tracing.py    Langfuse mirror tracer (one trace per document, scores)
  llm_chain.py           LangChain chain factory for eval loops
  master_labels.py       curated master ground-truth CSV loader (MAE diagnostics)
  metrics.py             re-export shim -> llm_dojo_scoring.diagnostics
                         (run-level MAE/R2, span drift, error decomposition)
  monte_carlo.py         zero-spend robustness simulation primitives (KANBAN-048)
  openrouter_utils.py    OpenRouter constants + vision message builders
  prompts.py             ALL agent prompts, versioned (the version key IS the identity)
  scorers.py             re-export shim -> llm_dojo_scoring.classification
                         (exact_match, failure + local cost registry)
  taxonomy.py            YAML loader for config/taxonomy.yaml
scripts/                 ops + evals + reporting + site + releases (see scripts/README.md)
  datasets/              sync the HF corpora into Braintrust datasets
  eda/                   full-corpus EDA (explore_cuad.py -> data/eda/)
  eval/                  the experiment loops + Langfuse mirrors + annotation queues
  reporting/             experiment-log renderer + reports + post-hoc scoring + backfills
  site/                  build_site.py: rebuild docs/ (GH Pages) data from the JSONL
  release.py             semver release automation (--bump / --check / --dry-run)
tests/                   network-free suite + headless site render audit (see tests/README.md)
governance/              agent process state: MESSAGE_BOARD.md/.qmd kanban + the
                         append-only discussion log .qmd (see AGENTS.md §board)
reports/                 the experiment log: experiment_log.{jsonl,md} (see reports/README.md)
docs/                    the GH Pages site: index.html + assets/ + slides/ + data/
                         + posit/ (rendered portal) + posit-src/ (its Quarto SOURCES,
                         see docs/posit-src/README.md) + wiki/ (GitHub-wiki pages +
                         sync-wiki.sh) + SCORING.md, memos/, sister-repos.md
data/                    (gitignored run artifacts: manifests/, legalbench_local/, samples/)
                         + tracked data/eda/ (EDA report, findings, figures)
                         + tracked data/gt/ (KANBAN-097 agent-bench ground truth:
                           edge_suites/, per-doc packets/, insurance-claim GT)
.opencode/               agent prompts + skills (prompt-engineer, experiment-log-sync, eval-judge)
```

</details>

Under `scripts/` the key files are:

<details>
<summary>Full scripts inventory — streamers, eval runners, reporting, site</summary>

```
scripts/datasets/
  stream_cuad_to_bt.py            CUAD v1: 510 contract PDFs, every page rendered
  stream_legalbench_to_bt.py      LegalBench MAUD v1 via Zenodo: contracts + per-question suite
  stream_maud_to_bt.py            MAUD v1 (Zenodo/HF): 152 merger agreements (GT merger_agreement +
                                  consideration-type subclass) + 25,827-row per-question suite;
                                  --local-dump + Langfuse mirror paths
  stream_s1_exhibits.py           EDGAR S-1 corporate-record exhibits (EX-3.x/4.x/21.x/24.x/25.x):
                                  text-extracted via SEC FTS + filing indexes -> mailroom-s1-corporate-records
  stream_legalbench_tasks_to_bt.py  60+ LegalBench classification tasks
  download_cuad_pdfs.py           full CUAD v1 corpus (PDFs + CUAD_v1.json) to data/cuad_pdfs/
scripts/eda/
  explore_cuad.py                 full-corpus EDA -> data/eda/{report.md,findings.md,figures/}
scripts/eval/
  run_classification_eval.py      one prompt, text/vision/task modes, local PDFs
  run_extraction_eval.py          contracts specialist vs CUAD ground truth
  run_chained_eval.py             sorter -> extractor end-to-end pipeline eval
  run_subtype_eval.py             sorter-only contract-subtype eval (one call per PDF)
  run_binary_class_eval.py        binary question precision/recall/F1
  run_multiclass_eval.py          all-class eval with per-class accuracy
  run_model_matrix.py             model x prompt grid on one surface
  evaluate_prompt_version.py      A/B two prompt versions on the same dataset
  run_annotation_queue.py         HITL annotation queues (llm-dojo mirror)
  run_langfuse_subtype_eval.py        PRIMARY-sink mirror of run_subtype_eval
  run_langfuse_chained_eval.py        PRIMARY-sink mirror of run_chained_eval
  run_langfuse_extraction_eval.py     PRIMARY-sink mirror of run_extraction_eval (--chunked)
  run_langfuse_classification_eval.py Langfuse mirror of run_classification_eval (--prompt-mode task)
  run_langfuse_contracteval_eval.py    directly-mirrored ContractEval benchmark (arXiv 2508.03080):
                                       one (contract, question) call per row over the CUAD test split,
                                       faithful full-context, ContractEval's exact rubric (F1/F2/Jaccard/
                                       false-"no related clause" rate) — see the evals section below
  sync_langfuse_prompts.py        mirror versioned prompts into Langfuse (idempotent)
  sync_langfuse_datasets.py       mirror Braintrust datasets into Langfuse datasets
scripts/datasets/
  build_contracteval_testset.py   build the ContractEval CUAD test split (4,182 pairs / 102 contracts /
                                  41 categories; positives = 1,244) into data/contracteval/
scripts/reporting/
  render_experiment_log.py        rebuild the markdown log from the JSONL source
  report_generator.py             markdown experiment report from Braintrust
  confusion_matrix.py             PNG + CSV confusion matrix from Braintrust
  score_extraction_manifest.py    post-hoc extraction scoring from a manifest
  rescore_manifests.py            re-score extraction manifests with the CURRENT scorer
                                  (immune to scorer drift; --auto-50 covers the 50-doc series)
  judge_experiment.py             post-hoc JudgeAgent review of failed classifications
  backfill_subtype_reasoning.py   one-time enrichment: full failure reasoning from spans
  backfill_cost_estimates.py      one-time backfill: stamp cost_estimated_usd on historical records
  run_contracteval_mapping.py     benchmark stored ONE-PASS extraction runs vs ContractEval Table III (offline)
  run_contracteval_report.py      benchmark directly-mirrored contracteval runs vs the 19-model Table III
                                   + per-category breakdown (offline, reads the experiment log)
scripts/site/
  build_site.py                   rebuild docs/ (GitHub Pages) data from the JSONL
```

</details>

`data/manifests/`, `data/legalbench_local/`, and `data/samples/` are
**gitignored** run checkpoints/local dumps (resumable manifests, the LegalBench
`--local-dump` eval surface) — they appear on disk after runs but are never
committed.

## Experiment log

Every eval run appends ONE record to `reports/experiment_log.jsonl` (plus a
fully expanded section in `reports/experiment_log.md`): experiment name,
timestamp, git commit, model, prompt version, data source + fingerprint,
sample quantity/seed, ALL run parameters, token usage + cost totals, all
scores (overall, per-field, per-class), and every per-row result — including
the model's raw predicted outputs.

The markdown log is rendered as **tables, never JSON dumps**: per-document
results, a document × field scoring matrix (the full per-doc scoring
calculation), entity-list F1, the factuality audit, CUAD category presence,
expected × predicted **confusion matrices** (classification and sorter
contract-subtype), and predicted extractions. The JSONL is the source of
truth; the markdown is rebuilt from it at any time:

```bash
python scripts/reporting/render_experiment_log.py          # rebuild the whole markdown log
python scripts/reporting/render_experiment_log.py --dry-run  # print instead of write
python scripts/site/build_site.py                          # rebuild the site data (docs/)
python scripts/site/build_site.py --check                  # verify the site data is current
```

```bash
# Inspect the whole history
python - <<'PY'
import json
for line in open("reports/experiment_log.jsonl"):
    r = json.loads(line)
    print(r["experiment_name"], r["model"], r["prompt_version"],
          r["scores"].get("overall_extraction_score"), r["tokens"]["total_tokens"])
PY
```

Paths default to `reports/experiment_log.{jsonl,md}` and are overridable with
`EXPERIMENT_LOG_PATH` / `EXPERIMENT_LOG_MD_PATH` or `--experiment-log`.

## Website

The associated website for this repo is a static experiment-log viewer
served by GitHub Pages — **no Actions runners**:

**https://exios66.github.io/llm-entity-extraction/**

- The site lives entirely in `docs/` (see `docs/README.md`): a
  dependency-free single-page viewer with a filterable/searchable runs index,
  per-run detail pages (scores, per-field breakdowns, per-document results,
  confusion matrices, failure insights), and lazy-loaded run data.
- **Posit Cloud portal** (complementary, same URL prefix): a Quarto website
  at `docs/posit/` (`site/` sources) integrating the **experiment log**, the
  **agent kanban board**, and the **discussion board** under one themed URL
  with a custom light/dark gradient theme, navbar, and search — deployable
  from Posit Cloud (`quarto render site` + publish) or served by GH Pages
  with zero Actions (see `site/README.md` and `docs/README.md`).
- **Every run is cost-scored**: OpenRouter usage payloads carry no cost, so
  the site computes deterministic token × price estimates per run (and shows
  billed OpenRouter totals when the activity CSV is ingested).
- **Visualization (v0.15.0)**: per-task score-trend charts (smoothed,
  per-prompt lines), a cost-vs-quality scatter (log-scale cost axis), and
  subtype failure-mode stacked bars — every chart point is hover-inspectable
  (run detail tooltip) and click-navigates to its run. A `#/prompts` diff
  view compares prompt versions side by side with their score deltas, a
  `#/memos` tab renders the archived research memos (`memos/*.md`), and
  the same-surface guardrail (dataset fingerprint + seed + sample size)
  keeps "Δ vs best" honest across runs.
- `docs/data/` is DERIVED from `reports/experiment_log.jsonl` via
  `scripts/site/build_site.py` — never hand-edit it. After every run:

  ```bash
  python scripts/reporting/render_experiment_log.py   # markdown log
  python scripts/site/build_site.py                   # site data
  ```

- Enabling Pages is a one-time repo setting: **Settings → Pages → Deploy from
  a branch → `main` → `/docs`**.
- The project **wiki** (https://github.com/Exios66/llm-entity-extraction/wiki)
  is version-controlled in `docs/wiki/` and pushed with `./docs/wiki/sync-wiki.sh`.

## Setup

Dependencies ship as purpose-scoped batches (KANBAN-081): install only what
your operative task needs. The core floor is deliberately small — exactly the
agent → prompt → scoring chain (all llm-mailroom imports):

```bash
python3 -m venv .venv && source .venv/bin/activate   # recommended; .venv/ is gitignored
pip install -r requirements.txt                      # CORE only
cp config/environments/braintrust.env.example config/environments/braintrust.env   # fill in creds (org/project/API key)
cp config/environments/.env.example config/environments/.env                       # fill in OPENROUTER_API_KEY
```

Add task-specific batches on top (each mirrors a pyproject extra; membership
pinned by `tests/test_dependency_manifests.py`):

| Batch | Install | Unlocks |
|---|---|---|
| `tracing` | `pip install -r requirements/tracing.txt` | Langfuse + Arize Phoenix observability (default eval-runner sink) |
| `evals` | `pip install -r requirements/evals.txt` | Braintrust dataset streaming / experiment logging |
| `datasets` | `pip install -r requirements/datasets.txt` | HF Hub publishers + PDF/vision page rendering |
| `reporting` | `pip install -r requirements/reporting.txt` | Decks, EDA plots, xlsx exports |
| `embeddings` | `pip install -r requirements/embeddings.txt` | Local semantic embedding rescue (pulls torch ~2–3 GB) |
| `dev` | `pip install -r requirements/dev.txt` | Test suite (includes the tracing modules' deps) |
| `all` | `pip install -r requirements/all.txt` | Every non-dev batch in one flag |

Equivalent package extras: `pip install -e ".[tracing]"`, `-e ".[evals]"`,
`-e ".[datasets]"`, `-e ".[reporting]"`, `-e ".[embeddings]"`,
`-e ".[dev]"`, `-e ".[all]"`.

The vision pipeline additionally needs the poppler system binary for PDF → PNG
rendering: `brew install poppler` (or `apt install poppler-utils`).

The repo is also pip-installable so the LangChain agents can be imported and
called from OTHER codebases (e.g. the llm-mailroom LangGraph architecture):

```bash
pip install -e .        # editable: new agent/prompt changes are picked up immediately
# then, from anywhere:
from agents.sorter_agent import SorterAgent
from agents.judge_agent import JudgeAgent
from agents.specialist_agents import ContractsSpecialist
```

Optional — local semantic embedding rescue (recommended): install the
`embeddings` batch to embed with the local `all-MiniLM-L6-v2` model
(free, fast, offline, reproducible) instead of paid OpenRouter embedding calls:

```bash
pip install -r requirements/embeddings.txt   # or: pip install -e ".[embeddings]"  (pulls torch ~2-3 GB)
```

Both routes are verified and interchangeable: the scorer uses the local model
when available and falls back to OpenRouter embeddings automatically when it
isn't. Without sentence-transformers, the rescue still works (OpenRouter
fallback, tiny per-request cost); with it, nothing is sent to the network.

Required env vars (in `braintrust.env` or `.env`; see `src/env_utils.py` —
and the full per-provider/per-sink guide in
[`docs/configuration.md`](docs/configuration.md)):

<details>
<summary>Environment variable table</summary>

| Variable | Purpose |
|---|---|
| `BRAINTRUST_ORG_ID` | Braintrust org |
| `BRAINTRUST_PROJECT_ID` / `BRAINTRUST_PROJECT_NAME` | project for experiments/datasets |
| `BRAINTRUST_API_KEY` | key with write access to the project |
| `BRAINTRUST_API_BASE` | API base (default `https://api.braintrust.dev`) |
| `BRAINTRUST_MODEL` | default eval model (default `qwen/qwen3.7-flash`) |
| `BRAINTRUST_DATASET_PROJECT` | project holding the datasets |
| `OPENROUTER_API_KEY` | LLM calls through OpenRouter |
| `OPENROUTER_BASE_URL` | optional: any OpenAI-compatible endpoint (Ollama, vLLM) |
| `EXPERIMENT_LOG_PATH` / `EXPERIMENT_LOG_MD_PATH` | experiment log paths (optional) |

</details>

## Sync the HF corpora into Braintrust

<details>
<summary>Dataset sync commands — CUAD / MAUD / S-1 / LegalBench tasks / local PDF mirror</summary>

```bash
# 1. CUAD / The Atticus Project (510 contract PDFs): ONE row per PDF with ALL
#    of its pages as image attachments + full contract text + 41 clause-category
#    QA ground truth (the extraction agent's labels), expected doc_type=contract
python scripts/datasets/stream_cuad_to_bt.py --limit 12 --dry-run     # preview
python scripts/datasets/stream_cuad_to_bt.py --limit 12               # 12 PDFs, every page
python scripts/datasets/stream_cuad_to_bt.py                          # all 510 PDFs
python scripts/datasets/stream_cuad_to_bt.py --category "Franchise" --max-pages 30

# 2. LegalBench MAUD (via Zenodo; legacy Braintrust path)
python scripts/datasets/stream_legalbench_to_bt.py --limit 6 --dry-run
python scripts/datasets/stream_legalbench_to_bt.py

# 2b. MAUD as a UTILIZED dataset (KANBAN-033): 152 merger agreements with the
#     merger_agreement doc class + consideration-type subclass GT, plus the
#     25,827-row per-question suite (22 question families, 7 MAUD categories
#     as metadata). --local-dump is the reliable path while Braintrust row
#     uploads are org-capped; the Langfuse mirror upserts the same records.
python scripts/datasets/stream_maud_to_bt.py --dry-run
python scripts/datasets/stream_maud_to_bt.py --local-dump data/maud/
python scripts/datasets/stream_maud_to_bt.py --source huggingface --split all --dry-run
python scripts/eval/sync_langfuse_datasets.py --maud --dry-run

# 2c. EDGAR S-1 corporate-record exhibits (EX-3.x/4.x/21.x/24.x/25.x):
#     SEC full-text search -> filing index -> text extraction. Ground truth
#     corporate_record + content-detected record_type subclass; the exhibit
#     code stays in metadata (provenance, not a classification level).
python scripts/datasets/stream_s1_exhibits.py --dry-run
python scripts/datasets/stream_s1_exhibits.py --max-filings 40 --limit 100 --local-dump data/s1_corporate_records/
python scripts/eval/sync_langfuse_datasets.py --s1 --dry-run

# 2d. Hierarchical doc-class eval (the new sorter task): doc_type (7 classes,
#     incl. merger_agreement) + doc_subclass (consideration type / record
#     type) scored across MAUD + CUAD + S-1 records in one mixed surface.
python scripts/eval/run_langfuse_docclass_eval.py --dry-run
python scripts/eval/run_langfuse_docclass_eval.py --local-dumps data/datasets/docclass_merged.jsonl \
  --stratified 120 --seed 42 --sorter-prompt-version sorter_docclass_v7

# 2e. Correspondence-only Enron eval (KANBAN-103): primary doc_type +
#     communication-function subclass + sentiment polarity, joined from
#     Lucius-Morningstar/enron-correspondence-dedup (agent-blind + GT).
#     Emails are short — default cap 20k chars; Braintrust traces ON.
python scripts/eval/run_correspondence_eval.py --dry-run --stratified 200 --seed 42
python scripts/eval/run_correspondence_eval.py --stratified 200 --seed 42 \
  --experiment-name qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42

# 3. LegalBench multi-class classification tasks (cuad_*, hearsay, and more)
#    from the GitHub raw data — one Braintrust dataset per task; synced rows
#    carry deterministic ids (reruns upsert, never duplicate)
python scripts/datasets/stream_legalbench_tasks_to_bt.py --dry-run
python scripts/datasets/stream_legalbench_tasks_to_bt.py --tasks hearsay   # e.g. the hearsay task:
                                                                           # 5 train rows, Yes/No, 5 slices
python scripts/datasets/stream_legalbench_tasks_to_bt.py --tasks all

# OPTIONAL — keep the FULL CUAD corpus locally instead of streaming to Braintrust:
# all 510 contract PDFs (CUAD folder structure preserved) + CUAD_v1.json clause
# QA annotations, mirrored into data/cuad_pdfs/. Resumable: re-running skips
# already-downloaded files. Feed the local PDFs to the eval loop with --pdf-dir.
python scripts/datasets/download_cuad_pdfs.py --dry-run      # preview
python scripts/datasets/download_cuad_pdfs.py --limit 12     # first 12 PDFs
python scripts/datasets/download_cuad_pdfs.py                # all 510 + CUAD_v1.json
python scripts/datasets/download_cuad_pdfs.py --category "Franchise"
python scripts/datasets/download_cuad_pdfs.py --out-dir data/cuad_pdfs --skip-json
python scripts/datasets/download_cuad_pdfs.py --overwrite    # re-download everything
```

</details>

## The loop (one prompt at a time)

<details>
<summary>Command gallery — classification / extraction / chained / subtype / A/B examples</summary>

```bash
# Vision classification of the CUAD PDFs (ONE row per PDF, ALL pages in one call)
python scripts/eval/run_classification_eval.py \
    --dataset mailroom-cuad-contracts --input-mode vision \
    --prompt-version sorter_vision_v0

# Same, but for a local folder of ACTUAL PDFs (rendered at eval time)
python scripts/eval/run_classification_eval.py \
    --pdf-dir ./pipeline/inbox --expected contract \
    --prompt-version sorter_vision_v0

# Full-text classification
python scripts/eval/run_classification_eval.py \
    --dataset mailroom-cuad-contracts --input-mode text --prompt-version sorter_v0

# LegalBench multi-class task eval (Yes/No clause classification)
python scripts/eval/run_classification_eval.py \
    --dataset mailroom-lb-cuad_governing_law --prompt-mode task \
    --valid-classes Yes,No --prompt-version legalbench_task_v0

# The hearsay task (binary: does the evidence qualify as hearsay? 5 train
# rows, 2 Yes / 3 No; dry-run first — it spends LLM money)
python scripts/eval/run_classification_eval.py \
    --dataset mailroom-lb-hearsay --prompt-mode task \
    --valid-classes Yes,No --prompt-version legalbench_task_v0 --dry-run
python scripts/eval/run_classification_eval.py \
    --dataset mailroom-lb-hearsay --prompt-mode task \
    --valid-classes Yes,No --prompt-version legalbench_task_v0

# Same surface traced into the llm-dojo Langfuse project
python scripts/eval/run_langfuse_classification_eval.py \
    --dataset mailroom-lb-hearsay --prompt-mode task \
    --valid-classes Yes,No --prompt-version legalbench_task_v0

# A/B two prompt versions on the same dataset
python scripts/eval/evaluate_prompt_version.py \
    --dataset mailroom-cuad-contracts --input-mode vision \
    --prompt-a sorter_vision_v0 --prompt-b sorter_vision_v1

# ---- Entity EXTRACTION eval (contracts specialist vs CUAD ground truth) ----
# Content-scored: every extracted field is compared against the CUAD clause-QA
# labels with the field-type-aware scorer (date/money/name/free-text,
# entity-list bipartite F1, semantic embedding rescue — local
# sentence-transformers with an OpenRouter embedding fallback). The task
# computes ALL scores locally and returns a composite
# output; registered Braintrust scorers are trivial lookups on it.
# Default --bt-scores overall registers the cross-experiment tracker pair:
# overall_extraction_score (complex content accuracy) + field_presence
# (binary conformance) — comparable across every run in the Braintrust UI.
# With --bt-scores full, per-field trackers report the SAME list score that
# feeds the field scores (ground-truth coverage for partial-GT fields like
# parties/key_obligations/termination_clauses, F1 otherwise); raw
# precision/recall/F1 are kept in each row's entity_list_scores metadata.
python scripts/eval/run_extraction_eval.py \
    --dataset mailroom-cuad-contracts --prompt-version contracts_specialist_v2 \
    --manifest data/manifests/extract_v2.jsonl
python scripts/reporting/score_extraction_manifest.py data/manifests/extract_v2.jsonl \
    --output reports/extraction_v2.md          # post-hoc scoring report (free)
python scripts/eval/run_extraction_eval.py --bt-scores none --limit 3   # pure local
python scripts/eval/run_extraction_eval.py --bt-scores full --limit 3   # + per-field scorers
python scripts/eval/run_extraction_eval.py --judge --limit 3            # LLM-judge ambiguous band
python scripts/eval/run_extraction_eval.py --prompt-version contracts_specialist_v1  # A/B vs v2

# ---- Chained pipeline eval (sorter -> extractor, end to end) ----
python scripts/eval/run_chained_eval.py \
    --dataset mailroom-cuad-contracts \
    --sorter-prompt-version sorter_v1 --extractor-prompt-version contracts_specialist_v4 \
    --manifest data/manifests/chained_5.jsonl

# ---- SORTER-ONLY subtype eval (contract subclass classification) ----
# One sorter call per PDF; scored for doc_type accuracy, EXACT subtype
# accuracy (CUAD-folder key) AND family-level accuracy (subtype_accuracy_equiv
# — defensible family equivalents like reseller/distributor,
# maintenance/license, development/license, affiliate/joint_venture count as
# correct routing). Per-subtype accuracy + expected x predicted confusion
# matrix in the repo log.
#
# PRIMARY SINK: run the Langfuse mirror (per-document traces + scores in
# Langfuse, LLM spans in LangSmith). The Braintrust runner below is the
# local-scoring / manifest-resume path — with BRAINTRUST_LOGGING disabled
# (the default) it skips braintrust.Eval entirely.
python scripts/eval/run_langfuse_subtype_eval.py \
    --dataset mailroom-cuad-contracts-full --stratified 250 --seed 42 \
    --sorter-prompt-version sorter_v11 --dry-run          # preview
python scripts/eval/run_subtype_eval.py --dry-run                  # preview (local path)
python scripts/eval/run_subtype_eval.py --sorter-prompt-version sorter_v3 \
    --manifest data/manifests/subtype_50_v3.jsonl
python scripts/eval/run_subtype_eval.py --sample 10 --seed 42      # pilot slice

# Inspect results
python scripts/reporting/report_generator.py --experiment qwen3.7-flash_sorter_vision_v0
python scripts/reporting/confusion_matrix.py --experiment qwen3.7-flash_sorter_vision_v0
python scripts/reporting/render_experiment_log.py
```

</details>

Experiment naming is `{model-slug}_{prompt-version}` (optionally suffixed
`_binary-{class}` / `_multiclass` / `_extraction` / `_chained`), so re-running
the same command overwrites the same experiment — identical prompt versions
are directly comparable in the Braintrust UI, and different prompt versions
never collide.

### Eval runners

<details>
<summary>Runner reference table — every script, its flags and scorers</summary>

| Script | Tests |
|---|---|
| `run_classification_eval.py` | one prompt version; `--input-mode auto/text/vision`, `--prompt-mode sorter/task`, `--valid-classes`, `--vision-pages all/first` (all pages of each PDF in one call by default), `--pdf-dir`/`--documents-dir`/`--images-dir` for local inputs, exact_match/failure/cost scorers, resumable manifest |
| `run_extraction_eval.py` | contracts-specialist **entity extraction** vs CUAD clause-QA ground truth: `overall_extraction_score` (complex content accuracy) + `field_presence` (binary guard) registered by default as cross-experiment trackers — composite-output lookups, nothing recomputed on Braintrust; `--bt-scores none/overall/full`; optional `--judge` pass for the ambiguous band; manifest-based post-hoc scoring via `score_extraction_manifest.py` |
| `run_chained_eval.py` | end-to-end pipeline: sorter (doc_type + contract subtype) → contracts specialist; per-stage scores and token usage, sorter subtype accuracy + extractor content scores in one record |
| `run_binary_class_eval.py` | one prompt version on a binary question (e.g. `--positive contract`), precision/recall/F1 |
| `run_multiclass_eval.py` | one prompt version across all taxonomy classes, per-class + macro accuracy |
| `run_subtype_eval.py` | sorter-only contract-family eval: one classification per PDF; `sorter_exact_match` (doc_type), `sorter_subtype_accuracy` (EXACT CUAD-folder key) and `sorter_subtype_accuracy_equiv` (family-level — defensible equivalents like reseller/distributor, maintenance/license, development/license, affiliate/joint_venture recognized as correct routing), per-subtype accuracy + confusion matrix in the repo log |
| `evaluate_prompt_version.py` | A/B: two prompt versions on the same dataset, delta summary |
| `run_langfuse_subtype_eval.py` | **Primary-sink mirror** of `run_subtype_eval` (same data/task/scorers) — one per-document Langfuse trace with numeric scores in `llm-dojo`, zero Braintrust scored-run quota; every LLM call also auto-traces to LangSmith |
| `run_langfuse_chained_eval.py` | **Primary-sink mirror** of the chained eval: per-agent spans (`sorter`, `contracts_specialist`) with each agent's designated task scores attached to its own observation; `--handoff-scope subtype` (default) cues the specialist with the predicted subtype's CUAD field groups |
| `run_langfuse_extraction_eval.py` | **Primary-sink mirror** of the specialist-only extraction eval (`--chunked` supported — the truncation-doctrine A/B surface) |
| `run_langfuse_classification_eval.py` | **Langfuse mirror** of the doc-type classification eval (text mode); `--prompt-mode task` + `--valid-classes` mirror the LegalBench task eval too (e.g. `mailroom-lb-hearsay`), one `legalbench_task` observation per row |
| `run_langfuse_contracteval_eval.py` | **Directly-mirrored ContractEval benchmark** (arXiv 2508.03080, KANBAN-052): one (contract, question) call per row over the CUAD test split (4,182 pairs / 102 contracts / 41 categories; build via `scripts/datasets/build_contracteval_testset.py`), ContractEval's exact system prompt (`contracteval_v0`), faithful full-context (`--max-input-chars 0` = no cap; temp 0; max_tokens 5000), ContractEval's EXACT rubric scored upstream (`llm-dojo-scoring` `contracteval` kind, pinned `@v0.10.0`): F1/F2/acc/prec/recall, token-set Jaccard over positives, false-"no related clause" rate (own + paper's 1,244 denominator), per-category breakdown; one `contracteval` observation per pair + one experiment-log record (`task: contracteval`). Compare vs Table III with `scripts/reporting/run_contracteval_report.py` |

Every runner supports `--samples-per-class`/`--sample`, `--sample-seed`/`--seed`,
`--limit`, `--dry-run`, `--experiment-log`, and stamps the full prompt text
into experiment metadata. `run_classification_eval`/`run_extraction_eval`/
`run_chained_eval` additionally accept `--manifest` (JSONL checkpoint) so an
interrupted run resumes without re-paying LLM calls.

</details>

### Prompt versions

<details>
<summary>Registered prompt families — sorter / vision / task / specialists / judges</summary>

Registered in `src/prompts.py` → `PROMPT_VERSIONS` (aliases noted):

| Family | Versions |
|---|---|
| Sorter (text) | `sorter_v0` (alias `sorter`), `sorter_v1` … `sorter_v14`, `sorter_docclass_v0` … `sorter_docclass_v7`, `sorter_docclass_vision_v1` |
| Sorter (vision) | `sorter_vision_v0` |
| LegalBench task | `legalbench_task_v0` |
| Contracts specialist | `contracts_specialist` (v0), `contracts_specialist_v1` … `contracts_specialist_v31` |
| Other specialists | `corporate_records_specialist`, `due_diligence_specialist`, `correspondence_specialist`, `compliance_specialist`, `court_opinions_specialist` |
| Agents / judges | `boss`, `reporter`, `judge`, `judge-classification`, `judge-correctness` |
| PDF | `pdf_transcriber` |

Run `python -c "from src.prompts import list_prompts; print('\\n'.join(list_prompts()))"`
for the authoritative, current list.

</details>

### LangChain + Braintrust wiring

The eval runners call `braintrust.integrations.langchain.setup_langchain()`
before any model call **when Braintrust logging is enabled**
(`BRAINTRUST_LOGGING=enabled`; it is **disabled by default**). That installs the
Braintrust LangChain callback handler, so every
`ChatPromptTemplate -> ChatOpenAI -> parser` chain invocation inside the eval
task is traced as a nested span under the Braintrust experiment row — prompt,
response, tokens, latency are all visible in the UI. With the default
`BRAINTRUST_LOGGING=disabled`, the runners skip `setup_langchain` + `braintrust.Eval`
entirely and run the same local scoring loop through `src/eval_shims.py` —
the PRIMARY sink is Langfuse (`run_langfuse_*_eval.py`) + LangSmith spans (see
AGENTS.md "Run sink").

### Langfuse mirror (two projects, two purposes)

<details>
<summary>Langfuse project split, designated tasks & handoff-scope results</summary>

The `run_langfuse_*_eval.py` runners execute the SAME datasets, tasks, and
deterministic logic scorers as their Braintrust counterparts, but trace into a
SEPARATE Langfuse project — **llm-dojo** by default (keys in gitignored
`config/environments/langfuse.env`, `config/environments/langfuse.env.example`
in-repo): this repo's prompt
iterations run and are reviewed there. A second project
(`llm-mailroom-experiments`) is EXCLUSIVELY for testing the full mailroom
pipeline in the llm-mailroom repo; insights flow llm-dojo → llm-mailroom,
never the reverse (see AGENTS.md "Langfuse projects"). Every trace carries
`environment=<LANGFUSE_ENVIRONMENT>` and a session-scoped deterministic
trace id, so re-runs of one experiment update their traces in place and
different experiments never merge. Langfuse runs never consume Braintrust
scored-run quotas: the logic scorers are computed locally and logged per trace
as NUMERIC scores. `scripts/eval/run_annotation_queue.py` builds the HITL
review queues on top of these traces (low-performing extractions +
failed sorter classifications → one shared annotation queue).

Each pipeline agent has a **designated task** traced as its own observation
with its scores attached to that observation — per-agent performance metrics
derivable over time in Langfuse:

| Agent | Observation | Task scores |
|---|---|---|
| `sorter` | span per document | `exact_match`, `subtype_accuracy`, `subtype_accuracy_equiv`, `confidence` |
| `contracts_specialist` | span per document | `overall_extraction_score`, `field_presence`, `overall_verified_precision`, `category_presence`, `schema_valid` |

The chained mirror passes the sorter's class + subclass to the specialist via
`handoff_context`; with `--handoff-scope subtype` (default) the specialist is
additionally cued with the PREDICTED subtype's CUAD field-group scope
(`build_subtype_handoff` — expected schema fields + applicable /
never-applicable clause categories; a pure function of the subtype, no
ground-truth answers). `--handoff-scope none` reproduces the legacy handoff.
Measured on the same 5-doc chained sample: overall 0.8666 vs 0.8497 (+1.7pp)
and category presence 0.7773 vs 0.7106 (+6.7pp).

```bash
cp config/environments/langfuse.env.example config/environments/langfuse.env   # fill in the SEPARATE project's keys
python scripts/eval/run_langfuse_chained_eval.py --sample 5 --seed 42 \
    --sorter-prompt-version sorter_v6 --extractor-prompt-version contracts_specialist_v11 \
    --manifest data/manifests/chained_langfuse.jsonl
```

</details>

## Adding a prompt version

1. Add a constant to `src/prompts.py` (e.g. `SORTER_PROMPT_V1`) and register it
   in `PROMPT_VERSIONS` under a version key (e.g. `"sorter_v1"`).
2. Run the eval with `--prompt-version sorter_v1`.
3. A/B against `sorter_v0` with `evaluate_prompt_version.py`.

## Tests

```bash
python -m pytest tests/ -v
```

375 tests, none hitting the network: prompts, scorers, taxonomy, evaluation
helpers, config loading, field scoring, CUAD ground truth, the subtype
handoff cue, page voting, the chained/extraction/classification/subtype/langfuse
eval smoke loops, the Langfuse annotation-queue + prompt-sync tooling, the
release workflow, the site builder, and the streamer parsers are all mocked.

## Credits

This project builds on — and evaluates against — the following openly
licensed corpora, benchmarks, and frameworks:

- **[LegalBench](https://github.com/HazyResearch/legalbench)** (Guha et al.,
  "LegalBench: A Collaboratively Built Benchmark for Measuring Legal
  Reasoning in Large Language Models," NeurIPS 2023, CC BY 4.0) — the
  multi-class classification tasks (`cuad_*`, `maud_*`, `hearsay`,
  `personal_jurisdiction`, `rule_qa`, and 60+ more) synced as
  `mailroom-lb-<task>` Braintrust datasets. The **hearsay** task
  (binary Yes/No, 100 samples) was contributed by Neel Guha.
- **[CUAD](https://huggingface.co/datasets/theatticusproject/cuad)** — the
  Contract Understanding Atticus Dataset (Hendrycks et al., "CUAD: An Expert-
  Annotated NLP Dataset for Legal Contract Review," NeurIPS 2021), created by
  **The Atticus Project** — the 510-contract PDF corpus and the 41-category
  clause-QA ground truth behind the extraction evals and the sorter's
  contract-subtype taxonomy.
- **[MAUD](https://zenodo.org/records/7500064)** — the Merger Agreement
  Understanding Dataset (CC BY 4.0) behind LegalBench's `maud_*` tasks,
  synced from the official v1 release.
- **[GEPA](https://arxiv.org/abs/2507.19457)** — the Genetic-Pareto (GEPA)
  framework for reflective prompt evolution (arXiv:2507.19457), the
  methodology the `prompt-engineer` agent applies to every prompt
  iteration in this repo.
- **[LangChain](https://github.com/langchain-ai/langchain)** /
  **[LangGraph](https://github.com/langchain-ai/langgraph)** — the agent
  framework under test; **[Braintrust](https://braintrust.dev)** and
  **[Langfuse](https://langfuse.com)** — the tracing/eval backends.

## Docs & navigation

**Repo root (this file)** — the front door. Then, by depth:

- `AGENTS.md` — the agent workflow guide: setup, commands, architecture,
  conventions, gotchas, and the inter-agent message-board protocol.
- `governance/MESSAGE_BOARD.md` — the living Kanban canvas shared by all agents
  (backlog / in_progress / blocked / in_review / done, discussion log,
  archive).
- `CHANGELOG.md` — semantic-version history of all significant releases
  (each tagged `vX.Y.Z`).
- [`docs/SCORING.md`](docs/SCORING.md) — every scorer and metric: where scoring lives (the
  `llm-dojo-scoring` package), classification, binary, multiclass, subtype,
  docclass hierarchical, task-aware (MAUD / LegalBench / court opinions /
  chained), field-type-aware content scoring, factuality audit, judge
  calibration, chained stage trackers + ablation, A/B deltas, cost
  accounting, Monte Carlo robustness, bootstrap CIs.
- `reports/V16_PROPOSITION.md` — the historical research proposition behind the
  v16+ prompt iterations (champion lineage, model sweeps).

**Per-area maps** — one README per top-level area, kept current with the
layout: [`agents/README.md`](agents/README.md) ·
[`config/README.md`](config/README.md) · [`src/README.md`](src/README.md) ·
[`scripts/README.md`](scripts/README.md) · [`tests/README.md`](tests/README.md) ·
[`reports/README.md`](reports/README.md) · [`docs/README.md`](docs/README.md) ·
[`docs/slides/README.md`](docs/slides/README.md) · [`docs/memos/README.md`](docs/memos/README.md).

**Working surfaces** — [`reports/experiment_log.md`](reports/experiment_log.md)
(rendered experiment log) · the [GH Pages site](https://exios66.github.io/llm-entity-extraction/)
(scoring decks, run viewer, board, memos) · the [graphify knowledge graph](https://exios66.github.io/llm-entity-extraction-graph/)
(interactive code-structure map of this repo; build artifact — see
[`docs/sister-repos.md`](docs/sister-repos.md)) · the public [wiki](https://github.com/Exios66/llm-entity-extraction/wiki)
(`docs/wiki/`, pushed with `./docs/wiki/sync-wiki.sh`) ·
[The-Mailroom](https://github.com/Exios66/The-Mailroom)
(the sister pipeline's pixel-art visual engine — an animated document
conveyor rendered purely from llm-mailroom's Langfuse traces).
