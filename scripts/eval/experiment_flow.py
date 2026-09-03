#!/usr/bin/env python3
"""Interactive asks-questions experiment-flow wizard (KANBAN-109).

A human-in-the-loop controller for the **OpenRouter vs Modal-hosted vLLM
(Qwen3-8B) cost comparison**. It orchestrates EXISTING machinery only — the
Modal one-shot benchmark controller (``scripts/eval/guided_vllm_benchmark.py``,
read-only base) and the docclass eval runner
(``scripts/eval/run_langfuse_docclass_eval.py``) — never editing either.

Four phases, each a thin interactive wrapper over pure, testable logic:

1. **ASK** — collect every knob (legs, keys via ``getpass`` — never echoed,
   model ids, prompt version, dataset source + HF knobs, sample/seed/
   concurrency, GPU + live hourly rate, spend cap, experiment names);
   validate every answer and re-prompt on invalid input.
2. **PREVIEW** — print the exact commands per leg and phase (cold smoke,
   warm-up, warm sample, OpenRouter baseline) with their env knobs and an
   estimated maximum spend; require an explicit y/N confirmation before
   EVERY paid step.
3. **RUN** — execute steps via subprocess with per-phase env switching
   (``OPENROUTER_BASE_URL`` / ``OPENROUTER_API_KEY`` flips, ``SERVING_PHASE``
   cold|warm|unset, ``BENCH_*`` GPU knobs), stream output to the console and
   a per-step log, enforce the spend cap, and allow a clean stop between
   phases.
4. **COMPARE** — read paired records from ``reports/experiment_log.jsonl``,
   verify dataset + prompt fingerprints match (reject mismatches), then print
   per-input/output/total-token cost for both sides, a cold-start amortization
   line, and a break-even sketch. All scoring math goes through the
   **llm-dojo-scoring** package (63d73d3) accessed ONLY at runtime via a
   subprocess shim that prepends the package dir to ``PYTHONPATH`` — the
   module never imports it, never reads its source, and never fabricates a
   number (None / an unknown marker with the reason whenever a value is
   unavailable).

Usage:
    python scripts/eval/experiment_flow.py                # full wizard
    python scripts/eval/experiment_flow.py --dry-run      # ask + preview only

The default scoring-package path is
``C:/Users/grant/fork-sync/worktrees/cost-comparison-scoring``; override with
``--dojo-scoring-path`` or ``DOJO_SCORING_PATH``.
"""

from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.experiment_log import default_jsonl_path
from src.openrouter_utils import DEFAULT_OPENROUTER_BASE_URL
from src.prompts import list_prompts
from src.serving_meta import (
    MODAL_PROVIDER,
    OPENROUTER_PROVIDER,
    OTHER_PROVIDER,
    provider_from_base_url,
)
from src.taxonomy import load_taxonomy

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDED_BENCH_SCRIPT = REPO_ROOT / "scripts" / "eval" / "guided_vllm_benchmark.py"
DOC_CLASS_EVAL_SCRIPT = REPO_ROOT / "scripts" / "eval" / "run_langfuse_docclass_eval.py"

DEFAULT_DOJO_SCORING_PATH = r"C:/Users/grant/fork-sync/worktrees/cost-comparison-scoring"

# ---------------------------------------------------------------------------
# Config schema + defaults
# ---------------------------------------------------------------------------

VALID_LEGS = ("openrouter", "modal", "both")
VALID_DATASET_SOURCES = ("braintrust", "local", "hf")
VALID_GPUS = ("L4", "A10G", "L40S", "H100")

DEFAULT_MODEL_OPENROUTER = "qwen/qwen3-8b"
DEFAULT_MODEL_MODAL = "Qwen/Qwen3-8B"
DEFAULT_PROMPT_VERSION = "sorter_v3"
DEFAULT_HF_DATASET = "Lucius-Morningstar/mailroom-corpus"
DEFAULT_HF_CONFIG = "ground_truth"
DEFAULT_GPU = "L4"
DEFAULT_GPU_HOURLY_USD = 0.50
DEFAULT_SAMPLE = 40
DEFAULT_SEED = 42
DEFAULT_MAX_CONCURRENCY = 8
DEFAULT_SPEND_CAP_USD = 5.00

# Conservative doc-eval spend ceiling inputs (mirror the docclass runner's
# own defaults: 100k max input chars ~= 25k tokens, 4096 max output tokens).
DOC_MAX_INPUT_CHARS = 100_000
DOC_MAX_OUTPUT_TOKENS = 4096

# Guided benchmark function timeouts (seconds) at base 6552289 — the wizard
# estimates spend from the same ceiling formula guided_vllm_benchmark uses.
GUIDED_FUNCTION_TIMEOUTS = {"smoke": 1200, "pilot": 1800}

PHASE_COLD = "cold"
PHASE_WARM = "warm"
PHASE_OPENROUTER = "openrouter_baseline"

KIND_GUIDED_SMOKE = "modal_cold_smoke"
KIND_GUIDED_PILOT = "modal_warmup"
KIND_DOC_EVAL = "docclass_eval"

_NAME_RE = "^[A-Za-z0-9._-]+$"


@dataclass(frozen=True)
class Step:
    id: str
    leg: str
    phase: str
    kind: str
    paid: bool
    description: str
    cmd: list[str]
    env: dict[str, str]
    est_max_spend_usd: float | None


def _validate_name(value: object) -> str | None:
    if not str(value or "").strip():
        return "a non-empty value is required"
    if not re.match(_NAME_RE, str(value).strip()):
        return "only letters, digits, '.', '_' and '-' are allowed"
    return None


_MODEL_SLUG_RE = "^[A-Za-z0-9_.:/+-]+$"


def _validate_model_slug(value: object, label: str) -> str | None:
    if not str(value or "").strip():
        return f"{label} is required"
    if not re.match(_MODEL_SLUG_RE, str(value).strip()):
        return f"{label} contains unsupported characters"
    return None


def validate_leg(value: object) -> str | None:
    if str(value or "") not in VALID_LEGS:
        return f"leg must be one of {VALID_LEGS}"
    return None


def validate_dataset_source(value: object) -> str | None:
    if str(value or "") not in VALID_DATASET_SOURCES:
        return f"dataset source must be one of {VALID_DATASET_SOURCES}"
    return None


def validate_model_openrouter(value: object) -> str | None:
    err = _validate_model_slug(value, "OpenRouter model slug")
    if err:
        return err
    if "/" not in str(value) and ":" not in str(value):
        return "an OpenRouter model slug is expected (e.g. qwen/qwen3-8b)"
    return None


def validate_model_modal(value: object) -> str | None:
    err = _validate_model_slug(value, "Modal HF checkpoint")
    if err:
        return err
    if "/" not in str(value):
        return "a Hugging Face checkpoint id is expected (e.g. Qwen/Qwen3-8B)"
    return None


def validate_prompt_version(value: object) -> str | None:
    version = str(value or "").strip()
    if not version:
        return "a prompt version is required"
    if version not in list_prompts():
        return f"unknown prompt version {version!r}"
    return None


def validate_sample(value: object) -> str | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "sample size must be an integer"
    if n < 0 or n > 100_000:
        return "sample size must be between 0 (all rows) and 100000"
    return None


