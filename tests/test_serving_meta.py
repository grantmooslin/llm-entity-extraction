"""Network-free tests for the ``serving`` metadata block (KANBAN-106).

The block is what lets a completed OpenRouter run and a completed Modal-hosted
vLLM (Qwen3-8B) run be compared faithfully from the append-only experiment-log
records alone: provider, endpoint, model identity, prompt + dataset
fingerprints, token totals, timing, GPU metadata, price basis, and cold/warm
phase. All values derive from env knobs + the taxonomy + resolved prompt text
— nothing here touches the network.
"""

from __future__ import annotations

import json

import pytest

from src.serving_meta import (
    LOCAL_PROVIDER,
    MODAL_PROVIDER,
    OLLAMA_PROVIDER,
    OPENROUTER_PROVIDER,
    OTHER_PROVIDER,
    PHASE_COLD,
    PHASE_UNKNOWN,
    PHASE_WARM,
    build_serving_block,
    call_latency_stats,
    gpu_metadata,
    model_identity,
    phase_from_env,
    price_basis,
    prompt_fingerprint,
    prompt_fingerprints,
    provider_from_base_url,
)
from src.prompts import get_prompt

MODAL_URL = "https://ws--entity-vllm-serve.modal.run/v1"


def test_provider_from_base_url_classification():
    assert provider_from_base_url("https://openrouter.ai/api/v1") == OPENROUTER_PROVIDER
    assert provider_from_base_url(MODAL_URL) == MODAL_PROVIDER
    assert provider_from_base_url("https://acme--entity-vllm-serve.modal.run/v1") == MODAL_PROVIDER
    assert provider_from_base_url("http://localhost:11434/v1") == LOCAL_PROVIDER
    assert provider_from_base_url("http://127.0.0.1:8000/v1") == LOCAL_PROVIDER
    assert provider_from_base_url("http://ollama-host:11434") == OLLAMA_PROVIDER
    assert provider_from_base_url("https://some-other-gateway.example/v1") == OTHER_PROVIDER
    assert provider_from_base_url(None) == OTHER_PROVIDER
    assert provider_from_base_url("") == OTHER_PROVIDER


def test_prompt_fingerprint_is_deterministic_and_sensitive():
    prompt = get_prompt("sorter_v3")
    assert prompt_fingerprint(prompt) == prompt_fingerprint(prompt)
    assert prompt_fingerprint(prompt) != prompt_fingerprint(prompt + "x")


def test_prompt_fingerprints_resolves_versions(monkeypatch):
    fps = prompt_fingerprints({"sorter": "sorter_v3"})
    assert fps["sorter"]["version"] == "sorter_v3"
    assert fps["sorter"]["sha256"] == prompt_fingerprint(get_prompt("sorter_v3"))

    # Unknown versions are skipped, never fatal.
    assert prompt_fingerprints({"sorter": "definitely-not-a-version"}) == {}


def test_model_identity_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.delenv("MODAL_VLLM_MODEL", raising=False)
    identity = model_identity("qwen/qwen3.7-flash")
    assert identity == {"slug": "qwen/qwen3.7-flash"}


