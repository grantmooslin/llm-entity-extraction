# Correspondence sorter v0 — Enron 200-row baseline (KANBAN-103)

**Research question:** On a 200-row subclass-stratified draw from the
deduplicated Enron correspondence Hub dump, how well does
`sorter_docclass_correspondence_v0` (v7 + rule 44) recover communication
function (`doc_subclass`) and content polarity (`sentiment_label` /
`sentiment_score`) against the Hub `ground_truth` assortment?

**Companions:** KANBAN-103; runner `scripts/eval/run_correspondence_eval.py`;
Braintrust [Mailroom-Sandbox experiment](https://www.braintrust.dev/app/UWM-Mailroom/p/Mailroom-Sandbox/experiments/qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42);
report `reports/report_qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42.md`.
**GEPA A/B is parked** — this memo is the handoff packet.

## Answer, Response, + Summary of Results

**Short answer:** Primary class is solved (`doc_type_accuracy` **1.000**,
n=200, 0 errors) because the runner pins `correspondence_focus`. The
discriminating task is **communication function**: subclass accuracy
**0.400** (CI 0.335–0.465). Sentiment label accuracy is **0.630** (CI
0.565–0.695); correspondence-exact (type ∧ subclass ∧ sentiment label) is
**0.305**. The dominant miss is **function-over-form inverted**: demand /
memo / letter / notice / press_release collapse to `email` (the delivery
channel). Negatives collapse to `neutral`. Next mutation should teach
*what the message does*, not *how it was delivered*, plus a polarity
cue that a complaint/threat is not “neutral because it is polite.”

| Tracker | Score | 95% CI | Notes |
|---|---|---|---|
| `doc_type_accuracy` | 1.000 | 1.000–1.000 | correspondence_focus |
| `subclass_accuracy` | 0.400 | 0.335–0.465 | 8 communication types |
| `exact_match` | 0.400 | 0.335–0.465 | type ∧ subclass |
| `sentiment_label_accuracy` | 0.630 | 0.565–0.695 | 3-way label |
| `sentiment_score_ok` (band 0.25) | 0.779 | — | MAE 0.1593 |
| `correspondence_exact` | 0.305 | 0.240–0.370 | type ∧ subclass ∧ label |
| confidence | 0.857 | — | overconfident vs 0.40 subclass |

Same-surface identity: HF `Lucius-Morningstar/enron-correspondence-dedup`,
filename manifest `data/manifests/enron_corr200_s42_filenames.jsonl`, seed
42, fingerprint `7df1e16be2c6f8b0…`, prompt
`sorter_docclass_correspondence_v0`, model `qwen/qwen3.7-flash`,
`--max-input-chars 20000`. n=200 (attorney_demand 3 / demand 25 / email 47
/ letter 25 / meeting_request 25 / memo 25 / notice 25 / press_release 25;
sentiment n 115 / pos 57 / neg 28). Braintrust project **Mailroom-Sandbox**.
Estimated cost ≈ $0.079 (181 rows with usage).

### Per-subclass (support)

| subclass | accuracy | support |
|---|---|---|
| email | 0.7447 | 47 |
| meeting_request | 0.6800 | 25 |
| notice | 0.4800 | 25 |
| press_release | 0.2800 | 25 |
| letter | 0.2000 | 25 |
| memo | 0.1600 | 25 |
| demand | 0.0000 | 25 |
| attorney_demand | 0.0000 | 3 |

### Per-sentiment

| label | accuracy | support |
|---|---|---|
| neutral | 0.8957 | 115 |
| positive | 0.3509 | 57 |
| negative | 0.1071 | 28 |

Failure modes: `subclass_miss` 120 / `sentiment_miss` 19 (n_failed 139).
Largest subclass collapses to `email`: demand 18, press_release 16, memo
16, letter 13, notice 13. Sentiment: 20/28 negatives → neutral; 26/57
positives → neutral; 19 rows missing a parseable label (`unknown`).

### Interpretation

1. **v7 rule 43 (function over format) is not firing on Enron mail.** The
   Hub GT labels by communication function; the model labels by SMTP
   envelope. That is the GEPA parent lesson for `sorter_docclass_correspondence_v1`.
2. **`demand` / `attorney_demand` are a total miss (0/28).** Look for
   payment/compliance verbs, lawyer letterhead, and “we demand” — not the
   From/To headers.
3. **Sentiment is a majority-class prior.** Neutral is ~58% of the draw
   and 90% accurate; the cost is missing complaints and thanks. Rule 44’s
   “politeness ≠ positive” needs a matching “polite complaint ≠ neutral.”
4. **Do not treat 0.400 subclass as a plateau.** The errors are one
   cluster (→ email), not a 1-off long tail. A single function-over-form
   mutation is in scope for the next version key.

*Sources:* `reports/experiment_log.jsonl` record
`qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42`;
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v0_enron200_s42.md`.

## What questions or uncertainties remain?

- Will a v1 function-over-form mutation recover demand/memo/letter without
  dropping email (47-row majority)? Same-surface A/B on the pinned
  filename manifest is required (noise floor unknown on this 200-row
  surface — first run; no champion rerun yet).
- `other` (not in the 8-class GT) absorbed several misses — is the schema
  enum leaking `DOC_SUBCLASS_UNKNOWN`?
- 19 `unknown` sentiment labels: parse/schema gap vs model omission?
- Tiny class `attorney_demand` (n=3) cannot support a per-class claim.
