<div align="center">

# 📁 Entity Extraction Config

**Configuration files for the llm-entity-extraction package.**

</div>

---

## Structure

| Path | Contents |
|:---|:---|
| [`environments/`](environments/) | Environment-specific configurations |
| [`prompt_engineer/`](prompt_engineer/) | Prompt engineering configurations |

## Configuration Files

| File | Purpose |
|:---|:---|
| `taxonomy.yaml` | Document classes and agent definitions |
| `env.example` | Environment variables template |

## Usage

Copy `env.example` to `.env` and configure:
- LLM provider settings
- Observability backends
- Dataset paths

## Related Files

- `agents/` — Agent implementations
- `src/` — Source code
