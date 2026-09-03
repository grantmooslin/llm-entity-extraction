#!/usr/bin/env python3
"""One-shot Modal vLLM throughput benchmark (KANBAN-095).

Starts a vLLM server on the selected Modal GPU, waits for readiness, runs
vLLM's standard ``vllm bench serve`` (random-dataset mode) against it, parses
the metrics, and returns a JSON report with throughput / latency / estimated
GPU cost. A ``modal run`` container starts, benchmarks, and exits — bounded,
single-shot GPU time instead of the ``modal serve`` retry loop.

Usage:
    modal run modal/benchmark_throughput.py --num-prompts 5 --max-tokens 32 \\
        --prompt-len 64 --concurrency 1           # tiny validation run
    modal run modal/benchmark_throughput.py       # defaults = max-utilization
    modal run modal/benchmark_throughput.py --dry-run   # config + mem estimate only

The GPU is selected at import time via the ``BENCH_GPU`` env var (default
``L4``); raise to ``A10G`` / ``L40S`` / ``H100`` if the L4 is too small.

Human-in-the-loop controller: this module is normally launched by
``scripts/eval/guided_vllm_benchmark.py``, which generates the unique app
name / run ID, gates the paid run, streams + tees the logs, and can stop the
exact app. The app name is read from ``MODAL_APP_NAME`` (set by the controller
before Modal imports this module) so every run has a unique identity.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import modal

# Make the sibling module importable both locally and remotely regardless of
# how Modal mounts the entrypoint (the observed hydration failure was exactly
# this import failing remotely because the sibling was absent / not on path).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vllm_server import hf_cache, vllm_image  # noqa: E402

MODEL_NAME = "Qwen/Qwen3-8B"
MODEL_REVISION = "main"
SERVED_MODEL_NAME = "qwen/qwen3-8b"   # alias benchmark_serving hits at /v1
PORT = 8000
BENCH_GPU = os.environ.get("BENCH_GPU", "L4")
BENCH_GPU_HOURLY_USD = float(os.environ.get("BENCH_GPU_HOURLY_USD", "0.50"))  # L4 rate
FAST_BOOT = True            # --enforce-eager: faster cold start, slightly lower peak throughput

# Bounded lifecycle (KANBAN-095): the controller passes these via env before
# Modal imports this module; each maps to one of the three separate timeouts
# (server-start / benchmark subprocess / overall function).
MODAL_FUNCTION_TIMEOUT = int(os.environ.get("MODAL_FUNCTION_TIMEOUT", "3600"))
MODAL_STARTUP_TIMEOUT = int(os.environ.get("MODAL_STARTUP_TIMEOUT", "600"))

# Unique identity per run: the guided controller sets MODAL_APP_NAME before
# importing this module so ``modal app stop <exact-id-or-name>`` can later
# target ONLY this run (never a shared/generic name).
APP_NAME = os.environ.get("MODAL_APP_NAME", "llm-mailroom-benchmark")
RUN_ID = os.environ.get("MODAL_RUN_ID", "unknown")
_STAGE_T0 = time.monotonic()


def _stage(n: int, name: str, run_id: str = "") -> None:
    """Flushed stage message (run ID + elapsed) for the controller to parse.

    Format is machine-parseable: ``LLM_BENCH_STAGE <n> <name> run=<run_id>
    t=<sec>``. The controller greps the teed log for these lines to show live
    progress and to detect "no stage progress past the deadline". ``run_id``
    is passed EXPLICITLY by the benchmark function (from the controller's run
    ID), never relied on from the remote environment alone.
    """
    rid = run_id or RUN_ID
    print(
        f"LLM_BENCH_STAGE {n} {name} run={rid} t={time.monotonic() - _STAGE_T0:.1f}",
        flush=True,
    )


app = modal.App(APP_NAME)


def _kv_cache_bytes_per_token(model_len_tokens: int, num_layers: int = 36,
                              num_kv_heads: int = 8, head_dim: int = 128,
                              dtype_bytes: int = 2) -> int:
    """Rough KV-cache footprint (bytes) for Qwen3-8B-style GQA at a context."""
    per_token = 2 * num_layers * num_kv_heads * head_dim * dtype_bytes
    return per_token * model_len_tokens


def estimate_memory_fit(max_model_len: int, max_num_seqs: int,
                        gpu_memory_utilization: float,
                        prompt_len: int = 512, output_len: int = 256,
                        concurrency: int = 8,
                        gpu_total_gb: int = 24) -> dict:
    """Honest fit estimate for Qwen3-8B (bf16 ~16GB weights) on a GPU.

    vLLM allocates a SHARED KV-cache block pool sized to available VRAM (after
    weights), not per-sequence-at-max-context. The real constraint is that the
    concurrent workload's live tokens (in-flight requests x prompt+output)
    fit inside that pool.
    """
    weights_gb = 16.1
    available_gb = gpu_total_gb * gpu_memory_utilization
    kv_pool_gb = max(0.0, available_gb - weights_gb)
    per_token_kv_gb = _kv_cache_bytes_per_token(1) / (1024 ** 3)  # 1-token slice
    kv_pool_tokens = int(kv_pool_gb / per_token_kv_gb) if per_token_kv_gb else 0
    in_flight = min(concurrency, max_num_seqs)
    live_tokens = in_flight * (prompt_len + output_len)
    # vLLM preallocates ONE shared block pool sized to available VRAM. The two
    # real constraints: the pool must hold a single max_model_len sequence
    # (context cap), and it must hold the live concurrent workload.
    fits = kv_pool_tokens >= max_model_len and kv_pool_tokens >= live_tokens
    return {
        "weights_gb_est": weights_gb,
        "gpu_total_gb": gpu_total_gb,
        "gpu_available_gb": round(available_gb, 2),
        "kv_pool_gb_est": round(kv_pool_gb, 2),
        "kv_pool_tokens_est": kv_pool_tokens,
        "max_model_len": max_model_len,
        "in_flight_requests": in_flight,
        "live_tokens_workload": live_tokens,
        "fits": fits,
    }


def _wait_for_server(url: str, timeout_sec: int = 900) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            time.sleep(5)
    raise TimeoutError(f"vLLM server at {url} did not become ready in {timeout_sec}s")


def _terminate_process(proc: subprocess.Popen, grace_sec: int = 30) -> None:
    """Graceful terminate -> bounded wait -> kill (bounded lifecycle, KANBAN-095)."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=grace_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass  # process is unresponsive; we already sent SIGKILL


