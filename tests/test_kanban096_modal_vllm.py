"""KANBAN-096 — Modal+vLLM serving capability tests (entity side).

Network-free by construction:
- deploy/modal_vllm.py is loaded with a stubbed ``modal`` module (the real one
  is a deploy-time extra, never installed in the runtime venv);
- provider-seam tests exercise src/openrouter_utils.py / agents/base_agent.py /
  src/classifier.py directly with monkeypatched env and a captured
  requests.post — no HTTP, no server, no API keys;
- dependency-manifest pins enforce the KANBAN-081 batch law for the new
  [deploy] extra.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_APP = REPO_ROOT / "deploy" / "modal_vllm.py"
MAILROOM_ROOT = REPO_ROOT.parent / "llm-mailroom"

# Canonical 1x1 PNG (no Pillow needed, nothing network-fetched).
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9c\xf8\xcf\xc0"
    b"\xf1\x8f\x00\x00\x00\x19\x00\x05\xfbl\xd7\xe2\x00\x00\x00\x00IEND"
    b"\xaeB`\x82"
)


def _install_modal_stub() -> None:
    """Minimal stand-in for the ``modal`` module surface used by the app."""
    if "modal" in sys.modules:
        return

    class _Secret:
        @staticmethod
        def from_local(*names):
            return ("secret", names)

    class _Volume:
        @staticmethod
        def from_name(name, create_if_missing=False):
            return ("volume", name)

    class _Image:
        @staticmethod
        def from_registry(ref, add_python=None):
            return _Image()

        def run_commands(self, *cmds):
            return self

        def env(self, mapping):
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
        web_server=_web_server,
    )
    sys.modules["modal"] = stub


def _load_app_module() -> types.ModuleType:
    _install_modal_stub()
    spec = importlib.util.spec_from_file_location("entity_modal_vllm", DEPLOY_APP)
    assert spec is not None and spec.loader is not None
    mod: types.ModuleType = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------- app file
class TestModalVllmApp:
    def test_app_file_exists(self):
        assert DEPLOY_APP.is_file(), "deploy/modal_vllm.py missing"

    def test_command_defaults(self):
        mod = _load_app_module()
        cmd = mod.build_vllm_command("Qwen/Qwen3-8B")
        assert cmd[:3] == ["vllm", "serve", "Qwen/Qwen3-8B"]
        assert "--host" in cmd and cmd[cmd.index("--host") + 1] == "0.0.0.0"
        assert "--port" in cmd and cmd[cmd.index("--port") + 1] == str(mod.SERVER_PORT)
        assert "--max-model-len" in cmd
        # fp16 default: no quantization flag unless configured
        assert "--quantization" not in cmd

    def test_quantization_flag_injected_when_configured(self):
        mod = _load_app_module()
        original = mod.QUANTIZATION
        try:
            mod.QUANTIZATION = "awq"
            cmd = mod.build_vllm_command("Qwen/Qwen3-14B")
            assert "--quantization" in cmd
            assert cmd[cmd.index("--quantization") + 1] == "awq"
        finally:
            mod.QUANTIZATION = original

    def test_api_token_maps_to_vllm_enforcement_var(self, monkeypatch):
        mod = _load_app_module()
        monkeypatch.setenv("MODAL_VLLM_API_TOKEN", "tok-abc123")
        assert mod._server_env()["VLLM_API_KEY"] == "tok-abc123"

    def test_no_token_means_keyless_server(self, monkeypatch):
        mod = _load_app_module()
        monkeypatch.delenv("MODAL_VLLM_API_TOKEN", raising=False)
        assert "VLLM_API_KEY" not in mod._server_env()

    def test_hf_token_passthrough_for_gated_repos(self, monkeypatch):
        mod = _load_app_module()
        monkeypatch.setenv("HF_TOKEN", "hf_xxx")
        assert mod._server_env()["HF_TOKEN"] == "hf_xxx"
        monkeypatch.delenv("HF_TOKEN")
        assert "HF_TOKEN" not in mod._server_env()

    def test_distinct_app_identity_from_mailroom_sibling(self):
        """Same knob contract, separate Modal app + volume per pipeline."""
        mod = _load_app_module()
        assert mod.APP_NAME != "mailroom-vllm"
        assert mod.HF_CACHE_VOLUME_NAME != "mailroom-hf-cache"


# ------------------------------------------------------------- provider seam
class TestProviderSeam:
    """OPENROUTER_BASE_URL must resolve AT CLIENT-BUILD TIME (KANBAN-096 fix):

    import-time binding silently ignored dotenv-set values because
    src.env_utils.load_env() runs lazily right before client construction.
    """

    def test_default_base_url_is_openrouter(self, monkeypatch):
        from src.openrouter_utils import DEFAULT_OPENROUTER_BASE_URL
        from src.openrouter_utils import resolve_openrouter_base_url

        monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
        assert (
            resolve_openrouter_base_url() == "https://openrouter.ai/api/v1"
            == DEFAULT_OPENROUTER_BASE_URL
        )

    def test_env_override_resolved_after_import_dotenv_regression(self, monkeypatch):
        """THE regression pin: the module is already imported (env unset or
        default at import time); setting the env NOW must still take effect —
        this is exactly how dotenv-loaded config reaches the seam."""
        from src.openrouter_utils import resolve_openrouter_base_url

        monkeypatch.setenv(
            "OPENROUTER_BASE_URL",
            "https://jack--entity-vllm-serve.modal.run/v1",
        )
        assert resolve_openrouter_base_url() == (
            "https://jack--entity-vllm-serve.modal.run/v1"
        )

    def test_api_url_composes_from_base(self, monkeypatch):
        from src.openrouter_utils import resolve_openrouter_api_url

        monkeypatch.setenv("OPENROUTER_BASE_URL", "http://localhost:8000/v1")
        monkeypatch.delenv("OPENROUTER_API_URL", raising=False)
        assert resolve_openrouter_api_url() == "http://localhost:8000/v1/chat/completions"

    def test_api_url_wholesale_override_wins(self, monkeypatch):
        from src.openrouter_utils import resolve_openrouter_api_url

        monkeypatch.setenv(
            "OPENROUTER_API_URL", "https://gateway.example.com/custom"
        )
        assert resolve_openrouter_api_url() == "https://gateway.example.com/custom"

    def test_trailing_slash_normalized(self, monkeypatch):
        from src.openrouter_utils import resolve_openrouter_base_url

        monkeypatch.setenv("OPENROUTER_BASE_URL", "https://host--app.modal.run/v1/")
        assert resolve_openrouter_base_url() == "https://host--app.modal.run/v1"


class TestRuntimeClientsHonorSeam:
    def _sorter_agent(self):
        from agents.sorter_agent import SorterAgent

        return SorterAgent()

    @staticmethod
    def _capture_chatopenai_kwargs(monkeypatch) -> dict:
        """Intercept ChatOpenAI construction to observe the exact kwargs
        base_agent passes — no dependence on LangChain's private pydantic
        field names, and no real HTTP client gets built."""
        import agents.base_agent as ba

        captured: dict = {}

        class _FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(ba, "ChatOpenAI", _FakeChat)
        return captured

    def test_base_agent_llm_targets_env_endpoint(self, monkeypatch):
        agent = self._sorter_agent()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.setenv(
            "OPENROUTER_BASE_URL", "https://jack--entity-vllm-serve.modal.run/v1"
        )
        captured = self._capture_chatopenai_kwargs(monkeypatch)
        agent.llm()
        assert captured["base_url"] == (
            "https://jack--entity-vllm-serve.modal.run/v1"
        ), "base_agent must forward the CURRENTLY-resolved seam URL"

    def test_base_agent_llm_default_path_unchanged(self, monkeypatch):
        """The capability must not move the default serving path."""
        agent = self._sorter_agent()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
        captured = self._capture_chatopenai_kwargs(monkeypatch)
        agent.llm()
        assert str(captured["base_url"]).startswith("https://openrouter.ai/api/v1")

    def test_classifier_posts_to_resolved_url(self, tmp_path, monkeypatch):
        """The raw-requests vision path rides the same call-time seam."""
        import src.classifier as classifier

        monkeypatch.setenv(
            "OPENROUTER_BASE_URL", "https://jack--entity-vllm-serve.modal.run/v1"
        )
        captured: dict = {}

        class _FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{"message": {"content": "{\"classification\": \"x\"}"}}],
                    "usage": {},
                }

        def _fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["auth"] = (headers or {}).get("Authorization", "")
            return _FakeResponse()

        monkeypatch.setattr(classifier.requests, "post", _fake_post)
        image_path = tmp_path / "page.png"
        image_path.write_bytes(TINY_PNG)
        result = classifier.classify_image(
            api_key="tok-vllm", image_path=image_path, prompt="classify this"
        )
        assert captured["url"].startswith(
            "https://jack--entity-vllm-serve.modal.run/v1"
        ), "classifier must post to the CURRENTLY-resolved endpoint"
        assert captured["auth"] == "Bearer tok-vllm"
        assert result["status"] == "success"


# --------------------------------------------------- dependency-manifest law
class TestDependencyManifests:
    """The [deploy] extra obeys the KANBAN-081 batch contract."""

    @staticmethod
    def _parse_requirements_txt(path: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-r"):
                continue
            m = line.split(">=")[0].split("==")[0].split("<")[0]
            out[m.strip()] = line
        return out

    def _extras(self) -> dict:
        import tomllib

        with open(REPO_ROOT / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["optional-dependencies"]

    def test_deploy_extra_matches_batch_file(self):
        extras = self._extras()
        req = self._parse_requirements_txt(REPO_ROOT / "requirements" / "deploy.txt")
        py_names = {}
        for entry in extras["deploy"]:
            m = entry.split(">=")[0]
            py_names[m.strip()] = entry
        assert req.keys() == py_names.keys(), "deploy batch drifted"
        assert set(req) == {"modal"}

    def test_all_extra_and_all_txt_include_deploy(self):
        extras = self._extras()
        assert "deploy" in extras["all"][0]
        all_txt = (REPO_ROOT / "requirements" / "all.txt").read_text(encoding="utf-8")
        assert "-r deploy.txt" in all_txt

    def test_core_floor_stays_free_of_modal(self):
        import tomllib

        with open(REPO_ROOT / "pyproject.toml", "rb") as f:
            deps = tomllib.load(f)["project"]["dependencies"]
        blob = " ".join(deps).lower()
        assert "modal" not in blob, "modal is deploy-time only, never core"


class TestRuntimeTreeStaysDeployClean:
    """No runtime module (agents/ or src/) may import modal — it is a
    deploy-time-only dependency by design."""

    def test_no_runtime_module_imports_modal(self):
        offenders: list[str] = []
        for sub in ("agents", "src"):
            for py in sorted((REPO_ROOT / sub).rglob("*.py")):
                tree = ast.parse(py.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    mods = []
                    if isinstance(node, ast.Import):
                        mods = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        mods = [node.module]
                    for m in mods:
                        if m.split(".")[0] == "modal":
                            offenders.append(str(py.relative_to(REPO_ROOT)))
        assert not offenders, f"runtime modules importing deploy-only modal: {offenders}"


# -------------------------------------------------------- cross-repo contract
class TestCrossRepoContract:
    """One shared env story across the governed family. Skips honestly when
    the sibling clone is absent (CI has no sibling checkout)."""

    def test_mailroom_sibling_app_exists_with_shared_knob_names(self):
        if not MAILROOM_ROOT.is_dir():
            pytest.skip("llm-mailroom sibling not cloned beside this repo")
        sibling = MAILROOM_ROOT / "deploy" / "modal_vllm.py"
        assert sibling.is_file(), "mailroom KANBAN-064 app missing"
        text = sibling.read_text(encoding="utf-8")
        for knob in (
            "MODAL_VLLM_MODEL",
            "MODAL_VLLM_GPU",
            "MODAL_VLLM_QUANTIZATION",
            "MODAL_VLLM_MAX_MODEL_LEN",
            "MODAL_VLLM_API_TOKEN",
            "HF_TOKEN",
        ):
            assert knob in text, f"sibling lost shared knob {knob}"

    def test_both_env_examples_document_the_flip(self):
        own = REPO_ROOT / "config" / "environments" / ".env.example"
        assert "OPENROUTER_BASE_URL" in own.read_text(encoding="utf-8")
        if not MAILROOM_ROOT.is_dir():
            pytest.skip("llm-mailroom sibling not cloned beside this repo")
        sibling = MAILROOM_ROOT / ".env.example"
        text = sibling.read_text(encoding="utf-8")
        assert "VLLM_BASE_URL" in text and "VLLM_API_KEY" in text
