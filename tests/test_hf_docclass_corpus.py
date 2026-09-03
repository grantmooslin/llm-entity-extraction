"""Network-free tests for the direct Hugging Face docclass corpus pipe
(KANBAN-107): the pure loader ``src/hf_docclass_corpus.py`` joins the HF
``default`` (blind doc_text/prompt/filename/metadata) with ``ground_truth``
(labels + GT fields) configs on filename — mirroring
``scripts/datasets/export_hf_docclass_merged.py`` — and the docclass runner
parses ``--dataset-source hf`` and dry-runs without touching the network.

``datasets`` is not installed in the test interpreter and is never called: a
fake ``datasets`` module is injected into ``sys.modules`` (its ``load_dataset``
serves the fixture rows), and the runner smoke stubs the loader itself.
"""

from __future__ import annotations

import sys
import types

import pytest

from src.hf_docclass_corpus import (
    BLIND_CONFIG,
    DEFAULT_GT_CONFIG,
    DEFAULT_HF_DATASET,
    load_hf_docclass_corpus,
)

VALID = {"contract", "corporate_record", "correspondence",
         "insurance_claim", "merger_agreement"}

BLIND_TRAIN = [
    {"filename": "contract_0.txt", "doc_text": "AGREEMENT AND PLAN OF MERGER " * 10,
     "prompt": "", "metadata": '{"source": "maud"}'},
    {"filename": "letter_1.txt", "doc_text": "Dear Sir, " * 10,
     "prompt": "", "metadata": '{"source": "enron"}'},
    {"filename": "bylaws_2.htm", "doc_text": "BYLAWS OF ACME INC. " * 10,
     "prompt": "", "metadata": {"source": "edgar"}},
    {"filename": "no_gt.txt", "doc_text": "text with no GT " * 10,
     "prompt": "", "metadata": {}},
    {"filename": "empty.txt", "doc_text": "   ", "prompt": "", "metadata": {}},
    {"filename": "bad_class.txt", "doc_text": "demand letter " * 10,
     "prompt": "", "metadata": {}},
    {"filename": "dict_expected.txt", "doc_text": "LICENSE AGREEMENT " * 10,
     "prompt": "", "metadata": {}},
]
BLIND_TEST = [
    {"filename": "insurance_1.txt", "doc_text": "CLAIM NOTICE " * 10,
     "prompt": "p", "metadata": {}},
]

GT_TRAIN = [
    {"filename": "contract_0.txt", "expected": "merger_agreement",
     "expected_subclass": "all_cash", "split": "train"},
    {"filename": "letter_1.txt", "expected": "correspondence",
     "expected_subclass": None, "split": "train"},
    {"filename": "bylaws_2.htm", "expected": "corporate_record",
     "expected_subclass": "bylaws", "split": "train"},
    {"filename": "empty.txt", "expected": "contract",
     "expected_subclass": None, "split": "train"},
    {"filename": "bad_class.txt", "expected": "attorney_demand",
     "expected_subclass": None, "split": "train"},
    {"filename": "dict_expected.txt",
     "expected": {"expected_doc_class": "contract",
                  "expected_fields": {"parties": ["Acme", "Beta"]}},
     "expected_subclass": None, "split": "train"},
]
GT_TEST = [
    {"filename": "insurance_1.txt", "expected": "insurance_claim",
     "expected_subclass": "carrier", "split": "test",
     "expected_output": {"doc_type": "insurance_claim"}},
]


@pytest.fixture
def fake_hf(monkeypatch):
    """A fake ``datasets`` module whose ``load_dataset`` serves the fixtures."""
    calls = {"kwargs": []}

    def load_dataset(repo, config, **kwargs):
        calls["kwargs"].append({"repo": repo, "config": config,
                                "revision": kwargs.get("revision")})
        if config == DEFAULT_GT_CONFIG:
            return {"train": GT_TRAIN, "test": GT_TEST}
        if config == BLIND_CONFIG:
            return {"train": BLIND_TRAIN, "test": BLIND_TEST}
        raise AssertionError(f"unexpected config {config!r}")

    mod = types.ModuleType("datasets")
    mod.load_dataset = load_dataset
    monkeypatch.setitem(sys.modules, "datasets", mod)
    return calls


