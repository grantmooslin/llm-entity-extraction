<div align="center">

# 📊 Report Generation Scripts

**Report generation scripts for the llm-entity-extraction package.**

</div>

---

## Scripts

| Script | Purpose |
|:---|:---|
| `render_experiment_log.py` | Render experiment log from JSONL |
| `generate_summary.py` | Generate summary reports |

## Usage

```bash
cd packages/llm-entity-extraction
python scripts/reporting/render_experiment_log.py
python scripts/reporting/generate_summary.py
```

## Output

Reports are saved to:
- `reports/` — Generated reports
- `docs/data/` — Site data

## Related Files

- `../eval/` — Evaluation scripts
- `../site/` — Site generation
- `reports/` — Generated reports
