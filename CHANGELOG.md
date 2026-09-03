# Changelog

All notable changes to **llm-entity-extraction** are cataloged here in
[semantic version](https://semver.org/) order. Every significant milestone is
tagged `vX.Y.Z`; each version maps to a single commit, so the changelog is a
history of the repository's tags. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Direct Hugging Face data pipe into the docclass eval runner (KANBAN-107).**
  `run_langfuse_docclass_eval.py` gains `--dataset-source {braintrust,local,hf}`
  (default `braintrust`; an explicit `--local-dumps` keeps the legacy local
  default) plus `--hf-dataset` (default `Lucius-Morningstar/mailroom-corpus`),
  `--hf-config` (default `ground_truth`) and `--hf-revision` (default None =
  repo default) so the OpenRouter-vs-Modal comparison can run on the mailroom
  EDA corpus directly from HF — no intermediate JSONL export hop. New
  `src/hf_docclass_corpus.py::load_hf_docclass_corpus(repo, config, revision,
  valid_classes)` is a pure loader joining the `default` blind config
  (doc_text/prompt/filename/metadata) with the ground-truth config (labels +
  GT fields) on filename (mirror of `export_hf_docclass_merged.py`); rows match
  the runner shape (`expected` from doc_type/expected_doc_class,
  `expected_subclass`, `metadata`, `expected_fields`/`expected_output` when
  present, `gt_fields`, `split`) and the honesty rules mirror
  `load_braintrust_dataset` (invalid classes / empty text skipped, never
  fabricated); `meta` carries repo/config/revision/num_rows + a content sha
  when the datasets lib exposes per-shard checksums (else None); `datasets` is
  imported inside the function for stubbing. The HF source reuses the existing
  valid-class filter + sampling/limit logic and attaches the HF identity
  (repo/config/revision/rows/sha) to the run record `data_source` block;
  braintrust/local paths untouched, `src/serving_meta.py` untouched. Network-free
  pins: `tests/test_hf_docclass_corpus.py` (7 — fake `datasets` module in
  `sys.modules`; join/class-filter/empty-skip/stable-filename/
  revision-passthrough/sha-when-obtainable + two runner dry-run smokes).
- **Serving / cost-comparison metadata on completed-run records (KANBAN-106).**
  Every completed subtype-run experiment-log record now carries a `serving`
  block (`src/serving_meta.py::build_serving_block`) so a completed OpenRouter
  run and a completed Modal-hosted vLLM Qwen3-8B run compare faithfully from
  the append-only log alone: `provider`/`endpoint` (classified from the
  `OPENROUTER_BASE_URL` seam), `model` identity (+ HF checkpoint id for Modal),
  sha256 `prompt_fingerprints` over each prompt version's literal text,
  `dataset_fingerprint`, prompt/completion/total `tokens`, `timing`
  (wall-clock window + per-call latency `first_s`/`median_s`/`mean_s`/`max_s`,
  excluding manifest-replayed rows), `gpu` metadata from the `MODAL_VLLM_*`
  deploy knobs (GPU/quantization/max-model-len + taxonomy `gpu_hourly_usd`),
  `price_basis` (taxonomy per-1M-token prices and/or GPU-hourly with a labeled
  `estimated_gpu_cost_usd` lower bound), and `phase` (`SERVING_PHASE=cold|warm`,
  else `unknown` — never guessed). Wired into `run_subtype_eval.py` +
  `run_langfuse_subtype_eval.py` via the shared `log_experiment_to_repo`;
  append-only log + manifest/resume semantics unchanged. Network-free pins:
  `tests/test_serving_meta.py` (14) + record asserts in
  `tests/test_subtype_eval_smoke.py`. Docs: `docs/SCORING.md` §13.1 +
  `config/environments/.env.example` deploy block.
- **Docclass-merged v6 rev1 — correspondence rebalance + original files +
  blind-surface repair (KANBAN-105).** Human directive 2026-08-30; the merged
  corpus was contracts-concentrated (contract 509 + merger_agreement 152 =
  54.6% of the 1,210 v5 rows; correspondence 110 = 9.1%). **+240
  correspondence** via `build_correspondence_append.py` (deterministic
  sha256-within-stratum draw from the
  [`enron-correspondence-dedup`](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup)
  GT pool — 247,413 available after excluding every existing filename; strata
  demand 35 / email 35 / letter 34 / meeting_request 34 / memo 34 / notice 34
  / press_release 34; `attorney_demand` honestly exhausted — all 3 corpus rows
  already in the v4 sample; **3-labeler verification pass GREEN** — the shared
  Enron labelers re-run on every drawn row reproduce the Hub GT on 960/960
  checks; KANBAN-103 overrides honored, 0 hits) + **700 originals** staged by
  `attach_original_files.py` (509 CUAD source PDFs + 152 MAUD `contract_N.txt`
  + 39 S-1 EDGAR exhibit originals; per-file sha256 +
  `original_files_mapping.jsonl` sidecar). **Blind-surface repair** (found at
  publish): the v4-era flat dump rode `expected_doc_type` / `expected_subclass`
  inside blind `metadata` and v5 shipped it verbatim, contradicting the card's
  "NO label columns" contract — v6 strips them (labels live ONLY in the
  `ground_truth` config; no repo consumer read the Hub blind metadata labels —
  verified across the BT/Langfuse mirrors and eval runners). Fixed en route:
  `render_card` asserted a v6 section before inserting it;
  `download_cuad_pdfs.py` 404'd on `#`-containing CUAD filenames (unencoded
  URL fragment).
- **Docclass-merged v6 rev2 PUBLISHED — FILE-COMPLETE `files/` tree + insurance
  boost (KANBAN-105).** Human directive (in-session): ALL document classes must
  be present at `docclass-merged/files`, same as contract/corporate_record/
  merger_agreement. [`Lucius-Morningstar/docclass-merged`](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged)
  now serves **schema v6 rev2 (1,650 rows; contract 509 / insurance_claim 600 /
  correspondence 350 / merger_agreement 152 / corporate_record 39)** with
  **1,650/1,650 originals under `files/` (153MB, sha round-trip verified across
  all five classes)**: `attach_original_files.py` extended with
  **correspondence → 350 CMU maildir raw RFC822 messages** (the row filename IS
  the maildir path; originals staged from
  [Enron-Evaluation-Environment](https://github.com/Exios66/Enron-Evaluation-Environment)
  `acquire_enron.py` — the human-named source repo; `doc_text` is only the
  composed Subject+body so the original carries the full headers) and
  **insurance_claim → 600 rendered EOB documents** (claims-data-eda
  `render_eob`; the render IS the original, staged verbatim). Publisher now
  asserts the file-complete contract (0 rows without `metadata.original_file`)
  and renders revision-idempotent cards (scalar anchors tolerate any prior rev;
  KANBAN-105 sections replace whole — `upsert_section` — never duplicate).
  **Insurance +200 landed**: `build_extra_claims.py` emitted 50/50/50/50 across
  carrier/inpatient/outpatient/pde (subtype-balanced round-robin — the claims
  sampler's output is type-grouped, so a first-N slice yields one family;
  measured 200/200 carrier), family split asserted at emit, verbatim GT
  contract verified per row, exclusion set fixed to actually see the parent
  400 (`glob("**/*.parquet")` — split subdirs). Acquire robustness: Wayback is
  unreachable from this machine (session-verified) — the CMS CDN serves the
  identical carrier/PDE archives (HTTP 200; acquirer zip-tests each download),
  appended as last-resort candidates; the 2010 Beneficiary Summary stays
  honestly unobtainable → documented nearest-year demographic fallback (no
  bene-derived GT keys affected). `publish_docclass_v6.py` patches hub 1.x's
  hardcoded 10s httpx read timeout (600s) — large multi-file PUTs to the CDN
  exceeded it. Hub sha round-trip: 15/15 sampled across all five classes; Hub
  bytes verified: 1,474 train / 176 test per config, 0 rows without
  `original_file`, 0 blind-surface leak keys. **Purpose/gist GT LANDED**: the
  llm-mailroom `sync_hf_ground_truth.py --real --resume` incremental pass
  labeled **375 new purpose-class rows** (488 real seed labels resumed with
  zero re-labeling; 19 honest short-text skips) and pushed the enriched GT
  train shard @ `a88e852b` — **863/1,474 train rows intent-labeled**;
  mailroom `FULL_CORPUS_REVISION` advanced by the push. Mirror re-sync
  (Langfuse llm-dojo + Braintrust Mailroom-Sandbox) blocked on project-scoped
  keys absent from this machine. Pins: `tests/test_kanban105_docclass_v6.py`
  (10 network-free).
- **Braintrust sandbox sync (KANBAN-104).** New runners
  `scripts/eval/sync_braintrust_prompts.py` and
  `scripts/eval/sync_braintrust_datasets.py` mirror the Langfuse twins into
  the **`mailroom-sandbox`** Braintrust project (`--env-file
  braintrust-sandbox.env`; template
  `config/environments/braintrust-sandbox.env.example`, project id
  `ba222477-2e1c-4fef-9f5d-02cc78765fe3`). Prompt sync upserts every
  `PROMPT_VERSIONS` key (incl. all 54 docclass variants) via
  `PUT /v1/prompt`; dataset sync uploads the default eval bundle
  (`--all`: hearsay, CUAD text-only, HF docclass-merged,
  Enron stratified-200 sample; `--enron-full` for ~247k corpus) with deterministic row ids.
  Helpers
  `get_prompt_by_slug` / `upsert_completion_prompt` live in
  `src/braintrust_utils.py`; `BRAINTRUST_SANDBOX_ENV_FILE` in
  `src/env_utils.py`.
- **Enron correspondence eval scaffold (KANBAN-103).** New runner
  `scripts/eval/run_correspondence_eval.py` scores the docclass sorter on
  Hugging Face [`Lucius-Morningstar/enron-correspondence-dedup`](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup)
  as a correspondence-only primary + secondary + sentiment task. Predicted
  fields lock to the Hub `ground_truth` assortment (`doc_type`↔`expected`,
  `doc_subclass`↔`expected_subclass`, `sentiment_label`/`sentiment_score`↔
  same names). Default draw is **200 subclass-stratified** rows (seed 42;
  reserved name `qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42`).
  Prompt `sorter_docclass_correspondence_v0` derives from `sorter_docclass_v7`
  (rule 44 + sentiment output fields); schema `CORRESPONDENCE_EVAL_SCHEMA`
  does not mutate `DOCCLASS_SCHEMA`. Braintrust experiment/span logging is
  **on by default** for this runner (`--no-braintrust-logging` to opt out).
  Loader `scripts/datasets/load_enron_correspondence.py` stratifies on GT
  first, then stream-joins only the selected filenames. Logs + metrics:
  `doc_type_accuracy`, `subclass_accuracy` (+ equiv), `exact_match`,
  `sentiment_label_accuracy`, `sentiment_score_ok` / MAE (band 0.25),
  `correspondence_exact`, CIs, per-subclass / per-sentiment tables,
  confusion, `failure_insights` (incl. `sentiment_miss`).
  `report_generator.py --from-log` renders those scorers from the experiment
  log (Braintrust fetch still works for label-only experiments).
  **Baseline run 2026-08-30** (same 200-row filename manifest, seed 42,
  Braintrust `Mailroom-Sandbox`): `doc_type_accuracy` **1.000**,
  `subclass_accuracy` **0.400** (CI 0.335–0.465), `sentiment_label_accuracy`
  **0.630**, `sentiment_score_ok` **0.779** (MAE 0.1593),
  `correspondence_exact` **0.305**, 0 errors. Dominant miss: function
  collapses to `email` (demand 0/25, memo 4/25, letter 5/25); negatives
  collapse to `neutral` (3/28). Memo
  `docs/memos/sorter_docclass_correspondence_v0.md`.
- **Correspondence sorter GEPA v1 (KANBAN-103).** Prompt
  `sorter_docclass_correspondence_v1` is a `.replace()` of v0 adding rule 45
  (Enron channel trap): SMTP headers are transport, never evidence for
  subclass `email`; ordered payload cascade attorney_demand → demand →
  meeting_request → press_release → notice → memo → letter → email;
  `other` banned on this surface. Same-surface A/B reserved as
  `qwen3.7-flash_sorter_docclass_correspondence_v1_enron200_s42` on
  `data/manifests/enron_corr200_s42_filenames.jsonl`. Runner publishes the
  selected prompt into the Braintrust project library by default
  (`--no-publish-prompt` to skip). **Same-surface A/B 2026-08-30**
  (Mailroom-Sandbox, 200/200, 0 errors): subclass **0.400 → 0.465**
  (+6.5pp; paired bootstrap CI +1.5 to +12.0pp); letter 0.20→0.44,
  press_release 0.28→0.48, meeting_request 0.68→0.80; `demand` /
  `attorney_demand` still 0/28; sentiment flat 0.630→0.625.
  Memo `docs/memos/sorter_docclass_correspondence_v1.md`.
- **Correspondence sorter GEPA v2 (KANBAN-103).** Prompt
  `sorter_docclass_correspondence_v2` is a `.replace()` of v1 adding rule 46
  (Hub demand markers): demand is a legal-phrase hit on the writer's own
  text (`DEMAND LETTER`, `FINAL NOTICE`, `BREACH OF CONTRACT`, …), not a
  formal letter addressed to the recipient; `attorney_demand` adds a
  law-firm sender. Cascade re-ordered to the GT labeler
  (meeting → press → demand → notice → memo → letter → email). Braintrust
  live scorers reduced to `sorter_doc_type` + `sorter_subclass`; sentiment /
  exact / confidence remain post-hoc. Reserved run
  `qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42`.
  **Same-surface A/B 2026-08-30** (Mailroom-Sandbox, 200/200, 0 errors):
  subclass **0.465 → 0.485** (+2.0pp; paired CI −1.5 to +6.0pp includes 0 —
  accepted into the GEPA pool, not a claimed win). Demand **0/25 → 3/25**,
  attorney_demand **0/3 → 1/3**; press_release 0.48→0.56. Memo
  `docs/memos/sorter_docclass_correspondence_v2.md`.
- **Correspondence sample takes every attorney_demand example (KANBAN-103).**
  The Hub dedup dump has 3 `attorney_demand` rows (all already in the seed-42
  200-row draw). The full CMU corpus has **4** — the leftover is
  `sanders-r/ecogas/26.` (Milbank / Ecogas demand letter; exact-body twin of
  `sanders-r/all_documents/126.`, dropped by first-occurrence dedup). Runner
  gains `--include-all-attorney-demand` (append leftover Hub attorney_demand
  after the draw) and `--extra-dumps` (merge recovered full-corpus rows).
  Fixture `tests/fixtures/enron_attorney_demand_extras.jsonl` holds the
  recovered 4th row (same Hub enrichment as its twin). Reserved expanded
  surface
  `qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42_attyall`
  (n=201 = pinned 200 + ecogas/26.). **Run 2026-08-30** (Mailroom-Sandbox,
  201/201, 0 errors, frozen v2): `doc_type_accuracy` **1.000**,
  `subclass_accuracy` **0.5124**, attorney_demand **1/4** (new row →
  `email`, same miss as its twin). Not a same-surface A/B vs the 200-row
  CIs. Memo `docs/memos/sorter_docclass_correspondence_v2_attyall.md`.
- **Phoenix span-export guard (KANBAN-103).** `src/phoenix_tracing.py`
  now calls `load_env()` before reading `PHOENIX_TRACING` (the v0
  correspondence run imported the tracer before dotenv and default-on
  OTLP-spammed a down `localhost:6006` — 86 `Failed to export span batch`
  lines) and skips the BatchSpanProcessor when the Phoenix HTTP server
  does not answer. Correspondence runner `--gt-overrides` applies
  filename-keyed Hub GT patches; sample corrections live in
  `data/gt/enron_correspondence_label_overrides.jsonl` (25 Hub `demand`
  rows + 2 hypothetical `attorney_demand` twins demoted — phrase-lexicon
  false positives). Publisher
  `scripts/datasets/publish_enron_gt_overrides.py` patches Hub
  `ground_truth/{train,test}.jsonl` and uploads a sidecar
  `ground_truth/overrides.jsonl`.
- **Correspondence sorter GEPA v3 (KANBAN-103).** Prompt
  `sorter_docclass_correspondence_v3` is a `.replace()` of frozen v2 adding
  rule 47 (demand is the speech act): this message itself demands that the
  recipient pay / cure / cease / arbitrate. Overrides the v2 Hub phrase
  lexicon (rule 46) — a mention, draft-request (`please draft a demand
  letter` / `we could send a demand letter`), news clip, IT-outage
  `FINAL NOTICE`, or cover note attaching a demand is NOT demand.
  `attorney_demand` = that speech act AND a lawyer/law-firm is the
  author/sender, not merely mentioned. Motivated by v2 demand **3/25** and
  attorney_demand **1/3** plus the Hub false positives already demoted in
  `data/gt/enron_correspondence_label_overrides.jsonl`. Same-surface A/B
  reserved as `qwen3.7-flash_sorter_docclass_correspondence_v3_enron200_s42`
  on pinned `enron_corr200_s42_filenames.jsonl` + `--gt-overrides`.
  **A/B 2026-08-30** (Mailroom-Sandbox, 200/200, 0 errors) vs **rescored
  frozen-v2 on the corrected GT** (not old-Hub 0.485): subclass
  **0.535 → 0.560** (+2.5pp; paired CI −2.0 to +7.0pp includes 0 —
  pool-accept, not a claimed win). Intended class **regressed**: demand
  **1/1 → 0/1**, attorney_demand **1/2 → 0/2**; v3 predicted zero
  `demand` / `attorney_demand`. Email 0.614→0.671 (two false v2 `demand`
  preds demoted). 8/14 recoveries are `other`→correct (parse-burn noise
  at `max_tokens` 2048). v2 remains the demand-arm parent. Memo
  `docs/memos/sorter_docclass_correspondence_v3.md`.

## [v0.21.0] - 2026-08-28

> Docclass bolster + stratified-120 A/B + dojo-scoring @v0.10.0

### Changed
- **Pin `llm-dojo-scoring` `@v0.10.0`.** `pyproject.toml` + `requirements.txt` +
  the dependency-manifest pin move from `@v0.7.0` to the tagged
  [v0.10.0](https://github.com/Exios66/llm-dojo-scoring/releases/tag/v0.10.0)
  release (field-micro P/R/F1/F2, docclass macro-PRF, insurance
  `determination_consistency`). Docs (`README`, `AGENTS.md`, `SCORING.md`,
  `docs/sister-repos.md`, wiki Scoring) cite the new pin.
### Added
- **Stratified-120 docclass A/B (KANBAN-101):** `scripts/datasets/export_hf_docclass_merged.py`
  exports HF `Lucius-Morningstar/docclass-merged` v5 (1,210 rows) to
  `docclass_merged_v5.jsonl`; `run_langfuse_docclass_eval.py` gains
  `--filename-manifest` / `--export-sample-manifest`; NEW
  `run_langfuse_docclass_specialist_eval.py` runs contracts + insurance docclass
  specialists on the pinned manifest. Same-surface A/B (seed 42, fp
  `05f05e9f…` sorter / `34083b16…` contracts / `b238c80e…` insurance):
  sorter v6→v7 exact **0.5833→0.6833** (+10.0pp), subclass **0.5917→0.6917**,
  doc_type **0.9917** flat; contracts v0→v1 overall **0.6884→0.8444** (+15.6pp,
  n=24 CUAD-scored / 48 routed); insurance v0→v1 overall **0.6957→0.6904**
  (n=24, flat within noise).
- **Docclass agent bolster (KANBAN-101):** `src/prompts_docclass.py` grows from
  32 → 54 registered keys — v1 bolstered variants for all 7 specialists
  (contracts derives from `contracts_specialist_v39` + CUAD/MAUD hub rules),
  reviewer/arbiter/boss/judge trio (label-consistency on correctness judge),
  plus seven missing `*_specialist_docclass_pilot_v0` keys; `sorter_docclass_v7`
  (v6 + rules 37–43 + correspondence/insurance subclass output contract) and
  `sorter_docclass_vision_v1` (insurance_claim + v7 rules on the vision
  skeleton) land in `src/prompts.py`. Registration remains the Langfuse deployment
  seam; runner default is now `sorter_docclass_v7` on `docclass_merged.jsonl`.
- **Docclass scoring parity (KANBAN-101):** `classify_failure` treats
  `subclass_ok is None` as pass (no spurious `subclass_miss`);
  `src/score_emitter.py` adds `emit_docclass_run_scores` + headline metric
  names; `run_langfuse_docclass_eval.py` wires the emitter; `docs/SCORING.md`
  §7 documents the 1,210-row / 8-class surface; `tests/test_docclass_parity_audit.py`
  machine-checks prompt/schema/metric alignment; `config/taxonomy.yaml` promotes
  `insurance_claim` + correspondence/insurance subclasses; agent bench defaults
  move to `*_docclass_v1`.
- **Durability program (full-roster agent evaluation):** hand-labeled GT sets
  for contract (34)/corporate_record (11)/correspondence (27) validated by
  scripts/gt_workbench.py (type conformance + verbatim grounding); insurance
  real-GT assembled from docclass-merged ground_truth with date_filed artifact
  stripping and a suspect-quarantine lane. scripts/gen_edge_cases.py emits the
  durability matrix (8 deterministic transforms; per-doc rotation; reviewed-
  synthetic queue). agents/pipeline_agents.py adds runnable Reviewer/Boss/
  Arbiter/Reporter/PdfTranscriber wrappers; InsuranceClaimsSpecialist +
  schema land in specialist_agents.py with the vendored base prompt
  (insurance_claims_specialist_v0). scripts/run_agent_bench.py scores edge
  expectations, judge planted-defect precision/recall, and arbiter/boss
  conflict resolution. scripts/prompt_engineer.py is spec-driven
  (config/prompt_engineer/agents.yaml) and reads judge-mutation manifests.
  Baseline findings: contracts_specialist is vulnerable to instruction-
  overlay injection; judge_correctness pilot v1 reaches recall 1.00 /
  FPR 0.00 on verified GT after its label-consistency repair (v1) and HF
  date_filed artifact stripping.
- **Per-role eval tasks for the docclass roster — agent bench suite landed house-grade + silent no-op mutation repaired (KANBAN-097, [#51](https://github.com/Exios66/llm-entity-extraction/issues/51), human directive 2026-08-24):** every classification-chain role now has a deterministic, machine-scored eval surface — no LLM-as-judge anywhere. NEW/landed tooling: `scripts/run_agent_bench.py` gains **blind-classification edge mode for the sorter/reviewer roles** (exact doc_type match over the shared adversarial suite, per-transform breakdown as the mutation signal), a `--dry-run` plan gate on all three money-spending modes, testable `main_with_args`, SERVED-model recording (JudgeAgent silently swaps the BaseAgent default for the taxonomy judge.model — records now name what actually ran), version-suffixed manifests (prompt-version in the filename so A/B arms never clobber each other), and ONE compact append-only record per completed run in the canonical `reports/experiment_log.jsonl` (`task: agent_bench`); `scripts/gen_edge_cases.py` builds deterministic transform suites with machine-checkable expectations and CANONICAL taxonomy GT labels (`contract`, not `contracts`) round-robin-stratified across classes; `scripts/gt_workbench.py` validates hand-GT against specialist schemas incl. verbatim-grounding spot-checks; `agents/pipeline_agents.py` wraps reviewer/boss/arbiter/reporter/transcriber prompts in runnable agents; the vendored `insurance_claims_specialist_v0` prompt + `InsuranceClaimsSpecialist` complete the 7-specialist roster upstream. **RESULTS (qwen3.7-flash pilots, seed 42):** judge-mutation v0 recall 1.00 / clean-FPR 0.88 vs repaired `judge_correctness_docclass_pilot_v1` recall 0.60 / **FPR 0.00** on the matched n=48 arm — Pareto trade; v1 is the FPR-dominant choice for pipeline gating, v0 stays max-recall audit. Conflicts: boss 10/10, arbiter 7/10 on planted-defect rivals. Reviewer blind classification **20/20 = 1.000** across all 8 transform families (after fixing the GT-label artifact that had scored it 0/20). **DEFECT REPAIR:** `judge_correctness_docclass_pilot_v1` had shipped byte-identical to v0 (broken `.replace()` anchor); re-derived off the REAL marker with the lesson verbatim. **MUTATION 1:** `insurance_claims_specialist_v1` = v0 + EVIDENCE-ONLY VISIBILITY (single-anchor derivation, guard-pinned) — baseline no_fabrication 0/20 with 30 true fabrications (template fills `CLM-SAMPLE-001`, composed narratives); v1 eliminates the template/prior-fill class entirely and lifts all_optional_null to 3/3; residue (damages_description visible-token compositions + claim_type partial-view guesses) queued as KANBAN-098. Guard suite `tests/test_kanban097_agent_benches.py` (12 network-free).
- **README Layout gains the tracked `data/gt/` bench corpus (human directive 2026-08-24, no-card edit):** one-line repo-map update — the `data/` entry now lists tracked `data/gt/` (KANBAN-097 agent-bench ground truth: `edge_suites/`, per-doc packets, insurance-claim GT) alongside the gitignored run artifacts and `data/eda/`, reflecting what `9483437` actually landed.
- **Root README collapsible-headings declutter (human directive 2026-08-24, no-card edit):** surgical reorganization of the 804-line front door with `<details>` folds in the KANBAN-093 (The-Mailroom) pattern — nine collapsibles for the reference bulk (scoring internals, repo map, scripts inventory, dataset-sync gallery, command gallery, runner table, prompt-version families, env-var table, Langfuse mirror details) while the visible page keeps the orientation path (intro, sorter jobs, agent table, scoring intro, setup quickstart, credits, navigation). ZERO operational content removed — verified by a line-level parity check against git HEAD (all 700 non-empty HEAD lines present; only additions are fold scaffolding) plus fence-safety and tag-balance checks. Factual fix in passing: "The sorter's two jobs" → "three jobs" (the list always had three). Setup now links the new `docs/configuration.md` provider/sink guide from its env-var section.
- **Environment configuration guide + condensed `.env.example` (human directive 2026-08-24, no-card edit):** NEW `docs/configuration.md` — the full how-to for configuring both governed pipelines per provider (OpenRouter default / research-funding key / Modal-vLLM / Ollama / generic OpenAI-compatible, incl. five copy-paste flip recipes and the one-deployment-backs-both-repos contract) and per trace sink (Phoenix local-first default / Langfuse primary-when-configured / Braintrust read-only-by-design / LangSmith mirror / none), plus load-order semantics (`load_env()` + call-time seam resolution) and a zero-cost fully-local stack recipe. `config/environments/.env.example` reorganized into labeled sections with every LIVE knob preserved; dead decoration evicted after code-census verification (`DEFAULT_PROVIDER`, `OLLAMA_BASE_URL`, `GENERIC_*`, `OBSERVABILITY_PROVIDER` had no consumer in this repo — mailroom-only concepts that drifted in); all guard pins kept green (`test_env_utils.py` Phoenix pins + KANBAN-096 flip-documentation test, **36 passed**). `docs/README.md` layout table gains the new doc.
- **Pilot-universe docclass variants + Prompt Engineer:** `sorter_docclass_pilot_v0..v3`
  and role `_pilot_v0` variants aligned to the docclass-merged GT (5-class
  primary list; NEW doc_subclass dimensions for correspondence and
  insurance_claim; Medicare/payer mapping; function-over-transport rule;
  ancillary-wrapper convention). `agents/sorter_agent.py`: insurance_claim
  class, both subclass dimensions registered, DOCCLASS_PILOT_SCHEMA,
  PILOT_CLASS_KEYS; docclass runner gained `--class-set pilot` and
  canonicalized two-sided subclass scoring (contract subtype rows now score).
- **scripts/prompt_engineer.py**: manifest-driven LLM mutation proposals with
  mechanical validation gates and one-command apply (produced pilot_v2/v3).
- **Modal-hosted vLLM serving capability + call-time provider-seam repair (KANBAN-096, [#50](https://github.com/Exios66/llm-entity-extraction/issues/50), human directive 2026-08-24):** `deploy/modal_vllm.py` deploys any HF-hosted model behind a bearer-authenticated OpenAI-compatible `/v1` endpoint on Modal GPU infrastructure — the entity-side sibling of llm-mailroom's KANBAN-064 app (SAME environment-knob contract `MODAL_VLLM_MODEL/GPU/QUANTIZATION/MAX_MODEL_LEN/API_TOKEN` + `HF_TOKEN`, separate Modal app name + persistent `entity-hf-cache` volume, so one workspace hosts independent deployments per pipeline or a single deployment backs BOTH repos via mailroom's own `VLLM_BASE_URL` seam). A configuration CAPABILITY, not a serving-path change: every eval runner keeps using OpenRouter unless `OPENROUTER_BASE_URL` is pointed at the deployment. Landing it exposed and fixed a REAL seam defect: `OPENROUTER_BASE_URL` was bound at module-import time in `src/openrouter_utils.py`, so dotenv-set values (loaded lazily by `env_utils.load_env()` immediately before client construction) never took effect — only true shell exports worked, silently breaking the entire dotenv-driven flip story. New resolvers `resolve_openrouter_base_url()` / `resolve_openrouter_api_url()` read env AT CLIENT-BUILD TIME; all three consumers converted (`agents/base_agent.py::llm()`, `src/llm_chain.py::build_chat_model()`, `src/classifier.py::classify_image()`); frozen import-time aliases retained for backward compatibility. New `[deploy]` extra + `requirements/deploy.txt` wired through the KANBAN-081 manifest law (`modal>=0.73`, deploy-time only — runtime tree stays clean); `config/environments/.env.example` gains the flip-the-switch block including the cross-repo contract; `scripts/smoke_vllm_endpoint.py` health-checks `/v1/models` + a real completion (exit-code semantics for CI); `deploy/README.md` documents deploy/flip/smoke/teardown plus cost shape (scale-to-zero after 15 idle minutes). Guard suite `tests/test_kanban096_modal_vllm.py` (21 network-free): stubbed-modal command assembly + quantization injection, bearer-enforcement mapping onto vLLM's native `VLLM_API_KEY`, distinct sibling identity, THE dotenv-regression pin, client-forwarding pins for base_agent (constructor-kwarg capture — no LangChain private-field coupling) and classifier, KANBAN-081 parity for the new extra, a runtime-tree census proving no runtime module imports `modal`, and a cross-repo knob-contract check against the mailroom sibling clone (skips honestly when absent).
### Changed
- **Single-source-of-truth repair: contracteval side-log merged into the canonical experiment record; derived tree made self-healing; the two chronic Posit-site failures fixed at root (KANBAN-094):** diagnosis of the long-failing `test_rendered_pages_committed` / `test_quarto_render_is_deterministic_and_clean` pair traced BOTH to one 2026-08-18 incident: 9 contracteval runs logged rows to an untracked side file (`reports/experiment_log_contracteval.jsonl`) while their per-run SPA files landed in `docs/data/runs/` — splitting the record (195 canonical rows vs 203 run files) and breaking the `experiment_log.jsonl ⇒ build_site.py ⇒ docs/data/runs/{n:03d}.json` derivation chain; one more side row (`contracteval_v5`) never produced a run file at all (run aborted on key-limit exhaustion). Fix: all 9 side rows verified (schema-clean, hazard-free, no overlap, chronological) and merged into the append-only canonical JSONL through the KANBAN-088 sanitizer → **204 rows**, side log deleted after absorption proof; `reports/experiment_log.md`, site data, pre-render includes, and rendered Posit pages ALL regenerated from the single source (204 run files, 204 deep links). `build_site.py` now prunes orphaned run files so the derived tree is always exactly `{001..N}` and its `--check` mode detects orphaned files (index length alone missed the incident); the quarto pre-render hook re-execs into the repo venv when driven by an interpreter without `llm_dojo_scoring` (quarto invokes bare `python3`), fixing the mid-render ModuleNotFoundError. New pins `tests/test_kanban094_single_source_truth.py` (5 network-free): no side logs may exist, run-tree is exactly `{001..N}`, `--check` rejects orphan files, hook survives system-python3 invocation, merged tail present/hazard-free/ordered.
- **Family-wide JSONL line-boundary hazard sweep — every remaining `ensure_ascii=False` writer classified, adopted, or explicitly exempted (KANBAN-088, [#44](https://github.com/Exios66/llm-entity-extraction/issues/44), the KANBAN-087 carve-out):** full census of the repo found **15 sites / 11 files**. NEW shared safety module `scripts/datasets/_jsonl_safety.py` now holds the canonical `sanitize_line_boundary_chars` + hazards map (extracted VERBATIM from the exporter) plus a one-call `safe_jsonl_line(obj, **dumps_kwargs)`; the KANBAN-087 exporter delegates to it with object-identical re-exports (its own 6 pins still pass unchanged). **9 row-writer sites across 7 files adopted** `safe_jsonl_line`: backfill_extraction_kpis (experiment-log rewrite), build_docclass_merged (merged-row writer), build_legalbench_full_pack (enriched + index writers), publish_enron_correspondence(+dedup) (publish writers), stream_legalbench_tasks_to_bt (BT staging + classes-manifest writers), build_docclass_v5 (`write_jsonl`). **5 sites exempted with inline justification markers**: three field-value dumps in build_docclass_* (nested JSON guarded downstream by the sanitizing row writer), two CSV-cell flattens in merged/pilot builders, and src/braintrust_utils record-id hash input (byte-stability beats split-safety; never persisted as rows). Guard suite `tests/test_kanban088_jsonl_safety_sweep.py` (5 network-free pins): lossless escape/round-trip, exporter re-export identity, per-file adoption, a repo-wide **no-unmarked-hazard-sites** scan (any future bare `ensure_ascii=False` fails CI until marked or adopted), and exemption-justification presence. Prevention over incident response: the U+2028 Hub-shredding failure mode is now structurally impossible for family writers.
- **Clause-category registry reconciled against the CUAD primary source — "verbatim" texts were paraphrases (KANBAN-072, [#25](https://github.com/Exios66/llm-entity-extraction/issues/25), foundation step):** `config/clause_categories.yaml` (49 categories: 41 CUAD + 8 MAUD) claimed verbatim Atticus Project question texts, but a character-level reconciliation against the canonical [`category_descriptions.csv`](https://github.com/The-Atticus-Project/cuad/blob/main/category_descriptions.csv) (fetched 2026-08-24, sha256 `7499950e…`, now vendored at `tests/fixtures/cuad_category_descriptions.csv` with license header) found **~30 of 41 CUAD texts deviated substantively** — including the texts quoted in issue #25 itself — while carrying the verbatim label; the smoking gun: `volume_restriction`'s old text actually described *price-increase consent* (a different category). All 41 CUAD `verbatim_question` fields are now CHARACTER-EXACT vs the primary source (normalized-diff proof: 0 mismatches); `answer_type` re-derived from the canonical per-category Answer Format column (9 non-Yes/No formats — the datasheet prose rounds to 8; `warranty_duration` flips to general_info, `outside_date` stays general_info as MAUD-side); the 8 MAUD deal points keep their #25-sourced text under an honest `[MAUD-SIDE … NOT yet reconciled]` tag. Added the issue's three `agent_inquiry_templates` (`change_of_control`→CUAD, `mae_clause_scope`→MAUD, `contract_amendment_restrictions`→CUAD/MAUD) verbatim. NEW `tests/test_kanban072_clause_registry.py` (5 network-free guards): registry shape 41+8, char-exactness vs the vendored oracle, answer-type↔format agreement, template presence/targets, and a mislabel-regression pin on the volume_restriction smoking gun. Zero code consumes this file today (pre-wiring groundwork for the specialist integration) — config-only change; suite holds baseline.
- **The-Mailroom visualizer mapped into the governed umbrella (KANBAN-091, [#47](https://github.com/Exios66/llm-entity-extraction/issues/47)):** [The-Mailroom](https://github.com/Exios66/The-Mailroom) (v0.2.0) — the sister pipeline's pixel-art visual engine, rendering every llm-mailroom run as an animated document conveyor driven solely by Langfuse traces — was absent from every umbrella surface despite being a fully governed family member (own AGENTS.md whose #1 maintenance duty is mirroring llm-mailroom's routing/taxonomy trace contract, own semver release train, own wiki). This repo: `docs/sister-repos.md` constellation diagram gains a `visualizer:` line and the At-a-glance table a "Downstream of the sister repo" row (reads traces, mirrors schema via `pipeline_schema.py`/`trace_interpreter.py`, dependency of no family repo); root README working-surfaces prose now lists it alongside the graph sites and wiki. Sister-side mirror edits landed in llm-mailroom (sister-repos map section + diagram node, README Umbrella row, wiki Home) under the same card — one card, one issue, both changelogs per the KANBAN-061 precedent. Docs-only; zero behavior change.
- **Cold-suite interpreter pin — posit pre-render subprocess spawned bare `python3` (KANBAN-086):** both spawn sites in `tests/test_posit_site.py` (the `_write_include` hook runner and the quarto-determinism test) invoked `_pre-render.py` via a bare `"python3"` argv, so any suite run without the repo venv on PATH died inside the subprocess with `ModuleNotFoundError: llm_dojo_scoring` → **5 phantom failures** in `test_posit_site.py` that masqueraded as content regressions (they rode along in KANBAN-080's documented baseline and KANBAN-081 recorded them as "7 chronic posit renders"). Both sites now use `sys.executable`, inheriting pytest's own interpreter — cold runs against any properly-installed venv just work. A/B proof in an identical stripped-PATH cold environment (`PATH=/usr/bin:/bin:/usr/sbin:/usr/local/bin`, PYTHONPATH scrubbed): unpatched **7 failed / 2 passed** → patched **7 passed / 2 failed**, the residual pair being the documented derived-site chronic class (`test_rendered_pages_committed`, `test_quarto_render_is_deterministic_and_clean`) which is unrelated to interpreter resolution. Test-only; zero behavior change for venv-on-PATH runs.
- **Root folder consolidation — content/governance dirs nested (KANBAN-083, issue #41, human directive 2026-08-23):** root visible directories reduced **13 → 10** by nesting the agent-plumbing dirs that confused newcomers, every live reference updated in lockstep from a full census (pathlib segment joins included — slashless `ROOT / "board"` literals are invisible to naive greps). Moves: `board/` + `discussion/` → **`governance/`** (MESSAGE_BOARD.md/.qmd + MESSAGE_BOARD_DISCUSSION.qmd — one umbrella for inter-agent state); `wiki/` → **`docs/wiki/`** (documentation under documentation — now matching llm-mailroom's existing convention); `site/` → **`docs/posit-src/`** (portal SOURCES beside their rendered `docs/posit/`, ending the two-sites ambiguity with `scripts/site/`). Deliberately NOT moved (idiomatic ML-repo citizens, 25–49 live code references each / import-level coupling): `reports/`, `data/`, `agents/ src/ config/ tests/ scripts/ requirements/`. Lockstep updates: `_quarto.yml` output-dir deepened to `../../docs/posit`; `_pre-render.py` ROOT depth + both governance reads; `build_site.py`; `render_message_board_qmd.py`; `test_posit_site.py` (SITE_DIR, div-balance read, git pathspec, and the `output-dir == "../../docs/posit"` contract re-pin); README layout block rewritten (+ stale root-`memos/` row from KANBAN-080 finally removed); `docs/README.md` posit section; wiki mirror pages (Site/Architecture/FAQ/Release-Process); `.gitignore` derived-output rules re-pathed. Portal render PROVEN from its new home (`quarto render docs/posit-src` → `docs/posit/` regenerated & committed); GitHub wiki synced via the script's new path `docs/wiki/sync-wiki.sh`. AGENTS.md path-doctrine rows (9 lines naming the old dirs) were PARKED through the ship, then APPROVED by Jack in-band later the same day and landed post-consent. Baseline discipline: pristine-HEAD worktree baseline 617 passed / 9 failed captured BEFORE judging deltas; in-tree verification after commit.
- **Modular dependency batches — evidence-derived install profiles (KANBAN-081, issue #39, human directive 2026-08-23):** dependencies split into purpose-scoped installable batches so users tailor their footprint instead of installing everything. Whole-repo AST import census drove every boundary: CORE (`pyproject.toml` `dependencies` + root `requirements.txt`, now identical sets) is exactly the agent → prompt → scoring chain's 8 needs (langchain-core, langchain-openai, openai, requests, python-dotenv, PyYAML, structlog, llm-dojo-scoring @v0.7.0) — the surface llm-mailroom imports. New extras mirroring new `requirements/<batch>.txt` files (7): `[tracing]` (arize-phoenix + opentelemetry-sdk + otlp exporter + langfuse), `[evals]` (braintrust), `[datasets]` (huggingface_hub + Pillow + pdf2image), `[reporting]` (numpy + matplotlib + openpyxl), `[embeddings]` (sentence-transformers, unchanged), `[dev]` (+tracing for the module tests), `[all]` (everything non-dev), plus a legacy `[pdf]` alias → `[datasets]`. Three manifest defects fixed in the same pass: (1) the tracing stack was MISSING from pyproject.toml entirely — a bare `pip install -e .` could not import the repo's own default tracing sink `src/tracing.py`; (2) `openpyxl` and `huggingface_hub` were imported by deck exporters/publishers but declared NOWHERE (worked only via transitive luck); (3) dead pins `pandas>=2.0.0`/`pyarrow>=15.0.0` removed — zero imports across all active code (no notebooks exist). NEW `tests/test_dependency_manifests.py` (6 network-free pins): core floor frozen exact-set, extras↔batch-file parity per package+floor, `[all]` completeness, dead-pins-stay-dead/undeclared-stay-declared guards, and a live AST census re-deriving the third-party import surface of shipped `agents/`+`src/` against a module→batch owner map (batch modules may use core ∪ their batch, nothing else). Proof before push: fresh-venv (python3.13, pip 26.1.2) core-only install from a clean tree copy → `src.prompts` (103 prompt versions) + `agents.sorter_agent` import GREEN with phoenix/langfuse/opentelemetry/braintrust/huggingface-hub/sentence-transformers VERIFIABLY ABSENT; `-e ".[tracing]"` add-on → `src.tracing` imports and initializes the live Phoenix tracer. Honest residues: `matplotlib`+`openpyxl` still arrive in core installs transitively because llm-dojo-scoring v0.7.0 itself declares them in its `install_requires` (upstream dojo slim-down owed, not fixable consumer-side); AGENTS.md quickstart dependency lines (3) APPROVED by Jack in-band later the same day and landed as an explicit-path follow-up commit; wiki `Getting-Started.md` updated in-repo and synced to the live wiki same day. Suite delta vs pristine-HEAD worktree baseline: 611→627 passed (+16 = 6 new pins + 9 data-gated HF-mirror tests that skip without untracked dumps + 1 worktree-artifact fail), FAILED set byte-identical (7 chronic posit renders + kanban076 hub-sha check).
- **Release infrastructure repaired — tags and GitHub releases now match the documented convention 1:1:** (1) the dangling `[v0.11.0]` link is resolved — the annotated tag was never cut when its section shipped, so `v0.11.0` was created retroactively at `f838e71` (the exact commit that landed the section, correctly before v0.12.0's tag) with a full backfilled release; (2) five tags that had been created lightweight against Release-Process.md's annotated rule (`v0.10.0`, `v0.12.0`, `v0.13.0`, `v0.19.1`, `v0.20.0`) were re-forged as annotated AT THE SAME COMMITS (zero history change; refs force-pushed individually); (3) the fourteen versions v0.1.0–v0.10.0/v0.12.0–v0.14.0 had NO GitHub releases at all — each now has one built from the version's own CHANGELOG section as it existed AT the tag, plus the full commit range (capped list), a CHANGELOG.md@tag link, and a compare/diff link; (4) the seven existing releases were standardized in place: curated prose preserved, same commits/references footer appended, titles normalized to `vX.Y.Z — <summary>`; Latest badge pinned back to `v0.20.0` after the tag swaps briefly drafted it. Header/link-ref normalization that made this possible is in the previous entry. Repo-metadata only; no code, prompts, or dependency changes.
- **v0.20.0 fresh-install archive proof re-run GREEN on the pushed tag** (KANBAN-080 wrap-up of the interrupted release train): clean-venv `pip install .` from `git archive v0.20.0` now resolves fully from default PyPI — `langchain-core` 1.6.0 is live (the earlier "unresolvable floor" finding was a stale index view, forensics 2026-08-23) — and the real-surface smoke import passes (`src.prompts`, 103 registered prompt versions). No pin change needed; tag and GH release stand as shipped.
- **Root de-clutter / file nesting with every live reference updated in lockstep (KANBAN-080, issue #38):** `SCORING.md` → `docs/SCORING.md`; orphaned legacy deploy script `deploy_phoenix.sh` → `scripts/deploy/deploy_phoenix.sh` (zero code references); the split-brain memo homes merged — root `memos/*.md` (12 newer v34–v39 design memos) moved into `docs/memos/` (35 total), fixing the site's memos tab, which had been silently serving only the old set (`build_site.py::build_memos` already read `docs/memos/` while its docstring claimed the root); tracked backup cruft removed from git (`src/prompts.py.bak`, `src/prompts_original.py`; history preserves them); legacy root convenience symlinks (`MESSAGE_BOARD.md`, `MESSAGE_BOARD.qmd`, `MESSAGE_BOARD_DISCUSSION.qmd`) deleted — every programmatic reader already used the canonical `board/` + `discussion/` paths. Live references updated across `README.md` (including two stale Layout-tree pointers: a phantom root `V16_PROPOSITION.md` and the dead `memos/README.md` link), `docs/README.md`, `docs/slides/*`, wiki pages, `scripts/site/build_site.py` (`scoring_md` URL + docstring + mirror comment), eval-runner help strings, and both deck exporters; frozen history (CHANGELOG sections, board rows, `reports/`) deliberately untouched by append-only policy. Immovable-at-root documented in the card row (pyproject.toml, requirements.txt, CHANGELOG.md, README.md, AGENTS.md, dotfiles). AGENTS.md path-doctrine updates (5 lines: file-map row, scoring-reference pointer, update-checklist cite, noise-floor memo cite, Research-memos section header) approved same-day by the human operator and landed in the follow-up governance commit. Derived artifacts regenerated: `docs/data/meta.json` scoring_md → `docs/SCORING.md`, `memos.json` 22 → 34 memos, benchmarks refreshed live (1,438 rows); `docs/posit/` re-rendered. Targeted suite (test_posit_site + test_graphify_skill): 12 passed, failures byte-identical to the documented chronic pair (derived-site classes).
### Added
- **Scoring-process notebooks launched — exemplar `03_doc_type_bundles` shipped (KANBAN-068, [#33](https://github.com/Exios66/llm-entity-extraction/issues/33), first deliverable of the six-notebook set):** NEW `notebooks/03_doc_type_bundles.ipynb` walks the v0.7.0 headline scoring process end-to-end offline: every bundle in `DOC_TYPE_BUNDLES` (metrics + validation per doc type), the `get_doc_bundle` honesty resolver with its explicit `used_fallback` flag, and — the payoff — a closing honest-gap table derived from THIS repo's real append-only log (`reports/experiment_log.jsonl`, 195 records / 19,642 scored document rows): contract ×16,783, correspondence ×407, merger_agreement ×335, corporate_record ×69, compliance_filing ×44 and due_diligence ×4 have REAL benchmark rows, while `court_opinion` and `insurance_claim` are shown as genuinely declared-pending. Thin-notebook pattern per the KANBAN-078 precedent: kernel-cwd-proof bootstrap (`find_repo_root()` walks up for `pyproject.toml`+`reports/`, runs from anywhere incl. hostile cwd), stdlib-only cells against the pinned `llm-dojo-scoring @v0.7.0`, zero network/LLM calls. Guard suite `tests/test_kanban068_bundles_notebook.py` (4 network-free tests): notebook validity, code-cell network/LLM-free scan, cwd-proof bootstrap pin, and full headless execution via nbclient FROM `notebooks/` asserting the honest-gap summary matches reality (contract REAL, court_opinion + insurance_claim pending). Install path: new `[notebooks]` extra = `requirements/notebooks.txt` 1:1 (nbformat/nbclient/ipykernel, floors = versions verified on python3.13), registered into `[all]`/`all.txt` and the KANBAN-081 manifest-parity guards (extras↔batch-file parity + all-batch tuples). `notebooks/README.md` scopes all six process notebooks with conventions; remaining five (classification, typed-field extraction, audit/verification, chained pipelines, report/aggregation) follow the same pattern.
- **Dedicated docclass prompts for every classification-chain role (KANBAN-090, issue #46, human directive via Discord #hermes 2026-08-23):** the docclass arm (KANBAN-033 lineage -> docclass-merged schema v5 + docclass-pilot) had specialized prompts ONLY at the sorter (`sorter_docclass_v0..v6` + `_vision_v0`) — every downstream role ran its GENERIC prompt inside docclass-context evals. NEW `src/prompts_docclass.py` ships a **21-key `DOCCLASS_PROMPT_VERSIONS`**: the 8 sorter-docclass keys RE-EXPORTED byte-identical (same objects, never redefined — this module is the docclass arm's single import surface), **10 derived variants** built by single-anchor `.replace()` off the REAL base constants (contracts / corporate_records / due_diligence / correspondence / compliance / court_opinions specialists + boss + the judge trio completeness/classification/correctness), and **3 authored-fresh V0s** for roles this repo has no base constant for (reviewer, arbiter, insurance_claims specialist — provenance-commented as modeled on llm-mailroom counterparts). Every variant prepends a shared **DOCCLASS ARM CONTEXT** block (the extended 8-class primary set incl. `insurance_claim` + `merger_agreement`, second-level doc_subclass dimensions: CUAD-style contract subtypes, merger consideration types, title-derived corporate record types) plus role-specific rules — routing label is pipeline STATE not ground truth, claim-documentation and M&A leakage read-through, judge trio gains subclass-specific support requirements and cross-family leakage checks, classification judge grades against the extended set with family discriminators, boss routes classification-fault conflicts to human review. Derivation discipline mirrors the version-lineage convention: anchors are single-count-asserted so a future base edit that adds a JSON closer fails loudly instead of silently duplicating blocks. **Registration IS deployment** per repo doctrine: the registry is merged into `PROMPT_VERSIONS` at the prompts.py tail (prompts_archive tail-import precedent), taking registered versions **103 -> 116** (the 8 sorter keys pre-dated the card; `update()` was a no-op on those, zero collisions asserted at import), so `scripts/eval/sync_langfuse_prompts.py` mirrors every key to Langfuse exactly like every other family. Runtime untouched: nothing fetches a docclass key by default — eval runners and pipeline configs opt in explicitly by key. Guarded by 6 network-free tests in `tests/test_kanban090_docclass_prompts.py` (full-registry resolvability through `get_prompt()`, re-export identity checks, `[:300]` head-prefix + tail-drift derivation pins, base-anchor single-closer guards, authored-V0 provenance comments verified in module source, negative proofs that generic routes carry no docclass text). Suite delta vs pre-change baseline: targeted prompt suites fully green (70 passed = 64 existing + 6 new); full-suite failures byte-identical to the documented pre-existing set (kanban076 hub-sha check requires a live localhost:6006 service; chronic derived-site posit renders).
- **Hub JSONL repair — mailroom-cuad-contracts-full DatasetGenerationError root-caused, artifact repaired, republished clean (KANBAN-087, board-only, human report 2026-08-23):** the Hub's parquet worker died with `ujson_loads` `ValueError: Expected object or value` while local loads passed — download forensics proved the JSONL structurally valid (510/510 lines parse) but ONE record (line 73) carried **16 literal U+2028 LINE SEPARATOR chars inside `.input.doc_text`** (CUAD PDF-extraction artifact); any loader parsing batches via `str.splitlines()` treats those as record breaks INSIDE the row and shreds it into invalid fragments, while local `datasets` 5.x splits BYTES (`bytes.splitlines()` ignores U+2028) — a version-dependent landmine where a green local load proves nothing. Writer fix: `scripts/datasets/export_bt_to_hf.py` now escapes the hazard set (U+2028/U+2029/NEL) at write time via new `sanitize_line_boundary_chars()` (lossless \uXXXX escapes; `json.loads` decodes identical values) — bare `ensure_ascii=False` dumps were shipping loaded guns to every line-oriented consumer. Artifact repair: staging file sha-matched the Hub bytes (`cac0c845…`), sanitized with the exporter's OWN function, per-row semantic round-trip asserted (0 mismatches), worker-shape A/B proven (original shreds into 526 pieces → repaired stays 510), manifest rewritten honestly (old+new sha256 `c8beefd6…`, repair note). Republish: repaired pair uploaded under CANONICAL names (`<dataset>.jsonl` + `manifest.json`) overwriting the broken blobs — after a first-pass detour that published misnamed `_repaired` duplicates beside the originals (the `hf upload <local-file>` publishes under the LOCAL basename trap; duplicates evicted via `hf repos delete-files`). Verification: repo tree census exactly 4 files, fresh-download round-trip sha equals the repaired artifact, hub manifest consistent, datasets-server `splits` reports `pending: [] / failed: []`. Guarded by 6 network-free pins in `tests/test_kanban087_jsonl_hazards.py` (hazard-set coverage, escape-at-write shape, lossless round-trip, worker-parse-shape collapse, incident-shape replay, writer-path wiring).
- **docclass-pilot — cleanly distributed Mailroom pilot corpus + docclass-merged schema v5 with clause-level ground truth (KANBAN-084, issue #43, human directive 2026-08-23):** NEW [docclass-pilot](https://huggingface.co/datasets/Lucius-Morningstar/docclass-pilot), derived directly from [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) as the pilot testing set for the Mailroom pipeline visualizer AND per-agent evaluation: **138 rows covering all 48 canonical strata** (quota=3 per `expected × expected_subclass`, min-stratum take-all), drawn deterministically by ascending sha256(filename) WITHIN each stratum (rebuild-stable byte-identical re-stage), same two-config layout as the parent (`default` blind vs `ground_truth` joined 1:1 on `filename`, both carrying train/test per the family `split`). The parent simultaneously evolves to **schema v5** (sharded parquet overwritten in place; legacy `docclass_merged.jsonl` retained UNTOUCHED for pinned consumers; `manifest.txt` replaced with the v5 lineage record): **+400 `insurance_claim` rows** (inpatient/outpatient/carrier/pde rendered EOBs from cms-desynpuf-insurance-claims with a verbatim GT contract aligned to llm-mailroom's InsuranceClaimExtraction; source keyed its placement on md5(record_id), fused under the family rule md5(filename)%10 — 65/400 rows changed placement, disclosed on-card; honest gaps: synthetic data, PAID claims only so `coverage_determination` is always approved / `denial_reasons` always empty, `adjuster` always null, single line of business) and **CLAUSE-LEVEL ANSWER KEYS, ground_truth config ONLY**: `cuad_clause_labels` on contract rows sourced from the official CUAD annotation JSON (the machine-readable superset of masterlabels.csv) — **509/509 contracts joined, 13,753/13,753 answer spans verified at exact char offsets** against the stored `doc_text` (compact JSON: clause name → [{text, start}]); `maud_clause_labels` on merger_agreement rows from MAUD's classification dump — **152/152 contracts joined** via contract id (task → category/answer/valid_classes/label_idx). These are the scoring substrate for entity extraction. **Subclass canon normalization** kills CUAD's duplicate grouping-folder spellings that skewed the contract-type distribution: `Affiliate Agreement`(1)+`Affiliate_Agreements`(9)→10, `Endorsement Agreement`(9)+`Endorsement`(15)→24 (contract subclasses 28→26, total strata 50→48); single-sourced as `CONTRACT_SUBCLASS_CANON` + `normalize_contract_subclass()` in `build_docclass_merged.py`, applied at v5 row construction with a build-time canon guard that fails loudly if any legacy spelling survives; deliberately-DISTINCT buckets pinned unmerged (Joint Venture vs `Joint Venture _ Filing` separate CUAD folders, `mixed_cash_stock_election` distinct MAUD class, `attorney_demand` vs `demand` distinct labeler subtypes). Builders: `scripts/datasets/build_docclass_v5.py` (six sha-pinned source shards verified, family-rule claims fusion, clause-GT attachment + span QA), `scripts/datasets/build_docclass_pilot.py` (stratified draw → stage → Hub publish), `scripts/datasets/publish_docclass_v5.py` (regex-anchored surgical edits on the LIVE parent card with count==1 assertions, all-string GT parquet schema matching the parent storage convention). Guarded by 10 network-free pins in `tests/test_kanban084_pilot_sample.py` (blind∩GT=∅ including the new clause keys, quota/coverage-exact deterministic draw, split preservation, shard-pin completeness, canon merge + identity-on-canonical-forms + never-merge list). Suite delta vs pristine HEAD (detached-worktree baseline): 613 passed (+10 pins); residual failures/errors byte-identical to the pre-existing baseline — the chronic posit pair clears on render-commit of this ship, while the kanban076 LFS-pin assert failure and six `tests.test_langfuse_tracing` collection errors reproduce at clean HEAD and are NOT this card's scope (parked for follow-up).
- **Graphify knowledge graph built & published for this repo (KANBAN-080):** first build here despite the skill being vendored since KANBAN-065 — `graphify . --code-only` (local AST, no LLM backend, matching mailroom's convention) → 3,402 nodes / 7,252 edges, then `cluster-only --no-label` → 151 communities + `GRAPH_REPORT.md` + standalone viewer. Published as the derived-artifact Pages site [llm-entity-extraction-graph](https://exios66.github.io/llm-entity-extraction-graph/) (new public repo `Exios66/llm-entity-extraction-graph`: `index.html` viewer + quarto-rendered `report.html` + `.nojekyll`, mirroring llm-mailroom-graph conventions; `graphify-out/` itself stays uncommitted here). NEW `docs/sister-repos.md` — the mailroom-convention umbrella map for THIS repo's side of the family (llm-mailroom, llm-dojo-scoring @v0.7.0, corpus feeds, HF family, both graph sites, governance notes). Links wired: README Working-surfaces, wiki Home quick-links block + `_Sidebar` External section, and mailroom's `docs/sister-repos.md` reciprocally (mailroom commit `b1ef37a`).
- **Scoring-documentation currency pass — every `llm-dojo-scoring` reference brought up to the live `@v0.7.0` pin:** five doc surfaces still described the outsourcing era's `@v0.2.0` pin (or a one-off `v0.4.0` task-kind ref) even though the dependency has been re-pinned three times since (v0.5.1 KANBAN-061, v0.6.0 KANBAN-062/063, v0.7.0 KANBAN-067): `SCORING.md` §0 + the "Scoring model" preamble in `AGENTS.md` + `README.md` §Scoring now all read `@v0.7.0`, and the ContractEval runner row no longer cites a stale upstream version. `SCORING.md` gains **§0.1 "The unified scoring layer & the score-emitter bridge"** documenting what v0.19.0 adopted but never documented on this page: the package-side `registry` (T0 HEADLINE/T1 CORE/T2 DEEP/T3 LOG tiers, built-in default covering both consumers' emission surfaces incl. all 37 mailroom SCORE_CONFIGS names), nine `bundles` task bundles, all 23 agent `profiles` (incl. the Lane A/B review set: `sorter_reviewer`, six per-specialist auditors, `arbiter` — ground-truth-free), the eight document-type-aware `doc_bundles` with the honest-gap mandate and `resolve_doc_bundle()`'s explicit `used_fallback` marker (KANBAN-067), the unified `emitter` (registry-validated emit → JSONL/Langfuse sinks, `get_scorecard(min_tier=...)`, `compare_headlines`), and `pruning` dashboard views — plus this repo's third adapter `src/score_emitter.py` (`build_emitter` / `emit_run_scores` returning `(emitted, skipped)` so unknown names surface as registry work, never silently lost; `dashboard_names`/`headline_names`), which was also missing from the AGENTS.md key-modules table. The expanded package-surface sentence now lists all 25 modules. `wiki/Scoring.md` re-mirrored byte-identical to `SCORING.md` (it had drifted twice: missing the v0.3.0 category-presence routing note AND the entire KANBAN-052 ContractEval §8 block) and pushed to the GitHub wiki via `./wiki/sync-wiki.sh`. Docs-only; zero behavior change; memos/board history deliberately untouched (append-only record).
- **Enron dedup GT enrichment — content-topic + sentiment labels, agent-blind two-config layout (KANBAN-079, issue #37, human directive 2026-08-23):** [enron-correspondence-dedup](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup) republished as **schema v2** with TWO card-declared configs so ground truth is invisible to pipeline agents by default: config `default` (blind/train+test.jsonl) carries ONLY filename/subject/text/split/metadata; config `ground_truth` (ground_truth/train+test.jsonl, joined 1:1 on `filename`) carries every answer key — `expected`, `expected_subclass`, `label_evidence` plus NEW enrichment columns `content_topic`/`topic_evidence` (11-key taxonomy of what each message is ABOUT: energy_market, legal_contracts, scheduling, hr_personnel, finance_earnings, regulatory, it_systems, travel_logistics, marketing_clients, announcements, general_business) and `sentiment_score`/`sentiment_label`/`sentiment_evidence` (deterministic lexicon polarity [-1,1], negation/intensifier-aware, politeness-formula controlled). `load_dataset(repo)` returns the blind view only; scorers opt into GT explicitly (`load_dataset(repo, "ground_truth", split=...)`); the viewer keeps both configs for human auditing (documented on-card as separation-of-concerns, not encryption). The legacy monolithic all-columns jsonl was DELETED from the Hub repo at publish (the JSON loader would otherwise fold its GT columns back into default and re-leak). Labelers live in Enron-Evaluation-Environment `scripts/` beside the shared subclass module (`content_topics.py`, `sentiment_scorer.py`; commit `c3bb908`) and are IMPORTED by the publisher — never forked; 34 network-free tests there (70/70 suite). Publisher rewrite (`publish_enron_correspondence_dedup.py`): same sha-gated source (`0554a5973935…`), same dedup rule (`body_hash` md5 exact-hash, first occurrence wins, empty bodies never deduped — 517,390 rows in → 247,523 out, 269,867 dropped, largest group 112, all 150 custodians), splits recomputed+asserted (222,572 train / 24,951 test, identical per config); guards refuse to publish on invalid topic keys, out-of-range/non-finite sentiment scores, unknown labels, non-uniform metadata key-sets, null leading columns, GT keys present in blind rows, or blind/GT filename join drift; determinism proven by two independent builds producing byte-identical output across ALL FOUR data files. Post-upload verification: LFS-sha equality for ≥10MB blobs + download round-trip hash for sub-threshold files (`ground_truth/test.jsonl`, 9.83 MB, ships as a plain git blob) — all four GREEN, legacy file confirmed gone. Distributions (manifest.txt): topics general_business 183,588 (74.2%) / energy_market 21,605 (8.7%) / hr_personnel 10,062 (4.1%) / scheduling 8,237 (3.3%) / legal_contracts 7,667 (3.1%) / regulatory 4,928 (2.0%) / marketing_clients 3,834 (1.5%) / travel_logistics 2,900 (1.2%) / it_systems 2,841 (1.1%) / finance_earnings 1,163 (0.5%) / announcements 698 (0.3%); sentiment neutral 167,964 / positive 51,668 / negative 27,891. Honest gaps on card + manifest: exact-hash dedup only; single-topic assignment + ~2000-char head window; lexicon sentiment = weak labels (no sarcasm/context modeling); voicemail impossible in a text-only corpus. Pins: 3 deliberate re-pins in `tests/test_kanban076_hf_sync_finish.py` (mechanisms preserved-but-strengthened) + 10 new in `tests/test_kanban079_gt_separation.py`.
## [v0.20.0] - 2026-08-23
### Added

- **HF family sync finish — Hub manifest landmine ROOT-CAUSED via live canaries, all three repos repaired, deduplicated Enron correspondence published (KANBAN-076, human directive 2026-08-23):** the datasets-server conversion failures blocking the family were traced to a sharper rule than the KANBAN-073/074 hotfix assumed: **the Hub's JSON loader ingests ANY repo path whose filename contains `.json` as data rows** — bare `manifest.json`, `.json.txt` (the 074 "fix" is disproven on current infra), at repo root OR in subdirectories — merging the manifest's fields into the data table (`CastError: column names don't match`) and failing `config-parquet`. Proven with four controlled canary uploads under the org (`kanban076-canary{1..4}`): jsonl-only converts clean; identical jsonl + `manifest.json.txt` fails; same with the manifest in a `data/` subdir still fails; identical jsonl + **`manifest.txt`** (no json substring anywhere in the name) converts clean serving pure data features. Repairs applied surgically to [enron-correspondence](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence) and [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) (round 1: `manifest.json`→`.json.txt`; round 2 after the canary verdict: →`manifest.txt`, content byte-identical each hop) with the verified corpus blobs asserted untouched across every mutation (LFS `0554a5973935…` and `af7705368c83…` re-read from the tree before/after). NEW [enron-correspondence-dedup](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup): **exact-duplicate removal over the full corpus — 517,390 rows in → 247,523 unique-text rows out** (269,867 byte-exact copies dropped = 52.2%, matching the source repo's EDA §14 "over half"; largest duplicate group 112 copies of one text; all 150 custodians retained; empty-body rows never deduped against each other), built by `scripts/datasets/publish_enron_correspondence_dedup.py` which imports `body_hash` from Enron-Evaluation-Environment's `scripts/dedupe.py` (single-source hash shared with the EDA duplicate counts — never reimplemented), refuses to build from any source whose sha256 ≠ the verified export prefix `0554a5973935`, streams first-occurrence-wins in maildir-path order (deterministic — two independent builds produced byte-identical output `e2f7241f4d45…`), recomputes+asserts every row's split against the family `assign_split()` (0 mismatches — the md5(filename) rule is keyed on filenames dedup never alters; coverage 222,572 train / 24,951 test), runs the full schema guard, verifies hub LFS sha == local after upload (GREEN), and ships its manifest ONLY as `manifest.txt`; card documents the honest gap (exact-hash dedup only — near-duplicates like quote-stripped replies are NOT detected; use `metadata.message_id` for thread grouping). **Round 3 (docclass-specific):** after the manifest repair docclass-merged STILL failed conversion — fresh error readout (`TypeError: Couldn't cast array of type struct`) exposed a SECOND landmine the manifest poison had been masking: MAUD rows carry a nested dict `metadata.maud_categories` while the leading CUAD row-group doesn't, and the loader infers ONE arrow struct for the whole `metadata` column from the first group then dies casting later groups (the KANBAN-073 partial-schema failure one level deeper — evidence scan confirmed `maud_categories` was the ONLY heterogeneous-typed key). Fixed in the builder via new `normalize_metadata_rows()`: every row carries the UNION of all metadata keys with EVERY value a plain string (missing → empty string, never null; nested dicts AND lists serialized to compact sorted-key JSON strings; scalars stringified). That took two rounds to get exactly right — round 3 preserved CUAD's list-typed `applicable_categories` as `list<string>` and filled absent rows with `""`, which re-crashed conversion (the loader casts later groups against the first group's inferred schema: `string ≠ list<string>` is a hard cast error); round 4 serializes containers uniformly so no key ever carries two types. `publish_kanban071.py` gained a matching pre-upload guard refusing non-uniform metadata key sets or non-string values. Rebuild produced identical 700-row content with the dataset fingerprint UNCHANGED (`cd652e77…` — the fingerprint does not hash metadata, so eval identity is stable); republished + verified LFS sha local == hub (`af0a5324bb65…`). All three publishers' staging blocks now ship `manifest.txt`; 12 network-free pins added in `tests/test_kanban076_hf_sync_finish.py` (no publisher may stage ANY path containing `.json`; `manifest.txt` required; dedup single-source/guard/sha-gate/empty-body-semantics pins; upstream `body_hash` contract; staged-artifact shape). Verification note: the `/status` datasets-server endpoint is retired (404) — job state now read from the `pending`/`failed` arrays carried by `/splits`, `/parquet`, and `/size` responses. Suite **609✓** (+12 pins) / 7 documented posit fails unchanged / 4 skip.

- **Karpathy coding guidelines adapted into core AGENTS.md doctrine (KANBAN-075, human directive 2026-08-22):** a new `## Coding guidelines (adapted from Karpathy)` section now sits between *Code conventions* and *Testing rules* in the repo-root AGENTS.md, translating the four principles from [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) — **Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution** — into house doctrine with repo-specific mappings (card-scope + version-key declaration before first edit; `.replace()` prompt derivation as native simplicity; every changed line traces to the card via explicit-path commits; Phase 4 artifact-derived evidence as goal-driven verification) and an explicit precedence clause: the governed workflow (board lifecycle, append-only prompt versioning, release gates) always outranks the principles where they touch. Adapt-don't-vendor per the KANBAN-066 recipe: upstream pinned at `2c606141936f1eeef17fa3043a72095b4765b9c2`, provenance sidecar `.opencode/agents/CODING_GUIDELINES_PROVENANCE.md` records sources consulted + re-sync protocol, and no upstream sentence is copied verbatim (anti-vendoring pins assert this). Overlap audit against the live tree: prior "surgical" mentions are pytest scope-selection only — fully additive doctrine. Guarded by 9 network-free mechanics pins in `tests/test_coding_guidelines_agent_file.py` (section presence, principle order, precedence clause, doc↔sidecar URL+pin consistency, placement between conventions/testing anchors, verbatim-copy prohibition). Docs-only change; no runtime behavior affected. Suite **597✓** (+9 pins) / 7 documented posit fails unchanged / 4 skip.

- **HF dataset family completeness — deterministic train/test splits everywhere + the cleaned Enron correspondence corpus published (KANBAN-074, human directive 2026-08-22):** every dataset in the `Lucius-Morningstar` family that has train/test semantics now carries a **deterministic per-row `split`** — rule: `md5(filename) % 10 == 0 → test` (~10%), order-independent and rebuild-stable, ONE shared implementation (`assign_split()` in `scripts/datasets/build_docclass_merged.py`) imported by both publishers so no forked rule can drift. Concretely: [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) republished as **schema v3** (700 rows, `filename`/`expected_subclass`/`split` all non-null strings; LFS sha256 local == hub `af7705368c83…`; manifest records `schema_version: 3` + `split_coverage` 628/72; datasets-server types every column `string` and row 0 serves `Co_Branding`/`train`). NEW [enron-correspondence](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence): the **FULL cleaned CMU Enron corpus** — **517,390 parsed messages from 150 custodians, zero dropped** (every index row published) — via new `scripts/datasets/publish_enron_correspondence.py`, consuming Enron-Evaluation-Environment's full-corpus index (`scripts/build_corpus_index.py` over the raw 3 GB maildir, sorted deterministic walk). Ground truth: the SHARED 10-key taxonomy labeler (`correspondence_subclasses.label_correspondence`, imported — never reimplemented) applied per row with an on-row `label_evidence` audit trail; distribution: email 505,929 / memo 3,568 / press_release 2,520 / notice 2,842 / letter 2,077 / demand 315 / meeting_request 135 / attorney_demand 4 / other+voicemail 0 (sums to exactly 517,390); splits 465,570 train / 51,820 test; LFS sha256 local == hub `0554a5973935…`; datasets-server GREEN (`pending: [] failed: []`, all 8 columns typed, row 0 = allen-p email/train); card documents labels as HEURISTIC ground truth with honest known gaps (attorney-detection list coverage, voicemail impossible in text corpus, cross-custodian duplicates NOT merged — group by `metadata.message_id`). Family audit verdicts recorded honestly: [legalbench-full](https://huggingface.co/datasets/Lucius-Morningstar/legalbench-full) ships native upstream train/test TSVs (complete as-is); the three mailroom BT mirrors are whole-gold eval pools where train/test semantics don't apply (documented, not manufactured). Guards extended: both the docclass builder refuse-to-write check and the publisher pre-upload guard now also require `split ∈ {train, test}`; +4 pins in `tests/test_kanban071_hf_pack.py` (split determinism + single-source rule, dump-level split coverage, enron publisher guard/labeler-source pins). Suite **588✓ / 7 documented posit fails unchanged / 4 skip**.

- **docclass-merged schema v2 — subclasses + file names on every row, Hub viewer cast-crash fixed (KANBAN-073, human directive 2026-08-22):** the [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) Hub dataset now carries `expected_subclass` and `filename` as non-null strings on ALL 700 rows — contracts included, using CUAD's own contract grouping (`metadata.category`, 28 groups: Marketing, Maintenance, License_Agreements, …) as the contract subclass, with `filename` = the source PDF basename; MAUD (consideration types) and S-1 (record subclasses) already carried both fields. This also fixes the reported Hub viewer failure (`DatasetGenerationError: Couldn't cast array of type string to null`): the old file was written CUAD-first with all-null subclass + empty filename, so the JSON loader inferred null-typed columns from the opening batches and crashed when later string batches arrived — the exact inference-on-prefix failure. Guardrails so it can't regress: the builder refuses to write any row lacking either field, and `publish_kanban071.py` gained a pre-upload schema guard refusing partial-null uploads; the manifest records `schema_version: 2` + subclass coverage (700/700/28 contract groups); 4 new network-free pins in `tests/test_kanban071_hf_pack.py` (now 12). Republished + verified: LFS sha256 local == hub (`3bd9d74de9f1…`), new deterministic fingerprint `cd652e77…`, and the datasets-server serves the dataset cleanly — `splits` shows no pending/failed conversions and `first-rows` types both label columns as `string` with real values on row 0. Side effect worth noting: the docclass eval runner already grades `expected_subclass` when present, so contract rows now participate in subclass scoring (previously skipped) — a strictly richer eval surface, no runner changes needed. Suite **585✓ / 7 documented posit fails unchanged / 4 skip**.

- **Full LegalBench pack + merged docclass corpus → Hugging Face Hub, CUAD-quality label enrichment (KANBAN-071, human directive 2026-08-22):** two new verified Hub datasets under `Lucius-Morningstar`. [legalbench-full](https://huggingface.co/datasets/Lucius-Morningstar/legalbench-full) mirrors ALL 162 upstream task directories of HazyResearch/legalbench (CC BY 4.0) fetched verbatim from source (160 with data: 856 train rows, 16 test splits = 10,219 rows, byte-exact TSVs/prompts/READMEs; 2 honestly marked EMPTY as upstream ships them) plus a CUAD enrichment layer for all 38 `cuad_*` tasks: every {excerpt, Yes/No} row is re-joined to CUAD_v1.json expert annotations via a whitespace-flexible excerpt locator (199 exact + 1 fuzzy ≥0.75 / 20 span-unmatched / 8 unknown-contract — every row dispositioned, none dropped), attaching char offsets, overlapping clause questions with exact expert spans, and an on-row `category_audit` cross-check of the LB label against CUAD's expert highlights ON THE EXCERPT (192 agree / 8 SUSPECT / 0 mismatch; labels never rewritten). [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) publishes the unified document-classification surface: 700 rows = 509 CUAD contracts (local staging-export reuse — BT stays read-only) + 152 MAUD merger agreements + 39 EDGAR S-1 corporate-record exhibits, deterministic order + fingerprint `5b682f62…`, subclass GT carried for MAUD consideration types and S-1 record subclasses. New tooling: `scripts/datasets/build_legalbench_full_pack.py` (full-task-tree fetch + enrichment + `ENRICHMENT_REPORT.json`) and `scripts/datasets/publish_kanban071.py` (dataset cards, upload, verification); `build_docclass_merged.py` gains a local-first CUAD loader (`--bt-cuad` fallback kept). Verification ran GREEN twice (re-upload doubles as independent reproduction): legalbench-full 379/379 files byte-proven via git-blob OID vs the Hub tree + aggregates round-trip hash; docclass-merged LFS sha256 local == hub (`c8faf0ab6ed8…`). Also restored the missing `data/maud/classification.jsonl` local dump (25,827 MAUD per-question rows — the earlier contracts-only stream had left it absent) and fixed a latent crash in the `tests/test_pipeline_sources_eda.py` footer-collision helper (a bare `FigureCanvasBase` lacks `get_renderer`; attach an Agg canvas when missing — that test was skip-guarded until this session's CUAD_v1.json download un-skipped it). Suite **573 passed / 7 failed (documented posit-render set, unchanged) / 4 skipped** + new network-free pins `tests/test_kanban071_hf_pack.py` (8 tests).

- **Braintrust → Hugging Face dataset mirror (KANBAN-069, issue #34):** the eval ground truth hosted in Braintrust is now mirrored to the Hub for universal agent/eval-runner access — [Lucius-Morningstar/mailroom-cuad-contracts](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-cuad-contracts) (50 rows + 546 page-PNG attachment payloads under `images/`), [Lucius-Morningstar/mailroom-cuad-contracts-full](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-cuad-contracts-full) (510 rows), and [Lucius-Morningstar/mailroom-lb-hearsay](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-lb-hearsay) (5 rows), each with a provenance dataset card (source corpus + CC BY 4.0 license, BT project/dataset ids, export sha256). New tooling: `scripts/datasets/export_bt_to_hf.py` (STRICTLY read-only against Braintrust — live-catalog discovery via `GET /v1/dataset`, streamer defaults absent from the catalog recorded as skipped never created, row reads via the SDK's BTQL query surface, resumable image-attachment download into gitignored `data/hf_export/`) and `scripts/datasets/publish_hf_mirror.py` (dataset-card generation, upload, post-upload sha256 verification). Verification record: `mailroom-cuad-contracts-full` byte-identical via LFS sha256; `mailroom-cuad-contracts` re-exported in the payload-resolved shape (`input.image`/`input.pages[]` = `{type: image_file, file: …}` refs) and round-trip hash-matched with all 596 row→image references resolving on the Hub; `mailroom-lb-hearsay` round-trip hash-matched. Honest gaps recorded in `EXPORT_SUMMARY.json`: `mailroom-maud-contracts` + `mailroom-s1-corporate-records` exist in BT but hold zero rows; the other LegalBench/MAUD-classification streamer defaults were never created upstream — populate upstream first, then re-run export→publish. Braintrust stays READ-ONLY per AGENTS.md (`BRAINTRUST_LOGGING=disabled` preserved); no prompt constants touched.

- **Doc-type-aware scoring engine re-pin — `llm-dojo-scoring` `v0.6.0 → v0.7.0` (KANBAN-067, issue #32):** upstream adds `DOC_TYPE_BUNDLES` (one registry-validated metric bundle per processed document class: contract, corporate_record, due_diligence, correspondence, compliance_filing, court_opinion, insurance_claim, merger_agreement), the explicit-fallback `AgentProfile.resolve_doc_bundle()` honesty resolver (degrades to task bundles with a `used_fallback=True` marker, never silently), and the 23rd agent profile `insurance_claims_specialist` (companion to llm-mailroom's insurance_claim class, mailroom commit `99536d8`). Honest-gap mandate honored in-code: MAUD-derived merger scorers, Enron-derived correspondence scorers, and DE-SynPUF-grounded claims scorers are declared PENDING in their bundle descriptions rather than invented; contracts (CUAD) and court_opinions (LegalBench) ship real type-specific metrics today. Also fixed a pre-existing drift: `requirements.txt` still pointed at `v0.4.0` (comment said v0.1.2) while pyproject was at `v0.6.0` — both now consistent at `v0.7.0`. Consumer venv verified on 0.7.0 (`direct_url.json`: tag v0.7.0 @ `51822bc`); bridge imports (`field_scoring`, `metrics`, `scorers`, `cost_models`, `bootstrap`) resolve clean; full suite **561 passed / 6 skipped**, unchanged. No prompt constants touched.

- **True-GEPA upgrade of the prompt-engineer agent (KANBAN-066, issue #31):** `.opencode/agents/prompt-engineer.md`'s GEPA sections rewritten to be source-true to [gepa-ai/gepa](https://github.com/gepa-ai/gepa) @ `b265bf9ca77fd8e8d82039d9f74911b8780fe1ce` (2026-08-19) — mechanics extracted from the engine source (`strategies/acceptance.py`, `candidate_selector.py`, `component_selector.py`, `batch_sampler.py`, `proposer/merge.py`, `proposer/reflective_mutation/reflective_mutation.py`, `core/state.py`, `api.py`), not paraphrased from the paper. The 5-step folklore loop is now the engine's real 9-step iteration: Pareto parent selection (`ParetoCandidateSelector` default / CurrentBest / EpsilonGreedy / TopKPareto — sample among frontier members, not always the champion), seeded epoch-shuffled minibatch sampling, full-trace ASI capture, reflection-dataset construction (separate `reflection_lm`, `skip_perfect_score=True`), component-scoped proposal (`RoundRobin` default vs `All`), same-minibatch child evaluation, the **`StrictImprovementAcceptance` gate** (accept iff sum(child) > sum(parent) on the SAME minibatch; `ImprovementOrEqualAcceptance` = labeled lateral moves), frontier recompute across `frontier_type` instance/objective/hybrid/cartesian (repo practice = hybrid), and system-aware merge as a scheduled event with the four source-true preconditions (common ancestry, validation-support disjointness `merge_val_overlap_floor=5`, composable shared components, accept iff score >= max(parents)). Phase 5 gains per-cell dominance semantics (`get_pareto_front_mapping`) and a rejected-mutation ledger doctrine (rejections are frontier signal). Governed workflow untouched: version-key identity, same-surface A/B, noise floor, chunked surfaces, board discipline all preserved. New sidecar `.opencode/agents/PROMPT_ENGINEER_GEPA_PROVENANCE.md` pins the upstream ref, license (Apache-2.0, names/behavior referenced only — no code vendored), per-file source map, and re-sync recipe. New `tests/test_prompt_engineer_gepa.py` (12 network-free tests, green): pins every class name/default/frontier-type/merge fact in the agent file, cross-checks agent↔provenance consistency, and asserts the governed-workflow markers survived the rewrite. Tooling/docs-only; no pipeline, prompt-constant, or dependency changes.

- **Vendored Graphify agent skill → `.opencode/skills/graphify/` (KANBAN-065, issue #30):** the official opencode agent skill from [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) (upstream `v8` @ `b2cd362`, Apache-2.0/MIT) copied verbatim — `SKILL.md` (the `/graphify` build/query/path/explain/update workflows) + 8 `references/` sidecars — alongside a PROVENANCE.md noting source ref, license, and re-sync steps. Gives every coding agent working here a deterministic knowledge-graph workflow over the codebase for future use (no runtime dependency added until someone actually installs the `graphifyy` CLI and builds a graph). Network-free consistency tests (`tests/test_graphify_skill.py`, 5 passed) pin the structure and keep the llm-mailroom copy byte-identical.

## [v0.19.1] - 2026-08-21
### Changed
- **Dependency re-pin — `llm-dojo-scoring` `v0.5.1 → v0.6.0` (KANBAN-062/063 support, issues #28/#29):** upstream added the review/audit profile registry this release train's new pipeline agents resolve by name — `sorter_reviewer` (Lane A classification review, classification bundle) and `arbiter` (Lane B judgment arbitration, audit bundle, ground-truth-free), plus six per-specialist auditors (`contract_auditor`, corporate_records, due_diligence, correspondence, compliance, court_opinions). No prompt constants touched (append-only discipline unaffected); the eval loop's scoring surface is unchanged (v0.6.0 is purely additive over v0.5.1's 37/37 registry). Both consumer venvs verified on 0.6.0; llm-mailroom ships its Lane A/B build on this pin in mailroom v0.4.0.

## [v0.19.0] - 2026-08-21
### Added
- **Unified scoring layer adoption — `src/score_emitter.py` bridge + `llm-dojo-scoring` re-pin `v0.5.0 → v0.5.1` (KANBAN-061, human-approved option C, 2026-08-21):** the shared scoring package now owns the full metric infrastructure this repo emits through: `registry.py` (YAML-backed metric definitions, T0 exact/T1 score/T2 aggregate/T3 log tiers — every existing function mapped: f1/binary_metrics→T0, precision/recall/f2/jaccard/field_presence/laziness/cost→T1, confusion/failure-modes/bootstrap→T2, raw logs→T3; registry covers 100% of both consumers' emission surfaces incl. all 37 mailroom SCORE_CONFIGS names), `bundles.py` (classification/extraction/extraction_open/cost/factuality/laziness_detection/transcription/audit — the audit bundle is first-class for KANBAN-060's audit pass), `profiles.py` (agent profiles: sorter, 6 specialists, judge, boss, pdf_transcriber, image_extractor, archivist, audit_agent), `emitter.py` (unified score emitter with Langfuse + local sinks), `pruning.py` (tier-based dashboard filtering). Local bridge `src/score_emitter.py` (+ `tests/test_score_emitter.py`, 5 network-free tests): resolves the active agent profile → bundle → tier filter, emits through the package's unified emitter; calculations untouched (Hungarian matching, embedding rescue, bootstrap CI, CUAD equivalences all live upstream unchanged). Upstream releases: `llm-dojo-scoring` v0.5.0 (unified layer) + v0.5.1 (registry completeness); llm-mailroom migrated onto the same engine in its v0.3.2 (1,273-LOC duplicate replaced by a shim). Pin bumped v0.5.0→v0.5.1; venv verified on 0.5.1; bridge tests green; full suite 540 passed (7 pre-existing Quarto site-render failures unrelated — opencode's KANBAN-060 site lane render lag).

### Added
- **v39 + audit iteration (KANBAN-059/060, 2026-08-20):** A/B tested  vs  on 20-row chunked sample (seed 42): overall +0.0142 inside ±0.03 noise floor; key_obligations +0.1109 (11.09pp) substantial improvement promoting v39 as frontier arm key_obligations specialist.  A/B: recall-side champion (F2-lead), Pareto {v39 (P), audit (R/F2)}. Memo  documents diagnosis, root cause (emission-stage omission), and frontier selection. No code behavior change; documentation + iteration-close only.

### Added
- **Runner-level audit pass → `contracts_audit_v0` + `ContractsSpecialist.audit_extraction()` + `--audit` flag (KANBAN-060, human directive 2026-08-20: address the missed absent-family pairs through the most fitting methods)** — the diagnosed mechanism (645 absent (doc, category) pairs; 551/645 labels VERBATIM in the model's input; 523/591 in-text pairs get ZERO output for the category) is emission-stage category-selective omission: a single forward generation cannot re-read, and every prompt lever measured flat (v37 scan family, v38 named re-scan, v39 completion: absent 636→645). The fitting method is a **second structured call with missed-category feedback**: `CONTRACTS_AUDIT_PROMPT_V0` (registered in `PROMPT_VERSIONS`; 32 exact canonical category names; verbatim quote discipline; never-fabricate; ADDING-only; one entry per distinct clause sentence) + `ContractsSpecialist.audit_extraction()` — one audit call per extraction window (same `_split_chunks` windows; single-window docs = one whole-text call), input = window text + the canonical-tagged already-quoted clauses, `AUDIT_SCHEMA` = `{"missing_obligations": [{category, clause}]}` at temp 0.1; merge = UNION with normalized dedupe into `key_obligations` + canonical-tagged reasoning entries (`section_ref: audit-pass`, routing the KPI mapper); failing/parse-error windows skipped, never fatal; `_last_usage` sums extract + audit calls. Runner `--audit` flag (dry-run prints `audit=ON`; `parameters.audit` in the experiment-log record). Tests: `tests/test_audit_pass.py` (7 unit: union/dedupe, empty-answer noop, parse-error skip, multi-window usage accumulation, whole-text single window, schema contract, unlabeled-entry rejection) + 2 langfuse-runner smokes (`--audit` wiring + merged output in the record; off by default) — 105 surgical tests green. A/B LANDED on the same 255-doc surface (seed 42, chunked): `qwen3.7-flash_contracts_specialist_v39_audit_extraction_chunked_half` — **run KPIs recall 0.3627 / F1 0.4605 / F2 0.3963 / precision 0.6306 / false-nr 0.2388 / verbatim 0.371 / laziness 0.799 vs v39 (R 0.2833 / F1 0.4146 / F2 0.3244 / P 0.7727 / false-nr 0.3643)**; corrected per-doc paired gate (252 shared, seed 42, 2000 boots): **recall +0.0637 BEATS (P 1.000), F2 +0.0489 BEATS (P 1.000 — the F2-lead decision), F1 +0.0258 inside band (P 0.950, CI lower −0.0048), precision −0.0942 LOSES (P 0.000)**. Mechanism direct: absent positive pairs 612→399 (−34.8%). Audit-added clauses: 1,139/227 docs = 55 TP + 797 in GT-present categories (357 overlap a GT label; 440 are real sibling sentences CUAD partial-GT never sampled) + 342 GT-absent (fp) — the precision loss is predominantly GT-coverage reality, not fabrication (verbatim discipline held). **Cost consolidation (human directive 2026-08-20 "we have already input the whole contract text once"): the audit call reuses the extraction system prompt + byte-identical user prefix (verified in tests), so the re-read hits OpenRouter's automatic context cache (qwen3.7-flash cache-read $0.006/M vs $0.03/M fresh = 20%) → next audit run ≈ $0.33-0.35 vs the pilot $0.49 (12.2M prompt tokens vs v39 5.84M).** Verdict: audit = new recall-side champion (F2-lead); v39 = precision champion; Pareto = {v39 (P), audit (R/F2)}.
- **Maximize-everything crossover → `contracts_specialist_v39` (KANBAN-059, human directive 2026-08-20: improve recall AND precision + F1 and F2)** — v39 = v37 (which embeds v36 + the payment fold; derivation chain v36→v37→v39 asserted) + 4 surgical `.replace()` edits, registered in `PROMPT_VERSIONS`. Measured substrate (255-doc half-corpus, CORRECTED scorer — whitespace-collapse + `<omitted>`-stripping landed in `load_master_gt`, all records re-scored): **v37 leads every recall-side metric** (F1 0.4170 / F2 0.3382 / R 0.3004 / P 0.6820 / J 0.4981 / false-nr 0.3260 vs champion v36 F1 0.4073 / F2 0.3243 / R 0.2855 / P 0.7107) but the per-doc paired gate is inside band (v37: +25 TP at +40 FP). **Per-category FP audit (corrected): Termination For Convenience = 53 fp — the largest fp category, all genuine model errors (term-of-agreement clauses, for-cause/default/product-discontinuation terminations tagged as convenience; the category has NO enumeration entry, only a guard-list name); Uncapped +5 fp (fee/royalty "CAPs" tagged as liability caps); Revenue/Profit +6 fp (service fees, cost-sharing); Price Restrictions fp only 13→14 under the corrected scorer; Third Party fp 31 = GT-label noise (disclaimer clauses ARE in-category per CUAD), NOT suppressed.** **Near-miss decomposition (v37, corrected): 556 = 371 multi-label under-quote (67%) + 88 sibling-sentence + 63 leading-phrase drop + 19 paraphrase + 15 dash-GT** — the 371 are NOT quote-style: 35% of positive pairs carry ≥2 GT clause sentences and the model quotes a subset (NETGEAR Insurance 3 clauses/2 quoted; Cap On Liability 9/3; label==span byte-identical for the quoted ones). Edits: (1) enumeration **entry 27 = Termination For Convenience** with the WITHOUT-CAUSE boundary + NEVER shapes (term/expiration clauses, default/breach/cause, regulatory/discontinuation) + measured 53/71 stat — the precision lever; (2) **money-family boundary clarifications** in the R2 payment block (a fee/royalty/price CAP is NOT a liability cap; service fees/cost-sharing are NOT Revenue/Profit Sharing; a price-change notice duty is not a Price Restriction unless it caps amounts or frequency); (3) **WITHIN-CATEGORY COMPLETION** in the grain rule (a category whose clause appears in several sentences is INCOMPLETE until EVERY distinct clause sentence is quoted as its own item, from its FIRST WORD through its final period — 35%/556-of-1,678 stats inlined); (4) R2 checklist strengthen (ONE item AND ONE reasoning entry PER DISTINCT CLAUSE SENTENCE). Precision risk of (3) ~zero (extra quotes land inside already-present categories; fp is GT-absent-category-defined). Contradiction check passed (entry 27's NEVER-shapes vs the v36 term rules; carve-outs don't touch Non-Compete/ROFR). Test `test_contracts_v39_payment_fold_precision_and_completion` — 64 prompt + 19 sweep + 12 smoke tests green; runner dry-run accepts v39 with the reserved name. Run name `qwen3.7-flash_contracts_specialist_v39_extraction_chunked_half` confirmed on the board; manifest `data/manifests/extract_v39_half.jsonl`; champion gate vs v36 — command returned to the human, run NOT launched. Prediction: P 0.68-0.72 / R 0.32-0.35 → F1 0.44-0.47, F2 0.36-0.39 (TFC boundary −20-30 fp; completion +40-100 TP).

### Fixed
- **GT/scorer artifact fix → ContractEval KPIs re-scored (KANBAN-058, the F1-chase lever): whitespace + `<omitted>` normalization in `src/contracteval.py::load_master_gt`** — the master-clauses GT stores clause spans with embedded `\n`/multi-space runs (1,416 cells) and `<omitted>`/`[omitted]` redaction markers (695 spans) that the verbatim containment predicate (`contracteval_classified`) can never match — measured **37% of the KPI FN mass on the 255-doc half-corpus (493/1,686 whitespace FN + 242 `<omitted>` FN) was GT-storage artifact, not extraction failure**. New `_clean_span()` collapses whitespace to single spaces and strips the redaction markers at GT-load time (the shared `llm_dojo_scoring` package is untouched — the normalization lives in the local GT pipeline). **Effect (re-scored stored records, no LLM spend): v34 F1 0.1331→0.1740, v35 0.1408→0.1777, v36 0.3277→0.4073 (recall 0.2187→0.2855, precision 0.653→0.7107), v37 0.3256→0.4170, v38 0.3108→0.4111; champion re-confirmed via the corrected per-doc paired bootstrap — v36 BEATS v34 (P 1.000), v36 vs v37/v38 inside band (v36 numerically ahead).** `backfill_extraction_kpis.py --refresh` recomputes KPI blocks under the corrected scorer (documented one-time re-scoring backfill); experiment-log md + site data regenerated. Tests `test_clean_span_*` / `test_load_master_gt_normalizes_artifact_spans` / `test_cleaned_gt_span_matches_model_output_verbatim` (16 contracteval tests green). The 18 literal-newline cells (unparseable literals) remain GT-data debt; the residual F1 headroom is now genuinely prompt-side (the sparse-family + payment + precision levers).

### Added
- **Sparse-family shape completion + named re-scan → `contracts_specialist_v38` (KANBAN-057, next F1 mutation on v36's WIN)** — v38 = v36 + 2 surgical `.replace()` edits (v36 byte-identical, derived chain asserted, registered in `PROMPT_VERSIONS`). Measured substrate (255-doc half-corpus, v36 record + master GT CSV, KPI-level fn decomposition over 1,686 positive pairs): **v36 FN 1,319 = 493 whitespace-artifact (GT-side `\n`/multi-space label runs — flagged to the scoring lane as KANBAN-058, NOT worked around in the prompt) + 242 `<omitted>`-placeholder GT labels (unfixable by any model) + 48 genuine near-misses + 536 ABSENT (no quoted span ≥0.7 token coverage)** — the prompt lever is the 536 absent pairs, concentrated in families the model never quotes: Post-Termination Services 55, Anti-Assignment 43, Cap On Liability 43, Minimum Commitment 37, License Grant 33, **Warranty Duration 32 (absent from the prompt entirely)**, Revenue/Profit Sharing 31, **Competitive Restriction Exception 29 + Volume Restriction 29 (guard-list names but NO shape entries)**, Covenant Not To Sue 25, Liquidated Damages 22, Non-Transferable License 20; shape-complete families (Covenant/Post-Termination/Liquidated) stay absent-heavy — the generic R2 checklist self-check does not fire, so the fix is a NAMED re-scan. Edits: (1) enumeration entries **27-29** — Warranty Duration (warranty-period clauses, real GT examples, "32 of 32 present clauses never quoted" stat), Competitive Restriction Exception (notwithstanding-carve-out shapes, "39 of 39" stat), Volume Restriction (quantity/amount ceilings, "35 of 39" stat); (2) **UNDER-QUOTED FAMILY RE-SCAN** sentence in the R2 completeness block naming the absent-heavy families (536/1686 stat inlined), placed after the ADDING-only discipline, adjacent to the never-fabricate guard. Precision risk ~zero (target families carry 0-6 fp on the surface); contradiction check passed (carve-out ≠ Non-Compete, Volume ceiling ≠ Minimum Commitment floor, re-scan tag spellings aligned to the guard list — `Joint Ip Ownership`). Crossover decision: v37's payment block NOT folded into v38 (measured F1-flat + precision regression 0.653→0.613 on the current scorer; its money quotes become assets post-KANBAN-058 — revisit as a v39 crossover). Test `test_contracts_v38_sparse_family_shapes` — 63 prompt + 46 sweep tests green; runner dry-run accepts v38 (255 rows, chunked 90k/8k, Langfuse llm-dojo). Run name reserved `qwen3.7-flash_contracts_specialist_v38_extraction_chunked_half`; manifest `data/manifests/extract_v38_half.jsonl`; champion gate vs v36 — command returned to the human, run NOT launched. Prediction: 80-130 new matched pairs → F1 0.328 → 0.37-0.40 (candidate win; conversion rate is the swing factor).
- **Payment/monetary capture + canonical tag discipline → `contracts_specialist_v37` (KANBAN-056, GEPA crossover built on v36's WIN)** — v37 = v36 + 4 surgical `.replace()` edits (+3,981 chars; v36 byte-identical) per the frozen design in `memos/contracts_specialist_v37_design.md`. Measured substrate (255-doc half-corpus, v34 record + master GT CSV, 255/255 normalized join): payment families are **297 of 801 (37%) present-but-untagged (doc, category) pairs** — Price Restrictions 0/9 tagged (+24 fp), Uncapped Liability 1/46, Volume Restriction 3/35, MFN 3/11; **78/255 docs collapse ALL key_obligations items under one field-level reasoning tag** (115 of the 297 misses; 50/78 of those docs contain emitted-but-untagged money items); **contract_value is never GT** (0/255 expected — the base-rate claim confirmed at record level) but predicted on 101/255 and **null on 113/255 docs that carry payment GT**. Edits: (1) **PAYMENT TERMS & MONETARY CLAUSES mandatory scan family** in the R2 completeness block — 10 money-clause shapes (Revenue/Profit Sharing, Minimum Commitment, Volume Restriction, Price Restrictions, Liquidated Damages, Cap/Uncapped Liability, Insurance, MFN, Post-Termination Services) each quoted at v36's full-sentence grain + tagged with its exact canonical category, measured examples inlined ("royalty equal to the Specified Royalty Percentage of all revenues received", "thirty percent (30%) of the Net Sales in excess of Eleven Thousand Dollars ($11,000) per calendar month", "not less than $1 million per occurrence", "nothing in this Agreement shall limit either party's liability"); (2) **canonical tag discipline** — never a field-level `key_obligations` entry, never a sibling/generic tag (a royalty is Revenue/Profit Sharing, NOT License Grant; an insurance limit is Insurance, not Cap On Liability), 78/255 collapse stat inlined; (3) **contract_value trigger extension** (rule 10) — a payment schedule ("$55,000 for First Contract Year"), a per-unit fee or royalty, a minimum commitment amount, or an aggregate consideration phrase ALL count as visible consideration (113/255 stat inlined); (4) Uncapped Liability (entry 21) + Liquidated Damages (entry 23) enumeration appends (entries 10-13 already carried the shapes). Section targets disjoint from v36's grain/term_length/effective_date edits; one-pass preserved; contradiction check passed (payment block additive-only; "a fee or payment amount alone is NOT a price restriction" resolves the 24-fp Price-Restrictions confusion). Test `test_contracts_v37_payment_monetary_capture` — 62 prompt tests + 15 sweep tests green; runner dry-run accepts v37; registered in `PROMPT_VERSIONS`. Run name reserved `qwen3.7-flash_contracts_specialist_v37_extraction_chunked_half` (255-doc half-corpus A/B vs v36 pending — command returned to the human, run NOT launched).
- **Full-sentence span-grain reconciliation → `contracts_specialist_v36` (KANBAN-056, GEPA iteration after the v34/v35 half-corpus A/B)** — v36 = v35 + 7 surgical `.replace()` edits resolving the **fragment-grain rule_contradiction** that v34/v35 inherited from the v10-era rules ("ATOMIC FRAGMENTS … typically 10-25 words", "STRIP sentence preamble and riders", "a list of a few long merged sentences signals missed spans: split them" vs v34's R3 verbatim rule). Measured substrate (sim-matrix over the shared 255-doc surface, expected-vs-predicted containment): key_obligations 1600 labels → MATCH 572 / NEAR 448 / MISS 580, with **146/448 NEAR = PURE TRUNCATIONS** (predicted item a head-prefix of the GT sentence; 88–93% of predicted tokens inside GT) + 265 ellipsis-condensed overlaps — the model follows the concrete fragment instruction and drops sentence continuations, which containment scoring can never reward (GT label = the annotator's stored clause sentence). v36 edits: (1) fragment grain → **FULL CLAUSE SENTENCE grain** (one item per distinct sentence, quoted verbatim in full, never per-right fragments, never ellipses — with the measured 146-of-448 truncation stat and the Bunker One / Licensee examples inlined); (2) SPAN-DISCIPLINE completion reframed to full-sentence grain; (3) R3's "trim to the 10-25-word operative core" → complete-sentence quoting; (4) SIZE-CALIBRATION reframed (split MERGED MULTI-SENTENCE items, never a sentence itself); (5) v35's ITEM-LEVEL CATEGORY GUARD kept but re-cast to full-sentence quoting per duty (dedupe within category only — no contradiction remains); (6) **term_length duration-only guard** ("two (2) years" with no clause = a MISS; measured 16/208 term_length expectations on v34 were duration-only; v35's paired term_length 0.7580 vs v34 0.8006, CI [0.004, 0.102]); (7) **effective_date blank-placeholder carve-out** (a "April __, 2005" blank is NOT a stated date → null, never a fabricated fill; the scorer satisfies blank-template expectations with null — 5/16 effective_date misses on v34 were fabricated fills). v0-v35 byte-identical; `CONTRACTS_SPECIALIST_PROMPT_V36` registered in `PROMPT_VERSIONS`; test `test_contracts_v36_full_sentence_grain` (61 prompt tests green; runner dry-run confirms the version). Memo `memos/contracts_specialist_v36.md`; run name reserved `qwen3.7-flash_contracts_specialist_v36_extraction_chunked_half` (255-doc half-corpus A/B vs v34 pending).
- **One-pass extraction: item-level category split → `contracts_specialist_v35` (KANBAN-055 — the THIRD anti-collapse lever)** — built on opencode's v34 (KANBAN-054): v34 added R1 field-presence self-check + R2 category-level completeness + R3 verbatim GT alignment (structural/category-discipline); v35 closes the third collapse mode neither of those targets — **ITEM-LEVEL CATEGORY COLLAPSE**, where a single `key_obligations` item holds duties from TWO different canonical categories (e.g. "Neither Party shall assign this Agreement nor use its trademarks" folds Anti-Assignment into Non-Disparagement/IP Ownership), routing to one category and scoring 0 on the other (measured ~15,516/33,312 umbrella-tagged entries on the stored v31/v32 reasoning corpus that drove KANBAN-051). **v35 = v33/v34 base + ONE surgical append** (`CONTRACTS_SPECIALIST_PROMPT_V35`): one ENTRY per distinct category's duty within a clause (a two-category clause emits one entry per duty, each tagged with its OWN canonical category name, quoting that duty's operative words), and EXACT-category tagging only — never a sibling / family / generic 'IP' (explicitly: 'No-Solicit Of Customers' ≠ 'No-Solicit Of Employees', 'Cap On Liability' ≠ 'Uncapped Liability', a license grant ≠ generic 'IP'). Registered in `PROMPT_VERSIONS`; test `test_contracts_v35_item_level_category_split` (full prompt file green). Rebased onto `origin/main` KANBAN-054 with a clean rename (the earlier local v34 name-collision resolved to v35 + KANBAN-055; opencode's v34 kept). Board KANBAN-055 + discussion post. **A/B vs v34 (50-doc chunked surface) held for the human per directive** — v35 is code-complete + unit-verified, not yet empirically A/B'd.
- **Extraction agent anti-collapse prompt `contracts_specialist_v34` + ContractEval-rubric KPIs as core extraction metrics (KANBAN-054, human request)** — (1) **prompt v34** = v33 + THREE surgical rules (human decision 2026-08-19: verbatim-at-span-grain formulation): **R1 FIELD-PRESENCE SELF-CHECK** (a schema field is null only when the document genuinely does not state it; `contract_value` = the consideration clause quoted verbatim — never null when a consideration/price/"$" phrase is visible; targets the v32@510 presence lows: contract_value 0.39, renewal_terms 0.37, effective_date 0.88, term_length 0.83; additive only); **R2 CATEGORY-LEVEL COMPLETENESS** (post-extraction checklist over the 32 canonical CUAD YES/NO categories — a category present in the text with zero canonical-tagged items/entries is INCOMPLETE, scan back and ADD, never fabricate; targets the mapping benchmark's dominant failure: 67% of present categories produced no mapped item, 42.7% of positive pairs covered ≥0.7); **R3 VERBATIM QUOTING at the GT span grain** (quote word-for-word — the GT label is the clause's own text; a paraphrase scores as a miss; cut preamble/riders, never reword the remainder; targets the 9.2% verbatim vs 42.7% ≥0.7 paraphrase penalty). (2) **KPIs** — `scores.contracteval_kpis` on EVERY extraction run record (`src/contracteval.py::run_kpis` = `evaluate_record` + `coverage_bands` over the run's own rows vs the committed master GT, injected in `run_extraction_eval.py::log_experiment_to_repo` — both extraction runners; offline, deterministic, best-effort like `diagnostics`): ContractEval's exact rubric — accuracy/P/R/F1, **recall-weighted F2**, token-set Jaccard over positive pairs, no-related + false-no-related rates, n_pairs/n_positive/n_docs/unjoined — plus the semantic coverage bands (verbatim / ≥0.7 / ≥0.5 / ≥0.3). Human decisions (2026-08-19): KPIs ADD alongside existing metrics with **F2 leading** (the honest axes for a one-pass extractor: precision structurally 1.0); A/B on the **50-doc chunked surface only** (full-corpus KPI baseline stays v32). Experiment-log renderer (`_contracteval_kpis_lines`), site trends keys (`build_trends`: f1/f2/jaccard_mean/false_no_related_rate/recall/semantic_ge0_7/semantic_verbatim/kpi_n_pairs) + a new F2/Jaccard/semantic/false-nr KPI trend chart in `docs/assets/site.js` (render audit re-run on the next site regen), and `scripts/reporting/backfill_extraction_kpis.py` (documented one-time backfill for the eval machine's historical records). Verified on the stored v32@510 record: F1 0.1579 / F2 0.1049 / Jaccard 0.2129 / false-nr 0.6818 / semantic ge0.7 0.4332 (consistent with the mapping memo). Tests: `test_contracts_v34_anti_collapse_rules` (58 prompt tests green), `test_run_kpis_block` + `test_run_kpis_empty_record_degrades`, `test_extraction_kpis_land_in_record` (hermetic master GT). Memo `memos/contracts_specialist_v34.md`. **A/B runs pending on the eval machine** (keys + local log): `qwen3.7-flash_contracts_specialist_v{33,34}_extraction_sample5_chunked` pilots, then `_extraction_chunked_50` (seed 42, `--chunked`); site data regen + render audit follow the A/B + backfill there.
- **ContractEval GEPA iteration 5 → `contracteval_v5` (the fragment synthesis) + gpt-4.1-mini cost model (KANBAN-052)** — v5 = v4 + ONE surgical replace: the sentence-granularity tail ("otherwise quote the complete sentence(s), never a fragment of a sentence") deleted in favor of an explicit fragment permission — any contiguous run of the original text (sub-sentence fragment to several sentences), provided it contains every word of the complete answer and no more text than the answer needs, with every part of a multi-part answer included; the verbatim character-for-character rule (the TP engine) and the bounded trigger are untouched. Motivation (5-run A/B, identical 4,182 rows, qwen3.7-flash, temp 0): the smallest-span rule fired only at the extremes (100 FP→TN; J 0.06→1.0 wins) while 1,310/1,567 shared quotes stayed byte-identical to v3 — sentence-granular quoting is the Jaccard drag (v4 J 0.533 vs v2's 0.648); the 51 TP→FN losses are 19 partial multi-span rows + 29 wrong spans + 3 refusals. Paired-row projection on real rows: TP 815–840, J 0.62–0.645, F1 0.560–0.574, F2 0.612–0.628, false-nr ~0.035. New `openai/gpt-4.1-mini` cost model in `config/taxonomy.yaml` (input 0.4 / output 1.6 per M) for the research-funding cross-model runs. Site data regenerated (docs/data, 203 runs). Tests `test_contracteval_v5_derived_fragment_permission` (58 prompt tests green).
- **ContractEval v0 benchmark — qwen3-8b on a local vLLM (single RTX A5000), full 4,182-pair test set (KANBAN-052 cross-model data point)** — the directly-mirrored run COMPLETE on the node's local vLLM serving `models/Qwen3-8B` (`--served-model-name qwen3-8b`, `OPENROUTER_BASE_URL=http://localhost:8000/v1`, dummy key): **F1 0.5646 / F2 0.5313 / Jaccard 0.1454 / false-nr 0.1367 (paper 0.1367)**, 4,182/4,182 rows, 0 errors, temp 0, `contracteval_v0` prompt, input cap 129,000 chars (the 8 giant contracts > 129k chars get head+tail truncation; the other 94 stay faithful full-context), max_tokens 5000, concurrency 40, 25.8M tokens (23.98M prompt / 1.83M completion), `rows_with_usage` 2,681. Confusion TP 899 / TN 2305 / FP 769 / FN 345; accuracy 0.7654 / precision 0.6303 / recall 0.5113; per-category: Document Name F1 0.980 best, Agreement Date 0.925, Parties 0.828; zero-F1 categories are the sparse ones (Source Code Escrow 1 positive, Price Restrictions 0, Most Favored Nation 3, Affiliate License-Licensor 6). **Table III positioning vs the paper's 19-model table: F1 0.565 beats the paper's own qwen3-8b (0.530) and qwen3-8b-thinking (0.540) — our F1 #9 of 20; F2 0.531 #9; Jaccard 0.145 well below the paper's qwen3-8b 0.340 (Jaccard gap driven by over-quoting on positives — the known v0 bloat pattern, same root cause as the qwen3.7-flash v0 0.5058 → v1+ iterations).** The node-side `agents/base_agent.py` client timeout was raised 120→600 s for 40-way concurrency on the local server (the 120 s default timed out queued 30k-token requests — zero server-side errors; edit is node-local, not committed). New experiment-log record `qwen3-8b_contracteval_v0_contracteval_langfuse` (task `contracteval`, git `2f9d416` dirty); `reports/contracteval_benchmark.{md,json}` regenerated with the run in the Table III comparison + per-category breakdown; experiment log md + site data rebuilt (203 records).
- **Full ContractEval v0 benchmark — qwen3.7-flash on the 4,182-pair test set (KANBAN-052) + GEPA iteration 1 → `contracteval_v1`** — the directly-mirrored run COMPLETE: **F1 0.5541 / F2 0.6164 / Jaccard 0.5058 / false-nr 0.0289 (paper 0.0289)**, 4,182/4,182 rows, 0 errors, temp 0, faithful full-context, 42.7M+8.5M tokens, `cost_estimated_usd` 2.3868; confusion TP 829 / TN 2019 / FP 919 / FN 415. Table III positioning: F1 #4, F2 #3, **Jaccard #1 (tied gemini-2.5-pro 0.506)**, false-nr #2 — `scripts/reporting/run_contracteval_report.py` writes `reports/contracteval_benchmark.md` (pooled vs the 19-model table + per-category Fig-4 analogue). **GEPA iteration 1** (`contracteval_v1` in `src/prompts.py`, registered in `PROMPT_VERSIONS`, tests `test_contracteval_v1_derived_scope_discipline`): ONE lesson mined from the failure data — FP over-quoting (31.3% of 2,938 negatives; median 97 tokens; precision 0.474), Jaccard bloat on positives (425/829 TPs >2× GT, p90 20×; Agreement Date median 14.9×), 220 partial-overlap FNs = same selection fuzziness → **"Quote the smallest span of the Context that states the complete answer"** (append-derived; v0 byte-identical; "No related clause." contract untouched — false-nr stays at paper level). **Phoenix annotations**: `src/phoenix_tracing.py` now emits OpenInference `annotations.*` attributes (name/score/label correct|incorrect/`annotator_kind=CODE`) from every `score()` call (agent + document spans), plus `hide_input_text` on the OpenAI instrumentation (Goldilocks payload bound — the 300k-char contexts no longer balloon the local DB); the full v0 run's 4,282 spans backfilled post-hoc via the Phoenix client SDK (`contracteval` + `jaccard` CODE annotations). Runner: `sorter.agent_name` relabeled `contracteval` (plain-LLM carrier — trace/log inspection can no longer be mistaken for sorter classification).

### Added
- **ContractEval GEPA iterations 2–4 + first cross-model run — the 5-way funded A/B series (KANBAN-052)** — same 4,182-pair surface, qwen3.7-flash temp 0: **v1** (smallest-span lesson) F1 0.5406 / F2 0.5759 / Jaccard 0.6081 / false-nr 0.045 (TP 749 / FP 778 / FN 495, $2.19) — paired vs v0: FP→TN 190 held, but 118 v0-TPs lost (72 with v0 Jaccard ≥ 0.5); **v2** (trigger carve-out + complete-quote) F1 0.5349 / F2 0.5608 / **Jaccard 0.6479** / false-nr 0.0426 (TP 721 / FP 731 / FN 523, $2.18) — recovered only 27/118 refusals, reverted 56/190 FP fixes, +87 new FPs; **v3** (verbatim character-for-character + whole-sentence-when-doubt) F1 0.5550 / F2 0.6140 / Jaccard 0.5258 / false-nr 0.037 (TP 822 / FP 896 / FN 422, $2.33) — quote fidelity recovered 132 TPs but the doubt-bias re-bloated (paired J −0.095, +208 TN→FP). The 4-run oscillation (bloat ↔ fragment) diagnosed: verbatim quoting wins TPs, smallest-complete-span wins Jaccard — **v4 = v3 minus doubt-bias + v2's smallest-complete-span rule (quote VERBATIM and SMALL)**, projected F1 0.574–0.592 / J 0.634–0.640 (simulated on real paired rows). **Cross-model: `openai/gpt-4.1-mini` × `contracteval_v1` FULL surface COMPLETE: F1 0.6562 / F2 0.6675 / Jaccard 0.4674 / false-nr 0.0844 (TP 840 / TN 2462 / FP 476 / FN 404)** — beats the paper's own gpt-4.1-mini (0.644) and every qwen version on F1, but bloat pattern (lowest Jaccard of the series). All versions logged in `reports/contracteval_benchmark.md` via `run_contracteval_report.py --all`. New prompts `contracteval_v2/v3/v4` in `src/prompts.py` (append-derived, v0/v1 byte-identical, banners cite the run tables; tests `test_contracteval_v2_derived_trigger_carveout` / `..._v3_derived_quote_fidelity` / `..._v4_derived_verbatim_smallest_span`). GEPA iterations 2–4 via the prompt-engineer agent: iteration 2 mined 107/118 TP→FN as fragments not refusals; iteration 3 FALSIFIED the trigger-restoration hypothesis (149/160 lost TPs are re-typing/whitespace/case failures; 8-vs-268 refusal arithmetic); iteration 4 quantified the oscillation and the synthesis.

### Fixed
- **ContractEval runner debugged + Phoenix made a REAL trace sink (KANBAN-052)** — the directly-mirrored benchmark's run path fixed end-to-end: (1) **missing dependency** — `llm-dojo-scoring@v0.4.0` (the canonical `contracteval` evaluator) was pinned but not installed in the venv, so `run_langfuse_contracteval_eval.py` crashed at import (`ModuleNotFoundError`); `pip install -e .` re-pulls it. (2) **`src/phoenix_tracing.py` emitted NOTHING** — the handles were no-ops and no instrumentation was ever enabled; it now opens a REAL root OTel span per document (`trace_document`) with session/tags/filename/expected/metadata attributes, a nested agent span (`agent_observation`), records outputs + deterministic scores as span events (`set_output`/`score`), best-effort instruments the OpenAI SDK (`OpenAIInstrumentor`, already installed) so every LLM call lands as a nested span with full prompt/response/token usage, and `flush()` force-flushes instead of permanently shutting the provider down. (3) **runner fixes** — new `--tracing-backend {langfuse,phoenix}` flag (default `langfuse`) wired to `resolve_tracer(prefer=...)`; the paper's plain-call convention restored by killing the sorter's `_reasoning_effort="medium"` leak (thinking mode would have deviated from the mirror + burned tokens); manifest-resumed rows now re-derive classification/jaccard/said_no_related from the stored output instead of carrying stale zeros; pairs are dispatched **grouped by contract** (stable sort by title, id) so each contract's 41 calls share the identical full-context prefix — OpenRouter's automatic prompt cache serves the repeated prefix at ~10% of input price, a large saving on the 300k-char contexts with ZERO deviation from the paper's one-call-per-pair methodology. Tests: new `tests/test_phoenix_tracing.py` (4, network-free, fake in-memory tracer) + `test_runner_smoke_contracteval_phoenix_backend` (tracing_backend=phoenix record, contract-grouped dispatch order, no reasoning-effort leak) + `tests/test_tracing.py` fallback test made independent of the local `langfuse.env`; 23 surgical tests green. **Pilot (qwen3.7-flash, `contracteval_v0`, 100 pairs / seed 42, Phoenix sink, default key): F1 0.4578 / F2 0.5053 / Jaccard 0.3433 / false-nr 0.1143 (paper-denominator 0.0032)**, 100/100 rows OK, ~$0.07 — Phoenix verified holding 100 doc traces + 100 agent spans + 100 LLM spans with outputs, classification/jaccard scores and token usage; full 4,182-pair benchmark run initialized (manifest-resumable, `data/manifests/contracteval_qwen_benchmark_full.jsonl`).

### Added
- **Directly-mirrored ContractEval task — replicate the arXiv 2508.03080 benchmark as a first-class eval (KANBAN-052 / issue #22)** — build stage (run later): (1) **dataset builder** `scripts/datasets/build_contracteval_testset.py` — the CUAD **test split** (`theatticusproject/cuad-qa`, the exact `test.json` the HF loader downloads): 4,182 (contract, question) pairs / 102 contracts / 41 categories into `data/contracteval/contracteval_test.jsonl` (pairs, compact) + `contracteval_contracts.jsonl` (FULL 645–300,768-char contexts, stored once) + committed `questions.json` (41 category→question) + `testset_summary.json`; **positives = 1,244 = the paper's hardcoded false-rate denominator** (the paper reports 4,128 total — a 54-negative-row-smaller snapshot of the same file; the positive set is identical); (2) **versioned prompt `contracteval_v0`** = the paper's system prompt VERBATIM + `CONTRACTEVAL_USER_TEMPLATE` (Context:/Question:), registered in `PROMPT_VERSIONS` for the GEPA iteration loop; (3) **canonical ContractEval evaluator UPSTREAM in `llm-dojo-scoring` v0.4.0** (new `contracteval` task kind: `get_jaccard`/`said_no_related`/`contracteval_classified`/`contracteval_metrics` mirroring `Evaluation.py`+`open_source_model.py` exactly — verbatim-containment TP, F1/F2/acc/prec/recall, token-set Jaccard over positives, no-related rate, false-no-related rate over BOTH the run's positives and the paper's 1,244 denominator, per-category breakdown; 8 upstream tests; `src/contracteval.py` metric math reconciled to a thin shim); (4) **dedicated runner** `scripts/eval/run_langfuse_contracteval_eval.py` — faithful full-context (one call per pair, temp 0, max_tokens 5000, `--max-input-chars 0` = no cap), manifest resume, Langfuse/Phoenix traces (observation `contracteval` with classification + Jaccard scores), ONE append-only experiment-log record (`task: contracteval`, pooled + per-category scores, per-row outputs/labels/classification); (5) **report tooling** `scripts/reporting/run_contracteval_report.py` (offline) — our runs vs the full **19-model Table III** reference + per-category (Fig-4 analogue). Tests `tests/test_contracteval_task.py` (5, network-free: builder units + runner smoke with mocked LLM + report). Docs: AGENTS.md cheatsheet, README eval section, SCORING.md contracteval section, data/contracteval README + scripts README.
- **key_obligations scoring bottleneck fixed — disaggregation + category-presence routing + reasoning-trace retag (KANBAN-051 / issue #21)** — (1) **disaggregate clause spans before scoring** (`run_extraction_eval.py` now preprocesses `key_obligations`/`termination_clauses` through the upstream `disaggregate_clause_spans` before `score_extraction` + `score_category_presence`, so a merged multi-clause item no longer dilutes the 0.6 bipartite match below threshold — the stored `predicted` keeps the raw model output, with `disaggregated_counts` in the composite for audit); (2) **reasoning-trace RETAG** — new prompt `contracts_specialist_v33` = v32 + the RETAG RULE: obligation `reasoning.entries[].field` must be the canonical CUAD category name (the 32-category vocabulary enumerated; the `key_obbligations` misspelling explicitly guarded) instead of the umbrella `key_obligations`, fixing the misattribution where `category_presence_detail` evaluated generic obligations against categories like Anti-Assignment (measured on the stored v31/v32 corpus: 15,516 of 33,312 entries carry the umbrella tag); (3) **upstream `llm-dojo-scoring` v0.3.0** — `score_category_presence` routes each YES/NO category to the reasoning-trace entry tagged with the canonical category name (else to the disaggregated spans of its mapped field) and matches by token containment (≥ 0.7) or embedding similarity (≥ new `presence_embedding_threshold` 0.7); new `disaggregate_clause_spans` + `_split_clause_spans` helpers; upstream suite 144 passed, pushed + tagged `v0.3.0`; dep re-pinned in `pyproject.toml` + `requirements.txt`.
- **ContractEval mapping scorer — benchmark our previous runs against ContractEval Table III (arXiv 2508.03080, KANBAN-051)** — new `src/contracteval.py` + `scripts/reporting/run_contracteval_mapping.py` (offline, free): loads the full per-category clause spans from the committed `data/cuad/master_clauses.csv`, maps each disaggregated predicted span to the CUAD category it covers (reasoning-trace routing → verbatim label containment → best containment ≥ 0.5), synthesizes the per-category answer, and applies ContractEval's EXACT rubric (TP = every GT label span verbatim-contained in the answer; token-set Jaccard over positive pairs; false-"no related clause" rate). **Results on the full-corpus champion runs**: qwen3.7-flash v32 F1 0.164 / F2 0.109 / Jaccard 0.215 / false-nr 0.670 (v31 ≈ identical); llama-4-scout v31 F1 0.034 — far below ContractEval's GPT-4.1 (F1 0.641). The `coverage_bands` companion shows the gap is a **paraphrase penalty, not missing extraction**: the champion covers 42.7% of positive-label pairs at containment ≥ 0.7 vs 9.2% verbatim. Report `reports/contracteval_benchmark.md` + memo `memos/contracteval_mapping_benchmark.md`; tests `tests/test_contracteval.py` (network-free).
- **Monte Carlo simulations folded into the GEPA loop as a champion-contender selection layer + half-corpus effectiveness pilot (KANBAN-049, issue #17)** — `scripts/reporting/monte_carlo_gepa.py` adds a formal GEPA selection step: for every ordered prompt-version pair on a model, per-document deltas over the SHARED surface are paired-bootstrapped (n_boot 2000, seed 42) → mean Δ, 95% CI, P(A beats B); a version *beats* a peer when the CI excludes zero AND P(win) ≥ 0.9 (the noise-floor contract); the **MC champion contender** is the version with the most wins (tiebreak by aggregate accuracy), and a **plateau** verdict when no version beats any peer. The layer adds committee-voting robustness @ K for the contender and a **document-count sweep** (25/50/75/100%) for the effectiveness pilot (`--sample 0.5` = half-corpus pilot). **Pilot results (qwen3.7-flash):** subtype — full corpus selects `sorter_v15` (0.9506, tied with v13 at 7 wins, tiebreak by accuracy), the **seeded 50% sample (254 shared docs) recovers the same champion**, 25% (127 docs) collapses to plateau (P(win) 0.021, CI touches zero) → the sample-efficiency boundary sits between 25% and 50%; docclass — **plateau at every fraction** (v6-vs-v3 full-676 +0.0015, CI [+0.0000, +0.0044], P(win)=0.637 — the noise-floor gate correctly refuses to crown v6, matching the same-surface A/B verdict). Reports `reports/monte_carlo/gepa-champion-contender-{subtype,docclass}_classification[-sample50%].md`. Tests `tests/test_monte_carlo.py` grow to 14 (13 passed + 1 skip; new gepa scenario smoke + clear-winner selection test + the committed gepa report added to the reproducibility drift-guard). Memo `memos/monte_carlo_gepa.md`. Issue #17 closed.
- **Monte Carlo simulation suite — zero-spend what-if analysis over the joint reasoning corpus (KANBAN-048, ported per issue #17 from the RVL-CDIP-classifier's `monte_carlo_*` suite)** — `src/monte_carlo.py` (shared helpers: `normalize_dist`/`shannon_entropy`/`majority_margin`/`draw_committee`/`bootstrap`/`paired_delta_bootstrap`/`uncertainty_phrases`/`confidence_score`/`save_figure`/`style_axis`, per-task label vocabularies from `agents/sorter_agent.py`, free-form-reasoning near-miss detection); `scripts/reporting/monte_carlo_corpus.py` builds the joint corpus (`reports/monte_carlo/corpus.jsonl`, gitignored — 17,691 rows: 16,162 subtype + 1,442 docclass + 80 chained + 7 sorter, 99.7% with reasoning) + `corpus-summary.md`; `monte_carlo_ensemble.py` — committee accuracy(K) with bootstrap CIs (subtype 0.9209 → 0.9513 @ K=25; doc_type saturated at 0.9928) + confidence blend + escalation Pareto (subtype +0.44 pp @ alpha 0.15 to a 0.95 model; docclass escalation loses — baseline already 0.9928) + `escalation_candidates-<task>.txt`; `monte_carlo_prompt_ablation.py` — paired-bootstrap gate over 156 subtype + 12 docclass (model, A, B) pairs on shared docs (sorter_v10/v11 vs v3 +14.1 pp P(win)=1.000; docclass v5 loses to v3/v4/v6 on the diag-30 slice); `monte_carlo_failures.py` — retry/fallback event simulation from the observed 0.2374% failure rate (max_tries=1 + fallback → 0.004%, without → 0.202%), 1K/25K/320K extrapolation with tail risk; `monte_carlo_exemplars.py` — confusion-pair near-miss mining (268 maintenance→license / 212 development→license traces) + Monte Carlo subset selection under a token budget → 6 subtype + 4 docclass exemplar appendices; `monte_carlo_verify.py` — spend-minimal verification recipe printing the exact eval commands (dry-run default; `--run-eval` is the only spend). Memo `memos/monte_carlo_robustness.md`; tests `tests/test_monte_carlo.py` (12, network-free: helper units + per-scenario smokes on a synthetic corpus + committed-output reproducibility). No model spend.
- **Full Phoenix local trace sink documentation + cost-efficiency configuration cemented (KANBAN-046 / issue #18)** — new `wiki/Phoenix-Tracing.md` (linked from `wiki/Home.md` + `_Sidebar.md`) documenting the local Arize Phoenix trace sink (Langfuse-primary resolution with Phoenix fallback via `src/tracing.py::resolve_tracer`, OTLP HTTP spans, SQLite store, discard-by-delete) and the **resume / checkpoint / queue / cache** cost-efficiency configuration: manifest resume + header contract (`src/evaluation.py::ManifestStore` — never resume a stale manifest), append-only experiment-log checkpoint, HITL annotation queue (`run_annotation_queue.py`), embedding-cache reuse + manifest-replayed-rows usage accounting, and the `--dry-run` / `assert_production_run` / `--research-funding-key` cost gates. `config/environments/.env.example` gains the documented Phoenix section (`PHOENIX_TRACING`, `PHOENIX_ENDPOINT`, `PHOENIX_SERVICE_NAME`, `PHOENIX_PROJECT`, `PHOENIX_SESSION`, `LANGCHAIN_TRACING_V2`, `OTEL_EXPORTER_OTLP_ENDPOINT`); the AGENTS.md tracing section points at the wiki; drift-guard test `test_env_example_documents_phoenix_sink` in `tests/test_env_utils.py` pins the template surface.
- **llm-dojo-scoring v0.2.0 — task-aware scoring across the additional document hierarchy (KANBAN-047 / issue #19)** — upstream package extended and re-pinned (`llm-dojo-scoring @ git+…@v0.2.0` in `pyproject.toml` + `requirements.txt`): new `llm_dojo_scoring.tasks` module with a `score_task()` dispatcher + task-aware normalization covering **MAUD** (merger-agreement doc-class + consideration-type subclass with strict/equiv scoring, per-question classification), **LegalBench** (binary Yes/No exact-match + per-class + binary P/R/F1), **multi-classification** (macro/micro + confusion), **court opinions** (court_opinion doc-class), and **chained evaluation runs** (`chained_composite` / `chained_summary`, sorter+extractor weighted 0.25/0.75); `config.py` gains the task registries (`DOC_CLASS_KEYS`, `MAUD_CONSIDERATION_*`, `LEGALBENCH_BINARY_LABELS`, `COURT_OPINION_CLASS`, `TASK_KINDS`); 10 new network-free tests (upstream suite 144 passed; pushed + tagged `v0.2.0`); README task-coverage section.
- **Full EDA suites on the new pipeline sources (KANBAN-045)** — `scripts/eda/explore_pipeline_sources.py` (reproducible, `--source all|maud|s1|docclass|legalbench`, `--no-figures`) writes per-source `data/eda/<source>/{report.md, findings.md, figures/}` for every post-CUAD source integrated into the pipeline: **MAUD** (152 merger agreements, 54.1M chars, median 338k chars — **all 152 over the 90k chunk window**; consideration-type GT all_cash 57 / other 57 / all_stock 24 / mixed_cash_stock 13 / mixed_cash_stock_election 1; the 25,827-row per-question suite across 22 families / 7 categories, MAE definition 8,548 rows largest), **EDGAR S-1 corporate records** (15 exhibits, EX-3.1×4 / EX-3.2×3 / EX-4.x, content-detected subclasses articles_of_incorporation 8 / rights_instrument 6 / bylaws 1, 3 CIKs), **merged doc-class surface** (676 = CUAD 509 + MAUD 152 + S-1 15; doc_type contract 75.3% / merger_agreement 22.5% / corporate_record 2.2%; GT-`other` gap cluster 57 rows + subclass-None 509 — the quantified driver of the full-676 subclass misses), and **LegalBench** (hearsay train 5 / test 94 + 10 CUAD subtask 6-row controlled surfaces with answer balance + slices). Reports regenerate byte-identically — the reproducibility contract is pinned by `tests/test_pipeline_sources_eda.py` (3 tests, network-free, skips when the gitignored corpus dumps are absent). No LLM calls (plan-free).
- **llm-dojo-scoring integration completed (KANBAN-044)** — scoring/error-analysis/export code now lives in the pinned `llm-dojo-scoring` package (`@v0.1.2`) shared with llm-mailroom: `src/dojo_config.py` maps `config/taxonomy.yaml` → package `Settings` (embedding_enabled, `cost_models` dict→list conversion, `load_env()` first, and the `ambiguous_band`→tuple / `partial_gt_fields`/`containment_fields`→set coercion the package's verbatim `configure()` otherwise skips); `src/dojo_compat.py` (`classify_failure` None-on-ok); the 6 local scoring modules (`field_scoring`/`metrics`/`scorers`/`bootstrap`/`cost_models`/`experiment_log` core) become thin re-export shims so llm-mailroom's `pip install -e .` imports keep working unchanged; `export_experiment_results.py` re-exports `llm_dojo_scoring.export`; `export_sweep_results.py` stays local (reference-format Notes contract, KANBAN-040); the `dojo-analyze`/`dojo-export`/`dojo-sync` CLIs are verified against the repo's workbook artifacts. Upstream fix shipped: the external `cli.py` had no `python -m` entry dispatch (module import no-op'd) — fixed, pushed, tagged `v0.1.1`→`v0.1.2` (`29c192f`→`3ad2ef4`→`1f291ba`), dep re-pinned. Memo `memos/llm_dojo_scoring_integration.md`.
- **Champion-sweep extension — llama-4-scout + gpt-4o-mini on sorter_v13, full-509 (KANBAN-043)** — two funded full-corpus subtype evals (`run_langfuse_subtype_eval.py`, reasoning medium, temp 0.1, seed 42, `--research-funding-key`, Langfuse-primary tracing; manifests `data/manifests/{llama4scout,gpt4omini}_sorter_v13_509.jsonl`): **`meta-llama/llama-4-scout` subtype 0.8880 (equiv 0.9077, bootstrap CI [0.8605, 0.9136], 57 fails)** and **`openai/gpt-4o-mini` subtype 0.9312 (equiv 0.9352, exact 0.9961, CI [0.9096, 0.9528], 35 fails)** — both 509/509, full failure reasoning + per_subtype. The sweep table (KANBAN-036) and workbook absorb both; experiment-log md regenerated (195 records).
- **Full results deck exporter — extraction lineage + sorter sweep + LegalBench as one Google-Slides deck (KANBAN-040 follow-on)** — `scripts/reporting/export_full_results_deck.py` builds `reports/sheets/extraction_sweep_legalbench_full_deck.xlsx` (19 × 16:9 "slides", landscape fit-to-page, dark banner + footer, reusing the slide styling from `export_slides_deck.py`): **Part A — extraction** (all 61 collected contracts-specialist/extraction records chronological with overall / field-presence / schema-valid / verified-precision / tokens / est. cost, champion v32 `510_full_clean` detail — metadata, headlines, per-field, error decomposition, entity lists, MAE/R² diagnostics — and the full extraction codebook), **Part B — sorter sweep** (all 22 `sorter_v13` subtype runs across 8 models with strict/equiv/exact/fails/CI + champion detail with failure modes and the 25-subtype codebook), **Part C — LegalBench** (all 56 performance records grouped task_v0/v1/v2 hearsay + task_v3/v4 contract families with n / exact / bootstrap CI / per-class accuracy / tokens / cost, a per-task results summary — hearsay lineage v0 0.7766 → v1 0.8617 → v2 0.8830 on the same 94-row test — and a task legend). Data read live from `reports/experiment_log.jsonl` + `config/taxonomy.yaml` + `agents/sorter_agent.py` (no network, no LLM); tests `tests/test_full_results_deck.py` (4, network-free: slide structure/banner/footer, lineage rows, sweep rows, LegalBench logs + summary).
- **Sorter model-sweep completion — gpt-4.1-nano full-509 resumed to completion (KANBAN-036)** — the partial `openai/gpt-4.1-nano` run on the champion `sorter_v13` prompt (332/509 rows cached in `data/manifests/gpt41nano_sorter_v13_509.jsonl`, no experiment-log record) resumed via manifest (`--manifest`, Phoenix sink matching the checkpoint header, `--research-funding-key`, temp 0.1, reasoning medium, seed 42) and polled to completion: **subtype 0.8605 (bootstrap 95% CI [0.8291, 0.8900]), equiv 0.8782, exact 0.9666, confidence 0.9432, 71 fails (36 family_confusion / 17 function_over_form / 9 equivalent_family / 9 other_fallback)** — the lowest exact-match of the full-509 sweep (0.9666; the 17 function_over_form + 9 other_fallback misses vs 2/1 for gpt-4o-mini). Tokens recorded 2.25M (manifest-replayed rows carry no usage — only the 177 newly-run rows count; extrapolated full-509 ≈ 6.48M ≈ **$0.66 est. at $0.10/$0.40 per M**). LangSmith 429 trace-limit noise non-fatal (known tenant monthly limit). Sweep workbook regenerated → `reports/sheets/Sorter_Model_Sweep_Results.xlsx` (9 rows, gpt-4.1-nano row added) + copied to `~/Downloads`; experiment-log md regenerated (185 records).
- **Docclass scoring depth — the new classes/subclasses scored equally deep (KANBAN-033)** — `run_langfuse_docclass_eval.py` metrics now mirror the subtype surface's richness: **bootstrap 95% CIs on every headline** (`doc_type_accuracy_ci` / `subclass_accuracy_ci` / `exact_match_ci`, percentile-bootstrap via `src/bootstrap.py`), **per-subclass accuracy tables with support counts** (`per_subclass_accuracy` + `per_subclass_support` — e.g. full-676: all_cash 0.877/57, all_stock 0.917/24, articles_of_incorporation 0.5/8, other 0.0/57), **equivalence-aware subclass scoring** (`subclass_accuracy_equiv` + `equiv_recovered` — `DOC_SUBCLASS_EQUIVALENCES` in `agents/sorter_agent.py`: mixed_cash_stock ↔ mixed_cash_stock_election, dimension-scoped; per-document `subclass_ok_equiv` + `handle.score("subclass_accuracy_equiv")`), and **input-mode split counts** (`input_mode_counts` — text/vision/text_fallback). The experiment-log renderer gains a docclass branch: per-document tables now show doc_subclass / expected subclass / subclass ok equiv / input mode (the second-level dimension was previously invisible), plus a "Per-subclass accuracy (second-level dimension)" section. Records also carry `results` (the shared renderer contract) alongside `per_row`. Tests: `test_equivalent_doc_subclasses_family_reads`, smoke assertions for CIs/per-subclass/equiv/rendering.
- **Docclass sorter iteration round 2 — v4/v5/v6 from the full-676 failure set (KANBAN-033)** — the full-corpus failures decomposed into 3 mechanisms: (C1) M&A-package machinery misread as standalone ancillary instruments (contract_2 full APM-with-CVRs, contract_33 TRANSACTION AGREEMENT → contract/other; rule-35 over-fire), (C2) agreement-package composition (FEDERATED EX-99 services agreement opening with a LIMITED POWER OF ATTORNEY → corporate_record), (C3) GT/text artifacts (UNITEDNATIONAL press-release-only text, OLDAPI certificate-only text — NOT prompt-fixable, flagged data-side). Candidates: `sorter_docclass_v4` (rule 36 M&A package machinery), `sorter_docclass_v5` (rule 37 agreement packages), `sorter_docclass_v6` (rule 36 SHARPENED: rule-31 title list declared illustrative + multi-agreement files governed by the primary agreement — from contract_33's v4 reasoning, which showed the model second-guessing rule 31's enumeration). **Diagnostic-surface A/B (30 rows, fp 946ac1c4): all deltas inside the bootstrap CIs** (v3 exact [0.40, 0.73] vs v4 [0.43, 0.77] vs v5 [0.40, 0.73]) — the targeted rows are high-variance; v4 recovered contract_2 deterministically (2/2), v5 showed no replicated signal (dropped). **Full-676 A/B with noise control (fp 5602b71f, qwen3.7-flash, temp 0.1): the v3 identical-prompt rerun reproduced the exact headline (0.8905 = 0.8905 — the merged surface's aggregate noise floor ≈ 0.000); v6 = 0.8935 (+0.0030), doc_type 0.9941 (5→4 misses), subclass 0.5868 (+1.19pp, all_cash 0.877→0.912), 2 rows fully recovered (contract_62 — the embedded-bylaws rule-34 target that still failed at scale — and contract_71 consideration read), 0 regressions, same cost → **v6 strictly dominates v3 and is promoted as the docclass text champion**. Residual: contract_33 persists (the model hallucinates an RRA title on the truncated 1MB doc — truncation/model-bound, documented). Runs: `qwen3.7-flash_sorter_docclass_{v4,v5}_docclass_diag30b`, `qwen3.7-flash_sorter_docclass_v3_docclass_full676c` (noise control), `qwen3.7-flash_sorter_docclass_v6_docclass_full676`; memo `memos/docclass_v6.md`.
- **Sorter model-sweep expansion — deepseek-v4-pro + llama-3.3-70b-instruct on the champion sorter_v13 prompt, full-509, research-funding key (KANBAN-042)** — two funded full-corpus subtype evals (`run_langfuse_subtype_eval.py`, reasoning medium, temp 0.1, seed 42, 509 rows, `--research-funding-key`, Langfuse-primary tracing, manifests `data/manifests/{dsv4pro,llama3370b}_sorter_v13_509.jsonl`): **`deepseek-v4-pro_sorter_v13_subtype_langfuse` — subtype 0.9528 (CI [0.9332, 0.9705]), exact 0.9961, equiv 0.9548, 24 fails (18 family_confusion / 3 other_fallback / 2 function_over_form / 1 equivalent_family), 6.97M tokens ≈ $3.15 est.** — the highest subtype accuracy in the sorter_v13 sweep to date (vs qwen champion 0.9430); cross-model significance NOT claimed (the ±0.006 band was measured on identical-prompt qwen reruns — descriptive only). **`meta-llama-llama-3.3-70b-instruct_sorter_v13_subtype_langfuse` — subtype 0.8782 (CI [0.8487, 0.9057]), exact 0.9941, equiv 0.8998, 62 fails (47 family_confusion / 11 equivalent_family / 3 function_over_form / 1 other_fallback), 6.66M tokens, est. cost None (OpenRouter-billed, no local price)**. Both `n_ok=509`, full failure reasoning + per_subtype present; LangSmith 429 trace-limit noise non-fatal (known tenant monthly limit). **Sweep workbook regenerated** → `reports/sheets/Sorter_Model_Sweep_Results.xlsx` (8 rows, Notes added for both runs) + copied to `~/Downloads`; **deck slide 16 updated** (llama sorter run table vs qwen champion + deepseek-v4-pro; the "no llama sorter runs" note superseded — llama-3.3-70b sorter run now traced to Langfuse llm-dojo) + deck recopied to `~/Downloads`; experiment-log md regenerated (178 records).
- **Slides deck regenerated — qwen sorter lineage v3→v13 + llama runs included (KANBAN-041)** — the slides-style xlsx deck grows 16 → **19 slides**: Part B gains (14) **Qwen lineage summary v3→v13** (best full-surface run per version: v5 0.8585 → v6 0.9312 → v8 0.9018 → v9 0.9175 → v12 0.9293 → v13 0.9430@509; 243/195/50-doc surfaces flagged non-comparable), (15) **all 30 qwen v3→v13 runs** (two-column chronological table incl. degraded rows: v11 first run 0.0000, v13 first run 0.7741 — kept for truthfulness), (16) **Llama runs (Langfuse)** — the ONLY llama run recorded anywhere: **llama-4-scout × contracts_specialist_v31 extraction** (Langfuse llm-dojo, 509 traces / 20 scored, truncated; overall 0.6627 vs qwen v31 0.8737 — n=20, NOT comparable, labeled signal only). Provenance: fetched via langfuse-cli (`langfuse.env` keys, model-contains-llama + session filters); record saved to `reports/sheets/llama4scout_v31_extraction_langfuse.json` (loaded via `--llama-json`, absent → embedded defaults). **No llama SORTER-task runs exist** — verified across the experiment log (0 hits), Langfuse llm-dojo (model+session filters), Braintrust (experiment reads 403 Forbidden), LangSmith (`LANGSMITH_PROJECT=HEARSAY` only); the slide states this explicitly. Lineage slides use a NEW raw-list loader (`load_records_list`) — the deduped name→record index dropped same-name reruns (v3 ×4, v6 ×3, v9 ×4, v13 ×2). Codebooks renumbered 17–18, docclass 19; deck copied to `~/Downloads` per user pattern.
- **Sorter model-sweep workbook — every model on the champion prompt, reference-format xlsx (KANBAN-040)** — `scripts/reporting/export_sweep_results.py` builds `reports/sheets/Sorter_Model_Sweep_Results.xlsx` in the EXACT reference format of `Sorter_Experiment_Results.xlsx` (114 columns + a trailing `Notes` column; `Eval Results` + `Codebook` sheets; 1F4E79 header, mm/dd/yyyy dates, 0.00% percentages, freeze F2, autofilter) by filtering `subtype_classification` runs to the champion prompt (default `sorter_v13`, `--prompt` overridable). **6 rows, chronological**: the DEGRADED first v13 qwen run (93 connection errors, superseded), the clean **champion rerun (qwen3.7-flash 0.9430)** — the comparison baseline, **gpt-5-nano 0.8978** (KANBAN-035 cost-floor arm, −4.5pp), deepseek-v4-flash + gpt-4.1-nano 1-doc smokes, and **deepseek-v4-flash 0.9253 full-509** (KANBAN-036). Column spec + styling + compact codebook reused verbatim from `export_experiment_results.py` (114 shared headers byte-identical to the reference; per-subtype strict/equiv accuracy + cell sizes, failure-mode counts, tokens/cost, params all populate from the log records). `Notes` column flags champion/degraded/smoke/benchmark per row. Tests `tests/test_export_sweep_results.py` (4 tests, network-free: prompt/task filter + chronology, note fallbacks incl. degraded detection, workbook structure incl. 115-col + codebook contract).
- **Slides-style xlsx deck export — latest contract-specialist + sorter results with full codebooks (KANBAN-039)** — `scripts/reporting/export_slides_deck.py` builds ONE Google-Slides-formatted workbook (`reports/sheets/contract_specialist_v32_and_sorter_v14_deck.xlsx`, 16 sheets, every sheet a 16:9 slide: landscape fit-to-page, dark title banner + footer, stat-card callouts, colored tables) from `reports/experiment_log.jsonl` + `config/taxonomy.yaml` + `agents/sorter_agent.py` (no network, no LLM, repeatable via `--log/--taxonomy/--outdir/--outfile`). **Part A — contracts specialist v32** (`qwen3.7-flash_contracts_specialist_v32_extraction_langfuse_510_full_clean`, 2026-08-16): metadata/params/dataset/git/tokens ($0.49 est.), headline scores (overall **0.8807** CI [0.8689, 0.8913], field_presence 0.9701, schema_valid 1.0, verified_precision 0.9799) + v31 comparison (+0.0070; memo verdict: logic repair inside the ±0.011 band), per-field table (8 fields × score/verified precision/hallucination), exact/partial/miss decomposition, entity-list coverage-F1 vs raw P/R/F1 (partial-GT caveat), MAE/R² diagnostics (date 34.2d R²0.982 n=413; duration 423.9d R²0.731 n=148; span-count MAE 5.35 signed +5.03 n=1129) + **full extraction codebook** (9 fields + types + scoring class, partial-GT/containment/factuality/ambiguous-band rubric). **Part B — sorter v14** (`qwen3.7-flash_sorter_v14_subtype_langfuse`): headlines (exact 0.9961, subtype 0.9371 CI [0.9155, 0.9568], equiv 0.9411) + v13 A/B note (Δ −0.0059 inside band, v13 stays champion), failure-mode breakdown (32: 27 family_confusion / 2 equivalent_family / 2 function_over_form / 1 other_fallback) + top-confidence failure examples with reasoning, per-subtype strict/equiv accuracy (derived from the 509 row-level results; development 0.750 worst, 10 families at 1.000) + **full sorter codebook** (25 CUAD subtypes with labels + definitions, 4 equivalence families, failure-mode taxonomy, scoring rules). **Part C — docclass v5 diag-30 bonus** (doc_type 0.8333 / subclass 0.5263 n=19 / exact 0.5667, per-class + per-subclass tables, failure modes 5 doc_type_miss / 8 subclass_miss) + sources & navigation slide. Script verified by reloading the workbook (16 slides, landscape/fit-to-page, spot-checked values cross-match the log records).
- **Posit Cloud integrated portal — Quarto site `site/` → `docs/posit/`, complementary to the SPA (KANBAN-037)** — a fully themed, fully integrated Quarto website bringing the **experiment log**, the **agent kanban board**, and the **discussion board** together at one URL prefix under `docs/` (the same tree GH Pages serves — zero Actions; Pages deploys from branch, Posit Cloud deployment is `quarto render site` + publish). **Pages**: portal landing with live stat counters + latest runs (`site/index.qmd`), `experiment-log.html` (generated from `reports/experiment_log.jsonl` on every render by `site/_pre-render.py` using the SAME `src/experiment_log.py::render_full_log` renderer as `reports/experiment_log.md` — full run index + per-run metadata/scores/tokens/diagnostics with per-run deep links into the SPA explorer `../index.html#/run/{n}`), `kanban.html` (`board/MESSAGE_BOARD.md` live copy), `discussion.html` (`MESSAGE_BOARD_DISCUSSION.qmd` live copy, agent colors preserved) — plus portal↔explorer navbar links in both directions. **Theme**: custom blue→teal gradient identity match to the SPA favicon (bootswatch cosmo light / darkly "gradient night" dark, light/dark toggle, navbar, TOC, client-side search). **Hygiene**: `_pre-render.py` hook regenerates `_includes/` + `_variables.yml` before every render (gitignored — they carry generation stamps); rendered output `docs/posit/` IS committed so GH Pages serves it with no build step; `.gitignore` gains a Quarto/Posit section (`.quarto/`, `site/_includes/`, `site/_variables.yml`, `rsconnect/`, RStudio/renv local artifacts, standalone board renders). **Repairs en route**: 6 discussion-board entries were missing their `:::` closing fences (pre-existing — pandoc swallowed them into nested divs) — closers added, entry bodies byte-identical (append-only preserved), balance pinned by test; `board/MESSAGE_BOARD.md` card-number collision resolved (KANBAN-037/038). Tests `tests/test_posit_site.py` (9 tests, network-free: pre-render output, `_quarto.yml` contract, committed pages, source-div balance, and a skip-if-no-quarto determinism check that a fresh render leaves `docs/` byte-identical). Docs: `site/README.md` (new), `docs/README.md`, `README.md`, `wiki/Site.md`.
- **Docclass sorter prompt COMPLETED + QWEN 3.7-flash benchmark on the merged docclass task (KANBAN-033)** — (1) **Prompt iteration closed**: `sorter_docclass_v1` (rule 34, embedded-records scope guard) + `sorter_docclass_v2` (rule 35, RRA-exhibit convention) from the pilot's 3 failure mechanisms, then **`sorter_docclass_v3` = the Phase 3.5 MERGE (v0 + rules 34 AND 35)** as the completed docclass sorter prompt. Same-surface A/B (stratified-30, seed 42, fp `d3d7b335…`, qwen3.7-flash, temp 0.1): **v3 exact 0.8000 / doc_type 1.0000 — recovers all 5 EX-4.x instrument doc_type misses (RRAs + warrants), failure set byte-identical to v2 (the 6 remaining = 3 MAUD consideration-GT gaps + 3 S-1 streamer-detection artifacts, NOT prompt-fixable), zero regressions from the merge**. (2) **Merged docclass corpus = ONE dataset**: `scripts/datasets/build_docclass_merged.py` → `data/datasets/docclass_merged.jsonl` = 509 CUAD contracts + 152 MAUD merger agreements + 15 S-1 corporate records (**676 rows**, fp `5602b71f…`, deterministic ordering, reproducible fingerprint); `sync_langfuse_datasets.py --docclass` mirrors it as ONE Langfuse dataset `mailroom-docclass` (676 items upserted, llm-dojo); all docclass prompts (v0..v3 + vision) synced to Langfuse. (3) **QWEN 3.7-flash benchmark on the merged task**: **doc_type 0.9926 / subclass 0.5808 / exact 0.8905, 0 errors, ≈$0.47** — the established baseline for the merged surface (5 doc_type misses; **56/69 subclass misses are the MAUD GT-gap cluster** — GT "other" fallback where the model reads an explicit consideration — plus 4 S-1 GT artifacts and ~13 genuine consideration near-misses). (4) **Vision-primary mode with text fallback** (the added-complexity arm): `sorter_docclass_vision_v0` prompt (vision twin of v3, 7 classes + rules 31–35 + `<subclass>` tag + UNREADABLE sentinel), `SorterAgent` vision parse extended to the docclass schema (7-class validation, subclass normalization, strict 6-class backward compatibility), runner `--input-mode text|vision|vision-primary` + `--pdf-dir` + `--vision-pages all|first` with per-row input_mode/fallback_reason accounting; pilot `..._docclass_vpilot` (8 rows: 5 vision + 3 no-PDF text-fallback, all correct, ≈$0.005). Memo `memos/docclass_v3_merged_benchmark.md`.
- **MAUD + EDGAR S-1 corporate-record wiring + hierarchical doc-class sorter eval task (KANBAN-033)** — (1) **MAUD as a utilized dataset**: `scripts/datasets/stream_maud_to_bt.py` (Zenodo `maud_v1.zip` / HF `theatticusproject/maud` mirror, CC BY 4.0) streams the 152 merger agreements (54 MB text) into `mailroom-maud-contracts` with GT `doc_type: merger_agreement` + a **consideration-type subclass** read from MAUD's own expert GT ("Type of Consideration": all_cash 57 / all_stock 24 / mixed_cash_stock 13 / mixed_cash_stock_election 2, rest other — train-CSV coverage note) and the 25,827-row per-question suite into `mailroom-maud-classification` (22 question families / 7 categories as metadata); `--local-dump` JSONL is the reliable eval path while Braintrust row uploads are org-capped, and `sync_langfuse_datasets.py --maud` mirrors the dumps into Langfuse datasets (25,994 items dry-run). (2) **New primary sorter class `merger_agreement`** behind `SORTER_DOCCLASS_PROMPT_V0` (= v14 + rules 31–33: merger-agreement class, SEC-exhibit corporate records stay corporate_record, doc_subclass dimension) + `DOCCLASS_SCHEMA` (7-class enum + nullable `doc_subclass`); the shared 6-class surface (v0..v14, `SORTER_SCHEMA`) is untouched — the extended classes/schema are opt-in `SorterAgent(doc_classes=, schema=)` params, with `normalize_doc_subclass()` enforcing per-class subclass dimensions (wrong-dimension values → other). (3) **New eval task `scripts/eval/run_langfuse_docclass_eval.py`**: one sorter call per document over a mixed surface (MAUD + CUAD + S-1 corporate records, Braintrust datasets or `--local-dumps`), scoring doc_type_accuracy + subclass_accuracy (rows without subclass GT unscored) + exact_match + confidence, per-class accuracy, subclass confusion, failure insights (doc_type_miss / subclass_miss); Phoenix/Langfuse sink, manifest resume, experiment-log record (`task: docclass_classification`). (4) **EDGAR S-1 corporate-record exhibits**: `scripts/datasets/stream_s1_exhibits.py` (SEC full-text search → filing index → text extraction; SEC fair-access throttle + 403/429 backoff; content-detected record_type subclass: bylaws / articles_of_incorporation / certificate_of_formation / powers_of_attorney / ...; exhibit code stays as metadata) → `mailroom-s1-corporate-records` (15-doc live collection pilot). **Tertiary class level DROPPED per human directive (only where the data necessitates it)** — MAUD categories and EDGAR exhibit codes are dataset metadata, not classification dimensions; subclass (consideration type / record type) is the data-necessitated second level. Taxonomy (`config/taxonomy.yaml`) gains `merger_agreement` + subclass enums for merger_agreement/corporate_record (no tertiary_classes anywhere — pinned by test). Live pilot `qwen3.7-flash_sorter_docclass_v0_docclass_pilot` (5 docs, seed 42): doc_type 0.6 / subclass 0.4, valid schema output, first confusion signals (EX-4.4 registration-rights agreement → contract; merger agreement → corporate_record/bylaws). Tests: `test_stream_maud.py`, `test_stream_s1.py`, `test_docclass_eval_smoke.py`, sorter-agent + prompt option-list == schema-enum tests.
- **Externally-funded OpenRouter key behind a production-only flag (KANBAN-034)** — `RESEARCH_FUNDING_OPENROUTER_API_KEY` in `.env` (external research funding) is reachable ONLY via `--research-funding-key` on the eval runners; the default `OPENROUTER_API_KEY` is untouched. `src/env_utils.py` gains `resolve_openrouter_key()` + `assert_production_run()` + `add_research_funding_flag()`: the gate HARD-REFUSES dry-runs and pilot-scale samples (fewer than 100 rows, or less than the full dataset when smaller) with a `SystemExit` before any LLM call, and prints a funding banner on accepted runs. Wired into all 10 `run_*_eval.py` / `run_langfuse_*_eval.py` runners (subtype, extraction, chained, classification, multiclass, binary) + `judge_experiment.py` untouched (stays on the default key). `.env.example` documents the variable; `tests/test_env_utils.py` covers resolution, the gate, and a runner-level refusal smoke test.
- **GPT cheapest-model benchmark on the sorter subtype surface — gpt-5-nano vs champion (KANBAN-035)** — full-509 subtype eval (`mailroom-cuad-contracts-full`, sorter_v13 champion prompt, reasoning medium, temp 0.1, Phoenix sink, 0 errors) with **`openai/gpt-5-nano`** — the smallest & cheapest GPT on OpenRouter ($0.05/M prompt + $0.40/M completion, 400k ctx). **gpt-5-nano strict 0.8978 (CI [0.8703, 0.9234]) vs the qwen3.7-flash champion 0.9430 = −4.5pp — far outside the ±0.006 noise band → nano does NOT match the champion; cost-floor frontier arm only** (equiv 0.9018, doc_type 0.9941; 52 fails: 41 family_confusion / 6 other_fallback / 3 function_over_form / 2 equivalent_family). 6.94M tokens ≈ **$0.48** for the full 509-doc run (recorded cost_usd 0.0 — gpt-5-nano absent from the local cost table; billed via OpenRouter). LangSmith ingest 429s (tenant monthly unique-traces limit) — non-fatal, traces skipped, scoring unaffected. Run `gpt-5-nano_sorter_v13_subtype_langfuse`; manifest `data/manifests/gpt5nano_sorter_v13_509.jsonl`; paid with `--research-funding-key` per human directive.
- **DeepSeek + GPT cheap-model sorter sweep — deepseek-v4-flash + gpt-4.1-nano on sorter_v13 (KANBAN-036)** — two more full-509 subtype evals on the champion `sorter_v13` prompt (reasoning medium, temp 0.1, Phoenix sink, 0 errors, `--research-funding-key`, manifests `data/manifests/{deepseekv4flash,gpt41nano}_sorter_v13_509.jsonl`), completing the cheap-model frontier around the qwen3.7-flash champion (0.9430): **`deepseek/deepseek-v4-flash` strict 0.9332 / equiv 0.9352 (34 fails: 27 family_confusion / 5 other_fallback / 1 equivalent_family / 1 function_over_form) — the standout cheap model, within −0.98pp of the champion** (6.91M tokens ≈ $0.39 est.); **`openai/gpt-4.1-nano` strict 0.8782 / equiv 0.8959 (62 fails: 35 family_confusion / 11 function_over_form / 9 equivalent_family / 7 other_fallback) — below gpt-5-nano (0.8978), a cost-floor frontier arm only** (6.65M tokens). Both runs clean 509/509. Runs `deepseek-v4-flash_sorter_v13_subtype_langfuse` + `gpt-4.1-nano_sorter_v13_subtype_langfuse`; Phoenix trace sink persisted to `.phoenix/` (gitignored, `f84556f`).
- **llama-4-scout × contracts_specialist_v31 extraction — cheap model collapses on structured extraction** — full-509 chunked extraction eval on the champion prompt `contracts_specialist_v31` (90k/8k windows, temp 0.1, reasoning none, `--research-funding-key`, manifest `data/manifests/llama4scout_v31_510_chunked_full.jsonl`) with **`meta-llama/llama-4-scout`**: **overall 0.6968 vs the qwen3.7-flash champion 0.8737 = −17.7pp** (509/509, 0 errors, 10.34M tokens). The model is classification-capable (0.888 on the sorter) but collapses on structured extraction: **key_obligations recall 0.259 / exact 0.048** (span-count signed mean −4.06 → under-extraction), **term_length exact 0.078** (date MAE 1,643 days, R² −4.04 → containment collapse), renewal_terms exact 0.292, termination_clauses exact 0.714. Verdict: cost-floor arm only — does NOT approach the champion on extraction. Run `llama-4-scout_contracts_specialist_v31_extraction_langfuse`.

- **Modal-hosted vLLM serving capability + call-time provider-seam repair (KANBAN-096, [#50](https://github.com/Exios66/llm-entity-extraction/issues/50), human directive 2026-08-24):** `deploy/modal_vllm.py` deploys any HF-hosted model behind a bearer-authenticated OpenAI-compatible `/v1` endpoint on Modal GPU infrastructure — the entity-side sibling of llm-mailroom's KANBAN-064 app (SAME environment-knob contract `MODAL_VLLM_MODEL/GPU/QUANTIZATION/MAX_MODEL_LEN/API_TOKEN` + `HF_TOKEN`, separate Modal app name + persistent `entity-hf-cache` volume, so one workspace hosts independent deployments per pipeline or a single deployment backs BOTH repos via mailroom's own `VLLM_BASE_URL` seam). A configuration CAPABILITY, not a serving-path change: every eval runner keeps using OpenRouter unless `OPENROUTER_BASE_URL` is pointed at the deployment. Landing it exposed and fixed a REAL seam defect: `OPENROUTER_BASE_URL` was bound at module-import time in `src/openrouter_utils.py`, so dotenv-set values (loaded lazily by `env_utils.load_env()` immediately before client construction) never took effect — only true shell exports worked, silently breaking the entire dotenv-driven flip story. New resolvers `resolve_openrouter_base_url()` / `resolve_openrouter_api_url()` read env AT CLIENT-BUILD TIME; all three consumers converted (`agents/base_agent.py::llm()`, `src/llm_chain.py::build_chat_model()`, `src/classifier.py::classify_image()`); frozen import-time aliases retained for backward compatibility. New `[deploy]` extra + `requirements/deploy.txt` wired through the KANBAN-081 manifest law (`modal>=0.73`, deploy-time only — runtime tree stays clean); `config/environments/.env.example` gains the flip-the-switch block including the cross-repo contract; `scripts/smoke_vllm_endpoint.py` health-checks `/v1/models` + a real completion (exit-code semantics for CI); `deploy/README.md` documents deploy/flip/smoke/teardown plus cost shape (scale-to-zero after 15 idle minutes). Guard suite `tests/test_kanban096_modal_vllm.py` (21 network-free): stubbed-modal command assembly + quantization injection, bearer-enforcement mapping onto vLLM's native `VLLM_API_KEY`, distinct sibling identity, THE dotenv-regression pin, client-forwarding pins for base_agent (constructor-kwarg capture — no LangChain private-field coupling) and classifier, KANBAN-081 parity for the new extra, a runtime-tree census proving no runtime module imports `modal`, and a cross-repo knob-contract check against the mailroom sibling clone (skips honestly when absent).

### Changed

- **Single-source-of-truth repair: contracteval side-log merged into the canonical experiment record; derived tree made self-healing; the two chronic Posit-site failures fixed at root (KANBAN-094):** diagnosis of the long-failing `test_rendered_pages_committed` / `test_quarto_render_is_deterministic_and_clean` pair traced BOTH to one 2026-08-18 incident: 9 contracteval runs logged rows to an untracked side file (`reports/experiment_log_contracteval.jsonl`) while their per-run SPA files landed in `docs/data/runs/` — splitting the record (195 canonical rows vs 203 run files) and breaking the `experiment_log.jsonl ⇒ build_site.py ⇒ docs/data/runs/{n:03d}.json` derivation chain; one more side row (`contracteval_v5`) never produced a run file at all (run aborted on key-limit exhaustion). Fix: all 9 side rows verified (schema-clean, hazard-free, no overlap, chronological) and merged into the append-only canonical JSONL through the KANBAN-088 sanitizer → **204 rows**, side log deleted after absorption proof; `reports/experiment_log.md`, site data, pre-render includes, and rendered Posit pages ALL regenerated from the single source (204 run files, 204 deep links). `build_site.py` now prunes orphaned run files so the derived tree is always exactly `{001..N}` and its `--check` mode detects orphaned files (index length alone missed the incident); the quarto pre-render hook re-execs into the repo venv when driven by an interpreter without `llm_dojo_scoring` (quarto invokes bare `python3`), fixing the mid-render ModuleNotFoundError. New pins `tests/test_kanban094_single_source_truth.py` (5 network-free): no side logs may exist, run-tree is exactly `{001..N}`, `--check` rejects orphan files, hook survives system-python3 invocation, merged tail present/hazard-free/ordered.

- **Family-wide JSONL line-boundary hazard sweep — every remaining `ensure_ascii=False` writer classified, adopted, or explicitly exempted (KANBAN-088, [#44](https://github.com/Exios66/llm-entity-extraction/issues/44), the KANBAN-087 carve-out):** full census of the repo found **15 sites / 11 files**. NEW shared safety module `scripts/datasets/_jsonl_safety.py` now holds the canonical `sanitize_line_boundary_chars` + hazards map (extracted VERBATIM from the exporter) plus a one-call `safe_jsonl_line(obj, **dumps_kwargs)`; the KANBAN-087 exporter delegates to it with object-identical re-exports (its own 6 pins still pass unchanged). **9 row-writer sites across 7 files adopted** `safe_jsonl_line`: backfill_extraction_kpis (experiment-log rewrite), build_docclass_merged (merged-row writer), build_legalbench_full_pack (enriched + index writers), publish_enron_correspondence(+dedup) (publish writers), stream_legalbench_tasks_to_bt (BT staging + classes-manifest writers), build_docclass_v5 (`write_jsonl`). **5 sites exempted with inline justification markers**: three field-value dumps in build_docclass_* (nested JSON guarded downstream by the sanitizing row writer), two CSV-cell flattens in merged/pilot builders, and src/braintrust_utils record-id hash input (byte-stability beats split-safety; never persisted as rows). Guard suite `tests/test_kanban088_jsonl_safety_sweep.py` (5 network-free pins): lossless escape/round-trip, exporter re-export identity, per-file adoption, a repo-wide **no-unmarked-hazard-sites** scan (any future bare `ensure_ascii=False` fails CI until marked or adopted), and exemption-justification presence. Prevention over incident response: the U+2028 Hub-shredding failure mode is now structurally impossible for family writers.

- **Clause-category registry reconciled against the CUAD primary source — "verbatim" texts were paraphrases (KANBAN-072, [#25](https://github.com/Exios66/llm-entity-extraction/issues/25), foundation step):** `config/clause_categories.yaml` (49 categories: 41 CUAD + 8 MAUD) claimed verbatim Atticus Project question texts, but a character-level reconciliation against the canonical [`category_descriptions.csv`](https://github.com/The-Atticus-Project/cuad/blob/main/category_descriptions.csv) (fetched 2026-08-24, sha256 `7499950e…`, now vendored at `tests/fixtures/cuad_category_descriptions.csv` with license header) found **~30 of 41 CUAD texts deviated substantively** — including the texts quoted in issue #25 itself — while carrying the verbatim label; the smoking gun: `volume_restriction`'s old text actually described *price-increase consent* (a different category). All 41 CUAD `verbatim_question` fields are now CHARACTER-EXACT vs the primary source (normalized-diff proof: 0 mismatches); `answer_type` re-derived from the canonical per-category Answer Format column (9 non-Yes/No formats — the datasheet prose rounds to 8; `warranty_duration` flips to general_info, `outside_date` stays general_info as MAUD-side); the 8 MAUD deal points keep their #25-sourced text under an honest `[MAUD-SIDE … NOT yet reconciled]` tag. Added the issue's three `agent_inquiry_templates` (`change_of_control`→CUAD, `mae_clause_scope`→MAUD, `contract_amendment_restrictions`→CUAD/MAUD) verbatim. NEW `tests/test_kanban072_clause_registry.py` (5 network-free guards): registry shape 41+8, char-exactness vs the vendored oracle, answer-type↔format agreement, template presence/targets, and a mislabel-regression pin on the volume_restriction smoking gun. Zero code consumes this file today (pre-wiring groundwork for the specialist integration) — config-only change; suite holds baseline.

- **The-Mailroom visualizer mapped into the governed umbrella (KANBAN-091, [#47](https://github.com/Exios66/llm-entity-extraction/issues/47)):** [The-Mailroom](https://github.com/Exios66/The-Mailroom) (v0.2.0) — the sister pipeline's pixel-art visual engine, rendering every llm-mailroom run as an animated document conveyor driven solely by Langfuse traces — was absent from every umbrella surface despite being a fully governed family member (own AGENTS.md whose #1 maintenance duty is mirroring llm-mailroom's routing/taxonomy trace contract, own semver release train, own wiki). This repo: `docs/sister-repos.md` constellation diagram gains a `visualizer:` line and the At-a-glance table a "Downstream of the sister repo" row (reads traces, mirrors schema via `pipeline_schema.py`/`trace_interpreter.py`, dependency of no family repo); root README working-surfaces prose now lists it alongside the graph sites and wiki. Sister-side mirror edits landed in llm-mailroom (sister-repos map section + diagram node, README Umbrella row, wiki Home) under the same card — one card, one issue, both changelogs per the KANBAN-061 precedent. Docs-only; zero behavior change.

- **Cold-suite interpreter pin — posit pre-render subprocess spawned bare `python3` (KANBAN-086):** both spawn sites in `tests/test_posit_site.py` (the `_write_include` hook runner and the quarto-determinism test) invoked `_pre-render.py` via a bare `"python3"` argv, so any suite run without the repo venv on PATH died inside the subprocess with `ModuleNotFoundError: llm_dojo_scoring` → **5 phantom failures** in `test_posit_site.py` that masqueraded as content regressions (they rode along in KANBAN-080's documented baseline and KANBAN-081 recorded them as "7 chronic posit renders"). Both sites now use `sys.executable`, inheriting pytest's own interpreter — cold runs against any properly-installed venv just work. A/B proof in an identical stripped-PATH cold environment (`PATH=/usr/bin:/bin:/usr/sbin:/usr/local/bin`, PYTHONPATH scrubbed): unpatched **7 failed / 2 passed** → patched **7 passed / 2 failed**, the residual pair being the documented derived-site chronic class (`test_rendered_pages_committed`, `test_quarto_render_is_deterministic_and_clean`) which is unrelated to interpreter resolution. Test-only; zero behavior change for venv-on-PATH runs.

- **Root folder consolidation — content/governance dirs nested (KANBAN-083, issue #41, human directive 2026-08-23):** root visible directories reduced **13 → 10** by nesting the agent-plumbing dirs that confused newcomers, every live reference updated in lockstep from a full census (pathlib segment joins included — slashless `ROOT / "board"` literals are invisible to naive greps). Moves: `board/` + `discussion/` → **`governance/`** (MESSAGE_BOARD.md/.qmd + MESSAGE_BOARD_DISCUSSION.qmd — one umbrella for inter-agent state); `wiki/` → **`docs/wiki/`** (documentation under documentation — now matching llm-mailroom's existing convention); `site/` → **`docs/posit-src/`** (portal SOURCES beside their rendered `docs/posit/`, ending the two-sites ambiguity with `scripts/site/`). Deliberately NOT moved (idiomatic ML-repo citizens, 25–49 live code references each / import-level coupling): `reports/`, `data/`, `agents/ src/ config/ tests/ scripts/ requirements/`. Lockstep updates: `_quarto.yml` output-dir deepened to `../../docs/posit`; `_pre-render.py` ROOT depth + both governance reads; `build_site.py`; `render_message_board_qmd.py`; `test_posit_site.py` (SITE_DIR, div-balance read, git pathspec, and the `output-dir == "../../docs/posit"` contract re-pin); README layout block rewritten (+ stale root-`memos/` row from KANBAN-080 finally removed); `docs/README.md` posit section; wiki mirror pages (Site/Architecture/FAQ/Release-Process); `.gitignore` derived-output rules re-pathed. Portal render PROVEN from its new home (`quarto render docs/posit-src` → `docs/posit/` regenerated & committed); GitHub wiki synced via the script's new path `docs/wiki/sync-wiki.sh`. AGENTS.md path-doctrine rows (9 lines naming the old dirs) were PARKED through the ship, then APPROVED by Jack in-band later the same day and landed post-consent. Baseline discipline: pristine-HEAD worktree baseline 617 passed / 9 failed captured BEFORE judging deltas; in-tree verification after commit.

- **Modular dependency batches — evidence-derived install profiles (KANBAN-081, issue #39, human directive 2026-08-23):** dependencies split into purpose-scoped installable batches so users tailor their footprint instead of installing everything. Whole-repo AST import census drove every boundary: CORE (`pyproject.toml` `dependencies` + root `requirements.txt`, now identical sets) is exactly the agent → prompt → scoring chain's 8 needs (langchain-core, langchain-openai, openai, requests, python-dotenv, PyYAML, structlog, llm-dojo-scoring @v0.7.0) — the surface llm-mailroom imports. New extras mirroring new `requirements/<batch>.txt` files (7): `[tracing]` (arize-phoenix + opentelemetry-sdk + otlp exporter + langfuse), `[evals]` (braintrust), `[datasets]` (huggingface_hub + Pillow + pdf2image), `[reporting]` (numpy + matplotlib + openpyxl), `[embeddings]` (sentence-transformers, unchanged), `[dev]` (+tracing for the module tests), `[all]` (everything non-dev), plus a legacy `[pdf]` alias → `[datasets]`. Three manifest defects fixed in the same pass: (1) the tracing stack was MISSING from pyproject.toml entirely — a bare `pip install -e .` could not import the repo's own default tracing sink `src/tracing.py`; (2) `openpyxl` and `huggingface_hub` were imported by deck exporters/publishers but declared NOWHERE (worked only via transitive luck); (3) dead pins `pandas>=2.0.0`/`pyarrow>=15.0.0` removed — zero imports across all active code (no notebooks exist). NEW `tests/test_dependency_manifests.py` (6 network-free pins): core floor frozen exact-set, extras↔batch-file parity per package+floor, `[all]` completeness, dead-pins-stay-dead/undeclared-stay-declared guards, and a live AST census re-deriving the third-party import surface of shipped `agents/`+`src/` against a module→batch owner map (batch modules may use core ∪ their batch, nothing else). Proof before push: fresh-venv (python3.13, pip 26.1.2) core-only install from a clean tree copy → `src.prompts` (103 prompt versions) + `agents.sorter_agent` import GREEN with phoenix/langfuse/opentelemetry/braintrust/huggingface-hub/sentence-transformers VERIFIABLY ABSENT; `-e ".[tracing]"` add-on → `src.tracing` imports and initializes the live Phoenix tracer. Honest residues: `matplotlib`+`openpyxl` still arrive in core installs transitively because llm-dojo-scoring v0.7.0 itself declares them in its `install_requires` (upstream dojo slim-down owed, not fixable consumer-side); AGENTS.md quickstart dependency lines (3) APPROVED by Jack in-band later the same day and landed as an explicit-path follow-up commit; wiki `Getting-Started.md` updated in-repo and synced to the live wiki same day. Suite delta vs pristine-HEAD worktree baseline: 611→627 passed (+16 = 6 new pins + 9 data-gated HF-mirror tests that skip without untracked dumps + 1 worktree-artifact fail), FAILED set byte-identical (7 chronic posit renders + kanban076 hub-sha check).

- **Release infrastructure repaired — tags and GitHub releases now match the documented convention 1:1:** (1) the dangling `[v0.11.0]` link is resolved — the annotated tag was never cut when its section shipped, so `v0.11.0` was created retroactively at `f838e71` (the exact commit that landed the section, correctly before v0.12.0's tag) with a full backfilled release; (2) five tags that had been created lightweight against Release-Process.md's annotated rule (`v0.10.0`, `v0.12.0`, `v0.13.0`, `v0.19.1`, `v0.20.0`) were re-forged as annotated AT THE SAME COMMITS (zero history change; refs force-pushed individually); (3) the fourteen versions v0.1.0–v0.10.0/v0.12.0–v0.14.0 had NO GitHub releases at all — each now has one built from the version's own CHANGELOG section as it existed AT the tag, plus the full commit range (capped list), a CHANGELOG.md@tag link, and a compare/diff link; (4) the seven existing releases were standardized in place: curated prose preserved, same commits/references footer appended, titles normalized to `vX.Y.Z — <summary>`; Latest badge pinned back to `v0.20.0` after the tag swaps briefly drafted it. Header/link-ref normalization that made this possible is in the previous entry. Repo-metadata only; no code, prompts, or dependency changes.

- **v0.20.0 fresh-install archive proof re-run GREEN on the pushed tag** (KANBAN-080 wrap-up of the interrupted release train): clean-venv `pip install .` from `git archive v0.20.0` now resolves fully from default PyPI — `langchain-core` 1.6.0 is live (the earlier "unresolvable floor" finding was a stale index view, forensics 2026-08-23) — and the real-surface smoke import passes (`src.prompts`, 103 registered prompt versions). No pin change needed; tag and GH release stand as shipped.

- **Root de-clutter / file nesting with every live reference updated in lockstep (KANBAN-080, issue #38):** `SCORING.md` → `docs/SCORING.md`; orphaned legacy deploy script `deploy_phoenix.sh` → `scripts/deploy/deploy_phoenix.sh` (zero code references); the split-brain memo homes merged — root `memos/*.md` (12 newer v34–v39 design memos) moved into `docs/memos/` (35 total), fixing the site's memos tab, which had been silently serving only the old set (`build_site.py::build_memos` already read `docs/memos/` while its docstring claimed the root); tracked backup cruft removed from git (`src/prompts.py.bak`, `src/prompts_original.py`; history preserves them); legacy root convenience symlinks (`MESSAGE_BOARD.md`, `MESSAGE_BOARD.qmd`, `MESSAGE_BOARD_DISCUSSION.qmd`) deleted — every programmatic reader already used the canonical `board/` + `discussion/` paths. Live references updated across `README.md` (including two stale Layout-tree pointers: a phantom root `V16_PROPOSITION.md` and the dead `memos/README.md` link), `docs/README.md`, `docs/slides/*`, wiki pages, `scripts/site/build_site.py` (`scoring_md` URL + docstring + mirror comment), eval-runner help strings, and both deck exporters; frozen history (CHANGELOG sections, board rows, `reports/`) deliberately untouched by append-only policy. Immovable-at-root documented in the card row (pyproject.toml, requirements.txt, CHANGELOG.md, README.md, AGENTS.md, dotfiles). AGENTS.md path-doctrine updates (5 lines: file-map row, scoring-reference pointer, update-checklist cite, noise-floor memo cite, Research-memos section header) approved same-day by the human operator and landed in the follow-up governance commit. Derived artifacts regenerated: `docs/data/meta.json` scoring_md → `docs/SCORING.md`, `memos.json` 22 → 34 memos, benchmarks refreshed live (1,438 rows); `docs/posit/` re-rendered. Targeted suite (test_posit_site + test_graphify_skill): 12 passed, failures byte-identical to the documented chronic pair (derived-site classes).

### Added

- **Scoring-process notebooks launched — exemplar `03_doc_type_bundles` shipped (KANBAN-068, [#33](https://github.com/Exios66/llm-entity-extraction/issues/33), first deliverable of the six-notebook set):** NEW `notebooks/03_doc_type_bundles.ipynb` walks the v0.7.0 headline scoring process end-to-end offline: every bundle in `DOC_TYPE_BUNDLES` (metrics + validation per doc type), the `get_doc_bundle` honesty resolver with its explicit `used_fallback` flag, and — the payoff — a closing honest-gap table derived from THIS repo's real append-only log (`reports/experiment_log.jsonl`, 195 records / 19,642 scored document rows): contract ×16,783, correspondence ×407, merger_agreement ×335, corporate_record ×69, compliance_filing ×44 and due_diligence ×4 have REAL benchmark rows, while `court_opinion` and `insurance_claim` are shown as genuinely declared-pending. Thin-notebook pattern per the KANBAN-078 precedent: kernel-cwd-proof bootstrap (`find_repo_root()` walks up for `pyproject.toml`+`reports/`, runs from anywhere incl. hostile cwd), stdlib-only cells against the pinned `llm-dojo-scoring @v0.7.0`, zero network/LLM calls. Guard suite `tests/test_kanban068_bundles_notebook.py` (4 network-free tests): notebook validity, code-cell network/LLM-free scan, cwd-proof bootstrap pin, and full headless execution via nbclient FROM `notebooks/` asserting the honest-gap summary matches reality (contract REAL, court_opinion + insurance_claim pending). Install path: new `[notebooks]` extra = `requirements/notebooks.txt` 1:1 (nbformat/nbclient/ipykernel, floors = versions verified on python3.13), registered into `[all]`/`all.txt` and the KANBAN-081 manifest-parity guards (extras↔batch-file parity + all-batch tuples). `notebooks/README.md` scopes all six process notebooks with conventions; remaining five (classification, typed-field extraction, audit/verification, chained pipelines, report/aggregation) follow the same pattern.

- **Dedicated docclass prompts for every classification-chain role (KANBAN-090, issue #46, human directive via Discord #hermes 2026-08-23):** the docclass arm (KANBAN-033 lineage -> docclass-merged schema v5 + docclass-pilot) had specialized prompts ONLY at the sorter (`sorter_docclass_v0..v6` + `_vision_v0`) — every downstream role ran its GENERIC prompt inside docclass-context evals. NEW `src/prompts_docclass.py` ships a **21-key `DOCCLASS_PROMPT_VERSIONS`**: the 8 sorter-docclass keys RE-EXPORTED byte-identical (same objects, never redefined — this module is the docclass arm's single import surface), **10 derived variants** built by single-anchor `.replace()` off the REAL base constants (contracts / corporate_records / due_diligence / correspondence / compliance / court_opinions specialists + boss + the judge trio completeness/classification/correctness), and **3 authored-fresh V0s** for roles this repo has no base constant for (reviewer, arbiter, insurance_claims specialist — provenance-commented as modeled on llm-mailroom counterparts). Every variant prepends a shared **DOCCLASS ARM CONTEXT** block (the extended 8-class primary set incl. `insurance_claim` + `merger_agreement`, second-level doc_subclass dimensions: CUAD-style contract subtypes, merger consideration types, title-derived corporate record types) plus role-specific rules — routing label is pipeline STATE not ground truth, claim-documentation and M&A leakage read-through, judge trio gains subclass-specific support requirements and cross-family leakage checks, classification judge grades against the extended set with family discriminators, boss routes classification-fault conflicts to human review. Derivation discipline mirrors the version-lineage convention: anchors are single-count-asserted so a future base edit that adds a JSON closer fails loudly instead of silently duplicating blocks. **Registration IS deployment** per repo doctrine: the registry is merged into `PROMPT_VERSIONS` at the prompts.py tail (prompts_archive tail-import precedent), taking registered versions **103 -> 116** (the 8 sorter keys pre-dated the card; `update()` was a no-op on those, zero collisions asserted at import), so `scripts/eval/sync_langfuse_prompts.py` mirrors every key to Langfuse exactly like every other family. Runtime untouched: nothing fetches a docclass key by default — eval runners and pipeline configs opt in explicitly by key. Guarded by 6 network-free tests in `tests/test_kanban090_docclass_prompts.py` (full-registry resolvability through `get_prompt()`, re-export identity checks, `[:300]` head-prefix + tail-drift derivation pins, base-anchor single-closer guards, authored-V0 provenance comments verified in module source, negative proofs that generic routes carry no docclass text). Suite delta vs pre-change baseline: targeted prompt suites fully green (70 passed = 64 existing + 6 new); full-suite failures byte-identical to the documented pre-existing set (kanban076 hub-sha check requires a live localhost:6006 service; chronic derived-site posit renders).

- **Hub JSONL repair — mailroom-cuad-contracts-full DatasetGenerationError root-caused, artifact repaired, republished clean (KANBAN-087, board-only, human report 2026-08-23):** the Hub's parquet worker died with `ujson_loads` `ValueError: Expected object or value` while local loads passed — download forensics proved the JSONL structurally valid (510/510 lines parse) but ONE record (line 73) carried **16 literal U+2028 LINE SEPARATOR chars inside `.input.doc_text`** (CUAD PDF-extraction artifact); any loader parsing batches via `str.splitlines()` treats those as record breaks INSIDE the row and shreds it into invalid fragments, while local `datasets` 5.x splits BYTES (`bytes.splitlines()` ignores U+2028) — a version-dependent landmine where a green local load proves nothing. Writer fix: `scripts/datasets/export_bt_to_hf.py` now escapes the hazard set (U+2028/U+2029/NEL) at write time via new `sanitize_line_boundary_chars()` (lossless \uXXXX escapes; `json.loads` decodes identical values) — bare `ensure_ascii=False` dumps were shipping loaded guns to every line-oriented consumer. Artifact repair: staging file sha-matched the Hub bytes (`cac0c845…`), sanitized with the exporter's OWN function, per-row semantic round-trip asserted (0 mismatches), worker-shape A/B proven (original shreds into 526 pieces → repaired stays 510), manifest rewritten honestly (old+new sha256 `c8beefd6…`, repair note). Republish: repaired pair uploaded under CANONICAL names (`<dataset>.jsonl` + `manifest.json`) overwriting the broken blobs — after a first-pass detour that published misnamed `_repaired` duplicates beside the originals (the `hf upload <local-file>` publishes under the LOCAL basename trap; duplicates evicted via `hf repos delete-files`). Verification: repo tree census exactly 4 files, fresh-download round-trip sha equals the repaired artifact, hub manifest consistent, datasets-server `splits` reports `pending: [] / failed: []`. Guarded by 6 network-free pins in `tests/test_kanban087_jsonl_hazards.py` (hazard-set coverage, escape-at-write shape, lossless round-trip, worker-parse-shape collapse, incident-shape replay, writer-path wiring).

- **docclass-pilot — cleanly distributed Mailroom pilot corpus + docclass-merged schema v5 with clause-level ground truth (KANBAN-084, issue #43, human directive 2026-08-23):** NEW [docclass-pilot](https://huggingface.co/datasets/Lucius-Morningstar/docclass-pilot), derived directly from [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) as the pilot testing set for the Mailroom pipeline visualizer AND per-agent evaluation: **138 rows covering all 48 canonical strata** (quota=3 per `expected × expected_subclass`, min-stratum take-all), drawn deterministically by ascending sha256(filename) WITHIN each stratum (rebuild-stable byte-identical re-stage), same two-config layout as the parent (`default` blind vs `ground_truth` joined 1:1 on `filename`, both carrying train/test per the family `split`). The parent simultaneously evolves to **schema v5** (sharded parquet overwritten in place; legacy `docclass_merged.jsonl` retained UNTOUCHED for pinned consumers; `manifest.txt` replaced with the v5 lineage record): **+400 `insurance_claim` rows** (inpatient/outpatient/carrier/pde rendered EOBs from cms-desynpuf-insurance-claims with a verbatim GT contract aligned to llm-mailroom's InsuranceClaimExtraction; source keyed its placement on md5(record_id), fused under the family rule md5(filename)%10 — 65/400 rows changed placement, disclosed on-card; honest gaps: synthetic data, PAID claims only so `coverage_determination` is always approved / `denial_reasons` always empty, `adjuster` always null, single line of business) and **CLAUSE-LEVEL ANSWER KEYS, ground_truth config ONLY**: `cuad_clause_labels` on contract rows sourced from the official CUAD annotation JSON (the machine-readable superset of masterlabels.csv) — **509/509 contracts joined, 13,753/13,753 answer spans verified at exact char offsets** against the stored `doc_text` (compact JSON: clause name → [{text, start}]); `maud_clause_labels` on merger_agreement rows from MAUD's classification dump — **152/152 contracts joined** via contract id (task → category/answer/valid_classes/label_idx). These are the scoring substrate for entity extraction. **Subclass canon normalization** kills CUAD's duplicate grouping-folder spellings that skewed the contract-type distribution: `Affiliate Agreement`(1)+`Affiliate_Agreements`(9)→10, `Endorsement Agreement`(9)+`Endorsement`(15)→24 (contract subclasses 28→26, total strata 50→48); single-sourced as `CONTRACT_SUBCLASS_CANON` + `normalize_contract_subclass()` in `build_docclass_merged.py`, applied at v5 row construction with a build-time canon guard that fails loudly if any legacy spelling survives; deliberately-DISTINCT buckets pinned unmerged (Joint Venture vs `Joint Venture _ Filing` separate CUAD folders, `mixed_cash_stock_election` distinct MAUD class, `attorney_demand` vs `demand` distinct labeler subtypes). Builders: `scripts/datasets/build_docclass_v5.py` (six sha-pinned source shards verified, family-rule claims fusion, clause-GT attachment + span QA), `scripts/datasets/build_docclass_pilot.py` (stratified draw → stage → Hub publish), `scripts/datasets/publish_docclass_v5.py` (regex-anchored surgical edits on the LIVE parent card with count==1 assertions, all-string GT parquet schema matching the parent storage convention). Guarded by 10 network-free pins in `tests/test_kanban084_pilot_sample.py` (blind∩GT=∅ including the new clause keys, quota/coverage-exact deterministic draw, split preservation, shard-pin completeness, canon merge + identity-on-canonical-forms + never-merge list). Suite delta vs pristine HEAD (detached-worktree baseline): 613 passed (+10 pins); residual failures/errors byte-identical to the pre-existing baseline — the chronic posit pair clears on render-commit of this ship, while the kanban076 LFS-pin assert failure and six `tests.test_langfuse_tracing` collection errors reproduce at clean HEAD and are NOT this card's scope (parked for follow-up).

- **Graphify knowledge graph built & published for this repo (KANBAN-080):** first build here despite the skill being vendored since KANBAN-065 — `graphify . --code-only` (local AST, no LLM backend, matching mailroom's convention) → 3,402 nodes / 7,252 edges, then `cluster-only --no-label` → 151 communities + `GRAPH_REPORT.md` + standalone viewer. Published as the derived-artifact Pages site [llm-entity-extraction-graph](https://exios66.github.io/llm-entity-extraction-graph/) (new public repo `Exios66/llm-entity-extraction-graph`: `index.html` viewer + quarto-rendered `report.html` + `.nojekyll`, mirroring llm-mailroom-graph conventions; `graphify-out/` itself stays uncommitted here). NEW `docs/sister-repos.md` — the mailroom-convention umbrella map for THIS repo's side of the family (llm-mailroom, llm-dojo-scoring @v0.7.0, corpus feeds, HF family, both graph sites, governance notes). Links wired: README Working-surfaces, wiki Home quick-links block + `_Sidebar` External section, and mailroom's `docs/sister-repos.md` reciprocally (mailroom commit `b1ef37a`).

- **Scoring-documentation currency pass — every `llm-dojo-scoring` reference brought up to the live `@v0.7.0` pin:** five doc surfaces still described the outsourcing era's `@v0.2.0` pin (or a one-off `v0.4.0` task-kind ref) even though the dependency has been re-pinned three times since (v0.5.1 KANBAN-061, v0.6.0 KANBAN-062/063, v0.7.0 KANBAN-067): `SCORING.md` §0 + the "Scoring model" preamble in `AGENTS.md` + `README.md` §Scoring now all read `@v0.7.0`, and the ContractEval runner row no longer cites a stale upstream version. `SCORING.md` gains **§0.1 "The unified scoring layer & the score-emitter bridge"** documenting what v0.19.0 adopted but never documented on this page: the package-side `registry` (T0 HEADLINE/T1 CORE/T2 DEEP/T3 LOG tiers, built-in default covering both consumers' emission surfaces incl. all 37 mailroom SCORE_CONFIGS names), nine `bundles` task bundles, all 23 agent `profiles` (incl. the Lane A/B review set: `sorter_reviewer`, six per-specialist auditors, `arbiter` — ground-truth-free), the eight document-type-aware `doc_bundles` with the honest-gap mandate and `resolve_doc_bundle()`'s explicit `used_fallback` marker (KANBAN-067), the unified `emitter` (registry-validated emit → JSONL/Langfuse sinks, `get_scorecard(min_tier=...)`, `compare_headlines`), and `pruning` dashboard views — plus this repo's third adapter `src/score_emitter.py` (`build_emitter` / `emit_run_scores` returning `(emitted, skipped)` so unknown names surface as registry work, never silently lost; `dashboard_names`/`headline_names`), which was also missing from the AGENTS.md key-modules table. The expanded package-surface sentence now lists all 25 modules. `wiki/Scoring.md` re-mirrored byte-identical to `SCORING.md` (it had drifted twice: missing the v0.3.0 category-presence routing note AND the entire KANBAN-052 ContractEval §8 block) and pushed to the GitHub wiki via `./wiki/sync-wiki.sh`. Docs-only; zero behavior change; memos/board history deliberately untouched (append-only record).

- **Enron dedup GT enrichment — content-topic + sentiment labels, agent-blind two-config layout (KANBAN-079, issue #37, human directive 2026-08-23):** [enron-correspondence-dedup](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup) republished as **schema v2** with TWO card-declared configs so ground truth is invisible to pipeline agents by default: config `default` (blind/train+test.jsonl) carries ONLY filename/subject/text/split/metadata; config `ground_truth` (ground_truth/train+test.jsonl, joined 1:1 on `filename`) carries every answer key — `expected`, `expected_subclass`, `label_evidence` plus NEW enrichment columns `content_topic`/`topic_evidence` (11-key taxonomy of what each message is ABOUT: energy_market, legal_contracts, scheduling, hr_personnel, finance_earnings, regulatory, it_systems, travel_logistics, marketing_clients, announcements, general_business) and `sentiment_score`/`sentiment_label`/`sentiment_evidence` (deterministic lexicon polarity [-1,1], negation/intensifier-aware, politeness-formula controlled). `load_dataset(repo)` returns the blind view only; scorers opt into GT explicitly (`load_dataset(repo, "ground_truth", split=...)`); the viewer keeps both configs for human auditing (documented on-card as separation-of-concerns, not encryption). The legacy monolithic all-columns jsonl was DELETED from the Hub repo at publish (the JSON loader would otherwise fold its GT columns back into default and re-leak). Labelers live in Enron-Evaluation-Environment `scripts/` beside the shared subclass module (`content_topics.py`, `sentiment_scorer.py`; commit `c3bb908`) and are IMPORTED by the publisher — never forked; 34 network-free tests there (70/70 suite). Publisher rewrite (`publish_enron_correspondence_dedup.py`): same sha-gated source (`0554a5973935…`), same dedup rule (`body_hash` md5 exact-hash, first occurrence wins, empty bodies never deduped — 517,390 rows in → 247,523 out, 269,867 dropped, largest group 112, all 150 custodians), splits recomputed+asserted (222,572 train / 24,951 test, identical per config); guards refuse to publish on invalid topic keys, out-of-range/non-finite sentiment scores, unknown labels, non-uniform metadata key-sets, null leading columns, GT keys present in blind rows, or blind/GT filename join drift; determinism proven by two independent builds producing byte-identical output across ALL FOUR data files. Post-upload verification: LFS-sha equality for ≥10MB blobs + download round-trip hash for sub-threshold files (`ground_truth/test.jsonl`, 9.83 MB, ships as a plain git blob) — all four GREEN, legacy file confirmed gone. Distributions (manifest.txt): topics general_business 183,588 (74.2%) / energy_market 21,605 (8.7%) / hr_personnel 10,062 (4.1%) / scheduling 8,237 (3.3%) / legal_contracts 7,667 (3.1%) / regulatory 4,928 (2.0%) / marketing_clients 3,834 (1.5%) / travel_logistics 2,900 (1.2%) / it_systems 2,841 (1.1%) / finance_earnings 1,163 (0.5%) / announcements 698 (0.3%); sentiment neutral 167,964 / positive 51,668 / negative 27,891. Honest gaps on card + manifest: exact-hash dedup only; single-topic assignment + ~2000-char head window; lexicon sentiment = weak labels (no sarcasm/context modeling); voicemail impossible in a text-only corpus. Pins: 3 deliberate re-pins in `tests/test_kanban076_hf_sync_finish.py` (mechanisms preserved-but-strengthened) + 10 new in `tests/test_kanban079_gt_separation.py`.

## [v0.20.0] - 2026-08-23
### Added

- **HF family sync finish — Hub manifest landmine ROOT-CAUSED via live canaries, all three repos repaired, deduplicated Enron correspondence published (KANBAN-076, human directive 2026-08-23):** the datasets-server conversion failures blocking the family were traced to a sharper rule than the KANBAN-073/074 hotfix assumed: **the Hub's JSON loader ingests ANY repo path whose filename contains `.json` as data rows** — bare `manifest.json`, `.json.txt` (the 074 "fix" is disproven on current infra), at repo root OR in subdirectories — merging the manifest's fields into the data table (`CastError: column names don't match`) and failing `config-parquet`. Proven with four controlled canary uploads under the org (`kanban076-canary{1..4}`): jsonl-only converts clean; identical jsonl + `manifest.json.txt` fails; same with the manifest in a `data/` subdir still fails; identical jsonl + **`manifest.txt`** (no json substring anywhere in the name) converts clean serving pure data features. Repairs applied surgically to [enron-correspondence](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence) and [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) (round 1: `manifest.json`→`.json.txt`; round 2 after the canary verdict: →`manifest.txt`, content byte-identical each hop) with the verified corpus blobs asserted untouched across every mutation (LFS `0554a5973935…` and `af7705368c83…` re-read from the tree before/after). NEW [enron-correspondence-dedup](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence-dedup): **exact-duplicate removal over the full corpus — 517,390 rows in → 247,523 unique-text rows out** (269,867 byte-exact copies dropped = 52.2%, matching the source repo's EDA §14 "over half"; largest duplicate group 112 copies of one text; all 150 custodians retained; empty-body rows never deduped against each other), built by `scripts/datasets/publish_enron_correspondence_dedup.py` which imports `body_hash` from Enron-Evaluation-Environment's `scripts/dedupe.py` (single-source hash shared with the EDA duplicate counts — never reimplemented), refuses to build from any source whose sha256 ≠ the verified export prefix `0554a5973935`, streams first-occurrence-wins in maildir-path order (deterministic — two independent builds produced byte-identical output `e2f7241f4d45…`), recomputes+asserts every row's split against the family `assign_split()` (0 mismatches — the md5(filename) rule is keyed on filenames dedup never alters; coverage 222,572 train / 24,951 test), runs the full schema guard, verifies hub LFS sha == local after upload (GREEN), and ships its manifest ONLY as `manifest.txt`; card documents the honest gap (exact-hash dedup only — near-duplicates like quote-stripped replies are NOT detected; use `metadata.message_id` for thread grouping). **Round 3 (docclass-specific):** after the manifest repair docclass-merged STILL failed conversion — fresh error readout (`TypeError: Couldn't cast array of type struct`) exposed a SECOND landmine the manifest poison had been masking: MAUD rows carry a nested dict `metadata.maud_categories` while the leading CUAD row-group doesn't, and the loader infers ONE arrow struct for the whole `metadata` column from the first group then dies casting later groups (the KANBAN-073 partial-schema failure one level deeper — evidence scan confirmed `maud_categories` was the ONLY heterogeneous-typed key). Fixed in the builder via new `normalize_metadata_rows()`: every row carries the UNION of all metadata keys with EVERY value a plain string (missing → empty string, never null; nested dicts AND lists serialized to compact sorted-key JSON strings; scalars stringified). That took two rounds to get exactly right — round 3 preserved CUAD's list-typed `applicable_categories` as `list<string>` and filled absent rows with `""`, which re-crashed conversion (the loader casts later groups against the first group's inferred schema: `string ≠ list<string>` is a hard cast error); round 4 serializes containers uniformly so no key ever carries two types. `publish_kanban071.py` gained a matching pre-upload guard refusing non-uniform metadata key sets or non-string values. Rebuild produced identical 700-row content with the dataset fingerprint UNCHANGED (`cd652e77…` — the fingerprint does not hash metadata, so eval identity is stable); republished + verified LFS sha local == hub (`af0a5324bb65…`). All three publishers' staging blocks now ship `manifest.txt`; 12 network-free pins added in `tests/test_kanban076_hf_sync_finish.py` (no publisher may stage ANY path containing `.json`; `manifest.txt` required; dedup single-source/guard/sha-gate/empty-body-semantics pins; upstream `body_hash` contract; staged-artifact shape). Verification note: the `/status` datasets-server endpoint is retired (404) — job state now read from the `pending`/`failed` arrays carried by `/splits`, `/parquet`, and `/size` responses. Suite **609✓** (+12 pins) / 7 documented posit fails unchanged / 4 skip.

- **Karpathy coding guidelines adapted into core AGENTS.md doctrine (KANBAN-075, human directive 2026-08-22):** a new `## Coding guidelines (adapted from Karpathy)` section now sits between *Code conventions* and *Testing rules* in the repo-root AGENTS.md, translating the four principles from [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) — **Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution** — into house doctrine with repo-specific mappings (card-scope + version-key declaration before first edit; `.replace()` prompt derivation as native simplicity; every changed line traces to the card via explicit-path commits; Phase 4 artifact-derived evidence as goal-driven verification) and an explicit precedence clause: the governed workflow (board lifecycle, append-only prompt versioning, release gates) always outranks the principles where they touch. Adapt-don't-vendor per the KANBAN-066 recipe: upstream pinned at `2c606141936f1eeef17fa3043a72095b4765b9c2`, provenance sidecar `.opencode/agents/CODING_GUIDELINES_PROVENANCE.md` records sources consulted + re-sync protocol, and no upstream sentence is copied verbatim (anti-vendoring pins assert this). Overlap audit against the live tree: prior "surgical" mentions are pytest scope-selection only — fully additive doctrine. Guarded by 9 network-free mechanics pins in `tests/test_coding_guidelines_agent_file.py` (section presence, principle order, precedence clause, doc↔sidecar URL+pin consistency, placement between conventions/testing anchors, verbatim-copy prohibition). Docs-only change; no runtime behavior affected. Suite **597✓** (+9 pins) / 7 documented posit fails unchanged / 4 skip.

- **HF dataset family completeness — deterministic train/test splits everywhere + the cleaned Enron correspondence corpus published (KANBAN-074, human directive 2026-08-22):** every dataset in the `Lucius-Morningstar` family that has train/test semantics now carries a **deterministic per-row `split`** — rule: `md5(filename) % 10 == 0 → test` (~10%), order-independent and rebuild-stable, ONE shared implementation (`assign_split()` in `scripts/datasets/build_docclass_merged.py`) imported by both publishers so no forked rule can drift. Concretely: [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) republished as **schema v3** (700 rows, `filename`/`expected_subclass`/`split` all non-null strings; LFS sha256 local == hub `af7705368c83…`; manifest records `schema_version: 3` + `split_coverage` 628/72; datasets-server types every column `string` and row 0 serves `Co_Branding`/`train`). NEW [enron-correspondence](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence): the **FULL cleaned CMU Enron corpus** — **517,390 parsed messages from 150 custodians, zero dropped** (every index row published) — via new `scripts/datasets/publish_enron_correspondence.py`, consuming Enron-Evaluation-Environment's full-corpus index (`scripts/build_corpus_index.py` over the raw 3 GB maildir, sorted deterministic walk). Ground truth: the SHARED 10-key taxonomy labeler (`correspondence_subclasses.label_correspondence`, imported — never reimplemented) applied per row with an on-row `label_evidence` audit trail; distribution: email 505,929 / memo 3,568 / press_release 2,520 / notice 2,842 / letter 2,077 / demand 315 / meeting_request 135 / attorney_demand 4 / other+voicemail 0 (sums to exactly 517,390); splits 465,570 train / 51,820 test; LFS sha256 local == hub `0554a5973935…`; datasets-server GREEN (`pending: [] failed: []`, all 8 columns typed, row 0 = allen-p email/train); card documents labels as HEURISTIC ground truth with honest known gaps (attorney-detection list coverage, voicemail impossible in text corpus, cross-custodian duplicates NOT merged — group by `metadata.message_id`). Family audit verdicts recorded honestly: [legalbench-full](https://huggingface.co/datasets/Lucius-Morningstar/legalbench-full) ships native upstream train/test TSVs (complete as-is); the three mailroom BT mirrors are whole-gold eval pools where train/test semantics don't apply (documented, not manufactured). Guards extended: both the docclass builder refuse-to-write check and the publisher pre-upload guard now also require `split ∈ {train, test}`; +4 pins in `tests/test_kanban071_hf_pack.py` (split determinism + single-source rule, dump-level split coverage, enron publisher guard/labeler-source pins). Suite **588✓ / 7 documented posit fails unchanged / 4 skip**.

- **docclass-merged schema v2 — subclasses + file names on every row, Hub viewer cast-crash fixed (KANBAN-073, human directive 2026-08-22):** the [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) Hub dataset now carries `expected_subclass` and `filename` as non-null strings on ALL 700 rows — contracts included, using CUAD's own contract grouping (`metadata.category`, 28 groups: Marketing, Maintenance, License_Agreements, …) as the contract subclass, with `filename` = the source PDF basename; MAUD (consideration types) and S-1 (record subclasses) already carried both fields. This also fixes the reported Hub viewer failure (`DatasetGenerationError: Couldn't cast array of type string to null`): the old file was written CUAD-first with all-null subclass + empty filename, so the JSON loader inferred null-typed columns from the opening batches and crashed when later string batches arrived — the exact inference-on-prefix failure. Guardrails so it can't regress: the builder refuses to write any row lacking either field, and `publish_kanban071.py` gained a pre-upload schema guard refusing partial-null uploads; the manifest records `schema_version: 2` + subclass coverage (700/700/28 contract groups); 4 new network-free pins in `tests/test_kanban071_hf_pack.py` (now 12). Republished + verified: LFS sha256 local == hub (`3bd9d74de9f1…`), new deterministic fingerprint `cd652e77…`, and the datasets-server serves the dataset cleanly — `splits` shows no pending/failed conversions and `first-rows` types both label columns as `string` with real values on row 0. Side effect worth noting: the docclass eval runner already grades `expected_subclass` when present, so contract rows now participate in subclass scoring (previously skipped) — a strictly richer eval surface, no runner changes needed. Suite **585✓ / 7 documented posit fails unchanged / 4 skip**.

- **Full LegalBench pack + merged docclass corpus → Hugging Face Hub, CUAD-quality label enrichment (KANBAN-071, human directive 2026-08-22):** two new verified Hub datasets under `Lucius-Morningstar`. [legalbench-full](https://huggingface.co/datasets/Lucius-Morningstar/legalbench-full) mirrors ALL 162 upstream task directories of HazyResearch/legalbench (CC BY 4.0) fetched verbatim from source (160 with data: 856 train rows, 16 test splits = 10,219 rows, byte-exact TSVs/prompts/READMEs; 2 honestly marked EMPTY as upstream ships them) plus a CUAD enrichment layer for all 38 `cuad_*` tasks: every {excerpt, Yes/No} row is re-joined to CUAD_v1.json expert annotations via a whitespace-flexible excerpt locator (199 exact + 1 fuzzy ≥0.75 / 20 span-unmatched / 8 unknown-contract — every row dispositioned, none dropped), attaching char offsets, overlapping clause questions with exact expert spans, and an on-row `category_audit` cross-check of the LB label against CUAD's expert highlights ON THE EXCERPT (192 agree / 8 SUSPECT / 0 mismatch; labels never rewritten). [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged) publishes the unified document-classification surface: 700 rows = 509 CUAD contracts (local staging-export reuse — BT stays read-only) + 152 MAUD merger agreements + 39 EDGAR S-1 corporate-record exhibits, deterministic order + fingerprint `5b682f62…`, subclass GT carried for MAUD consideration types and S-1 record subclasses. New tooling: `scripts/datasets/build_legalbench_full_pack.py` (full-task-tree fetch + enrichment + `ENRICHMENT_REPORT.json`) and `scripts/datasets/publish_kanban071.py` (dataset cards, upload, verification); `build_docclass_merged.py` gains a local-first CUAD loader (`--bt-cuad` fallback kept). Verification ran GREEN twice (re-upload doubles as independent reproduction): legalbench-full 379/379 files byte-proven via git-blob OID vs the Hub tree + aggregates round-trip hash; docclass-merged LFS sha256 local == hub (`c8faf0ab6ed8…`). Also restored the missing `data/maud/classification.jsonl` local dump (25,827 MAUD per-question rows — the earlier contracts-only stream had left it absent) and fixed a latent crash in the `tests/test_pipeline_sources_eda.py` footer-collision helper (a bare `FigureCanvasBase` lacks `get_renderer`; attach an Agg canvas when missing — that test was skip-guarded until this session's CUAD_v1.json download un-skipped it). Suite **573 passed / 7 failed (documented posit-render set, unchanged) / 4 skipped** + new network-free pins `tests/test_kanban071_hf_pack.py` (8 tests).

- **Braintrust → Hugging Face dataset mirror (KANBAN-069, issue #34):** the eval ground truth hosted in Braintrust is now mirrored to the Hub for universal agent/eval-runner access — [Lucius-Morningstar/mailroom-cuad-contracts](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-cuad-contracts) (50 rows + 546 page-PNG attachment payloads under `images/`), [Lucius-Morningstar/mailroom-cuad-contracts-full](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-cuad-contracts-full) (510 rows), and [Lucius-Morningstar/mailroom-lb-hearsay](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-lb-hearsay) (5 rows), each with a provenance dataset card (source corpus + CC BY 4.0 license, BT project/dataset ids, export sha256). New tooling: `scripts/datasets/export_bt_to_hf.py` (STRICTLY read-only against Braintrust — live-catalog discovery via `GET /v1/dataset`, streamer defaults absent from the catalog recorded as skipped never created, row reads via the SDK's BTQL query surface, resumable image-attachment download into gitignored `data/hf_export/`) and `scripts/datasets/publish_hf_mirror.py` (dataset-card generation, upload, post-upload sha256 verification). Verification record: `mailroom-cuad-contracts-full` byte-identical via LFS sha256; `mailroom-cuad-contracts` re-exported in the payload-resolved shape (`input.image`/`input.pages[]` = `{type: image_file, file: …}` refs) and round-trip hash-matched with all 596 row→image references resolving on the Hub; `mailroom-lb-hearsay` round-trip hash-matched. Honest gaps recorded in `EXPORT_SUMMARY.json`: `mailroom-maud-contracts` + `mailroom-s1-corporate-records` exist in BT but hold zero rows; the other LegalBench/MAUD-classification streamer defaults were never created upstream — populate upstream first, then re-run export→publish. Braintrust stays READ-ONLY per AGENTS.md (`BRAINTRUST_LOGGING=disabled` preserved); no prompt constants touched.

- **Doc-type-aware scoring engine re-pin — `llm-dojo-scoring` `v0.6.0 → v0.7.0` (KANBAN-067, issue #32):** upstream adds `DOC_TYPE_BUNDLES` (one registry-validated metric bundle per processed document class: contract, corporate_record, due_diligence, correspondence, compliance_filing, court_opinion, insurance_claim, merger_agreement), the explicit-fallback `AgentProfile.resolve_doc_bundle()` honesty resolver (degrades to task bundles with a `used_fallback=True` marker, never silently), and the 23rd agent profile `insurance_claims_specialist` (companion to llm-mailroom's insurance_claim class, mailroom commit `99536d8`). Honest-gap mandate honored in-code: MAUD-derived merger scorers, Enron-derived correspondence scorers, and DE-SynPUF-grounded claims scorers are declared PENDING in their bundle descriptions rather than invented; contracts (CUAD) and court_opinions (LegalBench) ship real type-specific metrics today. Also fixed a pre-existing drift: `requirements.txt` still pointed at `v0.4.0` (comment said v0.1.2) while pyproject was at `v0.6.0` — both now consistent at `v0.7.0`. Consumer venv verified on 0.7.0 (`direct_url.json`: tag v0.7.0 @ `51822bc`); bridge imports (`field_scoring`, `metrics`, `scorers`, `cost_models`, `bootstrap`) resolve clean; full suite **561 passed / 6 skipped**, unchanged. No prompt constants touched.

- **True-GEPA upgrade of the prompt-engineer agent (KANBAN-066, issue #31):** `.opencode/agents/prompt-engineer.md`'s GEPA sections rewritten to be source-true to [gepa-ai/gepa](https://github.com/gepa-ai/gepa) @ `b265bf9ca77fd8e8d82039d9f74911b8780fe1ce` (2026-08-19) — mechanics extracted from the engine source (`strategies/acceptance.py`, `candidate_selector.py`, `component_selector.py`, `batch_sampler.py`, `proposer/merge.py`, `proposer/reflective_mutation/reflective_mutation.py`, `core/state.py`, `api.py`), not paraphrased from the paper. The 5-step folklore loop is now the engine's real 9-step iteration: Pareto parent selection (`ParetoCandidateSelector` default / CurrentBest / EpsilonGreedy / TopKPareto — sample among frontier members, not always the champion), seeded epoch-shuffled minibatch sampling, full-trace ASI capture, reflection-dataset construction (separate `reflection_lm`, `skip_perfect_score=True`), component-scoped proposal (`RoundRobin` default vs `All`), same-minibatch child evaluation, the **`StrictImprovementAcceptance` gate** (accept iff sum(child) > sum(parent) on the SAME minibatch; `ImprovementOrEqualAcceptance` = labeled lateral moves), frontier recompute across `frontier_type` instance/objective/hybrid/cartesian (repo practice = hybrid), and system-aware merge as a scheduled event with the four source-true preconditions (common ancestry, validation-support disjointness `merge_val_overlap_floor=5`, composable shared components, accept iff score >= max(parents)). Phase 5 gains per-cell dominance semantics (`get_pareto_front_mapping`) and a rejected-mutation ledger doctrine (rejections are frontier signal). Governed workflow untouched: version-key identity, same-surface A/B, noise floor, chunked surfaces, board discipline all preserved. New sidecar `.opencode/agents/PROMPT_ENGINEER_GEPA_PROVENANCE.md` pins the upstream ref, license (Apache-2.0, names/behavior referenced only — no code vendored), per-file source map, and re-sync recipe. New `tests/test_prompt_engineer_gepa.py` (12 network-free tests, green): pins every class name/default/frontier-type/merge fact in the agent file, cross-checks agent↔provenance consistency, and asserts the governed-workflow markers survived the rewrite. Tooling/docs-only; no pipeline, prompt-constant, or dependency changes.

- **Vendored Graphify agent skill → `.opencode/skills/graphify/` (KANBAN-065, issue #30):** the official opencode agent skill from [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) (upstream `v8` @ `b2cd362`, Apache-2.0/MIT) copied verbatim — `SKILL.md` (the `/graphify` build/query/path/explain/update workflows) + 8 `references/` sidecars — alongside a PROVENANCE.md noting source ref, license, and re-sync steps. Gives every coding agent working here a deterministic knowledge-graph workflow over the codebase for future use (no runtime dependency added until someone actually installs the `graphifyy` CLI and builds a graph). Network-free consistency tests (`tests/test_graphify_skill.py`, 5 passed) pin the structure and keep the llm-mailroom copy byte-identical.

## [v0.19.1] - 2026-08-21
### Changed
- **Dependency re-pin — `llm-dojo-scoring` `v0.5.1 → v0.6.0` (KANBAN-062/063 support, issues #28/#29):** upstream added the review/audit profile registry this release train's new pipeline agents resolve by name — `sorter_reviewer` (Lane A classification review, classification bundle) and `arbiter` (Lane B judgment arbitration, audit bundle, ground-truth-free), plus six per-specialist auditors (`contract_auditor`, corporate_records, due_diligence, correspondence, compliance, court_opinions). No prompt constants touched (append-only discipline unaffected); the eval loop's scoring surface is unchanged (v0.6.0 is purely additive over v0.5.1's 37/37 registry). Both consumer venvs verified on 0.6.0; llm-mailroom ships its Lane A/B build on this pin in mailroom v0.4.0.

## [v0.19.0] - 2026-08-21
### Added
- **Unified scoring layer adoption — `src/score_emitter.py` bridge + `llm-dojo-scoring` re-pin `v0.5.0 → v0.5.1` (KANBAN-061, human-approved option C, 2026-08-21):** the shared scoring package now owns the full metric infrastructure this repo emits through: `registry.py` (YAML-backed metric definitions, T0 exact/T1 score/T2 aggregate/T3 log tiers — every existing function mapped: f1/binary_metrics→T0, precision/recall/f2/jaccard/field_presence/laziness/cost→T1, confusion/failure-modes/bootstrap→T2, raw logs→T3; registry covers 100% of both consumers' emission surfaces incl. all 37 mailroom SCORE_CONFIGS names), `bundles.py` (classification/extraction/extraction_open/cost/factuality/laziness_detection/transcription/audit — the audit bundle is first-class for KANBAN-060's audit pass), `profiles.py` (agent profiles: sorter, 6 specialists, judge, boss, pdf_transcriber, image_extractor, archivist, audit_agent), `emitter.py` (unified score emitter with Langfuse + local sinks), `pruning.py` (tier-based dashboard filtering). Local bridge `src/score_emitter.py` (+ `tests/test_score_emitter.py`, 5 network-free tests): resolves the active agent profile → bundle → tier filter, emits through the package's unified emitter; calculations untouched (Hungarian matching, embedding rescue, bootstrap CI, CUAD equivalences all live upstream unchanged). Upstream releases: `llm-dojo-scoring` v0.5.0 (unified layer) + v0.5.1 (registry completeness); llm-mailroom migrated onto the same engine in its v0.3.2 (1,273-LOC duplicate replaced by a shim). Pin bumped v0.5.0→v0.5.1; venv verified on 0.5.1; bridge tests green; full suite 540 passed (7 pre-existing Quarto site-render failures unrelated — opencode's KANBAN-060 site lane render lag).

### Added
- **v39 + audit iteration (KANBAN-059/060, 2026-08-20):** A/B tested  vs  on 20-row chunked sample (seed 42): overall +0.0142 inside ±0.03 noise floor; key_obligations +0.1109 (11.09pp) substantial improvement promoting v39 as frontier arm key_obligations specialist.  A/B: recall-side champion (F2-lead), Pareto {v39 (P), audit (R/F2)}. Memo  documents diagnosis, root cause (emission-stage omission), and frontier selection. No code behavior change; documentation + iteration-close only.

### Added
- **Runner-level audit pass → `contracts_audit_v0` + `ContractsSpecialist.audit_extraction()` + `--audit` flag (KANBAN-060, human directive 2026-08-20: address the missed absent-family pairs through the most fitting methods)** — the diagnosed mechanism (645 absent (doc, category) pairs; 551/645 labels VERBATIM in the model's input; 523/591 in-text pairs get ZERO output for the category) is emission-stage category-selective omission: a single forward generation cannot re-read, and every prompt lever measured flat (v37 scan family, v38 named re-scan, v39 completion: absent 636→645). The fitting method is a **second structured call with missed-category feedback**: `CONTRACTS_AUDIT_PROMPT_V0` (registered in `PROMPT_VERSIONS`; 32 exact canonical category names; verbatim quote discipline; never-fabricate; ADDING-only; one entry per distinct clause sentence) + `ContractsSpecialist.audit_extraction()` — one audit call per extraction window (same `_split_chunks` windows; single-window docs = one whole-text call), input = window text + the canonical-tagged already-quoted clauses, `AUDIT_SCHEMA` = `{"missing_obligations": [{category, clause}]}` at temp 0.1; merge = UNION with normalized dedupe into `key_obligations` + canonical-tagged reasoning entries (`section_ref: audit-pass`, routing the KPI mapper); failing/parse-error windows skipped, never fatal; `_last_usage` sums extract + audit calls. Runner `--audit` flag (dry-run prints `audit=ON`; `parameters.audit` in the experiment-log record). Tests: `tests/test_audit_pass.py` (7 unit: union/dedupe, empty-answer noop, parse-error skip, multi-window usage accumulation, whole-text single window, schema contract, unlabeled-entry rejection) + 2 langfuse-runner smokes (`--audit` wiring + merged output in the record; off by default) — 105 surgical tests green. A/B LANDED on the same 255-doc surface (seed 42, chunked): `qwen3.7-flash_contracts_specialist_v39_audit_extraction_chunked_half` — **run KPIs recall 0.3627 / F1 0.4605 / F2 0.3963 / precision 0.6306 / false-nr 0.2388 / verbatim 0.371 / laziness 0.799 vs v39 (R 0.2833 / F1 0.4146 / F2 0.3244 / P 0.7727 / false-nr 0.3643)**; corrected per-doc paired gate (252 shared, seed 42, 2000 boots): **recall +0.0637 BEATS (P 1.000), F2 +0.0489 BEATS (P 1.000 — the F2-lead decision), F1 +0.0258 inside band (P 0.950, CI lower −0.0048), precision −0.0942 LOSES (P 0.000)**. Mechanism direct: absent positive pairs 612→399 (−34.8%). Audit-added clauses: 1,139/227 docs = 55 TP + 797 in GT-present categories (357 overlap a GT label; 440 are real sibling sentences CUAD partial-GT never sampled) + 342 GT-absent (fp) — the precision loss is predominantly GT-coverage reality, not fabrication (verbatim discipline held). **Cost consolidation (human directive 2026-08-20 "we have already input the whole contract text once"): the audit call reuses the extraction system prompt + byte-identical user prefix (verified in tests), so the re-read hits OpenRouter's automatic context cache (qwen3.7-flash cache-read $0.006/M vs $0.03/M fresh = 20%) → next audit run ≈ $0.33-0.35 vs the pilot $0.49 (12.2M prompt tokens vs v39 5.84M).** Verdict: audit = new recall-side champion (F2-lead); v39 = precision champion; Pareto = {v39 (P), audit (R/F2)}.
- **Maximize-everything crossover → `contracts_specialist_v39` (KANBAN-059, human directive 2026-08-20: improve recall AND precision + F1 and F2)** — v39 = v37 (which embeds v36 + the payment fold; derivation chain v36→v37→v39 asserted) + 4 surgical `.replace()` edits, registered in `PROMPT_VERSIONS`. Measured substrate (255-doc half-corpus, CORRECTED scorer — whitespace-collapse + `<omitted>`-stripping landed in `load_master_gt`, all records re-scored): **v37 leads every recall-side metric** (F1 0.4170 / F2 0.3382 / R 0.3004 / P 0.6820 / J 0.4981 / false-nr 0.3260 vs champion v36 F1 0.4073 / F2 0.3243 / R 0.2855 / P 0.7107) but the per-doc paired gate is inside band (v37: +25 TP at +40 FP). **Per-category FP audit (corrected): Termination For Convenience = 53 fp — the largest fp category, all genuine model errors (term-of-agreement clauses, for-cause/default/product-discontinuation terminations tagged as convenience; the category has NO enumeration entry, only a guard-list name); Uncapped +5 fp (fee/royalty "CAPs" tagged as liability caps); Revenue/Profit +6 fp (service fees, cost-sharing); Price Restrictions fp only 13→14 under the corrected scorer; Third Party fp 31 = GT-label noise (disclaimer clauses ARE in-category per CUAD), NOT suppressed.** **Near-miss decomposition (v37, corrected): 556 = 371 multi-label under-quote (67%) + 88 sibling-sentence + 63 leading-phrase drop + 19 paraphrase + 15 dash-GT** — the 371 are NOT quote-style: 35% of positive pairs carry ≥2 GT clause sentences and the model quotes a subset (NETGEAR Insurance 3 clauses/2 quoted; Cap On Liability 9/3; label==span byte-identical for the quoted ones). Edits: (1) enumeration **entry 27 = Termination For Convenience** with the WITHOUT-CAUSE boundary + NEVER shapes (term/expiration clauses, default/breach/cause, regulatory/discontinuation) + measured 53/71 stat — the precision lever; (2) **money-family boundary clarifications** in the R2 payment block (a fee/royalty/price CAP is NOT a liability cap; service fees/cost-sharing are NOT Revenue/Profit Sharing; a price-change notice duty is not a Price Restriction unless it caps amounts or frequency); (3) **WITHIN-CATEGORY COMPLETION** in the grain rule (a category whose clause appears in several sentences is INCOMPLETE until EVERY distinct clause sentence is quoted as its own item, from its FIRST WORD through its final period — 35%/556-of-1,678 stats inlined); (4) R2 checklist strengthen (ONE item AND ONE reasoning entry PER DISTINCT CLAUSE SENTENCE). Precision risk of (3) ~zero (extra quotes land inside already-present categories; fp is GT-absent-category-defined). Contradiction check passed (entry 27's NEVER-shapes vs the v36 term rules; carve-outs don't touch Non-Compete/ROFR). Test `test_contracts_v39_payment_fold_precision_and_completion` — 64 prompt + 19 sweep + 12 smoke tests green; runner dry-run accepts v39 with the reserved name. Run name `qwen3.7-flash_contracts_specialist_v39_extraction_chunked_half` confirmed on the board; manifest `data/manifests/extract_v39_half.jsonl`; champion gate vs v36 — command returned to the human, run NOT launched. Prediction: P 0.68-0.72 / R 0.32-0.35 → F1 0.44-0.47, F2 0.36-0.39 (TFC boundary −20-30 fp; completion +40-100 TP).

### Fixed
- **GT/scorer artifact fix → ContractEval KPIs re-scored (KANBAN-058, the F1-chase lever): whitespace + `<omitted>` normalization in `src/contracteval.py::load_master_gt`** — the master-clauses GT stores clause spans with embedded `\n`/multi-space runs (1,416 cells) and `<omitted>`/`[omitted]` redaction markers (695 spans) that the verbatim containment predicate (`contracteval_classified`) can never match — measured **37% of the KPI FN mass on the 255-doc half-corpus (493/1,686 whitespace FN + 242 `<omitted>` FN) was GT-storage artifact, not extraction failure**. New `_clean_span()` collapses whitespace to single spaces and strips the redaction markers at GT-load time (the shared `llm_dojo_scoring` package is untouched — the normalization lives in the local GT pipeline). **Effect (re-scored stored records, no LLM spend): v34 F1 0.1331→0.1740, v35 0.1408→0.1777, v36 0.3277→0.4073 (recall 0.2187→0.2855, precision 0.653→0.7107), v37 0.3256→0.4170, v38 0.3108→0.4111; champion re-confirmed via the corrected per-doc paired bootstrap — v36 BEATS v34 (P 1.000), v36 vs v37/v38 inside band (v36 numerically ahead).** `backfill_extraction_kpis.py --refresh` recomputes KPI blocks under the corrected scorer (documented one-time re-scoring backfill); experiment-log md + site data regenerated. Tests `test_clean_span_*` / `test_load_master_gt_normalizes_artifact_spans` / `test_cleaned_gt_span_matches_model_output_verbatim` (16 contracteval tests green). The 18 literal-newline cells (unparseable literals) remain GT-data debt; the residual F1 headroom is now genuinely prompt-side (the sparse-family + payment + precision levers).

### Added
- **Sparse-family shape completion + named re-scan → `contracts_specialist_v38` (KANBAN-057, next F1 mutation on v36's WIN)** — v38 = v36 + 2 surgical `.replace()` edits (v36 byte-identical, derived chain asserted, registered in `PROMPT_VERSIONS`). Measured substrate (255-doc half-corpus, v36 record + master GT CSV, KPI-level fn decomposition over 1,686 positive pairs): **v36 FN 1,319 = 493 whitespace-artifact (GT-side `\n`/multi-space label runs — flagged to the scoring lane as KANBAN-058, NOT worked around in the prompt) + 242 `<omitted>`-placeholder GT labels (unfixable by any model) + 48 genuine near-misses + 536 ABSENT (no quoted span ≥0.7 token coverage)** — the prompt lever is the 536 absent pairs, concentrated in families the model never quotes: Post-Termination Services 55, Anti-Assignment 43, Cap On Liability 43, Minimum Commitment 37, License Grant 33, **Warranty Duration 32 (absent from the prompt entirely)**, Revenue/Profit Sharing 31, **Competitive Restriction Exception 29 + Volume Restriction 29 (guard-list names but NO shape entries)**, Covenant Not To Sue 25, Liquidated Damages 22, Non-Transferable License 20; shape-complete families (Covenant/Post-Termination/Liquidated) stay absent-heavy — the generic R2 checklist self-check does not fire, so the fix is a NAMED re-scan. Edits: (1) enumeration entries **27-29** — Warranty Duration (warranty-period clauses, real GT examples, "32 of 32 present clauses never quoted" stat), Competitive Restriction Exception (notwithstanding-carve-out shapes, "39 of 39" stat), Volume Restriction (quantity/amount ceilings, "35 of 39" stat); (2) **UNDER-QUOTED FAMILY RE-SCAN** sentence in the R2 completeness block naming the absent-heavy families (536/1686 stat inlined), placed after the ADDING-only discipline, adjacent to the never-fabricate guard. Precision risk ~zero (target families carry 0-6 fp on the surface); contradiction check passed (carve-out ≠ Non-Compete, Volume ceiling ≠ Minimum Commitment floor, re-scan tag spellings aligned to the guard list — `Joint Ip Ownership`). Crossover decision: v37's payment block NOT folded into v38 (measured F1-flat + precision regression 0.653→0.613 on the current scorer; its money quotes become assets post-KANBAN-058 — revisit as a v39 crossover). Test `test_contracts_v38_sparse_family_shapes` — 63 prompt + 46 sweep tests green; runner dry-run accepts v38 (255 rows, chunked 90k/8k, Langfuse llm-dojo). Run name reserved `qwen3.7-flash_contracts_specialist_v38_extraction_chunked_half`; manifest `data/manifests/extract_v38_half.jsonl`; champion gate vs v36 — command returned to the human, run NOT launched. Prediction: 80-130 new matched pairs → F1 0.328 → 0.37-0.40 (candidate win; conversion rate is the swing factor).
- **Payment/monetary capture + canonical tag discipline → `contracts_specialist_v37` (KANBAN-056, GEPA crossover built on v36's WIN)** — v37 = v36 + 4 surgical `.replace()` edits (+3,981 chars; v36 byte-identical) per the frozen design in `memos/contracts_specialist_v37_design.md`. Measured substrate (255-doc half-corpus, v34 record + master GT CSV, 255/255 normalized join): payment families are **297 of 801 (37%) present-but-untagged (doc, category) pairs** — Price Restrictions 0/9 tagged (+24 fp), Uncapped Liability 1/46, Volume Restriction 3/35, MFN 3/11; **78/255 docs collapse ALL key_obligations items under one field-level reasoning tag** (115 of the 297 misses; 50/78 of those docs contain emitted-but-untagged money items); **contract_value is never GT** (0/255 expected — the base-rate claim confirmed at record level) but predicted on 101/255 and **null on 113/255 docs that carry payment GT**. Edits: (1) **PAYMENT TERMS & MONETARY CLAUSES mandatory scan family** in the R2 completeness block — 10 money-clause shapes (Revenue/Profit Sharing, Minimum Commitment, Volume Restriction, Price Restrictions, Liquidated Damages, Cap/Uncapped Liability, Insurance, MFN, Post-Termination Services) each quoted at v36's full-sentence grain + tagged with its exact canonical category, measured examples inlined ("royalty equal to the Specified Royalty Percentage of all revenues received", "thirty percent (30%) of the Net Sales in excess of Eleven Thousand Dollars ($11,000) per calendar month", "not less than $1 million per occurrence", "nothing in this Agreement shall limit either party's liability"); (2) **canonical tag discipline** — never a field-level `key_obligations` entry, never a sibling/generic tag (a royalty is Revenue/Profit Sharing, NOT License Grant; an insurance limit is Insurance, not Cap On Liability), 78/255 collapse stat inlined; (3) **contract_value trigger extension** (rule 10) — a payment schedule ("$55,000 for First Contract Year"), a per-unit fee or royalty, a minimum commitment amount, or an aggregate consideration phrase ALL count as visible consideration (113/255 stat inlined); (4) Uncapped Liability (entry 21) + Liquidated Damages (entry 23) enumeration appends (entries 10-13 already carried the shapes). Section targets disjoint from v36's grain/term_length/effective_date edits; one-pass preserved; contradiction check passed (payment block additive-only; "a fee or payment amount alone is NOT a price restriction" resolves the 24-fp Price-Restrictions confusion). Test `test_contracts_v37_payment_monetary_capture` — 62 prompt tests + 15 sweep tests green; runner dry-run accepts v37; registered in `PROMPT_VERSIONS`. Run name reserved `qwen3.7-flash_contracts_specialist_v37_extraction_chunked_half` (255-doc half-corpus A/B vs v36 pending — command returned to the human, run NOT launched).
- **Full-sentence span-grain reconciliation → `contracts_specialist_v36` (KANBAN-056, GEPA iteration after the v34/v35 half-corpus A/B)** — v36 = v35 + 7 surgical `.replace()` edits resolving the **fragment-grain rule_contradiction** that v34/v35 inherited from the v10-era rules ("ATOMIC FRAGMENTS … typically 10-25 words", "STRIP sentence preamble and riders", "a list of a few long merged sentences signals missed spans: split them" vs v34's R3 verbatim rule). Measured substrate (sim-matrix over the shared 255-doc surface, expected-vs-predicted containment): key_obligations 1600 labels → MATCH 572 / NEAR 448 / MISS 580, with **146/448 NEAR = PURE TRUNCATIONS** (predicted item a head-prefix of the GT sentence; 88–93% of predicted tokens inside GT) + 265 ellipsis-condensed overlaps — the model follows the concrete fragment instruction and drops sentence continuations, which containment scoring can never reward (GT label = the annotator's stored clause sentence). v36 edits: (1) fragment grain → **FULL CLAUSE SENTENCE grain** (one item per distinct sentence, quoted verbatim in full, never per-right fragments, never ellipses — with the measured 146-of-448 truncation stat and the Bunker One / Licensee examples inlined); (2) SPAN-DISCIPLINE completion reframed to full-sentence grain; (3) R3's "trim to the 10-25-word operative core" → complete-sentence quoting; (4) SIZE-CALIBRATION reframed (split MERGED MULTI-SENTENCE items, never a sentence itself); (5) v35's ITEM-LEVEL CATEGORY GUARD kept but re-cast to full-sentence quoting per duty (dedupe within category only — no contradiction remains); (6) **term_length duration-only guard** ("two (2) years" with no clause = a MISS; measured 16/208 term_length expectations on v34 were duration-only; v35's paired term_length 0.7580 vs v34 0.8006, CI [0.004, 0.102]); (7) **effective_date blank-placeholder carve-out** (a "April __, 2005" blank is NOT a stated date → null, never a fabricated fill; the scorer satisfies blank-template expectations with null — 5/16 effective_date misses on v34 were fabricated fills). v0-v35 byte-identical; `CONTRACTS_SPECIALIST_PROMPT_V36` registered in `PROMPT_VERSIONS`; test `test_contracts_v36_full_sentence_grain` (61 prompt tests green; runner dry-run confirms the version). Memo `memos/contracts_specialist_v36.md`; run name reserved `qwen3.7-flash_contracts_specialist_v36_extraction_chunked_half` (255-doc half-corpus A/B vs v34 pending).
- **One-pass extraction: item-level category split → `contracts_specialist_v35` (KANBAN-055 — the THIRD anti-collapse lever)** — built on opencode's v34 (KANBAN-054): v34 added R1 field-presence self-check + R2 category-level completeness + R3 verbatim GT alignment (structural/category-discipline); v35 closes the third collapse mode neither of those targets — **ITEM-LEVEL CATEGORY COLLAPSE**, where a single `key_obligations` item holds duties from TWO different canonical categories (e.g. "Neither Party shall assign this Agreement nor use its trademarks" folds Anti-Assignment into Non-Disparagement/IP Ownership), routing to one category and scoring 0 on the other (measured ~15,516/33,312 umbrella-tagged entries on the stored v31/v32 reasoning corpus that drove KANBAN-051). **v35 = v33/v34 base + ONE surgical append** (`CONTRACTS_SPECIALIST_PROMPT_V35`): one ENTRY per distinct category's duty within a clause (a two-category clause emits one entry per duty, each tagged with its OWN canonical category name, quoting that duty's operative words), and EXACT-category tagging only — never a sibling / family / generic 'IP' (explicitly: 'No-Solicit Of Customers' ≠ 'No-Solicit Of Employees', 'Cap On Liability' ≠ 'Uncapped Liability', a license grant ≠ generic 'IP'). Registered in `PROMPT_VERSIONS`; test `test_contracts_v35_item_level_category_split` (full prompt file green). Rebased onto `origin/main` KANBAN-054 with a clean rename (the earlier local v34 name-collision resolved to v35 + KANBAN-055; opencode's v34 kept). Board KANBAN-055 + discussion post. **A/B vs v34 (50-doc chunked surface) held for the human per directive** — v35 is code-complete + unit-verified, not yet empirically A/B'd.
- **Extraction agent anti-collapse prompt `contracts_specialist_v34` + ContractEval-rubric KPIs as core extraction metrics (KANBAN-054, human request)** — (1) **prompt v34** = v33 + THREE surgical rules (human decision 2026-08-19: verbatim-at-span-grain formulation): **R1 FIELD-PRESENCE SELF-CHECK** (a schema field is null only when the document genuinely does not state it; `contract_value` = the consideration clause quoted verbatim — never null when a consideration/price/"$" phrase is visible; targets the v32@510 presence lows: contract_value 0.39, renewal_terms 0.37, effective_date 0.88, term_length 0.83; additive only); **R2 CATEGORY-LEVEL COMPLETENESS** (post-extraction checklist over the 32 canonical CUAD YES/NO categories — a category present in the text with zero canonical-tagged items/entries is INCOMPLETE, scan back and ADD, never fabricate; targets the mapping benchmark's dominant failure: 67% of present categories produced no mapped item, 42.7% of positive pairs covered ≥0.7); **R3 VERBATIM QUOTING at the GT span grain** (quote word-for-word — the GT label is the clause's own text; a paraphrase scores as a miss; cut preamble/riders, never reword the remainder; targets the 9.2% verbatim vs 42.7% ≥0.7 paraphrase penalty). (2) **KPIs** — `scores.contracteval_kpis` on EVERY extraction run record (`src/contracteval.py::run_kpis` = `evaluate_record` + `coverage_bands` over the run's own rows vs the committed master GT, injected in `run_extraction_eval.py::log_experiment_to_repo` — both extraction runners; offline, deterministic, best-effort like `diagnostics`): ContractEval's exact rubric — accuracy/P/R/F1, **recall-weighted F2**, token-set Jaccard over positive pairs, no-related + false-no-related rates, n_pairs/n_positive/n_docs/unjoined — plus the semantic coverage bands (verbatim / ≥0.7 / ≥0.5 / ≥0.3). Human decisions (2026-08-19): KPIs ADD alongside existing metrics with **F2 leading** (the honest axes for a one-pass extractor: precision structurally 1.0); A/B on the **50-doc chunked surface only** (full-corpus KPI baseline stays v32). Experiment-log renderer (`_contracteval_kpis_lines`), site trends keys (`build_trends`: f1/f2/jaccard_mean/false_no_related_rate/recall/semantic_ge0_7/semantic_verbatim/kpi_n_pairs) + a new F2/Jaccard/semantic/false-nr KPI trend chart in `docs/assets/site.js` (render audit re-run on the next site regen), and `scripts/reporting/backfill_extraction_kpis.py` (documented one-time backfill for the eval machine's historical records). Verified on the stored v32@510 record: F1 0.1579 / F2 0.1049 / Jaccard 0.2129 / false-nr 0.6818 / semantic ge0.7 0.4332 (consistent with the mapping memo). Tests: `test_contracts_v34_anti_collapse_rules` (58 prompt tests green), `test_run_kpis_block` + `test_run_kpis_empty_record_degrades`, `test_extraction_kpis_land_in_record` (hermetic master GT). Memo `memos/contracts_specialist_v34.md`. **A/B runs pending on the eval machine** (keys + local log): `qwen3.7-flash_contracts_specialist_v{33,34}_extraction_sample5_chunked` pilots, then `_extraction_chunked_50` (seed 42, `--chunked`); site data regen + render audit follow the A/B + backfill there.
- **ContractEval GEPA iteration 5 → `contracteval_v5` (the fragment synthesis) + gpt-4.1-mini cost model (KANBAN-052)** — v5 = v4 + ONE surgical replace: the sentence-granularity tail ("otherwise quote the complete sentence(s), never a fragment of a sentence") deleted in favor of an explicit fragment permission — any contiguous run of the original text (sub-sentence fragment to several sentences), provided it contains every word of the complete answer and no more text than the answer needs, with every part of a multi-part answer included; the verbatim character-for-character rule (the TP engine) and the bounded trigger are untouched. Motivation (5-run A/B, identical 4,182 rows, qwen3.7-flash, temp 0): the smallest-span rule fired only at the extremes (100 FP→TN; J 0.06→1.0 wins) while 1,310/1,567 shared quotes stayed byte-identical to v3 — sentence-granular quoting is the Jaccard drag (v4 J 0.533 vs v2's 0.648); the 51 TP→FN losses are 19 partial multi-span rows + 29 wrong spans + 3 refusals. Paired-row projection on real rows: TP 815–840, J 0.62–0.645, F1 0.560–0.574, F2 0.612–0.628, false-nr ~0.035. New `openai/gpt-4.1-mini` cost model in `config/taxonomy.yaml` (input 0.4 / output 1.6 per M) for the research-funding cross-model runs. Site data regenerated (docs/data, 203 runs). Tests `test_contracteval_v5_derived_fragment_permission` (58 prompt tests green).
- **ContractEval v0 benchmark — qwen3-8b on a local vLLM (single RTX A5000), full 4,182-pair test set (KANBAN-052 cross-model data point)** — the directly-mirrored run COMPLETE on the node's local vLLM serving `models/Qwen3-8B` (`--served-model-name qwen3-8b`, `OPENROUTER_BASE_URL=http://localhost:8000/v1`, dummy key): **F1 0.5646 / F2 0.5313 / Jaccard 0.1454 / false-nr 0.1367 (paper 0.1367)**, 4,182/4,182 rows, 0 errors, temp 0, `contracteval_v0` prompt, input cap 129,000 chars (the 8 giant contracts > 129k chars get head+tail truncation; the other 94 stay faithful full-context), max_tokens 5000, concurrency 40, 25.8M tokens (23.98M prompt / 1.83M completion), `rows_with_usage` 2,681. Confusion TP 899 / TN 2305 / FP 769 / FN 345; accuracy 0.7654 / precision 0.6303 / recall 0.5113; per-category: Document Name F1 0.980 best, Agreement Date 0.925, Parties 0.828; zero-F1 categories are the sparse ones (Source Code Escrow 1 positive, Price Restrictions 0, Most Favored Nation 3, Affiliate License-Licensor 6). **Table III positioning vs the paper's 19-model table: F1 0.565 beats the paper's own qwen3-8b (0.530) and qwen3-8b-thinking (0.540) — our F1 #9 of 20; F2 0.531 #9; Jaccard 0.145 well below the paper's qwen3-8b 0.340 (Jaccard gap driven by over-quoting on positives — the known v0 bloat pattern, same root cause as the qwen3.7-flash v0 0.5058 → v1+ iterations).** The node-side `agents/base_agent.py` client timeout was raised 120→600 s for 40-way concurrency on the local server (the 120 s default timed out queued 30k-token requests — zero server-side errors; edit is node-local, not committed). New experiment-log record `qwen3-8b_contracteval_v0_contracteval_langfuse` (task `contracteval`, git `2f9d416` dirty); `reports/contracteval_benchmark.{md,json}` regenerated with the run in the Table III comparison + per-category breakdown; experiment log md + site data rebuilt (203 records).
- **Full ContractEval v0 benchmark — qwen3.7-flash on the 4,182-pair test set (KANBAN-052) + GEPA iteration 1 → `contracteval_v1`** — the directly-mirrored run COMPLETE: **F1 0.5541 / F2 0.6164 / Jaccard 0.5058 / false-nr 0.0289 (paper 0.0289)**, 4,182/4,182 rows, 0 errors, temp 0, faithful full-context, 42.7M+8.5M tokens, `cost_estimated_usd` 2.3868; confusion TP 829 / TN 2019 / FP 919 / FN 415. Table III positioning: F1 #4, F2 #3, **Jaccard #1 (tied gemini-2.5-pro 0.506)**, false-nr #2 — `scripts/reporting/run_contracteval_report.py` writes `reports/contracteval_benchmark.md` (pooled vs the 19-model table + per-category Fig-4 analogue). **GEPA iteration 1** (`contracteval_v1` in `src/prompts.py`, registered in `PROMPT_VERSIONS`, tests `test_contracteval_v1_derived_scope_discipline`): ONE lesson mined from the failure data — FP over-quoting (31.3% of 2,938 negatives; median 97 tokens; precision 0.474), Jaccard bloat on positives (425/829 TPs >2× GT, p90 20×; Agreement Date median 14.9×), 220 partial-overlap FNs = same selection fuzziness → **"Quote the smallest span of the Context that states the complete answer"** (append-derived; v0 byte-identical; "No related clause." contract untouched — false-nr stays at paper level). **Phoenix annotations**: `src/phoenix_tracing.py` now emits OpenInference `annotations.*` attributes (name/score/label correct|incorrect/`annotator_kind=CODE`) from every `score()` call (agent + document spans), plus `hide_input_text` on the OpenAI instrumentation (Goldilocks payload bound — the 300k-char contexts no longer balloon the local DB); the full v0 run's 4,282 spans backfilled post-hoc via the Phoenix client SDK (`contracteval` + `jaccard` CODE annotations). Runner: `sorter.agent_name` relabeled `contracteval` (plain-LLM carrier — trace/log inspection can no longer be mistaken for sorter classification).

### Added
- **ContractEval GEPA iterations 2–4 + first cross-model run — the 5-way funded A/B series (KANBAN-052)** — same 4,182-pair surface, qwen3.7-flash temp 0: **v1** (smallest-span lesson) F1 0.5406 / F2 0.5759 / Jaccard 0.6081 / false-nr 0.045 (TP 749 / FP 778 / FN 495, $2.19) — paired vs v0: FP→TN 190 held, but 118 v0-TPs lost (72 with v0 Jaccard ≥ 0.5); **v2** (trigger carve-out + complete-quote) F1 0.5349 / F2 0.5608 / **Jaccard 0.6479** / false-nr 0.0426 (TP 721 / FP 731 / FN 523, $2.18) — recovered only 27/118 refusals, reverted 56/190 FP fixes, +87 new FPs; **v3** (verbatim character-for-character + whole-sentence-when-doubt) F1 0.5550 / F2 0.6140 / Jaccard 0.5258 / false-nr 0.037 (TP 822 / FP 896 / FN 422, $2.33) — quote fidelity recovered 132 TPs but the doubt-bias re-bloated (paired J −0.095, +208 TN→FP). The 4-run oscillation (bloat ↔ fragment) diagnosed: verbatim quoting wins TPs, smallest-complete-span wins Jaccard — **v4 = v3 minus doubt-bias + v2's smallest-complete-span rule (quote VERBATIM and SMALL)**, projected F1 0.574–0.592 / J 0.634–0.640 (simulated on real paired rows). **Cross-model: `openai/gpt-4.1-mini` × `contracteval_v1` FULL surface COMPLETE: F1 0.6562 / F2 0.6675 / Jaccard 0.4674 / false-nr 0.0844 (TP 840 / TN 2462 / FP 476 / FN 404)** — beats the paper's own gpt-4.1-mini (0.644) and every qwen version on F1, but bloat pattern (lowest Jaccard of the series). All versions logged in `reports/contracteval_benchmark.md` via `run_contracteval_report.py --all`. New prompts `contracteval_v2/v3/v4` in `src/prompts.py` (append-derived, v0/v1 byte-identical, banners cite the run tables; tests `test_contracteval_v2_derived_trigger_carveout` / `..._v3_derived_quote_fidelity` / `..._v4_derived_verbatim_smallest_span`). GEPA iterations 2–4 via the prompt-engineer agent: iteration 2 mined 107/118 TP→FN as fragments not refusals; iteration 3 FALSIFIED the trigger-restoration hypothesis (149/160 lost TPs are re-typing/whitespace/case failures; 8-vs-268 refusal arithmetic); iteration 4 quantified the oscillation and the synthesis.

### Fixed
- **ContractEval runner debugged + Phoenix made a REAL trace sink (KANBAN-052)** — the directly-mirrored benchmark's run path fixed end-to-end: (1) **missing dependency** — `llm-dojo-scoring@v0.4.0` (the canonical `contracteval` evaluator) was pinned but not installed in the venv, so `run_langfuse_contracteval_eval.py` crashed at import (`ModuleNotFoundError`); `pip install -e .` re-pulls it. (2) **`src/phoenix_tracing.py` emitted NOTHING** — the handles were no-ops and no instrumentation was ever enabled; it now opens a REAL root OTel span per document (`trace_document`) with session/tags/filename/expected/metadata attributes, a nested agent span (`agent_observation`), records outputs + deterministic scores as span events (`set_output`/`score`), best-effort instruments the OpenAI SDK (`OpenAIInstrumentor`, already installed) so every LLM call lands as a nested span with full prompt/response/token usage, and `flush()` force-flushes instead of permanently shutting the provider down. (3) **runner fixes** — new `--tracing-backend {langfuse,phoenix}` flag (default `langfuse`) wired to `resolve_tracer(prefer=...)`; the paper's plain-call convention restored by killing the sorter's `_reasoning_effort="medium"` leak (thinking mode would have deviated from the mirror + burned tokens); manifest-resumed rows now re-derive classification/jaccard/said_no_related from the stored output instead of carrying stale zeros; pairs are dispatched **grouped by contract** (stable sort by title, id) so each contract's 41 calls share the identical full-context prefix — OpenRouter's automatic prompt cache serves the repeated prefix at ~10% of input price, a large saving on the 300k-char contexts with ZERO deviation from the paper's one-call-per-pair methodology. Tests: new `tests/test_phoenix_tracing.py` (4, network-free, fake in-memory tracer) + `test_runner_smoke_contracteval_phoenix_backend` (tracing_backend=phoenix record, contract-grouped dispatch order, no reasoning-effort leak) + `tests/test_tracing.py` fallback test made independent of the local `langfuse.env`; 23 surgical tests green. **Pilot (qwen3.7-flash, `contracteval_v0`, 100 pairs / seed 42, Phoenix sink, default key): F1 0.4578 / F2 0.5053 / Jaccard 0.3433 / false-nr 0.1143 (paper-denominator 0.0032)**, 100/100 rows OK, ~$0.07 — Phoenix verified holding 100 doc traces + 100 agent spans + 100 LLM spans with outputs, classification/jaccard scores and token usage; full 4,182-pair benchmark run initialized (manifest-resumable, `data/manifests/contracteval_qwen_benchmark_full.jsonl`).

### Added
- **Directly-mirrored ContractEval task — replicate the arXiv 2508.03080 benchmark as a first-class eval (KANBAN-052 / issue #22)** — build stage (run later): (1) **dataset builder** `scripts/datasets/build_contracteval_testset.py` — the CUAD **test split** (`theatticusproject/cuad-qa`, the exact `test.json` the HF loader downloads): 4,182 (contract, question) pairs / 102 contracts / 41 categories into `data/contracteval/contracteval_test.jsonl` (pairs, compact) + `contracteval_contracts.jsonl` (FULL 645–300,768-char contexts, stored once) + committed `questions.json` (41 category→question) + `testset_summary.json`; **positives = 1,244 = the paper's hardcoded false-rate denominator** (the paper reports 4,128 total — a 54-negative-row-smaller snapshot of the same file; the positive set is identical); (2) **versioned prompt `contracteval_v0`** = the paper's system prompt VERBATIM + `CONTRACTEVAL_USER_TEMPLATE` (Context:/Question:), registered in `PROMPT_VERSIONS` for the GEPA iteration loop; (3) **canonical ContractEval evaluator UPSTREAM in `llm-dojo-scoring` v0.4.0** (new `contracteval` task kind: `get_jaccard`/`said_no_related`/`contracteval_classified`/`contracteval_metrics` mirroring `Evaluation.py`+`open_source_model.py` exactly — verbatim-containment TP, F1/F2/acc/prec/recall, token-set Jaccard over positives, no-related rate, false-no-related rate over BOTH the run's positives and the paper's 1,244 denominator, per-category breakdown; 8 upstream tests; `src/contracteval.py` metric math reconciled to a thin shim); (4) **dedicated runner** `scripts/eval/run_langfuse_contracteval_eval.py` — faithful full-context (one call per pair, temp 0, max_tokens 5000, `--max-input-chars 0` = no cap), manifest resume, Langfuse/Phoenix traces (observation `contracteval` with classification + Jaccard scores), ONE append-only experiment-log record (`task: contracteval`, pooled + per-category scores, per-row outputs/labels/classification); (5) **report tooling** `scripts/reporting/run_contracteval_report.py` (offline) — our runs vs the full **19-model Table III** reference + per-category (Fig-4 analogue). Tests `tests/test_contracteval_task.py` (5, network-free: builder units + runner smoke with mocked LLM + report). Docs: AGENTS.md cheatsheet, README eval section, SCORING.md contracteval section, data/contracteval README + scripts README.
- **key_obligations scoring bottleneck fixed — disaggregation + category-presence routing + reasoning-trace retag (KANBAN-051 / issue #21)** — (1) **disaggregate clause spans before scoring** (`run_extraction_eval.py` now preprocesses `key_obligations`/`termination_clauses` through the upstream `disaggregate_clause_spans` before `score_extraction` + `score_category_presence`, so a merged multi-clause item no longer dilutes the 0.6 bipartite match below threshold — the stored `predicted` keeps the raw model output, with `disaggregated_counts` in the composite for audit); (2) **reasoning-trace RETAG** — new prompt `contracts_specialist_v33` = v32 + the RETAG RULE: obligation `reasoning.entries[].field` must be the canonical CUAD category name (the 32-category vocabulary enumerated; the `key_obbligations` misspelling explicitly guarded) instead of the umbrella `key_obligations`, fixing the misattribution where `category_presence_detail` evaluated generic obligations against categories like Anti-Assignment (measured on the stored v31/v32 corpus: 15,516 of 33,312 entries carry the umbrella tag); (3) **upstream `llm-dojo-scoring` v0.3.0** — `score_category_presence` routes each YES/NO category to the reasoning-trace entry tagged with the canonical category name (else to the disaggregated spans of its mapped field) and matches by token containment (≥ 0.7) or embedding similarity (≥ new `presence_embedding_threshold` 0.7); new `disaggregate_clause_spans` + `_split_clause_spans` helpers; upstream suite 144 passed, pushed + tagged `v0.3.0`; dep re-pinned in `pyproject.toml` + `requirements.txt`.
- **ContractEval mapping scorer — benchmark our previous runs against ContractEval Table III (arXiv 2508.03080, KANBAN-051)** — new `src/contracteval.py` + `scripts/reporting/run_contracteval_mapping.py` (offline, free): loads the full per-category clause spans from the committed `data/cuad/master_clauses.csv`, maps each disaggregated predicted span to the CUAD category it covers (reasoning-trace routing → verbatim label containment → best containment ≥ 0.5), synthesizes the per-category answer, and applies ContractEval's EXACT rubric (TP = every GT label span verbatim-contained in the answer; token-set Jaccard over positive pairs; false-"no related clause" rate). **Results on the full-corpus champion runs**: qwen3.7-flash v32 F1 0.164 / F2 0.109 / Jaccard 0.215 / false-nr 0.670 (v31 ≈ identical); llama-4-scout v31 F1 0.034 — far below ContractEval's GPT-4.1 (F1 0.641). The `coverage_bands` companion shows the gap is a **paraphrase penalty, not missing extraction**: the champion covers 42.7% of positive-label pairs at containment ≥ 0.7 vs 9.2% verbatim. Report `reports/contracteval_benchmark.md` + memo `memos/contracteval_mapping_benchmark.md`; tests `tests/test_contracteval.py` (network-free).
- **Monte Carlo simulations folded into the GEPA loop as a champion-contender selection layer + half-corpus effectiveness pilot (KANBAN-049, issue #17)** — `scripts/reporting/monte_carlo_gepa.py` adds a formal GEPA selection step: for every ordered prompt-version pair on a model, per-document deltas over the SHARED surface are paired-bootstrapped (n_boot 2000, seed 42) → mean Δ, 95% CI, P(A beats B); a version *beats* a peer when the CI excludes zero AND P(win) ≥ 0.9 (the noise-floor contract); the **MC champion contender** is the version with the most wins (tiebreak by aggregate accuracy), and a **plateau** verdict when no version beats any peer. The layer adds committee-voting robustness @ K for the contender and a **document-count sweep** (25/50/75/100%) for the effectiveness pilot (`--sample 0.5` = half-corpus pilot). **Pilot results (qwen3.7-flash):** subtype — full corpus selects `sorter_v15` (0.9506, tied with v13 at 7 wins, tiebreak by accuracy), the **seeded 50% sample (254 shared docs) recovers the same champion**, 25% (127 docs) collapses to plateau (P(win) 0.021, CI touches zero) → the sample-efficiency boundary sits between 25% and 50%; docclass — **plateau at every fraction** (v6-vs-v3 full-676 +0.0015, CI [+0.0000, +0.0044], P(win)=0.637 — the noise-floor gate correctly refuses to crown v6, matching the same-surface A/B verdict). Reports `reports/monte_carlo/gepa-champion-contender-{subtype,docclass}_classification[-sample50%].md`. Tests `tests/test_monte_carlo.py` grow to 14 (13 passed + 1 skip; new gepa scenario smoke + clear-winner selection test + the committed gepa report added to the reproducibility drift-guard). Memo `memos/monte_carlo_gepa.md`. Issue #17 closed.
- **Monte Carlo simulation suite — zero-spend what-if analysis over the joint reasoning corpus (KANBAN-048, ported per issue #17 from the RVL-CDIP-classifier's `monte_carlo_*` suite)** — `src/monte_carlo.py` (shared helpers: `normalize_dist`/`shannon_entropy`/`majority_margin`/`draw_committee`/`bootstrap`/`paired_delta_bootstrap`/`uncertainty_phrases`/`confidence_score`/`save_figure`/`style_axis`, per-task label vocabularies from `agents/sorter_agent.py`, free-form-reasoning near-miss detection); `scripts/reporting/monte_carlo_corpus.py` builds the joint corpus (`reports/monte_carlo/corpus.jsonl`, gitignored — 17,691 rows: 16,162 subtype + 1,442 docclass + 80 chained + 7 sorter, 99.7% with reasoning) + `corpus-summary.md`; `monte_carlo_ensemble.py` — committee accuracy(K) with bootstrap CIs (subtype 0.9209 → 0.9513 @ K=25; doc_type saturated at 0.9928) + confidence blend + escalation Pareto (subtype +0.44 pp @ alpha 0.15 to a 0.95 model; docclass escalation loses — baseline already 0.9928) + `escalation_candidates-<task>.txt`; `monte_carlo_prompt_ablation.py` — paired-bootstrap gate over 156 subtype + 12 docclass (model, A, B) pairs on shared docs (sorter_v10/v11 vs v3 +14.1 pp P(win)=1.000; docclass v5 loses to v3/v4/v6 on the diag-30 slice); `monte_carlo_failures.py` — retry/fallback event simulation from the observed 0.2374% failure rate (max_tries=1 + fallback → 0.004%, without → 0.202%), 1K/25K/320K extrapolation with tail risk; `monte_carlo_exemplars.py` — confusion-pair near-miss mining (268 maintenance→license / 212 development→license traces) + Monte Carlo subset selection under a token budget → 6 subtype + 4 docclass exemplar appendices; `monte_carlo_verify.py` — spend-minimal verification recipe printing the exact eval commands (dry-run default; `--run-eval` is the only spend). Memo `memos/monte_carlo_robustness.md`; tests `tests/test_monte_carlo.py` (12, network-free: helper units + per-scenario smokes on a synthetic corpus + committed-output reproducibility). No model spend.
- **Full Phoenix local trace sink documentation + cost-efficiency configuration cemented (KANBAN-046 / issue #18)** — new `wiki/Phoenix-Tracing.md` (linked from `wiki/Home.md` + `_Sidebar.md`) documenting the local Arize Phoenix trace sink (Langfuse-primary resolution with Phoenix fallback via `src/tracing.py::resolve_tracer`, OTLP HTTP spans, SQLite store, discard-by-delete) and the **resume / checkpoint / queue / cache** cost-efficiency configuration: manifest resume + header contract (`src/evaluation.py::ManifestStore` — never resume a stale manifest), append-only experiment-log checkpoint, HITL annotation queue (`run_annotation_queue.py`), embedding-cache reuse + manifest-replayed-rows usage accounting, and the `--dry-run` / `assert_production_run` / `--research-funding-key` cost gates. `config/environments/.env.example` gains the documented Phoenix section (`PHOENIX_TRACING`, `PHOENIX_ENDPOINT`, `PHOENIX_SERVICE_NAME`, `PHOENIX_PROJECT`, `PHOENIX_SESSION`, `LANGCHAIN_TRACING_V2`, `OTEL_EXPORTER_OTLP_ENDPOINT`); the AGENTS.md tracing section points at the wiki; drift-guard test `test_env_example_documents_phoenix_sink` in `tests/test_env_utils.py` pins the template surface.
- **llm-dojo-scoring v0.2.0 — task-aware scoring across the additional document hierarchy (KANBAN-047 / issue #19)** — upstream package extended and re-pinned (`llm-dojo-scoring @ git+…@v0.2.0` in `pyproject.toml` + `requirements.txt`): new `llm_dojo_scoring.tasks` module with a `score_task()` dispatcher + task-aware normalization covering **MAUD** (merger-agreement doc-class + consideration-type subclass with strict/equiv scoring, per-question classification), **LegalBench** (binary Yes/No exact-match + per-class + binary P/R/F1), **multi-classification** (macro/micro + confusion), **court opinions** (court_opinion doc-class), and **chained evaluation runs** (`chained_composite` / `chained_summary`, sorter+extractor weighted 0.25/0.75); `config.py` gains the task registries (`DOC_CLASS_KEYS`, `MAUD_CONSIDERATION_*`, `LEGALBENCH_BINARY_LABELS`, `COURT_OPINION_CLASS`, `TASK_KINDS`); 10 new network-free tests (upstream suite 144 passed; pushed + tagged `v0.2.0`); README task-coverage section.
- **Full EDA suites on the new pipeline sources (KANBAN-045)** — `scripts/eda/explore_pipeline_sources.py` (reproducible, `--source all|maud|s1|docclass|legalbench`, `--no-figures`) writes per-source `data/eda/<source>/{report.md, findings.md, figures/}` for every post-CUAD source integrated into the pipeline: **MAUD** (152 merger agreements, 54.1M chars, median 338k chars — **all 152 over the 90k chunk window**; consideration-type GT all_cash 57 / other 57 / all_stock 24 / mixed_cash_stock 13 / mixed_cash_stock_election 1; the 25,827-row per-question suite across 22 families / 7 categories, MAE definition 8,548 rows largest), **EDGAR S-1 corporate records** (15 exhibits, EX-3.1×4 / EX-3.2×3 / EX-4.x, content-detected subclasses articles_of_incorporation 8 / rights_instrument 6 / bylaws 1, 3 CIKs), **merged doc-class surface** (676 = CUAD 509 + MAUD 152 + S-1 15; doc_type contract 75.3% / merger_agreement 22.5% / corporate_record 2.2%; GT-`other` gap cluster 57 rows + subclass-None 509 — the quantified driver of the full-676 subclass misses), and **LegalBench** (hearsay train 5 / test 94 + 10 CUAD subtask 6-row controlled surfaces with answer balance + slices). Reports regenerate byte-identically — the reproducibility contract is pinned by `tests/test_pipeline_sources_eda.py` (3 tests, network-free, skips when the gitignored corpus dumps are absent). No LLM calls (plan-free).
- **llm-dojo-scoring integration completed (KANBAN-044)** — scoring/error-analysis/export code now lives in the pinned `llm-dojo-scoring` package (`@v0.1.2`) shared with llm-mailroom: `src/dojo_config.py` maps `config/taxonomy.yaml` → package `Settings` (embedding_enabled, `cost_models` dict→list conversion, `load_env()` first, and the `ambiguous_band`→tuple / `partial_gt_fields`/`containment_fields`→set coercion the package's verbatim `configure()` otherwise skips); `src/dojo_compat.py` (`classify_failure` None-on-ok); the 6 local scoring modules (`field_scoring`/`metrics`/`scorers`/`bootstrap`/`cost_models`/`experiment_log` core) become thin re-export shims so llm-mailroom's `pip install -e .` imports keep working unchanged; `export_experiment_results.py` re-exports `llm_dojo_scoring.export`; `export_sweep_results.py` stays local (reference-format Notes contract, KANBAN-040); the `dojo-analyze`/`dojo-export`/`dojo-sync` CLIs are verified against the repo's workbook artifacts. Upstream fix shipped: the external `cli.py` had no `python -m` entry dispatch (module import no-op'd) — fixed, pushed, tagged `v0.1.1`→`v0.1.2` (`29c192f`→`3ad2ef4`→`1f291ba`), dep re-pinned. Memo `memos/llm_dojo_scoring_integration.md`.
- **Champion-sweep extension — llama-4-scout + gpt-4o-mini on sorter_v13, full-509 (KANBAN-043)** — two funded full-corpus subtype evals (`run_langfuse_subtype_eval.py`, reasoning medium, temp 0.1, seed 42, `--research-funding-key`, Langfuse-primary tracing; manifests `data/manifests/{llama4scout,gpt4omini}_sorter_v13_509.jsonl`): **`meta-llama/llama-4-scout` subtype 0.8880 (equiv 0.9077, bootstrap CI [0.8605, 0.9136], 57 fails)** and **`openai/gpt-4o-mini` subtype 0.9312 (equiv 0.9352, exact 0.9961, CI [0.9096, 0.9528], 35 fails)** — both 509/509, full failure reasoning + per_subtype. The sweep table (KANBAN-036) and workbook absorb both; experiment-log md regenerated (195 records).
- **Full results deck exporter — extraction lineage + sorter sweep + LegalBench as one Google-Slides deck (KANBAN-040 follow-on)** — `scripts/reporting/export_full_results_deck.py` builds `reports/sheets/extraction_sweep_legalbench_full_deck.xlsx` (19 × 16:9 "slides", landscape fit-to-page, dark banner + footer, reusing the slide styling from `export_slides_deck.py`): **Part A — extraction** (all 61 collected contracts-specialist/extraction records chronological with overall / field-presence / schema-valid / verified-precision / tokens / est. cost, champion v32 `510_full_clean` detail — metadata, headlines, per-field, error decomposition, entity lists, MAE/R² diagnostics — and the full extraction codebook), **Part B — sorter sweep** (all 22 `sorter_v13` subtype runs across 8 models with strict/equiv/exact/fails/CI + champion detail with failure modes and the 25-subtype codebook), **Part C — LegalBench** (all 56 performance records grouped task_v0/v1/v2 hearsay + task_v3/v4 contract families with n / exact / bootstrap CI / per-class accuracy / tokens / cost, a per-task results summary — hearsay lineage v0 0.7766 → v1 0.8617 → v2 0.8830 on the same 94-row test — and a task legend). Data read live from `reports/experiment_log.jsonl` + `config/taxonomy.yaml` + `agents/sorter_agent.py` (no network, no LLM); tests `tests/test_full_results_deck.py` (4, network-free: slide structure/banner/footer, lineage rows, sweep rows, LegalBench logs + summary).
- **Sorter model-sweep completion — gpt-4.1-nano full-509 resumed to completion (KANBAN-036)** — the partial `openai/gpt-4.1-nano` run on the champion `sorter_v13` prompt (332/509 rows cached in `data/manifests/gpt41nano_sorter_v13_509.jsonl`, no experiment-log record) resumed via manifest (`--manifest`, Phoenix sink matching the checkpoint header, `--research-funding-key`, temp 0.1, reasoning medium, seed 42) and polled to completion: **subtype 0.8605 (bootstrap 95% CI [0.8291, 0.8900]), equiv 0.8782, exact 0.9666, confidence 0.9432, 71 fails (36 family_confusion / 17 function_over_form / 9 equivalent_family / 9 other_fallback)** — the lowest exact-match of the full-509 sweep (0.9666; the 17 function_over_form + 9 other_fallback misses vs 2/1 for gpt-4o-mini). Tokens recorded 2.25M (manifest-replayed rows carry no usage — only the 177 newly-run rows count; extrapolated full-509 ≈ 6.48M ≈ **$0.66 est. at $0.10/$0.40 per M**). LangSmith 429 trace-limit noise non-fatal (known tenant monthly limit). Sweep workbook regenerated → `reports/sheets/Sorter_Model_Sweep_Results.xlsx` (9 rows, gpt-4.1-nano row added) + copied to `~/Downloads`; experiment-log md regenerated (185 records).
- **Docclass scoring depth — the new classes/subclasses scored equally deep (KANBAN-033)** — `run_langfuse_docclass_eval.py` metrics now mirror the subtype surface's richness: **bootstrap 95% CIs on every headline** (`doc_type_accuracy_ci` / `subclass_accuracy_ci` / `exact_match_ci`, percentile-bootstrap via `src/bootstrap.py`), **per-subclass accuracy tables with support counts** (`per_subclass_accuracy` + `per_subclass_support` — e.g. full-676: all_cash 0.877/57, all_stock 0.917/24, articles_of_incorporation 0.5/8, other 0.0/57), **equivalence-aware subclass scoring** (`subclass_accuracy_equiv` + `equiv_recovered` — `DOC_SUBCLASS_EQUIVALENCES` in `agents/sorter_agent.py`: mixed_cash_stock ↔ mixed_cash_stock_election, dimension-scoped; per-document `subclass_ok_equiv` + `handle.score("subclass_accuracy_equiv")`), and **input-mode split counts** (`input_mode_counts` — text/vision/text_fallback). The experiment-log renderer gains a docclass branch: per-document tables now show doc_subclass / expected subclass / subclass ok equiv / input mode (the second-level dimension was previously invisible), plus a "Per-subclass accuracy (second-level dimension)" section. Records also carry `results` (the shared renderer contract) alongside `per_row`. Tests: `test_equivalent_doc_subclasses_family_reads`, smoke assertions for CIs/per-subclass/equiv/rendering.
- **Docclass sorter iteration round 2 — v4/v5/v6 from the full-676 failure set (KANBAN-033)** — the full-corpus failures decomposed into 3 mechanisms: (C1) M&A-package machinery misread as standalone ancillary instruments (contract_2 full APM-with-CVRs, contract_33 TRANSACTION AGREEMENT → contract/other; rule-35 over-fire), (C2) agreement-package composition (FEDERATED EX-99 services agreement opening with a LIMITED POWER OF ATTORNEY → corporate_record), (C3) GT/text artifacts (UNITEDNATIONAL press-release-only text, OLDAPI certificate-only text — NOT prompt-fixable, flagged data-side). Candidates: `sorter_docclass_v4` (rule 36 M&A package machinery), `sorter_docclass_v5` (rule 37 agreement packages), `sorter_docclass_v6` (rule 36 SHARPENED: rule-31 title list declared illustrative + multi-agreement files governed by the primary agreement — from contract_33's v4 reasoning, which showed the model second-guessing rule 31's enumeration). **Diagnostic-surface A/B (30 rows, fp 946ac1c4): all deltas inside the bootstrap CIs** (v3 exact [0.40, 0.73] vs v4 [0.43, 0.77] vs v5 [0.40, 0.73]) — the targeted rows are high-variance; v4 recovered contract_2 deterministically (2/2), v5 showed no replicated signal (dropped). **Full-676 A/B with noise control (fp 5602b71f, qwen3.7-flash, temp 0.1): the v3 identical-prompt rerun reproduced the exact headline (0.8905 = 0.8905 — the merged surface's aggregate noise floor ≈ 0.000); v6 = 0.8935 (+0.0030), doc_type 0.9941 (5→4 misses), subclass 0.5868 (+1.19pp, all_cash 0.877→0.912), 2 rows fully recovered (contract_62 — the embedded-bylaws rule-34 target that still failed at scale — and contract_71 consideration read), 0 regressions, same cost → **v6 strictly dominates v3 and is promoted as the docclass text champion**. Residual: contract_33 persists (the model hallucinates an RRA title on the truncated 1MB doc — truncation/model-bound, documented). Runs: `qwen3.7-flash_sorter_docclass_{v4,v5}_docclass_diag30b`, `qwen3.7-flash_sorter_docclass_v3_docclass_full676c` (noise control), `qwen3.7-flash_sorter_docclass_v6_docclass_full676`; memo `memos/docclass_v6.md`.
- **Sorter model-sweep expansion — deepseek-v4-pro + llama-3.3-70b-instruct on the champion sorter_v13 prompt, full-509, research-funding key (KANBAN-042)** — two funded full-corpus subtype evals (`run_langfuse_subtype_eval.py`, reasoning medium, temp 0.1, seed 42, 509 rows, `--research-funding-key`, Langfuse-primary tracing, manifests `data/manifests/{dsv4pro,llama3370b}_sorter_v13_509.jsonl`): **`deepseek-v4-pro_sorter_v13_subtype_langfuse` — subtype 0.9528 (CI [0.9332, 0.9705]), exact 0.9961, equiv 0.9548, 24 fails (18 family_confusion / 3 other_fallback / 2 function_over_form / 1 equivalent_family), 6.97M tokens ≈ $3.15 est.** — the highest subtype accuracy in the sorter_v13 sweep to date (vs qwen champion 0.9430); cross-model significance NOT claimed (the ±0.006 band was measured on identical-prompt qwen reruns — descriptive only). **`meta-llama-llama-3.3-70b-instruct_sorter_v13_subtype_langfuse` — subtype 0.8782 (CI [0.8487, 0.9057]), exact 0.9941, equiv 0.8998, 62 fails (47 family_confusion / 11 equivalent_family / 3 function_over_form / 1 other_fallback), 6.66M tokens, est. cost None (OpenRouter-billed, no local price)**. Both `n_ok=509`, full failure reasoning + per_subtype present; LangSmith 429 trace-limit noise non-fatal (known tenant monthly limit). **Sweep workbook regenerated** → `reports/sheets/Sorter_Model_Sweep_Results.xlsx` (8 rows, Notes added for both runs) + copied to `~/Downloads`; **deck slide 16 updated** (llama sorter run table vs qwen champion + deepseek-v4-pro; the "no llama sorter runs" note superseded — llama-3.3-70b sorter run now traced to Langfuse llm-dojo) + deck recopied to `~/Downloads`; experiment-log md regenerated (178 records).
- **Slides deck regenerated — qwen sorter lineage v3→v13 + llama runs included (KANBAN-041)** — the slides-style xlsx deck grows 16 → **19 slides**: Part B gains (14) **Qwen lineage summary v3→v13** (best full-surface run per version: v5 0.8585 → v6 0.9312 → v8 0.9018 → v9 0.9175 → v12 0.9293 → v13 0.9430@509; 243/195/50-doc surfaces flagged non-comparable), (15) **all 30 qwen v3→v13 runs** (two-column chronological table incl. degraded rows: v11 first run 0.0000, v13 first run 0.7741 — kept for truthfulness), (16) **Llama runs (Langfuse)** — the ONLY llama run recorded anywhere: **llama-4-scout × contracts_specialist_v31 extraction** (Langfuse llm-dojo, 509 traces / 20 scored, truncated; overall 0.6627 vs qwen v31 0.8737 — n=20, NOT comparable, labeled signal only). Provenance: fetched via langfuse-cli (`langfuse.env` keys, model-contains-llama + session filters); record saved to `reports/sheets/llama4scout_v31_extraction_langfuse.json` (loaded via `--llama-json`, absent → embedded defaults). **No llama SORTER-task runs exist** — verified across the experiment log (0 hits), Langfuse llm-dojo (model+session filters), Braintrust (experiment reads 403 Forbidden), LangSmith (`LANGSMITH_PROJECT=HEARSAY` only); the slide states this explicitly. Lineage slides use a NEW raw-list loader (`load_records_list`) — the deduped name→record index dropped same-name reruns (v3 ×4, v6 ×3, v9 ×4, v13 ×2). Codebooks renumbered 17–18, docclass 19; deck copied to `~/Downloads` per user pattern.
- **Sorter model-sweep workbook — every model on the champion prompt, reference-format xlsx (KANBAN-040)** — `scripts/reporting/export_sweep_results.py` builds `reports/sheets/Sorter_Model_Sweep_Results.xlsx` in the EXACT reference format of `Sorter_Experiment_Results.xlsx` (114 columns + a trailing `Notes` column; `Eval Results` + `Codebook` sheets; 1F4E79 header, mm/dd/yyyy dates, 0.00% percentages, freeze F2, autofilter) by filtering `subtype_classification` runs to the champion prompt (default `sorter_v13`, `--prompt` overridable). **6 rows, chronological**: the DEGRADED first v13 qwen run (93 connection errors, superseded), the clean **champion rerun (qwen3.7-flash 0.9430)** — the comparison baseline, **gpt-5-nano 0.8978** (KANBAN-035 cost-floor arm, −4.5pp), deepseek-v4-flash + gpt-4.1-nano 1-doc smokes, and **deepseek-v4-flash 0.9253 full-509** (KANBAN-036). Column spec + styling + compact codebook reused verbatim from `export_experiment_results.py` (114 shared headers byte-identical to the reference; per-subtype strict/equiv accuracy + cell sizes, failure-mode counts, tokens/cost, params all populate from the log records). `Notes` column flags champion/degraded/smoke/benchmark per row. Tests `tests/test_export_sweep_results.py` (4 tests, network-free: prompt/task filter + chronology, note fallbacks incl. degraded detection, workbook structure incl. 115-col + codebook contract).
- **Slides-style xlsx deck export — latest contract-specialist + sorter results with full codebooks (KANBAN-039)** — `scripts/reporting/export_slides_deck.py` builds ONE Google-Slides-formatted workbook (`reports/sheets/contract_specialist_v32_and_sorter_v14_deck.xlsx`, 16 sheets, every sheet a 16:9 slide: landscape fit-to-page, dark title banner + footer, stat-card callouts, colored tables) from `reports/experiment_log.jsonl` + `config/taxonomy.yaml` + `agents/sorter_agent.py` (no network, no LLM, repeatable via `--log/--taxonomy/--outdir/--outfile`). **Part A — contracts specialist v32** (`qwen3.7-flash_contracts_specialist_v32_extraction_langfuse_510_full_clean`, 2026-08-16): metadata/params/dataset/git/tokens ($0.49 est.), headline scores (overall **0.8807** CI [0.8689, 0.8913], field_presence 0.9701, schema_valid 1.0, verified_precision 0.9799) + v31 comparison (+0.0070; memo verdict: logic repair inside the ±0.011 band), per-field table (8 fields × score/verified precision/hallucination), exact/partial/miss decomposition, entity-list coverage-F1 vs raw P/R/F1 (partial-GT caveat), MAE/R² diagnostics (date 34.2d R²0.982 n=413; duration 423.9d R²0.731 n=148; span-count MAE 5.35 signed +5.03 n=1129) + **full extraction codebook** (9 fields + types + scoring class, partial-GT/containment/factuality/ambiguous-band rubric). **Part B — sorter v14** (`qwen3.7-flash_sorter_v14_subtype_langfuse`): headlines (exact 0.9961, subtype 0.9371 CI [0.9155, 0.9568], equiv 0.9411) + v13 A/B note (Δ −0.0059 inside band, v13 stays champion), failure-mode breakdown (32: 27 family_confusion / 2 equivalent_family / 2 function_over_form / 1 other_fallback) + top-confidence failure examples with reasoning, per-subtype strict/equiv accuracy (derived from the 509 row-level results; development 0.750 worst, 10 families at 1.000) + **full sorter codebook** (25 CUAD subtypes with labels + definitions, 4 equivalence families, failure-mode taxonomy, scoring rules). **Part C — docclass v5 diag-30 bonus** (doc_type 0.8333 / subclass 0.5263 n=19 / exact 0.5667, per-class + per-subclass tables, failure modes 5 doc_type_miss / 8 subclass_miss) + sources & navigation slide. Script verified by reloading the workbook (16 slides, landscape/fit-to-page, spot-checked values cross-match the log records).
- **Posit Cloud integrated portal — Quarto site `site/` → `docs/posit/`, complementary to the SPA (KANBAN-037)** — a fully themed, fully integrated Quarto website bringing the **experiment log**, the **agent kanban board**, and the **discussion board** together at one URL prefix under `docs/` (the same tree GH Pages serves — zero Actions; Pages deploys from branch, Posit Cloud deployment is `quarto render site` + publish). **Pages**: portal landing with live stat counters + latest runs (`site/index.qmd`), `experiment-log.html` (generated from `reports/experiment_log.jsonl` on every render by `site/_pre-render.py` using the SAME `src/experiment_log.py::render_full_log` renderer as `reports/experiment_log.md` — full run index + per-run metadata/scores/tokens/diagnostics with per-run deep links into the SPA explorer `../index.html#/run/{n}`), `kanban.html` (`board/MESSAGE_BOARD.md` live copy), `discussion.html` (`MESSAGE_BOARD_DISCUSSION.qmd` live copy, agent colors preserved) — plus portal↔explorer navbar links in both directions. **Theme**: custom blue→teal gradient identity match to the SPA favicon (bootswatch cosmo light / darkly "gradient night" dark, light/dark toggle, navbar, TOC, client-side search). **Hygiene**: `_pre-render.py` hook regenerates `_includes/` + `_variables.yml` before every render (gitignored — they carry generation stamps); rendered output `docs/posit/` IS committed so GH Pages serves it with no build step; `.gitignore` gains a Quarto/Posit section (`.quarto/`, `site/_includes/`, `site/_variables.yml`, `rsconnect/`, RStudio/renv local artifacts, standalone board renders). **Repairs en route**: 6 discussion-board entries were missing their `:::` closing fences (pre-existing — pandoc swallowed them into nested divs) — closers added, entry bodies byte-identical (append-only preserved), balance pinned by test; `board/MESSAGE_BOARD.md` card-number collision resolved (KANBAN-037/038). Tests `tests/test_posit_site.py` (9 tests, network-free: pre-render output, `_quarto.yml` contract, committed pages, source-div balance, and a skip-if-no-quarto determinism check that a fresh render leaves `docs/` byte-identical). Docs: `site/README.md` (new), `docs/README.md`, `README.md`, `wiki/Site.md`.
- **Docclass sorter prompt COMPLETED + QWEN 3.7-flash benchmark on the merged docclass task (KANBAN-033)** — (1) **Prompt iteration closed**: `sorter_docclass_v1` (rule 34, embedded-records scope guard) + `sorter_docclass_v2` (rule 35, RRA-exhibit convention) from the pilot's 3 failure mechanisms, then **`sorter_docclass_v3` = the Phase 3.5 MERGE (v0 + rules 34 AND 35)** as the completed docclass sorter prompt. Same-surface A/B (stratified-30, seed 42, fp `d3d7b335…`, qwen3.7-flash, temp 0.1): **v3 exact 0.8000 / doc_type 1.0000 — recovers all 5 EX-4.x instrument doc_type misses (RRAs + warrants), failure set byte-identical to v2 (the 6 remaining = 3 MAUD consideration-GT gaps + 3 S-1 streamer-detection artifacts, NOT prompt-fixable), zero regressions from the merge**. (2) **Merged docclass corpus = ONE dataset**: `scripts/datasets/build_docclass_merged.py` → `data/datasets/docclass_merged.jsonl` = 509 CUAD contracts + 152 MAUD merger agreements + 15 S-1 corporate records (**676 rows**, fp `5602b71f…`, deterministic ordering, reproducible fingerprint); `sync_langfuse_datasets.py --docclass` mirrors it as ONE Langfuse dataset `mailroom-docclass` (676 items upserted, llm-dojo); all docclass prompts (v0..v3 + vision) synced to Langfuse. (3) **QWEN 3.7-flash benchmark on the merged task**: **doc_type 0.9926 / subclass 0.5808 / exact 0.8905, 0 errors, ≈$0.47** — the established baseline for the merged surface (5 doc_type misses; **56/69 subclass misses are the MAUD GT-gap cluster** — GT "other" fallback where the model reads an explicit consideration — plus 4 S-1 GT artifacts and ~13 genuine consideration near-misses). (4) **Vision-primary mode with text fallback** (the added-complexity arm): `sorter_docclass_vision_v0` prompt (vision twin of v3, 7 classes + rules 31–35 + `<subclass>` tag + UNREADABLE sentinel), `SorterAgent` vision parse extended to the docclass schema (7-class validation, subclass normalization, strict 6-class backward compatibility), runner `--input-mode text|vision|vision-primary` + `--pdf-dir` + `--vision-pages all|first` with per-row input_mode/fallback_reason accounting; pilot `..._docclass_vpilot` (8 rows: 5 vision + 3 no-PDF text-fallback, all correct, ≈$0.005). Memo `memos/docclass_v3_merged_benchmark.md`.
- **MAUD + EDGAR S-1 corporate-record wiring + hierarchical doc-class sorter eval task (KANBAN-033)** — (1) **MAUD as a utilized dataset**: `scripts/datasets/stream_maud_to_bt.py` (Zenodo `maud_v1.zip` / HF `theatticusproject/maud` mirror, CC BY 4.0) streams the 152 merger agreements (54 MB text) into `mailroom-maud-contracts` with GT `doc_type: merger_agreement` + a **consideration-type subclass** read from MAUD's own expert GT ("Type of Consideration": all_cash 57 / all_stock 24 / mixed_cash_stock 13 / mixed_cash_stock_election 2, rest other — train-CSV coverage note) and the 25,827-row per-question suite into `mailroom-maud-classification` (22 question families / 7 categories as metadata); `--local-dump` JSONL is the reliable eval path while Braintrust row uploads are org-capped, and `sync_langfuse_datasets.py --maud` mirrors the dumps into Langfuse datasets (25,994 items dry-run). (2) **New primary sorter class `merger_agreement`** behind `SORTER_DOCCLASS_PROMPT_V0` (= v14 + rules 31–33: merger-agreement class, SEC-exhibit corporate records stay corporate_record, doc_subclass dimension) + `DOCCLASS_SCHEMA` (7-class enum + nullable `doc_subclass`); the shared 6-class surface (v0..v14, `SORTER_SCHEMA`) is untouched — the extended classes/schema are opt-in `SorterAgent(doc_classes=, schema=)` params, with `normalize_doc_subclass()` enforcing per-class subclass dimensions (wrong-dimension values → other). (3) **New eval task `scripts/eval/run_langfuse_docclass_eval.py`**: one sorter call per document over a mixed surface (MAUD + CUAD + S-1 corporate records, Braintrust datasets or `--local-dumps`), scoring doc_type_accuracy + subclass_accuracy (rows without subclass GT unscored) + exact_match + confidence, per-class accuracy, subclass confusion, failure insights (doc_type_miss / subclass_miss); Phoenix/Langfuse sink, manifest resume, experiment-log record (`task: docclass_classification`). (4) **EDGAR S-1 corporate-record exhibits**: `scripts/datasets/stream_s1_exhibits.py` (SEC full-text search → filing index → text extraction; SEC fair-access throttle + 403/429 backoff; content-detected record_type subclass: bylaws / articles_of_incorporation / certificate_of_formation / powers_of_attorney / ...; exhibit code stays as metadata) → `mailroom-s1-corporate-records` (15-doc live collection pilot). **Tertiary class level DROPPED per human directive (only where the data necessitates it)** — MAUD categories and EDGAR exhibit codes are dataset metadata, not classification dimensions; subclass (consideration type / record type) is the data-necessitated second level. Taxonomy (`config/taxonomy.yaml`) gains `merger_agreement` + subclass enums for merger_agreement/corporate_record (no tertiary_classes anywhere — pinned by test). Live pilot `qwen3.7-flash_sorter_docclass_v0_docclass_pilot` (5 docs, seed 42): doc_type 0.6 / subclass 0.4, valid schema output, first confusion signals (EX-4.4 registration-rights agreement → contract; merger agreement → corporate_record/bylaws). Tests: `test_stream_maud.py`, `test_stream_s1.py`, `test_docclass_eval_smoke.py`, sorter-agent + prompt option-list == schema-enum tests.
- **Externally-funded OpenRouter key behind a production-only flag (KANBAN-034)** — `RESEARCH_FUNDING_OPENROUTER_API_KEY` in `.env` (external research funding) is reachable ONLY via `--research-funding-key` on the eval runners; the default `OPENROUTER_API_KEY` is untouched. `src/env_utils.py` gains `resolve_openrouter_key()` + `assert_production_run()` + `add_research_funding_flag()`: the gate HARD-REFUSES dry-runs and pilot-scale samples (fewer than 100 rows, or less than the full dataset when smaller) with a `SystemExit` before any LLM call, and prints a funding banner on accepted runs. Wired into all 10 `run_*_eval.py` / `run_langfuse_*_eval.py` runners (subtype, extraction, chained, classification, multiclass, binary) + `judge_experiment.py` untouched (stays on the default key). `.env.example` documents the variable; `tests/test_env_utils.py` covers resolution, the gate, and a runner-level refusal smoke test.
- **GPT cheapest-model benchmark on the sorter subtype surface — gpt-5-nano vs champion (KANBAN-035)** — full-509 subtype eval (`mailroom-cuad-contracts-full`, sorter_v13 champion prompt, reasoning medium, temp 0.1, Phoenix sink, 0 errors) with **`openai/gpt-5-nano`** — the smallest & cheapest GPT on OpenRouter ($0.05/M prompt + $0.40/M completion, 400k ctx). **gpt-5-nano strict 0.8978 (CI [0.8703, 0.9234]) vs the qwen3.7-flash champion 0.9430 = −4.5pp — far outside the ±0.006 noise band → nano does NOT match the champion; cost-floor frontier arm only** (equiv 0.9018, doc_type 0.9941; 52 fails: 41 family_confusion / 6 other_fallback / 3 function_over_form / 2 equivalent_family). 6.94M tokens ≈ **$0.48** for the full 509-doc run (recorded cost_usd 0.0 — gpt-5-nano absent from the local cost table; billed via OpenRouter). LangSmith ingest 429s (tenant monthly unique-traces limit) — non-fatal, traces skipped, scoring unaffected. Run `gpt-5-nano_sorter_v13_subtype_langfuse`; manifest `data/manifests/gpt5nano_sorter_v13_509.jsonl`; paid with `--research-funding-key` per human directive.
- **DeepSeek + GPT cheap-model sorter sweep — deepseek-v4-flash + gpt-4.1-nano on sorter_v13 (KANBAN-036)** — two more full-509 subtype evals on the champion `sorter_v13` prompt (reasoning medium, temp 0.1, Phoenix sink, 0 errors, `--research-funding-key`, manifests `data/manifests/{deepseekv4flash,gpt41nano}_sorter_v13_509.jsonl`), completing the cheap-model frontier around the qwen3.7-flash champion (0.9430): **`deepseek/deepseek-v4-flash` strict 0.9332 / equiv 0.9352 (34 fails: 27 family_confusion / 5 other_fallback / 1 equivalent_family / 1 function_over_form) — the standout cheap model, within −0.98pp of the champion** (6.91M tokens ≈ $0.39 est.); **`openai/gpt-4.1-nano` strict 0.8782 / equiv 0.8959 (62 fails: 35 family_confusion / 11 function_over_form / 9 equivalent_family / 7 other_fallback) — below gpt-5-nano (0.8978), a cost-floor frontier arm only** (6.65M tokens). Both runs clean 509/509. Runs `deepseek-v4-flash_sorter_v13_subtype_langfuse` + `gpt-4.1-nano_sorter_v13_subtype_langfuse`; Phoenix trace sink persisted to `.phoenix/` (gitignored, `f84556f`).
- **llama-4-scout × contracts_specialist_v31 extraction — cheap model collapses on structured extraction** — full-509 chunked extraction eval on the champion prompt `contracts_specialist_v31` (90k/8k windows, temp 0.1, reasoning none, `--research-funding-key`, manifest `data/manifests/llama4scout_v31_510_chunked_full.jsonl`) with **`meta-llama/llama-4-scout`**: **overall 0.6968 vs the qwen3.7-flash champion 0.8737 = −17.7pp** (509/509, 0 errors, 10.34M tokens). The model is classification-capable (0.888 on the sorter) but collapses on structured extraction: **key_obligations recall 0.259 / exact 0.048** (span-count signed mean −4.06 → under-extraction), **term_length exact 0.078** (date MAE 1,643 days, R² −4.04 → containment collapse), renewal_terms exact 0.292, termination_clauses exact 0.714. Verdict: cost-floor arm only — does NOT approach the champion on extraction. Run `llama-4-scout_contracts_specialist_v31_extraction_langfuse`.

### Changed
- **Repo storage optimization (KANBAN-053)** — two-part repo-size fix: (1) **untracked stale board renders** — `MESSAGE_BOARD.html` + `MESSAGE_BOARD_DISCUSSION.{html,md}` (root-level standalone Quarto renders, ~2.6 MB) removed from git tracking (`git rm --cached`, files stay on disk) and covered by `.gitignore`; (2) **history purge** — rewritten with `git-filter-repo` removing every historical blob of the already-gitignored `reports/experiment_log.jsonl` (69 blobs ≈ 1.98 GB) + `reports/experiment_log.md` (94 blobs ≈ 641 MB) + `.phoenix/` (wasm + db, ~29 MB) → **~2.65 GB of dead blobs gone; pack 64.4 MiB → 24.7 MiB (`.git` 80 MB → 25 MB)**; legacy `gh-pages` branch (15 commits, pre-`/docs`-era) deleted locally + on GitHub (Pages serves `/docs` from `main`). AGENTS.md "After every run" commit snippet corrected (the log files are gitignored; only `docs/data` is committed). **Critical data untouched**: `reports/experiment_log.{jsonl,md}` remain local-only per the existing 100 MB hard-limit rule, `docs/data/*` + `docs/posit/*` stay tracked (the public record GH Pages serves with no build step), `data/cuad/master_clauses.csv` (GT) untouched. **Caveat**: all commit SHAs changed — historical `git_snapshot` SHAs in log/site records are now cosmetic labels; existing clones must be re-cloned (backup bundle: `/tmp/opencode/llm-entity-extraction-backup.bundle`).
- **Scoring documentation refreshed to the current pipeline state (KANBAN-050)** — `SCORING.md` (+ its `wiki/Scoring.md` mirror) rewritten as the canonical reference: a new §0 maps **where the scoring lives** — the pinned `llm-dojo-scoring@v0.2.0` package shared with llm-mailroom, the six re-export shims (`src/{field_scoring,metrics,scorers,bootstrap,cost_models,experiment_log}.py`), and the `dojo_config` / `dojo_compat` adapters — and new sections document every metric added since the reference was last current: **subtype metrics** (strict/equiv accuracy, per-family, failure modes, CIs), **docclass hierarchical metrics** (doc_type/subclass accuracy + equiv + per-subclass + input modes), the **task-aware scoring dispatcher** (`llm_dojo_scoring.tasks::score_task`: MAUD consideration strict/equiv, LegalBench binary P/R/F1, multiclass macro/micro, court opinions, chained 0.25/0.75), **judge calibration**, **chained error-propagation ablation**, **cost scoring**, the **failure-mode taxonomy** (package `failure_modes`), and the **Monte Carlo robustness metrics** (KANBAN-048: committee voting, escalation, paired-bootstrap P(win), failure-pipeline, exemplar mining). Consumers updated: README scoring section + layout, `src/README.md` module table (shims + `dojo_config`/`dojo_compat`/`monte_carlo`), AGENTS.md scoring invariants + key-modules table + data-flow diagram, wiki Architecture/FAQ, the slides decks (module refs fixed in 02/04 + **new deck 12** `docs/slides/12-task-aware-and-robustness-metrics.md` + deck index), and `data/judgments/README.md`. Docs-only; no code/scoring behavior change. Wiki pushed via `./wiki/sync-wiki.sh`.
- **EDA figure citations moved into a dedicated footer band (no more label/legend overlap)** — `scripts/eda/explore_cuad.py::_add_citation` and `scripts/eda/explore_pipeline_sources.py::_add_citation` previously drew the dataset citation anchored below the axes (`ax.text` at negative axes coords / `fig.text` at the bottom-right corner), which collided with the x-axis labels and tick labels on short figures (measured: 8/10 CUAD figures + several pipeline-source figures). Both now reserve a footer band (`fig.tight_layout(rect=[0, 0.10/0.11, 1, 1])`) and center the citation inside it, so the axes + labels + legends always sit fully above the text. All 17 figures regenerated (`data/eda/figures/01–10` + the maud/s1/docclass/legalbench suites); the no-overlap contract is pinned by two new renderer-based regression tests in `tests/test_pipeline_sources_eda.py`.
- **llm-dojo-scoring integration fixes — the shim suite turned green (KANBAN-044)** — `src/dojo_config.py` now coerces the taxonomy's field-scoring values to the package's canonical types before `configure()` (`ambiguous_band` list→`(float, float)` tuple, `partial_gt_fields`/`containment_fields` list→`set[str]` — the package's inline `configure()` sets verbatim and only its YAML-file loader coerces); `src/metrics.py::extraction_diagnostics` binds `master` into the `expected_resolver` closure (the package calls the resolver with its own master slot, so the curated master-label preference was silently lost to the raw clause-text fallback — the resolver contract is `(master, filename, field, fallback)`); the external `llm_dojo_scoring.cli` gains a `python -m` entry dispatch (`analyze|export|sync` subcommand routing, default analyze; console entry points now accept an optional argv) — shipped upstream as `v0.1.1`→`v0.1.2` and the dep re-pinned to `@v0.1.2` in `pyproject.toml`/`requirements.txt`; 4 test expectations in `tests/test_dojo_integration.py` corrected to the real contract (compound `entity_list:free_text` field types, re-export identity + header equality instead of lambda-object equality, the sweep workbook's trailing reference-format `Notes` column, and the master-CSV `-Answer`/normalized-filename key format). `tests/test_dojo_integration.py` 11/11 green.
- **EDA figures regenerated with CUAD dataset citations + self-contained data paths (KANBAN-014 follow-on)** — `scripts/eda/explore_cuad.py` renders a **dataset citation footer on every figure** via a shared `_add_citation()` helper ("Source: CUAD — Contract Understanding Atticus Dataset (Hendrycks et al., NeurIPS 2021), The Atticus Project · huggingface.co/datasets/theatticusproject/cuad" + per-figure source notes), and figure 01 is retitled **"CUAD contract subclass distribution (25-family taxonomy, n=509)"** with per-bar count labels. The script is now **self-contained**: `CUAD_JSON` prefers the repo-local `data/cuad_pdfs/CUAD_v1.json` (gitignored corpus, sibling llm-mailroom path kept as fallback); the subtype distribution (figure 01 + report composition table) reads the **verified experiment-log per-subtype totals** (`SUBTYPE_FALLBACK`, sums to 509) instead of the vanished `subtype_distribution.json`; figure 07's per-subtype text-length stats are computed from the aligned corpus texts grouped by a **title-derived 25-family matcher** (longest-pattern-wins; patterns from `SUBTYPE_CUAD_FOLDERS` + `CONTRACT_SUBTYPES` labels; 503/510 contracts matched). All 10 figures + `data/eda/report.md` regenerated (510/510 texts aligned, 509 from the synced full corpus); `data/eda/findings.md` byte-identical (headline stats unchanged). Requires `data/cuad_pdfs/CUAD_v1.json` (40 MB, `scripts/datasets/download_cuad_pdfs.py`).
- **Sorter v13 model sweep — complete verified table (7 models, KANBAN-036 reconciliation)** — every model evaluated on the champion `sorter_v13` prompt (full-509, seed 42, temp 0.1, reasoning medium, 509/509 rows, 0 errors), reconciled against `reports/experiment_log.jsonl` with the strict subtype_accuracy + percentile-bootstrap CI: **`deepseek/deepseek-v4-pro` 0.9528** (equiv 0.9548, 24 fails, CI [0.9332, 0.9705]) — the only model to beat the champion; **`qwen/qwen3.7-flash` 0.9430** (champion, 0.9470, 29, [0.9214, 0.9627]); **`deepseek/deepseek-v4-flash` 0.9332** (0.9352, 34, [0.9096, 0.9528]); **`openai/gpt-5-nano` 0.8978** (0.9018, 52, [0.8703, 0.9234]); **`meta-llama/llama-3.3-70b-instruct` 0.8900** (0.9116, 56, [0.8625, 0.9175]); **`meta-llama/llama-4-scout` 0.8880** (0.9077, 57, [0.8605, 0.9136]); **`openai/gpt-4.1-nano` 0.8782** (0.8959, 62, [0.8487, 0.9057]). Corrections vs the earlier per-arm entries: **deepseek-v4-flash canonical is 0.9332** (the clean @06:38 rerun), not 0.9253 (the first @05:44 run — both are clean 509/509, the first is superseded); **llama-4-scout 0.8880 was previously omitted** from the sweep summaries (KANBAN-041's "no llama sorter runs" claim is superseded); **llama-3.3-70b-instruct ran twice** (0.8900 @06:54 → 0.8782 @10:51 duplicate; canonical 0.8900); **gpt-4.1-nano is complete at 0.8782**, not "pending". Cross-model significance is NOT claimed — the ±0.006 noise band was measured on identical-prompt qwen reruns, so a cross-model delta needs its own noise-floor control. **Sweep complete + workbook regenerated** — `reports/sheets/Sorter_Model_Sweep_Results.xlsx` now covers all 8 models (22 rows incl. smokes + the degraded first qwen run; llama-4-scout, gpt-4o-mini and the resumed gpt-4.1-nano full-509 rows added), superseding the earlier "regen needed" note.
- **Eval-run tracing: Langfuse PRIMARY, local Arize Phoenix server as fallback (human directive 2026-08-16)** — new `src/tracing.py::resolve_tracer()` flips the previous Phoenix-first default for all four `run_langfuse_*_eval.py` runners (docclass, subtype, extraction, chained): each run traces to **Langfuse** (llm-dojo project, keys in `langfuse.env`) whenever its keys are configured, and **falls back to the local Phoenix OpenTelemetry server** when Langfuse is unavailable — never silently untraced. The resolver returns `(tracer, tracing_backend, tracing_meta)` so the dry-run label, manifest header, and experiment-log record all report the REAL backend (the manifest/resolver ordering was fixed so the checkpoint header records the resolved backend; previously-hardcoded "langfuse" backends in extraction/chained now resolve dynamically). `prefer="phoenix"` preserves the old order for explicit opt-in. Verified live: full-676 docclass runs trace to llm-dojo (`tracing_backend=langfuse` in the records). Tests `tests/test_tracing.py` (selection order + fallback + record metadata, network-free). Also fixes the langfuse subtype smoke's environment gap (it previously selected Phoenix when PHOENIX_TRACING was unset; the Langfuse-primary default now exercises the stub as intended).
- **Adaptive eval-runner concurrency + rate-limit retry (speed/efficiency)** — new shared helpers in `src/evaluation.py`: `resolve_concurrency()` scales the worker pool with the sample size (auto = `min(32, max(1, min(8 + ceil(n/25), n)))` — 30 rows → 10 workers, 200 → 16, 676 → 32 — until diminishing returns / provider rate limits; explicit `--max-concurrency N` still wins) and `call_with_rate_limit_retry()` retries transient 429/rate-limit errors with exponential backoff + jitter (KANBAN-024's qwen-via-Alibaba burst shape). Wired into the four `run_langfuse_*_eval.py` runners (docclass, subtype, extraction, chained): `--max-concurrency` defaults to AUTO, the effective worker count + `rate_limit_retries` are recorded in each experiment-log record. 4 new unit tests (`test_resolve_concurrency_*`, `test_rate_limit_retry_*`).
- **Env files consolidated under `config/environments/`** — the live (gitignored) dotenv files and their committed `.example` templates now live in `config/environments/` (`braintrust.env`, `.env`, `langfuse.env` + templates), and every runtime loader resolves them there instead of the repo root or CWD: `src/env_utils.py` gains the shared path constants (`ENV_DIR`, `BRAINTRUST_ENV_FILE`, `DOTENV_FILE`, `LANGFUSE_ENV_FILE`) plus `resolve_env_file()` (absolute paths pass through; bare filenames resolve under `ENV_DIR`), and `load_env()` iterates `(BRAINTRUST_ENV_FILE, DOTENV_FILE)`; `src/braintrust_config.py` and `src/langfuse_config.py` default to `None` → the resolved env file and fall back to `DOTENV_FILE` (repo-root-absolute) instead of CWD `Path(".env")`; `scripts/eval/sync_langfuse_prompts.py` / `sync_langfuse_datasets.py` import the shared constant for their defaults, and `run_annotation_queue.py`'s `--env-file` default points at `config/environments/langfuse.env`. `.gitignore` ignores the new paths (root-level entries kept one release as a safety net); example-template headers and setup docs (README, AGENTS.md, wiki/Getting-Started, config/README, src/README) updated to the new `cp` paths. Tests `test_env_reads_config_environments` + `test_resolve_env_file_bare_name` in `tests/test_env_utils.py`.
- **Per-task experiment-results exporter `scripts/reporting/export_experiment_results.py`** — regenerates the Google-Sheets-friendly performance workbooks + codebooks from `reports/experiment_log.jsonl`, matching the reference format exactly: `Sorter_Experiment_Results.xlsx` (114 cols — headlines, CIs, failure modes, per-subtype strict/equiv accuracy + cell sizes, tokens/cost/params; `Eval Results` + `Codebook` sheets) + `Sorter_Experiment_Codebook.csv` (115-row variable dictionary) from `subtype_classification` runs; `Entity_Extraction_Results.xlsx` (141 cols — overall/per-field scores, CI, hallucination + verified-precision rates, entity-list F1, full diagnostics block: error decomposition, date/duration MAE+R², span-count drift, field presence) + `Entity_Extraction_Codebook.csv` (142 rows) from `contract_entity_extraction` runs. `--task {sorter,extraction,all}`, `--outdir`, `--log`. Verified against the reference workbooks: 0 differing cells on all 27 sorter rows and 49/50 extraction rows (the 2 residual diffs are stale-reference artifacts — the reference averaged an unnormalized float later corrected in the log, and one reference row is internally column-shifted by its own generator). Formatting: `mm/dd/yyyy` dates, `0.00%` percentages, bold frozen header row, autofilter, tuned widths; subtype order `co_branding`-before-`collaboration` per the reference. Tests `tests/test_export_experiment_results.py` (network-free, structure + values + codebook completeness).
- **Sorter v14 marketing-title strengthening — LOGIC REPAIR, NOT a win; v13 stays champion (KANBAN-032)** — `SORTER_PROMPT_V14` = v13 + rule 30 MARKETING TITLE WINS — STRENGTHENED (kills rule-26 narrowing: machinery re-reads, rule 9's hybrid read, first-named-family precedence), targeting the 3 deterministic marketing fails stuck at 14/17 since v12 (Zounds/PACIRA/Audible, identical predictions in v9-clean/v12-orig/v12-rerun/v13-clean). **Full-509 A/B (Phoenix sink, seed 42, temp 0.1, 0 errors): v14 0.9371 vs v13-clean 0.9430 = −0.0059, paired bootstrap CI [−0.0177, +0.0059], P(Δ≤0)=0.8765 — INSIDE the ±0.006 noise band, negative direction → NOT a claimed win** (v13 noise-floor rerun skipped per token-budget directive; the ±0.006 band was already measured twice on this surface). Rule 30 DID recover Audible + PACIRA (marketing cell 14/17 → 16/17, rule-30 reasoning pinned) but **the flagged license-primary counterfactual FIRED: Playboy "CONTENT LICENSE, MARKETING AND SALES AGREEMENT" regressed license→marketing** (carve-out (a) cited only the exact "Content License Agreement" phrase → banked v15 lesson: widen to any license-PRIMARY title); Zounds resists even its own literal example (model-bound ceiling). 4/6 other regressions (LinkPlus/Liquidmetal/Ehave/HALITRON) are untouched-family noise. v13 stays aggregate champion; the directional marketing gain is banked. Memo `memos/sorter_v14.md`; test `test_sorter_v14_marketing_title_wins_strengthened`.
- **Sorter v15 license-primary title-wins — LOGIC REPAIR, NOT a win; v13 stays champion (KANBAN-038)** — `SORTER_PROMPT_V15` = v13 + rule 31 LICENSE-PRIMARY TITLE WINS (widens rule 26 carve-out (a) to ANY license-PRIMARY title: a "Content License Agreement" — license as the primary family — stays license, never `other` and never `ip`, regardless of co-named marketing/sales/distribution or an IP-grant/joint-venture core; carve-outs preserved: rule 13 license+maintenance → maintenance, rule 14 license+hosting → hosting, rules 19/21 license+development → development, rule 26 marketing-core stays marketing — "Strategic Licensing, Distribution and Marketing Agreement" → marketing where licensing is merely co-named). Motivated by the cross-model failure traces on the SAME `sorter_v13` prompt (full-509, seed 42, temp 0.1, reasoning medium): **LejuHoldings "Content License Agreement" → `other` fails in ALL FIVE models** (champion 0.9430 + gpt-5-nano 0.8978 / gpt-4.1-nano 0.8782 / llama-4-scout 0.8880 / deepseek-v4-flash 0.9332), and Playboy / DataCall / ChinaRealEstate / Ideanomics ×2 / Midwest / AlliedEsports / GluMobile (all "Content License Agreement" titles) mis-route to `ip`/`joint_venture`/`marketing`/`manufacturing` in the weaker sweeps. **Full-509 A/B (seed 42, temp 0.1, reasoning medium, Phoenix sink, 0 errors): v15 0.9450 vs v13-clean 0.9430 = +0.0020, paired bootstrap 95% CI [−0.0059, +0.0098], P(Δ≤0)=0.4160 — INSIDE the ±0.006 noise band → logic repair, NOT a claimed win** (equiv 0.9509 vs 0.9470 = +0.0039). Rule 31 recovered PACIRA (marketing — a deterministic cross-model fail named verbatim in the carve-out) + 2 rule-24 outsourcing variance flips (NEXSTAR, ImperialGarden); regressed Paratek (outsourcing→manufacturing, rule-24 variance) + Artara (license→development, rules 19/21 working as designed, equiv-recovered). LejuHoldings "Content License Agreement2" is unfixable by rule 31 — the exhibit's actual title is "Mutual Termination Agreement" (the CUAD license-folder GT label is a labeling artifact, not a license-primary mis-route). v13 stays aggregate champion; v15 joins the frontier as the license-primary field specialist. Memo `memos/sorter_v15.md`; test `test_sorter_v15_license_primary_title_wins`.
- **LegalBench CUAD subtask prompts v4 — subtask-specific operative rules + V4 hygiene base (KANBAN-026 extension)** — the 7 `legalbench_task_v3_<subtask>` keys were aliases of the generic hearsay-doctrine v3 prompt (rule 6 never fires on CUAD clause tasks). **`LEGALBENCH_TASK_PROMPT_V4`** = v3 + two hygiene repairs (stray `"` from the `V2 + """"` construction; prohibition rule renumbered 6→7 clearing the rule-6 collision), verified no doctrine change. **`LEGALBENCH_TASK_PROMPT_V4_CRE`** = V4 + rule 8 COMPETITIVE-RESTRICTION EXCEPTIONS (a carveout includes the conditional-permission structure, not only "except/provided, however" qualifiers — the deterministic IGER/CERES failure on the 6-row CRE surface, fp de6ae646, failed 0.8333 in both v3 runs); **`LEGALBENCH_TASK_PROMPT_V4_CNTS`** = V4 + rule 8 COVENANT NOT TO SUE (conduct-restriction covenants count without the word "sue" — the Allied/Newegg failure, control oscillates 0.8333/1.0). 7 same-surface A/Bs (sampled 6-row surfaces, fp-matched to v3 controls, temp 0.1): **CRE 0.8333→1.0 (+1 deterministic row), CNTS →1.0 (+1, logic-repair grade), five subtasks unchanged at 1.0/6** (hygiene-only re-point, no regression). `legalbench_task_v4_<subtask>` keys registered (5 → V4, 2 → rule versions); v3_<subtask> keys unchanged (identity). Tests: `test_legalbench_task_v4_hygiene_fix`, `test_legalbench_task_v4_competitive_restriction_exception_rule`, `test_legalbench_task_v4_covenant_not_to_sue_rule`, `test_legalbench_subtask_v4_keys_resolve`; memo `memos/legalbench_task_v4.md`.
- **Sorter v13 maintenance-title arm — aggregate WIN outside the noise band (KANBAN-031)** — `SORTER_PROMPT_V13` = v12 + rule 29 MAINTENANCE TITLE WINS (title-wins doctrine mirror of rules 23/24/26/28), fixing the rule-13 INVERSION cluster: the model quoted rule 13 backwards ("financial-sense maintenance agreements are classified under 'other'") on SUNTRONCORP/WELLSFARGO/PRIMEENERGY (→other) and AtnInternational (→service). **Clean full-509 A/B (509-row paired intersection, seed 42, temp 0.1, reasoning medium): v13 0.9430 strict vs v12 rerun 0.9293 = +0.0137, bootstrap 95% CI [+0.0020, +0.0255], P(Δ≤0)=0.0090 — outside the ±0.006 identical-prompt noise band** (v12 rerun 0.9293 vs v12 original 0.9234 = band ±0.0059). Maintenance cell 30/34 → **34/34 (1.0)**; recovered 8 / regressed 1 (ImperialGarden = pre-existing rule-24 outsourcing variance flip, NOT rule-29 — correct in v9-clean + v12-rerun, wrong in v12-original/v13). 0-risk counterfactual verified (34/34 maintenance-titled docs GT maintenance). Note: the first v13 run was DEGRADED (93/509 `Connection error` defaults — runner except-clause marks them completed, resume cannot recover); replaced by `subtype_v13_509_clean.jsonl`. **Runner change: `run_langfuse_subtype_eval.py` now selects Arize Phoenix tracing by default** (`PHOENIX_TRACING=enabled` → `PhoenixTracer`, local OpenTelemetry; Langfuse fallback when disabled; experiment-log record reports `tracing_backend="phoenix"` + endpoint/service). Test `test_sorter_v13_maintenance_title_wins`; memo `memos/sorter_v13.md`.
- **Contract-specialist v32 effective_date A/B complete — logic repair, v31 stays champion (KANBAN-029)** — `CONTRACTS_SPECIALIST_PROMPT_V32` = v31 + one rule (Agreement/EXECUTION date wins whenever stated; a defined "Effective Date" term is fallback only when no execution date appears), fixing the v12-era rule_contradiction vs CUAD GT (Agreement Date = answers[0] in 493/493). **CLEAN full-510 A/B (495-row paired intersection, chunked, seed 42, temp 0.1): v32 0.8799 vs v31 0.8746 = +0.0053, bootstrap 95% CI [−0.0052, +0.0159], P(Δ≤0)=0.1715 — INSIDE the ±0.011 noise band → logic repair, NOT a claimed win** (the first candidate run's +0.0115 was survivorship bias from 52 transient errors; replaced by `..._510_full_clean`). effective_date field +0.0171 (23 improved/11 regressed, 16/23 on the diagnosed target cluster) → v32 = effective_date field specialist on the frontier. Never-null over-fire cluster deterministic (4/6 regressions reproduce) — banked as the v33 carve-out (stated-FULL-date requirement). Memo `memos/contracts_specialist_v32.md`; test `test_contracts_v32_effective_date_convention_fix`.
- **LegalBench task prompt `legalbench_task_v3` — prohibition clause disambiguation (KANBAN-027)** — v3 = v2 + ONE prohibition clause rule (when a clause uses prohibition language such as "shall not have the right to X," "shall not X," or "may not X," recognize this establishes a RESTRICTION where X is not permitted without consent/notice; in Yes/No tasks, output "Yes" if the question asks whether consent/notice is required). Same-surface 42-row A/B (fresh manifest, temp 0.0): **v3 7/7 tasks 42/42 exact_match (100%) vs v0 6/7 tasks 36/42 exact_match (83.3%, 1 failure on anti-assignment prohibition clause)** — recovered 6/6 rows in anti-assignment / no regressions. `LEGALBENCH_TASK_PROMPT_V3` registered; memo `memos/legalbench_task_v3.md`.
- **Contract-specialist v1..v16 archived to `src/prompts_archive.py` (prompt-file bloat cut)** — the pre-documentation lineage (full-text v1..v7 + the early replace chain, ~1,000 lines / ~72 KB) moved out of `src/prompts.py` into a FROZEN archive module and imported back, so `src/prompts.py` drops 227 KB → 155 KB (−32%) for later editing agents while EVERY version key stays resolvable (`get_prompt`, `PROMPT_VERSIONS`, manifests, Langfuse prompt syncs) and the 32 prompt strings are byte-identical (verified against git HEAD). The documented frontier lineage (v17..v32) with its data-backed banners stays in `prompts.py`. Archive rule pinned by tests: never edit an archived constant — a change = a new version key. 384 tests green (`test_contracts_archive_preserves_identity_and_version_keys`, `test_contracts_archive_chain_heads_resolve`).
- **LegalBench task prompt `legalbench_task_v1` — hearsay doctrine in the
  system prompt (KANBAN-026)** — v1 = v0 + ONE hearsay-doctrine rule (the
  truth-of-matter purpose test + statement scope incl. writings/assertive
  non-verbal conduct + party-admission-is-still-hearsay + in-court carve-out).
  Same-surface 94-row A/B (fresh manifest, temp 0.0): **v1 0.8511 (80/94) vs
  v0 band 0.7766–0.7872 (73–74/94) — recovered 12 (all 10 deterministic v0
  failures) / regressed 6, paired bootstrap 95% CI [−0.0213, +0.1489],
  P(Δ≤0)=0.0905 — directional win outside the ±1-row band, not 5%-significant**;
  yes-cell 0.7805–0.8049 → 0.9268. The 6 regressions are a NEW pattern
  (non-verbal-conduct clause over-fired on in-court pointing / protest signs /
  declarant-belief conduct) — banked as the v2 lesson. `LEGALBENCH_TASK_PROMPT_V1`
  registered + `test_legalbench_task_v1_hearsay_doctrine` (382 tests green);
  memo `memos/legalbench_task_v1.md`.
- **Run sink swapped to Langfuse + LangSmith — Braintrust logging OFF by
  default (KANBAN-025)** — the four `run_*_eval.py` runners (subtype,
  extraction, chained, classification) now consult `BRAINTRUST_LOGGING`
  (`src/braintrust_logging.py`, default `disabled`): when disabled they skip
  `setup_langchain` + `braintrust.Eval` entirely and run the SAME local
  scoring loop via `src/eval_shims.py::run_local_eval` (ThreadPoolExecutor +
  manifest resume + the repo experiment log, `tracing_backend="none"` with a
  `braintrust_logging/langsmith` tracing meta), so every surface — including
  vision classification and chunked extraction — runs with ZERO Braintrust
  plan quota; `braintrust.Eval`/`setup_langchain` stay opt-in per run with
  `BRAINTRUST_LOGGING=enabled`. The `run_langfuse_*_eval.py` mirrors are now
  the documented PRIMARY path (per-document Langfuse traces + numeric scores,
  LangSmith LLM spans, chunked extraction supported). Docs flipped
  (AGENTS.md cheatsheet + run-sink paragraph, README, wiki/Eval-Runners);
  `.env`/`.env.example` carry the flag. Verified live: 1-doc subtype pilot
  through the disabled path logged `tracing_backend=none` +
  `langsmith=True` with the trace tree captured in the LangSmith   `llm-mailroom`
  project and no Braintrust 400s. 365 tests green (+5 gate unit tests, +1
  disabled-path smoke test).
- **Repository streamlining + navigation pass (KANBAN-027)** — `README.md`
  gains a **Table of Contents** and a repaired, complete **Layout tree**
  (the `src/` modules `openrouter_utils`/`prompts`/`scorers`/`taxonomy` were
  mis-nested under `wiki/`; stale/missing entries corrected; every area
  linked to its own README), with stale test counts fixed (223 → 375) and
  the `sorter_v0…v12` / `contracts_specialist_v0…v31` prompt tables +
  `BRAINTRUST_LOGGING` conditional wiring documented. `src/README.md` gains
  `braintrust_logging`, `eval_shims`, `master_labels`, `metrics`;
  `memos/README.md` table formatting fixed + missing memo rows added
  (v28/v30/v31/sorter_v10_v11); `scripts/README.md` now enumerates every
  eval/reporting runner + `scripts/eda/`. `scripts/backfill_cost_estimates.py`
  **nested under `scripts/reporting/`** (one-time reporting backfill; run as
  `python scripts/reporting/backfill_cost_estimates.py`; live refs in
  `scripts/README.md` + `wiki/Scoring.md` updated). Docs-only + safe nesting —
  no functional change, 375 tests green, site render audit clean.
- **Sorter `sorter_v12` — strategic_alliance title-wins (KANBAN-023)** —
  rule 28 STRATEGIC ALLIANCE TITLE WINS (v12 = v11 + the first banked
  cluster from KANBAN-013): alliance-titled agreements beat collaboration/
  license/consulting/service machinery, mirroring the validated R23/24/26
  title-wins doctrine. Same-surface full-509 A/B (fp `c2341957…`, seed 42,
  temp 0.1, reasoning medium): **v12 0.9234 vs the v9 clean rerun 0.9175 =
  +0.0059, paired CI [−0.0098, +0.0216], P(Δ≤0)=0.251 — INSIDE the noise band
  (identical-prompt v9 rerun itself moved +0.0059) → logic repair, NOT an
  aggregate win**; the strategic_alliance cell is deterministically fixed
  **28/32 → 31/32** (Iovance/Giggles/Adaptimmune recovered with rule-28
  reasoning pinned; Intricon remains — the license carve-out didn't override
  the substance read), recovered 9 / regressed 6 (all 6 regressions argue
  from pre-existing Rule 9/13/24 machinery — no rule-28 pattern; 2 equiv-
  recovered). v9 remains aggregate champion; v12 joins the frontier as the
  strategic_alliance field specialist. Memo `memos/sorter_v12.md`. (Note: the
  FIRST v9 @509 rerun control was degraded — 42 transient
  `generator didn't stop after throw()` errors — replaced by a clean rerun.)

### Added
- **LegalBench test-set eval path (KANBAN-026)** — the official
  `nguha/legalbench` HF TEST splits are now evaluable despite the Braintrust
  org's log-bytes cap dropping dataset-row writes:
  `scripts/datasets/stream_legalbench_tasks_to_bt.py --test` fetches each
  task's test split via `fetch_hf_split`/`normalize_hf_rows` (paginated HF
  `/rows`), and `--local-dump <dir>` writes the SAME LegalBench-formatted
  records (filled few-shot `prompt`, `expected` label, metadata) to local
  JSONL instead of Braintrust (`write_local_jsonl`). Both
  `run_classification_eval.py` and `run_langfuse_classification_eval.py`
  gain `--task-dataset <jsonl>` (`load_task_dataset`) to evaluate those
  files directly — the local path is byte-for-byte the same row shape as a
  Braintrust dataset, so results stay same-surface comparable. New
  `scripts/eval/sync_langfuse_datasets.py` mirrors train + test records into
  Langfuse datasets (llm-dojo; `mailroom-lb-hearsay` 5 / `mailroom-lb-hearsay-test`
  94, deterministic content-addressed item ids → reruns upsert). `data/legalbench_local/`
  is gitignored. Tests: streamer `write_local_jsonl`↔runner `load_task_dataset`
  round-trip, `_sync_records` unit test, `--task-dataset` langfuse smoke
  (372 tests green).
- **`sorter_v10` + `sorter_v11` — marketing title-wins arm (KANBAN-013)** —
  the v9 close-out's "1-off long tail" plateau reading is superseded by
  cluster analysis: the **marketing cell ran 0.5/10 (243-doc) and 7/17
  (full-509) — the worst family accuracy on both surfaces, unchanged since
  v6** (v8/v9 both 10/17), all fails being marketing-titled docs
  re-classified by operative machinery (Monsanto→agency, Zounds→
  manufacturing, Principal→endorsement = rule-6 over-fire, Pacira→
  distributor, Todos→reseller, Vertex→JV, Audible→co_branding). **v10** =
  v9 + rule 26 MARKETING TITLE WINS (the R23/R24 title-wins doctrine
  mirrored to marketing; carve-outs: license-primary titles per annex
  inheritance, operational-service families transportation/hosting);
  **v11** = v10 + rule 27 AFFILIATE IS NOT MARKETING (boundary for the
  measured rule-26 over-fire: Cybergy + SteelVault, content-titled
  "Marketing Affiliate Agreement"). Same-surface 243-doc A/B (fp
  fb9f939d, seed 42, temp 0.1): **champion rerun noise floor = ±1 doc
  (0.9259 → 0.9300); v10 0.9342 and v11 0.9342 strict / 0.9424 equiv —
  delta +0.4pp inside the band (paired bootstrap CI [−0.0247, +0.0165],
  P(Δ≤0)=0.710) → logic repair, not a claimed win**. Rule-driven
  accounting: 4 deterministic recoveries (Monsanto, Principal, Todos,
  Dynamex), 2 affiliate restorations, 1 R27-wording regression (LinkPlus,
  equiv-recovered via affiliate↔joint_venture); **marketing cell 0.5 → 0.8
  at 243**. Banked lessons for the next arm (KANBAN-023): strategic_alliance
  title-wins (5 fails @509, 0-risk counterfactual), cooperation-title is
  collaboration (3 fails), rule-21 inversion mechanism. Memo
  `memos/sorter_v10_v11.md`; 357 tests green. (One append-only artifact: the
  first v11 launch hit a transient OpenRouter weekly-limit 403 and logged a
  strict-0.0 record; the rerun 15 min later succeeded — both records remain
  in the log.)
- **`contracts_specialist_v31` — token-efficiency refactor (KANBAN-021)** —
  same operative rules as v30, compressed: **−8.0% (2,679 chars; 8,377 →
  7,700 system tokens, −5.7%)** with every constraint preserved (28
  family-catalog entries, multi-item family-section rule, CoC-definition
  carve-out, additive re-scan, chunk-mode scalar quoting, term_length
  opener discipline, reasoning trace, formats). The v23 worked-example
  block (2,810 chars of verbatim quotes) is distilled into one-line
  family-boundary guidance — the lesson, not the text — and the
  EXHAUSTIVENESS/RE-SCAN/VERBATIM/SIZE-CALIBRATION boilerplate is merged
  with its overlapping neighbours. **Full-corpus A/B (509 docs, seed 42,
  chunked, current scorer): v31 0.8737 vs v28 0.8622 (+0.0116, paired
  bootstrap CI [+0.0005, +0.0236], P(Δ≤0)=0.021) with the leaner prompt —
  a Pareto win; no regression cluster** (term_length +0.058,
  termination_clauses +0.044, governing_law +0.014, key_obligations
  −0.003). Re-baseline: the 50-doc surface overstates the champion by ~6pp
  (v28 0.9228 @50 vs 0.8622 @510). 349→356 tests green (incl.
  `test_contracts_v31_token_efficiency_refactor`); 7,250-entry
  reasoning-trace corpus (14.2/doc) for the next reflection. The A/B was
  initially blocked by the OpenRouter weekly key limit and completed after
  a new key was installed (v28@510 resumed via manifest, v31@510 fresh).
  Memo `memos/contracts_specialist_v31.md` (v22→v31 token audit).
- **LegalBench HEARSAY task fully wired (KANBAN-022)** — the half-done sync
  completed end-to-end: `mailroom-lb-hearsay` synced from the actual
  LegalBench task data (binary Yes/No, 5 train rows / 95 test, 5 slices —
  statement made in-court, non-assertive conduct, standard hearsay,
  non-verbal hearsay, not-introduced-to-prove-truth; CC BY 4.0, Neel Guha),
  classes manifest written (`data/legalbench_classes.jsonl`), Braintrust
  task-mode eval path verified (`run_classification_eval.py --prompt-mode
  task --valid-classes Yes,No`), and **`run_langfuse_classification_eval.py`
  gains `--prompt-mode task`** (the mirror previously hardcoded the sorter
  doc-type path) — LegalBench tasks now trace into the llm-dojo Langfuse
  project with one `legalbench_task` observation per row carrying
  exact_match/confidence; task mode requires `--valid-classes` and defaults
  the prompt to `legalbench_task_v0`; 3 new smoke tests + 3
  `_deterministic_record_id` tests.
- **`upload_text_dataset` now inserts rows with deterministic
  content-addressed ids** (`src/braintrust_utils.py
  _deterministic_record_id`) — Braintrust's `insert` otherwise assigns a
  fresh random UUID per call, so every streamer rerun APPENDED duplicate
  rows (observed: `mailroom-lb-hearsay` held 2×5 identical rows after a
  partial + rerun). Reruns now upsert in place as the streamer docstrings
  always promised. KANBAN-022.
- **Root README credits section** — LegalBench (NeurIPS 2023, CC BY 4.0),
  CUAD / The Atticus Project (NeurIPS 2021), MAUD (Zenodo), the GEPA
  framework (arXiv 2507.19457), and the LangChain/LangGraph/Braintrust/
  Langfuse stack. KANBAN-022.
- **LegalBench-task docs updated with the actual hearsay data** — README
  (sorter's two jobs, sync step 3, loop examples incl. the Langfuse task
  mode), AGENTS.md cheatsheet, wiki/Eval-Runners.md (classification task
  mode + Langfuse mirrors + datasets), scripts/README.md,
  `stream_legalbench_tasks_to_bt.py` docstring. KANBAN-022.
- **First hearsay benchmark (KANBAN-022 live run)** —
  `qwen3.7-flash_legalbench_task_v0` on `mailroom-lb-hearsay` (5 rows, 2 Yes
  / 3 No, one row per slice): **exact_match 1.0 (5/5), failure 0.0,
  per-class no 1.0 / yes 1.0** — run twice, identical results on both the
  Braintrust-named surface (`_usage` rerun, 3,441 tokens, ~$0.00024) and the
  llm-dojo Langfuse mirror (`_classification_langfuse_usage`, 3,276 tokens,
  ~$0.00022, 5 `legalbench_task_classification` traces with exact_match +
  confidence scores, verified in llm-dojo). Caveats: the OpenRouter key used
  had a fresh weekly budget; the Braintrust ORG is at its monthly
  log-bytes plan limit (`num_log_bytes_calendar_months`), so the experiment
  row data does NOT upload to Braintrust until billing is addressed — the
  repo experiment log records (source of truth) are complete either way.
- **Master ground-truth CSV added to the repo + repo-local default
  (KANBAN-028)** — `data/cuad/master_clauses.csv` (the curated 510-contract
  CUAD ground-truth table, 40 normalized `-Answer` categories) is now
  committed so the extraction MAE/R² diagnostics no longer depend on the
  sibling llm-mailroom checkout. `DEFAULT_MASTER_LABELS` in
  `src/master_labels.py` resolves to the repo-local copy first
  (`MASTER_LABELS_CSV` env still wins; the sibling `../llm-mailroom/...` path
  is kept as fallback), and the loader now normalizes the CSV's one
  stray-space header variant (`Notice Period To Terminate Renewal- Answer`)
  so that category's answer loads (previously silently dropped by the
  `endswith("-Answer")` filter). Tests: repo-local CSV loads 510 rows +
  header-variant tolerance; 377 tests green.

### Fixed
- **`SorterAgent.classify_document([])` empty-input contract restored** (`agents/sorter_agent.py`) — the docclass-era guard (commit `9ca4f35`) returned `doc_type: None` on an empty page list, breaking the documented vision fallback (empty/unreadable input → `correspondence`); it now returns `doc_type: "correspondence"` (confidence 0.0) while keeping `unreadable: True`/`invalid_label: False` so the docclass vision-primary runner still classifies it as an unreadable fallback. Test: `tests/test_page_voting.py::test_classify_document_empty_input`.
- **Subtype smoke test isolated from the local `.env` LangSmith flag** (`tests/test_subtype_eval_smoke.py`) — the no-Braintrust loop test deleted `LANGSMITH_TRACING` from the process env, but the runner's dotenv load (`override=False`) re-enabled it from a local `config/environments/.env` (`LANGSMITH_TRACING=true`), failing the "LangSmith off by default" assertion; the test now pins the variable to a non-true value so the `.env` cannot re-enable it.
- **Posit portal pre-render intermediates untracked** (`site/_includes/`, `site/_variables.yml`) — they carry generation stamps and are gitignored by design (KANBAN-037); `git rm --cached` removes the accidental tracking so a fresh `quarto render site` leaves `git status` clean (the `test_quarto_render_is_deterministic_and_clean` gate).
- **`run_local_eval` shim now matches the `braintrust.EvalResult` contract**
  (`src/eval_shims.py`, KANBAN-026) — the no-Braintrust loop stored the FULL
  row dict as each result's ``input`` (so ``index`` resolved to -1 and
  ``r.expected`` was missing): the shared ``log_experiment_to_repo`` /
  ``print_classifications`` crashed on the classification runner, and the
  subtype/extraction/chained runners silently logged zero usage/cost on the
  disabled path. Each shim now carries the task's INNER input dict plus the
  row's ``expected``, so ``r.expected`` and ``index``-keyed usage/cost
  accounting resolve exactly as on the Braintrust path. Unit tests
  ``tests/test_eval_shims.py`` (375 tests green).
- **`BaseAgent._call_llm` now captures usage/cost** (`agents/base_agent.py`)
  — the plain-text completion path (LegalBench `--prompt-mode task`
  answers, judge calls) previously returned the string through
  `StrOutputParser` and NEVER set `_last_usage`, so task-mode experiment
  records carried `tokens: 0` / `cost: 0`. Now reads usage_metadata +
  response cost from the raw AIMessage, mirroring the structured + vision
  paths; content blocks are joined for list-form AIMessage content. 2 new
  unit tests. KANBAN-022.
- **HEARSAY v0 baseline (KANBAN-025, iteration-series step 1)** —
  `qwen3.7-flash_legalbench_task_v0_baseline` on `mailroom-lb-hearsay`
  (5 rows, one per slice): **exact_match 1.0 (5/5), per-class no 1.0 / yes
  1.0**, 3,585 tokens / ~$0.0003, replicated on the llm-dojo Langfuse mirror
  (`_classification_langfuse_baseline`, 3,481 tokens, 5
  `legalbench_task_classification` traces verified). **Read: the v0 prompt
  SATURATES the 5-row train surface — there is no headroom to measure
  iterative prompt improvements on this sample. Follow-on arm must sync the
  95-row LegalBench test set (``test.tsv``) so A/B deltas have resolution
  beyond the ceiling.**
 
### Fixed
- **`monte_carlo_failures.py` figure output honors `--out-dir`** — `make_figures` wrote the two scenario PNGs to the module-level repo `OUT_DIR` instead of the resolved `--out-dir`, so running the script (or its smoke test) with a custom out-dir silently overwrote the committed `reports/monte_carlo/failure-{scale-expected,sweep}.png`. Now takes the resolved `out_dir`; the smoke test no longer pollutes the committed figures. (Same pattern in `monte_carlo_ensemble.py` was already correct.)

## [v0.18.0] - 2026-08-15

> v0.18.0 — contracts specialist v26-v30 (term_length containment, multi-item family-section rule +4.48pp, noise-floor follow-up arm), extraction runner chunking, GEPA prompt-engineer agent, slides post-mortem decks

### Changed
- **`contracts_specialist_v29` + `contracts_specialist_v30` — follow-up
  logic repairs (KANBAN-020 arm)** — the v28 residuals, resolved with a
  noise-floor control (identical-prompt rerun of the v28 champion on the
  same 50-doc chunked surface: **±0.03 overall band, ~12 docs move >±0.02
  per field** — the surface's resolution limit). Per-span sim-matrix diff
  on the 4 regressed docs: Ediets' Change-of-Control DEFINITION spans were
  suppressed by v28's "definitions are NEVER items" criterion — a
  rule-vs-rule contradiction with the v10 re-scan note ("the defined term
  itself"); **v29 adds the carve-out** (CoC-family definitions ARE items —
  Ediets recovers 0.692→0.769). **v30 patches CHUNK DUTY** (scalar fields
  keep their exact quoting rules in every chunk; prefix-only/null
  term_length with the clause visible is a miss — the chunked-v26 collapse
  mechanism: Ritter "five (5) years" only, Phasebio null). Both measure
  INSIDE the noise band (paired deltas −0.0264/−0.0382 vs the identical-
  prompt rerun's −0.0293) — shipped as unmeasured logic repairs; **v28
  remains the champion (re-validated vs v26: +0.0448, CI [+0.0087,
  +0.0891], P=0.004)**. Also resolved: renewal_terms dip = 1 doc (NOVO,
  quote-truncation variance); Gridiron `":"` = 1-off (fresh runs 1.0);
  LinkPlus/Innerscope/LegacyTechnology regressions = noise. Memo
  `memos/contracts_specialist_v30.md`.
- **`run_extraction_eval.py` gains `--chunked/--chunk-chars/
  --chunk-overlap`** (the Braintrust runner previously could NOT chunk) +
  a dry-run truncation-confound warning when unchunked + `chunked`/
  `n_chunks` audit fields per row (`_last_chunked`/`_last_n_chunks` on
  `_SpecialistBase`). KANBAN-020.
- **`.opencode/agents/prompt-engineer.md` now runs the full GEPA workflow**
  (arXiv 2507.19457 reflective prompt evolution): sample trajectories →
  natural-language reflection on failures (sim-matrix miss classification)
  → one-lesson mutations → same-surface A/B with the noise-floor control →
  Pareto-aware selection across score/cost/robustness with a candidate
  frontier and cross-candidate lesson combining; plus the chunked-surface
  discipline and the rule-contradiction check in every mutation. AGENTS.md
  agent section updated. KANBAN-020.
- **`contracts_specialist_v27` + `contracts_specialist_v28` — multi-item
  family-section rule (KANBAN-004 arm)** — the key_obligations span
  residual: pairwise-similarity classification of every miss on the 50-doc +
  sample5 surfaces showed ~60–70% of misses are NEAR (sim 0.35–0.59) —
  **wrong-span at sentence level inside multi-requirement family sections**
  (the model quotes ONE sentence per insurance/audit/license/ROFR section
  while the GT holds 3–10 distinct requirement sentences: Ritter emitted
  insurance-procurement but not primary-of-all-purposes/additional-insured;
  the audit section's 10 GT spans went ~0). v27 states the rule directly
  (a family section is MULTI-ITEM — each distinct requirement sentence is
  its own item); v28 sharpens it with the two trace lessons (definitional
  sentences — "any X Property or improvements thereto which are used…" —
  are NEVER items; the completion re-scan only ADDS items, never removes).
  Same-surface 50-doc chunked A/B (seed 42, qwen3.7-flash, current scorer):
  **v28 0.9228 vs v26 0.8780 overall (+4.48pp, bootstrap 95% CI [+0.0094,
  +0.0907], P(Δ≤0)=0.004)**; key_obligations +11.4pp (0.7606→0.8747, 20
  recovered vs 4 regressed docs — regressions are single-span losses on
  ≥0.85 docs, no new pattern); term_length +0.040; tokens +6.7%. Also
  documented: the sample5 A/B surface is truncation-confounded
  (`chunked=false` — Phasebio 0.125 unchunked vs 0.94 chunked) — pilot
  surfaces must use `--chunked` for key_obligations to be measurable.
  KANBAN-004, issue #3 closed.
- **`contracts_specialist_v26` — term_length containment fix (KANBAN-017
  arm)** — v24's canonical-duration-prefix rule made the model REPLACE the
  clause opener with the duration phrase (the CUAD ground-truth span IS the
  opener: Ediets "This Agreement will become effective as of the Effective
  Date and, unless sooner terminated pursuant to Sections 3.1" — containment
  1.0→0.3333). v25's additive-prefix wording + worked example recovered
  Ediets (containment 1.0) but leaked the example's sentence template into
  OTHER documents (Ritter/Phasebio quoted the example clause with the
  duration swapped in). **v26** keeps the additive prefix and forbids
  dropping the opener, shows opener variants to match THIS document's
  wording, and bans reusing the instructions' wording — no template
  leakage. Same-surface 5-doc A/B (seed 42): **v26 term_length 1.0000 and
  overall 0.9447 — best of the arm** (v23 0.9366, v24 0.9336, v25 0.9154);
  all three term_length docs containment 1.0. KANBAN-017.
> Extraction regression diagnostics (date/duration/money MAE + R² vs master labels, span-count drift, error decomposition), contracts specialist v24 reasoning trace + metrics-aligned formats, inter-agent workflow (AGENTS.md), full-corpus CUAD EDA, sorter v9 full-scale benchmark, annotation-queue status fix
### Added
- **`prompt-engineer` agent — the master diagnostic evaluator & prompt
  engineer** — new `.opencode/agents/prompt-engineer.md` (project agent,
  `mode: all`): its SOLE role is to review all traces, reasoning logic,
  failures, error messages, and results of every evaluated prompt and
  produce a stronger, refined, data-backed mutation (new `PROMPT_VERSIONS`
  key, never an edit to a run prompt). Encodes the repo's full iteration
  contract: the diagnose → root-cause → mutate → verify → land loop, the
  failure taxonomy (extraction: boundary-shift / abbreviation / wrong-span
  / hallucination / scope; sorter: `function_over_form` /
  `other_fallback` / `equivalent_family` / `family_confusion`),
  same-surface A/B discipline with bootstrap-CI verdicts and per-row
  recovered-vs-regressed checks, the **plateau/overfit doctrine** (rules
  for failure CLUSTERS not 1-off outliers, family-level generalization
  test, MAE/R² evidence floor on pair counts, cost-as-tradeoff), and
  board + CHANGELOG + memo close-out with proof. `AGENTS.md` gains the
  "Agents (this repo)" section documenting it alongside
  experiment-log-sync. KANBAN-018.


### Changed

## [v0.17.0] - 2026-08-15

### Changed
- **`ContractsSpecialist` extraction carries a full per-field reasoning
  trace** — `CONTRACTS_SCHEMA` gains a required `reasoning` object (leading
  the schema: `summary` + `entries[{field, evidence, section_ref}]`),
  produced BEFORE the extraction values are finalized; the chunked-merge
  unions reasoning entries across windows (dedupe by field, first-witness
  evidence wins, summaries joined) so the trace covers the whole document;
  `_evidence_confidence` excludes the meta field. New prompt
  `contracts_specialist_v24` (derived from v23, base untouched): the
  REASONING BEFORE OUTPUT duty + metrics-aligned format discipline —
  `term_length` leads with the canonical duration phrase ("two (2) years"),
  `contract_value` stays a plain currency phrase ("$2,000,000") so the
  date/duration/money regression diagnostics (MAE + R² vs master labels)
  can parse more predicted values (format alignment only — the master CSV
  never reaches the model). 5-doc same-surface A/B (seed 42):
  v24 0.9336 vs v23 0.9366 overall (noise), **key_obligations +10.2pp
  (0.5984→0.7006)**, reasoning trace on 5/5 rows both runs (schema-driven),
  tokens +2.5%; term_length containment dipped on 1 doc (leading-phrase
  quote trades containment credit for parseability — monitored in the next
  arm). 6 new network-free tests; 341 total green. KANBAN-016.
- **`AGENTS.md` board section restructured into the full inter-agent
  workflow** — "Agent message board & inter-agent workflow": session
  pre-flight protocol (board read → rule-4 sanity sweep → name check →
  announce intent), the six-phase task lifecycle (card-first → claim →
  in_progress-from-first-edit → communicate-during → verify → close with
  proof → finish protocol), the inter-agent communication framework
  (channel hierarchy with the board discussion log canonical, what-to-post-
  when table), and the anti-trampling protocol (one owner per card, card-
  owned files, **experiment-name reservation before any run** — Braintrust
  silently suffixes re-runs so a shared name is a silent collision — one
  run one owner, task-relation rule, conflict rule, no silent completion).
  GitHub issue sync formalized as §5. KANBAN-015.
### Added
- **Full-corpus EDA of the CUAD contracts dataset** — new
  `scripts/eda/explore_cuad.py` (Braintrust full-corpus text aligned 510/510
  to the CUAD titles, with local-txt / CUAD-context fallback) rendering
  `data/eda/report.md`, `data/eda/findings.md`, and `data/eda/figures/01`–`10`
  (subtype distribution, text-length hist + pipeline budget lines, category
  YES rates, category span load, spans/doc, filing families, per-subtype
  lengths, restriction co-occurrence heatmap, annotation density) — all
  git-tracked. Headline numbers: median 33,425 chars (mean 52,563, max
  338,211); 17.1% of contracts exceed the 90k-char chunk window and 9.4% a
  32k-token context; the extractor's `key_obligations` scope (31 of 41
  categories) averages 16.0 spans/doc (49 contracts null); Anti-Assignment +
  Change Of Control co-occur in 98% of the less-common docs; 131 contracts
  carry `[***]`-style redaction markers. KANBAN-014.
- **Extraction regression diagnostics — MAE + R² as tracked performance
  metrics** — new `src/metrics.py` (run-level `scores.diagnostics`:
  field-level error decomposition, raw list P/R/F1 macro+micro, date and
  duration MAE, and the **coefficient of determination** `date_r2` /
  `duration_r2` = `1 − SS_res/SS_tot` over predicted-vs-expected
  date/duration pairs, negative kept as a signal) + new
  `src/master_labels.py` (curated `master_clauses.csv` loader; preferred
  parse source for the expected values, raw CUAD clause text the fallback)
  + `--master-labels` flag / `MASTER_LABELS_CSV` env on the extraction
  runners (Braintrust + Langfuse mirror); `field_scoring.parse_date` public
  alias; GH Pages per-run breakdown surfaces the headline diagnostics.
  18 new network-free tests (`tests/test_metrics.py` + smoke coverage).
  KANBAN-015.
- **Diagnostics extended: money MAE + span-count drift + support sizes** —
  `src/metrics.py` gains `money_mae_usd`/`money_median_ae_usd` (+
  per-field buckets; `parse_money` public alias in `src/field_scoring.py`),
  `span_count_mae` / `span_count_signed_mean` (+ per-field buckets,
  `span_count_n_docs` — symmetric item-count error vs signed
  over/under-extraction direction over list fields), and evidence
  denominators `date_n_pairs` / `duration_n_pairs` / `money_n_pairs` on
  every MAE/R² row. 4 new network-free tests (30 in `tests/test_metrics.py`).
  KANBAN-015.
- **Run-level diagnostics rendered in the experiment log + site** — new
  `_diagnostics_lines()` in `src/experiment_log.py` renders
  `scores.diagnostics` as grouped markdown tables (list quality with
  macro+micro P/R/F1, regression error with MAE/R² + pair counts, span-count
  drift, field error decomposition); the generic nested-scores path now
  skips `diagnostics` (dedicated section only). The GH Pages run-detail view
  gains a **Run-level diagnostics card** (`docs/assets/site.js`
  `diagnosticsCard()` + `.diag-block` styles). Renderer test added
  (`test_experiment_markdown_renders_diagnostics_section`); site render
  audit green. KANBAN-015.
- **Scoring-method slide decks** — `docs/slides/` (7 decks + index): example
  inputs/outputs and concise scientific explanations of every scoring
  method (field-type scoring, entity-list bipartite matching + P/R/F1
  macro/micro, MAE/R² regression diagnostics with the master-labels ground
  truth, factuality audit, failure analysis, reading the experiment log) —
  written for parallel researchers without time for the full docs. Includes
  a REAL diagnostics block captured from a 2-doc pilot
  (`pilot_diag_v22_sample2`, seed 42, master labels CSV active: dates MAE 0 /
  R² 1.0; `key_obligations` 43 predicted vs 18 expected → span-count +10.5,
  raw precision 0.31 — a textbook over-extraction signal). KANBAN-015.
### Fixed
- **`run_annotation_queue.py status` unbounded trace scan** — `status` now
  honors `--since-days` (default 30, shared with `build`) when building the
  item metadata map; previously it scanned the full trace history
  (`list_extraction_traces(..., since=None)`), which stalled for minutes on
  the subtype task under Langfuse rate limits. `--session-contains` remains
  the way to scope either subcommand to one run family.
### Added
- **Sorter scale-up — v9 re-baseline + full-509 v8/v9 benchmark**: three
  cheap runs (~$0.25, 1213 classifications) settle the scale question.
  **v9 @ 509 = 0.9116 strict / 0.9194 equiv, beating v8 @ 509 (0.9018 /
  0.9096) by +0.98pp — the v6→v9 rule iterations hold at full scale.**
  The re-baseline (v9 @ 195 = 0.8872) settles the 0.95-era question: the
  0.9436-era v6 number lived on the OLDER corpus revision (fingerprint
  2e1fe4b7 vs fb9f939d) — the 0.95 target was revision-confounded.
  Sample-size behavior is non-monotonic but bounded (v9: 0.8872 → 0.9259
  → 0.9116 across 195/243/509); the full-set number is the stable
  estimate. Full matrix: `V16_PROPOSITION.md` §19.

## [v0.16.0] - 2026-08-13

### Added
- **`sorter_v9` — the title-wins A/B (v9 WINS, +2.88pp strict)**: three
  data-backed rules from the exact v8 residual — 23. PROMOTION TITLE WINS
  (COLOGUARD/CO-PROMOTION/PROMOTION AND DISTRIBUTION agreements are
  promotion despite marketing/distribution machinery), 24. OUTSOURCING
  TITLE WINS (outsourcing-titled docs are outsourcing even when the
  outsourced services ARE manufacturing), 25. CUSTOMIZATION SCHEDULES ARE
  MAINTENANCE (annex inheritance for customization schedules). Same-surface
  A/B (243-doc stratified, seed 42, qwen3.7-flash, medium, llm-dojo):
  **strict 0.8971 → 0.9259 (+2.88pp), equiv 0.9012 → 0.9259, 25 → 18
  fails; all three target clusters eliminated**. Cumulative v6→v9:
  **+5.8pp strict (0.8683 → 0.9259)**. The remaining 18 fails are a 1-off
  long tail (no cluster >2) — ~0.93 is the practical plateau on this
  corpus revision; 0.95 needs tail-sampling iterations or a re-baseline.
  Full record: `V16_PROPOSITION.md` §18.
- **`sorter_v8` — the development/IP clusters A/B (v8 WINS, +2.06pp
  strict)**: two data-backed rules from the exact 8 v7 failures —
  21. DEVELOPMENT VERSUS COLLABORATION, LICENSE, AND FRANCHISE STRUCTURES
  ("Collaborative Development" agreements are development; "Development
  Agreement" titles stay development when grants/franchise structures
  deliver the developed materials) and 22. INTELLECTUAL PROPERTY
  AGREEMENTS ARE ip (IP-titled docs are ip despite license/JV sections).
  Same-surface A/B (243-doc stratified, seed 42, qwen3.7-flash, medium,
  llm-dojo): **strict 0.8765 → 0.8971 (+2.06pp), equiv 0.8889 → 0.9012,
  30 → 25 fails; both target clusters eliminated** (development→
  collaboration/license/franchise 5 → 0, ip→license/joint_venture 3 → 0).
  Cumulative v6→v8: +2.9pp strict. Remaining: promotion-title→marketing
  (2), outsourcing→manufacturing (2), customization-schedule annex (1)
  plus a 1-off tail — v9 rules designed, 0.95 strict is a multi-iteration
  target on this corpus revision. Full record: `V16_PROPOSITION.md` §17.
- **`sorter_v7` — the final classification A/B (250-sample) — v7 WINS
  (+0.82pp strict)**: three data-backed rules targeting the v6 509-doc
  full-corpus fails (strict 0.9312, 35 fails): consortium O&M →
  maintenance (shared-infrastructure governance wrappers do not make an
  agreement a joint_venture), development-over-license (development
  machinery wins over license grants for the developed IP), and the
  promotion guard (promotion title/core is its own family, not marketing or
  distributor). Constant + `PROMPT_VERSIONS` entry + unit tests landed;
  **same-surface A/B (mailroom-cuad-contracts-full, stratified 250 seed 42
  → 243 docs, qwen3.7-flash, medium reasoning, llm-dojo): strict 0.8683 →
  0.8765 (+0.82pp), equiv 0.8807 → 0.8889 (+0.82pp); the promotion→
  marketing cluster (6 errors) is eliminated; 32 → 30 fails.** Caveat: the
  current corpus revision (fingerprint fb9f939d…) is harder than the
  revision behind the 195-doc 0.9436 runs (2e1fe4b7…) — v6 itself scores
  0.8683 on it, so the >0.95 strict target needs further iterations on the
  development-family and ip→license confusions. Full record:
  `V16_PROPOSITION.md` §16.
- **Research memos — site polish + visualization pass**: all 9 memos
  re-checked through the site's actual `renderMd` — fixed two rendering
  glitches (a `[***]` redaction marker inside a table cell that stole the
  next bold pair; a `\*` footnote escape), de-indented paragraph
  continuations (double-space artifacts), and added a standardized
  **scorecard table + Verdict callout** to each memo that lacked a top-line
  results display. All memos verified CLEAN through the render harness and
  the headless render audit.
- **Annotation-queue score-config support**: `run_annotation_queue.py` now
  lists and creates Langfuse score-configs
  (`get_or_create_annotation_config`) and auto-provisions the default
  annotation score-config id when `--score-config-ids` is not given;
  `FakeLangfuse` mocks the new GET/POST routes to exercise the flow in
  `tests/test_annotation_queue.py`.
- **Agent message board — the cross-repo Kanban + GitHub issue routing**:
  `board/MESSAGE_BOARD.md` is the living Kanban canvas shared by ALL agents
  across **llm-entity-extraction and llm-mailroom** — `backlog` /
  `in_progress` / `blocked` / `in_review` / `done` lanes with timestamps,
  an append-only discussion log, and an audit archive (finished cards are
  kept for auditability, never deleted). Governance codified in `AGENTS.md`
  (§"Agent message board — READ THIS FIRST, EVERY SESSION"):
  read-the-board-first every session; claim → Owner + timestamp; **work
  underway = `in_progress` immediately, never `backlog`** (the `git status`
  sanity check before every commit); the six-point completion & issue-close
  criteria (verified work + clean tree, CHANGELOG entry in the same commit,
  card archived with version/commit/result, timestamped closing discussion
  entry, issue closed in the same commit, no orphaned scope); releases
  sweep cards to the Archive in semver lockstep with `CHANGELOG.md`.
- **Kanban → GitHub issue routing**: critical / high-priority / cross-repo
  cards route to dedicated GitHub issues (label `kanban`) opened in the
  repo where the work lands — each synced card's `Issue` column carries the
  FULL markdown link to its own dedicated issue (`[#NNN](url)`),
  one card = one issue, issue body ↔ card never disagree about status,
  issues close in the same commit that archives their card. Board-only
  cards (small, single-session) skip issues.
- **Site — agent board tab**: the Kanban board renders read-only on the
  experiment-log site as the `#/board` view (`build_site.py` emits
  `docs/data/board.json`; docs/README documents it); card links jump to
  the corresponding GitHub issue.
### Removed
- **Per-run cost/usage telemetry from the site data**: `docs/data/` now
  omits embedded OpenRouter cost/usage objects (the `costs` meta block and
  per-run `cost`) — the site no longer displays detailed cost telemetry;
  the append-only `reports/experiment_log.jsonl` remains the record of
  tokens/cost per run.


### Added
- **`sorter_v9` — the title-wins A/B (v9 WINS, +2.88pp strict)**: three
  data-backed rules from the exact v8 residual — 23. PROMOTION TITLE WINS
  (COLOGUARD/CO-PROMOTION/PROMOTION AND DISTRIBUTION agreements are
  promotion despite marketing/distribution machinery), 24. OUTSOURCING
  TITLE WINS (outsourcing-titled docs are outsourcing even when the
  outsourced services ARE manufacturing), 25. CUSTOMIZATION SCHEDULES ARE
  MAINTENANCE (annex inheritance for customization schedules). Same-surface
  A/B (243-doc stratified, seed 42, qwen3.7-flash, medium, llm-dojo):
  **strict 0.8971 → 0.9259 (+2.88pp), equiv 0.9012 → 0.9259, 25 → 18
  fails; all three target clusters eliminated**. Cumulative v6→v9:
  **+5.8pp strict (0.8683 → 0.9259)**. The remaining 18 fails are a 1-off
  long tail (no cluster >2) — ~0.93 is the practical plateau on this
  corpus revision; 0.95 needs tail-sampling iterations or a re-baseline.
  Full record: `V16_PROPOSITION.md` §18.
- **`sorter_v8` — the development/IP clusters A/B (v8 WINS, +2.06pp
  strict)**: two data-backed rules from the exact 8 v7 failures —
  21. DEVELOPMENT VERSUS COLLABORATION, LICENSE, AND FRANCHISE STRUCTURES
  ("Collaborative Development" agreements are development; "Development
  Agreement" titles stay development when grants/franchise structures
  deliver the developed materials) and 22. INTELLECTUAL PROPERTY
  AGREEMENTS ARE ip (IP-titled docs are ip despite license/JV sections).
  Same-surface A/B (243-doc stratified, seed 42, qwen3.7-flash, medium,
  llm-dojo): **strict 0.8765 → 0.8971 (+2.06pp), equiv 0.8889 → 0.9012,
  30 → 25 fails; both target clusters eliminated** (development→
  collaboration/license/franchise 5 → 0, ip→license/joint_venture 3 → 0).
  Cumulative v6→v8: +2.9pp strict. Remaining: promotion-title→marketing
  (2), outsourcing→manufacturing (2), customization-schedule annex (1)
  plus a 1-off tail — v9 rules designed, 0.95 strict is a multi-iteration
  target on this corpus revision. Full record: `V16_PROPOSITION.md` §17.
- **`sorter_v7` — the final classification A/B (250-sample) — v7 WINS
  (+0.82pp strict)**: three data-backed rules targeting the v6 509-doc
  full-corpus fails (strict 0.9312, 35 fails): consortium O&M →
  maintenance (shared-infrastructure governance wrappers do not make an
  agreement a joint_venture), development-over-license (development
  machinery wins over license grants for the developed IP), and the
  promotion guard (promotion title/core is its own family, not marketing or
  distributor). Constant + `PROMPT_VERSIONS` entry + unit tests landed;
  **same-surface A/B (mailroom-cuad-contracts-full, stratified 250 seed 42
  → 243 docs, qwen3.7-flash, medium reasoning, llm-dojo): strict 0.8683 →
  0.8765 (+0.82pp), equiv 0.8807 → 0.8889 (+0.82pp); the promotion→
  marketing cluster (6 errors) is eliminated; 32 → 30 fails.** Caveat: the
  current corpus revision (fingerprint fb9f939d…) is harder than the
  revision behind the 195-doc 0.9436 runs (2e1fe4b7…) — v6 itself scores
  0.8683 on it, so the >0.95 strict target needs further iterations on the
  development-family and ip→license confusions. Full record:
  `V16_PROPOSITION.md` §16.
- **Research memos — site polish + visualization pass**: all 9 memos
  re-checked through the site's actual `renderMd` — fixed two rendering
  glitches (a `[***]` redaction marker inside a table cell that stole the
  next bold pair; a `\*` footnote escape), de-indented paragraph
  continuations (double-space artifacts), and added a standardized
  **scorecard table + Verdict callout** to each memo that lacked a top-line
  results display. All memos verified CLEAN through the render harness and
  the headless render audit.
- **Annotation-queue score-config support**: `run_annotation_queue.py` now
  lists and creates Langfuse score-configs
  (`get_or_create_annotation_config`) and auto-provisions the default
  annotation score-config id when `--score-config-ids` is not given;
  `FakeLangfuse` mocks the new GET/POST routes to exercise the flow in
  `tests/test_annotation_queue.py`.
- **Agent message board — the cross-repo Kanban + GitHub issue routing**:
  `board/MESSAGE_BOARD.md` is the living Kanban canvas shared by ALL agents
  across **llm-entity-extraction and llm-mailroom** — `backlog` /
  `in_progress` / `blocked` / `in_review` / `done` lanes with timestamps,
  an append-only discussion log, and an audit archive (finished cards are
  kept for auditability, never deleted). Governance codified in `AGENTS.md`
  (§"Agent message board — READ THIS FIRST, EVERY SESSION"):
  read-the-board-first every session; claim → Owner + timestamp; **work
  underway = `in_progress` immediately, never `backlog`** (the `git status`
  sanity check before every commit); the six-point completion & issue-close
  criteria (verified work + clean tree, CHANGELOG entry in the same commit,
  card archived with version/commit/result, timestamped closing discussion
  entry, issue closed in the same commit, no orphaned scope); releases
  sweep cards to the Archive in semver lockstep with `CHANGELOG.md`.
- **Kanban → GitHub issue routing**: critical / high-priority / cross-repo
  cards route to dedicated GitHub issues (label `kanban`) opened in the
  repo where the work lands — each synced card's `Issue` column carries the
  FULL markdown link to its own dedicated issue (`[#NNN](url)`),
  one card = one issue, issue body ↔ card never disagree about status,
  issues close in the same commit that archives their card. Board-only
  cards (small, single-session) skip issues.
- **Site — agent board tab**: the Kanban board renders read-only on the
  experiment-log site as the `#/board` view (`build_site.py` emits
  `docs/data/board.json`; docs/README documents it); card links jump to
  the corresponding GitHub issue.

### Removed
- **Per-run cost/usage telemetry from the site data**: `docs/data/` now
  omits embedded OpenRouter cost/usage objects (the `costs` meta block and
  per-run `cost`) — the site no longer displays detailed cost telemetry;
  the append-only `reports/experiment_log.jsonl` remains the record of
  tokens/cost per run.

## [v0.15.0] - 2026-08-12


### Added
- **`contracts_specialist_v23` × reasoning=max — the ko-justified arm**:
  ko **0.8510** (best since v19's 0.8840), 50/50 rows (zero parse errors —
  vs v19's 1/50), ellipsis 18.7% (lowest of the max arms), overall 0.9363
  (CI .899-.964), verified_precision 0.974, $0.103. Within 3.3pp of the
  v19 peak without its parse-error risk or −2.3pp overall penalty —
  v23×max is the ko-justified production arm; v22×none (overall 0.9512)
  remains the overall champion. Full matrix: `V16_PROPOSITION.md` §15.
- **Same-scorer re-scoring pipeline** (`scripts/reporting/rescore_manifests.py`):
  re-scores any extraction manifest with the CURRENT scorer (consistent
  no-embedding pass) — the historical records stay append-only while every
  comparison becomes immune to scorer drift. `--auto-50` covers the 50-doc
  seed-42 series (v13→v23); report in `reports/same_scorer_scores.json`.
  String-level insight: the v19+ arms lean harder on the embedding rescue
  (official ko 0.83-0.85 vs string-level 0.38-0.43). Network-free smoke
  tests in `tests/test_rescore_manifests.py`.
- **Langfuse prompt-store cleanup**: the pre-idempotency-fix duplicate v2
  prompt versions are gone — the version-scoped delete route 404s on this
  instance, but delete-all + re-sync left all 45 prompts with exactly one
  version (verified version=1) and clean production/latest labels.
- **0-ko docs postmortem (corrected)**: SPRINGBANK/QBIOMED/PelicanDelivers
  are NOT failures — their CUAD GT holds ZERO obligation-family spans
  (QBIOMED is a Schedule 13G joint filing), so ko is None (excluded), not
  0.0, in every arm. Earlier "0-ko" references were token-level-audit
  artifacts. One scope note: PelicanDelivers' 11 payment-milestone items
  are general payment duties the prompt excludes (harmless — no GT).
- **`contracts_specialist_v23` — worked-example set v2 (the residual-34
  spans)**: built from the exact 34 GT spans v18 matched that v22 misses.
  Key finding: the v19 trademark NEGATIVE example was over-broad — it
  suppressed GT-labeled mark-ownership-use restrictions (Ritter "register,
  use or claim ownership") and mark non-tarnishment (ARMSTRONGFLOORING)
  along with the intended hygiene duties; v23 disambiguates mark-HYGIENE
  (operational) from mark-ownership-use / non-tarnishment (items) and adds
  verbatim positives for the recurring missed shapes (audited-statement
  delivery, revenue remittance/commissions, all-requirements supply,
  firm-service commitments, liability-cap fragments, post-termination
  exhaustion, sell-off revenues subject to royalties, joint trademark
  registration, sublicense-to-affiliates, option windows, "at cost without
  markup"). Results (same 50 docs, seed 42, chunked, llm-dojo,
  reasoning=none): **ko 0.8374 (best none-reasoning arm; trend 0.8168 →
  0.8294 → 0.8374), 42 spans recovered at token level (Ritter supply,
  PHREESIA assignment, Phasebio additional-insured) vs 31 lost**, overall
  0.9315 (v22's 0.9512 stays the champion — v23's field variance
  effective_date 0.917 / verified_precision 0.973 is same-surface noise,
  not a prompt effect). Full record: `V16_PROPOSITION.md` §14.
- **`contracts_specialist_v22` — ko-recovery rules (verbatim completeness +
  disciplined dedupe)**: the v21 span-level audit found 38 v18-matched GT
  spans lost to (1) ellipsis abbreviation (23.6% of v21 items contain
  "...", vs v18 15.8%) and (2) over-deduplication (LegacyEducation fell
  19→12 items — records, insurance, sell-off and assignment-exception
  clauses dropped). v22 narrows the dedupe to exact repeats and
  sentence/fragment pairs of the SAME requirement and adds VERBATIM
  COMPLETENESS (never ellipses). Results on the same 50 docs (seed 42,
  chunked, llm-dojo): **v22×none — overall 0.9512 (series best, CI
  .934-.967), ko 0.8294, ellipsis 19.5%, 50/50 rows, $0.039; v22×max —
  ko 0.8442, overall 0.9446, verified_precision 0.996, 50/50 rows (zero
  parse errors — the v22 output discipline retired the max-reasoning
  error rate), $0.100**. The ko regression is diagnosed as partially
  variance (identical-setting passes swing ±2.2pp), partially content
  (the v19+ content family plateaus ~0.83-0.85 at reasoning=none), and
  partially the reasoning setting (max adds +1.5pp on v22; v19's 0.8840
  was the favorable max roll). Production arm: v22×none. Full matrix:
  `V16_PROPOSITION.md` §13.
- **Langfuse two-project strategy (per direction)**: llm-dojo is where
  THIS repo's prompt iterations run (individual prompt improvements);
  llm-mailroom (llm-mailroom-experiments) is EXCLUSIVELY for testing and
  improving the full mailroom pipeline in the llm-mailroom repo — insights
  flow llm-dojo → llm-mailroom, never the reverse. Documented in AGENTS.md
  and `src/langfuse_config.py`; `sync_langfuse_prompts.py` supports both
  projects via repeatable `--env-file` (v22 synced to llm-dojo — 1 created,
  43 unchanged, idempotent).
- **Human-in-the-loop annotation queue for low-performing extraction
  traces** (`scripts/eval/run_annotation_queue.py`): scans the llm-dojo
  mirror's `contract_entity_extraction` traces (session-scoped to the
  extraction pipeline, prompt-version scoped to the contracts specialist),
  ranks them by the attached deterministic `overall_extraction_score`
  (worst first), and enqueues the ones below `--threshold` (default 0.85)
  into a Langfuse **annotation queue** as `PENDING` review items —
  idempotent (queue created once by name; already-enqueued traces never
  re-enqueued). `status` subcommand lists queue items with per-trace
  scores and review URLs. The queue is the HITL loop around the
  experiment cycle: `build` → human review/annotation in the Langfuse UI →
  annotations feed the next prompt iteration. `--dry-run` scans without
  writing; 10 network-free tests (`tests/test_annotation_queue.py`).
  Live-setup hardening: the queue auto-creates its own `annotation-verdict`
  categorical score config (correct/partial/incorrect) when none is passed
  (the API requires ≥1 config id); 429 rate-limit retries honor the
  server's `retryAfterSeconds`; `status` reads scores via the bulk v3
  scores endpoint (cursor-paginated, `subject` field group) instead of one
  request per trace; the queue's review URL is printed. Live on llm-dojo:
  queue `entity-extraction-low-performers` with 137 PENDING items.
- **Sorter failure queue (`--task subtype`)**: the same tool now serves the
  subtype-classification pipeline — `build --task subtype` enqueues every
  trace where the PRIMARY CLASS (doc_type), the contract SUBTYPE (CUAD
  folder), or both FAILED (read from the sorter's output composite,
  `doc_type_ok`/`subtype_ok`; both-failures lead). The Langfuse Hobby plan
  allows ONE annotation queue per project, so sorter items share the
  existing queue and `status --task <task>` filters items by trace name
  (extraction vs `subtype_classification`); sorter status shows
  exact_match / subtype_accuracy / subtype_accuracy_equiv / confidence
  with the failure flags. Live on llm-dojo: +35 PENDING sorter failures
  (2 class-failed, 35 subtype-failed) across the sorter_v6 runs.
- **`contracts_specialist_v21` — the merge arm, ADOPTED as the production
  arm**: v20's prompt text (v19 ko content + the four field rules) at
  **reasoning_effort=none**, same 50 docs, seed 42, chunked, Langfuse
  llm-dojo. Canonical record (run 051, `_50b`, fixed scorer): **overall
  0.9283 → 0.9396 (+1.7pp vs v18 — best on the flash line), 50/50 rows
  (zero parse errors — the EdietsComInc EX-10.4 failure from v19 is
  resolved: max reasoning burned the 32k structured-output budget; at
  reasoning=none the completion budget is the JSON alone), verified_precision
  0.997, effective_date 0.945, renewal_terms 0.905 (+6.4pp), parties 0.980,
  document_name 0.991, cost $0.039 (2.6x cheaper than max reasoning)**.
  The prompt-vs-reasoning confound is resolved: the +3pp v19 ko gain was
  the max-reasoning setting, not the worked examples (at fixed none,
  v19/v20 content scores ko 0.8385 vs v18's 0.8535; v19 keeps the ko crown
  0.8840 at 2.6x the cost and a 1/50 parse-error risk). Full record:
  `V16_PROPOSITION.md` §12.
- **Date-scorer bug fixes (field_scoring.py)**: the v20-era null-expectation
  rule (a) fired on parseable compact dates ("11/4/10" — three PERFECT
  matches scored 0.0) — now gated on `_parse_date(expected) is None`; and
  (b) was never reached for `pred is None` (the short-circuit returned 0.0)
  — the None path now consults the rule, so the five blank-template docs
  score 1.0 for the model's CORRECT null answer. effective_date 0.806 →
  0.945 on v21. SCORING.md §3 updated; regression tests added.
- **All experiments run in llm-dojo; prompts synced between projects**:
  `src/langfuse_config.py` defaults and `langfuse.env` label now read
  llm-dojo (the project-scoped keys have routed every trace there all
  along — verified via the traces API). New
  `scripts/eval/sync_langfuse_prompts.py` mirrors every PROMPT_VERSIONS key
  as a Langfuse text prompt — idempotent (skips unchanged latest-version
  content), `--dry-run`, repeatable `--env-file` so a second project
  (e.g. the primary llm-mailroom environment) is a drop-in with its own
  key file. 43 prompts synced to llm-dojo; network-free smoke tests in
  `tests/test_sync_langfuse_prompts.py`; workflow documented in AGENTS.md
  ("After every run"). Note: the first sync predated the idempotency fix
  and left duplicate v2 versions with identical content in llm-dojo
  (cosmetic; the version-delete API path 404s on this instance).
- **`contracts_specialist_v20` — non-obligation field fidelity (rules
  validated; arm ko-variance-dominated)**: four surgical prompt rules from
  the v19 per-field audit — renewal_terms EVERGREEN CLAUSES ("shall
  continue in full force and effect thereafter until terminated by N days'
  notice" — no "renew" word needed) + DEAL-TERMS TABLES; term_length
  DEFINED-TERM SENTENCES (carve-out of the no-definitions rule); governing
  law regulatory-jurisdiction sentences; termination_clauses REDACTED
  SECTIONS (heading + "[***]" marker). Same-scorer re-score (embedding
  off, both arms): **renewal_terms +4.5pp, termination_clauses +5.4pp** on
  target; official overall 0.9142 vs 0.9135 (tie) because ko −7.3pp was
  diffuse run variance (2 up vs 14 down, 34 flat — docs the rules never
  touch) + one parse-error row per arm. **Not adopted as champion** (v19
  holds ko 0.8840); next step v21 = v19 content + v20 field rules.
- **Scorer fixes (field_scoring.py, ADOPTED — all future runs)**: (1)
  blank-template/label-only expected dates ("_____ day of ________,
  19____", "Effective Date:") are null expectations — a null prediction
  scores 1.0 (3 of 5 v19 zero-date docs); (2) partial-GT party labels whose
  tokens appear verbatim in a predicted item are instantiated (role and
  pronoun labels: "Consultant", "Member", '"we," "us," or "our"' — 3 of 4
  v19 zero-parties docs; parties 0.918→1.000 on v20); (3) name fields score
  full token-containment → 1.0 (document_name 0.960→0.991 on v20).
  Historical records keep their stored scores; SCORING.md §3 documents the
  rules. Full record: `V16_PROPOSITION.md` §11.
- **Research memo `memos/contracts_specialist_v20.md`**: the field-fidelity
  iteration (scorer correctness fixes + field-rule validation), linked from
  the memos README and shipped on the site's memos tab.
- **`contracts_specialist_v19` — worked span examples + span discipline
  (flash-line ko champion)**: v18's residual (93/241 token-unmatched GT
  spans license-shaped, only 25/107 with naive "grants ... a license"
  phrasing) motivated WORKED SPAN EXAMPLES drawn verbatim from the misses
  (grants-and-assigns with territories, restriction-on-rights, options,
  end-user access grants; verified negatives: trademark-hygiene/product-
  marketing duties, sentence+fragment repeats). v18's 225 near-duplicate
  items motivated SPAN DISCIPLINE (one item per operative requirement +
  post-build dedupe). Run: qwen3.7-flash × **reasoning_effort=max**, same
  50 docs, seed 42, chunked, Langfuse llm-dojo — **ko 0.8535 → 0.8840
  (+3.0pp; +10.9pp vs v15), alignment precision 0.619 → 0.662, items −29%
  (1118→792), verified_precision 0.988**; gains concentrate in the target
  license docs (HPIL 0.5→1.0, NOVO 0.667→1.0, Fulucai 0.5→0.833).
  Caveats: 1/50 parse-error row (Ediets EX-10.4 — max reasoning overran
  the structured budget; ko ≈ 0.90 without it), prompt-vs-reasoning
  confound unresolved, cost 2.6x ($0.098). Full record: `V16_PROPOSITION.md`
  §10, `memos/contracts_specialist_v19.md`.
- **Research memo `memos/contracts_specialist_v19.md`**: dedicated memo for
  the worked-examples iteration (span examples beat prose shapes for the
  license family; reasoning-effort reliability trade), linked from the memos
  README and shipped on the site's memos tab.
- **v18 model sweep — scope-fidelity is model-agnostic, segmentation is
  model-bound**: v18 × {deepseek-v4-flash, deepseek-v4-pro} on the same
  50-doc surface (seed 42, chunked, Langfuse llm-dojo). Every model gains
  +6.0 to +11.5pp on key_obligations from v15 to v18; **deepseek-v4-pro ×
  v18 is the series champion — ko 0.7755 → 0.8907 (+11.5pp), overall 0.9289
  (series best), verified_precision 1.000 (zero hallucinations), alignment
  precision 0.685 (best)**, at an estimated $0.053 for the 50-doc surface.
  deepseek-v4-flash over-produces (1735 items, +56% over the GT sample;
  alignment precision 0.549) and lands ko 0.8358 (+6.0pp). The catalog
  fixed a prompt-layer scope defect, not a model quirk. Full table +
  interpretation in `memos/model_sweep_v18.md`; runs 047–048 in the
  experiment log.
- **`SCORING.md` §4/§8 — post-hoc scoring logic synthesized**: the
  per-row `entity_list_audit` artifact (`n_predicted`, `matched_gt`,
  `verified_in_doc`, `true_items`, `verified_precision`, `hallucinated`,
  `hallucination_rate`, `doc_verification`) is documented as the canonical
  post-hoc analysis record, with the derived post-hoc metrics (item count,
  matched GT spans, alignment precision = Σmatched/Σpredicted, verified
  precision) and the chunked-extraction scoring semantics (list union with
  normalized dedupe, scalar first-non-null, confidence max, failed-chunk
  skip). New §8 documents the sanctioned span-level miss-attribution
  chain: unmatched-span extraction → containment test → family
  decomposition → recovery check.
- **Research memo `memos/model_sweep_v18.md`**: the dedicated sweep memo
  (research question → answer + results tables → interpretation →
  remaining uncertainties) with same-surface identity and bootstrap-CI
  discipline, linked from the memos README and shipped on the site's
  memos tab.
- **Research memo on the v17→v18 contract-specialist findings**
  (`memos/contracts_specialist_v17_v18_enhancements.md`): documents the
  grain-vs-scope experiment — v16 fragment contract (+0.6pp ko, −2.7pp
  overall, over-fragmentation), v17 length anchor (627 matched spans,
  below v15), the refuted containment hypothesis (0/160 spans embedded),
  and the adopted v18 family-fidelity catalog (ko 0.7755→0.8535 +7.8pp,
  overall 0.9230, series best). Ships on the site's memos tab.
- **`contracts_specialist_v18` — family-fidelity catalog (ADOPTED)**: the
  terse 26-family list in `src/prompts.py` is replaced by a CUAD-category
  catalog (1:1 mirror of the 41-category catalog, 26 obligation families)
  with each category's operative clause shapes, derived from the 50-doc
  v15/v16/v17 decomposition of the 160 unmatched GT spans (cap-on-liability
  consequential-damages waivers, license grants phrased "right and
  license ... for the territory of", minimum guarantees/royalties, audit
  deficiency remedies, insurance coverage lists, IP-prosecution elections,
  family-term definitions). The exclusion rule narrows to true general
  duties with a WHERE-IT-SITS guard (family clauses inside
  indemnity/damages sections still count). v17's length-anchored grain is
  kept. A/B (same 50 docs, chunked, seed 42, Langfuse llm-dojo):
  **key_obligations 0.7755 → 0.8535 (+7.8pp)**, overall 0.9129 → **0.9230**
  (series best), parties/term_length tie v15, verified_precision 0.991.
  30/160 missed spans recovered at token level (cap liability +8, IP
  ownership +4, license +4); Penntex now extracts its labeled
  cap-on-liability clause (0 liability items in v15). Decision rule met
  (ko ≥ +3pp, no field regressed >2pp) — champion. Design + full table in
  `V16_PROPOSITION.md` §9.
- **Research memos + memos tab on the site**: `memos/*.md` archive the key
  findings from experimental runs and prompt iterations (research-question →
  answer + results summary → remaining uncertainties), shipped to the site
  under a new **memos** navigation tab (`build_site.py` emits
  `docs/data/memos.json`; the viewer renders the markdown subset with
  tables, inline formatting, and cross-memo links). Initial memos:
  subtype-classification improvements (sorter v3→v6) and entity-extraction
  improvements (specialist v2→v15 incl. the chunking enhancement).

### Fixed
- **Runs table sorts chronologically by default**: the `id` column (the
  chronological run number) fell through to a lexicographic string compare,
  so the default newest-first sort produced a garbled order ("9" before
  "43", newest runs buried mid-table). `id` now sorts numerically in every
  view's runs table; the default remains id desc (newest first), and the
  header click toggles numeric asc/desc correctly.
- **Stylized graph favicon for the site**: the GH Pages favicon is now a
  directed-graph motif (four nodes on the site's accent gradient with a
  highlighted vertex) replacing the placeholder "E" — matching the
  experiment-log/LangGraph identity. Also adds a Safari `mask-icon`.
- **Benchmarks view showed "OPENROUTER_API_KEY not set" despite a configured
  key**: `build_site.py` never loaded the repo's credential files
  (`braintrust.env` / `.env`), so the benchmarks fetch silently reported
  unavailable. It now calls `src.env_utils.load_env()` like the eval runners
  — rebuilt with the configured key, the site ships **1387 live benchmark
  rows** (133 Artificial Analysis + 1021 Design Arena, as-of 2026-08-12) in
  `docs/data/benchmarks.json`. Pricing rendering handles both `$X/1M`
  strings and per-token decimals (`$X/token`).

### Added
- **Real-browser audit of the GH Pages site** (`tests/test_browser_audit.py`
  + `tests/assets/browser_audit.mjs`, skipped without Chrome/node): serves
  docs/ and drives headless Chrome via the DevTools Protocol over every
  route, asserting zero console errors/exceptions, no layout overflow, and
  that each view renders — catching silent errors, visual breakage, and
  uncaught issues the stubbed-DOM audit cannot see.
- **OpenRouter benchmarks on the experiment-log site**: a dedicated
  `#/benchmarks` navigation tab rendering Artificial Analysis
  (intelligence/coding/agentic index rankings with per-model pricing) and
  Design Arena (ELO, win-rate, avg generation time, tournament stats) —
  fetched best-effort at build time (`build_site.py --benchmarks-key` or
  `$OPENROUTER_API_KEY`) into `docs/data/benchmarks.json`, with citation
  metadata preserved and the "benchmarks are evidence, not proof of
  availability" caveat surfaced in the view. Unavailable builds render a
  rebuild hint instead of failing; the headless render audit covers the view.
- **Issue & PR templates (YAML forms)**: `.github/ISSUE_TEMPLATE/`
  (`bug_report`, `feature_request`, `experiment_report`, `config.yml`) and
  `.github/PULL_REQUEST_TEMPLATE/pull_request.yml` enforcing this repo's
  discipline — same-surface identity on every bug/experiment report, the
  changelog-in-the-same-commit rule, derived-artifact regeneration, the
  render audit, and the `release.py --check` gate.
- **LangChain + LangGraph skills installed for all agents** (from
  github.com/langchain-ai/langchain-skills): `langchain-fundamentals`,
  `langchain-python-quickstart`, `langchain-dependencies`,
  `langchain-middleware`, `langchain-rag`, `langgraph-fundamentals`,
  `langgraph-python-quickstart`, `langgraph-cli`, `langgraph-persistence`,
  `langgraph-human-in-the-loop`, `ecosystem-primer`, and `eval-engineering`
  — project skills covering the full agent/graph stack the repo builds on
  and evaluates. AGENTS.md documents the skill set.
- **Langfuse skill installed for all agents**: `.opencode/skills/langfuse/`
  (SKILL.md + 11 reference files, from github.com/langfuse/skills) — a
  project skill, available to every agent in this repo, granting langfuse-cli
  API access + docs retrieval when loaded. AGENTS.md documents it.
- **Complete documentation pass**: per-directory READMEs added where missing —
  `src/README.md` (core modules incl. `bootstrap.py`/`cost_models.py`),
  `agents/README.md` (agent roster), `config/README.md` (taxonomy.yaml),
  `scripts/README.md` (ops/evals/reporting/site/releases), `tests/README.md`
  (conventions + render audit), `reports/README.md` (the experiment log) —
  and the root `README.md` layout + Website sections updated to reference
  them. AGENTS.md gained a "Docs & READMEs" convention.
- **Public GitHub wiki fully expanded** (`wiki/`, pushed by
  `./wiki/sync-wiki.sh` to https://github.com/Exios66/llm-entity-extraction/wiki):
  Home, Getting-Started, Architecture, Eval-Runners, Experiment-Log, Scoring
  (expanded from the previous Experiment-Scoring-Breakdown), Site, Release-
  Process, Taxonomy, FAQ, plus _Sidebar/_Footer — covering setup, every eval
  runner, the JSONL/md/site pipeline, all metrics (bootstrap CIs, judge
  calibration, ablation, cost scoring), the visualization site, and the
  release workflow.
- **Release automation (`scripts/release.py`)**: `--bump <patch|minor|major>
  --note "<summary>"` converts the accumulated `[Unreleased]` entries into
  `## [vX.Y.Z] - <date>` (keeping the empty placeholder), bumps
  `pyproject.toml` in lockstep, and prints the exact commit/tag/GH-Pages-push/
  llm-mailroom-sync commands; `--check` validates version == changelog
  header, site-data freshness (`build_site.py --check`), the full suite, and
  the headless render audit; `--dry-run` previews without writing; refuses on
  a dirty tree.
- **AGENTS.md release workflow codified**: changelog entries land in the SAME
  commit as every behavior-changing change ([Unreleased] discipline), docs
  (README/docs/SCORING/AGENTS) are updated when the change touches them,
  pyproject.toml must equal the changelog header, tags must match the header
  exactly, and the post-run GH Pages sync (render → build_site → audit →
  push) plus the llm-mailroom mirror sync are the expected pipeline.


## [v0.14.0] - 2026-08-11

### Added
- **Bootstrap confidence intervals (GitHub issue #1)**: `src/bootstrap.py` —
  percentile-bootstrap 95% CIs over per-document scores (`bootstrap_ci`) and
  two-sample bootstrap delta tests with significance verdicts
  (`delta_significance`, min-detectable-effect guard for A/Bs). Wired into
  all four eval runners as `scores.*_ci` (`overall_extraction_score_ci`,
  `subtype_accuracy_ci`, `exact_match_ci`, …) in every experiment record;
  `evaluate_prompt_version.py` prints the delta CI + significance for A/Bs.
  Older records get CIs too — the site resamples the per-doc arrays already
  stored in `results[]`, then falls back to Wilson (`_record_ci`).
- **Chained error-propagation ablation (`--handoff-scope ground_truth`)**:
  the specialist now ALSO extracts the same docs with the ground-truth-subtype
  handoff; `scores.ablation` records predicted-vs-GT handoff scores and the
  sorter routing loss (pp) — chained loss is split into sorter error vs
  specialist error instead of being attributed "mostly by inference" (both
  chained runners).
- **Judge-calibration tracker**: extraction `--judge` rows are persisted to
  `data/judgments/<experiment>.jsonl` (`kind: calibration` with the
  deterministic score + judge labels) and aggregated into
  `scores.judge_calibration` — agree rate vs the deterministic scorer plus a
  lenient/strict lean signal (strong ≥ 0.85 / weak ≤ 0.5 bands).
- **Cross-model matrix runner (`scripts/eval/run_model_matrix.py`)**: runs a
  fixed sample (same dataset/seed/size — one surface) across a model x prompt
  grid using the existing runners and prints a score (+bootstrap CI) x cost
  matrix.
- **Cost scoring for every run**: OpenRouter usage payloads carry no cost
  field, so every run previously recorded `cost_total_usd = 0.0` despite
  ~30M real tokens. `src/cost_models.py` scores cost deterministically from
  the recorded prompt/completion token counts x verified per-model prices
  (qwen $0.03/$0.13 per 1M, deepseek-v4-flash $0.05/$0.25, deepseek-v4-pro
  $0.435/$0.87; unknown models resolve by prefix or honestly report None).
  `tokens_summary()` now takes `model=` and stamps `cost_estimated_usd` on
  every future record; a documented one-time backfill
  (`scripts/backfill_cost_estimates.py`, append-only-log exception) scored
  all 38 historical records / 81 token buckets (est. $2.28 total). The site
  shows billed (OpenRouter CSV) when covered and the estimate otherwise —
  runs table, run detail (with price source), cost-vs-quality scatter, and
  trends.
- **Site — same-surface guardrail**: every index row carries
  `fingerprint`/`seed`/`sample_key`; `delta_best_pp` is computed only against
  the best run on the SAME surface (dataset fingerprint + seed + sample
  size), and the frontend refuses to color deltas across different surfaces
  — the v0.13.0 "regression" class of misread is now structurally
  impossible.
- **Site — trends, scatter, stacked bars, prompt diff**: `docs/data/trends.json`
  (per-task series with headline/cost/sample-key/failure-mode counts) and
  `docs/data/prompts.json` (full prompt text per version); the task view
  renders an SVG score-trend chart per prompt version, a cost-vs-quality
  scatter, and (subtype) failure-mode stacked bars; a `#/prompts` prompt-diff
  view shows a side-by-side line diff between two versions with their score
  delta.
- **Headless render audit for the site**: `tests/assets/site_render_audit.js`
  + `tests/test_site_render.py` exercise EVERY view (index, all task/prompt/
  model groups, all 38 runs, 114 document traces, prompt diff) against the
  real built data with a stubbed DOM and assert zero rendering errors
  (skipped when node is absent).
- `sorter_classification` gained a headline handler (exact_match + per-class
  detail), so its runs chart like every other task.

### Changed
- **Charts are legible, inspectable, and navigable**: the cost-vs-quality
  scatter uses a **log-scale x axis** (runs span ~4 orders of magnitude; the
  linear axis piled every point on the y axis) with $ grid ticks and filled
  (billed) vs hollow (estimated) points; trend lines are **smoothed**
  (Catmull-Rom splines) with raw points on top, from a **curated palette
  with dash patterns**; hovering a series dims the others. Every chart point
  is **hover-inspectable** (tooltip panel: experiment name, run id, model,
  prompt, headline, cost, n rows, sample key, timestamp) and **click-
  navigates to the coordinated run**; failure-mode stack rows are clickable
  too.
- **Navigation grouped**: task links live under a single **"tasks" dropdown**
  populated from `meta.tasks` (hardcoded per-task links removed — the nav no
  longer repeats task names twice): runs | tasks ▾ | prompt diff | repo |
  theme.
- **Site polish**: dynamic nav + confusion matrices sorted by expected-class
  frequency (Σ totals, per-class accuracy, cell tooltips); index gains a
  "Total cost (est.)" stat card; focus-visible outlines and
  `prefers-reduced-motion` support.

### Fixed
- **Chart tooltip overflow**: tooltip rows now wrap long unbroken strings
  (trace IDs, experiment names, sample keys) — nothing spills out of the box.
- **Chart panel + gridlines were invisible**: chart/nav/tooltip CSS
  referenced undefined vars (`--panel`/`--line`/`--ink`/`--gold`) — defined
  as theme-aware aliases in `:root`; charts now render on a panel surface
  with visible gridlines in both themes.
- **Hollow (estimated-cost) scatter points were invisible**: a global
  `.dot{stroke:var(--bg)}` rule overrode the per-point color presentation
  attribute — removed; hollow points render with their colored ring (crisp
  at any scale via `vector-effect: non-scaling-stroke`).
- **Tasks dropdown was transparent** (undefined `--panel` background) — now a
  proper surface that right-aligns to the viewport on mobile.
- Long kv labels (ablation/judge-calibration cards) no longer force table
  overflow.

## [v0.13.0] - 2026-08-11

### Fixed
- **Chained extraction "regression" diagnosed and disproven** — the apparent
  drop (0.906 → 0.85) was a measurement artifact: the historical chained runs
  evaluated on `mailroom-cuad-contracts` (50 docs) while the new runs use
  `mailroom-cuad-contracts-full` (509 docs), whose seed-42 5-doc samples are
  DISJOINT (0 overlapping documents). On the controlled same-surface A/B
  (Langfuse-audited, identical docs), sorter_v6 + specialist_v11 chained
  scores **0.946 vs the historical v11 0.906** — the newest pipeline is the
  best measured; the subtype handoff adds +4pp overall / +19pp category
  presence vs `--handoff-scope none`. Extraction score is dominated by the
  specialist's per-field accuracy, not the sorter's routing (sorter is
  subtype-perfect on the sample; verified_precision 1.0 — zero hallucinations
  in every chained run). The only true within-surface regressions were
  specialist v7/v8 (0.696-0.699 vs 0.89-0.92), recovered by v10/v11.
- **Date scorer containment + partial credit** (`score_date_field`) — CUAD
  maps BOTH "Agreement Date" and "Effective Date" onto `effective_date`;
  strict date equality scored legitimate multi-date documents 0.00 (NETGEAR
  GT `November 5, 1996` vs predicted `1996-03-01`; MOELIS GT `December 27,
  2011` vs `2012-01-01`). New tiers: label-date phrase contained in the
  prediction (or vice versa) → 1.0; shared year+month → 0.67; within a
  45-day cluster (execution vs defined effective date) → 0.67; year-only →
  0.33. A bare year never earns full credit. Documented in SCORING.md.
- **Contracts specialist v12** (`src/prompts.py`, derived from v11) —
  effective-date rule (the agreement's defined term wins, full date phrase);
  governing-law quoted VERBATIM in full (containment fix for the 0.39
  fragment scores); RE-SCAN DUTY for the families the 5-doc sample missed
  (volume restrictions, caps on liability, uncapped liability, audit rights,
  third-party beneficiary, change of control, anti-assignment); truncation
  honesty (scan both sides of the marker, never fabricate the omitted
  middle).
- **Truncation auditability** — chained/extraction composites and Langfuse
  `contracts_specialist` spans now carry the `truncated` flag
  (`specialist._last_truncated`); chained/extraction `--max-input-chars`
  default raised 100k → **150k** (fully covers Antares 106.8k and MOELIS
  122.1k; Phasebio 292k remains head+tail by design).
- **Measured on the identical full-corpus 5-doc sample** (Langfuse, seed 42):
  chained overall 0.8666 (v11) → **0.8882 (v12)** with category presence
  held at 0.777, field presence 1.0, verified_precision 1.0; MOELIS 0.823 →
  0.907, NETGEAR 0.792 → 0.828 (dates 0.00 → 0.67/0.33). Test count 223.

## [v0.12.0] - 2026-08-11

### Added
- **Full-corpus sorter baseline** — `qwen3.7-flash_sorter_v5_subtype`: the
  complete 509-contract CUAD run (sorter_v5, reasoning `medium`): doc_type
  exact_match 0.9843, strict subtype 0.8585, family-level equiv 0.8743, mean
  confidence 0.9404; 72 misses classified by failure mode (40 family
  confusion / 16 other-fallback / 8 function-over-form / 8 equivalent-family).
- **Sorter v6** (`src/prompts.py`) — surgical derivation of v5 (base string
  untouched, registered in `PROMPT_VERSIONS`) with data-backed rules for the
  509-run's miss clusters: rule 12 SEC Joint Filing Agreements →
  joint_venture (13/72 misses); rule 13 maintenance preference (license+
  maintenance hybrids + financial-sense maintenance, 17/72); rule 14 hosting
  is not license/development (8/72); rule 15 remarketing → marketing; rule 16
  marketing-core guard; rule 17 annex inheritance; plus the rule-10
  refinement (development preference does not override an operating core —
  manufacturing/marketing/hosting).
- **Same-sample 195-doc A/B** (`--stratified 200 --seed 42`, the documented
  baseline sample): sorter_v6 0.9385 strict vs v5 0.8410 (**+9.75pp**),
  equiv 0.9436 vs 0.8667, exact_match 1.0, failures 31→12 — vs the
  historical v3-medium 0.8359 / v4 0.8103 baselines on the same sample.
- **Langfuse mirror environment** — dedicated project
  (`llm-mailroom-experiments`, keys in gitignored `langfuse.env`), every
  trace tagged with `LANGFUSE_ENVIRONMENT`, session-scoped deterministic
  trace ids (`sha256(session|filename)`) so re-runs of the SAME experiment
  update traces in place while different experiments never merge.
- **Per-agent designated tasks on Langfuse** — `LangfuseTracer.agent_observation`
  opens one nested span per pipeline agent (sorter / contracts_specialist)
  with its own LangChain generation and its designated task scores attached
  to the agent's OWN observation: sorter (exact_match, subtype_accuracy,
  confidence) and contracts_specialist (overall_extraction_score,
  field_presence, overall_verified_precision, category_presence,
  schema_valid) — per-agent performance metrics derivable over time.
- **Langfuse mirror runners** — `run_langfuse_subtype_eval.py` (existing),
  `run_langfuse_chained_eval.py`, `run_langfuse_extraction_eval.py`,
  `run_langfuse_classification_eval.py` (text): same data/tasks/scorers/
  manifest/experiment-log as their Braintrust counterparts, zero scored-run
  quota (deterministic NUMERIC scores per trace). Braintrust loggers gained
  additive `tracing_backend`/`tracing_meta` record fields.
- **Subtype-scoped chained handoff** — `build_subtype_handoff(subtype)` in
  `src/cuad_ground_truth.py` (SUBTYPE_CUAD_FOLDERS reverse-mapping + the CUAD
  per-type category tables): with the new `--handoff-scope subtype` default
  the specialist is cued with the PREDICTED subtype's expected field groups
  and never-applicable clause categories. 5-doc chained A/B (sorter_v6 +
  specialist_v11, seed 42): overall 0.8666 vs 0.8497 (+1.7pp), category
  presence 0.7773 vs 0.7106 (+6.7pp). `--handoff-scope none` reproduces the
  legacy handoff.
- **GH Pages site** (`docs/`) — static, dependency-free viewer over the
  experiment log (`index.html` + `site.css`/`site.js` + generated
  `docs/data/`); `scripts/site/build_site.py` regenerates the data
  (`--check` verifies currency). Pages source fixed to `main → /docs`.

### Changed
- `agents/base_agent.py` accepts optional LangChain `callbacks` (Langfuse
  handler threading; Braintrust path unchanged); `ContractsSpecialist` and
  `SorterAgent` forward them.
- `requirements.txt`: +`langchain>=1.0`, +`langfuse>=3.0`.
- README/AGENTS.md document the Langfuse mirror workflow, per-agent task
  matrix, and handoff scope flag; test count 220.

## [v0.11.0] - 2026-08-10

### Added
- **Sorter-only subtype evaluation** (`scripts/eval/run_subtype_eval.py`) — one
  sorter call per PDF; strict + family-level (`subtype_accuracy_equiv`)
  scoring, per-subtype accuracy, confusion matrix, resumable manifest,
  `--stratified N` for even, class-representative sampling (200-doc run over
  the full 510-contract corpus: 8 docs per subtype × 25).
- **Subtype equivalence scoring** — `SUBTYPE_EQUIVALENCES` +
  `equivalent_subtypes()`: reseller↔distributor, maintenance↔license,
  development↔license, affiliate↔joint_venture count as correct routing
  (strict accuracy stays the discriminating tracker).
- **Sorter medium reasoning** — `SorterAgent` defaults to
  `reasoning_effort="medium"` (verified: 95→483 completion tokens vs `none` +
  4.6pp strict on the same 195-doc stratified sample); the eval runners
  expose `--reasoning-effort` / `--sorter-reasoning-effort` and stamp it in
  Braintrust experiment metadata.
- **Sorter prompts v4/v5** — the option list is now the COMPLETE, precise set
  of valid keys (25 families + `other`, matching the schema enum exactly —
  enforced by a wiring test over every CUAD folder); v5's `other`-guard fixes
  v4's over-caution (title-obvious contracts → `other` regressions).
- **Chained eval subtype-focus** — the chained runner now calls
  `classify_json(..., subtype_focus=True)`: the sorter is explicitly tasked
  with sorting each document into its contract subtype (all chained rows are
  contracts), so its scores measure the subtype task, not a doc-type gate.
- **Contracts specialist v10/v11** — data-scoped extraction from the full
  510-doc corpus: the GT `key_obligations` spans are exactly the CUAD
  restriction/covenant families (mean 7.4, max 22 items). v10 scoped
  `key_obligations` to those families (overproduction 21-58 → 2-6 items);
  v11 adds section-by-section family exhaustiveness — measured best overall
  (chained 5-doc sample: 0.906, obligations 2-12, `verified_precision` 1.0).
- **Post-hoc judge reviews** (`scripts/reporting/judge_experiment.py`) — the
  offline JudgeAgent audits every failed classification against the source
  document; judgments append to `data/judgments/<experiment>.jsonl` and the
  markdown log renders a **Judge agent review** section (judgment counts +
  per-row verdicts with the judge's reasoning). 31 judgments logged on the
  v4 195-doc run.
- **Failure-insights logging** — the subtype runner now stores full reasoning
  (4000 chars) on failed rows + per-row `failure_mode`
  (`function_over_form` / `other_fallback` / `equivalent_family` /
  `family_confusion`) + `scores.sorter.failure_insights`, rendered as a
  failed-classification insights section in the markdown log.
- **Backfill script** (`scripts/reporting/backfill_subtype_reasoning.py`) —
  one-time enrichment of the 5 historical subtype records: failure modes
  derived and full reasoning recovered from the Braintrust LLM spans
  (documented append-only exception; the v4 record's 139 manifest-cached rows
  have no spans and keep their 500-char excerpts).
- **Packaging** — `pyproject.toml` + `config/__init__.py`: `pip install -e .`
  exposes `agents`/`src`/`config` (taxonomy.yaml included) so the LangChain
  agents import and run inside the llm-mailroom LangGraph architecture;
  verified by an out-of-repo import test.
- **Judge agent test suite** (`tests/test_judge_agent.py`, 14 tests) — the
  evaluator's steps, choices, reasoning passthrough, and scoring fallbacks
  for all three dimensions.
- **Head + tail truncation window** (`BaseAgent.truncate_input`),
  `contracts_specialist_v9` (scan both sides of the marker), `--text-only`
  CUAD streamer mode, and wiring/option-list/renderer tests. Test count 194.

### Changed
- Chained eval: sorter reasoning flag wired through; sorter explicitly tasked
  with subtype sorting; `--max-tokens` default 32768.
- 200-doc stratified A/B (same 195 docs, seed 42): v3-none 0.7897 →
  v3-medium 0.8359 strict (+4.6pp — medium reasoning helps); v4 0.8103
  (option-list precision, over-cautious); the earlier "regression" vs the
  50-doc run (0.84/0.94) was sample composition (50-run: 5/8
  equivalence-recoverable misses; 200-run: 4/32), not the enhancements.
- AGENTS.md rewritten with the full experimental workflow, run→log→release
  lifecycle, configurations (reasoning, truncation, equivalence), and
  release-process steps; README documents packaging, the subtype eval, judge
  reviews, and the new prompt versions.

## [v0.10.0] - 2026-08-09

### Added
- `scripts/datasets/download_cuad_pdfs.py` — download the FULL CUAD v1 corpus
  (all 510 contract PDFs + `CUAD_v1.json` clause QA annotations) into a local
  subdirectory (`data/cuad_pdfs/` default), preserving the CUAD folder
  structure so `category_of()` still works locally. Resumable (existing
  non-empty files are skipped), `--limit`, `--category`, `--out-dir`,
  `--skip-json`, `--overwrite`, `--dry-run`. Complements the streaming
  `stream_cuad_to_bt.py`: keeps the PDFs on disk for `--pdf-dir` evals.
- `.venv` setup with `sentence-transformers` (torch-backed) — the semantic
  embedding rescue now runs the LOCAL `all-MiniLM-L6-v2` model (free, fast,
  offline, reproducible) with the OpenRouter `text-embedding-3-small`
  fallback verified working end-to-end when the local model is unavailable.
- **Sorter prompt v3** (`sorter_v3`) — hybrid-agreement development
  preference: when one named family is development AND development machinery
  is present (development plan, milestones, joint R&D committee, development
  funding), development wins over the commercial family (matches the CUAD
  corpus filing convention), and two-family hybrids are capped at 0.85
  confidence with the runner-up named. Fixes the last sorter subtype error:
  "Distribution and Development Agreement" → development (was distributor).
- **Contracts specialist prompts v6–v8** (`contracts_specialist_v6/v7/v8`) —
  v6 added the term-length definition guard (never answer with a defined
  term's definition — extract the agreement's own Term clause), per-clause
  key_obligations granularity, and truncated-tail governing-law scanning.
  Chained A/B showed v6's granularity rule fragmented single clauses into
  per-subsection micro-items (eDiets key_obligations 0.92 → 0.69, lost the
  "Minimum Commitment" GT span); v7's clause-complete counter-fix blew the
  16k-token output budget on a 122k-char agreement (JSON truncated, row
  scored 0.0). **v8 is the empirically validated synthesis**: v5's
  sentence-level granularity restored verbatim, keeping ONLY the two v6 rules
  that survived (term-length definition guard + truncated-tail governing
  law).
- `run_chained_eval.py` default `--max-tokens` raised 16384 → 32768 — full
  verbatim extraction of 50+ clauses on long agreements exceeds 16k tokens,
  which truncated the JSON and zeroed rows.

### Changed
- **Embedding rescue guard** (`src/field_scoring.py`, `_with_embedding_rescue`):
  empty/whitespace predictions or labels are never rescued by embeddings — a
  blank answer stays a miss. Previously an empty prediction could be inflated
  to ~0.45 by cosine similarity to any text once a real embedder was
  available; the bug only surfaced when the local sentence-transformers route
  became active (the OpenRouter fallback silently failed under the fake test
  key). Test suite still fully network-free, 183 tests passing.
- **Chained eval post-mortem (v2+v5 vs v3+v8, same 5-doc sample, seed 42)**:
  sorter subtype accuracy 0.8 → **1.0** (the Ritter hybrid fix, confidence
  correctly capped at 0.85); extractor overall 0.9165 → 0.8933, with the
  entire delta coming from the Phasebio 292k-char agreement whose ground-truth
  governing law (char 276k), term clause (char 196k), cap-on-liability
  (char 283k), and non-compete (char 109k) all sit beyond the 100k input cap —
  a pipeline truncation limit, not a prompt failure (all extractions remain
  100% verified, zero hallucinations). eDiets key_obligations varies 0.69–0.92
  run-to-run on identical prompt semantics (51 items, ±2 GT-span matches) —
  stochastic, not prompt-driven.
- `README.md` — setup documents the `.venv` + optional `sentence-transformers`
  install and both embedding routes; the corpus-sync section documents
  `download_cuad_pdfs.py`; layout adds the new streamer; prompt table lists
  `sorter_v3` and `contracts_specialist_v6/v7/v8`; test count fixed to 183 in
  the layout tree.

## [v0.9.0] - 2026-08-09

### Added
- `CHANGELOG.md` — full semantic version history (this file).
- `SCORING.md` — a complete scoring & metrics reference: every scorer, every
  metric, every formula (classification, binary, multiclass, field-type-aware
  content scoring, factuality audit, chained stage trackers, A/B deltas).
- Version tags `v0.1.0` … `v0.8.0` on every prior milestone commit, plus this
  release's `v0.9.0`.

### Changed
- `README.md` links `SCORING.md` and `CHANGELOG.md` from the docs section and
  updates the test count to 183.
- `AGENTS.md` points to `SCORING.md` as the canonical scorer documentation and
  updates the test count to 183.
- `reports/extraction_v2.md` and `reports/experiment_log.md` regenerated to
  match the current code state (no stale artifacts).

## [v0.8.0] - 2026-08-09

### Added
- `AGENTS.md` — comprehensive working guide for AI agents and contributors:
  setup, command cheatsheet, architecture & data flow, module map, scoring
  model rules, experiment-log mechanics, code conventions, testing rules,
  gotchas, useful one-liners.
- Three new unit tests in `tests/test_experiment_log.py` verifying the
  markdown renderer: score tables + per-field matrices, expected-vs-predicted
  confusion matrices, and `render_full_log` index/sections. Test count 183.

## [v0.7.0] - 2026-08-09

### Added
- `scripts/reporting/render_experiment_log.py` — CLI that rebuilds the whole
  human-readable experiment log from the append-only JSONL source of truth
  (title, experiment index table, one fully expanded section per run;
  `--dry-run` prints instead of writing).
- Rich markdown rendering in `src/experiment_log.py` (`experiment_markdown`,
  `render_full_log`): every section rendered as tables — run metadata, data
  source, parameters, per-stage token usage, scores + per-field breakdowns,
  per-document results, document × field scoring matrices with mean column,
  entity-list F1 matrices, aggregated factuality audit, CUAD category
  presence, expected × predicted confusion matrices (classification and sorter
  contract-subtype), sorter outputs, and the model's raw predicted
  extractions per document. No more raw JSON dumps.
- Extraction eval now persists the specialist's raw `predicted` extraction in
  the experiment log (`scripts/eval/run_extraction_eval.py`), so logged
  records carry outputs, not just scores.

### Changed
- `README.md` fully rewritten to match the repository's current state.
- `reports/experiment_log.md` regenerated with the new renderer.

## [v0.6.0] - 2026-08-09

### Added
- **CUAD type-aware ground truth** (`src/cuad_ground_truth.py`): the full
  41-category CUAD v1 catalog (9 string-answer, 32 YES/NO), grouped into
  clause families; expected fields derived per contract TYPE (CUAD folder) via
  `build_expected_fields` / `build_presence_expectations` — a document's
  expectations only cover categories applicable to its type
  (`ground_truth_mode: cuad_type_aware`).
- **Factuality guard** in `src/field_scoring.py`: every predicted list item
  must match a ground-truth label OR be grounded in the source document
  (token coverage ≥ 0.7; dates grounded via date-candidate parsing in any
  format); ungrounded items are hallucinations driving `verified_precision`
  down / `hallucination_rate` up. Scalar fields audited too.
- **CUAD category presence scoring** (`score_category_presence`): binary
  YES/NO conformance per presence-type category, with per-category detail.
- `scripts/eval/run_chained_eval.py` — end-to-end pipeline eval: sorter
  (doc_type + contract subtype) → contracts specialist, per-stage token
  usage and scores, subtype confusion matrix, resumable manifest.
- Specialist prompts v3–v5 (`contracts_specialist_v3/v4/v5`) and sorter
  prompt v2; chained smoke tests; expanded field-scoring, ground-truth, and
  sorter tests. Test count 180.
- `partial_gt_fields` (ground-truth coverage instead of F1) and
  `containment_fields` (expected-within-predicted containment) scoring modes
  in the taxonomy-driven scorer.

### Changed
- Extraction eval registers the factuality and category-presence trackers
  (`overall_verified_precision`, `category_presence`) in the default tracker
  set; per-row logs include the entity-list audit and presence detail.
- `score_extraction_manifest.py` post-hoc report extended with category
  presence, factuality audit, and per-document scoring matrices.
- First experiment records appended to `reports/experiment_log.jsonl` / `.md`
  (7 runs: specialist v2–v3 extraction, type-aware v3 runs, chained v1+v4 /
  v2+v5).

## [v0.5.0] - 2026-08-09

### Added
- **Repository experiment log** (`src/experiment_log.py`): every eval run
  appends ONE JSON record to `reports/experiment_log.jsonl` (append-only) plus
  a human-readable section to `reports/experiment_log.md` — git snapshot,
  model, prompt version, data source + fingerprint, all run parameters, token
  usage/cost, all scores, per-row results. Paths overridable via
  `EXPERIMENT_LOG_PATH` / `EXPERIMENT_LOG_MD_PATH` / `--experiment-log`.
- Logging wired into `run_classification_eval.py` and `run_extraction_eval.py`
  (each arm of `evaluate_prompt_version.py` included).
- `tests/test_experiment_log.py` (append-only semantics, token aggregation,
  markdown sections, env-overridable paths, git snapshot).

## [v0.4.0] - 2026-08-09

### Added
- **Composite-output extraction scoring** in `run_extraction_eval.py`: the
  task computes every score locally (deterministic field-type-aware content
  scoring) and returns a composite; registered Braintrust scorers
  (`overall_extraction_score`, `field_presence`, `schema_valid`) are trivial
  lookups on it — nothing recomputed on the Braintrust side, so UI, manifest,
  and log always agree.
- **Embedding rescue**: `name`/`free_text` fields and list elements consult
  sentence-transformers cosine similarity (OpenRouter embeddings fallback)
  when the string score is ambiguous (< 0.7), never overriding a confident
  string-level match.
- `--bt-scores none|overall|full` (with per-field + entity-list F1 trackers),
  `--judge` ambiguous-band LLM pass, and post-hoc offline reporting via
  `score_extraction_manifest.py` (`reports/extraction_v2.md`).
- Extraction smoke tests updated for the composite contract.

## [v0.3.0] - 2026-08-09

### Added
- **Vision classification pipeline**: `stream_cuad_to_bt.py` renders every
  page of the 510 real CUAD contract PDFs to 1024×1024 grayscale PNGs and
  uploads them as image attachments (one row per PDF, all pages); the sorter
  classifies the complete page set in a single vision call
  (`sorter_vision_v0`, `--input-mode vision`, `--vision-pages all/first`,
  confidence-weighted page voting for local PDFs via `--pdf-dir`).
- **LegalBench dataset streamers**: `stream_legalbench_to_bt.py` (MAUD v1:
  139 full-text merger agreements + the 13,256-row per-question
  classification suite with embedded answer spaces) and
  `stream_legalbench_tasks_to_bt.py` (60+ classification tasks —
  `cuad_*`, `maud_*`, hearsay, etc. — one Braintrust dataset per task with
  `metadata.valid_classes`).
- **Task-mode classification**: `--prompt-mode task` with the
  `legalbench_task_v0` prompt answers LegalBench multi-class tasks against
  `--valid-classes`.
- **Field-type-aware content scorer** (`src/field_scoring.py`, first pass):
  `id`/`date`/`money`/`name`/`free_text`/`entity_list` (bipartite matching)
  with the taxonomy-driven `field_types` mapping and heuristic fallback.
- **CUAD ground truth mapping** (`src/cuad_ground_truth.py`, first pass) and
  the extraction eval runner (`run_extraction_eval.py`, initial).
- Vision + extraction smoke tests, streamer tests, field-scoring tests,
  page-voting tests, post-hoc scorer tests. Test count 144.

## [v0.2.0] - 2026-08-09

### Added
- **LangChain agents** (`agents/`): `BaseAgent` (ChatOpenAI on OpenRouter,
  structured JSON output, vision calls, `_last_usage` token capture),
  `SorterAgent` (text + image classification), per-doc-class specialists with
  shared schemas (`specialist_agents.py`), and the offline `JudgeAgent`
  (classification/completeness/correctness).
- **Versioned prompt registry** (`src/prompts.py`): `PROMPT_VERSIONS` with
  `get_prompt` / `list_prompts`; initial versions for the sorter,
  specialists, boss/reporter, judges, and PDF transcriber.
- **Eval runners**: `run_classification_eval.py` (one prompt per experiment,
  text mode, exact_match/failure/cost scorers, resumable manifests),
  `run_binary_class_eval.py` (precision/recall/F1 on a binary question),
  `run_multiclass_eval.py` (per-class + macro accuracy), and
  `evaluate_prompt_version.py` (A/B with delta summary and `--compare-only`).
- **Dataset streamers** (initial): `stream_cuad_to_bt.py` (CUAD v1) and
  `stream_legalbench_to_bt.py` (MAUD v1) uploading full-text rows.
- **Reporting**: `report_generator.py` (markdown experiment report with
  per-class accuracy, confusion matrix, misclassification ledger) and
  `confusion_matrix.py` (PNG heatmap + CSV from a Braintrust experiment).
- `config/taxonomy.yaml` (doc classes, field types, agent→model mapping,
  confidence thresholds, cost models), `src/braintrust_config.py`,
  `src/braintrust_utils.py`, `src/env_utils.py`, `src/evaluation.py`
  (fingerprints + `ManifestStore`), `src/classifier.py`, `src/image_utils.py`,
  `src/llm_chain.py`, `src/openrouter_utils.py`.
- `.env.example` / `braintrust.env.example`, `.gitignore`, `requirements.txt`,
  first test suite (79 tests).

## [v0.1.0] - 2026-08-09

### Added
- Repository bootstrap: `.gitattributes`, initial `README.md` scaffold.

[Unreleased]: https://github.com/Exios66/llm-entity-extraction/compare
[v0.20.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.20.0
[v0.19.1]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.19.1
[v0.19.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.19.0
[v0.18.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.18.0
[v0.17.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.17.0
[v0.16.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.16.0
[v0.15.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.15.0
[v0.14.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.14.0
[v0.13.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.13.0
[v0.12.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.12.0
[v0.11.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.11.0
[v0.10.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.10.0
[v0.9.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.9.0
[v0.8.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.8.0
[v0.7.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.7.0
[v0.6.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.6.0
[v0.5.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.5.0
[v0.4.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.4.0
[v0.3.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.3.0
[v0.2.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.2.0
[v0.1.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.1.0

[v0.21.0]: https://github.com/Exios66/llm-entity-extraction/releases/tag/v0.21.0
