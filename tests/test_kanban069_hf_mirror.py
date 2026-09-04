"""KANBAN-069: network-free pins for the Braintrust -> Hugging Face mirror tooling.

Pins the READ-ONLY contract of the exporter and the verification behavior of
the publisher by inspecting their SOURCE TEXT (no network, no Braintruth/HF
calls at test time). Staging-data assertions are skipped when the gitignored
data/hf_export/ directory is absent.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER = REPO_ROOT / "scripts" / "datasets" / "export_bt_to_hf.py"
PUBLISHER = REPO_ROOT / "scripts" / "datasets" / "publish_hf_mirror.py"
GITIGNORE = REPO_ROOT / ".gitignore"
STAGING = REPO_ROOT / "data" / "hf_export"


def _src(path: Path) -> str:
    assert path.exists(), f"missing {path}"
    return path.read_text(encoding="utf-8")


# --- exporter: Braintrust stays READ-ONLY -------------------------------

def test_exporter_declares_readonly_contract():
    src = _src(EXPORTER)
    assert "READ-ONLY" in src
    # the get-or-create endpoint must only ever appear as a documented NEVER
    assert "never api/dataset/register" in src


def test_exporter_uses_catalog_get_and_btql_reads():
    src = _src(EXPORTER)
    assert "v1/dataset" in src          # live-catalog discovery (pure GET)
    assert "btql" in src                # row reads (SDK query surface)


def test_exporter_has_accidental_creation_guard():
    src = _src(EXPORTER)
    assert "ABORT" in src               # hard abort on any write-path surprise


def test_publisher_targets_lucius_morningstar_by_default(monkeypatch):
    monkeypatch.delenv("HF_USERNAME", raising=False)
    src = _src(PUBLISHER)
    assert 'os.environ.get("HF_USERNAME", "Lucius-Morningstar")' in src


def test_publisher_cards_carry_cc_by_4_0_frontmatter():
    src = _src(PUBLISHER)
    assert "license: cc-by-4.0" in src
    assert "braintrust-mirror" in src


def test_publisher_aborts_on_local_sha_mismatch_and_verifies_upload():
    src = _src(PUBLISHER)
    assert "ABORT_local_sha_mismatch" in src      # refuse to ship corrupt staging
    assert "verified" in src                      # post-upload sha comparison
    assert "repo_type=\"dataset\"" in src         # datasets, not models


def test_gitignore_guards_staging_but_tracks_readme():
    src = _src(GITIGNORE)
    assert "hf_export/*" in src  # anchored (/data/...) or bare (data/...)
    assert (
        "!/data/hf_export/README.md" in src or "!data/hf_export/README.md" in src
    )


# --- staging artifacts (skip when the gitignored dir is absent) ----------

def test_staging_manifests_match_summary_dispositions():
    import pytest

    if not STAGING.exists():
        pytest.skip("data/hf_export/ staging absent (regenerate via export_bt_to_hf.py)")
    if not (STAGING / "EXPORT_SUMMARY.json").is_file():
        pytest.skip(
            "data/hf_export/ staging incomplete — EXPORT_SUMMARY.json absent "
            "(regenerate via export_bt_to_hf.py)"
        )
    import json

    summary_path = STAGING / "EXPORT_SUMMARY.json"
    assert summary_path.exists(), "EXPORT_SUMMARY.json missing"
    entries = json.loads(summary_path.read_text())
    by_name = {e["dataset"]: e for e in entries}
    for name in ("mailroom-cuad-contracts", "mailroom-cuad-contracts-full"):
        entry = by_name.get(name)
        assert entry is not None, f"{name} missing from EXPORT_SUMMARY.json"
        assert entry.get("disposition") == "exported"
        manifest = json.loads((STAGING / f"{name}.manifest.json").read_text())
        assert manifest["sha256"] == entry["sha256"]
