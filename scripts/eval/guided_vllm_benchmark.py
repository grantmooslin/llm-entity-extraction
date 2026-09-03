#!/usr/bin/env python3
"""Guided human-in-the-loop controller for the Modal vLLM benchmark (KANBAN-095).

This is the operator-facing surface for ``modal/benchmark_throughput.py``. It
is built for a user who is NEW to Modal: every step is explained in plain
language, every paid attempt requires an explicit flag PLUS a run-specific
typed approval, every run gets a unique app identity, one invocation launches
at most ONE ``modal run`` child with zero retries, and Ctrl+C stops ONLY the
current app after an explicit confirmation.

Profiles:
    validate    (default) free — preflight + config + cost ceiling, launches nothing
    smoke       1 prompt, tiny context/output, concurrency 1
    pilot       small stability run
    benchmark   explicit larger measurement (extra warning, never a hidden yes)

Usage:
    python scripts/eval/guided_vllm_benchmark.py                          # validate
    python scripts/eval/guided_vllm_benchmark.py --profile smoke \\
        --enable-paid-run                                                 # gated run
    python scripts/eval/guided_vllm_benchmark.py --profile benchmark \\
        --gpu H100 --gpu-hourly-rate 4.00 --num-prompts 200 \\
        --enable-paid-run                                                 # larger run
    python scripts/eval/guided_vllm_benchmark.py --dry-run --profile smoke  # plan only

Runbook (README §Modal vLLM benchmark): validate -> smoke -> pilot ->
benchmark, ONE setting changed at a time, verify Live Apps returns to 0 after
every run.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_SCRIPT = REPO_ROOT / "modal" / "benchmark_throughput.py"
DEFAULT_RESULTS_DIR = REPO_ROOT / "reports" / "modal_runs"

STAGE_NAMES = {
    1: "preflight validated",
    2: "remote container hydrated / function entered",
    3: "GPU/config identified",
    4: "vLLM process started",
    5: "model loading / server readiness",
    6: "benchmark started",
    7: "benchmark completed",
    8: "vLLM terminated / cleanup complete",
}

PROFILES = {
    "validate": {
        "charges": False,
        "num_prompts": 1,
        "prompt_len": 16,
        "max_tokens": 16,
        "concurrency": 1,
        "max_model_len": 2048,
        "max_num_seqs": 1,
        "max_num_batched_tokens": 512,
        "startup_timeout": 600,
        "benchmark_timeout": 300,
        "function_timeout": 1200,
    },
    "smoke": {
        "charges": True,
        "num_prompts": 1,
        "prompt_len": 16,
        "max_tokens": 16,
        "concurrency": 1,
        "max_model_len": 2048,
        "max_num_seqs": 1,
        "max_num_batched_tokens": 512,
        "startup_timeout": 600,
        "benchmark_timeout": 300,
        "function_timeout": 1200,
    },
    "pilot": {
        "charges": True,
        "num_prompts": 5,
        "prompt_len": 64,
        "max_tokens": 32,
        "concurrency": 2,
        "max_model_len": 8192,
        "max_num_seqs": 8,
        "max_num_batched_tokens": 2048,
        "startup_timeout": 900,
        "benchmark_timeout": 600,
        "function_timeout": 1800,
    },
    "benchmark": {
        "charges": True,
        "num_prompts": 100,
        "prompt_len": 512,
        "max_tokens": 256,
        "concurrency": 8,
        "max_model_len": 32768,
        "max_num_seqs": 32,
        "max_num_batched_tokens": 8192,
        "startup_timeout": 900,
        "benchmark_timeout": 1800,
        "function_timeout": 3600,
    },
}

_GENERIC_APP_NAME = "llm-mailroom-benchmark"   # the shared/default app name


def format_usd(value: float) -> str:
    """Format a USD amount as ``$0.10`` (two decimals, no trailing junk)."""
    return f"${value:.2f}"


def compute_cost_ceiling(gpu_hourly_rate: float, function_timeout: int) -> float:
    """Conservative cost ceiling: GPU rate x maximum runtime (rounded UP).

    The maximum runtime is the overall function timeout (the hard bound on GPU
    time). Rounding up to the cent keeps the ceiling conservative — the real
    run is almost always cheaper (the function exits early on success/failure).
    """
    hours = function_timeout / 3600.0
    raw = gpu_hourly_rate * hours
    return math.ceil(raw * 100) / 100


def make_run_id(profile: str, rng=secrets) -> str:
    """Unique run ID per invocation (e.g. ``smoke-a1b2c3``). Never reused."""
    return f"{profile}-{rng.token_hex(3)}"


def make_app_name(run_id: str) -> str:
    """Unique Modal app name derived from the run ID (never the generic one)."""
    return f"llm-mailroom-benchmark-{run_id}"


def resolve_config(args: argparse.Namespace) -> dict:
    """Profile defaults overridden by explicit flags (argparse defaults)."""
    base = dict(PROFILES[args.profile])
    overrides = {
        "model": args.model,
        "gpu": args.gpu,
        "gpu_hourly_rate": args.gpu_hourly_rate,
        "num_prompts": args.num_prompts,
        "prompt_len": args.prompt_len,
        "max_tokens": args.max_tokens,
        "concurrency": args.concurrency,
        "max_model_len": args.max_model_len,
        "max_num_seqs": args.max_num_seqs,
        "max_num_batched_tokens": args.max_num_batched_tokens,
        "startup_timeout": args.startup_timeout,
        "benchmark_timeout": args.benchmark_timeout,
        "function_timeout": args.function_timeout,
        "fast_boot": args.fast_boot,
    }
    base.update(overrides)
    return base


def explain_profile(profile: str) -> str:
    """Plain-language explanation of what a profile does and whether it charges."""
    p = PROFILES[profile]
    if profile == "validate":
        return (
            "validate — FREE preflight. Checks that the Modal CLI is on PATH, "
            "resolves the exact config + command that a paid run would use, "
            "computes the conservative cost ceiling, and prints healthy-progress "
            "guidance. LAUNCHES NOTHING and cannot incur charges."
        )
    charge_note = "INCURS CHARGES on Modal GPUs" if p["charges"] else "FREE"
    workloads = {
        "smoke": "1 prompt, tiny context/output, concurrency 1 — proves the "
                 "container hydrates and one request round-trips.",
        "pilot": "a small stability run — a handful of prompts at low "
                 "concurrency to check throughput is healthy before scaling.",
        "benchmark": "an explicit LARGER measurement — this is the real "
                     "benchmark run you will compare against OpenRouter.",
    }
    return (
        f"{profile} — {charge_note}. {workloads[profile]} "
        f"Config: {p['num_prompts']} prompts x {p['prompt_len']}-token prompts, "
        f"up to {p['max_tokens']} output tokens, concurrency {p['concurrency']}."
    )


def profile_warnings(profile: str) -> list[str]:
    """Warnings to show before a paid run; benchmark gets an extra explicit one."""
    if profile == "benchmark":
        return [
            "This is the LARGEST profile and will use the most GPU time.",
            "Start with validate, then smoke, then pilot BEFORE this.",
        ]
    return []


def build_env(cfg: dict, run_id: str, app_name: str) -> dict:
    """Child-process env: unique app identity + config the module reads at import.

    Windows Unicode handling (KANBAN-095 smoke failure): the Modal CLI prints
    Unicode (e.g. ``✓ Created app``) which crashes under the cp1252 charmap
    locale. Force UTF-8 on the child so it never dies on its own output.
    """
    env = dict(os.environ)
    env["MODAL_APP_NAME"] = app_name
    env["MODAL_RUN_ID"] = run_id
    env["BENCH_GPU"] = cfg["gpu"]
    env["BENCH_GPU_HOURLY_USD"] = str(cfg["gpu_hourly_rate"])
    env["MODAL_FUNCTION_TIMEOUT"] = str(cfg["function_timeout"])
    env["MODAL_STARTUP_TIMEOUT"] = str(cfg["startup_timeout"])
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _ensure_utf8_stdio() -> None:
    """Make the controller's own console UTF-8-safe (Windows cp1252 default).

    Without this, streaming a child line containing ``✓`` to a cp1252 console
    raises ``UnicodeEncodeError`` in the controller itself, before/while it
    prints the live child output. ``errors="replace"`` guarantees the run never
    dies on an unencodable glyph.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def build_command(cfg: dict, app_name: str, result_path: Path, run_id: str,
                  modal_cmd: str = "modal") -> list[str]:
    """The exact ``modal run`` argv (one child, -n unique app name).

    ``--run-id`` is passed explicitly so the remote benchmark function stages
    carry the actual smoke/pilot/benchmark run ID (never ``unknown``).
    """
    return [
        modal_cmd, "run",
        "-n", app_name,
        str(BENCH_SCRIPT),
        "--run-id", run_id,
        "--model", cfg["model"],
        "--max-model-len", str(cfg["max_model_len"]),
        "--num-prompts", str(cfg["num_prompts"]),
        "--max-tokens", str(cfg["max_tokens"]),
        "--concurrency", str(cfg["concurrency"]),
        "--prompt-len", str(cfg["prompt_len"]),
        "--gpu-memory-utilization", str(cfg.get("gpu_memory_utilization", 0.95)),
        "--max-num-seqs", str(cfg["max_num_seqs"]),
        "--max-num-batched-tokens", str(cfg["max_num_batched_tokens"]),
        "--gpu-hourly-usd", str(cfg["gpu_hourly_rate"]),
        "--server-start-timeout", str(cfg["startup_timeout"]),
        "--benchmark-timeout", str(cfg["benchmark_timeout"]),
        "--fast-boot" if cfg["fast_boot"] else "--no-fast-boot",
        "--result-path", str(result_path),
    ]


