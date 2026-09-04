<div align="center">

# 📊 EDA Scripts

**Exploratory Data Analysis scripts for the llm-entity-extraction package.**

</div>

---

## Scripts

| Script | Purpose |
|:---|:---|
| `generate_figures.py` | Generate static figures |
| `generate_interactive.py` | Generate interactive charts |

## Usage

```bash
cd packages/llm-entity-extraction
python scripts/eda/generate_figures.py
python scripts/eda/generate_interactive.py
```

## Output

Generated charts are saved to:
- `data/eda/` — EDA outputs
- `data/eda/*/figures/` — Static PNGs

## Related Files

- `../datasets/` — Dataset scripts
- `../eval/` — Evaluation scripts
- `data/eda/` — Generated EDA outputs
