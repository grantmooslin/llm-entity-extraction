"""HUB-035 — mailroom-corpus dump builder + specialist-arm infrastructure.

Offline (no network, no LLM): the builder's ``load_dataset`` is monkeypatched
to tiny v7-shaped and v8-shaped fixture splits, exercising the join, the
dynamic GT-key derivation, the arm manifests, and the build manifest exactly
as a real run would. The specialist-arm tests cover the four canonical arms
of ``run_langfuse_docclass_specialist_eval``.
"""

from __future__ import annotations

import json

import pytest

from scripts.datasets.build_mailroom_corpus_dumps import (
    SPECIALIST_ARMS,
    build_dump_rows,
    main_with_args,
)
from scripts.eval.run_langfuse_docclass_specialist_eval import (
    CORRESPONDENCE_FIELD_KEYS,
    CORPORATE_RECORD_FIELD_KEYS,
    GT_FIELD_TYPES,
    SPECIALIST_DOC_TYPES,
    enrich_generic_rows,
    select_agent_rows,
)

# -- fixtures -----------------------------------------------------------------

V7_GT_KEYS = ("intent", "subject_matter", "keywords", "sentiment")


def _gt_row(name, expected, subclass, split="train", **extra):
    row = {
        "filename": name,
        "expected": expected,
        "expected_subclass": subclass,
        "split": split,
    }
    row.update(extra)
    return row


@pytest.fixture
def v7_configs():
    blind = [
        {"filename": "c1.md", "doc_text": "This agreement is made between the parties...", "split": "train"},
        {"filename": "i1.md", "doc_text": "Claim number 12345 for policy coverage...", "split": "train"},
        {"filename": "e1.md", "doc_text": "Dear counsel, we demand payment of...", "split": "test"},
        {"filename": "r1.md", "doc_text": "Board resolution of the corporation resolved...", "split": "test"},
    ]
    truth = [
        _gt_row("c1.md", "contract", "consulting_agreement", intent="", subject_matter="consulting"),
        _gt_row("i1.md", "insurance_claim", "property", claim_number="12345", policy_number="POL-9"),
        _gt_row("e1.md", "correspondence", "attorney_demand", intent="payment_demand"),
        _gt_row("r1.md", "corporate_record", "bylaws", filing_number="F-77"),
    ]
    return {"train": (blind[:2], truth[:2]), "test": (blind[2:], truth[2:])}


def test_build_dump_rows_joins_and_derives_gt_keys_dynamically(v7_configs):
    rows = build_dump_rows(v7_configs)
    assert len(rows) == 4
    by_name = {r["filename"]: r for r in rows}
    # doc_text comes from the default (textless ground_truth) config
    assert by_name["i1.md"]["doc_text"].startswith("Claim number")
    # expected/expected_subclass from the GT config
    assert by_name["i1.md"]["expected"] == "insurance_claim"
    assert by_name["i1.md"]["expected_subclass"] == "property"
    # GT scalar keys are whatever the config carries (dynamic, not hardcoded)
    assert by_name["i1.md"]["gt_fields"] == {"claim_number": "12345", "policy_number": "POL-9"}
    # empty-string GT values never become expected_fields
    assert by_name["c1.md"]["expected_fields"] == {"subject_matter": "consulting"}


def test_build_dump_rows_skips_textless_or_unmatched_rows():
    configs = {
        "train": (
            [{"filename": "a.md", "doc_text": "hello"}],
            [_gt_row("a.md", "contract", "nda"), _gt_row("ghost.md", "contract", "nda")],
        )
    }
    rows = build_dump_rows(configs)
    assert [r["filename"] for r in rows] == ["a.md"]


def test_v8_schema_growth_flows_through():
    """v8's extra GT metadata keys ride along untouched (no hardcoded key list)."""
    configs = {
        "train": (
            [{"filename": "v8.md", "doc_text": "FNOL for a auto policy..."}],
            [_gt_row("v8.md", "insurance_claim", "auto",
                     lob="auto", accident_type="rear_end", source_dataset="bdr_claims")],
        )
    }
    rows = build_dump_rows(configs)
    assert rows[0]["gt_fields"]["lob"] == "auto"
    assert rows[0]["expected_fields"]["accident_type"] == "rear_end"