def verify_approval(typed: str, run_id: str, ceiling: float) -> bool:
    """Exact approval phrase check — ``RUN <run_id> MAX $<ceiling>``.

    The typed text must match EXACTLY (after stripping whitespace) the phrase
    tied to this run ID and this cost ceiling. A mismatch, partial phrase, or
    blank input is a refusal.
    """
    expected = f"RUN {run_id} MAX {format_usd(ceiling)}"
    return typed.strip() == expected


def approval_prompt(run_id: str, ceiling: float) -> str:
    return f"Type the approval phrase to authorize this run: RUN {run_id} MAX {format_usd(ceiling)}"


def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _read_approval(prompt: str) -> str:
    """Read one typed line; raises on EOF so callers refuse cleanly."""
    try:
        return input(prompt + "\n")
    except EOFError:
        raise


# ---------------------------------------------------------------------------
# Stage parsing
# ---------------------------------------------------------------------------

_STAGE_RE = re.compile(r"LLM_BENCH_STAGE (\d+) (.*?) run=(\S+) t=([\d.]+)")


def parse_stage_line(line: str) -> dict | None:
    """Parse a remote stage line -> {n, name, run_id, t}; None if not a stage."""
    m = _STAGE_RE.search(line)
    if not m:
        return None
    return {"n": int(m.group(1)), "name": m.group(2),
            "run_id": m.group(3), "t": float(m.group(4))}


