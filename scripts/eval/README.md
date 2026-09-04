<div align="center">

# 🧪 Evaluation Scripts

**Evaluation scripts for the llm-entity-extraction package.**

</div>

---

## Scripts

| Script | Purpose |
|:---|:---|
| `run_eval.py` | Run evaluation pipeline |
| `run_agent_eval.py` | Run agent-specific evaluation |
| `run_quality_judges.py` | Run quality judge evaluation |

## Usage

```bash
cd packages/llm-entity-extraction
python scripts/eval/run_eval.py --mock
python scripts/eval/run_agent_eval.py --agent sorter --mock
```

## Sorter + specialists on the mailroom-corpus v7/v8 (HUB-035)

Revision-pinned dumps bridge the published HF corpus to the local-dump
runners (dumps are gitignored — rebuild deterministically with the pinned
revision; the build manifest records sha256s):

```bash
cd packages/llm-entity-extraction
# v7 = HUB-019 freeze (bb57c5ad); v8 = the HUB-028 publication (Hub tip)
python scripts/datasets/build_mailroom_corpus_dumps.py --revision bb57c5ad --label v7
python scripts/datasets/build_mailroom_corpus_dumps.py --revision eafe1ab4c0d330d8f9c7a5fb254155e75d290828 --label v8

# sorter (keyless dry-run verifies wiring; live run needs OPENROUTER_API_KEY)
python scripts/eval/run_langfuse_docclass_eval.py --dry-run --local-dumps data/datasets/mailroom_corpus_v8.jsonl --class-set pilot
python scripts/eval/run_langfuse_docclass_eval.py --local-dumps data/datasets/mailroom_corpus_v8.jsonl --class-set pilot

# specialists — all four canonical arms (contracts arm owns contract+merger)
python scripts/eval/run_langfuse_docclass_specialist_eval.py --dry-run \
    --agent contracts_specialist --prompt-version contracts_specialist_docclass_v0 \
    --local-dumps data/datasets/mailroom_corpus_v8.jsonl
# ... insurance_claims / correspondence / corporate_records likewise
```

GT-coverage reality (HUB-022 matrix): contracts scores 509/661 rows (CUAD
clause GT), insurance 950/950 (full scalar GT incl. the purpose/gist trio —
intent · subject_matter · keywords at 100% on ALL insurance rows, v8
conformance); correspondence scores
350/350 against the corpus GT it actually carries (intent · sentiment_label ·
content_topic at 100%, subject_matter/keywords at 27%) and corporate_records
38/39 (subject_matter/keywords) — explicit GT scoring types in
`GT_FIELD_TYPES`; the output-schema fields (sender, recipient, filing_number,
...) still lack corpus GT (reconciliation: HUB-031/032). The insurance
specialist schema + taxonomy carry `subject_matter`/`keywords` (v8 dictation,
HUB-028) and the prompt versioning is `insurance_claims_specialist_v0/v1/v2`
(v2 = purpose/gist extraction rules).

## Related Files

- `../reporting/` — Report generation
- `../datasets/` — Dataset scripts
- `data/gt/` — Ground truth data
- `reports/` — Generated reports
