"""KANBAN-096 — Modal-deployed vLLM server for llm-entity-extraction.

Cross-repo sibling of llm-mailroom's ``deploy/modal_vllm.py`` (KANBAN-064):
SAME environment-knob contract, SAME OpenAI-compatible /v1 surface, separate
app name + HF-cache volume — so ONE Modal workspace can host independent
deployments per pipeline, or a single deployment can back BOTH repos (see
deploy/README.md, "One deployment, two consumers").

A configuration CAPABILITY, not a serving-path change: OpenRouter stays the
primary LLM backend for every eval runner unless someone explicitly sets
``OPENROUTER_BASE_URL`` (entity seam: ``agents/base_agent.py::llm()`` +
``src/openrouter_utils.py``, resolved at client-build time) to this
deployment's URL. See deploy/README.md for the full flip-the-switch steps.

Deploy:

    cd llm-entity-extraction/deploy
    pip install -e ".[deploy]"   # once (modal CLI)
    modal token new              # once
    modal deploy modal_vllm.py   # prints the https://...modal.run URL

Dev smoke test without deploying (temporary URL while the command runs):

    modal serve modal_vllm.py

All knobs come from environment variables at DEPLOY time (baked into the
app via modal.Secret.from_dict — modal SDK 1.5.4 removed Secret.from_local),
so no code edits are needed to change model, GPU size, or quantization:

    MODAL_VLLM_MODEL           HF repo id            (default Qwen/Qwen3-8B)
    MODAL_VLLM_GPU             Modal GPU string      (default L4)
    MODAL_VLLM_QUANTIZATION    awq | gptq | ...      (default: unset = fp16/bf16)
    MODAL_VLLM_MAX_MODEL_LEN   int tokens            (default 32768)
    MODAL_VLLM_API_TOKEN      bearer token the server REQUIRES (recommended;
                               leave unset only for throwaway experiments)
    HF_TOKEN                   for gated/private repos (optional)

The served API is OpenAI-compatible (/v1/chat/completions, /v1/models,
/v1/completions). Point the entity pipeline at it with:

    OPENROUTER_BASE_URL=https://<workspace>--entity-vllm-serve.modal.run/v1
    OPENROUTER_API_KEY=<same value as MODAL_VLLM_API_TOKEN>

(the key env NAME stays OPENROUTER_API_KEY because the LangChain client was
born talking to OpenRouter; its VALUE is just the bearer credential).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

APP_NAME = "entity-vllm"
SERVER_PORT = 8000
HF_CACHE_VOLUME_NAME = "entity-hf-cache"

MODEL = os.environ.get("MODAL_VLLM_MODEL", "Qwen/Qwen3-8B")
GPU = os.environ.get("MODAL_VLLM_GPU", "L4")
QUANTIZATION = os.environ.get("MODAL_VLLM_QUANTIZATION", "")
MAX_MODEL_LEN = os.environ.get("MODAL_VLLM_MAX_MODEL_LEN", "32768")

# Pinned for reproducible deploys; bump deliberately (driver/CUDA compat).
VLLM_IMAGE_TAG = os.environ.get("MODAL_VLLM_IMAGE_TAG", "latest")

# Deploy-time secret env contract. modal SDK 1.5.4 removed
# ``modal.Secret.from_local``; the app builds the equivalent secret from a
# dict, filtered to names that are actually set so a missing token never
# bakes an empty value into the deployment.
CONFIG_SECRET_ENV_NAMES = (
    "MODAL_VLLM_MODEL",
    "MODAL_VLLM_QUANTIZATION",
    "MODAL_VLLM_MAX_MODEL_LEN",
    "MODAL_VLLM_API_TOKEN",
    "HF_TOKEN",
)


def build_config_secret_dict() -> dict[str, str]:
    """Env-name -> value dict for the app's deploy-time secret, filtered to
    names set (and non-empty) in ``os.environ``. Pure — reads only the
    environment, never imports the ``modal`` package, so network-free tests
    pin the filtered behavior directly."""
    return {
        name: os.environ[name]
        for name in CONFIG_SECRET_ENV_NAMES
        if os.environ.get(name, "").strip()
    }


_config_secret = modal.Secret.from_dict(build_config_secret_dict())

hf_cache = modal.Volume.from_name(HF_CACHE_VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.from_registry(f"vllm/vllm-openai:{VLLM_IMAGE_TAG}", add_python="3.12")
    .run_commands("pip install --no-cache-dir huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App(APP_NAME, image=image)


def _server_env() -> dict[str, str]:
    """Environment for the vLLM process inside the container."""
    env: dict[str, str] = {}
    api_token = os.environ.get("MODAL_VLLM_API_TOKEN", "").strip()
    if api_token:
        # vLLM's native bearer enforcement: requests without
        # `Authorization: Bearer <token>` get a 401.
        env["VLLM_API_KEY"] = api_token
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if hf_token:
        env["HF_TOKEN"] = hf_token
    return env


def build_vllm_command(model: str) -> list[str]:
    """Assemble the `vllm serve` argv. Kept pure for unit testing."""
    cmd = [
        "vllm",
        "serve",
        model,
        "--host",
        "0.0.0.0",
        "--port",
        str(SERVER_PORT),
        "--max-model-len",
        MAX_MODEL_LEN,
    ]
    if QUANTIZATION:
        cmd += ["--quantization", QUANTIZATION]
    # Eval workloads are bursty and latency-tolerant: batch freely.
    cmd += ["--disable-log-requests"]
    return cmd


@app.function(
    gpu=GPU,
    volumes={"/root/.cache/huggingface": hf_cache},
    secrets=[_config_secret],
    timeout=60 * 30,
    scaledown_window=15 * 60,
    # Long warm-up (weight download on first cold boot) before health checks.
)
@modal.web_server(port=SERVER_PORT, startup_timeout=60 * 20)
def serve() -> None:
    model = os.environ.get("MODAL_VLLM_MODEL", MODEL)
    cmd = build_vllm_command(model)
    print("starting:", " ".join(cmd))
    subprocess.Popen(cmd, env={**os.environ, **_server_env()})


@app.local_entrypoint()
def main() -> None:
    """`modal run modal_vllm.py` prints deployment guidance without serving."""
    print(f"Deploy with:  modal deploy {Path(__file__).name}")
    print(f"Serving model: {os.environ.get('MODAL_VLLM_MODEL', MODEL)} on GPU {GPU}")
    print(
        "Then point the pipelines at it:\n"
        "  ENTITY (eval runners):\n"
        f"    OPENROUTER_BASE_URL=https://modal.com>--{APP_NAME}-serve.modal.run/v1\n"
        "    OPENROUTER_API_KEY=<same value as MODAL_VLLM_API_TOKEN>\n"
        "  MAILROOM (graph pipeline):\n"
        "    DEFAULT_PROVIDER=vllm\n"
        f"    VLLM_BASE_URL=https://modal.com>--{APP_NAME}-serve.modal.run/v1\n"
        "    VLLM_API_KEY=<same value as MODAL_VLLM_API_TOKEN>"
    )
