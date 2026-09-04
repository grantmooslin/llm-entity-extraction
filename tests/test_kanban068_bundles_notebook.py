"""KANBAN-068 guards: the doc-type-bundles exemplar notebook must stay
network-free, structurally valid, and produce its honest-gap summary from
real experiment-log data when executed headlessly."""

import json
import re
from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")

REPO_ROOT = Path(__file__).resolve().parents[1]
NB = REPO_ROOT / "notebooks" / "03_doc_type_bundles.ipynb"

NETWORK_HINTS = re.compile(
    r"(requests\.|urllib|http[s]?://|socket|curl|wget|openai|anthropic|"
    r"api[_-]?key|BRAINTRUST|LANGFUSE)",
    re.IGNORECASE,
)


def _load():
    return nbformat.read(NB, as_version=4)


def test_notebook_exists_and_is_valid():
    nb = _load()
    assert len(nb.cells) >= 6
    code_cells = [c for c in nb.cells if c.cell_type == "code"]
    assert any("llm_dojo_scoring" in c.source for c in code_cells)


def test_cells_are_network_free_and_llm_free():
    nb = _load()
    for cell in nb.cells:
        src = cell.source
        # URLs appear only inside markdown prose/comments about the package pin
        if cell.cell_type == "code":
            assert not NETWORK_HINTS.search(src), f"network/LLM hint in code cell:\n{src[:120]}"


def test_bootstrap_is_kernel_cwd_proof():
    nb = _load()
    first_code = next(c for c in nb.cells if c.cell_type == "code")
    assert "find_repo_root" in first_code.source
    assert "pyproject.toml" in first_code.source


def _execute_nb(tmp_path):
    from nbclient import NotebookClient

    nb = _load()
    # Hostile-cwd proof per the KANBAN-078 precedent: kernel cwd = notebooks/
    # (NOT the repo root) — find_repo_root() must walk up to locate the repo.
    client = NotebookClient(nb, timeout=180, kernel_name="python3",
                            resources={"metadata": {"path": str(REPO_ROOT / "notebooks")}})
    client.execute()
    return nb


def test_headless_execution_produces_honest_gap_summary(tmp_path):
    """Execute against real reports/experiment_log.jsonl: contract must show
    real benchmark rows; court_opinion and insurance_claim must be
    declared-pending (the family's documented honest gap)."""
    if not (REPO_ROOT / "reports" / "experiment_log.jsonl").is_file():
        pytest.skip(
            "reports/experiment_log.jsonl absent (pruned heavy asset in monorepo; "
            "see upstream llm-entity-extraction repo)"
        )
    nb = _execute_nb(tmp_path)
    streams = [
        o["text"]
        for c in nb.cells if c.cell_type == "code"
        for o in c.get("outputs", [])
        if o.get("output_type") == "stream"
    ]
    joined = "\n".join(streams)
    assert "honest gap summary" in joined
    assert re.search(r"contract\s+->\s+REAL benchmark rows scored", joined)
    assert re.search(r"court_opinion\s+->\s+declared-pending", joined)
    assert re.search(r"insurance_claim\s+->\s+declared-pending", joined)
