# Correspondence sorter v2 — Enron 200-row GEPA A/B (KANBAN-103)

**Research question:** Does teaching the Hub demand convention (legal-phrase
hits on the writer's own text, `correspondence_subclasses.py`) recover the
v1 demand wipeout (0/25) on the same 200-row Enron filename manifest,
without giving back the v1 channel-trap gains?

**Companions:** parent memos
[sorter_docclass_correspondence_v0.md](sorter_docclass_correspondence_v0.md),
[sorter_docclass_correspondence_v1.md](sorter_docclass_correspondence_v1.md);
Braintrust
[Mailroom-Sandbox v2 experiment](https://www.braintrust.dev/app/UWM-Mailroom/p/Mailroom-Sandbox/experiments/qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42);
report
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42.md`.
Prompt published as `sorter-docclass-correspondence-v2`. Braintrust live
scorers: `sorter_doc_type` + `sorter_subclass` only; remaining metrics are
post-hoc.

## Answer, Response, + Summary of Results

**Short answer:** Same-surface A/B vs v1 (n=200, seed 42): subclass
**0.465 → 0.485** (+2.0pp). Paired bootstrap CI **−1.5 to +6.0pp includes
0** — accepted into the GEPA pool (strict minibatch improvement) but **not
a claimed win**. Demand moved **0/25 → 3/25 (0.12)**; attorney_demand
**0/3 → 1/3**. The marker lesson fired, weakly. 12 demand rows still go to
`email` and 6 to `other` (parse/`unknown`). v1 remains the safer overall
parent; v2 is the demand-arm candidate. Do not mutate v2.

| Tracker | v0 | v1 | v2 |
|---|---|---|---|
| `doc_type_accuracy` | 1.000 | 1.000 | 1.000 |
| `subclass_accuracy` | 0.400 | 0.465 | **0.485** |
| `sentiment_label_accuracy` (post-hoc) | 0.630 | 0.625 | 0.610 |
| `correspondence_exact` (post-hoc) | 0.305 | 0.350 | 0.385 |
| subclass_miss | 120 | 107 | 103 |

Paired v1→v2 subclass delta +2.0pp (CI −1.5 to +6.0pp); 10 recovered / 6
regressed. Same-surface identity unchanged (filename manifest
`enron_corr200_s42_filenames.jsonl`, fp `7df1e16be2c6f8b0…`,
qwen/qwen3.7-flash, max_tokens 2048). v2 estimated cost ≈ $0.083.

### Per-subclass

| subclass | v0 | v1 | v2 | support |
|---|---|---|---|---|
| email | 0.745 | 0.702 | 0.660 | 47 |
| meeting_request | 0.680 | 0.800 | 0.800 | 25 |
| notice | 0.480 | 0.440 | 0.480 | 25 |
| press_release | 0.280 | 0.480 | **0.560** | 25 |
| letter | 0.200 | 0.440 | 0.400 | 25 |
| memo | 0.160 | 0.240 | 0.240 | 25 |
| demand | 0.000 | 0.000 | **0.120** | 25 |
| attorney_demand | 0.000 | 0.000 | **0.333** | 3 |

v1→v2 flips: recovered demand 3 / press_release 2 / letter 2 / notice 1 /
attorney_demand 1 / email 1; regressed email 3 / letter 3.

### Interpretation

1. **The Hub demand class is a phrase lexicon, not a genre.** Rule 46
   lists the `DEMAND_MARKERS` from Enron-Evaluation-Environment
   `correspondence_subclasses.py` (FINAL NOTICE, BREACH OF CONTRACT,
   DEMAND LETTER, …) on the writer's own text. Three demand rows and one
   attorney_demand row recovered — the lesson is the right one, under-fired.
2. **Most Hub-demand rows still lack a visible marker in the truncated
   own-head the model sees**, or the model still prefers residual email.
   Six demand → `other` look like the 2048-token reasoning-burn parse
   gap, not a taxonomy miss.
3. **Strict gate vs promotion.** Child subclass 0.485 > parent 0.465 on
   the minibatch → accept into the pool. Paired CI includes 0 → do not
   promote v2 over v1 as the release champion.
4. **Sentiment was not on Braintrust** this run (post-hoc only) and is
   slightly down (0.625 → 0.610); out of scope.

*Sources:* `reports/experiment_log.jsonl` v0/v1/v2 records;
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42.md`;
labeler `correspondence_subclasses.py` @ Enron-Evaluation-Environment.

## What questions or uncertainties remain?

- Would exposing the first 1500 chars of own-text (labeler `_own_head`)
  as a runner-side strip — not a prompt — raise demand recall without
  another version key?
- The 6 demand→`other` parse burns: a `max_tokens` bump would confound
  a prompt A/B.
- Memo is still 0.24 — Hub memo is MEMORANDUM / TO-FROM-RE on own text,
  a separate lesson if a v3 is warranted.
- Champion rerun of v1 is still unmeasured.
