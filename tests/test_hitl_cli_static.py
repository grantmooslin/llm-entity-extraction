"""KANBAN-108 — HITL Modal vLLM benchmark CLI static tests.

Network-free by construction: ``modal/vllm_server.py`` +
``modal/benchmark_throughput.py`` are loaded with a stubbed ``modal`` module
(the real SDK is a deploy-time extra; importing it must never deploy
anything), and ``scripts/eval/guided_vllm_benchmark.py`` is parsed/imported
directly — it imports only stdlib. These pins cover the controller -> runner
env-knob contract, the ``vllm bench serve`` argv shape, the sibling-import /
image-packaging regression, and the modal SDK 1.5.4 finding (no
``Secret.from_local`` anywhere in the three files).
"""

from __future__ import annotations

import ast
import importlib
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_DIR = REPO_ROOT / "modal"
VLLM_SERVER = MODAL_DIR / "vllm_server.py"
BENCH_THROUGHPUT = MODAL_DIR / "benchmark_throughput.py"
GUIDED = REPO_ROOT / "scripts" / "eval" / "guided_vllm_benchmark.py"
CLI_FILES = (VLLM_SERVER, BENCH_THROUGHPUT, GUIDED)

CONTROLLER_ENV_KNOBS = {
    "MODAL_APP_NAME",
    "MODAL_RUN_ID",
    "BENCH_GPU",
    "BENCH_GPU_HOURLY_USD",
    "MODAL_FUNCTION_TIMEOUT",
    "MODAL_STARTUP_TIMEOUT",
}


def _install_modal_stub() -> types.ModuleType:
    """Superset stand-in for the ``modal`` surface used by every app module in
    this repo (deploy/modal_vllm.py + the two modal/ CLI modules). Installed
    unconditionally so test order never matters; covers ``from_registry`` /
    ``uv_pip_install`` / ``add_local_dir`` / ``Secret.from_dict`` /
    ``App.server`` / ``modal.enter`` / ``modal.exit`` / ``web_server``."""
    add_local_dir_calls: list[tuple[str, str]] = []

    class _Secret:
        @staticmethod
        def from_dict(mapping):
            return ("secret", mapping)

    class _Volume:
        @staticmethod
        def from_name(name, create_if_missing=False):
            return ("volume", name)

    class _Image:
        @staticmethod
        def from_registry(ref, add_python=None):
            return _Image()

        def entrypoint(self, cmd):
            return self

        def run_commands(self, *cmds):
            return self

        def uv_pip_install(self, *pkgs):
            return self

        def env(self, mapping):
            return self

        def add_local_dir(self, local_path, remote_path=None, copy=False,
                          ignore=None):
            add_local_dir_calls.append((str(local_path), str(remote_path)))
            return self

    class _App:
        def __init__(self, name, image=None):
            self.name = name

        def function(self, **kwargs):
            def deco(fn):
                return fn

            return deco

        def local_entrypoint(self, fn=None):
            if fn is not None:
                return fn

            def deco(f):
                return f

            return deco

        def server(self, **kwargs):
            def deco(cls):
                return cls

            return deco

    def _deco_factory():
        def deco(fn):
            return fn

        return deco

    def _web_server(port=None, startup_timeout=None):
        def deco(fn):
            return fn

        return deco

    stub = types.ModuleType("modal")
    stub.__dict__.update(
        Secret=_Secret,
        Volume=_Volume,
        Image=_Image,
        App=_App,
        enter=_deco_factory,
        exit=_deco_factory,
        web_server=_web_server,
        _add_local_dir_calls=add_local_dir_calls,
    )
    sys.modules["modal"] = stub
    return stub


def _load_benchmark_throughput() -> types.ModuleType:
    """Import modal/benchmark_throughput.py under the stub modal, with the
    modal/ dir on sys.path so the sibling ``from vllm_server import ...``
    resolves through the SAME stubbed surface."""
    _install_modal_stub()
    sys.path.insert(0, str(MODAL_DIR))
    for name in ("benchmark_throughput", "vllm_server"):
        sys.modules.pop(name, None)
    try:
        mod = importlib.import_module("benchmark_throughput")
        return mod
    finally:
        sys.path.remove(str(MODAL_DIR))


def _load_guided() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("guided_vllm_benchmark", GUIDED)
    assert spec is not None and spec.loader is not None
    mod: types.ModuleType = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- SDK audit
