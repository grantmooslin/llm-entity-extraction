"""Network-free smoke tests for Braintrust dataset sync."""

from pathlib import Path

import pytest

from scripts.eval.sync_braintrust_datasets import (
    _flat_row_to_record,
    _records_from_local_dump,
    _sync_legalbench_tasks,
)
from src.braintrust_config import BraintrustConfig


@pytest.fixture
def fake_cfg() -> BraintrustConfig:
    return BraintrustConfig(
        org_id="org",
        project_id="ba222477-2e1c-4fef-9f5d-02cc78765fe3",
        project_name="mailroom-sandbox",
        dataset_project="mailroom-sandbox",
        model="qwen/qwen3.7-flash",
        api_base="https://api.braintrust.dev",
        api_key="sk-fake",
    )


def test_flat_row_to_record_carries_subclass_and_sentiment():
    row = {
        "filename": "msg_1.eml",
        "doc_text": "Please remit payment.",
        "expected": "correspondence",
        "expected_subclass": "demand",
        "sentiment_label": "negative",
        "sentiment_score": -0.8,
        "metadata": {"source": "enron"},
    }
    record = _flat_row_to_record(row)
    assert record["expected"]["doc_type"] == "correspondence"
    assert record["expected"]["expected_subclass"] == "demand"
    assert record["expected"]["sentiment_label"] == "negative"
    assert record["input"]["metadata"]["expected_doc_type"] == "correspondence"


def test_records_from_local_dump(tmp_path: Path):
    dump = tmp_path / "rows.jsonl"
    dump.write_text(
        '{"filename":"a.txt","doc_text":"text","expected":"contract",'
        '"expected_subclass":"license","metadata":{"source":"test"}}\n'
    )
    records = _records_from_local_dump(dump)
    assert len(records) == 1
    assert records[0]["expected"]["doc_type"] == "contract"


def test_sync_legalbench_tasks_dry_run(fake_cfg, monkeypatch):
    import scripts.eval.sync_braintrust_datasets as sync

    def fake_load_task(task, include_prompt=True):
        return {
            "rows": [{"index": "0", "inputs": "Q: sample\nA:", "outputs": "Yes"}],
            "valid_classes": ["Yes", "No"],
            "task_type": "classification",
            "base_prompt": "Q: {{text}}\nA:",
        }

    def fake_build_records(meta):
        return [{
            "input": {"doc_text": "clause", "filename": "hearsay_0.txt",
                      "metadata": {"task": "hearsay", "valid_classes": ["No", "Yes"]}},
            "expected": {"doc_type": "No"},
            "metadata": {"task": "hearsay"},
        }]

    monkeypatch.setattr(sync, "load_task", fake_load_task)
    monkeypatch.setattr(sync, "build_records", fake_build_records)
    inserted, failed = _sync_legalbench_tasks(
        fake_cfg, "sk-fake", ["hearsay"], with_test=False, dry_run=True,
    )
    assert inserted == 1
    assert failed == 0


def test_main_requires_a_target(tmp_path):
    import scripts.eval.sync_braintrust_datasets as sync

    env_file = tmp_path / "bt.env"
    env_file.write_text(
        "BRAINTRUST_PROJECT_ID=ba222477-2e1c-4fef-9f5d-02cc78765fe3\n"
        "BRAINTRUST_API_KEY=sk-fake\n"
        "BRAINTRUST_PROJECT_NAME=mailroom-sandbox\n"
    )
    with pytest.raises(SystemExit):
        sync.main_with_args(["--env-file", str(env_file)])