def validate_seed(value: object) -> str | None:
    try:
        int(value)
    except (TypeError, ValueError):
        return "seed must be an integer"
    return None


def validate_max_concurrency(value: object) -> str | None:
    if value in ("", None):
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "max concurrency must be an integer, or blank for auto"
    if n < 1 or n > 64:
        return "max concurrency must be between 1 and 64"
    return None


def validate_gpu(value: object) -> str | None:
    if str(value or "").upper() not in VALID_GPUS:
        return f"GPU must be one of {VALID_GPUS}"
    return None


def validate_hourly_rate(value: object) -> str | None:
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "hourly rate must be a number"
    if not math.isfinite(rate) or rate <= 0:
        return "hourly rate must be a positive number"
    if rate > 10_000:
        return "hourly rate looks implausibly large"
    return None


def validate_spend_cap(value: object) -> str | None:
    try:
        cap = float(value)
    except (TypeError, ValueError):
        return "spend cap must be a number"
    if not math.isfinite(cap) or cap <= 0:
        return "spend cap must be a positive number"
    if cap > 100_000:
        return "spend cap looks implausibly large"
    return None


def validate_hf_dataset(value: object) -> str | None:
    if not str(value or "").strip():
        return "an HF dataset id is required (e.g. Lucius-Morningstar/mailroom-corpus)"
    return None


def validate_hf_config(value: object) -> str | None:
    if not str(value or "").strip():
        return "an HF config name is required (e.g. ground_truth)"
    return None


def validate_modal_endpoint(value: object) -> str | None:
    url = str(value or "").strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return "the Modal endpoint must be a http(s) URL"
    return None


def validate_config(cfg: dict) -> list[str]:
    """Return a list of config problems; an empty list means the config is valid."""
    problems: list[str] = []

    def add(err: str | None) -> None:
        if err:
            problems.append(err)

    add(validate_leg(cfg.get("leg")))
    leg = cfg.get("leg")
    if leg in ("openrouter", "both"):
        if not str(cfg.get("openrouter_api_key") or "").strip():
            problems.append("openrouter_api_key is required for this leg")
    if leg in ("modal", "both"):
        add(validate_modal_endpoint(cfg.get("modal_endpoint_url")))
        if not str(cfg.get("modal_api_token") or "").strip():
            problems.append("modal_api_token is required for this leg")
    add(validate_model_openrouter(cfg.get("api_model")))
    add(validate_model_modal(cfg.get("modal_model")))
    add(validate_prompt_version(cfg.get("prompt_version")))
    add(validate_dataset_source(cfg.get("dataset_source")))
    if cfg.get("dataset_source") == "hf":
        add(validate_hf_dataset(cfg.get("hf_dataset")))
        add(validate_hf_config(cfg.get("hf_config")))
    add(validate_sample(cfg.get("sample")))
    add(validate_seed(cfg.get("seed")))
    add(validate_max_concurrency(cfg.get("max_concurrency")))
    if leg in ("modal", "both"):
        add(validate_gpu(cfg.get("gpu")))
        add(validate_hourly_rate(cfg.get("gpu_hourly_usd")))
    add(validate_spend_cap(cfg.get("spend_cap_usd")))
    add(validate_experiment_name(cfg.get("experiment_name_api")))
    add(validate_experiment_name(cfg.get("experiment_name_modal")))
    if leg == "both" and str(cfg.get("experiment_name_api")) == str(cfg.get("experiment_name_modal")):
        problems.append("api and modal experiment names must differ")
    return problems


def validate_experiment_name(value: object) -> str | None:
    return _validate_name(value)


def default_experiment_name(cfg: dict, leg: str) -> str:
    if leg == "modal":
        return f"{str(cfg['modal_model']).split('/')[-1]}_{cfg['prompt_version']}_docclass_langfuse"
    return f"{str(cfg['api_model']).split('/')[-1]}_{cfg['prompt_version']}_docclass_langfuse"


def _valid_cfg_defaults() -> dict:
    cfg = {
        "leg": "both",
        "openrouter_api_key": "sk-or-test",
        "modal_endpoint_url": "https://ws--entity-vllm-serve.modal.run/v1",
        "modal_api_token": "tk-modal-test",
        "api_model": DEFAULT_MODEL_OPENROUTER,
        "modal_model": DEFAULT_MODEL_MODAL,
        "prompt_version": DEFAULT_PROMPT_VERSION,
        "dataset_source": "hf",
        "hf_dataset": DEFAULT_HF_DATASET,
        "hf_config": DEFAULT_HF_CONFIG,
        "hf_revision": "",
        "sample": DEFAULT_SAMPLE,
        "seed": DEFAULT_SEED,
        "max_concurrency": DEFAULT_MAX_CONCURRENCY,
        "gpu": DEFAULT_GPU,
        "gpu_hourly_usd": DEFAULT_GPU_HOURLY_USD,
        "spend_cap_usd": DEFAULT_SPEND_CAP_USD,
        "experiment_name_api": None,
        "experiment_name_modal": None,
    }
    cfg["experiment_name_api"] = default_experiment_name(cfg, "openrouter")
    cfg["experiment_name_modal"] = default_experiment_name(cfg, "modal")
    return cfg


def _resolve_experiment_name(cfg: dict, leg: str) -> str:
    key = "experiment_name_api" if leg == "openrouter" else "experiment_name_modal"
    value = cfg.get(key)
    if value:
        return str(value)
    return default_experiment_name(cfg, leg)


# ---------------------------------------------------------------------------
# ASK phase — interactive collection over the validators
# ---------------------------------------------------------------------------


def _ask(prompt: str, default: str, input_fn, validator, transform) -> object:
    while True:
        hint = f" [{default}]" if default not in ("", None) else ""
        raw = input_fn(f"{prompt}{hint}: ")
        if raw.strip() == "" and default not in ("", None):
            raw = str(default)
        err = validator(raw)
        if err is None:
            return transform(raw)
        print(f"  invalid: {err} — please try again.")


def _ask_choice(prompt: str, choices: tuple[str, ...], input_fn, default: str) -> str:
    while True:
        raw = input_fn(f"{prompt} {choices} [{default}]: ")
        if raw.strip() == "":
            raw = default
        if raw in choices:
            return raw
        print(f"  invalid: expected one of {choices} — please try again.")


def _ask_secret(prompt: str, getpass_fn) -> str:
    while True:
        value = getpass_fn(prompt)
        if value.strip():
            return value
        print("  invalid: a non-empty secret is required.")


