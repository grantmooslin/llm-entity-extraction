"""Score-emitter bridge — connects pipeline runs to the KANBAN-061 registry
layer (llm-dojo-scoring v0.5.0 ``registry`` / ``bundles`` / ``emitter`` /
``pruning``).

Thin by design: the package owns definitions, routing, and storage. This
module only adapts THIS repo's run records to the unified emitter:

- ``build_emitter()`` — local JSONL manifest sink (``reports/scores_manifest.jsonl``)
  plus an optional Langfuse sink (only when ``langfuse=True`` AND credentials
  resolve; otherwise the sink is inert — never fatal).
- ``emit_run_scores()`` — emit a dict of computed metric values for one
  agent/run; registry-unknown names are skipped (returned, never silently
  dropped) so new KPIs surface as registry work, not lost scores.
- ``dashboard_names()`` / ``headline_names()`` — what a dashboard panel for
  an agent shows (tier-capped bundle intersection).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from llm_dojo_scoring.emitter import Emitter, LangfuseSink, LocalManifestSink
from llm_dojo_scoring.pruning import dashboard_metrics, headline_metrics

from src.env_utils import load_env

__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "CORRESPONDENCE_HEADLINE_METRICS",
    "DOCCLASS_DASHBOARD_METRICS",
    "DOCCLASS_HEADLINE_METRICS",
    "build_emitter",
    "dashboard_names",
    "docclass_dashboard_names",
    "docclass_headline_names",
    "emit_docclass_run_scores",
    "emit_run_scores",
    "headline_names",
]

DEFAULT_MANIFEST_PATH = Path("reports/scores_manifest.jsonl")

# Docclass hierarchical task metrics (KANBAN-101). These live in the
# experiment-log / Langfuse eval runners but are not yet in the shared
# llm-dojo-scoring registry — emit_docclass_run_scores writes them to the
# local manifest with a docclass_ agent prefix.
DOCCLASS_HEADLINE_METRICS: tuple[str, ...] = (
    "doc_type_accuracy",
    "subclass_accuracy",
    "subclass_accuracy_equiv",
    "exact_match",
)
# Correspondence-only extras (KANBAN-103). Live on the dashboard so
# emit_docclass_run_scores registers them; they are NOT T0 docclass headlines
# (the mixed-surface runner does not emit them).
CORRESPONDENCE_HEADLINE_METRICS: tuple[str, ...] = (
    "sentiment_label_accuracy",
    "correspondence_exact",
)
DOCCLASS_DASHBOARD_METRICS: tuple[str, ...] = DOCCLASS_HEADLINE_METRICS + (
    "doc_type_accuracy_ci",
    "subclass_accuracy_ci",
    "exact_match_ci",
    "confidence",
) + CORRESPONDENCE_HEADLINE_METRICS + (
    "sentiment_label_accuracy_ci",
    "sentiment_score_ok",
    "sentiment_score_mae",
    "correspondence_exact_ci",
)


def build_emitter(
    manifest_path: str | Path | None = None,
    *,
    langfuse: bool = False,
) -> Emitter:
    """Emitter with a local manifest sink; optional Langfuse when asked for.

    ``langfuse=True`` still yields a working emitter when credentials are
    missing — the LangfuseSink simply reports itself unavailable.
    """
    load_env()
    sinks: list[Any] = [LocalManifestSink(manifest_path or DEFAULT_MANIFEST_PATH)]
    if langfuse:
        sinks.append(LangfuseSink())
    return Emitter(sinks=sinks)


def emit_run_scores(
    emitter: Emitter,
    agent: str,
    run_id: str,
    metrics: dict[str, Any],
    *,
    doc_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """Emit ``{metric_name: value}`` for one agent/run.

    Returns ``(emitted, skipped)`` — skipped names are either unknown to the
    registry (fail-fast philosophy stops at the emitter, not the pipeline)
    or ``None``-valued.
    """
    emitted: list[str] = []
    skipped: list[str] = []
    for name, value in metrics.items():
        try:
            emitter.registry.get(name)
        except KeyError:
            skipped.append(name)
            continue
        if value is None:
            skipped.append(name)
            continue
        emitter.emit_score(
            agent,
            doc_id=doc_id,
            metric_name=name,
            value=value,
            metadata=metadata or {},
            run_id=run_id,
        )
        emitted.append(name)
    return emitted, skipped


def dashboard_names(agent: str) -> list[str]:
    """Default dashboard panel for an agent (T0+T1 bundle intersection)."""
    return dashboard_metrics(agent)


def headline_names(agent: str) -> list[str]:
    """Strictly T0 — the one-number-per-agent view."""
    if agent in ("docclass_sorter", "sorter_docclass"):
        return list(DOCCLASS_HEADLINE_METRICS)
    return headline_metrics(agent)


def docclass_headline_names() -> list[str]:
    """T0 docclass hierarchical metrics for dashboard panels."""
    return list(DOCCLASS_HEADLINE_METRICS)


def docclass_dashboard_names() -> list[str]:
    """T0+CI docclass metrics for richer dashboard panels."""
    return list(DOCCLASS_DASHBOARD_METRICS)


def _register_docclass_metrics(emitter: Emitter) -> None:
    """Ad-hoc registry entries until llm-dojo-scoring ships docclass metrics."""
    from llm_dojo_scoring.registry import MetricTier

    for name in DOCCLASS_DASHBOARD_METRICS:
        try:
            emitter.registry.get(name)
        except KeyError:
            tier = (
                MetricTier.HEADLINE
                if name in DOCCLASS_HEADLINE_METRICS
                else MetricTier.CORE
            )
            emitter.register_metric(
                name,
                tier,
                units="float[0,1]",
                description=f"KANBAN-101 docclass hierarchical metric: {name}",
            )


def emit_docclass_run_scores(
    emitter: Emitter,
    run_id: str,
    metrics: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """Emit docclass headline/dashboard metrics to the local manifest.

    Docclass metric names are registered ad-hoc when absent from the shared
    registry; bootstrap CI payloads (dict values) are skipped.
    """
    _register_docclass_metrics(emitter)
    docclass_only = {
        k: v
        for k, v in metrics.items()
        if k in DOCCLASS_DASHBOARD_METRICS and isinstance(v, (int, float))
    }
    other = {
        k: v
        for k, v in metrics.items()
        if k not in docclass_only and isinstance(v, (int, float))
    }
    emitted, skipped = emit_run_scores(
        emitter, "sorter", run_id, other, metadata=metadata,
    )
    agent = "docclass_sorter"
    for name, value in docclass_only.items():
        if value is None:
            skipped.append(name)
            continue
        emitter.emit_score(
            agent,
            doc_id=None,
            metric_name=name,
            value=value,
            metadata=metadata or {},
            run_id=run_id,
        )
        emitted.append(name)
    return emitted, skipped
