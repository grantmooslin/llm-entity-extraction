"""End-to-end smoke test of the hierarchical doc-class eval loop
(no network, no LLM): one sorter call per document against the EXTENDED
7-class schema, doc_type + subclass trackers scored, per-class accuracy +
failure insights in the repo log.

The runner is exercised through ``main_with_args`` with a local JSONL dump
and a monkeypatched ``SorterAgent.classify_json`` — the same local-dump path
a real run takes (Braintrust row uploads are org-capped, so the local dump
IS the documented primary data path for this task). The Langfuse SDK is
stubbed (never constructed/contacted) and Phoenix is disabled.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from scripts.eval.run_langfuse_docclass_eval import (
    classify_failure,
    load_docclass_dataset,
    stratified_sample,
)
from tests.test_langfuse_tracing import StubLangfuse


@contextmanager
def _fake_propagate_attributes(**kwargs):
    yield


@pytest.fixture
def fake_langfuse(monkeypatch):
    stub = StubLangfuse()
    monkeypatch.setattr("langfuse.Langfuse", lambda **kwargs: stub)
    monkeypatch.setattr("langfuse.propagate_attributes", _fake_propagate_attributes)
    monkeypatch.setattr("langfuse.langchain.CallbackHandler", lambda: "stub-handler")
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL",
                 "LANGFUSE_PROJECT", "LANGFUSE_ENVIRONMENT", "PHOENIX_TRACING"):
        monkeypatch.setenv(name, "fake" if name != "PHOENIX_TRACING" else "disabled")
    return stub

DUMP_ROWS = [
    {"filename": "contract_0_merger_agreement.txt", "doc_text": "AGREEMENT AND PLAN OF MERGER " * 200,
     "expected": "merger_agreement", "expected_subclass": "all_cash",
     "metadata": {"source": "maud_v1", "expected_subclass": "all_cash"}},
    {"filename": "bylaws.htm", "doc_text": "BYLAWS OF ACME INC. " * 200,
     "expected": "corporate_record", "expected_subclass": "bylaws",
     "metadata": {"source": "edgar_s1", "expected_subclass": "bylaws"}},
    {"filename": "license_agreement.txt", "doc_text": "LICENSE AGREEMENT " * 200,
     "expected": "contract", "expected_subclass": None,
     "metadata": {"source": "cuad"}},
    {"filename": "letter.txt", "doc_text": "Dear Sir, " * 200,
     "expected": "correspondence", "expected_subclass": None,
     "metadata": {"source": "local"}},
]


@pytest.fixture
def dump_path(tmp_path):
    path = tmp_path / "docclass.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in DUMP_ROWS:
            fh.write(json.dumps(row) + "\n")
    return path


def test_load_docclass_dataset(dump_path):
    rows = load_docclass_dataset([], "project", "pid", local_dumps=[dump_path])
    assert len(rows) == 4
    by_name = {r["filename"]: r for r in rows}
    assert by_name["contract_0_merger_agreement.txt"]["expected"] == "merger_agreement"
    assert by_name["contract_0_merger_agreement.txt"]["expected_subclass"] == "all_cash"
    assert by_name["bylaws.htm"]["expected_subclass"] == "bylaws"
    assert by_name["license_agreement.txt"]["expected_subclass"] is None


def test_stratified_sample_even_across_classes(dump_path):
    rows = load_docclass_dataset([], "p", "pid", local_dumps=[dump_path])
    sample = stratified_sample(rows, 4, seed=42)
    classes = sorted({r["expected"] for r in sample})
    assert len(classes) == 4  # one per doc_type class


def test_classify_failure_modes():
    assert classify_failure(True, True, "all_cash") is None
    assert classify_failure(False, False, "all_cash") == "doc_type_miss"
    assert classify_failure(True, False, "all_stock") == "subclass_miss"
    # Rows without subclass GT (subclass_ok=None) must not get subclass_miss.
    assert classify_failure(True, None, None) is None


def test_docclass_eval_smoke(dump_path, tmp_path, monkeypatch, fake_langfuse):
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "log.md"))

    calls = {"n": 0}

    def fake_classify_json(self, doc_text):
        calls["n"] += 1
        if "MERGER" in doc_text.upper():
            doc_type, subclass = "merger_agreement", "all_cash"
        elif "BYLAWS" in doc_text.upper():
            doc_type, subclass = "corporate_record", "bylaws"
        elif "LICENSE" in doc_text.upper():
            doc_type, subclass = "contract", None
        else:
            doc_type, subclass = "correspondence", None
        return {"doc_type": doc_type, "contract_subtype": None, "doc_subclass": subclass,
                "confidence": 0.95, "reasoning": f"{doc_type} evidence"}

    monkeypatch.setattr("agents.sorter_agent.SorterAgent.classify_json", fake_classify_json)

    from scripts.eval.run_langfuse_docclass_eval import main_with_args

    exit_code = main_with_args([
        "--local-dumps", str(dump_path),
        "--experiment-name", "docclass_smoke_test",
        "--manifest", str(tmp_path / "manifest.jsonl"),
        "--max-concurrency", "2",
    ])
    assert exit_code == 0
    assert calls["n"] == 4  # one sorter call per document
    assert len(fake_langfuse.spans) == 4  # one trace per document

    records = [json.loads(line) for line in
               (tmp_path / "log.jsonl").read_text().strip().splitlines()]
    assert len(records) == 1
    rec = records[0]
    assert rec["task"] == "docclass_classification"
    assert rec["experiment_name"] == "docclass_smoke_test"
    assert rec["scores"]["doc_type_accuracy"] == 1.0
    assert rec["scores"]["subclass_accuracy"] == 1.0
    assert rec["scores"]["exact_match"] == 1.0
    assert rec["scores"]["per_class_accuracy"]["merger_agreement"] == 1.0
    assert rec["scores"]["sorter"]["failure_insights"]["n_failed"] == 0
    assert len(rec["per_row"]) == 4

    # Docclass scoring depth (the subtype-surface mirror): bootstrap CIs on
    # every headline, a per-subclass accuracy table with support counts, the
    # equivalence-aware subclass headline, and the input-mode split. The
    # subclass CI covers only rows with subclass GT (2 of the 4 rows).
    ci = rec["scores"]["doc_type_accuracy_ci"]
    assert ci is not None and ci["n"] == 4 and 0.0 <= ci["lo"] <= ci["hi"] <= 1.0
    ci = rec["scores"]["subclass_accuracy_ci"]
    assert ci is not None and ci["n"] == 2 and 0.0 <= ci["lo"] <= ci["hi"] <= 1.0
    ci = rec["scores"]["exact_match_ci"]
    assert ci is not None and ci["n"] == 4 and 0.0 <= ci["lo"] <= ci["hi"] <= 1.0
    per_sub = rec["scores"]["per_subclass_accuracy"]
    assert per_sub["all_cash"] == 1.0
    assert rec["scores"]["per_subclass_support"]["all_cash"] == 1
    assert rec["scores"]["subclass_accuracy_equiv"] == 1.0
    assert rec["scores"]["equiv_recovered"] == []
    assert rec["scores"]["input_mode_counts"] == {"text": 4}
    # Every scored row carries the equivalence flag.
    assert all(r["sorter"]["subclass_ok_equiv"] is not None
               for r in rec["per_row"] if r["sorter"]["expected_subclass"])

    # The markdown log gained a section.
    md = (tmp_path / "log.md").read_text()
    assert "docclass_smoke_test" in md
    # The per-document table renders the second-level dimension.
    assert "expected subclass" in md
    assert "subclass ok equiv" in md
    # The per-subclass accuracy table renders.
    assert "Per-subclass accuracy (second-level dimension)" in md
    assert "all_cash" in md


def test_docclass_specialist_eval_smoke(dump_path, tmp_path, monkeypatch, fake_langfuse):
    """Docclass specialist runner: mocked extraction + CUAD GT scoring."""
    import json as _json

    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "spec_log.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "spec_log.md"))

    contract_row = {
        "filename": "license_agreement.txt",
        "doc_text": "LICENSE AGREEMENT " * 200,
        "expected": "contract",
        "expected_subclass": "License_Agreements",
        "metadata": {"category": "License_Agreements", "source": "cuad"},
        "gt_fields": {
            "cuad_clause_labels": _json.dumps({
                "Parties": [{"text": "Acme Corp and Beta LLC", "start": 10}],
                "Governing Law": [{"text": "State of Delaware", "start": 50}],
            }),
        },
    }
    spec_dump = tmp_path / "spec.jsonl"
    with spec_dump.open("w", encoding="utf-8") as fh:
        fh.write(_json.dumps(contract_row) + "\n")

    manifest = tmp_path / "spec_manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"filename": "license_agreement.txt",
                              "expected": "contract"}) + "\n")

    def fake_extract(self, doc_text):
        return {
            "parties": ["Acme Corp", "Beta LLC"],
            "governing_law": "State of Delaware",
            "effective_date": None,
            "term_length": None,
            "termination_clauses": [],
            "key_obligations": [],
            "contract_value": None,
            "renewal_terms": None,
        }

    monkeypatch.setattr(
        "agents.specialist_agents.ContractsSpecialist.extract", fake_extract)

    from scripts.eval.run_langfuse_docclass_specialist_eval import main_with_args

    exit_code = main_with_args([
        "--agent", "contracts_specialist",
        "--prompt-version", "contracts_specialist_docclass_v0",
        "--local-dumps", str(spec_dump),
        "--filename-manifest", str(manifest),
        "--experiment-name", "docclass_specialist_smoke",
        "--manifest", str(tmp_path / "resume.jsonl"),
        "--max-concurrency", "1",
    ])
    assert exit_code == 0
    records = [_json.loads(line) for line in
               (tmp_path / "spec_log.jsonl").read_text().strip().splitlines()]
    rec = records[0]
    assert rec["task"] == "docclass_specialist_extraction"
    assert rec["scores"]["overall_extraction_score"] is not None
    assert rec["scores"]["n_rows"] == 1


def test_docclass_eval_vision_primary_falls_back_to_text(dump_path, tmp_path, monkeypatch, fake_langfuse):
    """--input-mode vision-primary: the vision pass runs FIRST; when it cannot
    produce a label (UNREADABLE sentinel / call error / no pages) the runner
    falls back to the text pass and records input_mode + fallback_reason."""
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "log3.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "log3.md"))

    calls = {"vision": 0, "text": 0}

    def fake_classify_document(self, pages_base64, image_format="png"):
        calls["vision"] += 1
        # The first page renders fine -> UNREADABLE (images unusable) so the
        # runner must fall back to text; no page images -> unreadable too.
        return {"doc_type": None, "contract_subtype": None, "doc_subclass": None,
                "confidence": 0.0, "reasoning": "blank page", "unreadable": True,
                "invalid_label": False}

    def fake_classify_json(self, doc_text):
        calls["text"] += 1
        if "MERGER" in doc_text.upper():
            return {"doc_type": "merger_agreement", "contract_subtype": None,
                    "doc_subclass": "all_cash", "confidence": 0.95, "reasoning": "merger"}
        if "BYLAWS" in doc_text.upper():
            return {"doc_type": "corporate_record", "contract_subtype": None,
                    "doc_subclass": "bylaws", "confidence": 0.95, "reasoning": "bylaws"}
        if "LICENSE" in doc_text.upper():
            return {"doc_type": "contract", "contract_subtype": None,
                    "doc_subclass": None, "confidence": 0.95, "reasoning": "license"}
        return {"doc_type": "correspondence", "contract_subtype": None,
                "doc_subclass": None, "confidence": 0.95, "reasoning": "letter"}

    monkeypatch.setattr("agents.sorter_agent.SorterAgent.classify_document",
                        fake_classify_document)
    monkeypatch.setattr("agents.sorter_agent.SorterAgent.classify_json", fake_classify_json)

    from scripts.eval.run_langfuse_docclass_eval import main_with_args

    exit_code = main_with_args([
        "--local-dumps", str(dump_path),
        "--input-mode", "vision-primary",
        "--pdf-dir", str(tmp_path),  # no PDFs -> every row falls back to text
        "--experiment-name", "docclass_smoke_vision_primary",
        "--manifest", str(tmp_path / "manifest3.jsonl"),
        "--max-concurrency", "2",
    ])
    assert exit_code == 0
    # No PDFs matched -> zero vision calls, all four rows via text fallback.
    assert calls["vision"] == 0
    assert calls["text"] == 4

    records = [json.loads(line) for line in
               (tmp_path / "log3.jsonl").read_text().strip().splitlines()]
    rec = records[0]
    assert rec["scores"]["exact_match"] == 1.0
    assert rec["parameters"]["input_mode"] == "vision-primary"
    modes = {r["sorter"]["input_mode"] for r in rec["per_row"]}
    assert modes == {"text_fallback"}
    reasons = {r["sorter"].get("fallback_reason") for r in rec["per_row"]}
    assert reasons == {"no_pages"}


def test_docclass_eval_smoke_detects_subclass_miss(dump_path, tmp_path, monkeypatch, fake_langfuse):
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "log2.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "log2.md"))

    def fake_classify_json(self, doc_text):
        # doc_type always correct; the merger row's consideration subclass
        # is WRONG (all_stock vs GT all_cash) -> subclass_miss insight.
        if "MERGER" in doc_text.upper():
            return {"doc_type": "merger_agreement", "contract_subtype": None,
                    "doc_subclass": "all_stock", "confidence": 0.9, "reasoning": "stock"}
        if "BYLAWS" in doc_text.upper():
            return {"doc_type": "corporate_record", "contract_subtype": None,
                    "doc_subclass": "bylaws", "confidence": 0.9, "reasoning": "bylaws"}
        if "LICENSE" in doc_text.upper():
            return {"doc_type": "contract", "contract_subtype": None,
                    "doc_subclass": None, "confidence": 0.9, "reasoning": "license"}
        return {"doc_type": "correspondence", "contract_subtype": None,
                "doc_subclass": None, "confidence": 0.9, "reasoning": "letter"}

    monkeypatch.setattr("agents.sorter_agent.SorterAgent.classify_json", fake_classify_json)

    from scripts.eval.run_langfuse_docclass_eval import main_with_args

    exit_code = main_with_args([
        "--local-dumps", str(dump_path),
        "--experiment-name", "docclass_smoke_miss",
        "--manifest", str(tmp_path / "manifest2.jsonl"),
        "--max-concurrency", "2",
    ])
    assert exit_code == 0
    records = [json.loads(line) for line in
               (tmp_path / "log2.jsonl").read_text().strip().splitlines()]
    rec = records[0]
    assert rec["scores"]["doc_type_accuracy"] == 1.0
    assert rec["scores"]["subclass_accuracy"] == 0.5  # merger row misses, bylaws hits
    assert rec["scores"]["exact_match"] == 0.75
    insights = rec["scores"]["sorter"]["failure_insights"]
    assert insights["mode_counts"].get("subclass_miss") == 1
    assert insights["n_failed"] == 1
    assert insights["failures"][0]["failure_mode"] == "subclass_miss"