# ---------------------------------------------------------------------------
# Failure classification — exactly ONE recommended next step
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*\S+"),
]

_MODULE_NAME = re.compile(r"No module named '[^']*'", re.IGNORECASE)


def redact(text: str) -> str:
    """Mask API keys / bearer tokens so log tails never leak secrets."""
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("<redacted>", out)
    return _MODULE_NAME.sub("No module named '<redacted>'", out)


def _has_repeated_lines(text: str, threshold: int = 3) -> bool:
    """Detect a repeated/static log line (e.g. the same traceback over and over)."""
    counts: dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        counts[stripped] = counts.get(stripped, 0) + 1
        if counts[stripped] >= threshold:
            return True
    return False


def classify_failure(log_text: str) -> tuple[str, str]:
    """Classify output/errors -> (category, one recommended next step).

    Order matters: hydration/import first (the observed KANBAN-095 failure),
    then CUDA OOM, model identity, startup-timeout variants, benchmark timeout,
    then auth/rate limits. Exactly one next step is returned.
    """
    text = redact(log_text)
    low = text.lower()

    # 0. Local console / child-process encoding failure (Windows charmap).
    #    E.g. "'charmap' codec can't encode character '\u2713'". This is a LOCAL
    #    console-encoding problem, not a Modal/GPU/model failure.
    if ("charmap" in low or "unicodeencodeerror" in low
            or "unicodedecodeerror" in low
            or "can't encode" in low or "cannot encode" in low
            or "cp1252" in low or "codec can't" in low):
        return ("local_console_encoding",
                "Local console encoding failure (Windows charmap cannot encode "
                "Unicode such as '\u2713'). Fix your terminal/locale or set "
                "PYTHONUTF8=1, then re-run validate before retrying. This is "
                "NOT a GPU/model problem — do not change the GPU.")

    # 1. Import / hydration (the observed prior failure: sibling module absent).
    if ("modulenotfounderror" in low or "importerror" in low
            or "cannot import" in low or "no module named" in low
            or "from vllm_server import" in low):
        return ("hydration_import",
                "Packaging problem: a module was absent on the remote image. "
                "Fix packaging (vllm_server is now explicitly added to the "
                "image) — do NOT change the GPU. Re-run validate first.")

    # 2. CUDA OOM.
    if ("cuda out of memory" in low or "outofmemoryerror" in low
            or ("cuda error" in low and "memory" in low)):
        return ("cuda_oom",
                "CUDA OOM: LOWER max_model_len, max_num_seqs, "
                "max_num_batched_tokens, or concurrency BEFORE upgrading the "
                "GPU. Change one of these at a time, then re-run validate.")

    # 3. Model alias / checkpoint / identifier errors.
    if ("model not found" in low or "repository not found" in low
            or "does not exist" in low
            or "404" in low and "model" in low
            or "revision not found" in low or "snapshot_download" in low
            or ("checkpoint" in low and "failed" in low)
            or "modelnotfound" in low or "invalid model" in low
            or ("served-model-name" in low and "mismatch" in low)):
        return ("model_identity",
                "Model alias/checkpoint error: fix the model identifier "
                "(e.g. the served-model-name alias vs the HF checkpoint). "
                "Do NOT change the GPU.")

    # 4. Startup timeout variants.
    startup_signs = ("startup timeout" in low or "did not become ready" in low
                     or "failed to start" in low or "startup_timeout" in low
                     or ("timed out" in low and "serve" in low))
    if startup_signs:
        if ("loading checkpoint shards" in low or "downloading" in low
                or "%|" in text or "it/s" in low or "shard" in low):
            return ("startup_timeout_downloading",
                    "Startup timed out while model shards were still "
                    "downloading/loading (healthy progress). Consider ONE "
                    "bounded startup-timeout increase (--startup-timeout), "
                    "then re-run the same profile.")
        if _has_repeated_lines(text):
            return ("startup_timeout_static",
                    "Startup timed out with repeated/static log lines (a "
                    "loop, not progress). DIAGNOSE — do not just wait longer. "
                    "Watch the dashboard; if the same traceback repeats, stop "
                    "and change one setting.")
        return ("startup_timeout",
                "Startup timed out. If logs show downloading/shard progress, "
                "increase --startup-timeout once. If logs are static/repeated, "
                "stop and diagnose instead of waiting longer.")

    # 5. Benchmark subprocess failure (nonzero vllm bench serve returncode).
    if ("benchmark_failure" in low or "vllm bench serve failed" in low
            or "produced no result file" in low
            or "unreadable result json" in low):
        return ("benchmark_failure",
                "The vllm bench serve subprocess failed (nonzero exit). "
                "Review the redacted log tail, fix the benchmark invocation, "
                "and re-run validate before retrying.")

    # 6. Benchmark timeout.
    if ("vllm bench serve exceeded" in low or "benchmark_serving exceeded" in low
            or "timeoutexpired" in low
            or "benchmark_timeout" in low or "benchmark timeout" in low):
        return ("benchmark_timeout",
                "Benchmark subprocess timed out: reduce prompts, output "
                "tokens, or concurrency (--num-prompts / --max-tokens / "
                "--concurrency). One change at a time.")

    # 7. Auth / rate limits.
    if ("401" in low or "403" in low or "429" in low
            or "unauthorized" in low or "authentication" in low
            or "rate limit" in low or "insufficient" in low
            or "quota" in low):
        return ("auth_rate_limit",
                "Authentication or rate limit: STOP and fix your Modal "
                "credentials / limits. Never share or print keys.")

    return ("unknown",
            "No clear pattern in the log. Review the log tail, change ONE "
            "setting at a time, and re-run validate before retrying.")


