import os
import subprocess
import sys
from pathlib import Path

import modal

MODEL_NAME = "Qwen/Qwen3-8B"          # downloadable HF checkpoint (KANBAN-095 unblock)
MODEL_REVISION = "main"               # pin a git SHA if you want reproducibility
SERVED_MODEL_NAME = "qwen/qwen3-8b"   # alias exposed at /v1 (OpenRouter-style name)
N_GPU = 1
PORT = 8000
FAST_BOOT = True              # set False for max throughput once warmed up

# KANBAN-095 memory-fit (2026-08-29): Qwen/Qwen3-8B (~16GB bf16 weights) does
# NOT fit on an L4 (24GB) at vLLM's default 40960-token context window after
# model load — the previous serve attempt hit a vLLM retry loop / OOM. Cap the
# context to 32768 and bound the scheduler so the KV cache stays within the
# ~6-7GB left over on the L4. Overridable via env for larger GPUs.
MODAL_MAX_MODEL_LEN = int(os.environ.get("MODAL_MAX_MODEL_LEN", "32768"))
MODAL_GPU_MEMORY_UTILIZATION = float(os.environ.get("MODAL_GPU_MEMORY_UTILIZATION", "0.95"))
MODAL_MAX_NUM_SEQS = int(os.environ.get("MODAL_MAX_NUM_SEQS", "32"))
MODAL_MAX_NUM_BATCHED_TOKENS = int(os.environ.get("MODAL_MAX_NUM_BATCHED_TOKENS", "8192"))

# Auth gate: pass VLLM_API_KEY to vLLM as a bearer token (--api-key) and keep
# the Modal endpoint private (unauthenticated=False) unless VLLM_ALLOW_PUBLIC=1.
VLLM_API_KEY = os.environ.get("VLLM_API_KEY", "")
VLLM_ALLOW_PUBLIC = os.environ.get("VLLM_ALLOW_PUBLIC", "") == "1"

_MODULE_DIR = Path(__file__).resolve().parent

vllm_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .entrypoint([])
    .uv_pip_install(
        "vllm>=0.8.5",                  # Qwen3 needs vLLM>=0.8.5 (official Qwen/Qwen3-8B card)
        "huggingface_hub[hf_transfer]",
    )
    .env({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "VLLM_LOG_STATS_INTERVAL": "1",
    })
)

# KANBAN-095 hydration fix: a prior paid Modal invocation repeatedly failed
# during hydration at `from vllm_server import ...` because this sibling module
# was ABSENT remotely (never packaged into the remote image). Bake the local
# `modal/` source directory into the image at /root/modal and put it on
# PYTHONPATH, so `import vllm_server` resolves in the remote container
# regardless of how Modal mounts the entrypoint. copy=True bakes the files into
# the image at build time (guaranteed present), and ignore keeps __pycache__
# junk out. Regression test: tests/test_guided_vllm_benchmark.py
# (test_vllm_server_is_packaged_into_benchmark_image).
vllm_image = vllm_image.add_local_dir(
    str(_MODULE_DIR),
    remote_path="/root/modal",
    copy=True,
    ignore=["__pycache__", "*.pyc", "*.pyo"],
).env({"PYTHONPATH": "/root/modal"})

hf_cache = modal.Volume.from_name("huggingface-cache", create_if_missing=True)

app = modal.App("llm-mailroom-inference")


@app.server(
    image=vllm_image,
    gpu=f"L4:{N_GPU}",                     # smallest smoke-test GPU; raise for warm-up
    scaledown_window=900,                 # keep warm for 15 min of idle
    startup_timeout=600,                    # model download + load can take minutes
    port=PORT,
    target_concurrency=32,                  # requests one replica queues before scaling out
    unauthenticated=VLLM_ALLOW_PUBLIC,  # default: require Modal auth (see start())
    volumes={"/root/.cache/huggingface": hf_cache},
)
class Server:
    @modal.enter()
    def start(self):
        cmd = [
            "vllm",
            "serve",
            MODEL_NAME,
            "--revision", MODEL_REVISION,
            "--served-model-name", SERVED_MODEL_NAME,
            "--host", "0.0.0.0",
            "--port", str(PORT),
            "--trust-remote-code",
            "--uvicorn-log-level", "info",
            # KANBAN-095 memory-fit: bound context + scheduler for the L4's
            # remaining VRAM (the default 40960 context OOMs Qwen3-8B).
            "--max-model-len", str(MODAL_MAX_MODEL_LEN),
            "--gpu-memory-utilization", str(MODAL_GPU_MEMORY_UTILIZATION),
            "--max-num-seqs", str(MODAL_MAX_NUM_SEQS),
            "--max-num-batched-tokens", str(MODAL_MAX_NUM_BATCHED_TOKENS),
        ]

        # FAST_BOOT trades compile/graph capture for quicker boots; turn off later
        if FAST_BOOT:
            cmd.append("--enforce-eager")

        if N_GPU > 1:
            cmd += ["--tensor-parallel-size", str(N_GPU)]

        if VLLM_API_KEY:
            cmd += ["--api-key", VLLM_API_KEY]
        if VLLM_ALLOW_PUBLIC:
            print("WARNING: VLLM_ALLOW_PUBLIC=1 — serving a PUBLIC (unauthenticated) "
                  "GPU endpoint. Do not expose this in production.", file=sys.stderr)

        self.process = subprocess.Popen(cmd)

    @modal.exit()
    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass  # already sent SIGKILL; shutdown continues