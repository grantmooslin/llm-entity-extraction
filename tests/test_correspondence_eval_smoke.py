"""Network-free smoke of the Enron correspondence eval scaffold (KANBAN-103).

Covers: GT/blind join (no answer-key leak into sorter text), subclass
stratification, sentiment scoring against the Hub GT assortment, predicted-
field alignment, and ``main_with_args --dry-run`` / a mocked live loop.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.sorter_agent import (
    CORRESPONDENCE_EVAL_SCHEMA,
    SENTIMENT_LABELS,
    normalize_sentiment_label,
    normalize_sentiment_score,
    sentiment_label_from_score,
)
from src.correspondence_eval import (
    CORRESPONDENCE_DOC_TYPE,
    GT_FIELDS,
    PREDICTED_FIELDS,
    append_missing_by_subclass,
    compose_doc_text,
    filter_correspondence,
    join_blind_and_gt,
    merge_eval_rows,
    predicted_aligns_with_gt,
    score_sentiment,
    stratified_by_subclass,
)
from src.prompts import get_prompt, list_prompts


# --- schema / prompt / field alignment --------------------------------------


def test_correspondence_eval_schema_carries_sentiment_and_docclass():
    props = CORRESPONDENCE_EVAL_SCHEMA["properties"]
    assert "doc_type" in props
    assert "doc_subclass" in props
    assert "sentiment_score" in props
    assert "sentiment_label" in props
    assert set(props["sentiment_label"]["enum"]) == set(SENTIMENT_LABELS)
    assert props["sentiment_score"]["minimum"] == -1.0
    assert props["sentiment_score"]["maximum"] == 1.0


def test_correspondence_prompt_registered_and_derives_from_v7():
    assert "sorter_docclass_correspondence_v0" in list_prompts()
    prompt = get_prompt("sorter_docclass_correspondence_v0")
    v7 = get_prompt("sorter_docclass_v7")
    assert prompt.startswith(v7[:300])
    assert "44. CORRESPONDENCE SENTIMENT" in prompt
    assert "sentiment_score" in prompt
    assert "sentiment_label" in prompt
    assert "44. CORRESPONDENCE SENTIMENT" not in v7


def test_correspondence_v1_derives_from_v0_and_adds_channel_trap():
    """GEPA v1 is a .replace() of v0: rule 45 only; v0 bytes stay intact."""
    assert "sorter_docclass_correspondence_v1" in list_prompts()
    v0 = get_prompt("sorter_docclass_correspondence_v0")
    v1 = get_prompt("sorter_docclass_correspondence_v1")
    assert v1.startswith(v0[:400])
    assert v1 != v0
    assert "45. ENRON CHANNEL TRAP" in v1
    assert "45. ENRON CHANNEL TRAP" not in v0
    assert "Never output doc_subclass other" in v1
    assert "Headers (From/To/Cc/Subject/Sent/Fwd/Re/MIME) are TRANSPORT" in v1
    assert "44. CORRESPONDENCE SENTIMENT" in v1


def test_correspondence_v2_derives_from_v1_and_adds_demand_markers():
    """GEPA v2 is a .replace() of v1: rule 46 Hub demand markers only."""
    assert "sorter_docclass_correspondence_v2" in list_prompts()
    v1 = get_prompt("sorter_docclass_correspondence_v1")
    v2 = get_prompt("sorter_docclass_correspondence_v2")
    assert v2.startswith(v1[:400])
    assert v2 != v1
    assert "46. HUB DEMAND MARKERS" in v2
    assert "46. HUB DEMAND MARKERS" not in v1
    assert "BREACH OF CONTRACT" in v2
    assert "FINAL NOTICE" in v2
    assert "kayescholer.com" in v2
    assert "45. ENRON CHANNEL TRAP" in v2


def test_correspondence_v3_derives_from_v2_and_adds_speech_act():
    """GEPA v3 is a .replace() of v2: rule 47 demand speech-act only."""
    assert "sorter_docclass_correspondence_v3" in list_prompts()
    v2 = get_prompt("sorter_docclass_correspondence_v2")
    v3 = get_prompt("sorter_docclass_correspondence_v3")
    assert v3.startswith(v2[:400])
    assert v3 != v2
    assert "47. DEMAND IS THE SPEECH ACT" in v3
    assert "47. DEMAND IS THE SPEECH ACT" not in v2
    assert "OVERRIDES rule 46" in v3
    assert "speech act" in v3.lower() or "performs the demand" in v3
    assert "we could send a demand letter" in v3
    assert "please draft a demand letter" in v3
    assert "NOT demand" in v3
    assert "46. HUB DEMAND MARKERS" in v3
    assert "46. HUB DEMAND MARKERS" in v2
    assert "Keep reasoning to two short sentences" in v3


def test_predicted_fields_align_with_gt_assortment():
    assert PREDICTED_FIELDS == (
        "doc_type", "doc_subclass", "sentiment_label", "sentiment_score")
    assert GT_FIELDS == (
        "expected", "expected_subclass", "sentiment_label", "sentiment_score")
    aligned = predicted_aligns_with_gt(
        {"doc_type": "correspondence", "doc_subclass": "memo",
         "sentiment_label": "positive", "sentiment_score": 0.4},
        {"expected": "correspondence", "expected_subclass": "memo",
         "sentiment_label": "positive", "sentiment_score": 0.4},
    )
    assert aligned["doc_type"]["ok"] is True
    assert aligned["doc_subclass"]["ok"] is True
    assert aligned["sentiment_label"]["ok"] is True


def test_join_does_not_put_gt_in_doc_text():
    blind = [{
        "filename": "a/1.",
        "subject": "Lunch",
        "text": "See you at noon.",
        "metadata": {"custodian": "allen-p"},
    }]
    gt = [{
        "filename": "a/1.",
        "expected": "correspondence",
        "expected_subclass": "email",
        "sentiment_score": 0.2,
        "sentiment_label": "positive",
        "content_topic": "general_business",
        "label_evidence": "ordinary email",
        "sentiment_evidence": "lunch",
        "split": "train",
    }]
    rows = join_blind_and_gt(blind, gt)
    assert len(rows) == 1
    row = rows[0]
    assert row["expected"] == CORRESPONDENCE_DOC_TYPE
    assert row["expected_subclass"] == "email"
    assert row["sentiment_label"] == "positive"
    assert "positive" not in row["doc_text"]
    assert "ordinary email" not in row["doc_text"]
    assert "Subject: Lunch" in row["doc_text"]
    assert "See you at noon." in row["doc_text"]


def test_join_drops_non_correspondence_and_empty_bodies():
    blind = [
        {"filename": "c/1.", "subject": "", "text": ""},
        {"filename": "c/2.", "subject": "Hi", "text": "Hello"},
        {"filename": "k/1.", "subject": "K", "text": "contract text"},
    ]
    gt = [
        {"filename": "c/1.", "expected": "correspondence", "expected_subclass": "email",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
        {"filename": "c/2.", "expected": "correspondence", "expected_subclass": "letter",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
        {"filename": "k/1.", "expected": "contract", "expected_subclass": "license",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
    ]
    rows = join_blind_and_gt(blind, gt)
    assert [r["filename"] for r in rows] == ["c/2."]
    assert filter_correspondence(rows) == rows


def test_stratified_by_subclass_covers_every_class():
    rows = []
    for sub, n in (("email", 40), ("memo", 10), ("demand", 5),
                   ("attorney_demand", 3)):
        for i in range(n):
            rows.append({
                "filename": f"{sub}_{i}",
                "expected": "correspondence",
                "expected_subclass": sub,
                "doc_text": f"{sub} body {i}",
            })
    sample = stratified_by_subclass(rows, 16, seed=42)
    assert len(sample) == 16
    classes = {r["expected_subclass"] for r in sample}
    assert classes == {"email", "memo", "demand", "attorney_demand"}
    # Tiny class contributes every available row, not more.
    assert sum(1 for r in sample if r["expected_subclass"] == "attorney_demand") == 3
    # Deterministic.
    assert [r["filename"] for r in sample] == [
        r["filename"] for r in stratified_by_subclass(rows, 16, seed=42)
    ]


def test_append_missing_by_subclass_adds_only_absent():
    selected = [
        {"filename": "attorney_demand_0", "expected_subclass": "attorney_demand"},
        {"filename": "email_0", "expected_subclass": "email"},
    ]
    pool = [
        {"filename": "attorney_demand_0", "expected_subclass": "attorney_demand"},
        {"filename": "attorney_demand_1", "expected_subclass": "attorney_demand"},
        {"filename": "sanders-r/ecogas/26.", "expected_subclass": "attorney_demand"},
        {"filename": "email_9", "expected_subclass": "email"},
    ]
    merged = append_missing_by_subclass(selected, pool, "attorney_demand")
    assert [r["filename"] for r in merged] == [
        "attorney_demand_0", "email_0",
        "attorney_demand_1", "sanders-r/ecogas/26.",
    ]


def test_merge_eval_rows_first_filename_wins():
    a = [{"filename": "x", "expected_subclass": "email"}]
    b = [{"filename": "x", "expected_subclass": "attorney_demand"},
         {"filename": "y", "expected_subclass": "attorney_demand"}]
    merged = merge_eval_rows(a, b)
    assert [r["filename"] for r in merged] == ["x", "y"]
    assert merged[0]["expected_subclass"] == "email"


def test_extra_attorney_demand_fixture_is_joined_shape():
    from scripts.datasets.load_enron_correspondence import load_local_jsonl
    from pathlib import Path

    path = Path("tests/fixtures/enron_attorney_demand_extras.jsonl")
    rows = load_local_jsonl(path)
    assert len(rows) == 1
    row = rows[0]
    assert row["filename"] == "sanders-r/ecogas/26."
    assert row["expected"] == "correspondence"
    assert row["expected_subclass"] == "attorney_demand"
    assert row["sentiment_label"] == "negative"
    assert "Ecogas" in row["doc_text"]
    assert "demand letter" in row["doc_text"].lower()


def test_sentiment_scoring_band_and_label():
    hit = score_sentiment(0.10, "neutral", 0.0, "neutral")
    assert hit["sentiment_label_ok"] is True
    assert hit["sentiment_score_ok"] is True
    assert hit["sentiment_score_mae"] == pytest.approx(0.10)

    miss = score_sentiment(-0.9, "negative", 0.8, "positive")
    assert miss["sentiment_label_ok"] is False
    assert miss["sentiment_score_ok"] is False
    assert miss["sentiment_score_mae"] == pytest.approx(1.7)

    derived = score_sentiment(-0.4, None, -0.5, "negative")
    assert derived["sentiment_label"] == "negative"
    assert derived["sentiment_label_ok"] is True


def test_sentiment_normalizers():
    assert normalize_sentiment_label("Positive") == "positive"
    assert normalize_sentiment_label("meh") is None
    assert normalize_sentiment_score(1.5) == 1.0
    assert normalize_sentiment_score(-2) == -1.0
    assert sentiment_label_from_score(-0.2) == "negative"
    assert sentiment_label_from_score(0.0) == "neutral"
    assert sentiment_label_from_score(0.2) == "positive"


def test_compose_doc_text():
    assert compose_doc_text("Re: Q3", "Please send the report.") == (
        "Subject: Re: Q3\n\nPlease send the report."
    )
    assert compose_doc_text("", "body only") == "body only"


# --- runner smoke -----------------------------------------------------------


@pytest.fixture
def dump_path(tmp_path):
    rows = [
        {"filename": "e1", "subject": "Hi", "doc_text": "Subject: Hi\n\nSee you.",
         "expected": "correspondence", "expected_subclass": "email",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
        {"filename": "m1", "subject": "Memo", "doc_text": "TO: all\nFROM: legal\nRE: policy",
         "expected": "correspondence", "expected_subclass": "memo",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
        {"filename": "d1", "subject": "Demand", "doc_text": "We demand payment of $5000.",
         "expected": "correspondence", "expected_subclass": "demand",
         "sentiment_label": "negative", "sentiment_score": -0.6},
        {"filename": "skip_contract", "doc_text": "THIS AGREEMENT",
         "expected": "contract", "expected_subclass": "license",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
    ]
    path = tmp_path / "enron.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def test_local_dump_filters_to_correspondence(dump_path):
    from scripts.datasets.load_enron_correspondence import load_local_jsonl

    rows = load_local_jsonl(dump_path)
    assert {r["filename"] for r in rows} == {"e1", "m1", "d1"}
    assert all(r["expected"] == "correspondence" for r in rows)


def test_patch_gt_file_rewrites_matching_rows(tmp_path):
    from scripts.datasets.publish_enron_gt_overrides import patch_gt_file

    src = tmp_path / "gt.jsonl"
    dest = tmp_path / "out.jsonl"
    src.write_text("\n".join([
        json.dumps({"filename": "a", "expected_subclass": "demand"}),
        json.dumps({"filename": "b", "expected_subclass": "email"}),
    ]) + "\n")
    hits = patch_gt_file(src, dest, {"a": {"expected_subclass": "email"}})
    assert hits == 1
    rows = [json.loads(line) for line in dest.read_text().splitlines() if line]
    assert rows[0]["expected_subclass"] == "email"
    assert rows[1]["expected_subclass"] == "email"


def test_committed_gt_overrides_are_unique_and_valid():
    from src.correspondence_eval import read_gt_overrides
    from pathlib import Path

    path = Path("data/gt/enron_correspondence_label_overrides.jsonl")
    overrides = read_gt_overrides(path)
    assert len(overrides) >= 20
    allowed = {
        "demand", "attorney_demand", "meeting_request", "press_release",
        "memo", "email", "letter", "notice",
    }
    assert all(v.get("expected_subclass") in allowed for v in overrides.values())
    # The two official attorney_demand hits stay unlabeled here (no override).
    assert "sanders-r/px/19." not in overrides
    assert "sanders-r/px/17." not in overrides
    assert overrides["sanders-r/all_documents/126."]["expected_subclass"] == "email"


def test_gt_overrides_patch_subclass():
    from src.correspondence_eval import apply_gt_overrides, read_gt_overrides
    from pathlib import Path
    import tempfile

    rows = [
        {"filename": "a", "expected_subclass": "demand"},
        {"filename": "b", "expected_subclass": "email"},
    ]
    patched = apply_gt_overrides(rows, {
        "a": {"expected_subclass": "attorney_demand"},
    })
    assert patched[0]["expected_subclass"] == "attorney_demand"
    assert patched[1]["expected_subclass"] == "email"
    assert rows[0]["expected_subclass"] == "demand"

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ov.jsonl"
        path.write_text(json.dumps({
            "filename": "a",
            "expected_subclass": "attorney_demand",
            "reason": "law-firm sender",
        }) + "\n")
        loaded = read_gt_overrides(path)
        assert loaded == {"a": {"expected_subclass": "attorney_demand"}}


def test_include_all_attorney_demand_merges_extra_dump(tmp_path, monkeypatch):
    """Pinned draw + leftover attorney_demand extras land in one sample."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("BRAINTRUST_API_KEY", "sk-bt-test")
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "log.md"))

    dump = tmp_path / "drawn.jsonl"
    dump.write_text("\n".join(json.dumps(r) for r in [
        {"filename": "e1", "subject": "Hi", "doc_text": "Subject: Hi\n\nSee you.",
         "expected": "correspondence", "expected_subclass": "email",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
        {"filename": "sanders-r/px/19.", "subject": "CalPX",
         "doc_text": "Subject: CalPX\n\nDraft demand for arbitration.",
         "expected": "correspondence", "expected_subclass": "attorney_demand",
         "sentiment_label": "neutral", "sentiment_score": 0.0},
    ]) + "\n")
    extra = Path("tests/fixtures/enron_attorney_demand_extras.jsonl")
    manifest = tmp_path / "filenames.jsonl"
    manifest.write_text(json.dumps({"filename": "e1", "expected_subclass": "email"}) + "\n")

    from scripts.eval.run_correspondence_eval import main_with_args

    code = main_with_args([
        "--local-dumps", str(dump),
        "--filename-manifest", str(manifest),
        "--include-all-attorney-demand",
        "--extra-dumps", str(extra),
        "--dry-run",
        "--no-braintrust-logging",
        "--no-publish-prompt",
        "--experiment-name", "correspondence_attyall_smoke",
    ])
    assert code == 0


def test_gt_overrides_flag_rewrites_sample_subclass(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("BRAINTRUST_API_KEY", "sk-bt-test")
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "log.md"))

    dump = tmp_path / "drawn.jsonl"
    dump.write_text(json.dumps({
        "filename": "dasovich-j/all_documents/2894.",
        "subject": "Arter",
        "doc_text": "From: counsel@arterhadden.com\n\nDemand for payment.",
        "expected": "correspondence",
        "expected_subclass": "demand",
        "sentiment_label": "negative",
        "sentiment_score": -0.5,
    }) + "\n")
    overrides = tmp_path / "overrides.jsonl"
    overrides.write_text(json.dumps({
        "filename": "dasovich-j/all_documents/2894.",
        "expected_subclass": "attorney_demand",
        "reason": "law-firm sender missing from LAW_FIRM_DOMAINS",
    }) + "\n")

    from scripts.eval.run_correspondence_eval import main_with_args

    code = main_with_args([
        "--local-dumps", str(dump),
        "--gt-overrides", str(overrides),
        "--dry-run",
        "--no-braintrust-logging",
        "--no-publish-prompt",
        "--experiment-name", "correspondence_override_smoke",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "gt-overrides" in out
    assert "attorney_demand" in out


def test_correspondence_eval_dry_run(dump_path, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("BRAINTRUST_API_KEY", "sk-bt-test")
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "log.md"))

    from scripts.eval.run_correspondence_eval import main_with_args

    code = main_with_args([
        "--local-dumps", str(dump_path),
        "--stratified", "3",
        "--seed", "42",
        "--dry-run",
        "--no-braintrust-logging",
        "--no-publish-prompt",
        "--experiment-name", "correspondence_smoke_dry",
    ])
    assert code == 0
    assert not (tmp_path / "log.jsonl").exists()


def test_correspondence_eval_mocked_run(dump_path, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("BRAINTRUST_API_KEY", "sk-bt-test")
    monkeypatch.setenv("EXPERIMENT_LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setenv("EXPERIMENT_LOG_MD_PATH", str(tmp_path / "log.md"))
    monkeypatch.setenv("PHOENIX_TRACING", "disabled")
    monkeypatch.setenv("BRAINTRUST_LOGGING", "disabled")

    def fake_classify_json(self, doc_text, subtype_focus=False,
                           correspondence_focus=False):
        text = doc_text.upper()
        if "DEMAND" in text:
            subclass, label, score = "demand", "negative", -0.6
        elif "TO:" in text and "FROM:" in text:
            subclass, label, score = "memo", "neutral", 0.0
        else:
            subclass, label, score = "email", "neutral", 0.0
        return {
            "doc_type": "correspondence",
            "contract_subtype": None,
            "doc_subclass": subclass,
            "sentiment_label": label,
            "sentiment_score": score,
            "confidence": 0.9,
            "reasoning": f"{subclass} {label}",
        }

    monkeypatch.setattr(
        "agents.sorter_agent.SorterAgent.classify_json", fake_classify_json)

    from scripts.eval.run_correspondence_eval import main_with_args

    code = main_with_args([
        "--local-dumps", str(dump_path),
        "--stratified", "3",
        "--seed", "42",
        "--no-braintrust-logging",
        "--no-publish-prompt",
        "--experiment-name", "correspondence_smoke_run",
        "--manifest", str(tmp_path / "manifest.jsonl"),
        "--max-concurrency", "2",
    ])
    assert code == 0
    records = [json.loads(line) for line in
               (tmp_path / "log.jsonl").read_text().strip().splitlines()]
    assert len(records) == 1
    rec = records[0]
    assert rec["task"] == "correspondence_classification"
    assert rec["experiment_name"] == "correspondence_smoke_run"
    assert rec["prompt_versions"]["sorter"] == "sorter_docclass_correspondence_v0"
    assert rec["scores"]["doc_type_accuracy"] == 1.0
    assert rec["scores"]["subclass_accuracy"] == 1.0
    assert rec["scores"]["sentiment_label_accuracy"] == 1.0
    assert rec["scores"]["correspondence_exact"] == 1.0
    assert rec["scores"]["n_rows"] == 3
    assert rec["scores"]["sorter"]["failure_insights"]["n_failed"] == 0
    md = (tmp_path / "log.md").read_text()
    assert "correspondence_smoke_run" in md
    assert "Per-sentiment-label accuracy" in md
    assert "expected sent." in md


def test_report_generator_from_log(tmp_path):
    from scripts.reporting.report_generator import (
        load_log_record,
        render_correspondence_report,
    )

    record = {
        "experiment_name": "corr_report_smoke",
        "task": "correspondence_classification",
        "model": "qwen/qwen3.7-flash",
        "prompt_versions": {"sorter": "sorter_docclass_correspondence_v0"},
        "data_source": {
            "hf_repo": "Lucius-Morningstar/enron-correspondence-dedup",
            "n_samples": 3, "stratified": 3, "seed": 42,
            "ground_truth": "expected + expected_subclass + sentiment_label + sentiment_score",
        },
        "parameters": {"braintrust_logging": True},
        "git": {"commit": "deadbeef"},
        "tokens": {"total": {"prompt_tokens": 10, "completion_tokens": 5, "total_cost": 0.0}},
        "scores": {
            "n_rows": 3, "n_errors": 0,
            "doc_type_accuracy": 1.0, "subclass_accuracy": 0.6667,
            "subclass_accuracy_equiv": 0.6667, "exact_match": 0.6667,
            "sentiment_label_accuracy": 1.0, "sentiment_score_ok": 1.0,
            "sentiment_score_mae": 0.01, "sentiment_score_band": 0.25,
            "correspondence_exact": 0.6667, "confidence": 0.9,
            "per_subclass_accuracy": {"email": 1.0, "memo": 0.0},
            "per_subclass_support": {"email": 2, "memo": 1},
            "per_sentiment_accuracy": {"neutral": 1.0},
            "per_sentiment_support": {"neutral": 3},
            "subclass_confusion": {"email": {"email": 2}, "memo": {"email": 1}},
            "sentiment_confusion": {"neutral": {"neutral": 3}},
            "sorter": {"failure_insights": {
                "n_failed": 1, "mode_counts": {"subclass_miss": 1},
                "failures": [{
                    "filename": "m1", "failure_mode": "subclass_miss",
                    "expected": {"doc_subclass": "memo", "sentiment_label": "neutral"},
                    "predicted": {"doc_subclass": "email", "sentiment_label": "neutral"},
                    "reasoning": "looks like email",
                }],
            }},
        },
    }
    md = render_correspondence_report(record)
    assert "correspondence_exact" in md
    assert "sentiment_label_accuracy" in md
    assert "subclass_miss" in md
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps(record) + "\n")
    assert load_log_record("corr_report_smoke", log)["task"] == "correspondence_classification"
    import sys
    import scripts.reporting.report_generator as rg
    old = sys.argv
    try:
        sys.argv = [
            "report_generator.py",
            "--experiment", "corr_report_smoke",
            "--from-log",
            "--experiment-log", str(log),
            "--output-dir", str(tmp_path),
        ]
        assert rg.main() == 0
    finally:
        sys.argv = old
    written = (tmp_path / "report_corr_report_smoke.md").read_text()
    assert "0.6667" in written
    assert "Per-subclass accuracy" in written
