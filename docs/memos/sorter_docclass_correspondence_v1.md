# Correspondence sorter v1 — Enron 200-row GEPA A/B (KANBAN-103)

**Research question:** Does one function-over-form mutation
(`sorter_docclass_correspondence_v1`, rule 45 Enron channel trap) recover
communication-function subclass accuracy versus parent v0 on the same
200-row Enron filename manifest, without a demand-class rescue and without
claiming a win inside an unmeasured unpaired noise band?

**Companions:** KANBAN-103; parent memo
[sorter_docclass_correspondence_v0.md](sorter_docclass_correspondence_v0.md);
runner `scripts/eval/run_correspondence_eval.py`; Braintrust
[Mailroom-Sandbox v1 experiment](https://www.braintrust.dev/app/UWM-Mailroom/p/Mailroom-Sandbox/experiments/qwen3.7-flash_sorter_docclass_correspondence_v1_enron200_s42);
reports
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42.md`
and
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v1_enron200_s42.md`.
Prompts published to Mailroom-Sandbox as
`sorter-docclass-correspondence-v0` /
`sorter-docclass-correspondence-v1`.

## Answer, Response, + Summary of Results

**Short answer:** Same-surface A/B (n=200, seed 42, pinned
`enron_corr200_s42_filenames.jsonl`): subclass **0.400 → 0.465** (+6.5pp).
Paired bootstrap 95% CI on the subclass delta is **+1.5pp to +12.0pp**
(excludes 0; 21 recovered / 8 regressed). The gain is the intended cluster
— letter +24pp, press_release +20pp, meeting_request +12pp, memo +8pp —
while `email` trades −4.3pp. **`demand` and `attorney_demand` stay 0/28.**
Sentiment is flat (0.630 → 0.625). Correspondence-exact 0.305 → 0.350
(paired CI includes 0). v1 is the new subclass parent; do not mutate v1;
the next lesson is demand-payload verbs, not another header rule.

| Tracker | v0 | v1 | Δ |
|---|---|---|---|
| `doc_type_accuracy` | 1.000 | 1.000 | 0 |
| `subclass_accuracy` | 0.400 | **0.465** | **+6.5pp** |
| `exact_match` | 0.400 | **0.465** | **+6.5pp** |
| `sentiment_label_accuracy` | 0.630 | 0.625 | −0.5pp |
| `sentiment_score_ok` | 0.779 | 0.770 | −0.9pp |
| `correspondence_exact` | 0.305 | 0.350 | +4.5pp (paired CI crosses 0) |
| confidence | 0.857 | 0.863 | +0.6pp |
| subclass_miss / n_failed | 120 / 139 | 107 / 130 | −13 / −9 |

Same-surface identity: HF `Lucius-Morningstar/enron-correspondence-dedup`,
filename manifest `data/manifests/enron_corr200_s42_filenames.jsonl`, seed
42, fingerprint `7df1e16be2c6f8b0…`, model `qwen/qwen3.7-flash`,
`--max-input-chars 20000`, `--max-tokens 2048`, `reasoning_effort=medium`.
Braintrust project **Mailroom-Sandbox**. v1 estimated cost ≈ $0.082 (183
rows with usage).

### Per-subclass (support unchanged)

| subclass | v0 | v1 | Δ | support |
|---|---|---|---|---|
| email | 0.7447 | 0.7021 | −4.3pp | 47 |
| meeting_request | 0.6800 | **0.8000** | +12.0pp | 25 |
| notice | 0.4800 | 0.4400 | −4.0pp | 25 |
| press_release | 0.2800 | **0.4800** | +20.0pp | 25 |
| letter | 0.2000 | **0.4400** | +24.0pp | 25 |
| memo | 0.1600 | 0.2400 | +8.0pp | 25 |
| demand | 0.0000 | 0.0000 | 0 | 25 |
| attorney_demand | 0.0000 | 0.0000 | 0 | 3 |

Paired flips: recovered letter 7 / press_release 5 / meeting_request 3 /
memo 3 / email 3; regressed email 5 / letter 1 / memo 1 / notice 1.

### Interpretation

1. **Rule 45 fired on form-labeled mail.** v0 cited `Subject:` as email
   evidence; v1's payload cascade recovered letters and press releases that
   travel in SMTP wrappers. That was the parent lesson.
2. **Demand is a different cluster.** 20/25 demand rows still go to
   `email`. The cascade's step (2) did not match whatever the Hub labels
   as demand (often polite operational mail, not "we demand"/"please remit").
   A v2 must diagnose those 25 bodies — do not stack another header ban.
3. **Unpaired CIs overlap; paired does not.** Marginal subclass CIs are
   v0 0.335–0.465 vs v1 0.400–0.530. The honest test on this pinned
   surface is the paired bootstrap (+1.5 to +12.0pp). Champion rerun of
   v0 is still unmeasured (run-to-run noise unknown).
4. **Sentiment was out of scope** and stayed a majority-class prior
   (negatives 3/28 both arms). Do not treat the −0.5pp as a regression.

*Sources:* `reports/experiment_log.jsonl` records
`qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42` and
`qwen3.7-flash_sorter_docclass_correspondence_v1_enron200_s42`;
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v1_enron200_s42.md`.

## What questions or uncertainties remain?

- What does the Hub actually mark as `demand` on these 25 rows (payment
  verbs vs. operational "need this by Friday")? That audit is the v2
  parent lesson.
- `other` still appears (parse/`DOC_SUBCLASS_UNKNOWN` leak + 2048-token
  reasoning burn). A runner `max_tokens` bump would confound a prompt A/B.
- Tiny class `attorney_demand` (n=3) still cannot support a per-class claim.
- Champion rerun of v0 on this manifest would pin the noise floor.
