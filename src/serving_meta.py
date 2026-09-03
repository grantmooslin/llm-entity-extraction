"""Serving / cost-comparison metadata for completed eval-run records.

The eval runners append ONE append-only record per run to
``reports/experiment_log.jsonl``. This module builds the ``serving`` block of
that record — the standardized lens for comparing a completed **OpenRouter**
run against a completed **Modal-hosted vLLM (Qwen3-8B)** run faithfully:

- ``provider`` / ``endpoint`` — where the LLM calls went (resolved from the
  OpenAI-compatible ``OPENROUTER_BASE_URL`` seam at record time).
- ``model`` — the model slug used in calls, plus the HF checkpoint identity
  (``MODAL_VLLM_MODEL``) when the provider is Modal.
- ``prompt_fingerprints`` — sha256 over each prompt version's literal text
  (the version key IS the experiment identity; the fingerprint pins the exact
  bytes that ran, so a mutation under a reused key is detectable).
- ``dataset_fingerprint`` — the already-computed sha256 row identity.
- ``tokens`` — prompt/completion/total token totals for the run.
- ``timing`` — wall-clock run window plus per-call latency statistics (the
  first-call vs mean/max split is the honest signal for cold-start analysis).
- ``gpu`` — Modal deployment knobs (GPU type, quantization, max model len)
  plus the taxonomy ``gpu_hourly_usd`` price for that GPU; OpenRouter reports
  ``reported: false`` (the GPU is server-side, not exposed).
- ``price_basis`` — what the run was priced against: per-1M-token prices from
  the taxonomy ``cost_models`` table, and/or GPU-hourly pricing, with the
  source of each number. For Modal it also carries an *estimated* GPU bill
  over the runner's wall-clock window (a lower bound on Modal's container-
  lifetime billing, labeled as such).
- ``phase`` — cold/warm/unknown: whether the run hit a cold container. This
  is taken from the ``SERVING_PHASE`` env knob (``cold`` | ``warm``) because
  the runner is network-free and cannot probe the server; default ``unknown``
  when not configured.

Everything here is network-free and deterministic — it derives only from env
knobs (``OPENROUTER_BASE_URL``, ``MODAL_VLLM_*``, ``SERVING_PHASE``), the
taxonomy price tables, and the resolved prompt text. The manifest/resume
semantics are untouched: the block is computed at record time from the same
args a resumed run replays, and never changes the manifest header contract.
"""

from __future__ import annotations

import hashlib
import os
import statistics
from typing import Any

from src.openrouter_utils import resolve_openrouter_base_url
from src.prompts import get_prompt
from src.taxonomy import load_taxonomy

# ---------------------------------------------------------------------------
# Provider labels (mirror of the provider seam's vocabulary)
# ---------------------------------------------------------------------------

OPENROUTER_PROVIDER = "openrouter"
MODAL_PROVIDER = "modal"
OLLAMA_PROVIDER = "ollama"
LOCAL_PROVIDER = "local"
OTHER_PROVIDER = "other"

PHASE_COLD = "cold"
PHASE_WARM = "warm"
PHASE_UNKNOWN = "unknown"

PHASE_ENV = "SERVING_PHASE"

MODAL_GPU_DEFAULT = "L4"
MODAL_MAX_LEN_DEFAULT = "32768"


def provider_from_base_url(base_url: str | None) -> str:
    """Classify the OpenAI-compatible endpoint into a provider label.

    The ``OPENROUTER_BASE_URL`` seam is the single switching point between
    OpenRouter (default), a Modal-hosted vLLM deployment (KANBAN-096), a
    local Ollama/vLLM server, or anything else. An unknown/unset endpoint
    degrades to ``other`` — never guessed.
    """
    if not base_url:
        return OTHER_PROVIDER
    url = str(base_url).strip().lower().rstrip("/")
    if "openrouter.ai" in url:
        return OPENROUTER_PROVIDER
    if ".modal.run" in url:
        return MODAL_PROVIDER
    if "ollama" in url:
        return OLLAMA_PROVIDER
    if "localhost" in url or "127.0.0.1" in url or "0.0.0.0" in url:
        return LOCAL_PROVIDER
    return OTHER_PROVIDER


# ---------------------------------------------------------------------------
# Prompt fingerprints
# ---------------------------------------------------------------------------