# ---------------------------------------------------------------------------
# Emergency stop helpers
# ---------------------------------------------------------------------------

_APP_ID_PATTERNS = [
    # Observed URL: https://modal.com/apps/grantmooslin/main/ap-<id>
    # The app ID is ALWAYS the ap-... component; account ("grantmooslin") and
    # environment ("main") path segments must NEVER be extracted.
    re.compile(r"modal\.com/apps/[^/\s]*/[^/\s]*/(ap-[A-Za-z0-9_-]+)"),
    re.compile(r"\b(ap-[A-Za-z0-9_-]+)\b"),
    re.compile(r"App ID[:=]\s*(ap-[A-Za-z0-9_-]+)"),
    re.compile(r"app_id[:=]\s*(ap-[A-Za-z0-9_-]+)"),
]


def find_app_id(log_text: str) -> str | None:
    """Extract the unique app ID from Modal output if possible."""
    for pat in _APP_ID_PATTERNS:
        m = pat.search(log_text)
        if m:
            return m.group(1)
    return None


def stop_target(app_id: str | None, app_name: str) -> str | None:
    """Prefer the exact app ID; else ONLY an explicitly-unique app name.

    Refuses (returns None) when no ID exists AND the name is the shared/generic
    default — we must never stop an app by a name we did not generate.
    """
    if app_id:
        return app_id
    if app_name and app_name != _GENERIC_APP_NAME:
        return app_name
    return None