def ask_config(input_fn=input, getpass_fn=getpass.getpass) -> dict:
    """Ask every knob; validate each answer and re-prompt on invalid input.

    Keys are collected via ``getpass`` and are never echoed to the terminal.
    """
    cfg = _valid_cfg_defaults()
    cfg["leg"] = _ask_choice("Experiment legs", VALID_LEGS, input_fn, "both")

    if cfg["leg"] in ("openrouter", "both"):
        cfg["openrouter_api_key"] = _ask_secret("OpenRouter API key (hidden)", getpass_fn)
    if cfg["leg"] in ("modal", "both"):
        cfg["modal_endpoint_url"] = _ask(
            "Modal vLLM endpoint URL", "", input_fn, validate_modal_endpoint, str)
        cfg["modal_api_token"] = _ask_secret(
            "Modal vLLM API token (hidden — used as OPENROUTER_API_KEY toward Modal)", getpass_fn)

    cfg["api_model"] = _ask("OpenRouter model slug", DEFAULT_MODEL_OPENROUTER,
                            input_fn, validate_model_openrouter, str)
    cfg["modal_model"] = _ask("Modal HF checkpoint", DEFAULT_MODEL_MODAL,
                              input_fn, validate_model_modal, str)
    cfg["prompt_version"] = _ask("Prompt version", DEFAULT_PROMPT_VERSION,
                                 input_fn, validate_prompt_version, str)
    cfg["dataset_source"] = _ask_choice("Dataset source", VALID_DATASET_SOURCES,
                                        input_fn, "hf")
    if cfg["dataset_source"] == "hf":
        cfg["hf_dataset"] = _ask("HF dataset", DEFAULT_HF_DATASET,
                                 input_fn, validate_hf_dataset, str)
        cfg["hf_config"] = _ask("HF ground-truth config", DEFAULT_HF_CONFIG,
                                input_fn, validate_hf_config, str)
        cfg["hf_revision"] = _ask("HF revision (blank = default)", "",
                                  input_fn, lambda v: None, str)
    cfg["sample"] = _ask("Sample size (0 = all rows)", str(DEFAULT_SAMPLE),
                         input_fn, validate_sample, int)
    cfg["seed"] = _ask("Seed", str(DEFAULT_SEED), input_fn, validate_seed, int)
    cfg["max_concurrency"] = _ask("Max concurrency (blank = auto)", "",
                                  input_fn, validate_max_concurrency,
                                  lambda raw: None if raw.strip() == "" else int(raw))
    if cfg["leg"] in ("modal", "both"):
        cfg["gpu"] = _ask("GPU", DEFAULT_GPU, input_fn,
                          lambda v: validate_gpu(v), lambda v: str(v).upper())
        cfg["gpu_hourly_usd"] = _ask("GPU hourly rate (USD, live)", str(DEFAULT_GPU_HOURLY_USD),
                                     input_fn, validate_hourly_rate, float)
    cfg["spend_cap_usd"] = _ask("Spend cap (USD)", str(DEFAULT_SPEND_CAP_USD),
                                input_fn, validate_spend_cap, float)
    cfg["experiment_name_api"] = _ask("OpenRouter experiment name",
                                      default_experiment_name(cfg, "openrouter"),
                                      input_fn, validate_experiment_name, str)
    cfg["experiment_name_modal"] = _ask("Modal experiment name",
                                        default_experiment_name(cfg, "modal"),
                                        input_fn, validate_experiment_name, str)

    problems = validate_config(cfg)
    if problems:
        raise ValueError("config validation failed after prompting: " + "; ".join(problems))
    return cfg


# ---------------------------------------------------------------------------
# Secret handling + redaction
# ---------------------------------------------------------------------------


def secret_values(cfg: dict) -> tuple[str, ...]:
    """Every getpass-collected value in the config (never echoed, always redacted)."""
    out: list[str] = []
    for key in ("openrouter_api_key", "modal_api_token"):
        value = str(cfg.get(key) or "")
        if value.strip():
            out.append(value)
    return tuple(out)


_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*\S+"),
]


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """Mask API keys / bearer tokens and any configured secret value."""
    out = str(text)
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("<redacted>", out)
    for value in secrets:
        if value:
            out = out.replace(value, "<redacted>")
    return out


def redacted_env(env: dict, secrets: tuple[str, ...] = ()) -> dict:
    """Copy an env map with secret values masked for display."""
    return {key: redact(str(value), secrets) for key, value in env.items()}


# ---------------------------------------------------------------------------
# Plan building — commands, per-phase env maps, spend estimates
# ---------------------------------------------------------------------------


def _guided_ceiling(cfg: dict, profile: str) -> float:
    timeout = GUIDED_FUNCTION_TIMEOUTS[profile]
    return math.ceil(cfg["gpu_hourly_usd"] * timeout / 3600.0 * 100) / 100


def estimate_doc_eval_max_spend(cfg: dict, model: str) -> float | None:
    """Conservative doc-eval ceiling: sample x max tokens x taxonomy price.

    Returns None (honestly unknown) when the sample is "all rows" (sample 0)
    or the model has no price in the local taxonomy cost table — the caller
    then treats the cap as unenforceable and requires explicit approval.
    """
    sample = int(cfg.get("sample") or 0)
    if sample <= 0:
        return None
    prices = (load_taxonomy().get("cost_models") or {}).get(model)
    if not isinstance(prices, dict):
        return None
    input_price = prices.get("input_per_million")
    output_price = prices.get("output_per_million")
    if not input_price or not output_price:
        return None
    est_input_tokens = sample * (DOC_MAX_INPUT_CHARS / 4)
    est_output_tokens = sample * DOC_MAX_OUTPUT_TOKENS
    est = (est_input_tokens * float(input_price) + est_output_tokens * float(output_price)) / 1_000_000
    return round(est, 2)


def estimate_max_spend(step: Step, cfg: dict) -> float | None:
    """Maximum spend a step can incur, by kind (GPU ceiling or token ceiling)."""
    if step.kind == KIND_GUIDED_SMOKE:
        return _guided_ceiling(cfg, "smoke")
    if step.kind == KIND_GUIDED_PILOT:
        return _guided_ceiling(cfg, "pilot")
    if step.kind == KIND_DOC_EVAL:
        model = cfg["modal_model"] if step.leg in ("modal", "both") and step.phase != PHASE_OPENROUTER else cfg["api_model"]
        return estimate_doc_eval_max_spend(cfg, model)
    return None


def build_guided_command(cfg: dict, profile: str, *, python_exe: str | None = None,
                         dry_run: bool = False) -> list[str]:
    """The wizard's invocation of the guided Modal benchmark controller.

    ``--enable-paid-run`` is passed for the charging profiles (smoke/pilot);
    ``--dry-run`` downgrades it to a plan-only launch (no Modal workload).
    """
    python_exe = python_exe or sys.executable
    cmd = [python_exe, str(GUIDED_BENCH_SCRIPT), "--profile", profile,
           "--gpu", cfg["gpu"], "--gpu-hourly-rate", str(cfg["gpu_hourly_usd"])]
    if profile in ("smoke", "pilot"):
        cmd.append("--enable-paid-run")
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def build_docclass_command(cfg: dict, *, experiment_name: str, model: str,
                           python_exe: str | None = None) -> list[str]:
    """The docclass eval runner invocation for one side of the comparison.

    Both legs share sample/seed/prompt/dataset so the dataset fingerprint
    matches and the records are legitimately pairable.
    """
    python_exe = python_exe or sys.executable
    cmd = [python_exe, str(DOC_CLASS_EVAL_SCRIPT),
           "--prompt-version", cfg["prompt_version"],
           "--model", model,
           "--dataset-source", cfg["dataset_source"],
           "--sample", str(cfg["sample"]),
           "--seed", str(cfg["seed"]),
           "--experiment-name", experiment_name]
    if cfg["dataset_source"] == "hf":
        cmd += ["--hf-dataset", cfg["hf_dataset"], "--hf-config", cfg["hf_config"]]
        if str(cfg.get("hf_revision") or "").strip():
            cmd += ["--hf-revision", str(cfg["hf_revision"]).strip()]
    if cfg.get("max_concurrency"):
        cmd += ["--max-concurrency", str(cfg["max_concurrency"])]
    return cmd


