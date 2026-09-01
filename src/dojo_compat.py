"""Compatibility layer between this repo and the ``llm_dojo_scoring`` package.

The scoring/error-analysis definitions now live in ``llm_dojo_scoring``; the
local ``src/`` modules (``field_scoring``, ``metrics``, ``scorers``,
``bootstrap``, ``cost_models``) are thin re-export shims so llm-mailroom's
``pip install -e .`` imports keep working unchanged. This module holds the
small pieces where the package's contract deliberately diverges from this
repo's call sites:

- ``classify_failure(doc_type_ok, subclass_ok, predicted_subclass)``
  — the hierarchical docclass failure-mode classifier. The package's
  ``classify_docclass_failure(row)`` takes a row dict and never returns
  ``None`` for correct rows; the runner's original contract (positional
  booleans, ``None`` on success) is preserved here.
- Docclass subclass scoping is NOT shimmed: ``agents/sorter_agent.py`` keeps
  its ``doc_type``-scoped ``equivalent_doc_subclasses`` /
  ``normalize_doc_subclass`` (the package uses ``allowed=`` sets, and the
  ``SUBCLASS_DIMENSIONS`` mapping has no package counterpart).

Importing this module also wires the repo taxonomy into the package settings
(``src/dojo_config.py::apply_taxonomy_settings``).
"""

from __future__ import annotations

from src.dojo_config import apply_taxonomy_settings  # noqa: F401  (side-effect: wiring)

__all__ = ["classify_failure"]


def classify_failure(doc_type_ok: bool, subclass_ok: bool,
                     predicted_subclass: str | None) -> str | None:
    """Failure mode for the hierarchical docclass task (KANBAN-033).

    Returns ``None`` when the row is fully correct, ``"doc_type_miss"`` when
    the primary class was wrong, and ``"subclass_miss"`` when the primary
    class was right but the second-level subclass was wrong. Rows with no
    subclass ground truth (``subclass_ok is None``) never receive a
    ``subclass_miss`` failure mode.
    """
    if doc_type_ok and subclass_ok is not False:
        return None
    if not doc_type_ok:
        return "doc_type_miss"
    return "subclass_miss"
