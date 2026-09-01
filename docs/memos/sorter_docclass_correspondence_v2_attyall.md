# Correspondence sample — all attorney_demand examples (KANBAN-103)

**Research question:** The Hub dedup dump has only 3 `attorney_demand`
rows, and the seed-42 200-row draw already contained all three. Are there
more official attorney_demand examples, and what happens when they are
folded into the experiment sample under frozen v2?

**Companions:** parent memo
[sorter_docclass_correspondence_v2.md](sorter_docclass_correspondence_v2.md);
Braintrust
[Mailroom-Sandbox attyall experiment](https://www.braintrust.dev/app/UWM-Mailroom/p/Mailroom-Sandbox/experiments/qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42_attyall);
report
`reports/report_qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42_attyall.md`.
v2 prompt is **not mutated**.

## Answer, Response, + Summary of Results

**Short answer:** The full CMU corpus has **4** attorney_demand rows. The
missing one is `sanders-r/ecogas/26.` — the Milbank / Ecogas demand letter,
an exact-body twin of `sanders-r/all_documents/126.` that exact-body dedup
dropped. Integrating it yields n=201 (pinned 200 + extras). Frozen v2 on
this **new surface**: `doc_type_accuracy` **1.000**, `subclass_accuracy`
**0.5124**, attorney_demand **1/4**. The new row misses as `email` (same
mode as its twin). Headline scores are **not** a same-surface A/B vs the
200-row CIs.

| Tracker | v2 n=200 | v2 attyall n=201 |
|---|---|---|
| `doc_type_accuracy` | 1.000 | 1.000 |
| `subclass_accuracy` | 0.485 | 0.5124 |
| `attorney_demand` | 1/3 | **1/4** |
| `demand` | 3/25 | 2/25 |
| `sentiment_label_accuracy` (post-hoc) | 0.610 | 0.612 |
| `correspondence_exact` (post-hoc) | 0.385 | 0.388 |
| n_errors | 0 | 0 |

Fingerprint `0dc53901a3148b2895…`. Estimated cost ≈ $0.085.

### Official attorney_demand inventory

| filename | source | v2 predicted | ok |
|---|---|---|---|
| `sanders-r/px/19.` | Hub (in 200) | attorney_demand | ✓ |
| `sanders-r/px/17.` | Hub (in 200) | demand | ✗ |
| `sanders-r/all_documents/126.` | Hub (in 200) | email | ✗ |
| `sanders-r/ecogas/26.` | full corpus (this extra) | email | ✗ |

`ecogas/26.` and `all_documents/126.` share the same parsed body
(Message-IDs differ). Dedup kept the first path.

### Interpretation

1. **There were no leftover Hub attorney_demand rows.** `--include-all-attorney-demand`
   appended 0 from the dump; `--extra-dumps` restored the one full-corpus
   path the publisher dropped.
2. **Adding the twin does not add new linguistic signal.** v2 misses both
   Ecogas copies as `email` — the marker is “we could send a demand
   letter” (hypothetical), which the Hub labeler still fires on.
3. **px/17. moved from `other` (parse burn on the 200-row v2 run) to
   `demand`.** Still a miss vs attorney_demand (law-firm sender not
   applied). Temperature-0.1 reruns of the other 200 rows also moved
   (demand 3/25 → 2/25; email 0.66 → 0.72) — another reason this is not
   a same-surface A/B.
4. **Arter & Hadden** (`dasovich-j/all_documents/2894.`, Hub `demand`)
   is a law-firm sender missing from `LAW_FIRM_DOMAINS`. Not promoted
   here — Hub GT stays the scoring target.

*Sources:* CMU `enron_mail_20150507.tar.gz` sanders-r mailbox labeled with
Enron-Evaluation-Environment `correspondence_subclasses.py`; Hub
`Lucius-Morningstar/enron-correspondence-dedup` GT; experiment
`qwen3.7-flash_sorter_docclass_correspondence_v2_enron200_s42_attyall`.

## What questions or uncertainties remain?

- Should a later publisher pass add `sanders-r/ecogas/26.` back as a
  distinct eval row (different Message-ID) or keep treating it as a
  duplicate?
- `arterhadden.com` (and `bracepatt.com`) are missing from the official
  law-firm domain list — a labeler card, not a prompt card.
- A champion rerun of v2 on the original 200 is still the only valid
  noise-floor measurement for that surface.
