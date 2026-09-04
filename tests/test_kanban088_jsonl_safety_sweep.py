"""KANBAN-088 pins: the family-wide JSONL line-boundary hazard sweep.

Contract established by this card:
1. ONE canonical sanitizer definition lives in
   ``scripts/datasets/_jsonl_safety.py``; the KANBAN-087 exporter names are
   re-exports of it (object-identical).
2. Every Hub-bound / line-oriented JSONL row writer in ``scripts/`` + ``src/``
   writes through ``safe_jsonl_line`` (or the sanitizer directly, exporter).
3. Any remaining ``ensure_ascii=False`` site must carry an explicit
   ``KANBAN-088-EXEMPT`` marker documenting WHY split-safety doesn't apply
   (field-value dumps guarded downstream, CSV cell values, hash inputs).
Network-free.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.datasets._jsonl_safety import (  # noqa: E402
    LINE_BOUNDARY_HAZARDS,
    safe_jsonl_line,
    sanitize_line_boundary_chars,
)

ADOPTERS = [
    "scripts/reporting/backfill_extraction_kpis.py",
    "scripts/datasets/build_docclass_merged.py",
    "scripts/datasets/build_legalbench_full_pack.py",
    "scripts/datasets/publish_enron_correspondence_dedup.py",
    "scripts/datasets/stream_legalbench_tasks_to_bt.py",
    "scripts/datasets/publish_enron_correspondence.py",
    "scripts/datasets/build_docclass_v5.py",
    "scripts/datasets/build_mailroom_corpus_dumps.py",
]


def test_sanitizer_escapes_and_roundtrips_losslessly():
    rec = {"doc_text": "a\u2028b\u2029c\x85d", "n": 1, "nested": {"k": ["\u2028"]}}
    line = safe_jsonl_line(rec)
    assert "\u2028" not in line and "\u2029" not in line and "\x85" not in line
    assert "\\u2028" in line and "\\u0085" in line
    assert json.loads(line) == rec


def test_exporter_names_are_object_identical_reexports():
    exp = importlib.import_module("scripts.datasets.export_bt_to_hf")
    assert exp.sanitize_line_boundary_chars is sanitize_line_boundary_chars
    assert exp.LINE_BOUNDARY_HAZARDS == LINE_BOUNDARY_HAZARDS


def test_every_row_writer_adopts_the_shared_helper():
    for rel in ADOPTERS:
        t = (REPO_ROOT / rel).read_text()
        assert "from scripts.datasets._jsonl_safety import safe_jsonl_line" in t, rel
        assert "safe_jsonl_line(" in t, rel


def test_no_unmarked_hazard_sites_remain():
    """Any ensure_ascii=False outside the safety module / exporter must either
    be gone or carry the explicit KANBAN-088-EXEMPT justification."""
    offenders = []
    for base in ("scripts", "src"):
        for py in (REPO_ROOT / base).rglob("*.py"):
            rel = str(py.relative_to(REPO_ROOT))
            if rel.endswith("_jsonl_safety.py") or rel.endswith("export_bt_to_hf.py"):
                continue  # canonical module + already-pinned exporter writer
            for i, ln in enumerate(py.read_text(errors="replace").splitlines(), 1):
                if "ensure_ascii=False" in ln and "KANBAN-088-EXEMPT" not in ln:
                    offenders.append(f"{rel}:{i}")
    assert not offenders, f"unmarked ensure_ascii=False sites: {offenders}"


def test_exemption_markers_carry_justification():
    expected_files = {
        "scripts/datasets/build_docclass_merged.py",
        "scripts/datasets/build_docclass_pilot.py",
        "scripts/datasets/build_docclass_v5.py",
        "src/braintrust_utils.py",
    }
    seen = set()
    for rel in expected_files:
        for ln in (REPO_ROOT / rel).read_text().splitlines():
            if "KANBAN-088-EXEMPT" in ln:
                seen.add(rel)
                assert len(ln.split("KANBAN-088-EXEMPT:", 1)[-1]) > 20, (
                    f"{rel}: exemption lacks justification"
                )
    assert seen == expected_files