def test_join_default_and_ground_truth(fake_hf):
    rows, meta = load_hf_docclass_corpus(valid_classes=VALID)
    assert len(rows) == 5
    by_name = {r["filename"]: r for r in rows}
    merger = by_name["contract_0.txt"]
    assert merger["expected"] == "merger_agreement"
    assert merger["expected_subclass"] == "all_cash"
    assert merger["split"] == "train"
    assert merger["metadata"] == {"source": "maud"}  # JSON-string metadata coerced
    assert merger["gt_fields"] == {}
    assert by_name["letter_1.txt"]["expected_subclass"] is None
    # The test-split row joins too (both configs, both splits).
    assert by_name["insurance_1.txt"]["expected"] == "insurance_claim"
    assert by_name["insurance_1.txt"]["expected_subclass"] == "carrier"
    assert by_name["insurance_1.txt"]["split"] == "test"
    assert by_name["insurance_1.txt"]["expected_output"] == {"doc_type": "insurance_claim"}
    # dict-expected resolution: expected_doc_class + expected_fields.
    dict_row = by_name["dict_expected.txt"]
    assert dict_row["expected"] == "contract"
    assert dict_row["expected_fields"] == {"parties": ["Acme", "Beta"]}
    # meta identity.
    assert meta["repo"] == DEFAULT_HF_DATASET
    assert meta["config"] == DEFAULT_GT_CONFIG
    assert meta["revision"] is None
    assert meta["num_rows"] == 5
    assert meta["sha"] is None  # plain-dict stub carries no download_checksums


def test_class_filtering(fake_hf):
    rows, meta = load_hf_docclass_corpus(valid_classes=VALID)
    assert all(r["expected"] in VALID for r in rows)
    assert "bad_class.txt" not in {r["filename"] for r in rows}
    # Without a filter, nothing is dropped on class grounds.
    rows_all, meta_all = load_hf_docclass_corpus()
    names = {r["filename"] for r in rows_all}
    assert "bad_class.txt" in names
    assert meta_all["num_rows"] == len(rows_all) == 6


def test_empty_text_skipped(fake_hf):
    rows, _ = load_hf_docclass_corpus(valid_classes=VALID)
    assert "empty.txt" not in {r["filename"] for r in rows}
    assert all(r["doc_text"].strip() for r in rows)


def test_stable_filename_identity(fake_hf):
    rows, _ = load_hf_docclass_corpus(valid_classes=VALID)
    filenames = [r["filename"] for r in rows]
    assert len(filenames) == len(set(filenames))  # unique per-document ids
    assert all(isinstance(f, str) and f for f in filenames)
    assert "contract_0.txt" in filenames


def test_revision_passthrough(fake_hf):
    rows, meta = load_hf_docclass_corpus(revision="abc123def", valid_classes=VALID)
    assert meta["revision"] == "abc123def"
    assert len(rows) == 5
    assert len(fake_hf["kwargs"]) == 2  # blind + ground_truth configs
    for call in fake_hf["kwargs"]:
        assert call["repo"] == DEFAULT_HF_DATASET
        assert call["revision"] == "abc123def"
    assert {c["config"] for c in fake_hf["kwargs"]} == {BLIND_CONFIG, DEFAULT_GT_CONFIG}


