"""Real-browser audit of the GH Pages site (skipped without Chrome).

Serves docs/ over HTTP and drives headless Chrome via the DevTools Protocol
to verify EVERY view renders with zero console errors/exceptions and no
layout overflow — catching silent errors, visual breakage, and uncaught
issues that the stubbed-DOM render audit cannot see (real computed styles,
event dispatch, navigation, theming, mobile viewport).
"""

from __future__ import annotations

import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT = REPO_ROOT / "tests" / "assets" / "browser_audit.mjs"


@pytest.mark.skipif(
    not Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists()
    and shutil.which("google-chrome") is None
    and shutil.which("chromium") is None,
    reason="no Chrome/Chromium available",
)
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "data" / "meta.json").is_file(),
    reason="docs/data/ site data absent (regenerate via scripts/site/build_site.py)",
)
def test_browser_audit_every_view():
    docs = REPO_ROOT / "docs"

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):  # silence the server
            pass

    handler = functools.partial(QuietHandler, directory=str(docs))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            chrome = None
            if Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists():
                chrome = str(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
            elif shutil.which("google-chrome"):
                chrome = shutil.which("google-chrome")
            else:
                chrome = shutil.which("chromium")
            node_env = dict(os.environ)
            node_env["CHROME_BIN"] = chrome
            node_env["SITE_PORT"] = str(port)
            proc = subprocess.run(
                ["node", str(AUDIT)],
                capture_output=True, text=True, timeout=300,
                env=node_env,
            )
        finally:
            server.shutdown()
    assert proc.returncode == 0, f"browser audit failed:\n{proc.stdout}\n{proc.stderr}"
    assert "ok     index" in proc.stdout
    assert "ok     run" in proc.stdout