def test_model_identity_modal(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", MODAL_URL)
    monkeypatch.setenv("MODAL_VLLM_MODEL", "Qwen/Qwen3-8B")
    identity = model_identity("Qwen/Qwen3-8B")
    assert identity == {"slug": "Qwen/Qwen3-8B", "hf_model_id": "Qwen/Qwen3-8B"}


def test_gpu_metadata_openrouter_is_honest(monkeypatch):
    monkeypatch.delenv("MODAL_VLLM_GPU", raising=False)
    meta = gpu_metadata(provider=OPENROUTER_PROVIDER)
    assert meta["reported"] is False
    assert "gpu" not in meta  # never a guessed GPU


def test_gpu_metadata_modal_reads_deploy_knobs(monkeypatch):
    monkeypatch.setenv("MODAL_VLLM_GPU", "L4")
    monkeypatch.setenv("MODAL_VLLM_QUANTIZATION", "awq")
    monkeypatch.setenv("MODAL_VLLM_MAX_MODEL_LEN", "4096")
    monkeypatch.setenv("MODAL_VLLM_MODEL", "Qwen/Qwen3-8B")
    meta = gpu_metadata(provider=MODAL_PROVIDER)
    assert meta["reported"] is True
    assert meta["gpu"] == "L4"
    assert meta["quantization"] == "awq"
    assert meta["max_model_len"] == 4096
    assert meta["hf_model_id"] == "Qwen/Qwen3-8B"
    assert meta["gpu_hourly_usd"] == 0.5  # taxonomy L4 price


def test_price_basis_openrouter_priced_and_unpriced(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    basis = price_basis("qwen/qwen3.7-flash", provider=OPENROUTER_PROVIDER)
    assert basis["basis"] == ["per_token"]
    assert basis["per_token_usd"] == {"input_per_million": 0.03, "output_per_million": 0.13}
    assert "taxonomy:cost_models" in basis["source"]

    # An unpriced model is honest: provider_billed, never a fabricated number.
    basis = price_basis("some/unknown-model", provider=OPENROUTER_PROVIDER)
    assert basis["basis"] == ["provider_billed"]


def test_price_basis_modal_gpu_hourly_and_estimate(monkeypatch):
    monkeypatch.setenv("MODAL_VLLM_GPU", "L4")
    gpu_meta = {"gpu": "L4"}
    basis = price_basis("Qwen/Qwen3-8B", provider=MODAL_PROVIDER, gpu_meta=gpu_meta,
                        duration_s=3600.0, tokens={"cost_total_usd": 0.0})
    assert basis["basis"] == ["gpu_hourly"]
    assert basis["gpu_hourly_usd"] == 0.5
    assert basis["estimated_gpu_cost_usd"] == 0.5  # 0.5 $/h * 1h

    # Unknown GPU -> no hourly price, no estimate (honest, not guessed).
    basis = price_basis("Qwen/Qwen3-8B", provider=MODAL_PROVIDER,
                        gpu_meta={"gpu": "A5000"}, duration_s=60.0)
    assert "gpu_hourly_usd" not in basis
    assert "estimated_gpu_cost_usd" not in basis


def test_phase_from_env(monkeypatch):
    assert phase_from_env() == PHASE_UNKNOWN
    monkeypatch.setenv("SERVING_PHASE", "cold")
    assert phase_from_env() == PHASE_COLD
    monkeypatch.setenv("SERVING_PHASE", "WARM")
    assert phase_from_env() == PHASE_WARM
    monkeypatch.setenv("SERVING_PHASE", "garbage")
    assert phase_from_env() == PHASE_UNKNOWN


def test_call_latency_stats():
    stats = call_latency_stats({0: 0.7, 1: 0.5, 2: 0.6})
    assert stats == {"n": 3, "first_s": 0.5, "median_s": 0.6,
                     "mean_s": 0.6, "max_s": 0.7}
    assert call_latency_stats({}) is None
    assert call_latency_stats(None) is None


def test_build_serving_block_openrouter_full_shape(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.delenv("SERVING_PHASE", raising=False)
    block = build_serving_block(
        model="qwen/qwen3.7-flash",
        prompt_versions={"sorter": "sorter_v3"},
        dataset_fingerprint="fp-123",
        tokens={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                "cost_total_usd": 0.001},
        started_at="2026-09-03T00:00:00Z",
        finished_at="2026-09-03T00:01:00Z",
        duration_s=60.0,
        call_latency=call_latency_stats({0: 0.5, 1: 0.7}),
    )
    assert block["provider"] == OPENROUTER_PROVIDER
    assert block["endpoint"] == "https://openrouter.ai/api/v1"
    assert block["model"] == {"slug": "qwen/qwen3.7-flash"}
    assert block["prompt_fingerprints"]["sorter"]["sha256"] == \
        prompt_fingerprint(get_prompt("sorter_v3"))
    assert block["dataset_fingerprint"] == "fp-123"
    assert block["tokens"] == {"prompt_tokens": 100, "completion_tokens": 20,
                               "total_tokens": 120}
    assert block["timing"]["duration_s"] == 60.0
    assert block["timing"]["call_latency_s"]["n"] == 2
    assert block["gpu"]["reported"] is False
    assert block["price_basis"]["per_token_usd"]["input_per_million"] == 0.03
    assert block["phase"] == PHASE_UNKNOWN


def test_build_serving_block_modal_explicit_overrides(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("MODAL_VLLM_MODEL", "Qwen/Qwen3-8B")
    monkeypatch.setenv("MODAL_VLLM_GPU", "L4")
    monkeypatch.setenv("SERVING_PHASE", "cold")
    block = build_serving_block(
        model="Qwen/Qwen3-8B",
        prompt_versions={"sorter": "sorter_v3"},
        dataset_fingerprint="fp-456",
        provider=MODAL_PROVIDER,
        endpoint=MODAL_URL,
        phase=PHASE_COLD,
        duration_s=600.0,
        tokens={"cost_total_usd": 0.0},
    )
    assert block["provider"] == MODAL_PROVIDER
    assert block["endpoint"] == MODAL_URL
    assert block["model"] == {"slug": "Qwen/Qwen3-8B", "hf_model_id": "Qwen/Qwen3-8B"}
    assert block["gpu"]["reported"] is True
    assert block["gpu"]["gpu"] == "L4"
    assert block["price_basis"]["estimated_gpu_cost_usd"] == round(0.5 * 600.0 / 3600.0, 6)
    assert block["phase"] == PHASE_COLD


def test_record_carries_serving_block(monkeypatch, tmp_path):
    """End-to-end: the subtype runner's append-only experiment-log record
    carries the serving block with provider/fingerprints/timing present."""
    import scripts.eval.run_subtype_eval as runner

    monkeypatch.setenv("LANGSMITH_TRACING", "0")

    dataset = {
        "input": {"doc_text": "This Agreement between Acme and Beta is a license agreement.",
                  "filename": "cuad_doc_01.txt", "expected": "contract",
                  "metadata": {"category": "License_Agreements"}},
        "expected": "contract",
        "filename": "cuad_doc_01.txt",
        "doc_text": "This Agreement between Acme and Beta is a license agreement.",
        "metadata": {"category": "License_Agreements"},
    }
    monkeypatch.setattr(runner, "require_env", lambda *names: tuple("fake-key" for _ in names))
    monkeypatch.setattr("scripts.eval.run_subtype_eval.load_braintrust_dataset",
                        lambda *a, **k: [dict(dataset)])

    def fake_classify_json(self, doc_text):
        self._last_usage = {"prompt_tokens": 10, "completion_tokens": 2,
                            "total_tokens": 12, "cost": 0.0001}
        return {"doc_type": "contract", "contract_subtype": "license",
                "confidence": 0.95, "reasoning": "license agreement"}

    monkeypatch.setattr("agents.sorter_agent.SorterAgent.classify_json", fake_classify_json)

    rc = runner.main_with_args([
        "--dataset", "mailroom-cuad-contracts",
        "--sorter-prompt-version", "sorter_v3",
        "--experiment-name", "smoke_serving_block",
        "--project-id", "proj-test-0000",
        "--experiment-log", str(tmp_path / "exp.jsonl"),
    ])
    assert rc == 0

    record = json.loads(next(iter(open(tmp_path / "exp.jsonl"))))
    serving = record["serving"]
    assert serving["provider"] == OPENROUTER_PROVIDER
    assert serving["endpoint"] == "https://openrouter.ai/api/v1"
    assert serving["model"]["slug"] == "qwen/qwen3.7-flash"
    assert serving["prompt_fingerprints"]["sorter"]["version"] == "sorter_v3"
    assert serving["dataset_fingerprint"] == record["data_source"]["dataset_fingerprint"]
    assert serving["tokens"]["prompt_tokens"] == 10
    assert serving["tokens"]["total_tokens"] == 12
    assert serving["timing"]["duration_s"] is not None
    assert serving["timing"]["call_latency_s"]["n"] == 1
    assert serving["gpu"]["reported"] is False
    assert serving["price_basis"]["per_token_usd"]["input_per_million"] == 0.03
    assert serving["phase"] == PHASE_UNKNOWN