class TestModalSdk145Audit:
    """modal SDK 1.5.4 removed ``Secret.from_local`` (the KANBAN-096 fix in
    deploy/modal_vllm.py). None of the three HITL CLI files may use it."""

    def test_no_secret_from_local_in_any_cli_file(self):
        for path in CLI_FILES:
            assert "from_local" not in path.read_text(encoding="utf-8"), (
                f"{path.name} must not call modal.Secret.from_local (removed "
                "in modal SDK 1.5.4)"
            )

    def test_cli_files_are_parseable_python(self):
        for path in CLI_FILES:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --------------------------------------------------- modal/ module imports
class TestVllmServerStatic:
    def test_vllm_server_imports_under_stub(self):
        mod = _load_benchmark_throughput()  # sibling import resolves vllm_server
        sys.modules.pop("vllm_server", None)

        _install_modal_stub()
        import importlib.util as _ilu

        spec = _ilu.spec_from_file_location("vllm_server_probe", VLLM_SERVER)
        assert spec is not None and spec.loader is not None
        vs: types.ModuleType = _ilu.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(vs)
        assert vs.MODEL_NAME == "Qwen/Qwen3-8B"
        assert vs.SERVED_MODEL_NAME == "qwen/qwen3-8b"

    def test_benchmark_image_packages_modal_dir(self):
        """KANBAN-095 hydration regression: the sibling ``modal/`` dir must be
        baked into the remote image at /root/modal (the prior paid run failed
        importing vllm_server remotely because it was absent)."""
        mod = _load_benchmark_throughput()
        stub = sys.modules["modal"]
        calls = stub._add_local_dir_calls
        assert calls, "vllm_image must add_local_dir the modal/ source dir"
        assert any(remote == "/root/modal" for _, remote in calls)

    def test_benchmark_resolves_sibling_hf_cache_and_image(self):
        mod = _load_benchmark_throughput()
        assert mod.hf_cache == ("volume", "huggingface-cache")
        assert mod.vllm_image is not None

    def test_benchmark_env_knobs_read_at_import(self, monkeypatch):
        monkeypatch.setenv("BENCH_GPU", "H100")
        monkeypatch.setenv("BENCH_GPU_HOURLY_USD", "4.00")
        monkeypatch.setenv("MODAL_APP_NAME", "llm-mailroom-benchmark-smoke-abc")
        monkeypatch.setenv("MODAL_RUN_ID", "smoke-abc123")
        monkeypatch.setenv("MODAL_FUNCTION_TIMEOUT", "1200")
        monkeypatch.setenv("MODAL_STARTUP_TIMEOUT", "600")
        mod = _load_benchmark_throughput()
        assert mod.BENCH_GPU == "H100"
        assert mod.BENCH_GPU_HOURLY_USD == 4.00
        assert mod.APP_NAME == "llm-mailroom-benchmark-smoke-abc"
        assert mod.RUN_ID == "smoke-abc123"
        assert mod.MODAL_FUNCTION_TIMEOUT == 1200
        assert mod.MODAL_STARTUP_TIMEOUT == 600

    def test_benchmark_command_shape(self):
        mod = _load_benchmark_throughput()
        cmd = mod.build_benchmark_command(
            served_model_name="qwen/qwen3-8b", tokenizer="Qwen/Qwen3-8B",
            base_url="http://127.0.0.1:8000", num_prompts=5,
            max_concurrency=2, input_len=64, output_len=32)
        assert cmd[:4] == ["vllm", "bench", "serve", "--backend"]
        assert cmd[cmd.index("--dataset-name") + 1] == "random"
        assert cmd[cmd.index("--num-prompts") + 1] == "5"
        assert cmd[cmd.index("--random-input-len") + 1] == "64"
        assert cmd[cmd.index("--random-output-len") + 1] == "32"
        assert "--trust-remote-code" in cmd


