"""Environment variable helpers.

Require specific env vars are set, with helpful error messages, and load the
repo's dotenv files (``braintrust.env`` first, then ``.env``) so scripts can
run without exporting anything. Real shell environment variables always win.

The live (gitignored) dotenv files live under ``config/environments/`` — the
shared ``ENV_DIR`` / ``BRAINTRUST_ENV_FILE`` / ``DOTENV_FILE`` /
``LANGFUSE_ENV_FILE`` constants below are the single source of truth for where
every loader and CLI default resolves them; ``resolve_env_file()`` maps
bare filenames (and ``--env-file`` args) into that directory.
"""

from __future__ import annotations

import os
from argparse import ArgumentParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_DIR = REPO_ROOT / "config" / "environments"
BRAINTRUST_ENV_FILE = ENV_DIR / "braintrust.env"
BRAINTRUST_SANDBOX_ENV_FILE = ENV_DIR / "braintrust-sandbox.env"
DOTENV_FILE = ENV_DIR / ".env"
LANGFUSE_ENV_FILE = ENV_DIR / "langfuse.env"

# Externally-funded OpenRouter key (research funding). Set in .env under this
# name; only ever resolved through ``--research-funding-key`` and gated to
# fully-ready production runs by ``assert_production_run``.
RESEARCH_FUNDING_KEY_ENV = "RESEARCH_FUNDING_OPENROUTER_API_KEY"

# Floor for a run to count as production-scale: at least this many rows, or
# the full dataset when it is smaller.
PRODUCTION_RUN_MIN_ROWS = 100


def resolve_env_file(path: str | Path | None, *, default: Path) -> Path:
    """Resolve a dotenv path for a loader or CLI ``--env-file`` arg.

    Absolute paths pass through unchanged; bare filenames (e.g.
    ``"langfuse.env"``) resolve under ``ENV_DIR`` (``config/environments/``);
    ``None`` falls back to ``default``.
    """
    if path is None:
        return default
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return ENV_DIR / resolved


def load_env() -> None:
    """Load ``braintrust.env`` then ``.env`` into the environment (idempotent).

    Both files live under ``config/environments/``. Existing environment
    variables are never overridden. Safe to call from any script entry point.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for env_file in (BRAINTRUST_ENV_FILE, DOTENV_FILE):
        if env_file.exists():
            load_dotenv(env_file, override=False)


def require_env(*names: str) -> tuple[str, ...]:
    """Validate that all given environment variables are set and non-empty.

    Returns the resolved values as a tuple. Exits with a helpful message if any are missing.
    """
    load_env()
    values = []
    missing = []
    for name in names:
        value = os.environ.get(name, "").strip()
        if not value:
            missing.append(name)
        else:
            values.append(value)
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
    return tuple(values)


def get_env(name: str, default: str = "") -> str:
    """Get an environment variable with a default fallback."""
    load_env()
    return os.environ.get(name, default).strip()


def bool_env(name: str, default: bool = False) -> bool:
    """Get a boolean environment variable."""
    value = os.environ.get(name, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def resolve_openrouter_key(research_funding: bool = False) -> str:
    """Resolve the OpenRouter API key for an eval run.

    Default: the run's normal ``OPENROUTER_API_KEY``. With
    ``research_funding=True`` (the ``--research-funding-key`` flag) the
    externally-funded key from ``RESEARCH_FUNDING_OPENROUTER_API_KEY`` is
    REQUIRED instead — it is paid from external research funding, so it must
    never fire on pilots or dry-runs (enforced by ``assert_production_run``).
    """
    if research_funding:
        (key,) = require_env(RESEARCH_FUNDING_KEY_ENV)
        return key
    (key,) = require_env("OPENROUTER_API_KEY")
    return key


def assert_production_run(research_funding: bool, *, dry_run: bool,
                          selected_rows: int, total_rows: int,
                          min_rows: int = PRODUCTION_RUN_MIN_ROWS) -> None:
    """Gate ``--research-funding-key`` runs to fully-ready production scale.

    The funding key is paid from external research funding, so it must never
    fire on a dry-run or a pilot-scale sample — both are refused with a hard
    error before any LLM call is made. A run passes only when it is NOT a
    dry-run and selects at least ``min_rows`` rows (or the full dataset when
    it is smaller). Call after dataset selection, before the dry-run block.
    """
    if not research_funding:
        return
    if dry_run:
        raise SystemExit(
            "--research-funding-key is reserved for FULLY READY PRODUCTION RUNS: "
            "refusing a dry-run (no LLM spend, no external funding). Re-run without the flag."
        )
    floor = min(total_rows, min_rows)
    if selected_rows < floor:
        raise SystemExit(
            f"--research-funding-key is reserved for FULLY READY PRODUCTION RUNS: this run "
            f"selects only {selected_rows}/{total_rows} rows (floor: {floor}). "
            f"Re-run without the flag."
        )
    print("--research-funding-key: paying with the externally-funded "
          f"{RESEARCH_FUNDING_KEY_ENV} key")


def add_research_funding_flag(parser: ArgumentParser) -> None:
    """Add the ``--research-funding-key`` flag to an eval runner's parser."""
    parser.add_argument(
        "--research-funding-key", action="store_true",
        help="Pay with the externally-funded OpenRouter key "
             f"({RESEARCH_FUNDING_KEY_ENV}) — REFUSED on dry-runs and pilot-scale "
             "samples; only fully-ready production runs may spend external funding.",
    )