def test_meta_sha_when_obtainable(monkeypatch):
    """When the datasets lib exposes per-shard download checksums the meta
    records a folded sha; an unexposing stub degrades to None (never guessed)."""

    class _Info:
        download_checksums = {
            "default/train/0000.parquet": {"checksum": "sha256:aa11"},
            "default/test/0000.parquet": {"checksum": "sha256:bb22"},
        }

    class _DS:
        def __init__(self, rows):
            self.rows = rows
            self.info = _Info()

        def __iter__(self):
            return iter(self.rows)

    def load_dataset(repo, config, **kwargs):
        if config == DEFAULT_GT_CONFIG:
            return _DS(GT_TRAIN + GT_TEST)
        return _DS(BLIND_TRAIN + BLIND_TEST)

    mod = types.ModuleType("datasets")
    mod.load_dataset = load_dataset
    monkeypatch.setitem(sys.modules, "datasets", mod)

    rows, meta = load_hf_docclass_corpus()
    assert meta["sha"] is not None and len(meta["sha"]) == 64
    assert len(rows) == 6


HF_ROWS = [
    {"doc_text": "AGREEMENT AND PLAN OF MERGER " * 50, "prompt": "",
     "filename": "contract_0.txt", "expected": "merger_agreement",
     "expected_subclass": "all_cash", "metadata": {}, "expected_fields": {},
     "gt_fields": {}, "split": "train"},
    {"doc_text": "BYLAWS OF ACME INC. " * 50, "prompt": "",
     "filename": "bylaws_2.htm", "expected": "corporate_record",
     "expected_subclass": "bylaws", "metadata": {}, "expected_fields": {},
     "gt_fields": {}, "split": "train"},
    {"doc_text": "LICENSE AGREEMENT " * 50, "prompt": "",
     "filename": "license.txt", "expected": "contract",
     "expected_subclass": None, "metadata": {}, "expected_fields": {},
     "gt_fields": {}, "split": "train"},
    {"doc_text": "CLAIM NOTICE " * 50, "prompt": "",
     "filename": "insurance_1.txt", "expected": "insurance_claim",
     "expected_subclass": "carrier", "metadata": {}, "expected_fields": {},
     "gt_fields": {}, "split": "test"},
]


def _stub_hf_loader(monkeypatch):
    calls = {}

    def fake_load(repo=DEFAULT_HF_DATASET, config=DEFAULT_GT_CONFIG,
                  revision=None, valid_classes=None):
        calls.update({"repo": repo, "config": config,
                      "revision": revision, "valid_classes": valid_classes})
        return HF_ROWS, {"repo": repo, "config": config, "revision": revision,
                         "num_rows": len(HF_ROWS), "sha": "deadbeef"}

    monkeypatch.setattr("src.hf_docclass_corpus.load_hf_docclass_corpus", fake_load)
    return calls


def test_docclass_runner_hf_dry_run(tmp_path, monkeypatch):
    """--dataset-source hf parses, loads through the stubbed loader, and
    dry-runs — no network, no Braintrust load, no Langfuse."""
    calls = _stub_hf_loader(monkeypatch)

    from scripts.eval.run_langfuse_docclass_eval import main_with_args

    exit_code = main_with_args([
        "--dataset-source", "hf",
        "--sample", "20", "--seed", "42",
        "--dry-run",
    ])
    assert exit_code == 0
    assert calls["repo"] == DEFAULT_HF_DATASET
    assert calls["config"] == DEFAULT_GT_CONFIG
    assert calls["revision"] is None
    # The runner passes the valid-class filter through (extended union).
    assert calls["valid_classes"] is not None
    assert "merger_agreement" in calls["valid_classes"]


def test_docclass_runner_hf_flags_passthrough(tmp_path, monkeypatch):
    """Explicit --hf-dataset/--hf-config/--hf-revision reach the loader."""
    calls = _stub_hf_loader(monkeypatch)

    from scripts.eval.run_langfuse_docclass_eval import main_with_args

    exit_code = main_with_args([
        "--dataset-source", "hf",
        "--hf-dataset", "Lucius-Morningstar/docclass-merged",
        "--hf-config", "ground_truth",
        "--hf-revision", "abc123",
        "--sample", "20", "--seed", "42",
        "--dry-run",
    ])
    assert exit_code == 0
    assert calls["repo"] == "Lucius-Morningstar/docclass-merged"
    assert calls["config"] == "ground_truth"
    assert calls["revision"] == "abc123"