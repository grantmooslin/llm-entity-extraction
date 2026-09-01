# `data/datasets/` — merged corpus artifacts

**Status:** gitignored (local only, regenerable)

The merged docclass corpus: every document the hierarchical sorter eval
(KANBAN-033) classifies, in ONE dataset. The Hub-published versions live at
[`Lucius-Morningstar/docclass-merged`](https://huggingface.co/datasets/Lucius-Morningstar/docclass-merged)
(parquet shards, `default` = blind / `ground_truth` = answer keys / `files` =
upstream originals); the local JSONL dumps are the builder staging artifacts.

## Contents

| File | Rows | Sources |
|---|---|---|
| `docclass_merged_v6.jsonl` | 1,450 (schema v6 rev1, KANBAN-105: v5 parent + 240 correspondence; the +200 insurance boost is a pending follow-up revision) | v5 Hub shards + `build_correspondence_append.py` via `build_docclass_v6.py` |
| `correspondence_append_v6.jsonl` | 240 | stratified sha256 draw from `enron-correspondence-dedup` GT pool (3-labeler verification pass) |
| `insurance_append_v6.jsonl` | (pending) | DE-SynPUF Sample-1 re-render via claims-data-eda (`build_extra_claims.py`; staging lost to tmp cleanup, rebuild pending) |
| `v6_original_files/` | 700 files (~153MB) | CUAD source PDFs + MAUD `contract_N.txt` + S-1 EDGAR exhibit originals (`attach_original_files.py`) |
| `v5_parent/` | 1,210 | the v5 Hub parquet shards (fusion parent) |

Row shape (the flat streamer-dump shape the docclass eval runner reads via
`--local-dumps`): `{filename, doc_text, prompt, expected, expected_subclass,
split, gt_fields, metadata}` — `expected` is the doc_type key,
`expected_subclass` the second-level key, `gt_fields` the joined answer keys
(classification GT + clause labels + the 13 InsuranceClaimExtraction keys +
purpose/gist trio where labeled).

## Consumers

- `scripts/eval/run_langfuse_docclass_eval.py --local-dumps data/datasets/docclass_merged_v6.jsonl`
  — one-file A/B surface for the docclass sorter iterations.
- `scripts/eval/sync_langfuse_datasets.py --docclass` — Langfuse mirror as a
  single `mailroom-docclass` dataset (llm-dojo).

The dump is deterministically ordered (corpus rank, then filename), so its
fingerprint is reproducible across rebuilds — the same-surface contract holds
for any sample drawn from it. Pinned A/B surfaces
(`data/manifests/docclass_ab120_s42_filenames.jsonl`) are filename-keyed and
remain valid across schema versions.
