#!/usr/bin/env python3
"""Pre-render hook for the Posit Cloud Quarto website (`site/` → `docs/posit/`).

Regenerates every DERIVED input of the portal before `quarto render` so the
rendered site never goes stale (idempotent; nothing here is hand-edited):

  ``_includes/experiment-log.md`` — canonical run index + per-run sections
      rendered from ``reports/experiment_log.jsonl`` by the SAME
      ``src.experiment_log`` code that builds ``reports/experiment_log.md``
      (per-document result dumps are omitted — the SPA explorer owns them —
      and each run gains an ``[Interactive explorer detail]`` deep link into
      ``../index.html#/run/{n}`` when the SPA run record exists)
  ``_includes/kanban.md``        — ``MESSAGE_BOARD.md`` (h1 stripped; the page
    supplies its own title)
  ``_includes/discussion.md``    — ``MESSAGE_BOARD_DISCUSSION.qmd`` with its
    YAML front matter stripped (agent colors and entry styling preserved)
  ``_includes/recent-runs.md``   — newest runs table with explorer deep links
  ``_variables.yml``             — portal stat counters for ``{{< var >}}``

Run standalone with ``python3 site/_pre-render.py`` (writes into the site
dir); ``--outdir DIR`` redirects the writes for tests. The ``quarto render``
project hook runs the same command with no arguments.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
SITE_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT / "src"))


def _ensure_scoring_deps() -> None:
    """Re-exec under the repo venv when the active interpreter lacks the
    scoring package (KANBAN-094). Quarto invokes bare ``python3`` for this
    hook; system interpreters may not have ``llm_dojo_scoring`` installed,
    which made ``from experiment_log import ...`` die mid-render. Re-exec is
    transparent: same argv, same stdio, same exit code."""
    import os

    try:
        import llm_dojo_scoring  # noqa: F401
    except ImportError:
        pass
    else:
        return
    candidate = ROOT / ".venv" / "bin" / "python"
    if (candidate.exists()
            and os.path.realpath(candidate) != os.path.realpath(sys.executable)):
        os.execv(str(candidate), [str(candidate), str(Path(__file__)), *sys.argv[1:]])


_ensure_scoring_deps()

from experiment_log import render_full_log  # noqa: E402

# Sections that exist only to dump per-document/results content — omitted from
# the generated include (the interactive SPA explorer owns the per-doc view).
_RESULT_SECTIONS = (
    "Per-document results",
    "Sorter outputs",
    "Predicted extractions (specialist output per document)",
    "Predicted outputs",
)

N_RECENT_RUNS = 8


def _load_records() -> list[dict]:
    path = ROOT / "reports" / "experiment_log.jsonl"
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _total_tokens(record: dict) -> Any:
    tokens = record.get("tokens") or {}
    if isinstance(tokens.get("total"), dict):
        return tokens["total"].get("total_tokens")
    return tokens.get("total_tokens")


def _headline(record: dict) -> str:
    """Mirror the canonical index headline rule (src/experiment_log.py)."""
    scores = record.get("scores") or {}
    if isinstance(scores.get("overall_extraction_score"), (int, float)):
        return f"extraction {scores['overall_extraction_score']:.4f}"
    if isinstance(scores.get("exact_match"), (int, float)):
        return f"exact_match {scores['exact_match']:.4f}"
    if isinstance(scores.get("extractor"), dict) and isinstance(
            scores["extractor"].get("overall_extraction_score"), (int, float)):
        sorter = scores.get("sorter", {}).get("exact_match")
        sorter_s = f"{sorter:.4f}" if isinstance(sorter, (int, float)) else "—"
        return (f"sorter {sorter_s} / "
                f"extractor {scores['extractor']['overall_extraction_score']:.4f}")
    if isinstance(scores.get("accuracy"), (int, float)):
        return f"accuracy {scores['accuracy']:.4f}"
    return "—"


def _prompt_label(record: dict) -> str:
    prompt = record.get("prompt_version")
    if not prompt and isinstance(record.get("prompt_versions"), dict):
        prompt = " + ".join(str(v) for v in record["prompt_versions"].values())
    return str(prompt) if prompt else "—"


def _experiment_log_include(records: list[dict]) -> str:
    """The experiment-log page body: canonical renderer output minus per-doc
    dumps, plus per-run explorer deep links."""
    clean: list[dict] = []
    for record in records:
        stripped = copy.deepcopy(record)
        stripped["results"] = []  # per-doc view is the SPA explorer's job
        clean.append(stripped)

    text = render_full_log(clean, "Experiment Log")

    lines: list[str] = []
    dropping: str | None = None
    for line in text.splitlines():
        if dropping is not None:
            if line.startswith("### ") or line.startswith("## ") or line == "---":
                dropping = None
            else:
                continue
        if line.startswith("# "):
            continue  # the page supplies its own h1
        if line.startswith("_Generated from "):
            continue  # render timestamp would dirty git on every render
        for header in _RESULT_SECTIONS:
            if line.startswith(f"### {header}"):
                dropping = header
                break
        else:
            lines.append(line)

    # Re-attach canonical run numbers (## sections appear in record order
    # after the Index) and add per-run explorer deep links.
    out: list[str] = []
    section_idx = 0
    for line in lines:
        if line.startswith("## ") and not line.startswith("## Index"):
            section_idx += 1
            out.append(line)
            if (ROOT / "docs" / "data" / "runs" / f"{section_idx:03d}.json").exists():
                out.append("")
                out.append(f"> [Interactive explorer detail →](../index.html#/run/{section_idx})")
            out.append("")
        elif line == "" and out and out[-1] == "":
            continue
        else:
            out.append(line)
    return "\n".join(out).strip() + "\n"


def _recent_runs_include(records: list[dict]) -> str:
    """Newest-runs table for the portal landing page (deep-linked to the SPA)."""
    rows: list[list[str]] = []
    for i, record in enumerate(records[-N_RECENT_RUNS:][::-1], start=1):
        idx = len(records) - N_RECENT_RUNS + i
        name = record.get("experiment_name", "—")
        if (ROOT / "docs" / "data" / "runs" / f"{idx:03d}.json").exists():
            name = f"[{name}](../index.html#/run/{idx})"
        rows.append([
            str(idx),
            name,
            record.get("model", "—"),
            _prompt_label(record),
            _headline(record),
            str(record.get("n_rows", "—")),
            str(_total_tokens(record) or "—"),
        ])
    header = ["#", "Experiment", "Model", "Prompt(s)", "Headline score", "Rows", "Tokens"]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def _kanban_include() -> str:
    """MESSAGE_BOARD.md with its h1 stripped (the page supplies its own title)."""
    text = (ROOT / "governance" / "MESSAGE_BOARD.md").read_text(encoding="utf-8").strip()
    return re.sub(r"^# .*\n\n?", "", text, count=1) + "\n"


_REPO_BLOB = "https://github.com/Exios66/llm-entity-extraction/blob/main/"
_RELATIVE_LINK = re.compile(r"\[([^\]]+)\]\(([^)#\s][^)\s]*)\)")


def _absolutize_links(markdown: str) -> str:
    """Rewrite repo-relative markdown links to GitHub blob URLs.

    The discussion board is authored with repo-root-relative links
    (``[tests/test_env_utils.py](tests/test_env_utils.py)``) that GitHub's
    renderer resolves fine — but when Quarto renders the same file from the
    ``site/`` project, those targets don't exist relative to the portal, so
    every link emits an "Unable to resolve link target" warning. The portal
    copy rewrites them to their GitHub blob URL (issue anchors ``#NNN``,
    fragment links ``#…``, and absolute URLs are left untouched).
    """

    def _replace(m: re.Match) -> str:
        label, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://", "mailto:", "#", "/")):
            return m.group(0)
        if "://" in target:
            return m.group(0)
        return f"[{label}]({_REPO_BLOB}{target})"

    return _RELATIVE_LINK.sub(_replace, markdown)


def _discussion_include() -> str:
    """MESSAGE_BOARD_DISCUSSION.qmd without its YAML front matter."""
    text = (ROOT / "governance" / "MESSAGE_BOARD_DISCUSSION.qmd").read_text(encoding="utf-8")
    match = re.match(r"^---\n.*?\n---\n", text, flags=re.S)
    if match:
        text = text[match.end():]
    return _absolutize_links(text.strip()) + "\n"


def _board_stats(kanban_text: str) -> dict[str, int]:
    """Lane counts from the open kanban table + the archive."""
    stats = {"backlog": 0, "in_progress": 0, "blocked": 0, "in_review": 0,
             "done": 0, "archived": 0}
    m_open = re.search(r"^## Key Kanban table.*?^## Discussion board",
                       kanban_text, flags=re.S | re.M)
    m_archive = re.search(r"^Archive \(completed work.*$", kanban_text,
                          flags=re.S | re.M)
    open_block = m_open.group(0) if m_open else ""
    for row in re.finditer(r"^| KANBAN-\d+ \|[^|]*\| `([a-z_]+)` \|", open_block,
                           flags=re.M):
        status = row.group(1)
        if status in stats:
            stats[status] += 1
    if m_archive:
        archive_block = m_archive.group(0)
        stats["archived"] = len(
            re.findall(r"^\| KANBAN-\d+ \|", archive_block, flags=re.M))
    return stats


def _variables(records: list[dict], discussion_text: str, kanban_text: str) -> dict:
    """Stat counters consumed by `{{< var >}}` substitution on the pages."""
    total_tokens = sum(_total_tokens(r) or 0 for r in records)
    stats = _board_stats(kanban_text)
    tasks = sorted({str(r.get("task", "—")) for r in records})
    return {
        "runs": len(records),
        "models": len({str(r.get("model", "—")) for r in records}),
        "prompt_versions": len({_prompt_label(r) for r in records}),
        "tasks": len(tasks),
        "task_list": ", ".join(tasks),
        "total_tokens": _fmt_int(total_tokens),
        "last_run": str(records[-1].get("timestamp", "—"))[:10] if records else "—",
        "open_cards": stats["backlog"] + stats["in_progress"] + stats["blocked"],
        "in_progress_cards": stats["in_progress"],
        "backlog_cards": stats["backlog"],
        "archived_cards": stats["archived"],
        "discussion_entries": len(re.findall(r"^::: \{\.entry", discussion_text,
                                             flags=re.M)),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def _fmt_int(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def main_with_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=SITE_DIR,
                        help="write directory (default: the site dir)")
    args = parser.parse_args(argv)
    outdir = args.outdir
    includes = outdir / "_includes"
    includes.mkdir(parents=True, exist_ok=True)

    records = _load_records()
    kanban_text = _kanban_include()
    discussion_text = _discussion_include()

    (includes / "experiment-log.md").write_text(
        _experiment_log_include(records), encoding="utf-8")
    (includes / "kanban.md").write_text(kanban_text, encoding="utf-8")
    (includes / "discussion.md").write_text(discussion_text, encoding="utf-8")
    (includes / "recent-runs.md").write_text(
        _recent_runs_include(records), encoding="utf-8")

    import yaml
    vars_path = outdir / "_variables.yml"
    vars_path.write_text(yaml.safe_dump(
        _variables(records, discussion_text, kanban_text),
        sort_keys=False, default_flow_style=False), encoding="utf-8")
    print(f"pre-render: wrote {len(records)} runs, kanban, discussion, "
          f"recent-runs, _variables.yml → {outdir}")
    return 0


def main() -> None:
    raise SystemExit(main_with_args(sys.argv[1:]))


if __name__ == "__main__":
    main()