def build_plan_env(*, leg: str, phase: str, kind: str, cfg: dict) -> dict[str, str]:
    """The per-phase env map applied to a child for the given step.

    ``SERVING_PHASE`` of ``""`` means "unset" (the caller drops the key so the
    runner records the phase honestly as unknown). ``OPENROUTER_BASE_URL`` /
    ``OPENROUTER_API_KEY`` flip between the Modal endpoint and OpenRouter.
    """
    env: dict[str, str] = {}
    if leg in ("modal", "both"):
        env["BENCH_GPU"] = cfg["gpu"]
        env["BENCH_GPU_HOURLY_USD"] = str(cfg["gpu_hourly_usd"])
    if phase == PHASE_COLD:
        env["SERVING_PHASE"] = "cold"
    elif phase == PHASE_WARM:
        env["SERVING_PHASE"] = "warm"
    else:
        env["SERVING_PHASE"] = ""
    if kind == KIND_DOC_EVAL:
        if phase == PHASE_OPENROUTER:
            env["OPENROUTER_BASE_URL"] = DEFAULT_OPENROUTER_BASE_URL
            env["OPENROUTER_API_KEY"] = cfg["openrouter_api_key"]
        else:
            env["OPENROUTER_BASE_URL"] = cfg["modal_endpoint_url"]
            env["OPENROUTER_API_KEY"] = cfg["modal_api_token"]
            env["MODAL_VLLM_MODEL"] = cfg["modal_model"]
            env["MODAL_VLLM_GPU"] = cfg["gpu"]
    return env


def env_for_step(step: Step, cfg: dict, *, base_env: dict | None = None) -> dict:
    """Full child env: the inherited environment plus the step's per-phase map."""
    env = dict(os.environ if base_env is None else base_env)
    for key, value in step.env.items():
        if value in ("", None):
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


def build_plan(cfg: dict) -> list[Step]:
    """Ordered steps per leg: modal = cold smoke, warm-up, warm sample;
    openrouter = the API baseline. ``both`` = all four."""
    steps: list[Step] = []
    python_exe = str(cfg.get("python_exe") or sys.executable)

    if cfg["leg"] in ("modal", "both"):
        steps.append(Step(
            id="modal_cold_smoke",
            leg="modal",
            phase=PHASE_COLD,
            kind=KIND_GUIDED_SMOKE,
            paid=True,
            description="Modal cold smoke — first container start (guided smoke profile)",
            cmd=build_guided_command(cfg, "smoke", python_exe=python_exe),
            env=build_plan_env(leg="modal", phase=PHASE_COLD, kind=KIND_GUIDED_SMOKE, cfg=cfg),
            est_max_spend_usd=_guided_ceiling(cfg, "smoke"),
        ))
        steps.append(Step(
            id="modal_warmup",
            leg="modal",
            phase=PHASE_WARM,
            kind=KIND_GUIDED_PILOT,
            paid=True,
            description="Modal warm-up — cache warm, stability check (guided pilot profile)",
            cmd=build_guided_command(cfg, "pilot", python_exe=python_exe),
            env=build_plan_env(leg="modal", phase=PHASE_WARM, kind=KIND_GUIDED_PILOT, cfg=cfg),
            est_max_spend_usd=_guided_ceiling(cfg, "pilot"),
        ))
        steps.append(Step(
            id="modal_warm_sample",
            leg="modal",
            phase=PHASE_WARM,
            kind=KIND_DOC_EVAL,
            paid=True,
            description="Modal warm sample — docclass eval against the deployed vLLM endpoint",
            cmd=build_docclass_command(cfg, experiment_name=_resolve_experiment_name(cfg, "modal"),
                                       model=cfg["modal_model"], python_exe=python_exe),
            env=build_plan_env(leg="modal", phase=PHASE_WARM, kind=KIND_DOC_EVAL, cfg=cfg),
            est_max_spend_usd=estimate_doc_eval_max_spend(cfg, cfg["modal_model"]),
        ))

    if cfg["leg"] in ("openrouter", "both"):
        steps.append(Step(
            id="openrouter_baseline",
            leg="openrouter",
            phase=PHASE_OPENROUTER,
            kind=KIND_DOC_EVAL,
            paid=True,
            description="OpenRouter baseline — same sample/prompt against the API",
            cmd=build_docclass_command(cfg, experiment_name=_resolve_experiment_name(cfg, "openrouter"),
                                       model=cfg["api_model"], python_exe=python_exe),
            env=build_plan_env(leg="openrouter", phase=PHASE_OPENROUTER, kind=KIND_DOC_EVAL, cfg=cfg),
            est_max_spend_usd=estimate_doc_eval_max_spend(cfg, cfg["api_model"]),
        ))
    return steps


# ---------------------------------------------------------------------------
# Spend-cap math
# ---------------------------------------------------------------------------


def spend_cap_check(committed_usd: float, step_est_usd: float | None,
                    cap_usd: float | None) -> tuple[bool, str]:
    """Gate a step against the spend cap.

    Returns ``(approved, message)``. An unavailable step estimate cannot be
    cap-enforced (the wizard then requires an explicit approval phrase);
    a None cap means no cap configured.
    """
    if cap_usd is None:
        return (True, "no spend cap configured")
    if step_est_usd is None:
        return (True, "step spend estimate unavailable — cap not enforceable; "
                     "explicit approval required")
    if committed_usd + step_est_usd <= cap_usd + 1e-9:
        return (True, f"estimated ${step_est_usd:.2f} within cap ${cap_usd:.2f} "
                      f"(committed ${committed_usd:.2f})")
    return (False, f"REFUSED: estimated ${step_est_usd:.2f} + committed "
                   f"${committed_usd:.2f} exceeds cap ${cap_usd:.2f}")


def cumulative_max_spend(steps: list[Step]) -> tuple[float, bool]:
    """(sum of estimated max spend, whether any step's estimate is unknown)."""
    total = 0.0
    unknown = False
    for step in steps:
        if step.est_max_spend_usd is None:
            unknown = True
        else:
            total += step.est_max_spend_usd
    return total, unknown


# ---------------------------------------------------------------------------
# PREVIEW
# ---------------------------------------------------------------------------


