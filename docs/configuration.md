# Configuration Guide — LLM providers & trace sinks

How to configure both governed pipelines (**llm-entity-extraction** and
**llm-mailroom**) across every supported LLM provider and observability sink.
The committed templates are the authoritative knob lists:
[`config/environments/.env.example`](../config/environments/.env.example)
(entity) and [`https://github.com/Exios66/llm-mailroom/blob/main/.env.example`](https://github.com/Exios66/llm-mailroom/blob/main/.env.example)
(mailroom). This guide explains what to set, when, and why.

## How configuration loads

| | llm-entity-extraction | llm-mailroom |
|---|---|---|
| File | `config/environments/.env` (copy from `.env.example`) | `.env` (repo root) |
| Load point | lazily by `src.env_utils.load_env()` immediately before client construction | at every entrypoint (watcher, API, pilot, scripts) |
| Provider seam resolution | **at client-build time** (KANBAN-096 repair) — dotenv values always take effect | at graph startup via `DEFAULT_PROVIDER` |

Because both load from plain environment variables, true shell exports always
work too; the dotenv file is just the persistent home for them.

## Providers

Every provider speaks the OpenAI-compatible chat API. The difference is only
*which base URL + key* the client is pointed at.

| Provider | entity seam | mailroom seam | Notes |
|---|---|---|---|
| **OpenRouter** (default) | `OPENROUTER_API_KEY` (+ optional `OPENROUTER_BASE_URL`) | `OPENROUTER_API_KEY` + `DEFAULT_PROVIDER=openrouter` | Primary path in both repos; unset everything else and this is what runs |
| **Research-funding key** | `RESEARCH_FUNDING_OPENROUTER_API_KEY`, reachable ONLY via `--research-funding-key` | — | entity-only. The production gate refuses dry-runs and sub-full-dataset samples, so external funding pays solely for fully-ready production runs |
| **vLLM (any server)** | point `OPENROUTER_BASE_URL` at the `/v1` endpoint (key name stays `OPENROUTER_API_KEY`) | `DEFAULT_PROVIDER=vllm` + `VLLM_BASE_URL` + `VLLM_API_KEY` | Same wire protocol; each repo flips through its own seam |
| **Ollama (local)** | — (no code consumer; do not set here) | `DEFAULT_PROVIDER=ollama` + `OLLAMA_BASE_URL` (`http://localhost:11434/v1`) | mailroom-only capability |
| **Generic OpenAI-compatible** | same `OPENROUTER_BASE_URL` mechanism | `DEFAULT_PROVIDER=generic` + `GENERIC_API_KEY` + `GENERIC_BASE_URL` | For any other compatible endpoint |

> Honesty note: `OLLAMA_BASE_URL` / `GENERIC_*` / `DEFAULT_PROVIDER` /
> `OBSERVABILITY_PROVIDER` have **no consumer in llm-entity-extraction** — they
> were mailroom inheritance in the old template and were removed in the 2026-08-24
> condensation. Setting them there does nothing.

### Modal-deployed vLLM (both repos)

Each repo ships a sibling Modal app under the SAME environment-knob contract:

```
MODAL_VLLM_MODEL / MODAL_VLLM_GPU / MODAL_VLLM_QUANTIZATION /
MODAL_VLLM_MAX_MODEL_LEN / MODAL_VLLM_API_TOKEN / HF_TOKEN
```

Deploy-time knobs are set in your shell/dashboard BEFORE `modal deploy` — they
are not runtime env vars and do not belong in `.env`.

```bash
# entity (app name: entity-vllm-serve, volume: entity-hf-cache)
pip install -e ".[deploy]" && cd deploy && modal deploy modal_vllm.py

# mailroom (app name: mailroom-vllm-serve)
cd deploy && modal deploy modal_vllm.py
```

Each prints a `*.modal.run` URL — a bearer-authenticated OpenAI-compatible
`/v1`. Cost shape: GPU scales to zero after ~15 idle minutes; you pay storage
for the HF cache volume between runs. Full runbook (deploy / flip / smoke /
teardown): `deploy/README.md` in either repo. Smoke-check any endpoint:

```bash
python scripts/smoke_vllm_endpoint.py   # entity; exit code is CI-usable
```

### Recipe 1 — default cloud (do nothing)

Set `OPENROUTER_API_KEY` in the repo's `.env`; leave everything else untouched.
OpenRouter stays primary; no serving-path change happens unless YOU flip one.

### Recipe 2 — flip entity onto Modal vLLM

```dotenv
OPENROUTER_API_KEY=<your MODAL_VLLM_API_TOKEN value>
OPENROUTER_BASE_URL=https://<workspace>--entity-vllm-serve.modal.run/v1
```

The key NAME stays `OPENROUTER_API_KEY` (the LangChain client was born talking
OpenRouter); only its VALUE changes. Resolved at call time, so dotenv works.

### Recipe 3 — flip mailroom onto the same deployment

```dotenv
DEFAULT_PROVIDER=vllm
VLLM_BASE_URL=https://<workspace>--entity-vllm-serve.modal.run/v1
VLLM_API_KEY=<your MODAL_VLLM_API_TOKEN value>
```

### Recipe 4 — ONE deployment backing BOTH pipelines

Deploy either app once, then apply Recipe 2 in entity and Recipe 3 in
mailroom, both pointed at the SAME `*.modal.run` URL and token. The contracts
were built cross-compatible on purpose (KANBAN-094-era parity work, KANBAN-096).

### Recipe 5 — fully local, no cloud

- mailroom: `DEFAULT_PROVIDER=ollama`, Ollama running at the default port.
- either repo against a hand-run vLLM: start vLLM locally, then entity →
  `OPENROUTER_BASE_URL=http://localhost:8000/v1`; mailroom →
  `DEFAULT_PROVIDER=vllm` + `VLLM_BASE_URL=http://localhost:8000/v1`.
- Pair with the all-local trace stack (Recipe 7 below) for a zero-subscription rig.

### Teardown / cost guardrails

`modal app stop <app-name>` stops serving (volume persists); delete the volume
from the Modal dashboard when the cache is no longer wanted. Never commit real
tokens — `.env` is gitignored in both repos.

## Trace sinks

Three distinct layers exist; don't conflate them:

1. **Eval-run tracing** (entity `run_langfuse_*_eval.py`) — one trace per
   document per run, recorded as `tracing_backend` in the experiment log.
2. **Pipeline tracing** (mailroom graph) — spans for every agent hop.
3. **Parallel per-call tracers** — LangSmith and/or LangChain's OpenTelemetry
   instrumentation mirror individual LLM calls alongside either of the above.

| Sink | entity | mailroom | Cost | Choose when |
|---|---|---|---|---|
| **Arize Phoenix** (local-first default) | default fallback of `resolve_tracer()`; `PHOENIX_TRACING=enabled`, endpoint `http://localhost:6006/v1/traces` | `OBSERVABILITY_PROVIDER=phoenix` or reached by `auto` | free, SQLite, no tokens | you want zero-cost local tracing (`phoenix serve`, then open :6006) |
| **Langfuse** | primary when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set | `OBSERVABILITY_PROVIDER=langfuse` (+ keys); `LANGFUSE_BASE_URL` alias accepted | cloud quota or self-host | team dashboards / prompt datasets / cloud history |
| **Braintrust** | READ-ONLY by design: datasets yes, scored-run/span logging gated behind `BRAINTRUST_LOGGING=enabled` (default `disabled` — plan quota protection) | `OBSERVABILITY_PROVIDER=braintrust` + `BRAINTRUST_API_KEY` | plan-metered | dataset hosting (entity) or full backend (mailroom) |
| **LangSmith** | `LANGSMITH_TRACING=true` + key + project NAME | — | plan-metered | mirroring LangChain calls next to the above |
| **none** | skip trace flags / leave keys unset | `OBSERVABILITY_PROVIDER=none` (also gates graph startup explicitly) | free | quiet mode |

Resolution order details:

- entity: `resolve_tracer(prefer="langfuse")` tries Langfuse first, falls back
  to the local Phoenix server when Langfuse keys are absent/disabled — tracing
  never silently turns off; the experiment log reports which backend fired.
  (`prefer="phoenix"` restores the older local-first order.)
- mailroom: `OBSERVABILITY_PROVIDER=auto` walks langfuse → braintrust →
  phoenix (local-first fallback, same never-silent principle).
- `OBSERVABILITY_ENVIRONMENT` (mailroom) labels traces `live` / `pilot` /
  `misc` / `mock`; entrypoints set it automatically.

### Recipe 6 — Langfuse cloud

```dotenv
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com   # omit for self-hosted default localhost:3000
```
entity: nothing more needed (becomes the primary tracer). mailroom: also set
`OBSERVABILITY_PROVIDER=langfuse` (or leave `auto`).

### Recipe 7 — fully local, zero-cost stack

Leave all cloud keys unset. Start Phoenix (`phoenix serve`), keep
`PHOENIX_TRACING=enabled` (entity) / `OBSERVABILITY_PROVIDER=auto` reaching
phoenix (mailroom), and pair with Recipe 5 providers. Nothing leaves the machine.

### Recipe 8 — quiet mode

entity: don't configure any sink keys and set `PHOENIX_TRACING=disabled` +
`LANGCHAIN_TRACING_V2=false`. mailroom: `OBSERVABILITY_PROVIDER=none`.

## Related docs

- Templates: entity [`config/environments/.env.example`](../config/environments/.env.example) · mailroom `.env.example`
- Modal runbooks: `deploy/README.md` in both repos · wiki: Phoenix-Tracing
- mailroom taxonomy/model mappings: [`docs/configuration.md`](https://github.com/Exios66/llm-mailroom/blob/main/docs/configuration.md) (its own repo doc)
