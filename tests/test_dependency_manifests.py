"""Manifest↔imports contract pins for the KANBAN-081 dependency batches.

Network-free guards so the modular install profiles cannot rot silently:

1. The CORE dependency floor stays exactly the agent -> prompt -> scoring
   chain's needs — no task-specific package sneaks back into the default
   install (and nothing the chain needs ever leaves it).
2. Every ``requirements/<batch>.txt`` file declares the SAME packages as the
   matching ``[project.optional-dependencies]`` extra in pyproject.toml
   (same names, same version floors) — the manifests-drift class that bit
   llm-dojo-scoring re-pins twice before (KANBAN-044/067).
3. A live AST census of the shipped packages (``agents/``, ``src/``)
   re-derives the third-party import surface and checks it lands inside the
   declared batches: anything imported by core must be a core dep; anything
   imported by the tracing modules must come from the tracing batch.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CORE_EXPECTED = {
    "langchain-core": ">=1.0",
    "langchain-openai": ">=0.3",
    "openai": ">=1.60",
    "requests": ">=2.32.0",
    "python-dotenv": ">=1.0.0",
    "PyYAML": ">=6.0",
    "structlog": ">=24.0",
    "llm-dojo-scoring": "@ git+https://github.com/Exios66/llm-dojo-scoring.git@v0.10.0",
}

EXTRA_TO_BATCH_FILE = {
    "tracing": "tracing.txt",
    "evals": "evals.txt",
    "datasets": "datasets.txt",
    "reporting": "reporting.txt",
    "embeddings": "embeddings.txt",
    "notebooks": "notebooks.txt",
    "dev": "dev.txt",
}

# Third-party top-level modules allowed per surface (AST census side).
CORE_IMPORT_ALLOWLIST = {
    "langchain_core", "langchain_openai", "openai", "requests",
    "dotenv", "yaml", "structlog", "llm_dojo_scoring",
}
TRACING_IMPORT_ALLOWLIST = {
    "langfuse", "phoenix", "openinference", "opentelemetry",
}

# Modules whose imports belong to a BATCH (in addition to core) even though
# they sit in src/ — the batch-owner map: allowed = CORE ∪ owner-batch.
BATCH_MODULE_OWNERS = {
    "src/tracing.py": TRACING_IMPORT_ALLOWLIST,
    "src/langfuse_tracing.py": TRACING_IMPORT_ALLOWLIST,
    "src/phoenix_tracing.py": TRACING_IMPORT_ALLOWLIST,
    "src/langfuse_config.py": TRACING_IMPORT_ALLOWLIST,
    "src/braintrust_utils.py": {"braintrust"},
    "src/braintrust_config.py": {"braintrust"},
    "src/image_utils.py": {"PIL", "pdf2image"},
    "src/monte_carlo.py": {"numpy", "matplotlib"},
}


def _load_pyproject() -> dict:
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _parse_requirements_txt(path: Path) -> dict[str, str]:
    """name -> spec string ('' when unpinned); skips comments/blanks/-r lines."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        m = re.match(r"^([A-Za-z0-9._-]+)\s*(.*)$", line)
        assert m is not None, f"unparseable requirement line: {line!r}"
        out[m.group(1)] = m.group(2).strip()
    return out


def _third_party_toplevel(py_file: Path) -> set[str]:
    import sys

    stdlib = set(sys.stdlib_module_names)
    first_party = {"agents", "src", "config", "tests", "scripts", "site"}
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    tops: set[str] = set()
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods = [node.module]
        for m in mods:
            top = m.split(".")[0]
            if top not in stdlib and top not in first_party:
                tops.add(top)
    return tops


# ---------------------------------------------------------------- test 1
def test_pyproject_core_is_exactly_the_agent_chain_floor():
    deps = _load_pyproject()["project"]["dependencies"]
    got: dict[str, str] = {}
    for d in deps:
        m = re.match(r"^([A-Za-z0-9._-]+)\s*(.*)$", d)
        assert m is not None, f"unparseable dependency entry: {d!r}"
        got[m.group(1)] = m.group(2).strip() or "ANY"
    assert got == CORE_EXPECTED, (
        "Core dependency floor drifted from the pinned contract.\n"
        f"  unexpected: {sorted(set(got) - set(CORE_EXPECTED))}\n"
        f"  missing:    {sorted(set(CORE_EXPECTED) - set(got))}"
    )