_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*\S+"),
]


def redact(text: str) -> str:
    """Mask API keys / bearer tokens so log tails never leak secrets."""
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("<redacted>", out)
    return out


def bounded_tail(text: str, limit: int = 2000) -> str:
    """Bounded, redacted tail of subprocess stdout/stderr for failure reports."""
    if not text:
        return ""
    return redact(text[-limit:])


def build_benchmark_command(
    *,
    served_model_name: str,
    tokenizer: str,
    base_url: str,
    num_prompts: int,
    max_concurrency: int,
    input_len: int,
    output_len: int,
    result_dir: str = "/tmp",
    result_filename: str = "bench_result.json",
) -> list[str]:
    """The supported ``vllm bench serve`` CLI (vLLM >= 0.8.5).

    ``python -m vllm.benchmarks.benchmark_serving`` was removed in the
    pinned/released vLLM line; the supported online-serving benchmark is
    ``vllm bench serve``. Pure helper so the exact flags are unit-testable.
    """
    return [
        "vllm", "bench", "serve",
        "--backend", "openai",
        "--model", served_model_name,
        "--tokenizer", tokenizer,
        "--base-url", base_url,
        "--endpoint", "/v1/completions",
        "--dataset-name", "random",
        "--num-prompts", str(num_prompts),
        "--max-concurrency", str(max_concurrency),
        "--random-input-len", str(input_len),
        "--random-output-len", str(output_len),
        "--trust-remote-code",
        "--save-result",
        "--result-dir", result_dir,
        "--result-filename", result_filename,
    ]


def _finite_positive_float(value: object) -> float | None:
    """float(value) if it is a finite positive number, else None.

    Missing, malformed, zero, negative, NaN, and Infinity all yield None so
    callers never crash on upstream garbage and never emit non-JSON values.
    """
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if math.isfinite(f) and f > 0:
        return f
    return None