def prompt_fingerprint(prompt_text: str) -> str:
    """sha256 (hex) over a prompt's literal text — the byte-identity of a
    prompt version. A mutated prompt under a reused key is detectable."""
    return hashlib.sha256(str(prompt_text).encode("utf-8")).hexdigest()


def prompt_fingerprints(prompt_versions: dict[str, str]) -> dict[str, dict]:
    """Resolve ``{role: version}`` prompt selections into byte fingerprints.

    Each role maps to ``{"version": ..., "sha256": ...}`` where the sha256 is
    over the prompt text ``get_prompt(version)`` returns. Unknown versions
    are skipped (never crash the record builder).
    """
    resolved: dict[str, dict] = {}
    for role, version in (prompt_versions or {}).items():
        try:
            text = get_prompt(str(version))
        except KeyError:
            continue
        resolved[str(role)] = {"version": str(version),
                               "sha256": prompt_fingerprint(text)}
    return resolved


# ---------------------------------------------------------------------------
# Model identity / GPU metadata / price basis
# ---------------------------------------------------------------------------


def model_identity(model_slug: str, *, provider: str | None = None) -> dict:
    """The model's record identity: the slug used in calls plus, for Modal,
    the HF checkpoint id the deployment serves (``MODAL_VLLM_MODEL``)."""
    identity: dict[str, Any] = {"slug": model_slug}
    if (provider or provider_from_base_url(resolve_openrouter_base_url())) == MODAL_PROVIDER:
        hf_id = os.environ.get("MODAL_VLLM_MODEL", "").strip()
        if hf_id:
            identity["hf_model_id"] = hf_id
    return identity


def gpu_metadata(*, provider: str) -> dict:
    """GPU metadata for the serving endpoint.

    Modal deployments expose their knobs via the ``MODAL_VLLM_*`` env vars
    (baked at deploy time — ``deploy/modal_vllm.py``); the taxonomy
    ``gpu_hourly_usd`` table prices the configured GPU. OpenRouter (and every
    other server-side provider) reports ``reported: false`` — the GPU is not
    exposed and must never be guessed.
    """
    if provider != MODAL_PROVIDER:
        return {
            "reported": False,
            "note": "server-side GPU; not exposed by the provider",
        }
    gpu = os.environ.get("MODAL_VLLM_GPU", MODAL_GPU_DEFAULT).strip() or MODAL_GPU_DEFAULT
    hourly = load_taxonomy().get("gpu_hourly_usd") or {}
    max_len = os.environ.get("MODAL_VLLM_MAX_MODEL_LEN", MODAL_MAX_LEN_DEFAULT).strip()
    try:
        max_len = int(max_len)
    except (TypeError, ValueError):
        max_len = int(MODAL_MAX_LEN_DEFAULT)
    return {
        "reported": True,
        "gpu": gpu,
        "quantization": os.environ.get("MODAL_VLLM_QUANTIZATION", "").strip() or None,
        "max_model_len": max_len,
        "hf_model_id": os.environ.get("MODAL_VLLM_MODEL", "").strip() or None,
        "image_tag": os.environ.get("MODAL_VLLM_IMAGE_TAG", "").strip() or None,
        "gpu_hourly_usd": hourly.get(gpu),
    }


def price_basis(
    model_slug: str,
    *,
    provider: str,
    gpu_meta: dict | None = None,
    duration_s: float | None = None,
    tokens: dict | None = None,
) -> dict:
    """What a run was priced against: per-1M-token prices and/or GPU-hourly.

    ``per_token_usd`` comes from the taxonomy ``cost_models`` table (the same
    prices the deterministic cost scorer uses). For Modal, ``gpu_hourly_usd``
    is the taxonomy price for the configured GPU, and — when a run duration is
    supplied — ``estimated_gpu_cost_usd`` projects it over the runner's
    wall-clock window. That estimate is a LOWER BOUND on the Modal bill
    (Modal charges container lifetime, not run time), which the field label
    makes explicit.
    """
    taxonomy = load_taxonomy()
    cost_models = taxonomy.get("cost_models") or {}
    gpu_hourly = taxonomy.get("gpu_hourly_usd") or {}

    prices = cost_models.get(model_slug)
    per_token: dict[str, float] | None = None
    if isinstance(prices, dict):
        per_token = {
            "input_per_million": float(prices.get("input_per_million")),
            "output_per_million": float(prices.get("output_per_million")),
        }

    basis: dict[str, Any] = {
        "basis": [],
        "source": [],
        "cost_total_usd": (tokens or {}).get("cost_total_usd"),
    }
    if per_token:
        basis["basis"].append("per_token")
        basis["per_token_usd"] = per_token
        basis["source"].append("taxonomy:cost_models")
    if provider == MODAL_PROVIDER:
        gpu_name = (gpu_meta or {}).get("gpu")
        hourly = gpu_hourly.get(gpu_name) if gpu_name else None
        if hourly is not None:
            basis["basis"].append("gpu_hourly")
            basis["gpu_hourly_usd"] = float(hourly)
            basis["source"].append("taxonomy:gpu_hourly_usd")
            if duration_s is not None:
                basis["estimated_gpu_cost_usd"] = round(
                    float(hourly) * duration_s / 3600.0, 6)
    if not basis["basis"]:
        basis["basis"] = ["provider_billed"]
        basis["source"] = ["provider usage"]
    return basis