def preview_text(cfg: dict, steps: list[Step]) -> str:
    secrets = secret_values(cfg)
    lines = [
        "=" * 72,
        "EXPERIMENT FLOW PREVIEW",
        "=" * 72,
        f"legs: {cfg['leg']}   sample: {cfg['sample']} (0 = all rows)   "
        f"seed: {cfg['seed']}   prompt: {cfg['prompt_version']}",
        f"dataset source: {cfg['dataset_source']}"
        + (f"   hf: {cfg['hf_dataset']} @ {cfg['hf_config']}"
           + (f" rev {cfg['hf_revision']}" if str(cfg.get('hf_revision') or '').strip() else "")
           if cfg["dataset_source"] == "hf" else ""),
        f"experiments: api={cfg['experiment_name_api']}  modal={cfg['experiment_name_modal']}",
    ]
    if cfg["leg"] in ("modal", "both"):
        lines.append(f"GPU: {cfg['gpu']} @ ${cfg['gpu_hourly_usd']:.2f}/hr   "
                     f"spend cap: ${cfg['spend_cap_usd']:.2f}")
    for i, step in enumerate(steps, 1):
        lines.append("")
        lines.append(f"STEP {i}: {step.description}  [{'PAID' if step.paid else 'FREE'}]")
        lines.append(f"  phase: {step.phase}")
        lines.append(f"  command: {' '.join(step.cmd)}")
        lines.append(f"  env: {redacted_env(step.env, secrets)}")
        if step.est_max_spend_usd is not None:
            lines.append(f"  estimated max spend: ${step.est_max_spend_usd:.2f}")
        else:
            lines.append("  estimated max spend: unknown")
    total, unknown = cumulative_max_spend(steps)
    lines.append("")
    lines.append(f"TOTAL estimated max spend: {'>=$' + f'{total:.2f}' if unknown else '$' + f'{total:.2f}'}")
    lines.append(f"spend cap: ${cfg['spend_cap_usd']:.2f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# RUN phase
# ---------------------------------------------------------------------------


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _confirm(prompt: str, input_fn, default_yes: bool = False) -> bool:
    while True:
        raw = str(input_fn(prompt)).strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        if raw == "":
            return default_yes
        print("  please answer y or n.")


def new_run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "reports" / "experiment_flow_runs" / stamp


def run_one_step(step: Step, cfg: dict, *, run_dir: Path,
                 popen_factory=subprocess.Popen) -> dict:
    """Stream one step's child output to the console and a redacted log.

    The log and console both receive redacted lines so a child that echoes
    env (keys) never leaks them to disk or terminal.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / f"{step.id}.log"
    env = env_for_step(step, cfg)
    secrets = secret_values(cfg)
    proc = popen_factory(step.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1, encoding="utf-8", errors="replace",
                         env=env)
    lines: list[str] = []
    with open(log_path, "w", encoding="utf-8") as logf:
        for raw in proc.stdout:
            clean = redact(raw.rstrip("\n"), secrets)
            lines.append(clean)
            logf.write(clean + "\n")
            logf.flush()
            print(clean, flush=True)
    code = proc.wait()
    return {"step_id": step.id, "exit_code": code, "log_path": str(log_path),
            "lines": lines, "env": env}


# ---------------------------------------------------------------------------
# COMPARE phase — record pairing over the experiment log
# ---------------------------------------------------------------------------


def iter_records(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def list_records(path: Path) -> list[dict]:
    return list(iter_records(path))


def record_provider(record: dict) -> str:
    """Provider for a record: serving block, else endpoint, else model guess."""
    serving = record.get("serving") or {}
    provider = serving.get("provider")
    if provider in (OPENROUTER_PROVIDER, MODAL_PROVIDER):
        return provider
    endpoint = serving.get("endpoint")
    if endpoint:
        return provider_from_base_url(endpoint)
    model = str(record.get("model") or "")
    if "Qwen3-8B" in model or "Qwen/Qwen3-8B" in model:
        return MODAL_PROVIDER
    return OTHER_PROVIDER


def record_tokens(record: dict) -> dict:
    """Token totals for a record: the serving block, plus cost from the tokens
    block (which carries ``cost_total_usd`` the serving snapshot lacks)."""
    merged: dict = {}
    serving = record.get("serving") or {}
    serving_tokens = serving.get("tokens")
    if isinstance(serving_tokens, dict) and serving_tokens.get("total_tokens") is not None:
        merged.update(serving_tokens)
    tokens = record.get("tokens") or {}
    for key in ("total", "sorter"):
        block = tokens.get(key)
        if isinstance(block, dict) and block.get("total_tokens") is not None:
            merged.update(block)
    return merged


def _record_dataset_fingerprint(record: dict) -> str | None:
    serving = record.get("serving") or {}
    value = serving.get("dataset_fingerprint")
    if value:
        return str(value)
    value = (record.get("data_source") or {}).get("dataset_fingerprint")
    return str(value) if value else None


def _record_prompt_version(record: dict) -> str | None:
    value = (record.get("prompt_versions") or {}).get("sorter")
    return str(value) if value else None


def _record_prompt_sha(record: dict) -> str | None:
    serving = record.get("serving") or {}
    fps = serving.get("prompt_fingerprints") or {}
    sorter = fps.get("sorter") or {}
    sha = sorter.get("sha256")
    return str(sha) if sha else None


def verify_pair(api_record: dict, modal_record: dict) -> list[str]:
    """Problems that make a pair invalid; an empty list means a valid pair.

    Checks provider identity, dataset fingerprint equality, and prompt
    identity (version key, plus the byte sha256 when serving blocks exist).
    A pair is REJECTED on any mismatch — never silently compared.
    """
    problems: list[str] = []
    api_provider = record_provider(api_record)
    modal_provider = record_provider(modal_record)
    if api_provider != OPENROUTER_PROVIDER:
        problems.append(f"api record provider is {api_provider!r}, expected 'openrouter'")
    if modal_provider != MODAL_PROVIDER:
        problems.append(f"modal record provider is {modal_provider!r}, expected 'modal'")

    api_fp = _record_dataset_fingerprint(api_record)
    modal_fp = _record_dataset_fingerprint(modal_record)
    if api_fp and modal_fp:
        if api_fp != modal_fp:
            problems.append(f"dataset fingerprint mismatch: api={api_fp} modal={modal_fp}")
    else:
        problems.append("dataset fingerprints unavailable on one or both records — "
                        "cannot verify a common sample")

    api_version = _record_prompt_version(api_record)
    modal_version = _record_prompt_version(modal_record)
    if api_version and modal_version:
        if api_version != modal_version:
            problems.append(f"prompt version mismatch: api={api_version} modal={modal_version}")
    else:
        problems.append("prompt versions unavailable on one or both records")

    api_sha = _record_prompt_sha(api_record)
    modal_sha = _record_prompt_sha(modal_record)
    if api_sha and modal_sha and api_sha != modal_sha:
        problems.append(f"prompt byte fingerprint mismatch: api={api_sha} modal={modal_sha}")
    return problems


def find_matching_pair(records: list[dict]) -> dict | None:
    """The most recent valid openrouter+modal pair with matching fingerprints.

    Returns ``{"api": ..., "modal": ..., "problems": []}`` or None when no
    valid pair exists in the log.
    """
    candidates: list[dict] = []
    for api in records:
        if record_provider(api) != OPENROUTER_PROVIDER:
            continue
        for modal in records:
            if record_provider(modal) != MODAL_PROVIDER:
                continue
            problems = verify_pair(api, modal)
            if not problems:
                candidates.append({"api": api, "modal": modal, "problems": []})
    if not candidates:
        return None
    candidates.sort(key=lambda c: str(c["modal"].get("timestamp") or ""), reverse=True)
    return candidates[0]


# ---------------------------------------------------------------------------
# Dojo scoring subprocess shim — the ONLY way the scoring package is touched
# ---------------------------------------------------------------------------

_DOJO_SHIM = r"""
import dataclasses
import inspect
import json
import sys

sys.path.insert(0, sys.argv[1])

from llm_dojo_scoring import cost, throughput

_MODULES = {"cost": cost, "throughput": throughput}


def _sig(fn):
    try:
        return inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}


