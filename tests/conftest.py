"""Shared fixtures for the mailroom eval-loop test suite.

Tests never touch the network: Braintrust/OpenRouter keys are faked with
placeholder values, and any module that would call the APIs is mocked per-test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
# Standalone convention: tests resolve data/fixture paths relative to the
# package root ("runnable from the repo root"). In the monorepo pytest starts
# at the hub root, so anchor CWD here exactly as the standalone suite expects.
os.chdir(REPO_ROOT)

FAKE_BT_KEY = "sk-test-braintrust-fake-key"
FAKE_OR_KEY = "sk-or-test-fake-key"


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    """Provide fake credentials + known Braintrust config for every test."""
    monkeypatch.setenv("BRAINTRUST_ORG_ID", "org-test-0000")
    monkeypatch.setenv("BRAINTRUST_PROJECT_ID", "proj-test-0000")
    monkeypatch.setenv("BRAINTRUST_PROJECT_NAME", "mailroom-eval-test")
    monkeypatch.setenv("BRAINTRUST_DATASET_PROJECT", "mailroom-eval-test")
    monkeypatch.setenv("BRAINTRUST_MODEL", "qwen/qwen3.7-flash")
    monkeypatch.setenv("BRAINTRUST_API_KEY", FAKE_BT_KEY)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_OR_KEY)
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # The taxonomy loader caches on first call; reset it per test.
    from src import taxonomy

    taxonomy.load_taxonomy.cache_clear()
    return {"braintrust_key": FAKE_BT_KEY, "openrouter_key": FAKE_OR_KEY}


@pytest.fixture(autouse=True)
def _isolate_experiment_log(monkeypatch, tmp_path):
    """Redirect the repo experiment log to a per-test tmp dir.

    Tests that run the eval loops (smoke tests) append experiment records;
    they must never pollute the repo's reports/experiment_log.* files.
    """
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "experiment_log.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "experiment_log.md"))


@pytest.fixture
def sample_dataset_rows():
    """A small valid multiclass dataset (no network involved)."""
    return [
        {"doc_text": "AGREEMENT between Acme and Beta dated 2024-01-01.",
         "filename": "doc_contract_01.txt", "expected": "contract"},
        {"doc_text": "Board resolution of Acme Inc., January 2024.",
         "filename": "doc_corp_02.txt", "expected": "corporate_record"},
        {"doc_text": "Due diligence checklist — employment matters.",
         "filename": "doc_dd_03.txt", "expected": "due_diligence"},
        {"doc_text": "Dear Counsel: demand letter dated 2024-02-01.",
         "filename": "doc_corr_04.txt", "expected": "correspondence"},
    ]


@pytest.fixture
def sample_maud_zip(tmp_path):
    """Build a tiny fake MAUD zip (contracts + label csv) in a temp file."""
    import zipfile

    zip_path = tmp_path / "maud_v1.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("data/contracts/contract_0.txt", "This is a long merger agreement text. " * 50)
        zf.writestr("data/contracts/contract_1.txt", "Another agreement text here. " * 50)
        zf.writestr(
            "data/MAUD_train.csv",
            "data_type,contract_name,text,answer,label,question,subquestion,text_type,id,category\n"
            "main,contract_0,some text,Yes,Yes,Is there a termination clause?,None,Termination Clause,1,Conditions to Closing\n"
            "main,contract_0,more text,No,No,Is there an anti-assignment?,None,Anti-Assignment,2,Deal Protection\n"
            "main,contract_1,text,Yes,Yes,Change of control?,None,Change of Control,3,Deal Protection\n",
        )
    return zip_path
