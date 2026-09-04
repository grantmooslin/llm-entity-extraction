# Scoring & Metrics Reference

Every metric this repo reports, where it is computed, and how to read it.
Scoring is deliberately **deterministic** — the run scorers are trivial
lookups on locally computed composites, so the trace UI (Langfuse / Phoenix),
the run manifests, and `reports/experiment_log.jsonl` never disagree.

## 0. Where the scoring lives — the `llm-dojo-scoring` package

The scoring definitions are **outsourced to the `llm-dojo-scoring` package**
(KANBAN-044 / KANBAN-047, pinned `@v0.10.0` in `pyproject.toml` +
`requirements.txt`), the **single source shared with llm-mailroom**. The local
`src/` modules are thin re-export shims so every import site (eval runners,
reporting scripts, tests, and llm-mailroom's `pip install -e .` imports) keeps
working unchanged:

| Local shim | Package source |
|---|---|
| `src/field_scoring.py` | `llm_dojo_scoring.field_scoring` (keeps the one-arg `get_field_types(doc_class)` taxonomy resolver) |
| `src/metrics.py` | `llm_dojo_scoring.diagnostics` (keeps the `master=` keyword via a resolver closure) |
| `src/scorers.py` | `llm_dojo_scoring.classification` (keeps the local `cost` scorer + name registry + `EvalResult`-list `per_class_stats`/`macro_accuracy`) |
| `src/bootstrap.py` | `llm_dojo_scoring.bootstrap` |
| `src/cost_models.py` | `llm_dojo_scoring.cost` |
| `src/experiment_log.py` (core) | `llm_dojo_scoring.experiment` + `llm_dojo_scoring.cost` (`append_experiment`, `git_snapshot`, `mean`, `tokens_summary`); the markdown renderers stay local |

Two adapter modules bridge the repo into the package:

- **`src/dojo_config.py`** — wires `config/taxonomy.yaml` into the package
  `Settings` at import time (idempotent): the `field_scoring:` block (including
  `embedding_enabled`, which the package defaults off), the `cost_models:`
  block (YAML dict form → the package's `[input, output]` list form), type
  coercion (`ambiguous_band` → tuple, `partial_gt_fields`/`containment_fields`
  → set), and `load_env()` first so the embedding rescue sees the repo keys.
  `LLM_DOJO_SCORING_CONFIG` pointing at an external YAML file wins wholesale.
- **`src/dojo_compat.py`** — keeps the runner's `classify_failure(doc_type_ok,
  subclass_ok, predicted_subclass)` positional-boolean contract (`None` on
  success) against the package's row-dict `classify_docclass_failure`.

Package surface (importable as `llm_dojo_scoring.*`): `bootstrap`,
`classification`, `bundles`, `config` (all thresholds/equivalence sets/subtype
lists/cost tables/failure modes), `cost`, `diagnostics`, `doc_bundles`,
`emitter`, `equivalences`, `error_analysis`, `experiment`, `export`,
`failure_modes`, `field_scoring`, `io`, `interpret`, `langfuse_sync`,
`phoenix_sync`, `profiles`, `pruning`, `registry`, `report`, `tasks` (§8),
`visualize`. Settings
are one `Settings` object (per-module ad-hoc accessors replaced): `configure()`
for inline overrides, `load_settings()` for YAML files, `get_settings()` /
`clear_settings_cache()` for the process-wide cached object. CLIs:
`dojo-analyze` / `dojo-export` / `dojo-sync` (and `python -m
llm_dojo_scoring.cli`).

### 0.1 The unified scoring layer & the score-emitter bridge (v0.19.0+)

Since KANBAN-061 the package also owns this repo's metric **infrastructure**
(pinned `@v0.5.1` at adoption, current pin `@v0.10.0`); calculations are
untouched — Hungarian matching, embedding rescue, bootstrap CI and CUAD
equivalences all live upstream unchanged:

- **`registry`** — every score name → tier (**T0 HEADLINE** / **T1 CORE** /
  **T2 DEEP** / **T3 LOG**), units, aggregation, applicable agents. The
  built-in default covers both consumers' full emission surfaces (incl. all 37
  llm-mailroom `SCORE_CONFIGS` names, which mailroom validates against at
  import). Override via `LLM_DOJO_SCORING_REGISTRY` YAML.
- **`bundles`** — nine task bundles (`classification`, `extraction`,
  `extraction_open`, `cost`, `factuality`, `laziness_detection`, `audit`,
  `reporter`, `transcription`), registry-validated.
- **`profiles`** — **23 agent profiles**, one per pipeline agent's scoring
  identity: sorter, seven specialists (incl. `insurance_claims_specialist`),
  judge/boss/reporter/transcribers/archivist/audit_agent, plus the Lane A/B
  review set (`sorter_reviewer`, six per-specialist auditors, `arbiter`) that
  never require ground truth. YAML overlay via `LLM_DOJO_SCORING_PROFILES`.
- **`doc_bundles`** (KANBAN-067) — eight document-type-aware
  `DOC_TYPE_BUNDLES` (`contract`, `merger_agreement`, `corporate_record`,
  `due_diligence`, `correspondence`, `compliance_filing`, `court_opinion`,
  `insurance_claim`). Honesty mandate: type-specific metrics ship only where
  real scorers exist today; pending types declare the gap instead of inventing
  numbers. `AgentProfile.resolve_doc_bundle()` falls back to a task bundle
  with an EXPLICIT `used_fallback=True` marker.
- **`emitter`** — unified fan-out: registry-validated `emit_score` → sinks
  (`LocalManifestSink` JSONL; `LangfuseSink` inert unless credentials resolve);
  aggregated `get_scorecard(agent, run_id, min_tier=...)` + T0-only
  `compare_headlines`.
- **`pruning`** — dashboard views: `dashboard_metrics(agent)` (profile bundle ∩
  T0+T1), `headline_metrics(agent)` (strictly T0), `prune_records`.

This repo consumes that layer through a third adapter module:

- **`src/score_emitter.py`** — thin bridge over `emitter` + `pruning`:
  `build_emitter(manifest_path=None, *, langfuse=False)` (local JSONL sink at
  `reports/scores_manifest.jsonl`, optional Langfuse sink that stays inert
  without credentials), `emit_run_scores(emitter, agent, run_id, metrics)` →
  `(emitted, skipped)` (registry-unknown or `None` names are returned as
  skipped — new KPIs surface as registry work, never silently lost), and
  `dashboard_names(agent)` / `headline_names(agent)` tier-capped views.


## 1. Label normalization (`llm_dojo_scoring.classification`)

| Function | Purpose |
|---|---|
| `normalize_label(value)` | Coerce an LLM output into a canonical doc-class key: lowercase, strip quoting; prefer a JSON object's `doc_type` field; word-boundary regex fallback (`corporate_record` matches "Corporate Record", "corporate record", ...). |
| `ERROR_PREFIX` | Sentinel `"ERROR: "` prepended to failed-row outputs so failures are never silently counted as predictions. |
| `normalize_task_answer(task, value, valid=)` | Task-aware label normalization (see §8): MAUD consideration + LegalBench answers use their own tables; doc-class/subtype/others go through `normalize_label`. |

## 2. Classification scorers (`llm_dojo_scoring.classification`)

Used by `run_classification_eval.py` (`--scorers exact_match,failure,cost`).

| Scorer | Signature | Definition |
|---|---|---|
| `exact_match` | `(output, expected) -> float` | `1.0` iff `normalize_label(output) == normalize_label(expected)`, else `0.0`. |
| `failure` | `(output, expected) -> float` | `1.0` for rows whose output starts with the `ERROR:` sentinel (model error, invalid class, timeout), else `0.0`. Failed rows are counted as misses in `exact_match` and tracked separately via `failure`. |
| `cost` | `(input) -> float` | Actual billed USD for the row, captured from OpenRouter `usage.cost` by the task; `0.0` for manifest-replayed rows (paid for in the original run). |

**Per-class / macro** (`run_multiclass_eval.py`, plus helpers in the package):

| Metric | Definition |
|---|---|
| per-class accuracy | `correct / n` per expected class (failed rows excluded) |
| `macro_accuracy` | unweighted mean of per-class accuracies over non-empty classes |

**Binary question** (`run_binary_class_eval.py`, `--positive <class>`): treats
one class as positive and reports `precision`, `recall`, `f1` over
predicted/expected positives plus exact match.

## 3. Field-type-aware content scoring (`llm_dojo_scoring.field_scoring`)

Each extracted field is scored by its declared type
(`config/taxonomy.yaml → doc_classes[].field_types`; unmapped fields fall back
to a name heuristic). `FIELD_SCORERS` dispatch table:

| Type | Scorer | Definition |
|---|---|---|
| `id` | `score_id_field` | Normalize (uppercase, strip punctuation/whitespace, drop corporate suffixes) → exact match. Docket/filing/reference numbers. |
| `date` | `score_date_field` | Parse both sides to a canonical `datetime.date` (ISO, `mm/dd/yyyy`, "March 3, 2024", ordinal prose "10th day of January 2000", OCR artifacts) → exact match. **Null-expectation rule (v20-era scorer, hardened in v21):** a blank-template or label-only expected date ("_____ day of ________, 19____", "Effective Date:", "the date of the Closing") holds no real date — the row's expectation is null: a null/empty prediction scores 1.0 (the model is CORRECT to find no date), any non-empty prediction scores 0.0. The rule only fires when the expected is genuinely template/label garbage — a PARSEABLE expected date ("11/4/10", "9/9/97") is never null — and it is consulted BOTH inside `score_date_field` and at the `pred is None` short-circuit in `score_extraction` (a null answer for a null-expectation field is a full-credit answer, not a miss). Fallbacks, in order: **containment** — the label's date phrase (month/day-level: 3+ tokens or an explicit month) appears inside the prediction, or vice versa (CUAD maps BOTH "Agreement Date" and "Effective Date" onto `effective_date`, so documents legitimately carry several dates and the labeler may hold any of them) → 1.0; **partial credit** on shared components when both sides parse — year+month → 0.67, within a 45-day cluster (execution vs defined effective date — the same agreement's date pair) → 0.67, year-only → 0.33; unparseable values fall back to `name` fuzzy matching. A bare year ("2024") never earns full credit. |
| `money` | `score_money_field` | Strip `$`, commas, expand `K`/`M`/`B` suffixes and "USD/DOLLARS/EUROS" → float compare within **one cent** (legal amounts are exact: $250,001 ≠ $250,000). Unparseable prose falls back to `name` matching. |
| `name` | `score_name_field` | Normalized fuzzy matching: max(Jaro-Winkler, token-set ratio), but JW is only trusted when the token sets share ≥ 1 token (JW is dangerously lenient on disjoint short-vs-long names). **Containment first (v20-era scorer):** when EVERY expected token appears in the prediction ("FRANCHISE AGREEMENT" inside "Goosehead Insurance Agency, LLC Franchise Agreement") → 1.0 — short titles contained in longer extracted titles are matches. |
| `free_text` | `score_free_text_field` | SQuAD-style token F1 over lowercase token multisets. |
| `containment` | `score_containment_field` | Share of the EXPECTED text's (stopword-filtered) tokens covered by the prediction. For verbatim-clause fields whose label is one sentence of a longer passage — returning the expected sentence plus riders/citations scores 1.0. Applied automatically to `containment_fields` (`governing_law`, `term_length`, `renewal_terms`). |
| `entity_list[:<element>]` | `score_entity_list` | Pairwise similarity matrix over predicted vs expected items, **optimal bipartite matching** (Hungarian algorithm, `scipy`; greedy fallback), threshold `bipartite_match_threshold` (0.6) → `precision = matched/n_predicted`, `recall = matched/n_expected`, `f1 = 2PR/(P+R)`. A compound type like `entity_list:free_text` resolves to entity-list scoring with `free_text` element similarity via `is_entity_list`. |

**Embedding rescue** — `name`/`free_text` and list elements of those types
additionally get a second signal when the string score is below
`embedding_rescue_below` (0.7): cosine similarity from
`sentence-transformers/all-MiniLM-L6-v2` (local) with an OpenRouter
`text-embedding-3-small` fallback, lazy-loaded, degrading silently to the
string score when unavailable. `max(string_score, sim)` — never overrides a
confident string-level match.

**Partial ground truth** (`partial_gt_fields`: `parties`,
`key_obligations`, `termination_clauses`) — CUAD clause-QA labels are partial
samples, not exhaustive lists, so the model is usually MORE complete than the
label set. For these fields:

- the reported list score is **ground-truth coverage** = `recall` over matched
  label items (`EntityListScore.score`), NOT F1 — extra correct extractions
  don't cut the score;
- role-word labels ("Shipper.", "Seller", "Sponsor", ...) count as matched
  whenever the prediction names at least one party (the role is instantiated);
- **contained labels (v20-era scorer)**: a GT label of 3-6 tokens whose
  tokens appear VERBATIM, contiguously, inside a predicted item is also
  instantiated — CUAD party labels are sometimes fragments of the extracted
  name ("Consultant" inside 'Timothy Cabrera ("Consultant")', the pronoun
  alias '"we," "us," or "our"' inside 'Goosehead Insurance Agency, LLC
  ("we," "us," or "our")'). Matched unconditionally (no party-presence
  gate needed — the containing item is the evidence);
- raw precision/recall/F1 are always kept in `entity_list_scores` for audit.

**Ambiguous band** `[0.5, 0.85]` — per-field scores inside the band set
`ambiguous_fields`, which (a) marks the row `needs_judge_review` and (b)
triggers the optional `--judge` LLM pass (correctness/completeness).

## 4. Composite extraction-eval metrics (`run_extraction_eval.py`)

The task returns a composite output computed locally; registered scorers are
lookups on it:

| Tracker | Definition |
|---|---|
| `overall_extraction_score` | mean of per-field content scores over expected fields with a non-null expected value (`overall_score` in the composite). |
| `field_presence` | binary conformance: share of expected fields the model populated (non-null/non-empty). |
| `schema_valid` | `1.0` iff the model returned parseable, schema-conformant JSON. |
| `category_presence` | CUAD YES/NO category conformance: share of the document's applicable presence-type categories (labeled clauses that must be covered) whose clause text is present in the extraction. Absent categories are satisfied unless fabricated (the factuality guard catches fabrication). Since llm-dojo-scoring v0.3.0 (issue #21): the evaluator first routes each category to the reasoning-trace entry tagged with the canonical CUAD category name (v33 retag), else to the DISAGGREGATED spans of the category's mapped field, and a category is matched when any candidate span covers the labeled clause by token containment (≥ `verification_token_coverage` 0.7) or embedding similarity (≥ `presence_embedding_threshold` 0.7). |
| `overall_verified_precision` | factuality guard: mean `verified_precision` over every audited field (list + scalar) the model populated — anchored to exactly the components that make it up. |
| `{field}_score` (`--bt-scores full`) | the field's content score (same number that feeds `overall_extraction_score`). |
| `{field}_f1` (`--bt-scores full`) | the SAME list score that feeds the per-field score (GT coverage for partial-GT fields, F1 otherwise) — tracker consistency rule. |
| `{field}_precision` (`--bt-scores full`) | over-extraction guard: `matched_gt / n_predicted` (raw precision). |
| `{field}_verified_precision` (`--bt-scores full`) | truth guard: share of predicted items that match a GT label OR are grounded in the document text. |

**The `entity_list_audit` artifact** — the canonical post-hoc analysis record.
Every result row carries `entity_list_audit.<field>` (one entry per list
field, and for scalars too) with the exact numbers behind the trackers:

```
{
  "n_predicted": <items the model returned>,
  "matched_gt": <items matched to a GT label via bipartite matching ≥ 0.6>,
  "verified_in_doc": <matched_gt + items grounded in the source document>,
  "true_items": <n_predicted − hallucinated>,
  "verified_precision": true_items / n_predicted,
  "hallucinated": n_predicted − true_items,
  "hallucination_rate": hallucinated / n_predicted,
  "doc_verification": <bool — whether the doc-grounding pass ran>
}
```

Post-hoc analysis is performed on these numbers directly (summed over rows),
never on recomputed scores. The A/B-series metrics derive from them:

| Post-hoc metric | Definition |
|---|---|
| item count | `Σ n_predicted` over `key_obligations` audits (per-doc median words in the raw items) |
| matched GT spans | `Σ matched_gt` — the recall numerator over the partial GT labels |
| **alignment precision** | `Σ matched_gt / Σ n_predicted` — how many of the model's items actually line up with an annotator span (the `{field}_precision` tracker, summed) |
| verified precision | `Σ true_items / Σ n_predicted` (the `overall_verified_precision` tracker) |

**Factuality audit** — every predicted item/value must be TRUE: it either
matches a ground-truth label (element scorer ≥ 0.6) or its content is present
in the source document (normalized token coverage ≥ `token_coverage` 0.7;
dates grounded by parsing date candidates in ANY format from the document).
Items that are neither are hallucinations:

```
verified_precision = (GT-matched + doc-grounded) / n_predicted
hallucination_rate  = (n_predicted - true_items) / n_predicted
```

**Chunked extraction scoring** (`--chunked`, the v15+ architecture): the
document is split on paragraph boundaries into overlapping windows (90k
chars, 8k overlap); each window is extracted in its own call and the passes
are merged — list fields union with normalized dedupe (a clause crossing the
cut is quoted on both sides and deduped), scalars keep the first non-null
value, confidence takes the max. Nothing is truncated, so the merged output
is scored against the full expected field set exactly like a single-pass
output; a chunk that fails to parse is skipped, not fatal. `n_chunks` and
`chunked` are stored per row for audit.

**Run-level regression diagnostics** (`scores.diagnostics` in the experiment
log, computed by `src/metrics.py` → `llm_dojo_scoring.diagnostics`) — post-hoc
aggregates over the stored rows, NOT per-row trackers (run-level, not
per-row):

- **Error decomposition** — `field_exact_rate` / `field_partial_rate` /
  `field_miss_rate`: share of scored (doc, field) pairs at 1.0, `0 < s < 1`,
  and 0.0, with `error_decomposition.<field>` per field and
  `field_presence_per_field` (per-field population share).
- **List quality** — raw (not GT-coverage) precision/recall/F1:
  `entity_list_precision/recall/raw_f1` per field, macro `list_*` over
  `key_obligations`, and span-summed micro `list_micro_*` (each contract
  weighted by its number of spans).
- **Regression error (MAE)** — `date_mae_days` / `duration_mae_days` /
  `money_mae_usd` (+ median AE and per-field buckets): mean/median
  ABSOLUTE error between predicted and expected values over rows where BOTH
  sides parse — dates (`effective_date`) and durations (`term_length`,
  `renewal_terms`) in calendar days, money amounts (`contract_value`,
  `demand_amount`) in USD. A day-shifted date or a $1-off amount is a
  near-miss, not a binary wrong answer. Support sizes (`date_n_pairs`,
  `duration_n_pairs`, `money_n_pairs`) state the evidence behind every row.
- **Regression fit (R²)** — `date_r2` / `duration_r2` (+ per-field
  buckets): coefficient of determination over the SAME parseable pairs:

  ```
  R² = 1 − SS_res / SS_tot
  SS_res = Σ (pred − exp)²        SS_tot = Σ (exp − mean(exp))²
  ```

  1.0 = the predictions reproduce the ground truth exactly; 0.0 = as good
  as predicting the mean; **negative = worse than the mean** (kept, not
  clamped — it signals the extraction is anti-correlated with the truth).
  Undefined (`null`) with fewer than 2 parseable pairs or zero expected
  variance (all expected values identical — `SS_tot = 0`). Dates are
  encoded as ordinal days (translation-invariant, so the offset is
  irrelevant).
- **Span-count drift** — `span_count_mae` / `span_count_signed_mean`
  (+ per-field buckets, `span_count_n_docs`): over list fields, the
  model-vs-annotator item-count delta per document. MAE is symmetric
  (over- AND under-extraction both hurt); the signed mean shows the
  DIRECTION — positive = systematic over-extraction (invented/split
  spans), negative = systematic under-extraction (merged/omitted spans).

Parse sources: expected values prefer the curated master-labels CSV
(`src/master_labels.py`, default `../llm-mailroom/data/cuad/master_clauses.csv`
— normalized answers like `"5/8/14"`, `"2 years"`), falling back to the raw
CUAD clause-label text. A `term_length` expected value that is actually an
expiration date ("...shall terminate on June 30, 2010") feeds the date
buckets, not the duration buckets. The optional `--master-labels` flag and
the `MASTER_LABELS_CSV` env var point at the CSV; the diagnostics degrade
gracefully (raw text parsing) when it is absent.

**Extractor reasoning trace** (`predicted.reasoning` in the per-document
output) — the contracts specialist emits a per-field reasoning trace
BEFORE finalizing the extraction (v24+ schema `reasoning`: `summary` +
`entries[{field, evidence, section_ref}]`). It is a TRACE, never a score:
none of the metrics read it (the diagnostics consume only the extracted
values), it rides along for researchers in the experiment log and Langfuse
observation outputs, and the chunked pass unions entries across windows so
the trace covers the whole document. The predicted values must stay in the
canonical parseable forms (ISO dates, leading duration phrases, plain
currency amounts) for the MAE/R² pairs to be counted — the v24 format
discipline exists precisely for that.

## 5. Chained eval metrics (`run_chained_eval.py`)

Per-stage trackers, registered with `--bt-scores overall|full`:

| Tracker | Definition |
|---|---|
| `sorter_exact_match` | `1.0` iff sorter doc_type == expected (`contract` for CUAD rows). |
| `sorter_subtype_accuracy` | `1.0` iff doc_type AND contract_subtype (normalized against CUAD folder names) match the row's expected subtype. |
| `sorter_confidence` | the sorter's reported confidence. |
| `extractor_overall` / `extractor_field_presence` / `extractor_verified_precision` / `extractor_category_presence` / `extractor_schema_valid` | the same composite lookups as §4, from the specialist stage. |

The package's task layer also provides a single-number composite and a
record-shaped summary (§8): `chained_composite(sorter_score,
extractor_score, weights=(0.25, 0.75))` — the extractor carries the
document-level output the pipeline is ultimately judged on, so it dominates
the default weighting — and `chained_summary(...)` mirroring the
sorter-doc_type/subtype + extractor-overall/presence composite.

## 6. Subtype metrics (`run_subtype_eval.py` / `run_langfuse_subtype_eval.py`)

| Tracker | Definition |
|---|---|
| `exact_match` | share of rows where doc_type == `contract` |
| `subtype_accuracy` | share of rows whose normalized subtype exactly equals the CUAD ground-truth folder |
| `subtype_accuracy_equiv` | strict OR a defensible equivalent family (`SUBTYPE_EQUIVALENCES` in the package `config`: reseller↔distributor, maintenance↔license, development↔license, affiliate↔joint_venture) |
| `confidence` | mean model-reported confidence |
| `failure_insights` | `mode_counts` + per-failed-row `{expected, predicted, mode, equiv_recovered, reasoning}`; modes (package `SORTER_FAILURE_MODES`): `function_over_form`, `other_fallback`, `equivalent_family`, `family_confusion` |
| `per_subtype` | per-family strict/equiv accuracy + counts |
| `confusion_matrix` | expected x predicted counts |
| `subtype_accuracy_ci` / `exact_match_ci` | bootstrap 95% CIs over the per-document flags (see §10) |

## 7. Docclass hierarchical metrics (`run_langfuse_docclass_eval.py`)

The hierarchical sorter task scores BOTH the primary `doc_type` and the
second-level `doc_subclass` dimension (consideration type for merger
agreements — MAUD expert GT; record type for corporate records —
content-detected; communication type for correspondence; claim-document type
for insurance_claim). The **extended** merged surface is the schema v5
`mailroom-corpus` corpus — **1,210 rows / 8 primary classes**
(`data/datasets/docclass_merged.jsonl`, `DOCCLASS_SCHEMA`). The **pilot**
surface is the 5-class docclass-pilot subset (138 stratified rows,
`DOCCLASS_PILOT_SCHEMA`) with four second-level dimensions taught by
`sorter_docclass_pilot_v3` and downstream `*_docclass_pilot_v0` keys.

Contract rows on the extended surface carry `contract_subtype` (the CUAD
folder key) as a separate output field; docclass eval does **not** apply
`SUBTYPE_EQUIVALENCES` to contract rows — strict folder-key match only
(by design; family-level routing belongs on the subtype eval surface).

| Tracker | Definition |
|---|---|
| `doc_type_accuracy` (+ `doc_type_accuracy_ci`) | share of rows with the correct primary class (bootstrap 95% CI). |
| `subclass_accuracy` (+ `subclass_accuracy_ci`) | share of rows whose `doc_subclass` equals the GT — **rows without a subclass GT are unscored** (the class has no second level); they neither count for nor against the metric. |
| `subclass_accuracy_equiv` | strict subclass OR a defensible equivalent family (`DOC_SUBCLASS_EQUIVALENCES`: `mixed_cash_stock` ↔ `mixed_cash_stock_election` — an election structure IS a mixed cash+stock deal with a per-shareholder choice). |
| `exact_match` (+ `exact_match_ci`) | `doc_type` AND subclass both exact. |
| `confidence` | mean model-reported confidence. |
| `per_class_accuracy` | per-primary-class accuracy (doc_type level). |
| `per_subclass_accuracy` / `per_subclass_support` | per-subclass accuracy with support counts (the second-level dimension). |
| `subclass_confusion` | expected x predicted subclass counts. |
| `equiv_recovered` | named rows wrong strictly but a defensible equivalent family read. |
| `input_mode_counts` | text / vision / text_fallback split (the vision-primary arm). |
| `failure_insights` (`sorter.failure_insights`) | `mode_counts` + per-failed-row `{expected, predicted, failure_mode, reasoning}`; modes: `doc_type_miss` (primary class wrong) / `subclass_miss` (primary right, subclass wrong) — classified by `src/dojo_compat.classify_failure` (package `DOCCLASS_FAILURE_MODES`). |

Per-row flags carried in the record: `doc_type_ok`, `subclass_ok`,
`subclass_ok_equiv`, `failure_mode`, `input_mode`, `fallback_reason`.

### Correspondence-only surface (`run_correspondence_eval.py`)

KANBAN-103 adds a correspondence-only sibling on Hugging Face
`Lucius-Morningstar/enron-correspondence-dedup` (agent-blind `default` joined
to `ground_truth` on `filename`; rows with `expected != correspondence` are
dropped). Predicted fields lock to the Hub GT assortment:

| Predicted | Ground truth |
|---|---|
| `doc_type` | `expected` (always `correspondence`) |
| `doc_subclass` | `expected_subclass` (8 communication types) |
| `sentiment_label` | `sentiment_label` (`negative` / `neutral` / `positive`) |
| `sentiment_score` | `sentiment_score` (lexicon polarity in `[-1, 1]`) |

Default draw: **200 subclass-stratified** rows, seed 42 (tiny class
`attorney_demand` has 3 rows on the Hub dump — all 3 are taken; leftover
slots redistribute). Schema `CORRESPONDENCE_EVAL_SCHEMA` (does not mutate
`DOCCLASS_SCHEMA`). Prompt `sorter_docclass_correspondence_v0`.

| Tracker | Definition |
|---|---|
| `doc_type_accuracy` / `subclass_accuracy` / `exact_match` | same as the mixed docclass surface above. |
| `sentiment_label_accuracy` (+ CI) | exact match on the three-way polarity label. |
| `sentiment_score_ok` | share of rows with `\|pred − gt\| ≤ 0.25` (`SENTIMENT_SCORE_BAND`). |
| `sentiment_score_mae` | mean absolute residual on parseable score pairs. |
| `correspondence_exact` (+ CI) | `doc_type` AND subclass AND sentiment label all exact. |
| `per_sentiment_accuracy` / `per_sentiment_support` | per-label accuracy with support. |
| `sentiment_confusion` | expected × predicted sentiment-label counts. |
| `failure_insights` | mixed-surface modes plus `sentiment_miss` (class pair right, label wrong). |

## 8. Task-aware scoring dispatcher (`llm_dojo_scoring.tasks`)

The CUAD-focused suite generalized to every task kind the eval loop produces
(KANBAN-047 / issue #19). `task_kind(task)` maps a task key to a scoring kind
via `TASK_KINDS` (`subtype`, `doc_class`, `docclass`, `maud_docclass`,
`maud_question`, `legalbench`, `multiclass`, `court_opinion`, `chained`,
`contracteval`; unknown keys fall back to the task name → plain label
classification). `score_task(task, expected, predicted, *, valid=,
expected_subclass=, predicted_subclass=, seed=42, n_boot=2000)` returns a
task-appropriate score dict — exact match + per-class + confusion + bootstrap
CIs for the label-classification kinds, plus binary metrics for LegalBench,
plus the doc_type/subclass pair for the hierarchical kinds. All are
deterministic pure functions over `(predicted, expected)` pairs so offline
rescoring, manifest re-scoring, and live scoring never disagree; failed rows
(`ERROR_PREFIX`) count as mismatches in the headline and are skipped by
per-class/confusion breakdowns.

**ContractEval** (KANBAN-052 / arXiv 2508.03080, `llm_dojo_scoring.tasks`
v0.4.0, the `contracteval` task kind) — the directly-mirrored clause-level
legal-risk benchmark: one (contract, question) call per row over the CUAD test
split (4,182 pairs / 102 contracts / 41 categories; 1,244 positives). The
rubric mirrors the paper's `Evaluation.py` + `open_source_model.py` EXACTLY:
`score_task("contracteval", expected_spans, outputs, categories=...)` where
`expected_spans` is a list of GT label-span lists (empty = absent category) and
`outputs` the raw model answers. Confusion — TP = every GT span
verbatim-contained in the output (`contracteval_classified`); TN = absent
category + `No related clause.` (`said_no_related`); FP = absent category +
non-empty clause; FN = present category + no-related or partial coverage —
drives accuracy/precision/recall/F1/F2. Output effectiveness = mean/median
token-set **Jaccard** (`get_jaccard`: strip `.,;:`, lowercase, `/`→space,
|∩|/|∪|) over **positive** pairs. Laziness = `no_related_rate` (over all
pairs) and `false_no_related_rate` — reported over BOTH the run's own positive
count and the paper's hardcoded **1,244** denominator
(`false_no_related_rate_paper`). Per-category metrics (`per_category`, the
paper's Fig-4 analogue) when `categories` is supplied. Fidelity: faithful
full-context (the paper feeds each contract whole, up to 301k chars; the
`contracteval` runner disables the input cap), temperature 0, max_tokens 5000.
The paper's reported 4,128 total is a 54-negative-row-smaller snapshot of the
same `test.json`; the positive set is identical, so F1/F2/Jaccard/false-nr are
directly comparable.

**MAUD** — `maud_docclass_score(...)` (merger-agreement doc_type +
consideration-type subclass with strict + `subclass_accuracy_equiv` scoring)
and `maud_question_score(...)` (the 25,827-row per-question suite). Answers
normalize via `normalize_maud_consideration` — canonical keys `all_cash` /
`all_stock` / `mixed_cash_stock` / `mixed_cash_stock_election` / `other`
(alias table + label surface; unknown values degrade to `other`, the GT-gap
convention).

**LegalBench** — `legalbench_score(...)` / task kind `legalbench`: binary
Yes/No exact match (+ CI), per-class accuracy, and `binary_metrics`
(precision / recall / f1 with `yes` as the positive label), confusion +
top confusions. Answers normalize via `normalize_legalbench`
(`LEGALBENCH_BINARY_LABELS = ("yes", "no")` with `LEGALBENCH_YES_NO` aliases).

**Multiclass** — `multiclass_score(...)`: macro accuracy + `micro_accuracy`
(= exact match) + per-class + confusion. **Court opinions** —
`court_opinion_score(...)`: the `court_opinion` doc-class path (plain label
classification). Task registries live in the package `config`
(`DOC_CLASS_KEYS`, `MAUD_CONSIDERATION_*`, `LEGALBENCH_BINARY_LABELS`,
`COURT_OPINION_CLASS`, `TASK_KINDS`).

## 9. A/B evaluation (`evaluate_prompt_version.py`)

Runs prompt A and prompt B on the same dataset, then reports
`delta exact_match (B − A)` with a verdict (`A wins` / `B wins` / `tie` at
±0.001) plus a per-metric side-by-side table. `--compare-only` fetches two
existing experiments without re-running. A/B deltas are judged against the
measured identical-prompt noise floor on the same surface (see §10).

## 10. Bootstrap confidence intervals & delta significance

- Every run's headline carries a **95% bootstrap CI** (percentile method,
  2000 resamples, seed 42) over its per-document scores — computed by the
  runner and stored as `scores.*_ci` (`src/bootstrap.py` →
  `llm_dojo_scoring.bootstrap.bootstrap_ci`); the site falls back to
  resampling the stored `results[]` arrays, then Wilson, for older records.
- **A/B deltas** (same surface only) get a two-sample bootstrap CI on the
  difference (`delta_significance`): "significant" means the CI excludes
  zero. A 5-doc 0.94-vs-0.88 gap is a CI overlap, not a win.
- **Noise floor** — identical-prompt reruns on the same surface quantify the
  band within which a candidate delta is a logic repair, not a win (measured:
  ±0.006 subtype on 509 docs, ±0.011 extraction on 510, ±0.03 overall on the
  50-doc chunked extraction surface). Candidate deltas inside the band are
  reported as logic repairs.
- **Same-surface rule enforced end-to-end**: a run's "Δ vs best" is only
  computed/colored against the best run with the same dataset fingerprint +
  seed + sample size; the site refuses to compare across surfaces.

## 11. Judge calibration (`--judge`, `run_extraction_eval.py`)

Every ambiguous-band row the judge reviews is persisted to
`data/judgments/<experiment>.jsonl` (`kind: calibration`) and aggregated into
`scores.judge_calibration`:

- `n_judged` / `n_scored` — rows reviewed / rows with a scored verdict;
- `agree_rate` — deterministic strong (≥ 0.85) & judge `accurate`, or
  deterministic weak (≤ 0.5) & judge `inaccurate`, over scored rows;
- `judge_strict` / `judge_lenient` — deterministic strong but judge
  `inaccurate` (strict) / deterministic weak but judge `accurate` (lenient) —
  a systematic lean means trusting the judge more broadly needs calibration.

## 12. Chained error-propagation ablation (`--handoff-scope ground_truth`)

`scores.ablation` on the SAME documents compares the specialist under the
predicted-subtype handoff vs the ground-truth-subtype handoff:

- `predicted_handoff_overall` / `ground_truth_handoff_overall` — extractor
  scores with each cue;
- `sorter_loss_pp` — the gap: sorter routing error, isolated from specialist
  error (same model, prompt, and documents — only the cue differs).

## 13. Token & cost accounting

- `tokens_summary()` (`src/cost_models.py` → `llm_dojo_scoring.cost`)
  aggregates per-row `_last_usage` records into prompt/completion/total
  tokens, mean cost and total cost, and `rows_with_usage` — rows replayed
  from a manifest carry no usage and are excluded from cost summaries.
- `cost_usd` = mean per-row cost; `cost_total_usd` = sum. Chained runs report
  sorter/extractor/total stage rows separately.
- **Cost scoring (every run)** — OpenRouter usage payloads carry no cost, so
  every run is cost-scored deterministically from its recorded
  prompt/completion token counts × verified per-model prices (the package
  `cost_models` table, fed from the taxonomy: qwen $0.03/$0.13 per 1M in/out,
  deepseek-v4-flash $0.05/$0.25, deepseek-v4-pro $0.435/$0.87; unknown models
  resolve by prefix and otherwise report `None` — an honest "unknown price",
  never a fabricated number). `tokens_summary(model=)` stamps
  `cost_estimated_usd` on every record; historical records were backfilled
  (`scripts/reporting/backfill_cost_estimates.py`, documented one-time
  append-only exception). The site shows billed OpenRouter totals when the
  activity CSV is ingested (`build_site.py --openrouter-csv`), and the
  estimate otherwise.

## 14. Monte Carlo robustness metrics (`src/monte_carlo.py`, KANBAN-048)

Zero-spend what-if analysis over the joint reasoning corpus (`reports/
monte_carlo/corpus.jsonl`, gitignored — 17,691 rows from the experiment log +
manifests, each treated as one sample from a per-document/per-prompt/per-model
label distribution). Primitives: `normalize_dist` / `shannon_entropy` /
`majority_margin` (one-document label-distribution statistics), `draw_committee`
(one Monte Carlo majority-vote draw), `bootstrap` / `paired_delta_bootstrap`
(resampled CIs + win probabilities), `confidence_score` / `uncertainty_phrases`
(the escalation heuristic), `task_label_vocabulary` / `decoy_mentioned`
(near-miss signal for free-form reasoning traces). Scenario metrics
(`scripts/reporting/monte_carlo_*.py`, outputs in `reports/monte_carlo/`):

| Scenario | Metric | Reference result |
|---|---|---|
| Ensemble voting | committee accuracy K (majority vote over K simulated votes) with bootstrap CIs | subtype 0.9209 → 0.9513 @ K=25 (weak lever, ~4pp ceiling); doc_type saturated at 0.9928 (no gain) |
| Confidence-gated escalation | headroom vs cost at an alpha confidence threshold (Pareto) | subtype +0.44 pp @ alpha 0.15 to a 0.95 model (1.3× cost); docclass escalation loses |
| Paired-bootstrap prompt ablation | P(win) + CI-excludes-zero per (model, A, B) pair on shared docs | 156 subtype + 12 docclass pairs; sorter_v10/v11 vs v3 +14.1 pp P(win)=1.000; docclass v5 loses |
| Failure pipeline | retry/fallback event simulation from the observed 0.2374% failure rate | max_tries=1 + fallback → 0.004% vs 0.202% without; ~0 failures at 320K |
| Exemplar mining | near-miss detection + token-budget subset selection | 6 subtype + 4 docclass exemplar appendices (development→license first, +25.0 expected flips) |

Full results + interpretation: `memos/monte_carlo_robustness.md`; the
GEPA loop folds the paired-bootstrap ablation + committee-voting robustness
in as a champion-contender selection step (KANBAN-049).

## 15. Failure-mode taxonomy (`llm_dojo_scoring.failure_modes`)

The shared failure-mode definitions (previously inlined in the subtype
runner) live in the package so every report aggregates the SAME modes:

- **Sorter/subtype** — `SORTER_FAILURE_MODES`: `function_over_form` (doc_type
  miss — a document whose function overrode its contract form),
  `other_fallback` (answered "other" for a corpus-filed family),
  `equivalent_family` (defensible equivalent, recovered by
  `subtype_accuracy_equiv`), `family_confusion` (genuine wrong-family pick).
  `classify_failure(sorter)` + `summarize_failures(rows)` →
  `{n_total, n_failed, n_ok, mode_counts, rate, mode_rate, failures}`
  (each failure carries reasoning/filename/confidence when present);
  `per_subtype_accuracy(rows, keys, equivalences=)` and
  `confusion_from_rows(rows, keys, unknown=)` power the per-family tables and
  confusion matrices.
- **Docclass** — `DOCCLASS_FAILURE_MODES`: `doc_type_miss` / `subclass_miss`
  (see §7; `classify_docclass_failure(row)` is the package row-dict form,
  `src/dojo_compat.classify_failure` the runner's positional-boolean form).

## 16. Post-hoc span-level diagnostics (miss attribution)

When a list field's score plateaus, the score alone cannot say WHY. The
sanctioned diagnostic chain (used for the v15→v18 family-fidelity work)
operates on the stored rows + the eval manifest's expected spans:

1. **Unmatched-span extraction** — for each GT span, compute its best
   predicted-item similarity as the scorer would: string token coverage
   first, then the embedding rescue (`max(string_score, embed_sim)`, 0.6
   threshold). Spans below threshold on every item are the score's residual.
2. **Containment test** — check whether an unmatched span is nonetheless
   token-contained (≥ 0.7) in some longer predicted item. If yes, the miss
   is a boundary/segmentation artifact (fixable by grain); if no, the miss
   is a genuine content omission (fixable by scope). This test empirically
   refuted the containment hypothesis on the 50-doc sample: 0/160 unmatched
   spans were embedded — the residual was scope, not segmentation.
3. **Family decomposition** — classify the unmatched spans into the CUAD
   clause categories by keyword/verbatim shapes and tabulate. The category
   with the largest miss count is where the prompt's family enumeration is
   incomplete or its exclusion rule over-broad. The v15 50-doc miss table
   (license grant 40, minimum commitment 12, IP ownership 10,
   anti-assignment 9, audit 6, revenue sharing 6, cap liability 5, ...)
   motivated the v18 family-fidelity catalog.
4. **Recovery check** — re-run the same unmatched-span extraction against
   the candidate prompt's rows to quantify exactly which spans and which
   families a change recovered, before trusting the composite delta.

## 17. ContractEval mapping scorer (`src/contracteval.py`, KANBAN-051)

Benchmarks stored extraction runs against ContractEval (arXiv 2508.03080)
with ContractEval's EXACT rubric, bridging the task-unit gap (they run one
(contract, question) per category; we extract the obligation lists in one
pass). Run via
`python scripts/reporting/run_contracteval_mapping.py` (offline, free).

- **GT**: `data/cuad/master_clauses.csv` — full per-category clause spans +
  presence, joined to stored rows by aggressive filename normalization.
- **Mapping**: each disaggregated predicted span is attributed to the CUAD
  category it covers — reasoning-trace routing first (v33 retag), then
  verbatim label containment, then every category with best expected-within-
  predicted containment ≥ 0.5. The per-category answer is the union of its
  mapped spans, else "no related clause".
- **Metrics (ContractEval-verbatim)**: pooled correctness accuracy/P/R/F1/F2
  with TP = *all* GT label spans verbatim-contained in the answer; token-set
  Jaccard over positive-label pairs; false-"no related clause" rate over
  positive-label pairs. `coverage_bands` adds the semantic lens (best-span
  containment ≥ 0.7/0.5/0.3) to separate paraphrase penalty from missing
  extraction.
- **Caveat**: a one-pass extractor never claims a category the GT marks
  absent, so precision is structurally 1.0 — the discriminating axes vs
  ContractEval are recall / F2 / Jaccard / false-rate.

## Run sink & tracing (how scores reach a UI)

- The primary run path is the **`run_langfuse_*_eval.py` runners** — one trace
  per document with numeric scores, Langfuse **primary** (`llm-dojo` project,
  keys in `langfuse.env`) with the **local Arize Phoenix OpenTelemetry server
  as fallback** (`src/tracing.py::resolve_tracer`; the resolved backend is
  recorded as `tracing_backend` in the manifest header + experiment-log
  record). Every LangChain LLM call can also auto-trace to LangSmith
  (`LANGSMITH_TRACING=true`).
- **Braintrust experiment/span logging is DISABLED by default**
  (`BRAINTRUST_LOGGING=disabled`) — with it off, the `run_*_eval.py` runners
  skip `braintrust.Eval` entirely and use the shared local scoring loop
  (`src/eval_shims.py`, `run_local_eval()`); the same deterministic scorers
  feed the manifest, the experiment log, and any opt-in Braintrust run.
- Adaptive concurrency (`resolve_concurrency`) + rate-limit retry
  (`call_with_rate_limit_retry`) are recorded per run
  (`max_concurrency`, `rate_limit_retries`); external research funding is
  gated behind `--research-funding-key` + `assert_production_run`.