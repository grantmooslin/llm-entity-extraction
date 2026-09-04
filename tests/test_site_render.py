"""Headless render audit for the experiment-log site (GitHub issue #1).

Exercises EVERY view (index, every task/prompt/model group, every run, up to
3 document traces per run, the prompt diff) against the REAL built data with
a stubbed DOM and asserts zero rendering errors. Skipped when node is
unavailable (the site is vanilla JS; pytest does not require it).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "tests" / "assets" / "site_render_audit.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "data" / "meta.json").is_file(),
    reason="docs/data/ site data absent (regenerate via scripts/site/build_site.py)",
)
def test_every_view_renders_cleanly():
    proc = subprocess.run(
        ["node", str(HARNESS)],
        capture_output=True, text=True, timeout=300, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"render audit failed:\n{proc.stdout}\n{proc.stderr}"
    assert "ALL VIEWS RENDER CLEANLY" in proc.stdout
    assert "runs " in proc.stdout and "OK" in proc.stdout
    assert "docs " in proc.stdout and "OK" in proc.stdout