def _finite_or_none(value: object) -> float | None:
    """float(value) if it is a finite number, else None (JSON null).

    Keeps latency/timing metrics from emitting NaN or Infinity upstream.
    """
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _int_or_zero(value: object) -> int:
    """int(value) if it is a finite number, else 0 (guards JSON null)."""
    try:
        return int(_finite_or_none(value) or 0)
    except (TypeError, ValueError):
        return 0


def resolve_total_tokens_per_sec(
    reported_total_tps: object,
    total_input_tokens: int,
    total_output_tokens: int,
    duration_sec: object,
) -> float:
    """Total-token throughput, derived from counts/duration when the reported
    ``total_throughput`` field is missing, zero, or otherwise unusable.

    Prefers a finite positive reported value. Otherwise derives
    ``(input + output) / duration`` when duration is a finite positive float.
    Returns ``0.0`` when derivation is impossible. Never raises.
    """
    reported = _finite_positive_float(reported_total_tps)
    if reported is not None:
        return reported
    duration = _finite_positive_float(duration_sec)
    if duration is None:
        return 0.0
    try:
        total_tokens = int(total_input_tokens) + int(total_output_tokens)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if total_tokens <= 0:
        return 0.0
    return total_tokens / duration


def cost_per_million_tokens(usd_per_hr: float, tokens_per_sec: float) -> float | None:
    """USD per 1M tokens at a tokens/sec rate; None (JSON null) when unusable.

    Returns a finite float when ``tokens_per_sec`` is a finite positive number,
    otherwise None — the result never carries Infinity or NaN.
    """
    if not math.isfinite(tokens_per_sec) or tokens_per_sec <= 0:
        return None
    return usd_per_hr / (tokens_per_sec * 3600) * 1_000_000


def _nonnegative_float_or_none(value: object) -> float | None:
    """float(value) if it is finite and nonnegative, else None (JSON null).

    Applied to monotonic-derived durations so the result never carries NaN,
    Infinity, or negative values.
    """
    f = _finite_or_none(value)
    if f is None or f < 0:
        return None
    return f


def estimate_gpu_cost(usd_per_hr: float, duration_sec: object) -> float | None:
    """USD cost for a GPU interval; None (JSON null) when duration is unusable.

    cost = usd_per_hr * duration_sec / 3600. Always finite, never negative.
    """
    dur = _nonnegative_float_or_none(duration_sec)
    if dur is None:
        return None
    return usd_per_hr * dur / 3600


def parse_gpu_telemetry_sample(text: str) -> tuple[float, float, float] | None:
    try:
        utilization, memory_mb, power_watts = (
            float(value.strip()) for value in text.strip().split(",")[:3]
        )
    except (TypeError, ValueError):
        return None
    values = (utilization, memory_mb / 1024, power_watts)
    return values if all(math.isfinite(value) and value >= 0 for value in values) else None


def summarize_gpu_telemetry(samples: list[tuple[float, float, float]]) -> dict:
    if not samples:
        return {
            "gpu_utilization_avg_pct": None,
            "gpu_utilization_peak_pct": None,
            "gpu_memory_avg_gb": None,
            "gpu_memory_peak_gb": None,
            "gpu_power_avg_watts": None,
            "gpu_power_peak_watts": None,
            "gpu_telemetry_samples": 0,
        }
    columns = list(zip(*samples))
    return {
        "gpu_utilization_avg_pct": round(sum(columns[0]) / len(samples), 2),
        "gpu_utilization_peak_pct": round(max(columns[0]), 2),
        "gpu_memory_avg_gb": round(sum(columns[1]) / len(samples), 2),
        "gpu_memory_peak_gb": round(max(columns[1]), 2),
        "gpu_power_avg_watts": round(sum(columns[2]) / len(samples), 2),
        "gpu_power_peak_watts": round(max(columns[2]), 2),
        "gpu_telemetry_samples": len(samples),
    }


def _collect_gpu_telemetry(stop: threading.Event,
                           samples: list[tuple[float, float, float]],
                           interval_sec: float = 1.0) -> None:
    command = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,power.draw",
        "--format=csv,noheader,nounits",
    ]
    while not stop.is_set():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                sample = parse_gpu_telemetry_sample(result.stdout.splitlines()[0])
                if sample is not None:
                    samples.append(sample)
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
        stop.wait(interval_sec)


