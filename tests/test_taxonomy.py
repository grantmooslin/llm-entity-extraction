"""Tests for taxonomy loading and agent config resolution."""

from src.taxonomy import agent_config, doc_class_by_key, doc_class_keys, doc_class_labels, load_taxonomy


def test_doc_classes_match_prompts():
    keys = doc_class_keys()
    # The shared 6-class surface plus the MAUD corpus class merger_agreement
    # (KANBAN-033) — the first six stay the sorter's default surface.
    assert keys == [
        "contract", "corporate_record", "due_diligence",
        "correspondence", "insurance_claim", "compliance_filing",
        "court_opinion", "merger_agreement",
    ]


def test_doc_class_subclass_dimensions():
    """The data-necessitated second level per class (KANBAN-033): consideration
    types for merger_agreement, record types for corporate_record. The
    tertiary level is absent by design — MAUD categories and EDGAR exhibit
    codes are dataset metadata, not classification dimensions."""
    merger = doc_class_by_key("merger_agreement")
    subclasses = {s["key"] for s in merger["subclasses"]}
    assert subclasses == {"all_cash", "all_stock", "mixed_cash_stock",
                          "mixed_cash_stock_election", "other"}
    corp = doc_class_by_key("corporate_record")
    corp_subclasses = {s["key"] for s in corp["subclasses"]}
    assert {"bylaws", "articles_of_incorporation", "certificate_of_formation",
            "powers_of_attorney", "subsidiary_list", "indenture", "other"} <= corp_subclasses
    # No class carries a tertiary_classes key — the level was dropped.
    for cls in load_taxonomy()["doc_classes"]:
        assert "tertiary_classes" not in cls


def test_doc_class_labels():
    labels = doc_class_labels()
    assert labels["contract"] == "Contract / Agreement"
    assert labels["court_opinion"] == "Court Opinion"


def test_doc_class_by_key():
    entry = doc_class_by_key("contract")
    assert entry["specialist"] == "contracts_specialist"
    assert "field_types" in entry
    assert doc_class_by_key("banana") is None


def test_insurance_claim_v8_surface():
    """v8 LOB expansion (HUB-028): property/auto subclasses + the purpose/gist
    extraction fields ride the insurance_claim taxonomy entry (they exist on
    every v8 row and on the InsuranceClaimExtraction schema)."""
    ins = doc_class_by_key("insurance_claim")
    subclasses = {s["key"] for s in ins["subclasses"]}
    assert {"carrier", "pde", "outpatient", "inpatient",
            "property", "auto"} <= subclasses
    ft = set(ins["field_types"])
    assert {"subject_matter", "keywords"} <= ft


def test_agent_config_defaults():
    cfg = agent_config("sorter")
    assert cfg["model"] == "qwen/qwen3.7-flash"
    assert cfg["max_input_chars"] == 12000
    judge = agent_config("judge")
    assert judge["model"] == "deepseek/deepseek-v4-flash"
    assert agent_config("no_such_agent") == {}


def test_load_taxonomy_has_confidence_gates():
    taxonomy = load_taxonomy()
    confidence = taxonomy.get("confidence", {})
    assert confidence["high"] == 0.95
    assert confidence["low"] == 0.70
