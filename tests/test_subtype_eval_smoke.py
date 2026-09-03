"""End-to-end smoke test of the SORTER-ONLY subtype eval loop
(no network, no LLM): one sorter call per PDF, subtype trackers registered
and scored, confusion matrix + per-subtype accuracy in the repo log."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from scripts.eval.run_subtype_eval import stratified_sample


class FakeEvalResult:
    def __init__(self, input, expected, output, error=None):
        self.input = input
        self.expected = expected
        self.output = output
        self.error = error


class FakeEvalRun:
    def __init__(self):
        self.kwargs = None
        self.results = []

    def _run(self):
        import inspect

        data_rows = self.kwargs["data"]()
        task = self.kwargs["task"]
        for row in data_rows:
            try:
                output = task(row["input"])
            except Exception as exc:  # noqa: BLE001
                self.results.append(FakeEvalResult(row["input"], row["expected"], None, str(exc)))
                continue
            self.results.append(FakeEvalResult(row["input"], row["expected"], output))
        self.scores = {}
        for scorer in self.kwargs.get("scores", []):
            arity = len(inspect.signature(scorer).parameters)
            values = []
            for r in self.results:
                if r.error is not None:
                    continue
                values.append(scorer(r.output, r.expected))
            self.scores[scorer.__name__] = values
        return self


@pytest.fixture
def fake_subtype_eval(monkeypatch):
    run = FakeEvalRun()
    monkeypatch.setenv("BRAINTRUST_LOGGING", "enabled")


    def fake_eval_call(project, *args, **kwargs):
        run.kwargs = kwargs
        run.kwargs["project"] = project
        return run._run()

    import braintrust

    monkeypatch.setattr(braintrust, "Eval", fake_eval_call)
    monkeypatch.setattr(braintrust, "flush", lambda *a, **k: None)
    monkeypatch.setattr("braintrust.integrations.langchain.setup_langchain", lambda *a, **k: True)
    monkeypatch.setattr("scripts.eval.run_subtype_eval.setup_langchain", lambda *a, **k: True)

    calls = {"sorter": 0}

    def fake_classify_json(self, doc_text):
        calls["sorter"] += 1
        return {"doc_type": "contract", "contract_subtype": "license",
                "confidence": 0.95, "reasoning": "license agreement"}

    monkeypatch.setattr("agents.sorter_agent.SorterAgent.classify_json", fake_classify_json)
    run.calls = calls
    return run


def test_stratified_sample_even_distribution():
    # 3 subtypes with 10 rows each, plus one tiny class with 2 rows.
    rows = [{"filename": f"{subtype}_{i}", "expected_subtype": subtype}
            for subtype in ("license", "development", "distributor")
            for i in range(10)]
    rows += [{"filename": f"other_{i}", "expected_subtype": "maintenance"}
             for i in range(2)]

    sample = stratified_sample(rows, 20, seed=42)
    counts = Counter(r["expected_subtype"] for r in sample)
    # Even: 20 across 4 classes -> 5 each; the tiny class takes what it has.
    assert counts["license"] == 5
    assert counts["development"] == 5
    assert counts["distributor"] == 5
    assert counts["maintenance"] == 2  # class too small to fill its allocation
    assert len(sample) == 17
    assert len({r["filename"] for r in sample}) == len(sample)  # no duplicates

    # Every subtype is represented when n >= class count.
    assert len(Counter(r["expected_subtype"] for r in stratified_sample(rows, 4, seed=1))) == 4

    # Deterministic with the same seed.
    assert [r["filename"] for r in stratified_sample(rows, 20, seed=42)] == \
           [r["filename"] for r in stratified_sample(rows, 20, seed=42)]

    # Oversized requests fail loudly.
    with pytest.raises(ValueError):
        stratified_sample(rows, 500, seed=0)


def test_subtype_loop_wiring(fake_subtype_eval, monkeypatch, tmp_path):
    import scripts.eval.run_subtype_eval as runner

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

    rc = runner.main_with_args([
        "--dataset", "mailroom-cuad-contracts",
        "--sorter-prompt-version", "sorter_v3",
        "--experiment-name", "smoke_subtype",
        "--project-id", "proj-test-0000",
        "--experiment-log", str(tmp_path / "exp.jsonl"),
    ])
    assert rc == 0

    # The sorter ran EXACTLY once per PDF.
    assert fake_subtype_eval.calls["sorter"] == 1

    # Wiring: task + prompt version stamped in metadata.
    assert fake_subtype_eval.kwargs["metadata"]["task"] == "subtype_classification"
    assert fake_subtype_eval.kwargs["metadata"]["sorter_prompt"] == "sorter_v3"

    # Sorter trackers registered (default overall set).
    names = set(fake_subtype_eval.scores)
    for tracker in ("sorter_exact_match", "sorter_subtype_accuracy",
                    "sorter_subtype_accuracy_equiv", "sorter_confidence"):
        assert tracker in names
    assert fake_subtype_eval.scores["sorter_subtype_accuracy"] == [1.0]
    assert fake_subtype_eval.scores["sorter_subtype_accuracy_equiv"] == [1.0]

    # CUAD folder -> canonical subtype ground truth, scored correctly.
    row = fake_subtype_eval.results[0].output
    assert row["sorter"]["doc_type_ok"] is True
    assert row["sorter"]["subtype_ok"] is True  # License_Agreements -> license
    assert row["sorter"]["subtype_ok_equiv"] is True
    assert row["sorter"]["expected_subtype"] == "license"

    # The repo experiment log record carries per-subtype accuracy + confusion.
    log_path = tmp_path / "exp.jsonl"
    for line in open(log_path):
        record = json.loads(line)
        assert record["task"] == "subtype_classification"
        assert record["prompt_versions"] == {"sorter": "sorter_v3"}
        assert record["scores"]["sorter"]["subtype_accuracy"] == 1.0
        assert record["scores"]["sorter"]["subtype_accuracy_equiv"] == 1.0
        assert record["scores"]["sorter"]["per_subtype"]["license"]["correct"] == 1
        assert record["scores"]["sorter"]["confusion_matrix"]["license"]["license"] == 1


def test_subtype_loop_no_braintrust_logging(monkeypatch, tmp_path):
    """With BRAINTRUST_LOGGING unset (the default), the runner must NOT call
    braintrust.Eval — the run sinks to the repo experiment log instead."""
    import braintrust
    import scripts.eval.run_subtype_eval as runner

    monkeypatch.delenv("BRAINTRUST_LOGGING", raising=False)
    # Pin LANGSMITH_TRACING to a non-true value (not just delete it): the
    # runner loads config/environments/.env with override=False, so a local
    # LANGSMITH_TRACING=true there would otherwise re-enable LangSmith and
    # break the "off by default" contract this test verifies.
    monkeypatch.setenv("LANGSMITH_TRACING", "0")

    eval_calls = {"n": 0}

    def spy_eval(*a, **k):
        eval_calls["n"] += 1
        return None

    monkeypatch.setattr(braintrust, "Eval", spy_eval)

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
        return {"doc_type": "contract", "contract_subtype": "license",
                "confidence": 0.95, "reasoning": "license agreement"}

    monkeypatch.setattr("agents.sorter_agent.SorterAgent.classify_json", fake_classify_json)

    rc = runner.main_with_args([
        "--dataset", "mailroom-cuad-contracts",
        "--sorter-prompt-version", "sorter_v3",
        "--experiment-name", "smoke_subtype_nobt",
        "--project-id", "proj-test-0000",
        "--experiment-log", str(tmp_path / "exp.jsonl"),
    ])
    assert rc == 0
    assert eval_calls["n"] == 0, "braintrust.Eval must not be called when logging is disabled"

    records = [json.loads(line) for line in open(tmp_path / "exp.jsonl")]
    assert len(records) == 1
    rec = records[0]
    assert rec["scores"]["sorter"]["subtype_accuracy"] == 1.0
    assert rec["parameters"]["tracing_backend"] == "none"
    assert rec["parameters"]["tracing"]["braintrust_logging"] is False
    assert rec["parameters"]["tracing"]["langsmith"] is False

    # The serving metadata block (KANBAN-106) rides on every record.
    from src.prompts import get_prompt
    from src.serving_meta import prompt_fingerprint

    serving = rec["serving"]
    assert serving["provider"] == "openrouter"
    assert serving["endpoint"] == "https://openrouter.ai/api/v1"
    assert serving["prompt_fingerprints"]["sorter"] == {
        "version": "sorter_v3", "sha256": prompt_fingerprint(get_prompt("sorter_v3"))}
    assert serving["dataset_fingerprint"] == rec["data_source"]["dataset_fingerprint"]
    assert serving["phase"] in ("cold", "warm", "unknown")