# ---------------------------------------------------------------- test 2
def test_batch_files_match_pyproject_extras():
    extras = _load_pyproject()["project"]["optional-dependencies"]
    for extra, fname in EXTRA_TO_BATCH_FILE.items():
        req = _parse_requirements_txt(REPO_ROOT / "requirements" / fname)
        py_names: dict[str, str] = {}
        for entry in extras[extra]:
            if entry.startswith("llm-entity-extraction["):
                continue  # self-references ([dev]->[tracing], [all]->...) checked below
            m = re.match(r"^([A-Za-z0-9._-]+)\s*(.*)$", entry)
            assert m is not None, f"unparseable extra entry: {entry!r}"
            py_names[m.group(1)] = m.group(2).strip()
        if extra != "dev":
            # pytest appears in dev.txt only; strip it from the dev batchfile view
            req.pop("pytest", None)
            req.pop("pytest-mock", None) if extra != "dev" else None
        assert req == py_names, (
            f"[{extra}] extra vs requirements/{fname} drift:\n"
            f"  pyproject: {py_names}\n  batchfile: {req}"
        )


# ---------------------------------------------------------------- test 3
def test_all_extra_and_all_txt_reference_every_non_dev_batch():
    extras = _load_pyproject()["project"]["optional-dependencies"]
    joined = extras["all"][0]
    for batch in ("tracing", "evals", "datasets", "reporting", "embeddings", "notebooks"):
        assert batch in joined
    all_txt = (REPO_ROOT / "requirements" / "all.txt").read_text(encoding="utf-8")
    for batch in ("tracing", "evals", "datasets", "reporting", "embeddings", "notebooks"):
        assert f"-r {batch}.txt" in all_txt
    # dev is deliberately NOT part of [all]: runtime installs never need pytest
    assert "dev" not in joined


# ---------------------------------------------------------------- test 4
def test_dead_pins_stay_dead_and_undeclared_deps_stay_declared():
    """pandas/pyarrow were removed in KANBAN-081 (zero imports); openpyxl +
    huggingface_hub were ADDED there after being found undeclared."""
    deps = _load_pyproject()["project"]["dependencies"]
    blob = " ".join(deps).lower()
    assert "pandas" not in blob and "pyarrow" not in blob, "dead pins resurrected"
    extras_blob = str(_load_pyproject()["project"]["optional-dependencies"]).lower()
    assert '"openpyxl' in extras_blob.replace("'", '"') or "openpyxl>=" in extras_blob
    assert "huggingface-hub>=" in extras_blob or "huggingface_hub>=" in extras_blob


# ---------------------------------------------------------------- test 5
def test_ast_census_core_imports_stay_inside_the_core_floor():
    offenders: dict[str, set[str]] = {}
    for sub in ("agents", "src"):
        for py in sorted((REPO_ROOT / sub).rglob("*.py")):
            rel = str(py.relative_to(REPO_ROOT)).replace(os.sep, "/")
            allow = BATCH_MODULE_OWNERS.get(rel)
            tops = _third_party_toplevel(py)
            if allow is None:
                bad = tops - CORE_IMPORT_ALLOWLIST
                if bad:
                    offenders[rel] = bad
            else:
                bad = tops - (CORE_IMPORT_ALLOWLIST | allow)
                if bad:
                    offenders[rel] = bad
    assert not offenders, (
        "Third-party imports outside the declared batches — add them to the "
        f"matching manifest deliberately or move the module: {offenders}"
    )


# ---------------------------------------------------------------- test 6
def test_root_requirements_is_core_only_with_pointer_header():
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    parsed = _parse_requirements_txt(REPO_ROOT / "requirements.txt")
    assert set(parsed) == set(CORE_EXPECTED), (
        f"root requirements.txt must stay core-only, got: {sorted(parsed)}"
    )
    assert "requirements/" in text and "test_dependency_manifests" in text, (
        "pointer header to the batch files went missing"
    )
