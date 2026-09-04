<div align="center">

# 🌐 Site Generation Scripts

**Site generation scripts for the llm-entity-extraction package.**

</div>

---

## Scripts

| Script | Purpose |
|:---|:---|
| `build_site.py` | Build the experiment log viewer site |

## Usage

```bash
cd packages/llm-entity-extraction
python scripts/site/build_site.py
python scripts/site/build_site.py --check
python scripts/site/build_site.py --openrouter-csv activity.csv
```

## Output

Generated site data is saved to:
- `docs/data/` — Site data (meta.json, index.json, runs/)

## Related Files

- `../reporting/` — Report generation
- `../eval/` — Evaluation scripts
- `docs/` — Generated site