# --------------------------------------------------- guided controller static
class TestGuidedControllerStatic:
    def test_controller_imports_only_stdlib(self):
        """The controller must never import the modal SDK or repo modules —
        it shells out to the ``modal`` CLI, so the validate profile runs with
        zero third-party deps."""
        tree = ast.parse(GUIDED.read_text(encoding="utf-8"), filename=str(GUIDED))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module.split(".")[0])
        banned = {"modal", "src", "scripts", "agents", "llm_dojo"}
        assert not (banned & set(imported)), (
            f"controller must be stdlib-only, imports {sorted(banned & set(imported))}"
        )

    def test_controller_loads_without_modal(self, monkeypatch):
        monkeypatch.delenv("MODAL_APP_NAME", raising=False)
        mod = _load_guided()
        assert sorted(mod.PROFILES) == ["benchmark", "pilot", "smoke", "validate"]
        assert mod.BENCH_SCRIPT == MODAL_DIR / "benchmark_throughput.py"

    def test_build_env_sets_controller_knob_contract(self):
        mod = _load_guided()
        cfg = {
            "gpu": "L4", "gpu_hourly_rate": 0.50, "function_timeout": 3600,
            "startup_timeout": 900,
        }
        env = mod.build_env(cfg, "benchmark-a1b2c3", "llm-mailroom-benchmark-benchmark-a1b2c3")
        for knob in CONTROLLER_ENV_KNOBS:
            assert knob in env, f"controller must set {knob}"
        assert env["MODAL_APP_NAME"] == "llm-mailroom-benchmark-benchmark-a1b2c3"
        assert env["MODAL_RUN_ID"] == "benchmark-a1b2c3"
        assert env["BENCH_GPU"] == "L4"
        assert env["BENCH_GPU_HOURLY_USD"] == "0.5"
        assert env["MODAL_FUNCTION_TIMEOUT"] == "3600"
        assert env["MODAL_STARTUP_TIMEOUT"] == "900"
        assert env["PYTHONUTF8"] == "1"

    def test_controller_app_name_unique_per_run_id(self):
        mod = _load_guided()
        assert mod.make_app_name("smoke-a1b2c3") != mod._GENERIC_APP_NAME
        assert mod.make_app_name("smoke-a1b2c3") != mod.make_app_name("smoke-f4e5d6")

    def test_build_command_single_modal_run_child(self):
        mod = _load_guided()
        cfg = dict(mod.PROFILES["smoke"])
        cfg.update({
            "model": "Qwen/Qwen3-8B", "gpu": "L4", "gpu_hourly_rate": 0.50,
            "fast_boot": True, "gpu_memory_utilization": 0.95,
        })
        cmd = mod.build_command(
            cfg, "llm-mailroom-benchmark-smoke-a1b2c3",
            Path("reports/modal_runs/smoke-a1b2c3/result.json"), "smoke-a1b2c3")
        assert cmd[0] == "modal" and cmd[1] == "run"
        assert "-n" in cmd and "llm-mailroom-benchmark-smoke-a1b2c3" in cmd
        assert "--run-id" in cmd and cmd[cmd.index("--run-id") + 1] == "smoke-a1b2c3"
        assert str(BENCH_THROUGHPUT) in cmd
        assert "--result-path" in cmd
        assert "--fast-boot" in cmd
        assert cmd.count("run") == 1  # one child launch, never more

    def test_verify_approval_is_exact_phrase(self):
        mod = _load_guided()
        run_id = "smoke-a1b2c3"
        ceiling = 0.17
        phrase = f"RUN {run_id} MAX {mod.format_usd(ceiling)}"
        prompt = mod.approval_prompt(run_id, ceiling)
        assert prompt.endswith(phrase)
        assert mod.verify_approval(phrase, run_id, ceiling)
        assert mod.verify_approval("  " + phrase + "  ", run_id, ceiling)  # strip-tolerance
        assert not mod.verify_approval("RUN smoke-a1b2c3 MAX $0.18", run_id, ceiling)
        assert not mod.verify_approval("RUN smoke-a1b2c3", run_id, ceiling)
        assert not mod.verify_approval("", run_id, ceiling)
        assert mod.verify_approval("RUN smoke-a1b2c3 MAX $0.17", run_id, ceiling)

    def test_stage_line_parsing(self):
        mod = _load_guided()
        parsed = mod.parse_stage_line(
            "LLM_BENCH_STAGE 4 vLLM process started run=smoke-a1b2c3 t=12.5")
        assert parsed == {"n": 4, "name": "vLLM process started",
                          "run_id": "smoke-a1b2c3", "t": 12.5}
        assert mod.parse_stage_line("unrelated log line") is None

    def test_cost_ceiling_rounds_up_to_cent(self):
        mod = _load_guided()
        assert mod.compute_cost_ceiling(0.50, 1200) == 0.17  # 0.5*1/3 = 0.1667
        assert mod.format_usd(0.1667) == "$0.17"