<div align="center">

# 🧪 Entity Extraction Tests

**Test suites for the llm-entity-extraction package.**

</div>

---

## Running Tests

```bash
cd packages/llm-entity-extraction
uv run pytest tests/
```

## Structure

| Path | Contents |
|:---|:---|
| [`assets/`](assets/) | Test assets |
| [`fixtures/`](fixtures/) | Test fixtures |

## Test Structure

Tests cover:
- Agent behavior
- Pipeline processing
- Scoring accuracy
- Data integrity

## Related Files

- `agents/` — Agent implementations
- `src/` — Source code
- `data/` — Test data
