"""Network-free tests for the interactive experiment-flow wizard (KANBAN-109).

``scripts/eval/experiment_flow.py`` is a thin interactive wizard over pure
functions: config schema + validation, plan/command building, per-phase env
maps, record pairing (fingerprint verification + rejection), redaction,
spend-cap gating, and a subprocess shim that touches the llm-dojo-scoring
package ONLY at runtime. Nothing here imports the scoring package, calls the
network, or launches a subprocess — ``dojo_call``'s runner is stubbed.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

import scripts.eval.experiment_flow as flow


def _cfg(**overrides) -> dict:
    cfg = flow._valid_cfg_defaults()
    cfg.update(overrides)
    return cfg


def _api_record(*, fp="fp-abc", version="sorter_v3", sha="aa", model="qwen/qwen3-8b",
                cost=0.0001, prompt_tokens=1000, completion_tokens=500) -> dict:
    return {
        "model": model,
        "experiment_name": "api_run",
        "prompt_versions": {"sorter": version},
        "serving": {
            "provider": "openrouter",
            "endpoint": "https://openrouter.ai/api/v1",
            "dataset_fingerprint": fp,
            "prompt_fingerprints": {"sorter": {"version": version, "sha256": sha}},
            "tokens": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                       "total_tokens": prompt_tokens + completion_tokens},
        },
        "data_source": {"dataset_fingerprint": fp, "sample_requested": 40, "seed": 42},
        "tokens": {"total": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                             "total_tokens": prompt_tokens + completion_tokens,
                             "cost_total_usd": cost}},
        "scores": {"n_rows": 40},
        "results": [{}] * 40,
    }


def _modal_record(*, fp="fp-abc", version="sorter_v3", sha="aa", model="Qwen/Qwen3-8B",
                  duration_s=300.0) -> dict:
    return {
        "model": model,
        "experiment_name": "modal_run",
        "prompt_versions": {"sorter": version},
        "serving": {
            "provider": "modal",
            "endpoint": "https://ws--entity-vllm-serve.modal.run/v1",
            "dataset_fingerprint": fp,
            "prompt_fingerprints": {"sorter": {"version": version, "sha256": sha}},
            "tokens": {"prompt_tokens": 2000, "completion_tokens": 1000, "total_tokens": 3000},
            "timing": {"duration_s": duration_s},
            "gpu": {"gpu": "L4", "gpu_hourly_usd": 0.5},
        },
        "data_source": {"dataset_fingerprint": fp, "sample_requested": 40, "seed": 42},
        "tokens": {"total": {"prompt_tokens": 2000, "completion_tokens": 1000,
                             "total_tokens": 3000, "cost_total_usd": 0.0}},
        "scores": {"n_rows": 40},
        "results": [{}] * 40,
    }


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_valid_default_config_passes():
    assert flow.validate_config(_cfg()) == []


def test_validate_leg_and_dataset_source():
    assert "leg must be one of" in flow.validate_leg("bogus")
    assert flow.validate_leg("both") is None
    assert "dataset source must be one of" in flow.validate_dataset_source("nope")
    assert flow.validate_dataset_source("hf") is None


def test_validate_model_slugs():
    assert flow.validate_model_openrouter("qwen/qwen3-8b") is None
    assert "model slug is expected" in flow.validate_model_openrouter("qwen3-8b")
    assert flow.validate_model_modal("Qwen/Qwen3-8B") is None
    assert "checkpoint id is expected" in flow.validate_model_modal("Qwen3-8B")
    assert "unsupported characters" in flow.validate_model_openrouter("qwen/hello world")


def test_validate_prompt_version_rejects_unknown():
    assert flow.validate_prompt_version("sorter_v3") is None
    assert "unknown prompt version" in flow.validate_prompt_version("definitely-not-real-v99")


def test_validate_numeric_ranges():
    assert flow.validate_sample("40") is None
    assert "must be between" in flow.validate_sample("-5")
    assert flow.validate_seed("42") is None
    assert "must be an integer" in flow.validate_seed("abc")
    assert flow.validate_max_concurrency("") is None
    assert flow.validate_max_concurrency(None) is None
    assert flow.validate_max_concurrency("8") is None
    assert "must be between" in flow.validate_max_concurrency("0")
    assert flow.validate_hourly_rate("0.5") is None
    assert "positive" in flow.validate_hourly_rate("0")
    assert flow.validate_spend_cap("5.0") is None
    assert "positive" in flow.validate_spend_cap("-1")
    assert flow.validate_gpu("L4") is None
    assert "GPU must be one of" in flow.validate_gpu("A5000")


def test_validate_config_requires_leg_appropriate_fields():
    problems = flow.validate_config(_cfg(leg="openrouter", openrouter_api_key=""))
    assert any("openrouter_api_key is required" in p for p in problems)

    problems = flow.validate_config(_cfg(leg="modal", modal_endpoint_url="not-a-url"))
    assert any("http(s) URL" in p for p in problems)

    problems = flow.validate_config(_cfg(leg="modal", modal_api_token=""))
    assert any("modal_api_token is required" in p for p in problems)

    cfg = _cfg(leg="both", experiment_name_api="same", experiment_name_modal="same")
    assert any("experiment names must differ" in p for p in flow.validate_config(cfg))


def test_validate_config_hf_knobs():
    cfg = _cfg(dataset_source="hf", hf_dataset="")
    assert any("HF dataset id is required" in p for p in flow.validate_config(cfg))
    cfg = _cfg(dataset_source="local")
    assert flow.validate_config(cfg) == []


# ---------------------------------------------------------------------------
# ASK phase wiring + re-prompt on invalid
# ---------------------------------------------------------------------------


def _both_answers():
    return iter([
        "both",                            # leg
        "sk-or-1234567890",                # openrouter key (getpass)
        "not-a-url",                       # modal endpoint (INVALID -> re-prompt)
        "https://ws--entity-vllm-serve.modal.run/v1",  # modal endpoint (valid)
        "tk-modal-1234567890",             # modal token (getpass)
        "qwen/qwen3-8b", "Qwen/Qwen3-8B",  # api + modal models
        "sorter_v3",                       # prompt version
        "hf",                              # dataset source
        "", "", "",                        # hf dataset/config/revision defaults
        "10",                              # sample
        "42",                              # seed
        "",                                # max concurrency -> auto (None)
        "",                                # gpu default L4
        "",                                # hourly rate default 0.5
        "2.5",                             # spend cap
        "", "",                            # experiment names -> defaults
    ])


def test_ask_config_wires_all_fields_and_reprompts_on_invalid(capsys):
    answers = _both_answers()
    cfg = flow.ask_config(input_fn=lambda _p: next(answers),
                          getpass_fn=lambda _p: next(answers))
    assert flow.validate_config(cfg) == []
    assert cfg["leg"] == "both"
    assert cfg["modal_endpoint_url"] == "https://ws--entity-vllm-serve.modal.run/v1"
    assert cfg["sample"] == 10
    assert cfg["seed"] == 42
    assert cfg["max_concurrency"] is None
    assert cfg["spend_cap_usd"] == 2.5
    assert cfg["experiment_name_api"] == flow.default_experiment_name(cfg, "openrouter")
    assert cfg["experiment_name_modal"] == flow.default_experiment_name(cfg, "modal")
    assert "please try again" in capsys.readouterr().out


def test_ask_config_never_echoes_secrets(capsys):
    answers = _both_answers()
    cfg = flow.ask_config(input_fn=lambda _p: next(answers),
                          getpass_fn=lambda _p: next(answers))
    captured = capsys.readouterr().out
    assert "sk-or-1234567890" not in captured
    assert "tk-modal-1234567890" not in captured
    assert cfg["openrouter_api_key"] == "sk-or-1234567890"
    assert cfg["modal_api_token"] == "tk-modal-1234567890"


# ---------------------------------------------------------------------------
# Plan / preview command building
# ---------------------------------------------------------------------------


def test_build_plan_both_leg_has_four_phases():
    steps = flow.build_plan(_cfg(leg="both"))
    assert [s.id for s in steps] == ["modal_cold_smoke", "modal_warmup",
                                     "modal_warm_sample", "openrouter_baseline"]
    assert all(s.paid for s in steps)
    assert [s.phase for s in steps] == [flow.PHASE_COLD, flow.PHASE_WARM,
                                        flow.PHASE_WARM, flow.PHASE_OPENROUTER]


def test_build_plan_openrouter_leg_is_single_baseline():
    steps = flow.build_plan(_cfg(leg="openrouter"))
    assert [s.id for s in steps] == ["openrouter_baseline"]
    assert steps[0].kind == flow.KIND_DOC_EVAL
    assert "qwen/qwen3-8b" in steps[0].cmd
    assert "--sample" in steps[0].cmd and "--seed" in steps[0].cmd


def test_build_plan_modal_leg_has_three_steps():
    steps = flow.build_plan(_cfg(leg="modal"))
    assert [s.id for s in steps] == ["modal_cold_smoke", "modal_warmup",
                                     "modal_warm_sample"]
    assert all("--enable-paid-run" in s.cmd for s in steps[:2])
    assert "Qwen/Qwen3-8B" in steps[2].cmd
    assert "--experiment-name" in steps[2].cmd


def test_guided_and_docclass_command_building():
    cfg = _cfg()
    smoke = flow.build_guided_command(cfg, "smoke")
    assert "--profile" in smoke and "smoke" in smoke
    assert "--enable-paid-run" in smoke and "--gpu" in smoke and "--gpu-hourly-rate" in smoke
    assert "--dry-run" in flow.build_guided_command(cfg, "smoke", dry_run=True)

    doc = flow.build_docclass_command(cfg, experiment_name="exp_x", model="qwen/qwen3-8b")
    joined = " ".join(doc)
    assert "--prompt-version sorter_v3" in joined
    assert "--dataset-source hf" in joined
    assert "--sample 40" in joined and "--seed 42" in joined
    assert "--experiment-name exp_x" in joined
    assert "--max-concurrency 8" in joined


def test_docclass_command_hf_knobs():
    cfg = _cfg(hf_revision="abc123")
    joined = " ".join(flow.build_docclass_command(cfg, experiment_name="x", model="m"))
    assert "--hf-dataset Lucius-Morningstar/mailroom-corpus" in joined
    assert "--hf-config ground_truth" in joined
    assert "--hf-revision abc123" in joined


def test_preview_text_lists_steps_and_redacts_secrets():
    cfg = _cfg(leg="both", openrouter_api_key="sk-or-secret-abcdef123456", sample=10)
    preview = flow.preview_text(cfg, flow.build_plan(cfg))
    assert "STEP 1" in preview and "STEP 4" in preview
    assert "sk-or-secret-abcdef123456" not in preview
    assert "<redacted>" in preview
    assert "TOTAL estimated max spend" in preview


def test_estimate_max_spend():
    cfg = _cfg(gpu_hourly_usd=0.5)
    steps = {s.id: s for s in flow.build_plan(_cfg(leg="modal"))}
    assert steps["modal_cold_smoke"].est_max_spend_usd == 0.17
    assert steps["modal_warmup"].est_max_spend_usd == 0.25
    # Modal Qwen3-8B has no OpenRouter price in the taxonomy -> honest unknown.
    assert steps["modal_warm_sample"].est_max_spend_usd is None


# ---------------------------------------------------------------------------
# Env-per-phase maps
# ---------------------------------------------------------------------------


def test_env_cold_smoke():
    env = flow.build_plan_env(leg="modal", phase=flow.PHASE_COLD,
                              kind=flow.KIND_GUIDED_SMOKE, cfg=_cfg())
    assert env["SERVING_PHASE"] == "cold"
    assert env["BENCH_GPU"] == "L4"
    assert env["BENCH_GPU_HOURLY_USD"] == "0.5"
    assert "OPENROUTER_BASE_URL" not in env


def test_env_warmup_modal():
    env = flow.build_plan_env(leg="modal", phase=flow.PHASE_WARM,
                              kind=flow.KIND_GUIDED_PILOT, cfg=_cfg())
    assert env["SERVING_PHASE"] == "warm"
    assert env["BENCH_GPU"] == "L4"
    assert "OPENROUTER_BASE_URL" not in env


def test_env_warm_sample_modal():
    cfg = _cfg(modal_api_token="tk-modal-token-abcdef123456")
    env = flow.build_plan_env(leg="modal", phase=flow.PHASE_WARM,
                              kind=flow.KIND_DOC_EVAL, cfg=cfg)
    assert env["SERVING_PHASE"] == "warm"
    assert env["OPENROUTER_BASE_URL"] == cfg["modal_endpoint_url"]
    assert env["OPENROUTER_API_KEY"] == "tk-modal-token-abcdef123456"
    assert env["MODAL_VLLM_MODEL"] == "Qwen/Qwen3-8B"
    assert env["MODAL_VLLM_GPU"] == "L4"


def test_env_openrouter_baseline_unsets_phase():
    cfg = _cfg(openrouter_api_key="sk-or-key-abcdef123456")
    env = flow.build_plan_env(leg="openrouter", phase=flow.PHASE_OPENROUTER,
                              kind=flow.KIND_DOC_EVAL, cfg=cfg)
    assert env["SERVING_PHASE"] == ""          # unset marker
    assert env["OPENROUTER_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert env["OPENROUTER_API_KEY"] == "sk-or-key-abcdef123456"
    assert "BENCH_GPU" not in env


def test_env_for_step_drops_unset_phase():
    cfg = _cfg(leg="both")
    step = flow.build_plan(cfg)[-1]  # openrouter baseline
    env = flow.env_for_step(step, cfg, base_env={})
    assert "SERVING_PHASE" not in env
    assert env["OPENROUTER_BASE_URL"] == "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_redact_patterns_and_custom_secrets():
    text = "key=sk-live-key-abcdef123456 bearer Bearer tok-abc token:xyz"
    assert "<redacted>" in flow.redact(text)
    assert "sk-live-key-abcdef123456" not in flow.redact(text)
    custom = "tk-my-custom-token-abcdef123456"
    assert flow.redact(f"value {custom}", (custom,)) == "value <redacted>"


def test_redacted_env_masks_secrets():
    cfg = _cfg(openrouter_api_key="sk-or-key-abcdef123456", modal_api_token="tk-m-abcdef123456")
    env = flow.redacted_env({"OPENROUTER_API_KEY": cfg["openrouter_api_key"],
                             "MODAL_VLLM_MODEL": "Qwen/Qwen3-8B"},
                            flow.secret_values(cfg))
    assert env["OPENROUTER_API_KEY"] == "<redacted>"
    assert env["MODAL_VLLM_MODEL"] == "Qwen/Qwen3-8B"


# ---------------------------------------------------------------------------
# Spend-cap gating
# ---------------------------------------------------------------------------


def test_spend_cap_within_cap():
    ok, msg = flow.spend_cap_check(0.0, 0.17, 5.0)
    assert ok is True
    assert "within cap" in msg


def test_spend_cap_exceeded():
    ok, msg = flow.spend_cap_check(5.0, 1.0, 5.0)
    assert ok is False
    assert "REFUSED" in msg and "exceeds cap" in msg


def test_spend_cap_unavailable_estimate_not_enforced():
    ok, msg = flow.spend_cap_check(0.0, None, 5.0)
    assert ok is True
    assert "unavailable" in msg


def test_spend_cap_none_configured():
    ok, msg = flow.spend_cap_check(0.0, 1.0, None)
    assert ok is True
    assert "no spend cap" in msg


def test_cumulative_max_spend():
    steps = flow.build_plan(_cfg(leg="modal"))
    total, unknown = flow.cumulative_max_spend(steps)
    assert total == pytest.approx(0.17 + 0.25)
    assert unknown is True  # the modal warm sample has no price


# ---------------------------------------------------------------------------
# Record pairing — fingerprint verification + rejection
# ---------------------------------------------------------------------------


def test_verify_pair_valid():
    assert flow.verify_pair(_api_record(), _modal_record()) == []


def test_verify_pair_rejects_mismatched_dataset_fingerprint():
    problems = flow.verify_pair(_api_record(fp="fp-a"), _modal_record(fp="fp-b"))
    assert any("dataset fingerprint mismatch" in p for p in problems)


def test_verify_pair_rejects_mismatched_prompt_version():
    problems = flow.verify_pair(_api_record(version="sorter_v3"),
                                _modal_record(version="sorter_v4"))
    assert any("prompt version mismatch" in p for p in problems)


def test_verify_pair_rejects_mismatched_prompt_sha():
    problems = flow.verify_pair(_api_record(sha="aa"), _modal_record(sha="bb"))
    assert any("prompt byte fingerprint mismatch" in p for p in problems)


def test_verify_pair_rejects_wrong_provider_roles():
    api = _api_record()
    modal = _modal_record()
    problems = flow.verify_pair(modal, api)  # roles swapped
    assert any("expected 'openrouter'" in p for p in problems)
    assert any("expected 'modal'" in p for p in problems)


def test_verify_pair_falls_back_to_data_source_when_no_serving():
    api = _api_record()
    modal = _modal_record()
    for record in (api, modal):
        record.pop("serving")
    # Without serving metadata the modal side is still identified by its HF
    # checkpoint model string, but the api side cannot be confirmed as
    # openrouter — the honest verdict is a provider problem, never a guess.
    problems = flow.verify_pair(api, modal)
    assert any("expected 'openrouter'" in p for p in problems)
    # Fingerprint verification still works through the data_source fallback.
    assert flow.verify_pair(_api_record(fp="fp-a", model="Qwen/Qwen3-8B"),
                            _modal_record(fp="fp-b")) != []
    problems = flow.verify_pair(_api_record(fp="fp-a", model="Qwen/Qwen3-8B"),
                                _modal_record(fp="fp-b"))
    assert any("dataset fingerprint mismatch" in p for p in problems)
    # A serving-less modal record is still recognized as modal by its model.
    assert flow.record_provider({"model": "Qwen/Qwen3-8B"}) == "modal"


def test_record_provider_from_endpoint_and_model_guess():
    assert flow.record_provider(_api_record()) == "openrouter"
    assert flow.record_provider(_modal_record()) == "modal"
    guess = {"model": "Qwen/Qwen3-8B"}
    assert flow.record_provider(guess) == "modal"
    assert flow.record_provider({"model": "qwen/qwen3-8b"}) == "other"


def test_find_matching_pair_selects_valid_and_ignores_mismatched():
    good_api, good_modal = _api_record(fp="fp-x"), _modal_record(fp="fp-x")
    bad_api, bad_modal = _api_record(fp="fp-a"), _modal_record(fp="fp-b")
    pair = flow.find_matching_pair([bad_modal, good_api, bad_api, good_modal])
    assert pair is not None
    assert pair["api"] is good_api and pair["modal"] is good_modal
    assert pair["problems"] == []


def test_find_matching_pair_none_when_all_mismatched():
    records = [_api_record(fp="fp-a"), _modal_record(fp="fp-b")]
    assert flow.find_matching_pair(records) is None
    assert flow.find_matching_pair([]) is None


# ---------------------------------------------------------------------------
# Compare ops + dojo subprocess shim (stubbed runner)
# ---------------------------------------------------------------------------


def test_build_compare_ops_shape():
    cfg = _cfg()
    ops = flow.build_compare_ops(_api_record(), _modal_record(), cfg,
                                 cold_start_seconds=120.0)
    by_id = {op["id"]: op for op in ops}
    assert by_id["api_price"]["fn"] == "cost.price_for"
    assert by_id["api_price"]["params"]["model"] == "qwen/qwen3-8b"
    assert by_id["api_breakdown"]["params"]["prompt_tokens"] == 1000
    assert by_id["modal_billed"]["params"]["metrics"]["gpu_type"] == "L4"
    assert by_id["modal_billed"]["params"]["metrics"]["generation_time_sec"] == 300.0
    assert by_id["cold_amortization"]["params"]["cold_start_seconds"] == 120.0
    assert by_id["break_even"]["params"]["api_cost_usd"] == 0.0001
    assert by_id["modal_tps"]["params"]["total_tokens"] == 3000


def test_dojo_call_forwards_to_stubbed_runner():
    captured = {}

    def fake_runner(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps([{"id": "api_price", "ok": True,
                                         "result": {"input_per_million": 0.03}}]),
            stderr="")

    results = flow.dojo_call([{"id": "api_price", "fn": "cost.price_for",
                               "params": {"model": "qwen/qwen3-8b"}}],
                             python_exe="py313", scoring_path="C:/scoring",
                             runner=fake_runner)
    assert results[0]["result"] == {"input_per_million": 0.03}
    argv = captured["argv"]
    assert argv[0] == "py313"
    assert argv[1].endswith(".py")           # the shim temp file
    assert argv[2] == "C:/scoring"
    assert json.loads(captured["kwargs"]["input"])[0]["id"] == "api_price"
    assert "C:/scoring" in captured["kwargs"]["env"]["PYTHONPATH"]
    assert captured["kwargs"]["env"]["PYTHONUTF8"] == "1"


def test_dojo_call_raises_on_nonzero_exit():
    def fake_runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")

    with pytest.raises(RuntimeError, match="exited 1"):
        flow.dojo_call([{"id": "x", "fn": "cost.price_for", "params": {}}],
                       python_exe="py", scoring_path="S", runner=fake_runner)


def test_dojo_call_empty_ops_skips_runner():
    called = []

    def fake_runner(argv, **kwargs):
        called.append(argv)
        raise AssertionError("should not be called")

    assert flow.dojo_call([], runner=fake_runner) == []
    assert called == []


def test_format_compare_report_has_break_even_sketch():
    cfg = _cfg()
    api = _api_record()
    modal = _modal_record()
    ops = flow.build_compare_ops(api, modal, cfg, cold_start_seconds=120.0)
    results = [
        {"id": "api_price", "ok": True, "result": {"input_per_million": 0.03,
                                                   "output_per_million": 0.13}},
        {"id": "api_breakdown", "ok": True, "result": {"input_cost_per_token": 3e-8,
                                                       "output_cost_per_token": 1.3e-7,
                                                       "total_cost_per_token": 6.33e-8}},
        {"id": "api_estimate", "ok": True, "result": 9.5e-5},
        {"id": "modal_price", "ok": True, "result": None},
        {"id": "modal_billed", "ok": True, "result": 0.0416667},
        {"id": "cold_amortization", "ok": True, "result": 0.000417},
        {"id": "modal_tps", "ok": True, "result": 7.14},
        {"id": "break_even", "ok": True, "result": {"savings_usd": -0.0415,
                                                    "api_vs_gpu_savings_pct": -41566.0,
                                                    "api_per_million_usd": 0.0333,
                                                    "gpu_per_million_usd": 13.889,
                                                    "effective_tokens_per_sec": 7.14,
                                                    "billed_cold_start_seconds": 120.0}},
    ]
    report = flow.format_compare_report(api, modal, ops, results, cfg)
    assert "COST COMPARISON" in report
    assert "Break-even sketch" in report
    assert "$0.041667" in report
    assert "per-run cold-start cost" in report


def test_format_compare_report_unknown_markers_on_missing():
    cfg = _cfg()
    api = _api_record()
    modal = _modal_record()
    ops = flow.build_compare_ops(api, modal, cfg)
    results = [{"id": op["id"], "ok": False, "result": None,
                "reason": f"{op['id']} failed"} for op in ops]
    report = flow.format_compare_report(api, modal, ops, results, cfg)
    assert "N/A" in report
    assert "failed" in report