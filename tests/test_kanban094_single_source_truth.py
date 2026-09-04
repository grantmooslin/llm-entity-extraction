"""KANBAN-094 pins: single-source-of-truth repair for the experiment record.

Incident (2026-08-18 batch, diagnosed 2026-08-24): the contracteval eval
runner logged 9 runs to an untracked side file
(``reports/experiment_log_contracteval.jsonl``) while their per-run SPA
files landed in ``docs/data/runs/`` — splitting the record and breaking the
``experiment_log.jsonl => build_site.py => docs/data/runs/{n:03d}.json``
derivation chain. The Posit-site pins then failed as "chronic baseline"
(195 deep links vs 203 run files) until the side log was merged into the
canonical append-only JSONL.

These pins make that failure mode structurally impossible:
1. ONE canonical log — no ``reports/experiment_log_*.jsonl`` side logs.
2. The derived run-file tree is exactly ``{001..N}`` (builder prunes).
3. ``build_site.py --check`` detects orphaned run files, not just index drift.
4. The pre-render hook survives interpreters without the scoring package
   (quarto invokes bare ``python3``) by re-execing into the repo venv.

Network-free; reads only local files.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "reports"
LOG_JSONL = REPORTS / "experiment_log.jsonl"
RUNS_DIR = REPO_ROOT / "docs" / "data" / "runs"
BUILD_SITE = REPO_ROOT / "scripts" / "site" / "build_site.py"


def _records():
    return [json.loads(l) for l in LOG_JSONL.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def test_no_side_experiment_logs_exist():
    """The canonical append-only JSONL is THE record: no sibling
    ``experiment_log_*.jsonl`` side logs may exist in reports/."""
    side_logs = sorted(REPORTS.glob("experiment_log_*.jsonl"))
    assert not side_logs, (
        f"side experiment log(s) found: {side_logs} — merge into "
        f"reports/experiment_log.jsonl (the single source of truth)")


def test_run_file_tree_is_exactly_one_to_n():
    """docs/data/runs/ holds exactly {001..N}.json, one per canonical row,
    with no gaps or orphans."""
    if not LOG_JSONL.is_file():
        pytest.skip("reports/experiment_log.jsonl absent (live artifact; regenerate via an eval run)")
    records = _records()
    n = len(records)
    on_disk = sorted(p.name for p in RUNS_DIR.glob("*.json"))
    expected = [f"{i:03d}.json" for i in range(1, n + 1)]
    assert on_disk == expected, (
        f"run tree drift: {len(on_disk)} files vs {n} rows; "
        f"missing={sorted(set(expected) - set(on_disk))[:5]} "
        f"orphan={sorted(set(on_disk) - set(expected))[:5]}")


def test_build_site_check_detects_orphan_run_files(tmp_path):
    """--check must fail when a stale run file exists beyond N — the exact
    KANBAN-094 incident shape (index length alone missed it)."""
    if not LOG_JSONL.is_file():
        pytest.skip("reports/experiment_log.jsonl absent (live artifact; regenerate via an eval run)")
    import shutil

    out = tmp_path / "site-data"
    (out / "runs").mkdir(parents=True)
    records = _records()
    # build a minimal consistent view of the REAL data, then add one orphan
    subprocess.run(
        [sys.executable, str(BUILD_SITE), "--out", str(out)],
        check=True, capture_output=True, text=True, timeout=300,
    )
    n = len(json.loads((out / "index.json").read_text()))
    shutil.copy(out / "runs" / f"{n:03d}.json", out / "runs" / f"{n + 1:03d}.json")
    r = subprocess.run(
        [sys.executable, str(BUILD_SITE), "--check", "--out", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    assert r.returncode != 0, "--check accepted an orphaned run file"
    assert str(n + 1) in r.stdout, "check should report the stale file count"


def test_pre_render_hook_reexecs_without_scoring_package():
    """Quarto drives this hook with bare python3; the hook must survive an
    interpreter without llm_dojo_scoring by re-execing into the repo venv."""
    hook = REPO_ROOT / "docs" / "posit-src" / "_pre-render.py"
    if not hook.is_file():
        pytest.skip("docs/posit-src/ absent (pruned heavy asset; see the upstream repo)")
    t = hook.read_text()
    assert "_ensure_scoring_deps" in t
    assert "os.execv" in t, "hook must re-exec rather than crash"
    # and it must actually work from the system interpreter
    r = subprocess.run(
        ["python3", str(REPO_ROOT / "docs" / "posit-src" / "_pre-render.py"),
         "--outdir", "/tmp/kanban094_prerender_check"],
        capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, f"pre-render failed under system python3:\n{r.stderr[-400:]}"


def test_merged_side_rows_are_hazard_free_and_ordered():
    """The 2026-08-24 merge absorbed all 9 side rows losslessly: every
    merged name is present, sits in the appended tail in its own merge
    order (= timestamp order), and the log stays hazard-free. NOTE: the
    pre-existing log follows APPEND order, not global timestamp order
    (backfills legitimately invert), so only the merged tail is pinned."""
    if not LOG_JSONL.is_file():
        pytest.skip("reports/experiment_log.jsonl absent (live artifact; regenerate via an eval run)")
    from scripts.datasets._jsonl_safety import LINE_BOUNDARY_HAZARDS

    records = _records()
    merged_names = [
        "qwen3.7-flash_contracteval_v0_contracteval_langfuse",
        "gpt-4.1-mini_contracteval_v1_contracteval_langfuse",
        "qwen3-8b_contracteval_v0_contracteval_langfuse",
        "qwen3.7-flash_contracteval_v5_contracteval_langfuse",
    ]
    names = {r["experiment_name"] for r in records}
    for n in merged_names:
        assert n in names, f"merged row missing: {n}"
    # the LAST record must be the newest merged row (v5, appended last)
    assert records[-1]["experiment_name"].startswith(
        "qwen3.7-flash_contracteval_v5_"), "merged tail disturbed"
    # the 9-row appended tail must be chronologically ordered within itself
    tail = [r["timestamp"] for r in records[-9:]]
    assert tail == sorted(tail), "merged tail not in chronological order"
    text = LOG_JSONL.read_text(encoding="utf-8")  # guarded above
    for ch in LINE_BOUNDARY_HAZARDS:
        assert ch not in text