# ---------------------------------------------------------------------------
# Phase + timing
# ---------------------------------------------------------------------------


def phase_from_env() -> str:
    """Cold/warm phase for the run: the ``SERVING_PHASE`` env knob
    (``cold`` | ``warm``), or ``unknown`` when unset. The runner is
    network-free and cannot probe the server, so an unconfigured phase is
    recorded honestly as unknown rather than guessed."""
    value = os.environ.get(PHASE_ENV, "").strip().lower()
    return value if value in (PHASE_COLD, PHASE_WARM) else PHASE_UNKNOWN


def call_latency_stats(elapsed_by_index: dict | None) -> dict | None:
    """Aggregate per-call wall-clock latencies (seconds) into a stats block.

    ``elapsed_by_index`` maps row index -> elapsed seconds for rows that
    actually called the model (manifest-replayed rows carry no call and are
    excluded — the same honesty rule as ``rows_with_usage``).
    """
    values = sorted(float(v) for v in (elapsed_by_index or {}).values() if v is not None)
    if not values:
        return None
    return {
        "n": len(values),
        "first_s": round(values[0], 4),
        "median_s": round(statistics.median(values), 4),
        "mean_s": round(statistics.mean(values), 4),
        "max_s": round(values[-1], 4),
    }


# ---------------------------------------------------------------------------
# The record block
# ---------------------------------------------------------------------------


def build_serving_block(
    *,
    model: str,
    prompt_versions: dict[str, str] | None = None,
    dataset_fingerprint: str | None = None,
    tokens: dict | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    duration_s: float | None = None,
    call_latency: dict | None = None,
    provider: str | None = None,
    endpoint: str | None = None,
    phase: str | None = None,
) -> dict:
    """Assemble the ``serving`` metadata block for a completed-run record.

    All values are derived network-free from env + taxonomy + the resolved
    prompts; ``provider`` / ``endpoint`` / ``phase`` may be pinned explicitly
    (the runners pass through what they know) or resolved from the env seam.
    """
    provider = provider or provider_from_base_url(resolve_openrouter_base_url())
    endpoint = endpoint or resolve_openrouter_base_url()
    phase = phase or phase_from_env()
    gpu = gpu_metadata(provider=provider)
    tokens = tokens or {}

    timing: dict[str, Any] = {}
    if started_at:
        timing["started_at"] = started_at
    if finished_at:
        timing["finished_at"] = finished_at
    if duration_s is not None:
        timing["duration_s"] = round(float(duration_s), 4)
    if call_latency:
        timing["call_latency_s"] = call_latency

    return {
        "provider": provider,
        "endpoint": endpoint,
        "model": model_identity(model, provider=provider),
        "prompt_fingerprints": prompt_fingerprints(prompt_versions or {}),
        "dataset_fingerprint": dataset_fingerprint,
        "tokens": {
            "prompt_tokens": tokens.get("prompt_tokens"),
            "completion_tokens": tokens.get("completion_tokens"),
            "total_tokens": tokens.get("total_tokens"),
        },
        "timing": timing,
        "gpu": gpu,
        "price_basis": price_basis(
            model, provider=provider, gpu_meta=gpu,
            duration_s=duration_s, tokens=tokens),
        "phase": phase,
    }