# data/hf_export — KANBAN-069 staging + KANBAN-071 upstream-source staging

Gitignored staging area for the Braintrust → Hugging Face Hub dataset mirror
(KANBAN-069) and the upstream-source dataset packs (KANBAN-071).
Contents here are EPHEMERAL — regenerate anytime with:

    .venv/bin/python scripts/datasets/export_bt_to_hf.py        # KANBAN-069
    .venv/bin/python scripts/datasets/build_legalbench_full_pack.py   # 071 pack
    .venv/bin/python scripts/datasets/build_docclass_merged.py        # 071 docclass

Per dataset `<name>` you get:

- `<name>.jsonl` — exported rows (`id`, `input`, `expected`, `metadata`,
  `tags`, `created`); CUAD page-image refs point into `<name>/images/`
- `<name>.manifest.json` — BT project/dataset ids, row count, sha256 of the
  JSONL, source streamer script, license note, export timestamp
- `<name>/images/*.png` — downloaded attachment payloads (1024x1024 grayscale
  contract pages, RVL-CDIP preprocessing shape)

`EXPORT_SUMMARY.json` records each dataset's disposition (exported /
skipped_empty / skipped_not_in_project) for the board's evidence trail.

The Hub copies live at https://huggingface.co/Lucius-Morningstar (one dataset
repo per BT dataset, provenance dataset card included). Braintrust itself is
never written by any of this — reads only.

## Live mirror state (verified 2026-08-22)

| Dataset | BT rows | HF repo | Export sha256 (first 12) |
|---|---|---|---|
| `mailroom-cuad-contracts` | 50 (+546 page PNGs under `images/`) | [mailroom-cuad-contracts](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-cuad-contracts) | `fd61aa0d88d5` |
| `mailroom-cuad-contracts-full` | 510 | [mailroom-cuad-contracts-full](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-cuad-contracts-full) | `cac0c8457e0f` |
| `mailroom-lb-hearsay` | 5 | [mailroom-lb-hearsay](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-lb-hearsay) | `7759253da9a6` |

All three verified post-upload (LFS sha256 or round-trip download hash; the
cuad-contracts repo's 596 row→`images/…` references were checked against the
Hub file list — zero missing). Honest gaps (live BT catalog):
`mailroom-maud-contracts` + `mailroom-s1-corporate-records` +
`mailroom-lb-hearsay-test` exist in Braintrust but hold zero rows; the other
streamer-default names (`mailroom-legalbench-contracts`,
`mailroom-legalbench-maud-classification`, `mailroom-maud-classification`)
were never created upstream. Populate upstream first, then re-run export +
publish.

Note on row shape: cuad-contracts rows carry downloaded payloads —
`input.image` / `input.pages[]` are `{type: image_file, file: …,
source_ref: {key, content_type}}` dicts pointing at the repo's `images/`
folder. An earlier export serialized raw `braintrust_attachment` refs; that
shape is superseded.

## KANBAN-071 upstream-source staging (added 2026-08-22)

| Path | What it holds | Published to |
|---|---|---|
| `legalbench_full/` | 162 task dirs (verbatim TSVs/prompts/READMEs + `*.enriched.jsonl` for cuad_*), `index.jsonl`, `ENRICHMENT_REPORT.json`, generated card | [legalbench-full](https://huggingface.co/datasets/Lucius-Morningstar/legalbench-full) |
| `docclass_merged.jsonl` (+ `docclass_merged.manifest.json`) | 700-row merged docclass corpus (CUAD 509 + MAUD 152 + S-1 39) | [docclass-merged](https://huggingface.co/datasets/Lucius-Morningstar/mailroom-corpus) |
| `KANBAN071_PUBLISH_SUMMARY.json` | per-repo verification record (blob-OID counts, LFS sha256, round-trip verdicts) | — (evidence only) |

Verification record 2026-08-22, GREEN twice: legalbench-full 379/379 local
files matched the Hub tree's git blob OIDs (0 missing, aggregates
round-trip-hash clean); docclass-merged republished as **schema v2**
(KANBAN-073 — non-null `expected_subclass` + `filename` on every row,
28 CUAD contract groups; fixes the Hub viewer's string→null cast crash)
with LFS sha256 local == hub (`3bd9d74de9f1…`, fingerprint `cd652e77…`),
then as **schema v3** (KANBAN-074 — adds per-row `split`; sha
`af7705368c83…`, manifest split_coverage 628/72). Honest enrichment gaps
live in `ENRICHMENT_REPORT.json`
(20 span-unmatched, 8 unknown-contract, 8 audit-SUSPECT — flagged on-row).

## KANBAN-074 Enron staging (added 2026-08-22)

| Path | What it holds | Published to |
|---|---|---|
| `enron_correspondence.jsonl` (+ `enron_correspondence.manifest.json`) | FULL cleaned CMU corpus: 517,390 rows / 150 custodians, 10-key GT + evidence + splits | [enron-correspondence](https://huggingface.co/datasets/Lucius-Morningstar/enron-correspondence) |
| `KANBAN074_PUBLISH_SUMMARY.json` | enron verification record (rows, splits, subclass counts, LFS sha verdict) | — (evidence only) |

Enron verification GREEN: LFS sha256 local == hub (`0554a5973935…`);
splits 465,570 train / 51,820 test; datasets-server `pending [] failed []`,
all columns string-typed. Regenerate via
`.venv/bin/python scripts/datasets/publish_enron_correspondence.py`
(requires the sibling repo's `data/enron/index.jsonl` — build with its
`scripts/build_corpus_index.py`).
