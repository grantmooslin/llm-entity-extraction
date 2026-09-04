"""KANBAN-101 — machine-checkable docclass parity audit (Phase 1 acceptance).

Guards cross-repo prompt alignment, schema↔prompt option lists for champion
and pilot surfaces, and metric-name parity between the entity runner,
SCORING.md §7, and the score-emitter docclass helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.sorter_agent import (
    DOC_SUBCLASS_KEYS,
    DOCCLASS_SCHEMA,
    DOCCLASS_PILOT_SCHEMA,
    SorterAgent,
    DOCCLASS_CLASSES,
)
from src.prompts import get_prompt
from src.prompts_docclass import (
    DOCCLASS_PROMPT_VERSIONS,
    _DOCCONTEXT_V1,
    _PILOT_CONTEXT,
)
from src.score_emitter import DOCCLASS_DASHBOARD_METRICS, DOCCLASS_HEADLINE_METRICS


# Mailroom reference fragments (byte-compatible with entity _DOCCONTEXT_V1).
_MAILROOM_CORRESPONDENCE_LINE = "correspondence ->"
_MAILROOM_INSURANCE_LINE = "insurance_claim ->"


def test_doccontext_v1_includes_correspondence_and_insurance_subclasses():
    assert _MAILROOM_CORRESPONDENCE_LINE in _DOCCONTEXT_V1
    assert _MAILROOM_INSURANCE_LINE in _DOCCONTEXT_V1
    for key in ("demand", "attorney_demand", "carrier", "pde", "outpatient", "inpatient"):
        assert key in _DOCCONTEXT_V1


def test_pilot_context_is_strict_superset_of_extended_v1_context():
    for fragment in ("correspondence ->", "insurance_claim ->", "merger_agreement ->"):
        assert fragment in _PILOT_CONTEXT
    assert "pilot classification mode" in _PILOT_CONTEXT


def test_contracts_docclass_v1_carries_mailroom_cuad_maud_rules():
    prompt = DOCCLASS_PROMPT_VERSIONS["contracts_specialist_docclass_v1"]
    for fragment in (
        "CUAD families",
        "MAUD mergers",
        "cuad_clauses",
        "maud_clauses",
    ):
        assert fragment in prompt


def test_insurance_docclass_v1_carries_hub_and_evidence_rules():
    prompt = DOCCLASS_PROMPT_VERSIONS["insurance_claims_specialist_docclass_v1"]
    assert "pde" in prompt and "inpatient" in prompt
    assert "EVIDENCE-ONLY VISIBILITY" in prompt


def test_champion_and_pilot_prompts_list_all_schema_subclass_keys():
    enum = set(DOCCLASS_SCHEMA["properties"]["doc_subclass"]["enum"])
    pilot_enum = set(DOCCLASS_PILOT_SCHEMA["properties"]["doc_subclass"]["enum"])
    assert enum == set(DOC_SUBCLASS_KEYS)

    # HUB-041 lineage split: the mailroom-named v8 lineages teach the full
    # enum incl. the LOB tokens (property/auto); every docclass version
    # frozen BEFORE the v8 corpus (v7 champion, pilot v3) predates them,
    # is never mutated, and is expected to carry the pre-v8 key set only.
    lob_tokens = {"property", "auto"}
    pre_v8_keys = [k for k in DOC_SUBCLASS_KEYS if k not in lob_tokens]

    champion = SorterAgent(
        prompt_version="sorter_docclass_v7",
        doc_classes=DOCCLASS_CLASSES,
        schema=DOCCLASS_SCHEMA,
    ).system_prompt()
    for key in pre_v8_keys:
        assert key in champion, f"sorter_docclass_v7 missing {key!r}"

    pilot = get_prompt("sorter_docclass_pilot_v3")
    for key in (k for k in pilot_enum if k not in lob_tokens):
        assert key in pilot, f"sorter_docclass_pilot_v3 missing {key!r}"

    mailroom_champion = SorterAgent(
        prompt_version="sorter_mailroom_v0",
        doc_classes=DOCCLASS_CLASSES,
        schema=DOCCLASS_SCHEMA,
    ).system_prompt()
    for key in DOC_SUBCLASS_KEYS:
        assert key in mailroom_champion, f"sorter_mailroom_v0 missing {key!r}"

    mailroom_pilot = get_prompt("sorter_mailroom_pilot_v0")
    for key in pilot_enum:
        assert key in mailroom_pilot, f"sorter_mailroom_pilot_v0 missing {key!r}"


def test_scoring_md_documents_docclass_metric_names():
    text = Path("docs/SCORING.md").read_text(encoding="utf-8")
    section = text.split("## 7. Docclass hierarchical metrics")[1].split("## 8.")[0]
    for name in DOCCLASS_HEADLINE_METRICS:
        assert name in section, f"SCORING.md §7 missing {name!r}"
    assert "1,210 rows" in section
    assert "8 primary classes" in section or "8-class" in section


def test_score_emitter_docclass_metric_names_match_runner():
    runner_src = Path("scripts/eval/run_langfuse_docclass_eval.py").read_text(encoding="utf-8")
    for name in DOCCLASS_HEADLINE_METRICS:
        assert f'"{name}"' in runner_src
    assert set(DOCCLASS_HEADLINE_METRICS).issubset(set(DOCCLASS_DASHBOARD_METRICS))


def test_classify_failure_none_subclass_is_not_subclass_miss():
    from src.dojo_compat import classify_failure

    assert classify_failure(True, None, None) is None
