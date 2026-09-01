# Correspondence sorter v3 — demand speech-act (KANBAN-103)

**Research question:** Does overriding the v2 Hub phrase lexicon (rule 46)
with a speech-act test (rule 47: this message itself demands that the
recipient pay / cure / cease / arbitrate) recover true demand /
attorney_demand without treating IT FINAL NOTICE, draft-requests, news
clips, or "we could send a demand letter" as demand — on the same pinned
200-row Enron filename manifest plus `--gt-overrides`?

**Companions:** parent memos
[sorter_docclass_correspondence_v0.md](sorter_docclass_correspondence_v0.md),
[sorter_docclass_correspondence_v1.md](sorter_docclass_correspondence_v1.md),
[sorter_docclass_correspondence_v2.md](sorter_docclass_correspondence_v2.md);
overrides `data/gt/enron_correspondence_label_overrides.jsonl`; Braintrust
[Mailroom-Sandbox v3 experiment](https://www.braintrust.dev/app/UWM-Mailroom/p/Mailroom-Sandbox/experiments/qwen3.7-flash_sorter_docclass_correspondence_v3_enron200_s42);
report
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v3_enron200_s42.md`.
Prompt published as `sorter-docclass-correspondence-v3`. Honest parent is
**rescored frozen-v2 predictions on the corrected GT** (subclass 0.535),
not the old-Hub v2 score 0.485.

## Answer, Response, + Summary of Results

**Short answer:** Same-filename A/B vs rescored v2 (n=200, seed 42, Hub
overrides applied): subclass **0.535 → 0.560** (+2.5pp). Paired bootstrap
CI **−2.0 to +7.0pp includes 0** — accepted into the GEPA pool, **not a
claimed win**. The intended class **got worse**: demand **1/1 → 0/1**,
attorney_demand **1/2 → 0/2**. v3 predicted **zero** `demand` and zero
`attorney_demand`. Rule 47 over-tightened: it correctly demoted two
false-positive v2 `demand` preds to `email`, but also reclassified the
one true demand (`haedicke-m/all_documents/902.`) and the one true
attorney_demand v2 had recovered (`sanders-r/px/19.`) as `email`. 8 of
14 recoveries are `other`→correct (parse-burn noise at `max_tokens=2048`),
not the speech-act lesson. Do not mutate v3. v2 remains the demand-arm
parent.

| Tracker | v2 (old Hub GT) | v2 rescored | v3 |
|---|---|---|---|
| `doc_type_accuracy` | 1.000 | 1.000 | 1.000 |
| `subclass_accuracy` | 0.485 | **0.535** | **0.560** |
| `sentiment_label_accuracy` | 0.610 | 0.610 | 0.640 |
| `correspondence_exact` | 0.385 | 0.405 | 0.440 |
| subclass_miss | 103 | 93 | 88 |
| pred `other` | 21 | 21 | 18 |

Paired v2-rescored→v3 subclass delta +2.5pp (CI −2.0 to +7.0pp); 14
recovered / 9 regressed. Same filename manifest
`enron_corr200_s42_filenames.jsonl`, fp `7df1e16be2c6f8b0…`,
`qwen/qwen3.7-flash`, `max_tokens` 2048. v3 estimated cost ≈ $0.085.
200/200, 0 errors. GT distribution after overrides: attorney_demand 2 /
demand 1 / notice 27 / email 70 / letter 25 / meeting_request 25 /
memo 25 / press_release 25.

### Per-subclass (corrected GT)

| subclass | v2 rescored | v3 | support |
|---|---|---|---|
| email | 0.614 | **0.671** | 70 |
| meeting_request | **0.800** | 0.720 | 25 |
| notice | 0.444 | **0.519** | 27 |
| press_release | 0.560 | 0.560 | 25 |
| letter | 0.400 | **0.480** | 25 |
| memo | 0.240 | 0.280 | 25 |
| demand | **1.000** | 0.000 | 1 |
| attorney_demand | **0.500** | 0.000 | 2 |

v2-rescored→v3 flips: recovered email 8 / letter 3 / notice 2 / memo 1;
regressed email 4 / meeting_request 2 / attorney_demand 1 / demand 1 /
letter 1.

Demand-class rows:

| filename | GT | v2 | v3 |
|---|---|---|---|
| `haedicke-m/all_documents/902.` | demand | demand | email |
| `sanders-r/px/19.` | attorney_demand | attorney_demand | email |
| `sanders-r/px/17.` | attorney_demand | other | other |
| `germany-c/sent_items/636.` | email (override) | demand | email |
| `sanders-r/all_documents/1047.` | email (override) | demand | email |

### Interpretation

1. **Rule 47 did the false-positive job and then kept going.** The two
   leftover v2 `demand` preds on demoted Hub rows (`germany-c/sent_items/636.`,
   `sanders-r/all_documents/1047.`) flipped to `email`. The same tightness
   also flipped the only remaining true demand and the Kaye Scholer draft
   (`px/19.`) to `email`. Speech-act "this message itself performs the
   demand" rejected a forward of actual demand letters and a law firm
   circulating its own draft instrument — both of which rule 47's own
   text was supposed to keep.
2. **Headline +2.5pp is not the demand lesson.** Eight recoveries are
   `other`→correct at unchanged `max_tokens=2048` (the v2 parse-burn
   cluster). That is run noise, not rule 47. Meeting-request dropped
   20/25 → 18/25 on the same parse-`other` path.
3. **Pool-accept, do not promote.** Child 0.560 > parent 0.535 on the
   minibatch → accept into the GEPA pool. Paired CI includes 0 → do not
   claim a win and do not replace v2 as the demand-arm parent. v1 remains
   the safer overall parent on old-GT history; v2 remains the demand-arm
   candidate on corrected GT.
4. **Do not compare 0.560 to the published v2 0.485.** The Hub GT
   changed (27 overrides). Same filenames, different labels. The only
   valid parent is the rescored v2 row.

*Sources:* `reports/experiment_log.jsonl` v2 + v3 records (paired on
filename); `data/gt/enron_correspondence_label_overrides.jsonl`;
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v3_enron200_s42.md`.

## What questions or uncertainties remain?

- Next GEPA lesson (still KANBAN-103): recover the two true speech-act
  positives — a forward of actual demand letters, and a law firm
  circulating / revising its own draft demand — without bringing back
  the phrase-lexicon false positives. Do not loosen rule 47 back into
  rule 46.
- Parse-burn `other` (18 rows at max_tokens 2048) is still a separate
  confound. Do not bump `max_tokens` on the next prompt A/B.
- Sentiment 0.610 → 0.640 was not the lesson and was not gated.