def _build_throughput_metrics(data):
    tm_type = getattr(throughput, "ThroughputMetrics", None)
    if tm_type is None:
        return None, "throughput.ThroughputMetrics unavailable in this package"
    if isinstance(data, tm_type):
        return data, None
    if not isinstance(data, dict):
        return None, "metrics must be a dict, got %s" % type(data).__name__
    annotations = getattr(tm_type, "__annotations__", {})
    kwargs = {k: v for k, v in data.items() if k in annotations and v is not None}
    fields = getattr(tm_type, "__dataclass_fields__", None) or {}
    missing = dataclasses.MISSING
    for name in fields:
        default = fields[name].default
        factory = fields[name].default_factory
        if name not in kwargs and default is missing and factory is missing:
            annotation = annotations.get(name)
            is_string = annotation in (str, "str")
            kwargs[name] = "" if is_string else 0
    try:
        return tm_type(**kwargs), None
    except Exception as exc:
        return None, "cannot construct ThroughputMetrics: %s" % exc


def _call(fn, kwargs):
    try:
        return fn(**kwargs), None
    except Exception as exc:
        return None, str(exc)


def _fail(op_id, reason):
    return {"id": op_id, "ok": False, "result": None, "reason": str(reason)}


def run_op(op):
    op_id = op.get("id", "?")
    fn_name = op.get("fn", "")
    mod_name, _, name = fn_name.rpartition(".")
    module = _MODULES.get(mod_name)
    fn = getattr(module, name, None) if module is not None else None
    if fn is None:
        return _fail(op_id, "function %s unavailable" % fn_name)
    params = op.get("params") or {}
    sig = _sig(fn)

    if name == "price_for":
        result, err = _call(fn, {"model": params.get("model")})
        if err:
            return _fail(op_id, err)
        if result is None:
            return {"id": op_id, "ok": True, "result": None}
        return {"id": op_id, "ok": True,
                "result": {"input_per_million": result[0], "output_per_million": result[1]}}

    if name == "token_cost_breakdown":
        kwargs = {"prompt_tokens": params.get("prompt_tokens"),
                  "completion_tokens": params.get("completion_tokens")}
        if "model" in sig:
            kwargs["model"] = params.get("model")
        result, err = _call(fn, kwargs)
        if err:
            result, err = _call(fn, {"prices": params.get("prices"),
                                     "prompt_tokens": params.get("prompt_tokens"),
                                     "completion_tokens": params.get("completion_tokens")})
        if err:
            return _fail(op_id, err)
        return {"id": op_id, "ok": True, "result": result}

    if name == "estimate_cost":
        result, err = _call(fn, {"prompt_tokens": params.get("prompt_tokens"),
                                 "completion_tokens": params.get("completion_tokens"),
                                 "model": params.get("model")})
        if err:
            return _fail(op_id, err)
        return {"id": op_id, "ok": True, "result": result}

    if name == "estimate_billed_gpu_cost":
        if "metrics" in sig:
            metrics, err = _build_throughput_metrics(params.get("metrics") or {})
            if err:
                return _fail(op_id, err)
            kwargs = {"metrics": metrics, "gpu_hourly_usd": params.get("gpu_hourly_usd")}
        else:
            kwargs = {"gpu_type": params.get("gpu_type"), "elapsed_sec": params.get("elapsed_sec"),
                      "gpu_hourly_usd": params.get("gpu_hourly_usd")}
        result, err = _call(fn, kwargs)
        if err:
            return _fail(op_id, err)
        return {"id": op_id, "ok": True, "result": result}

    if name == "amortize_cold_start":
        if "n_runs" in sig:
            kwargs = {"cold_start_seconds": params.get("cold_start_seconds"),
                      "gpu_hourly_usd": params.get("gpu_hourly_usd"),
                      "n_runs": params.get("n_requests")}
        else:
            kwargs = {"total_gpu_cost": params.get("total_gpu_cost"),
                      "cold_start_seconds": params.get("cold_start_seconds"),
                      "total_seconds": params.get("total_seconds"),
                      "n_requests": params.get("n_requests")}
        result, err = _call(fn, kwargs)
        if err:
            return _fail(op_id, err)
        return {"id": op_id, "ok": True, "result": result}

    if name == "effective_tokens_per_sec":
        if "tokens_generated" in sig:
            kwargs = {"tokens_generated": params.get("total_tokens"),
                      "generation_time_sec": params.get("elapsed_sec")}
            if "cold_start_seconds" in sig:
                kwargs["cold_start_seconds"] = params.get("cold_start_seconds") or 0.0
        else:
            kwargs = {"total_tokens": params.get("total_tokens"),
                      "elapsed_sec": params.get("elapsed_sec")}
        result, err = _call(fn, kwargs)
        if err:
            return _fail(op_id, err)
        return {"id": op_id, "ok": True, "result": result}

    if name == "compare_api_vs_gpu":
        if "metrics" in sig:
            metrics, err = _build_throughput_metrics(params.get("metrics") or {})
            if err:
                return _fail(op_id, err)
            kwargs = {"api_cost_usd": params.get("api_cost_usd"), "metrics": metrics,
                      "gpu_hourly_usd": params.get("gpu_hourly_usd")}
        else:
            kwargs = {"api_cost_usd": params.get("api_cost_usd"), "metrics": params.get("metrics"),
                      "gpu_hourly_usd": params.get("gpu_hourly_usd")}
        result, err = _call(fn, kwargs)
        if err:
            return _fail(op_id, err)
        return {"id": op_id, "ok": True, "result": result}

    return _fail(op_id, "unsupported op %s" % fn_name)


def main():
    ops = json.loads(sys.stdin.read() or "[]")
    results = [run_op(op) for op in ops]
    json.dump(results, sys.stdout, default=str)


if __name__ == "__main__":
    main()