def build_stop_command(target: str, modal_cmd: str = "modal") -> list[str]:
    """``modal app stop <exact-id-or-unique-name> --yes`` (installed syntax)."""
    return [modal_cmd, "app", "stop", target, "--yes"]


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------


def _open_log(dirpath: Path, run_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return dirpath / f"run-{run_id}-{stamp}.log"


def run_one(cfg: dict, run_id: str, app_name: str, results_dir: Path,
            modal_cmd: str = "modal",
            popen_factory=subprocess.Popen,
            input_fn=input, isatty_fn=_is_interactive,
            interrupt: BaseException | None = None) -> dict:
    """Launch the single ``modal run`` child, tee + stream, observe stages.

    Returns a status dict:
      {status: "success"|"failed"|"stopped", run_id, app_name, exit_code,
       stage_progress, log_path, result/error fields...}

    ``interrupt`` is a test seam: when provided (truthy exception), it is
    raised after the first line is read, simulating Ctrl+C mid-stream.
    """
    dirpath = results_dir / run_id
    dirpath.mkdir(parents=True, exist_ok=True)
    log_path = _open_log(dirpath, run_id)
    result_path = dirpath / "result.json"
    status_path = dirpath / "status.json"
    env = build_env(cfg, run_id, app_name)
    cmd = build_command(cfg, app_name, result_path, run_id, modal_cmd=modal_cmd)

    stages_seen: dict[int, dict] = {}
    app_id: str | None = None
    log_lines: list[str] = []

    proc = popen_factory(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace", env=env,
    )
    started = time.monotonic()
    print(f"[controller] launched one child: {' '.join(cmd)}")
    print(f"[controller] log: {log_path}   result: {result_path}")

    stop_refused_status: dict | None = None
    with open(log_path, "a", encoding="utf-8") as logf:
        try:
            for raw in proc.stdout:  # stream child stdout live
                line = raw.rstrip("\n")
                log_lines.append(line)
                logf.write(raw)
                logf.flush()
                print(line, flush=True)
                stage = parse_stage_line(line)
                if stage:
                    stages_seen[stage["n"]] = stage
                app_id = app_id or find_app_id(line)
                if interrupt is not None:
                    raise interrupt
        except KeyboardInterrupt:
            stop_refused_status = _emergency_stop(cfg, run_id, app_name, dirpath,
                                                   log_path, status_path, log_lines,
                                                   stages_seen, app_id, proc,
                                                   modal_cmd, input_fn)
            return stop_refused_status
        except BaseException as exc:  # test seam: injected interrupt/exception
            return _fail(cfg, run_id, app_name, dirpath, log_path, status_path,
                         log_lines, stages_seen, proc,
                         error=f"controller stream error: {exc}")
        finally:
            if stop_refused_status is not None and stop_refused_status.get("status") == "stop_refused":
                # Confirmation was refused: the child was intentionally left
                # running. Don't block the controller waiting for it.
                code = None
                elapsed = time.monotonic() - started
            else:
                code = proc.wait()
                elapsed = time.monotonic() - started

    log_text = "\n".join(log_lines)

    # Success REQUIRES the parsed result JSON to report ok=True/status=success.
    # A child exit code 0 plus a result-file exists is NOT sufficient — the
    # remote function can exit cleanly while result.json reports failure
    # (e.g. a nonzero vllm bench serve returncode -> ok=false/benchmark_failure).
    if code == 0 and result_path.exists():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            result = {}
        if result.get("ok") is True and result.get("status") == "success":
            status = {
                "status": "success",
                "run_id": run_id,
                "app_name": app_name,
                "exit_code": code,
                "elapsed_sec": round(elapsed, 1),
                "stage_progress": {k: v["n"] for k, v in stages_seen.items()},
                "stages_reached": max(stages_seen) if stages_seen else 0,
                "app_id": app_id,
                "log_path": str(log_path),
                "result_path": str(result_path),
                "result": result,
            }
            _write_status(status_path, status)
            return status
        return _fail(cfg, run_id, app_name, dirpath, log_path, status_path,
                     log_lines, stages_seen, proc, exit_code=code,
                     error=result.get("error") or "benchmark result reported failure",
                     category=result.get("error_category") or "benchmark_failure")

    return _fail(cfg, run_id, app_name, dirpath, log_path, status_path,
                 log_lines, stages_seen, proc, exit_code=code,
                 error="benchmark did not produce a result file" if code == 0
                       else f"modal run exited with code {code}")


def _fail(cfg: dict, run_id: str, app_name: str, dirpath: Path, log_path: Path,
          status_path: Path, log_lines: list[str], stages_seen: dict,
          proc, exit_code: int | None = None,
          error: str = "", category: str = "") -> dict:
    log_text = "\n".join(log_lines)
    if category:
        # Propagate the exact category, but still derive the recommended next
        # step from the available log/error text so the operator gets a
        # concrete action (never just "something failed").
        _, next_step = classify_failure(log_text + "\n" + error)
    else:
        category, next_step = classify_failure(log_text + "\n" + error)
    tail = redact("\n".join(log_lines[-50:]))
    status = {
        "status": "failed",
        "run_id": run_id,
        "app_name": app_name,
        "exit_code": exit_code,
        "error": error,
        "error_category": category,
        "next_step": next_step,
        "stage_progress": {k: v["n"] for k, v in stages_seen.items()},
        "stages_reached": max(stages_seen) if stages_seen else 0,
        "log_path": str(log_path),
        "log_tail_redacted": tail,
    }
    _write_status(status_path, status)
    return status


def _emergency_stop(cfg: dict, run_id: str, app_name: str, dirpath: Path,
                    log_path: Path, status_path: Path, log_lines: list[str],
                    stages_seen: dict, app_id: str | None, proc,
                    modal_cmd: str, input_fn=input) -> dict:
    """Confirmed emergency stop: explain, confirm, stop ONLY this app."""
    print("\n[controller] EMERGENCY STOP — stopping now immediately terminates "
          "the containers and CANNOT resume the app.")
    target = stop_target(app_id, app_name)
    if target is None:
        print("[controller] Cannot identify the exact app to stop (no app ID "
              "and no unique name). NOT stopping anything.")
        print("[controller] Dashboard: https://modal.com/apps — check the "
              "running app's ID, then run manually:")
        print(f"[controller]     {modal_cmd} app stop <APP_ID> --yes")
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        status = {
            "status": "stopped_ambiguous",
            "run_id": run_id,
            "app_name": app_name,
            "note": "emergency stop refused: app identity ambiguous",
            "stage_progress": {k: v["n"] for k, v in stages_seen.items()},
            "log_path": str(log_path),
        }
        _write_status(status_path, status)
        return status

    try:
        confirm = input_fn(
            f"Type STOP {run_id} to confirm stopping app '{target}': ")
    except EOFError:
        confirm = ""
    if confirm.strip() != f"STOP {run_id}":
        print("[controller] Confirmation did not match — NOT stopping anything.")
        print("[controller] The run continues. Press Ctrl+C again and type the "
              "exact phrase to stop.")
        status = {"status": "stop_refused", "run_id": run_id,
                  "app_name": app_name, "log_path": str(log_path)}
        _write_status(status_path, status)
        return status

    stop_cmd = build_stop_command(target, modal_cmd=modal_cmd)
    print(f"[controller] stopping current app ONLY: {' '.join(stop_cmd)}")
    stop_error: str | None = None
    try:
        result = subprocess.run(stop_cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=60)
        ok = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        ok = False
        result = None
        stop_error = str(exc)
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()

    if ok:
        print("[controller] app stop succeeded — verify Live Apps returns to 0 "
              "in the Modal dashboard.")
    else:
        detail = (result.stdout + result.stderr)[-500:] if result else stop_error
        print(f"[controller] app stop reported failure: {detail[-500:]}")
        print("[controller] Dashboard: https://modal.com/apps — verify the "
              "app actually stopped; stop manually if needed.")
    status = {
        "status": "stopped",
        "run_id": run_id,
        "app_name": app_name,
        "app_id": app_id,
        "stop_target": target,
        "stop_ok": ok,
        "stage_progress": {k: v["n"] for k, v in stages_seen.items()},
        "log_path": str(log_path),
    }
    _write_status(status_path, status)
    return status


def _write_status(status_path: Path, status: dict) -> None:
    status_path.write_text(json.dumps(status, indent=2, default=str),
                           encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--profile", choices=sorted(PROFILES), default="validate",
                        help="validate (default, free) | smoke | pilot | benchmark")
    parser.add_argument("--enable-paid-run", action="store_true",
                        help="REQUIRED for smoke/pilot/benchmark — explicitly "
                             "authorize a paid Modal run")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the resolved plan + command, launch nothing")
    parser.add_argument("--gpu", default="L4", help="Modal GPU (L4/A10G/L40S/H100)")
    parser.add_argument("--gpu-hourly-rate", type=float, default=0.50,
                        help="GPU hourly rate for the cost ceiling ($/hr)")
    parser.add_argument("--model", default="Qwen/Qwen3-8B",
                        help="HF checkpoint the vLLM server serves")
    parser.add_argument("--max-model-len", type=int, default=None)
    parser.add_argument("--num-prompts", type=int, default=None)
    parser.add_argument("--prompt-len", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--max-num-seqs", type=int, default=None)
    parser.add_argument("--max-num-batched-tokens", type=int, default=None)
    parser.add_argument("--startup-timeout", type=int, default=None)
    parser.add_argument("--benchmark-timeout", type=int, default=None)
    parser.add_argument("--function-timeout", type=int, default=None)
    parser.add_argument("--fast-boot", action="store_true",
                        help="keep --enforce-eager fast boot (default)")
    parser.add_argument("--no-fast-boot", dest="fast_boot", action="store_false",
                        help="disable --enforce-eager for max throughput")
    parser.set_defaults(fast_boot=True)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
                        help="where run logs + result/status JSON are written")
    parser.add_argument("--modal-cmd", default="modal",
                        help="Modal CLI executable (default 'modal')")
    return parser


def _apply_flag_defaults(parser: argparse.ArgumentParser, args: argparse.Namespace):
    """Fill None-valued config flags from the profile defaults."""
    base = PROFILES[args.profile]
    for key in ("max_model_len", "num_prompts", "prompt_len", "max_tokens",
                "concurrency", "max_num_seqs", "max_num_batched_tokens",
                "startup_timeout", "benchmark_timeout", "function_timeout"):
        if getattr(args, key) is None:
            setattr(args, key, base[key])
    return args


def main_with_args(argv: list[str]) -> int:
    _ensure_utf8_stdio()   # Windows cp1252 would crash printing child Unicode
    parser = build_parser()
    args = parser.parse_args(argv)
    args = _apply_flag_defaults(parser, args)
    cfg = resolve_config(args)
    profile = args.profile
    charges = PROFILES[profile]["charges"]

    print("=" * 72)
    print(explain_profile(profile))
    print("=" * 72)

    if charges:
        print("This profile INCURS CHARGES on Modal GPUs.")
    else:
        print("This profile is FREE — no paid compute is scheduled.")

    ceiling = compute_cost_ceiling(cfg["gpu_hourly_rate"], cfg["function_timeout"])
    print(f"\nResolved configuration:")
    for k in ("gpu", "model", "max_model_len", "num_prompts", "prompt_len",
              "max_tokens", "concurrency", "max_num_seqs",
              "max_num_batched_tokens", "startup_timeout", "benchmark_timeout",
              "function_timeout", "gpu_hourly_rate"):
        print(f"  {k:<22} {cfg[k]}")
    print(f"  {'cost ceiling (conservative)':<22} {format_usd(ceiling)}")
    print("  Healthy progress: stages 1..8 advance with the run ID + elapsed "
          "seconds; expected dashboard state is ONE live app, ONE call, ONE "
          "container.")
    print("  Stop conditions: repeated identical tracebacks, unexpected extra "
          "containers, no stage progress past the deadline, OOM, or repeated "
          "vLLM startup. After completion verify Live Apps returns to 0.")

    if profile == "validate":
        print("\n[validate] No paid compute. Launching nothing. To run, use "
              "--profile smoke --enable-paid-run (see README runbook).")
        return 0

    if args.dry_run:
        print("\n[dry-run] NOT launching. Resolved command would be:")
        print("  ", " ".join(build_command(cfg, make_app_name("dry-run-xxxx"),
                                           args.results_dir / "x" / "result.json",
                                           "dry-run-xxxx",
                                           modal_cmd=args.modal_cmd)))
        return 0

    # ---- Paid execution gate ------------------------------------------------
    if not args.enable_paid_run:
        print("\nREFUSED: --enable-paid-run is required for paid profiles. "
              "No Modal workload was launched. Add the flag and an exact typed "
              "approval to run.")
        return 1

    if not _is_interactive():
        print("\nREFUSED: approval requires an interactive terminal (piped/"
              "noninteractive stdin). No Modal workload was launched.")
        return 1

    if not shutil.which(args.modal_cmd):
        print(f"\nREFUSED: Modal CLI '{args.modal_cmd}' not found on PATH. "
              "Install Modal (`pip install modal`) before running.")
        return 1

    for warning in profile_warnings(profile):
        print(f"\n[warning] {warning}")

    run_id = make_run_id(profile)
    app_name = make_app_name(run_id)
    print(f"\nThis run will use the unique identity: run={run_id} app={app_name}")
    print(f"One `{args.modal_cmd} run` child max; zero retries (retries=0 in "
          "Modal config).")
    print("Expected dashboard state: one live app, one call, one container.")

    phrase = approval_prompt(run_id, ceiling)
    try:
        typed = _read_approval(phrase)
    except EOFError:
        print("\nREFUSED: approval input ended (EOF) before a valid phrase. "
              "No Modal workload was launched.")
        return 1
    except KeyboardInterrupt:
        print("\n\nCANCELLED: approval interrupted. No Modal workload was launched.")
        return 1
    if not verify_approval(typed, run_id, ceiling):
        print(f"\nREFUSED: approval did not match '{phrase}'. No Modal "
              "workload was launched. Rerun to generate a fresh run ID.")
        return 1

    print("\nApproval accepted. The run-specific approval is NEVER stored or "
          "reused — any later attempt needs its own run ID + typed phrase.")
    status = run_one(cfg, run_id, app_name, args.results_dir,
                     modal_cmd=args.modal_cmd)
    print(f"\n[controller] run {run_id} -> {status['status']}")
    print(f"[controller] status JSON: {args.results_dir / run_id / 'status.json'}")
    if status["status"] == "success":
        print("[controller] verify Live Apps returns to 0 in the Modal "
              "dashboard; then compare with scripts/eval/benchmark_openrouter.py")
        return 0
    if status["status"] == "failed":
        if status.get("error_category"):
            print(f"[controller] failure category: {status['error_category']}")
        if status.get("error"):
            print(f"[controller] error: {status['error']}")
        print(f"[controller] next step: {status['next_step']}")
        return 1
    return 1


def main() -> None:
    raise SystemExit(main_with_args(sys.argv[1:]))


if __name__ == "__main__":
    main()