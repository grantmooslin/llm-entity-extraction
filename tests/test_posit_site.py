"""Tests for the Posit Cloud portal (`site/` → `docs/posit/`).

Covers, all network-free: (1) the pre-render hook's generated includes +
`_variables.yml` (the experiment-log body, the kanban copy, the discussion
copy, the recent-runs table, and the portal stat counters); (2) the
`site/_quarto.yml` contract (website project, `../docs/posit` output,
pre-render wiring, light/dark theme, navbar); (3) the committed rendered
pages under `docs/posit/` (what GitHub Pages actually serves); (4) a
determinism check: re-rendering with the local `quarto` binary must not dirty
`docs/` (skipped when quarto is absent); (5) the append-only discussion board
keeps its fenced `.entry` divs balanced (a regression guard for the repair
that landed with KANBAN-037).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "docs" / "posit-src"
DOCS_DIR = REPO_ROOT / "docs"
POSIT_DIR = DOCS_DIR / "posit"
QUARTO_YML = SITE_DIR / "_quarto.yml"
PRE_RENDER = SITE_DIR / "_pre-render.py"
LOG_JSONL = REPO_ROOT / "reports" / "experiment_log.jsonl"

OPEN_DIV = re.compile(r"^:{3,}\s*\{")
CLOSE_DIV = re.compile(r"^:{3,}\s*$")

# docs/posit-src/ (site source) and reports/experiment_log.jsonl (live log)
# are pruned/gitignored in the monorepo; tests that read them skip there.
# The upstream repo stays the reference for the Posit site contract.
_needs_site = pytest.mark.skipif(
    not SITE_DIR.is_dir() or not LOG_JSONL.is_file(),
    reason="docs/posit-src/ or reports/experiment_log.jsonl absent (pruned/live artifacts; see upstream repo)",
)


def _write_include(outdir: Path) -> dict[str, Path]:
    """Run the pre-render hook into a tmp dir; return the generated files."""
    subprocess.run(
        [sys.executable, str(PRE_RENDER), "--outdir", str(outdir)],
        check=True, capture_output=True, text=True, timeout=120,
    )
    inc = outdir / "_includes"
    return {
        "experiment-log": inc / "experiment-log.md",
        "kanban": inc / "kanban.md",
        "discussion": inc / "discussion.md",
        "recent-runs": inc / "recent-runs.md",
        "variables": outdir / "_variables.yml",
    }


@_needs_site
def test_pre_render_generates_all_includes(tmp_path):
    files = _write_include(tmp_path)
    for name, path in files.items():
        assert path.exists(), f"missing generated include: {name}"


@_needs_site
def test_pre_render_experiment_log_include(tmp_path):
    files = _write_include(tmp_path)
    text = files["experiment-log"].read_text(encoding="utf-8")

    records = [json.loads(l) for l in LOG_JSONL.read_text().splitlines() if l.strip()]
    newest = records[-1]["experiment_name"]

    assert text.startswith("## Index"), "include must open with the run index"
    assert newest in text, "newest run missing from the generated log"
    # per-run sections: one "## " heading per record plus the Index
    sections = len(re.findall(r"^## ", text, flags=re.M))
    assert sections == 1 + len(records), (
        f"expected 1 index + {len(records)} run sections, got {sections}")
    # no render-timestamp (would dirty git on every render)
    assert "_Generated from" not in text
    # no per-document dumps
    assert "Per-document results" not in text
    # deep links into the SPA explorer exist
    assert "../index.html#/run/1" in text


@_needs_site
def test_pre_render_kanban_include(tmp_path):
    files = _write_include(tmp_path)
    text = files["kanban"].read_text(encoding="utf-8")
    assert not text.startswith("# "), "kanban h1 must be stripped (page title)"
    assert "The living, shared Kanban canvas" in text
    assert "KANBAN-037" in text  # the portal card
    assert "## Discussion board" in text  # full board structure preserved


@_needs_site
def test_pre_render_discussion_include(tmp_path):
    files = _write_include(tmp_path)
    text = files["discussion"].read_text(encoding="utf-8")
    assert not text.startswith("---"), "YAML front matter must be stripped"
    assert "## Entries" in text
    assert 'data-card="' in text  # entry divs preserved
    assert ".entry" in text  # entry styling preserved
    # fenced divs must be balanced (append-only entries close correctly)
    depth = 0
    for line in text.splitlines():
        s = line.strip()
        if OPEN_DIV.match(s):
            depth += 1
        elif CLOSE_DIV.match(s):
            depth -= 1
            assert depth >= 0, "stray div close in discussion include"
    assert depth == 0


@_needs_site
def test_pre_render_variables(tmp_path):
    files = _write_include(tmp_path)
    vars_ = yaml.safe_load(files["variables"].read_text(encoding="utf-8"))
    records = [json.loads(l) for l in LOG_JSONL.read_text().splitlines() if l.strip()]
    assert vars_["runs"] == len(records)
    assert vars_["models"] >= 1
    assert vars_["discussion_entries"] >= 1
    assert set(vars_) >= {"runs", "models", "prompt_versions", "tasks",
                          "total_tokens", "last_run", "open_cards",
                          "in_progress_cards", "backlog_cards",
                          "archived_cards", "discussion_entries", "generated"}


@_needs_site
def test_quarto_yml_contract(tmp_path):
    cfg = yaml.safe_load(QUARTO_YML.read_text(encoding="utf-8"))
    assert cfg["project"]["type"] == "website"
    assert cfg["project"]["output-dir"] == "../../docs/posit"
    assert "pre-render" in cfg["project"]
    theme = cfg["format"]["html"]["theme"]
    assert isinstance(theme, dict) and "light" in theme and "dark" in theme
    navbar = cfg["website"]["navbar"]["left"]
    hrefs = [item["href"] for item in navbar]
    assert "experiment-log.qmd" in hrefs
    assert "kanban.qmd" in hrefs
    assert "discussion.qmd" in hrefs
    assert "../index.html" in hrefs  # portal <-> SPA interop


@_needs_site
def test_rendered_pages_committed():
    """The rendered portal pages are committed under docs/posit/ — GitHub
    Pages serves them directly (no build step, no Actions)."""
    assert POSIT_DIR.exists(), "docs/posit/ must exist (quarto render site)"
    index = (POSIT_DIR / "index.html").read_text(encoding="utf-8")
    for page in ("experiment-log.html", "kanban.html", "discussion.html"):
        assert (POSIT_DIR / page).exists(), f"missing rendered page {page}"
        assert page in index, f"landing page must link to {page}"
    assert "../index.html" in index or "./../index.html" in index
    kanban = (POSIT_DIR / "kanban.html").read_text(encoding="utf-8")
    assert "KANBAN-" in kanban
    discussion = (POSIT_DIR / "discussion.html").read_text(encoding="utf-8")
    assert 'class="entry' in discussion
    exp_log = (POSIT_DIR / "experiment-log.html").read_text(encoding="utf-8")
    # every SPA run record (docs/data/runs/{n:03d}.json) is deep-linked from
    # the portal's experiment-log page; self-consistent and immune to the
    # concurrent-eval race (the jsonl can grow after the last render).
    n_runs = len(list((DOCS_DIR / "data" / "runs").glob("*.json")))
    assert exp_log.count("../index.html#/run/") == n_runs, (
        f"expected {n_runs} explorer deep links, got "
        f"{exp_log.count('../index.html#/run/')}")


def test_source_board_divs_stay_balanced():
    """The append-only discussion board must never regress into unbalanced
    fenced divs (KANBAN-037 repaired six untracked closers)."""
    text = (REPO_ROOT / "governance" / "MESSAGE_BOARD_DISCUSSION.qmd").read_text(encoding="utf-8")
    depth = 0
    for line in text.splitlines():
        s = line.strip()
        if OPEN_DIV.match(s):
            depth += 1
        elif CLOSE_DIV.match(s):
            depth -= 1
            assert depth >= 0, "stray close fence in discussion board"
    assert depth == 0, "discussion board has unbalanced fenced divs"


@pytest.mark.skipif(shutil.which("quarto") is None, reason="quarto not installed")
@_needs_site
def test_quarto_render_is_deterministic_and_clean():
    """Re-render with the local quarto must leave no diff under docs/ —
    proof the committed deployment is byte-identical to a fresh render."""
    subprocess.run([sys.executable, str(PRE_RENDER)], check=True,
                   capture_output=True, text=True, timeout=120, cwd=str(SITE_DIR))
    subprocess.run(["quarto", "render"], check=True,
                   capture_output=True, text=True, timeout=600, cwd=str(SITE_DIR))
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "docs"],
        capture_output=True, text=True, check=True, cwd=str(REPO_ROOT),
    ).stdout.strip()
    assert status == "", f"render left tracked changes:\n{status}"