"""


def dojo_call(ops: list[dict], *, python_exe: str | None = None,
              scoring_path: str | None = None,
              runner=subprocess.run) -> list[dict]:
    """Run scoring ops through the llm-dojo-scoring package in a subprocess.

    The shim prepends ``scoring_path`` to the child's ``PYTHONPATH`` and
    adapts each op to the package's real signatures at runtime (introspection
    + keyword args in try/except), so a signature drift surfaces as a
    ``{"ok": false, "reason": ...}`` result instead of a crash. Tests stub
    ``runner`` and never touch the package.
    """
    if not ops:
        return []
    python_exe = python_exe or sys.executable
    scoring_path = str(scoring_path or os.environ.get("DOJO_SCORING_PATH")
                       or DEFAULT_DOJO_SCORING_PATH)
    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8")
    try:
        handle.write(_DOJO_SHIM)
        handle.close()
        env = dict(os.environ)
        env["PYTHONPATH"] = scoring_path + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONUTF8"] = "1"
        completed = runner([python_exe, handle.name, scoring_path],
                           input=json.dumps(ops), capture_output=True, text=True,
                           encoding="utf-8", env=env)
    finally:
        try:
            handle.close()
        except OSError:
            pass
        try:
            os.unlink(handle.name)
        except OSError:
            pass
    returncode = getattr(completed, "returncode", 0)
    if returncode != 0:
        stderr = redact(str(getattr(completed, "stderr", "") or ""), ())
        raise RuntimeError(f"dojo scoring subprocess exited {returncode}: {stderr[-500:]}")
    try:
        return json.loads(str(getattr(completed, "stdout", "") or "[]"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"dojo scoring subprocess returned unparseable output: {exc}")


# ---------------------------------------------------------------------------
# COMPARE report building
# ---------------------------------------------------------------------------


def build_compare_ops(api_record: dict, modal_record: dict, cfg: dict,
                      *, cold_start_seconds: float | None = None) -> list[dict]:
    """The dojo ops list for a paired comparison.

    Every number flows from the paired records (tokens, timing, GPU, price
    basis) plus the config; nothing is fabricated — an unavailable value stays
    None and the report prints an unknown marker with the reason.
    """
    api_tokens = record_tokens(api_record)
    modal_tokens = record_tokens(modal_record)
    api_model = str(cfg.get("api_model") or api_record.get("model") or "")
    modal_model = str(cfg.get("modal_model") or modal_record.get("model") or "")
    modal_serving = modal_record.get("serving") or {}
    gpu = (modal_serving.get("gpu") or {}).get("gpu") or cfg.get("gpu")
    duration_s = (modal_serving.get("timing") or {}).get("duration_s")
    if duration_s is not None:
        duration_s = float(duration_s)
    n_requests = (api_record.get("scores") or {}).get("n_rows") or len(api_record.get("results") or []) or None

    modal_metrics = {
        "gpu_type": gpu,
        "tokens_generated": modal_tokens.get("total_tokens") or modal_tokens.get("completion_tokens"),
        "generation_time_sec": duration_s,
        "prompt_tokens": modal_tokens.get("prompt_tokens"),
        "cold_start_seconds": cold_start_seconds,
    }
    return [
        {"id": "api_price", "fn": "cost.price_for", "params": {"model": api_model}},
        {"id": "api_breakdown", "fn": "cost.token_cost_breakdown",
         "params": {"prompt_tokens": api_tokens.get("prompt_tokens"),
                    "completion_tokens": api_tokens.get("completion_tokens"),
                    "model": api_model}},
        {"id": "api_estimate", "fn": "cost.estimate_cost",
         "params": {"prompt_tokens": api_tokens.get("prompt_tokens"),
                    "completion_tokens": api_tokens.get("completion_tokens"),
                    "model": api_model}},
        {"id": "modal_price", "fn": "cost.price_for", "params": {"model": modal_model}},
        {"id": "modal_billed", "fn": "throughput.estimate_billed_gpu_cost",
         "params": {"metrics": modal_metrics, "gpu_type": gpu,
                    "elapsed_sec": duration_s, "gpu_hourly_usd": cfg.get("gpu_hourly_usd")}},
        {"id": "cold_amortization", "fn": "throughput.amortize_cold_start",
         "params": {"cold_start_seconds": cold_start_seconds,
                    "gpu_hourly_usd": cfg.get("gpu_hourly_usd"),
                    "n_requests": n_requests,
                    "total_gpu_cost": None, "total_seconds": duration_s}},
        {"id": "modal_tps", "fn": "throughput.effective_tokens_per_sec",
         "params": {"total_tokens": modal_tokens.get("total_tokens"),
                    "elapsed_sec": duration_s,
                    "cold_start_seconds": cold_start_seconds}},
        {"id": "break_even", "fn": "throughput.compare_api_vs_gpu",
         "params": {"api_cost_usd": api_tokens.get("cost_total_usd"),
                    "metrics": modal_metrics, "gpu_hourly_usd": cfg.get("gpu_hourly_usd")}},
    ]


def format_compare_report(api_record: dict, modal_record: dict, ops: list[dict],
                          results: list[dict], cfg: dict) -> str:
    """Render the paired cost comparison; every unavailable number prints an
    unknown marker with its reason (never a fabricated value)."""
    by_id = {op["id"]: res for op, res in zip(ops, results)}

    def _result(op_id: str):
        res = by_id.get(op_id) or {}
        if not res.get("ok"):
            return None, str(res.get("reason") or "call failed")
        return res.get("result"), None

    def _num(op_id: str, key: str):
        value, reason = _result(op_id)
        if value is None:
            return None, reason
        if isinstance(value, dict):
            value = value.get(key)
        if value is None:
            return None, "not provided by the scoring package"
        return value, None

    def _fmt_usd(value, reason):
        if value is None:
            return f"N/A ({reason or 'unavailable'})"
        if abs(value) < 0.001:
            return f"${value:.3e}"
        return f"${value:.6f}"

    api_tokens = record_tokens(api_record)
    modal_tokens = record_tokens(modal_record)
    modal_serving = modal_record.get("serving") or {}
    gpu = (modal_serving.get("gpu") or {}).get("gpu") or cfg.get("gpu")
    api_model = str(cfg.get("api_model") or api_record.get("model") or "")
    modal_model = str(cfg.get("modal_model") or modal_record.get("model") or "")
    api_fp = _record_dataset_fingerprint(api_record)

    lines = [
        "=" * 72,
        "COST COMPARISON: OpenRouter vs Modal-hosted vLLM (Qwen3-8B)",
        "=" * 72,
        f"api model: {api_model}   modal model: {modal_model} "
        f"({gpu} @ ${cfg.get('gpu_hourly_usd', 0):.2f}/hr)",
        f"dataset fingerprint: {api_fp}",
        f"prompt version: {_record_prompt_version(api_record)}",
        f"api tokens:  {api_tokens.get('prompt_tokens')} in / "
        f"{api_tokens.get('completion_tokens')} out "
        f"({api_tokens.get('total_tokens')} total)",
        f"modal tokens: {modal_tokens.get('prompt_tokens')} in / "
        f"{modal_tokens.get('completion_tokens')} out "
        f"({modal_tokens.get('total_tokens')} total)",
        "",
        "API side (OpenRouter, per-token):",
    ]

    price_in, _ = _num("api_price", "input_per_million")
    price_out, _ = _num("api_price", "output_per_million")
    if price_in is None or price_out is None:
        lines.append("  price_for: N/A (no OpenRouter price for this model)")
    else:
        lines.append(f"  price: ${price_in:.4f} / 1M input, ${price_out:.4f} / 1M output")
    in_ct, _ = _num("api_breakdown", "input_cost_per_token")
    out_ct, _ = _num("api_breakdown", "output_cost_per_token")
    tot_ct, _ = _num("api_breakdown", "total_cost_per_token")
    lines.append(f"  cost per input token:  {_fmt_usd(in_ct, 'unavailable')}")
    lines.append(f"  cost per output token: {_fmt_usd(out_ct, 'unavailable')}")
    lines.append(f"  cost per total token:  {_fmt_usd(tot_ct, 'unavailable')}")
    api_est, _ = _num("api_estimate", None)
    lines.append(f"  estimated API cost (estimate_cost): {_fmt_usd(api_est, 'unavailable')}")

    lines.append("")
    lines.append("Modal side (GPU-hosted vLLM):")
    billed, billed_reason = _num("modal_billed", None)
    lines.append(f"  billed GPU cost (est, generation window): "
                 f"{_fmt_usd(billed, billed_reason)}")
    modal_total = modal_tokens.get("total_tokens")
    if billed is not None and modal_total:
        lines.append(f"  cost per total token: ${billed / float(modal_total):.8f}")
    else:
        lines.append("  cost per total token: N/A (no billed cost or token total)")
    tps, tps_reason = _num("modal_tps", None)
    if tps is not None:
        lines.append(f"  effective tokens/sec: {tps:.1f}")
    else:
        lines.append(f"  effective tokens/sec: N/A ({tps_reason or 'unavailable'})")

    lines.append("")
    lines.append("Cold-start amortization:")
    amort, amort_reason = _num("cold_amortization", None)
    if amort is not None:
        lines.append(f"  per-run cold-start cost (amortize_cold_start): ${amort:.6f}")
    else:
        lines.append(f"  per-run cold-start cost: N/A ({amort_reason or 'unavailable'})")
    be, be_reason = _result("break_even")
    if be is None:
        lines.append(f"  break-even sketch: N/A ({be_reason or 'unavailable'})")
    else:
        billed_cs = be.get("billed_cold_start_seconds")
        if billed_cs is not None:
            lines.append(f"  billed cold-start seconds in comparison: {billed_cs}")

    lines.append("")
    lines.append("Break-even sketch:")
    if be is None:
        lines.append(f"  N/A ({be_reason or 'unavailable'})")
    else:
        savings = be.get("savings_usd")
        pct = be.get("api_vs_gpu_savings_pct")
        api_m = be.get("api_per_million_usd")
        gpu_m = be.get("gpu_per_million_usd")
        eff_tps = be.get("effective_tokens_per_sec")
        lines.append(f"  API cost: ${be.get('api_cost_usd', 0):.6f}   "
                     f"GPU cost: ${be.get('gpu_cost_usd', 0):.6f}")
        lines.append(f"  savings: {'$' + f'{savings:.6f}' if savings is not None else 'N/A'}   "
                     f"({'N/A' if pct is None else f'{pct:.1f}%'})")
        lines.append(f"  per-1M tokens: API {'$' + f'{api_m:.4f}' if api_m is not None else 'N/A'}   "
                     f"GPU {'$' + f'{gpu_m:.4f}' if gpu_m is not None else 'N/A'}")
        lines.append(f"  GPU effective tokens/sec: "
                     f"{'N/A' if eff_tps is None else f'{eff_tps:.1f}'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive wizard + CLI
# ---------------------------------------------------------------------------


def _ask_cold_start(input_fn) -> float | None:
    raw = str(input_fn("Modal cold-start seconds for amortization "
                       "(blank = unknown): ")).strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        print("  invalid: not a number — treating as unknown.")
        return None
    return max(0.0, value)


def run_compare_phase(cfg: dict, *, log_path: Path | None = None,
                      input_fn=input, scoring_path: str | None = None) -> int:
    print("\n" + "=" * 72)
    print("COMPARE PHASE")
    print("=" * 72)
    path = log_path or default_jsonl_path()
    records = list_records(path)
    if not records:
        print(f"No experiment-log records found in {path}. Nothing to compare.")
        return 1
    print(f"{len(records)} records loaded from {path}")
    cold_start_seconds = _ask_cold_start(input_fn)
    pair = find_matching_pair(records)
    if pair is None:
        print("No valid OpenRouter + Modal pair with matching fingerprints "
              "found in the log — comparison refused.")
        print("Records present:")
        for record in records:
            source = record.get("data_source") or {}
            print(f"  - {record_provider(record):<10} {record.get('experiment_name')} "
                  f"sample={source.get('sample_requested')} seed={source.get('seed')} "
                  f"fp={_record_dataset_fingerprint(record)}")
        return 1
    api = pair["api"]
    modal = pair["modal"]
    print(f"Paired: api={api.get('experiment_name')}  "
          f"modal={modal.get('experiment_name')}  "
          f"(dataset fp {_record_dataset_fingerprint(api)})")
    ops = build_compare_ops(api, modal, cfg, cold_start_seconds=cold_start_seconds)
    results = dojo_call(ops, python_exe=cfg.get("python_exe"),
                        scoring_path=scoring_path)
    print(format_compare_report(api, modal, ops, results, cfg))
    return 0


def main_with_args(argv: list[str]) -> int:
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="ask + preview only — launch nothing, compare nothing")
    parser.add_argument("--experiment-log", type=Path, default=None,
                        help="experiment log for the COMPARE phase "
                             "(default: $EXPERIMENT_LOG_PATH)")
    parser.add_argument("--dojo-scoring-path", default=None,
                        help="override the llm-dojo-scoring package path")
    parser.add_argument("--python-exe", default=None,
                        help="python executable for child subprocesses")
    args = parser.parse_args(argv)

    cfg = ask_config()
    if args.python_exe:
        cfg["python_exe"] = args.python_exe

    steps = build_plan(cfg)
    print(preview_text(cfg, steps))

    if args.dry_run:
        print("\n[dry-run] Not launching anything. Re-run without --dry-run to execute.")
        return 0

    if not _is_interactive():
        print("\nREFUSED: paid steps require an interactive terminal "
              "(piped/noninteractive stdin). Nothing was launched.")
        return 1

    if not _confirm(f"\nRun {len(steps)} step(s) now? Paid steps require "
                    f"per-step approval. [y/N] ", input_fn=input):
        print("Cancelled — nothing was launched.")
        return 0

    run_dir = new_run_dir()
    print(f"[flow] run artifacts: {run_dir}")
    committed = 0.0
    for i, step in enumerate(steps, 1):
        approved, cap_msg = spend_cap_check(committed, step.est_max_spend_usd,
                                            cfg["spend_cap_usd"])
        print(f"\n=== STEP {i}/{len(steps)} — {step.description} ===")
        print(f"phase: {step.phase}")
        print(f"command: {' '.join(step.cmd)}")
        print(f"env knobs: {redacted_env(step.env, secret_values(cfg))}")
        estimate = step.est_max_spend_usd
        print(f"estimated max spend: "
              f"{'unknown' if estimate is None else f'${estimate:.2f}'}")
        print(f"spend cap check: {cap_msg}")
        if not approved:
            print("REFUSED by spend cap — stopping cleanly.")
            break
        if step.paid:
            if not _confirm("Approve this PAID step? [y/N] ", input_fn=input):
                print("Not approved — stopping cleanly.")
                break
        result = run_one_step(step, cfg, run_dir=run_dir)
        print(f"[flow] step {step.id} exit={result['exit_code']} "
              f"log={result['log_path']}")
        committed += step.est_max_spend_usd or 0.0
        if result["exit_code"] != 0:
            print(f"[flow] step {step.id} FAILED (exit {result['exit_code']}) — "
                  f"stopping. See {result['log_path']}")
            break
        if i < len(steps):
            if not _confirm("Continue to the next phase? [Y/n] ",
                            input_fn=input, default_yes=True):
                print("Stopped cleanly between phases.")
                break

    return run_compare_phase(cfg, log_path=args.experiment_log,
                             scoring_path=args.dojo_scoring_path)


def main() -> None:
    raise SystemExit(main_with_args(sys.argv[1:]))


if __name__ == "__main__":
    main()