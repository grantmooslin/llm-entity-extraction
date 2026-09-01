# Modal-deployed vLLM serving (KANBAN-096)

OpenAI-compatible LLM endpoint on Modal GPU infrastructure, serving any
HF-hosted model through vLLM. This is the llm-entity-extraction side of the
cross-repo capability — the sibling of llm-mailroom's `deploy/modal_vllm.py`
(KANBAN-064): **same environment-knob contract, same `/v1` surface,
separate app name and HF-cache volume**, so both pipelines can share one
deployment or run their own.

This is a configuration *capability*, not a serving-path change: every eval
runner keeps using OpenRouter unless you explicitly point the provider seam
(`OPENROUTER_BASE_URL`) at this deployment.

## Deploy

```bash
cd ~/Desktop/Cold_Storage/llm-entity-extraction
pip install -e ".[deploy]"        # once: installs the modal CLI
modal token new                   # once: authenticate

# Optional knobs (all default-sane; set BEFORE deploy):
export MODAL_VLLM_MODEL="Qwen/Qwen3-8B"     # HF repo id (default Qwen3-8B)
export MODAL_VLLM_GPU="L4"                  # Modal GPU string (default L4)
export MODAL_VLLM_QUANTIZATION=""           # awq|gptq|... (default fp16/bf16)
export MODAL_VLLM_MAX_MODEL_LEN="32768"     # context window in tokens
export MODAL_VLLM_API_TOKEN="pick-a-long-random-string"   # REQUIRED for real use
export HF_TOKEN="hf_..."                    # only for gated/private repos

cd deploy && modal deploy modal_vllm.py       # prints https://<ws>--entity-vllm-serve.modal.run
```

`MODAL_VLLM_API_TOKEN` makes the server reject unauthenticated calls (vLLM's
native bearer enforcement) — set it for anything longer than a throwaway
experiment. First cold boot downloads weights into the persistent
`entity-hf-cache` volume; subsequent boots are fast.

Dev iteration without committing a deployment: `modal serve modal_vllm.py`
(temporary URL while the command runs).

## Point the entity pipeline at it

The provider seam resolves `OPENROUTER_BASE_URL` **at client-build time**
(fixed under this card — import-time binding silently ignored dotenv-set
values), so a line in `config/environments/.env` is the whole switch:

```bash
OPENROUTER_BASE_URL=https://<workspace>--entity-vllm-serve.modal.run/v1
OPENROUTER_API_KEY=<same value as MODAL_VLLM_API_TOKEN>
```

(The key *name* stays `OPENROUTER_API_KEY`; its *value* becomes the vLLM
bearer token.) Also set the runner model to whatever the server actually
serves — e.g. the eval runners' `--model Qwen/Qwen3-8B` — since vLLM serves
exactly the deployed model, not the OpenRouter catalog.

Revert = delete/comment those lines: back to canonical OpenRouter, zero code
involved.

## One deployment, two consumers

llm-mailroom speaks to the SAME server through its own seam:

```bash
DEFAULT_PROVIDER=vllm
VLLM_BASE_URL=https://<workspace>--entity-vllm-serve.modal.run/v1
VLLM_API_KEY=<same value as MODAL_VLLM_API_TOKEN>
```

Deploying the entity app vs the mailroom app are independent Modal apps
(different names, different HF volumes) sharing identical knobs — mirror
whichever knob set you changed across both if you want them serving the same
model.

## Smoke test

```bash
source .venv/bin/activate
python scripts/smoke_vllm_endpoint.py \
    --base-url https://<workspace>--entity-vllm-serve.modal.run/v1 \
    --model Qwen/Qwen3-8B
```

Checks `/v1/models` then a real chat completion, printing the reply and token
usage. Exit 0 = endpoint healthy. (Bearer taken from `--api-key`, else
`VLLM_API_KEY`, else `OPENROUTER_API_KEY`.)

## Tear down / cost

```bash
modal app stop entity-vllm      # stop billing immediately
```

The app scales to zero after 15 idle minutes (`scaledown_window`); you pay
GPU time only while it is warm. The HF weight cache volume persists (~$0.19
GB/month style object storage) — delete with `modal volume delete
entity-hf-cache` if you want the space back.

## Local test coverage

`tests/test_kanban096_modal_vllm.py` (network-free) pins: command assembly +
quantization injection, bearer-token enforcement mapping, distinct app
identity from the mailroom sibling, the call-time seam resolution (incl. the
dotenv regression), classifier/base_agent forwarding, KANBAN-081 manifest
parity for the `[deploy]` extra, and a runtime-tree census proving no runtime
module imports `modal`.
