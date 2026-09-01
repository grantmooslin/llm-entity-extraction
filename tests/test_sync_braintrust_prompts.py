"""Network-free smoke tests for Braintrust prompt sync."""

from pathlib import Path

import pytest

from src.prompts import PROMPT_VERSIONS


@pytest.fixture
def fake_env_file(tmp_path: Path) -> Path:
    env_file = tmp_path / "braintrust-sandbox.env"
    env_file.write_text(
        "BRAINTRUST_ORG_ID=org-fake\n"
        "BRAINTRUST_PROJECT_NAME=mailroom-sandbox\n"
        "BRAINTRUST_PROJECT_ID=ba222477-2e1c-4fef-9f5d-02cc78765fe3\n"
        "BRAINTRUST_API_KEY=sk-fake-sandbox-key\n"
        "BRAINTRUST_API_BASE=https://api.braintrust.dev\n"
    )
    return env_file


def _run_sync(argv, monkeypatch, remote: dict[str, str]):
    import scripts.eval.sync_braintrust_prompts as sync

    calls = {"get": 0, "put": 0}

    def fake_get(api_key, project_id, slug, api_base="https://api.braintrust.dev/v1"):
        calls["get"] += 1
        content = remote.get(slug)
        if content is None:
            return None
        return {
            "slug": slug,
            "prompt_data": {"prompt": {"type": "completion", "content": content}},
        }

    def fake_put(api_key, project_id, slug, content, **kwargs):
        calls["put"] += 1
        remote[slug] = content
        return {"slug": slug}

    monkeypatch.setattr(sync, "get_prompt_by_slug", fake_get)
    monkeypatch.setattr(sync, "upsert_completion_prompt", fake_put)
    rc = sync.main_with_args(argv)
    return rc, calls


def test_sync_dry_run_reports_creates(fake_env_file, monkeypatch, capsys):
    rc, calls = _run_sync(["--env-file", str(fake_env_file), "--dry-run"], monkeypatch, {})
    assert rc == 0
    assert calls["put"] == 0
    out = capsys.readouterr().out
    assert "would upsert" in out
    assert "mailroom-sandbox" in out


def test_sync_upserts_absent_and_skips_unchanged(fake_env_file, monkeypatch):
    versions = dict(PROMPT_VERSIONS)
    rc, calls = _run_sync(["--env-file", str(fake_env_file)], monkeypatch, {})
    assert rc == 0
    assert calls["put"] == len(versions)

    rc, calls = _run_sync(["--env-file", str(fake_env_file)], monkeypatch, versions)
    assert rc == 0
    assert calls["put"] == 0
    assert calls["get"] == len(versions)


def test_sync_missing_env_file_warns(tmp_path, monkeypatch, capsys):
    rc, calls = _run_sync(["--env-file", str(tmp_path / "nope.env")], monkeypatch, {})
    assert rc == 0
    out = capsys.readouterr().out
    assert "not found" in out


def test_sync_without_keys_skips_project(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("BRAINTRUST_API_KEY", raising=False)
    monkeypatch.delenv("BRAINTRUST_PROJECT_ID", raising=False)
    env_file = tmp_path / "no-keys.env"
    env_file.write_text("BRAINTRUST_PROJECT_NAME=mailroom-sandbox\n")
    rc, calls = _run_sync(["--env-file", str(env_file)], monkeypatch, {})
    assert rc == 0
    assert calls["get"] == 0
    out = capsys.readouterr().out
    assert "no Braintrust" in out