def test_main_writes_dump_manifests_and_build_manifest(tmp_path, v7_configs, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "datasets").mkdir(parents=True)
    monkeypatch.setattr(
        "scripts.datasets.build_mailroom_corpus_dumps.load_split_configs",
        lambda revision, dataset: v7_configs,
    )
    rc = main_with_args(["--revision", "bb57c5ad", "--label", "v7"])
    assert rc == 0
    dump = tmp_path / "data" / "datasets" / "mailroom_corpus_v7.jsonl"
    assert dump.exists()
    lines = [json.loads(l) for l in dump.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 4
    # four canonical arm manifests, one per specialist family
    for arm in SPECIALIST_ARMS:
        assert (tmp_path / "data" / "manifests" / f"mailroom_corpus_v7_{arm}.jsonl").exists()
    contracts = tmp_path / "data" / "manifests" / "mailroom_corpus_v7_contracts_specialist.jsonl"
    assert len(contracts.read_text(encoding="utf-8").strip().splitlines()) == 1
    build = json.loads(
        (tmp_path / "data" / "manifests" / "mailroom_corpus_v7.build.json").read_text())
    assert build["revision"] == "bb57c5ad"
    assert build["rows_by_class"] == {
        "contract": 1, "corporate_record": 1, "correspondence": 1, "insurance_claim": 1}
    assert all(f["sha256"] for f in build["files"])


# -- specialist arms ----------------------------------------------------------

def test_all_four_canonical_arms_registered():
    assert set(SPECIALIST_DOC_TYPES) == {
        "contracts_specialist",
        "insurance_claims_specialist",
        "correspondence_specialist",
        "corporate_records_specialist",
    }
    assert SPECIALIST_ARMS.keys() == SPECIALIST_DOC_TYPES.keys()


def test_select_agent_rows_per_arm():
    rows = [
        {"expected": "contract", "id": 1},
        {"expected": "merger_agreement", "id": 2},
        {"expected": "insurance_claim", "id": 3},
        {"expected": "correspondence", "id": 4},
        {"expected": "corporate_record", "id": 5},
    ]
    assert [r["id"] for r in select_agent_rows(rows, "contracts_specialist")] == [1, 2]
    assert [r["id"] for r in select_agent_rows(rows, "insurance_claims_specialist")] == [3]
    assert [r["id"] for r in select_agent_rows(rows, "correspondence_specialist")] == [4]
    assert [r["id"] for r in select_agent_rows(rows, "corporate_records_specialist")] == [5]
    with pytest.raises(ValueError):
        select_agent_rows(rows, "due_diligence_specialist")


def test_enrich_generic_rows_prefers_nonempty_gt():
    rows = [{
        "gt_fields": {"intent": "request", "content_topic": "", "keywords": "[\"a\"]"},
        "expected_fields": {"stale": "precomputed"},
    }]
    enrich_generic_rows(rows, CORRESPONDENCE_FIELD_KEYS)
    # fresh GT wins when present; precomputed values survive for empty slots
    assert rows[0]["expected_fields"]["intent"] == "request"
    assert rows[0]["expected_fields"]["keywords"] == ["a"]
    assert rows[0]["expected_fields"]["stale"] == "precomputed"
    # empty GT never overwrites
    assert "content_topic" not in rows[0]["expected_fields"]


def test_gt_keys_match_corpus_reality():
    """Arms score the GT the corpus carries (HUB-022 matrix), not the
    output schemas — sender/filing_number GT does not exist yet."""
    assert set(CORRESPONDENCE_FIELD_KEYS) == {
        "intent", "sentiment_label", "content_topic", "subject_matter", "keywords"}
    assert set(CORPORATE_RECORD_FIELD_KEYS) == {"subject_matter", "keywords"}
    assert GT_FIELD_TYPES["correspondence_specialist"]["intent"] == "name"
    assert GT_FIELD_TYPES["correspondence_specialist"]["keywords"] == "entity_list:free_text"


def test_enrich_decodes_json_encoded_list_gt():
    rows = [{
        "gt_fields": {"keywords": '["voice mail", "demand letter"]',
                      "intent": "request"},
    }]
    enrich_generic_rows(rows, CORRESPONDENCE_FIELD_KEYS)
    assert rows[0]["expected_fields"]["keywords"] == ["voice mail", "demand letter"]
    assert rows[0]["expected_fields"]["intent"] == "request"
    # non-JSON strings pass through untouched
    rows = [{"gt_fields": {"subject_matter": "payment dispute over services"}}]
    enrich_generic_rows(rows, ("subject_matter",))
    assert rows[0]["expected_fields"]["subject_matter"] == "payment dispute over services"