def _start_gpu_telemetry() -> tuple[threading.Event, threading.Thread | None,
                                    list[tuple[float, float, float]]]:
    stop = threading.Event()
    samples: list[tuple[float, float, float]] = []
    if shutil.which("nvidia-smi") is None:
        return stop, None, samples
    thread = threading.Thread(
        target=_collect_gpu_telemetry, args=(stop, samples), daemon=True)
    thread.start()
    return stop, thread, samples


def _stop_gpu_telemetry(stop: threading.Event, thread: threading.Thread | None,
                        samples: list[tuple[float, float, float]]) -> dict:
    stop.set()
    if thread is not None:
        thread.join(timeout=6)
    return summarize_gpu_telemetry(samples)


@app.function(
    image=vllm_image,
    gpu=BENCH_GPU,
    timeout=MODAL_FUNCTION_TIMEOUT,
    startup_timeout=MODAL_STARTUP_TIMEOUT,
    retries=0,                       # NEVER auto-retry a benchmark (KANBAN-095)
    volumes={"/root/.cache/huggingface": hf_cache},
)
def benchmark(
    model: str = MODEL_NAME,
    run_id: str = RUN_ID,
    max_model_len: int = 32768,
    num_prompts: int = 100,
    max_tokens: int = 256,
    concurrency: int = 8,
    prompt_len: int = 512,
    gpu_memory_utilization: float = 0.95,
    max_num_seqs: int = 32,
    max_num_batched_tokens: int = 8192,
    gpu_hourly_usd: float = BENCH_GPU_HOURLY_USD,
    fast_boot: bool = FAST_BOOT,
    server_start_timeout: int = 900,
    benchmark_timeout: int = 1800,
) -> dict:
    """Run one vLLM throughput benchmark inside a Modal GPU container.

    Bounded lifecycle: the vLLM server process is terminated in ``finally`` on
    EVERY path (graceful terminate -> bounded wait -> kill). The benchmark
    subprocess gets its own timeout. No retries anywhere.
    """
    server: subprocess.Popen | None = None
    entry_t0 = time.monotonic()
    _stage(2, "remote container hydrated / function entered", run_id=run_id)
    _stage(3, f"GPU/config identified gpu={BENCH_GPU} model={model}", run_id=run_id)

    serve_cmd = [
        "vllm", "serve", model,
        "--revision", MODEL_REVISION,
        "--served-model-name", SERVED_MODEL_NAME,
        "--host", "127.0.0.1",
        "--port", str(PORT),
        "--trust-remote-code",
        "--uvicorn-log-level", "info",
        "--max-model-len", str(max_model_len),
        "--gpu-memory-utilization", str(gpu_memory_utilization),
        "--max-num-seqs", str(max_num_seqs),
        "--max-num-batched-tokens", str(max_num_batched_tokens),
    ]
    if fast_boot:
        serve_cmd.append("--enforce-eager")

    log_path = Path("/tmp/vllm_serve.log")
    try:
        with open(log_path, "w") as log:
            server = subprocess.Popen(serve_cmd, stdout=log, stderr=subprocess.STDOUT)
        _stage(4, "vLLM process started", run_id=run_id)
        try:
            _wait_for_server(f"http://127.0.0.1:{PORT}/v1/models",
                             timeout_sec=server_start_timeout)
        except TimeoutError:
            tail = log_path.read_text(errors="replace")[-4000:]
            return {"ok": False, "status": "failed",
                    "error": "vLLM serve failed to start",
                    "error_category": "startup_timeout", "log_tail": tail}
        startup_duration_sec = _nonnegative_float_or_none(time.monotonic() - entry_t0)
        _stage(5, "model loading / server readiness", run_id=run_id)

        bench_cmd = build_benchmark_command(
            served_model_name=SERVED_MODEL_NAME,
            tokenizer=model,
            base_url=f"http://127.0.0.1:{PORT}",
            num_prompts=num_prompts,
            max_concurrency=concurrency,
            input_len=prompt_len,
            output_len=max_tokens,
        )
        _stage(6, "benchmark started", run_id=run_id)
        bench_t0 = time.monotonic()
        telemetry_stop, telemetry_thread, telemetry_samples = _start_gpu_telemetry()
        try:
            try:
                bench_result = subprocess.run(
                    bench_cmd,
                    capture_output=True,
                    text=True,
                    timeout=benchmark_timeout,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "status": "failed",
                        "error": f"vllm bench serve exceeded {benchmark_timeout}s",
                        "error_category": "benchmark_timeout", "log_tail": ""}
        finally:
            gpu_telemetry = _stop_gpu_telemetry(
                telemetry_stop, telemetry_thread, telemetry_samples)

        if bench_result.returncode != 0:
            return {
                "ok": False,
                "status": "failed",
                "error": f"vllm bench serve failed with exit code "
                         f"{bench_result.returncode}",
                "error_category": "benchmark_failure",
                "stdout": bounded_tail(bench_result.stdout),
                "stderr": bounded_tail(bench_result.stderr),
            }

        result_path = Path("/tmp/bench_result.json")
        if not result_path.exists():
            return {
                "ok": False,
                "status": "failed",
                "error": "vllm bench serve produced no result file",
                "error_category": "benchmark_failure",
                "stdout": bounded_tail(bench_result.stdout),
                "stderr": bounded_tail(bench_result.stderr),
            }
        try:
            raw = json.loads(result_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {
                "ok": False,
                "status": "failed",
                "error": "vllm bench serve produced unreadable result JSON",
                "error_category": "benchmark_failure",
                "stdout": bounded_tail(bench_result.stdout),
                "stderr": bounded_tail(bench_result.stderr),
            }
        benchmark_duration_sec = _nonnegative_float_or_none(
            time.monotonic() - bench_t0)
        total_remote_duration_sec = _nonnegative_float_or_none(
            time.monotonic() - entry_t0)
        _stage(7, "benchmark completed", run_id=run_id)

        output_tps = _finite_positive_float(raw.get("output_throughput")) or 0.0
        total_input = _int_or_zero(raw.get("total_input_tokens", 0))
        total_output = _int_or_zero(raw.get("total_output_tokens", 0))
        duration = _finite_positive_float(raw.get("duration"))
        req_s = _finite_positive_float(raw.get("request_throughput")) or 0.0
        total_tps = resolve_total_tokens_per_sec(
            raw.get("total_throughput"), total_input, total_output, raw.get("duration"))

        output_cost = cost_per_million_tokens(gpu_hourly_usd, output_tps)
        total_cost = cost_per_million_tokens(gpu_hourly_usd, total_tps)

        return {
            "ok": True,
            "status": "success",
            "gpu": BENCH_GPU,
            "gpu_hourly_usd": gpu_hourly_usd,
            "model": model,
            "config": {
                "max_model_len": max_model_len,
                "num_prompts": num_prompts,
                "max_tokens": max_tokens,
                "concurrency": concurrency,
                "prompt_len": prompt_len,
                "input_len": prompt_len,
                "output_len": max_tokens,
                "gpu_memory_utilization": gpu_memory_utilization,
                "max_num_seqs": max_num_seqs,
                "max_num_batched_tokens": max_num_batched_tokens,
                "fast_boot": fast_boot,
            },
            "memory_fit_estimate": estimate_memory_fit(
                max_model_len, max_num_seqs, gpu_memory_utilization,
                prompt_len=prompt_len, output_len=max_tokens, concurrency=concurrency,
                gpu_total_gb={"L4": 24, "A10G": 24, "L40S": 48, "H100": 80}.get(BENCH_GPU, 24),
            ),
            "metrics": {
                "output_tokens_per_sec": round(output_tps, 2),
                "total_tokens_per_sec": round(total_tps, 2),
                "requests_per_sec": round(req_s, 2),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "mean_ttft_ms": _finite_or_none(raw.get("mean_ttft_ms")),
                "median_ttft_ms": _finite_or_none(raw.get("median_ttft_ms")),
                "p99_ttft_ms": _finite_or_none(raw.get("p99_ttft_ms")),
                "mean_itl_ms": _finite_or_none(raw.get("mean_itl_ms")),
                "median_itl_ms": _finite_or_none(raw.get("median_itl_ms")),
                "p99_itl_ms": _finite_or_none(raw.get("p99_itl_ms")),
                "duration_sec": duration,
                "startup_duration_sec": startup_duration_sec,
                "benchmark_duration_sec": benchmark_duration_sec,
                "total_remote_duration_sec": total_remote_duration_sec,
                **gpu_telemetry,
            },
            "cost": {
                "cost_per_1m_output_tokens_usd": (
                    round(output_cost, 4) if output_cost is not None else None
                ),
                "cost_per_1m_total_tokens_usd": (
                    round(total_cost, 4) if total_cost is not None else None
                ),
                "estimated_run_cost_usd": round(
                    gpu_hourly_usd * (duration or 0.0) / 3600, 6
                ),
                "estimated_inference_cost_usd": round(
                    estimate_gpu_cost(gpu_hourly_usd, benchmark_duration_sec), 6
                ) if benchmark_duration_sec is not None else None,
                "estimated_startup_cost_usd": round(
                    estimate_gpu_cost(gpu_hourly_usd, startup_duration_sec), 6
                ) if startup_duration_sec is not None else None,
                "estimated_end_to_end_cost_usd": round(
                    estimate_gpu_cost(gpu_hourly_usd, total_remote_duration_sec), 6
                ) if total_remote_duration_sec is not None else None,
            },
        }
    finally:
        _terminate_process(server)
        _stage(8, "vLLM terminated / cleanup complete", run_id=run_id)


@app.local_entrypoint()
def main(
    model: str = MODEL_NAME,
    run_id: str = RUN_ID,
    max_model_len: int = 32768,
    num_prompts: int = 100,
    max_tokens: int = 256,
    concurrency: int = 8,
    prompt_len: int = 512,
    gpu_memory_utilization: float = 0.95,
    max_num_seqs: int = 32,
    max_num_batched_tokens: int = 8192,
    gpu_hourly_usd: float = BENCH_GPU_HOURLY_USD,
    fast_boot: bool = FAST_BOOT,
    server_start_timeout: int = 900,
    benchmark_timeout: int = 1800,
    result_path: str = "modal/benchmark_result.json",
    dry_run: bool = False,
):
    """CLI entry point: ``modal run modal/benchmark_throughput.py --flag value``."""
    cfg = {
        "model": model,
        "run_id": run_id,
        "max_model_len": max_model_len,
        "num_prompts": num_prompts,
        "max_tokens": max_tokens,
        "concurrency": concurrency,
        "prompt_len": prompt_len,
        "gpu_memory_utilization": gpu_memory_utilization,
        "max_num_seqs": max_num_seqs,
        "max_num_batched_tokens": max_num_batched_tokens,
        "gpu_hourly_usd": gpu_hourly_usd,
        "fast_boot": fast_boot,
        "server_start_timeout": server_start_timeout,
        "benchmark_timeout": benchmark_timeout,
    }
    mem = estimate_memory_fit(
        max_model_len, max_num_seqs, gpu_memory_utilization,
        prompt_len=prompt_len, output_len=max_tokens, concurrency=concurrency,
        gpu_total_gb={"L4": 24, "A10G": 24, "L40S": 48, "H100": 80}.get(BENCH_GPU, 24),
    )
    print(f"[benchmark_throughput] RUN_ID={RUN_ID} app={APP_NAME} GPU={BENCH_GPU}")
    print(f"[benchmark_throughput] config={json.dumps(cfg, indent=2)}")
    print(f"[benchmark_throughput] memory fit estimate: {json.dumps(mem, indent=2)}")
    if dry_run:
        print("[benchmark_throughput] DRY RUN — no GPU scheduled, exiting.")
        return
    print("[benchmark_throughput] scheduling one-shot GPU benchmark...")
    _stage(1, "preflight validated", run_id=run_id)
    report = benchmark.remote(**cfg)
    print("[benchmark_throughput] RESULT")
    print(json.dumps(report, indent=2))
    Path(result_path).write_text(json.dumps(report, indent=2))
    print(f"[benchmark_throughput] wrote {result_path}")