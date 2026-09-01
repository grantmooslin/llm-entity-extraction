"""Arize Phoenix tracing — local OpenTelemetry-native default.

Phoenix is Apache/Elastic-licensed, runs as a single local process with SQLite/
in-memory storage, and is OpenTelemetry-native. It ingests spans as they are
produced with no Docker/multi-service stack, and the DB file can be deleted
when a batch is done — ideal for pour-in, poke-around, discard workflows.

Design
------
- One OpenTelemetry TracerProvider is lazily initialised per process.
- The provider emits spans over OTLP HTTP to the Phoenix endpoint
  (``PHOENIX_ENDPOINT``, default ``http://localhost:6006/v1/traces``).
- ``trace_document`` opens a ROOT span per evaluated document (name =
  ``trace_name``) carrying session id, tags, filename, expected value and the
  caller's metadata as span attributes; ``agent_observation`` opens a child
  span under it. Outputs and deterministic logic scores are recorded on the
  spans as events (``set_output`` / ``score``), so Phoenix holds the SAME
  per-document data shape the Langfuse mirror records.
- Best-effort ``OpenAIInstrumentor`` (openinference-instrumentation-openai,
  already a dependency) instruments the OpenAI SDK used by the LangChain
  agents, so every LLM call lands as a nested span with the full prompt,
  response and token usage — captured under the agent span via context
  propagation. Instrumentation failure only degrades to manual spans; it
  never breaks a run.
- The tracer is a no-op when PHOENIX_TRACING is disabled or when provider
  initialisation failed — evaluation runs identically without observability.
- ``flush()``/``shutdown()`` force-flush the batch processor WITHOUT shutting
  the provider down (a shutdown would permanently disable the process's
  tracer); batch spans are exported on flush or on a later exit.
"""

from __future__ import annotations

import json
import os
import structlog
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = structlog.get_logger(__name__)

_TRUE_VALUES = {"1", "true", "enabled", "yes", "on"}


def phoenix_enabled() -> bool:
    """Return True when Phoenix tracing should be active.

    Reads PHOENIX_TRACING (default: enabled). When disabled the module
    degrades to a no-op tracer so runs are unaffected.

    ``load_env()`` runs first so a dotenv ``PHOENIX_TRACING=disabled`` wins
    even when this module is imported before the caller loads dotenv
    (KANBAN-103: the first correspondence run imported the tracer at
    module-import time and default-on OTLP-spammed a down Phoenix).
    """
    try:
        from src.env_utils import load_env

        load_env()
    except Exception:  # noqa: BLE001 — observability must never break the run
        pass
    return os.environ.get("PHOENIX_TRACING", "enabled").strip().lower() in _TRUE_VALUES


def phoenix_endpoint_reachable(timeout: float = 0.5) -> bool:
    """Return True when the Phoenix HTTP server answers.

    Probes the REST base (``PHOENIX_ENDPOINT`` with the ``/v1/traces`` suffix
    stripped). A down server must not attach a BatchSpanProcessor — that is
    what produced the 50+ ``Failed to export span batch`` lines on the
    KANBAN-103 v0 run.
    """
    try:
        import urllib.request

        req = urllib.request.Request(_phoenix_server_base(), method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 — down/refused/timeout => treat as absent
        return False


def _instrument_openai() -> None:
    """Best-effort OpenInference instrumentation of the OpenAI SDK.

    The LangChain agents call OpenRouter through langchain-openai, which uses
    the OpenAI SDK under the hood; instrumenting it emits one span per LLM
    call (model, token usage, latency, output) nested under the current agent
    span. ``hide_input_text`` drops the FULL request payload from the spans —
    the ContractEval contexts run up to 300k chars each and would otherwise
    balloon the local Phoenix SQLite DB; the bounded question/output/scores
    stay on the manual document + agent spans.
    """
    try:
        from openinference.instrumentation import TraceConfig
        from openinference.instrumentation.openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument(config=TraceConfig(hide_input_text=True))
        logger.info("phoenix_openai_instrumented")
    except Exception:  # noqa: BLE001 - observability must never break the run
        logger.warning("phoenix_openai_instrument_failed", exc_info=True)


def phoenix_project_name() -> str:
    """Return the Phoenix project every run traces into.

    ``PHOENIX_PROJECT`` (default ``llm-dojo`` — the dedicated project for this
    repo's prompt iterations) is attached to spans as the
    ``openinference.project.name`` resource attribute, so Phoenix routes each
    run's traces under that project instead of the ``default`` one.
    """
    return os.environ.get("PHOENIX_PROJECT", "llm-dojo").strip() or "llm-dojo"


def _phoenix_server_base() -> str:
    """Strip the OTLP path off PHOENIX_ENDPOINT to get the REST server base."""
    endpoint = os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")
    return endpoint.split("/v1/")[0]


def _init_opentelemetry() -> Any | None:
    """Initialise OpenTelemetry SDK with Phoenix OTLP exporter.

    Returns the tracer provider or None on failure / disabled.
    """
    if not phoenix_enabled():
        logger.info("phoenix_tracing_disabled", reason="PHOENIX_TRACING not enabled")
        return None
    if not phoenix_endpoint_reachable():
        logger.info(
            "phoenix_tracing_disabled",
            reason="phoenix endpoint unreachable",
            endpoint=os.environ.get(
                "PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces"),
        )
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        endpoint = os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")
        service_name = os.environ.get("PHOENIX_SERVICE_NAME", "llm-entity-extraction")
        project = phoenix_project_name()
        resource = Resource.create({
            "service.name": service_name,
            # Phoenix routes ingested spans to the project named here — the
            # dedicated llm-dojo project (created on first ingest).
            "openinference.project.name": project,
        })

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("phoenix_tracing_initialized", endpoint=endpoint,
                    service=service_name, project=project)
        _instrument_openai()
        return provider
    except Exception:  # noqa: BLE001
        logger.warning("phoenix_tracing_init_failed", exc_info=True)
        return None


# Initialise once per process
_provider = _init_opentelemetry()

_TRACER_NAME = "llm-entity-extraction"


def _tracer() -> Any | None:
    """Return the module's OTel tracer, or None when tracing is disabled."""
    if _provider is None:
        return None
    try:
        from opentelemetry import trace

        return trace.get_tracer(_TRACER_NAME)
    except Exception:  # noqa: BLE001
        return None


def _set_attributes(span: Any, attributes: dict[str, Any]) -> None:
    """Set span attributes from a dict, skipping unusable values."""
    for key, value in attributes.items():
        if value is None:
            continue
        try:
            span.set_attribute(key, value)
        except Exception:  # noqa: BLE001 - one bad attribute must not kill the span
            logger.warning("phoenix_attribute_failed", key=key, exc_info=True)


def _annotation_attributes(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten collected scores into OpenInference ``annotations.*`` attributes.

    Phoenix ingests feedback attached via the flattened ``annotations``
    semantic convention (``annotations.{index}.{field}`` — name/score/label/
    annotator_kind/explanation) and renders them as span annotations, so each
    scored entry is filterable as correct/incorrect in the Phoenix UI.
    """
    attributes: dict[str, Any] = {}
    for index, annotation in enumerate(annotations):
        prefix = f"annotations.{index}"
        for key, value in annotation.items():
            if value is None:
                continue
            attributes[f"{prefix}.{key}"] = value
    return attributes


@dataclass
class TraceHandle:
    """Document-level span handle (name = the tracer's trace_name)."""

    trace_id: str
    disabled: bool = True
    handler: Any | None = None
    _span: Any = None
    _annotations: list[dict[str, Any]] = field(default_factory=list)

    def set_output(self, output: Any) -> None:
        """Record the document's composite output as a span event."""
        if self.disabled or self._span is None:
            return
        try:
            self._span.add_event(
                "output",
                {"payload": json.dumps(output, default=str)[:200_000]},
            )
        except Exception:  # noqa: BLE001
            logger.warning("phoenix_output_event_failed", trace_id=self.trace_id)

    def score(self, name: str, value: float, comment: str = "",
              observation_id: str | None = None) -> None:
        """Record one deterministic logic score as a span event + annotation."""
        if self.disabled or self._span is None:
            return
        try:
            self._span.add_event("score", {
                "name": name, "value": str(value), "comment": comment,
            })
        except Exception:  # noqa: BLE001
            logger.warning("phoenix_score_event_failed", trace_id=self.trace_id, name=name)
        self._annotations.append({
            "name": name,
            "score": float(value),
            "label": "correct" if value >= 0.5 else "incorrect",
            "annotator_kind": "CODE",
            "explanation": comment,
        })


@dataclass
class AgentHandle:
    """Agent-level span handle (nested under the document span)."""

    trace_id: str
    observation_id: str = ""
    disabled: bool = True
    handler: Any | None = None
    _span: Any = None
    _annotations: list[dict[str, Any]] = field(default_factory=list)

    def set_output(self, output: Any) -> None:
        """Record the agent's result as a span event."""
        if self.disabled or self._span is None:
            return
        try:
            self._span.add_event(
                "output",
                {"payload": json.dumps(output, default=str)[:200_000]},
            )
        except Exception:  # noqa: BLE001
            logger.warning("phoenix_agent_output_failed", trace_id=self.trace_id)

    def score(self, name: str, value: float, comment: str = "") -> None:
        """Record one deterministic logic score as a span event + annotation."""
        if self.disabled or self._span is None:
            return
        try:
            self._span.add_event("score", {
                "name": name, "value": str(value), "comment": comment,
            })
        except Exception:  # noqa: BLE001
            logger.warning("phoenix_agent_score_failed",
                           trace_id=self.trace_id, name=name)
        self._annotations.append({
            "name": name,
            "score": float(value),
            "label": "correct" if value >= 0.5 else "incorrect",
            "annotator_kind": "CODE",
            "explanation": comment,
        })


class PhoenixTracer:
    """Phoenix tracer mirroring the LangfuseTracer API surface.

    ``trace_document`` opens a ROOT span per document; ``agent_observation``
    opens a child span under it. Outputs and scores are recorded as span
    events; the OpenAI SDK instrumentation adds nested LLM-call spans.
    """

    def __init__(self, session_id: str = "", tags: list[str] | None = None,
                 trace_name: str = "evaluation"):
        self.session_id = session_id or os.environ.get("PHOENIX_SESSION", "default")
        self.tags = tags or []
        self.trace_name = trace_name
        self.disabled = not phoenix_enabled() or _provider is None

    def flush(self) -> None:
        """Force-export buffered spans without disabling the provider."""
        if self.disabled or _provider is None:
            return
        try:
            _provider.force_flush()
        except Exception:  # noqa: BLE001
            logger.warning("phoenix_flush_failed")

    def shutdown(self) -> None:
        """Final flush before the process exits (provider stays reusable)."""
        self.flush()

    @contextmanager
    def trace_document(self, filename: str, expected: Any = None,
                       metadata: dict | None = None) -> Iterator[TraceHandle]:
        """Open a document-level ROOT span; yields its :class:`TraceHandle`.

        The span carries session id, tags, filename, expected value and the
        caller's metadata as attributes (question, category, prompt version,
        model, ...), so Phoenix holds the same per-document data shape as the
        Langfuse mirror.
        """
        trace_id = f"phoenix-{self.session_id}-{filename}"
        handle = TraceHandle(trace_id=trace_id, disabled=True)
        otel_tracer = _tracer()
        if self.disabled or otel_tracer is None:
            yield handle
            return
        attributes: dict[str, Any] = {
            "session_id": self.session_id,
            # OpenInference session convention — Phoenix groups spans into a
            # session per value, so every run (one session_id per experiment)
            # is inspectable as its OWN session in the Phoenix UI.
            "session.id": self.session_id,
            "tags": ",".join(self.tags),
            "filename": filename,
            "expected": expected,
        }
        for key, value in (metadata or {}).items():
            attributes[key] = value
        with otel_tracer.start_as_current_span(self.trace_name,
                                               attributes=attributes) as span:
            handle = TraceHandle(trace_id=trace_id, disabled=False, _span=span)
            try:
                yield handle
            finally:
                _set_attributes(span, _annotation_attributes(handle._annotations))
                # The start_as_current_span context manager ends the span.
                pass

    @contextmanager
    def agent_observation(self, agent_name: str,
                          metadata: dict | None = None) -> Iterator[AgentHandle]:
        """Open an agent-level span NESTED under the current document span.

        Must be called INSIDE a :meth:`trace_document` block — the span is a
        child of the current span via OTel context propagation, and the
        instrumented OpenAI SDK call nests under it in turn.
        """
        handle = AgentHandle(trace_id="", disabled=True)
        otel_tracer = _tracer()
        if self.disabled or otel_tracer is None:
            yield handle
            return
        attributes: dict[str, Any] = {"agent": agent_name}
        for key, value in (metadata or {}).items():
            attributes[key] = value
        with otel_tracer.start_as_current_span(agent_name,
                                               attributes=attributes) as span:
            handle = AgentHandle(trace_id="", observation_id=getattr(span, "context", None),
                                 disabled=False, _span=span)
            try:
                yield handle
            finally:
                _set_attributes(span, _annotation_attributes(handle._annotations))
                # The start_as_current_span context manager ends the span.
                pass


def init_phoenix_tracing(service_name: str | None = None, endpoint: str | None = None) -> None:
    """Explicit initialisation helper for scripts that want to control startup.

    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _provider
    if _provider is not None:
        return
    if service_name:
        os.environ["PHOENIX_SERVICE_NAME"] = service_name
    if endpoint:
        os.environ["PHOENIX_ENDPOINT"] = endpoint
    # Re-initialise
    _provider = _init_opentelemetry()


def register_phoenix_experiment(*, experiment_name: str, model: str,
                                prompt_version: str, dataset_name: str,
                                pairs: list[dict[str, Any]],
                                results: list[dict[str, Any]],
                                timestamp: str) -> bool:
    """Best-effort: register ONE run as an experiment in the Phoenix project.

    Creates (idempotently) the project + dataset in Phoenix and logs the run:
    one experiment record named after the experiment (its own individually
    inspectable run), one run per (contract, question) pair with the predicted
    output, and CODE evaluations for the deterministic scores (contracteval
    correct/incorrect + token-set jaccard). Best-effort by design —
    observability must never break a run, so any failure only logs a warning.

    ``pairs`` must carry ``id``/``context``/``question``/``category``/
    ``label_spans``; ``results`` must carry ``id``/``predicted``/
    ``classification``/``jaccard``.
    """
    try:
        from phoenix.client import Client

        client = Client(base_url=_phoenix_server_base())
        project = phoenix_project_name()
        projects = client.projects.list(name_contains=project)
        if not any(p.name == project for p in projects):
            client.projects.create(
                name=project,
                description="llm-entity-extraction eval iterations (llm-dojo)",
            )

        datasets = client.datasets.list()
        dataset = next((d for d in datasets if d.name == dataset_name), None)
        if dataset is None:
            dataset = client.datasets.create_dataset(
                name=dataset_name,
                dataset_description=(
                    f"Directly-mirrored ContractEval surface "
                    f"({len(pairs)} (contract, question) pairs), "
                    f"faithful full-context inputs"
                ),
                examples=[
                    {
                        "input": {"context": p["context"], "question": p["question"],
                                  "category": p["category"]},
                        "output": {"label_spans": p["label_spans"]},
                        "metadata": {"id": p["id"], "category": p["category"]},
                    }
                    for p in pairs
                ],
            )
        examples = getattr(dataset, "examples", None)
        if not examples:
            refreshed = client.datasets.get_dataset(dataset.id)
            examples = getattr(refreshed, "examples", []) or []
        example_ids = {
            dict(ex).get("metadata", {}).get("id"): dict(ex)["id"]
            for ex in examples if dict(ex).get("metadata", {}).get("id")
        }

        experiments = client.experiments.list()
        experiment = next((e for e in experiments if e.name == experiment_name), None)
        if experiment is None:
            experiment = client.experiments.create(
                dataset_id=dataset.id,
                experiment_name=experiment_name,
                experiment_metadata={
                    "model": model, "prompt_version": prompt_version,
                    "task": "contracteval",
                },
            )

        start = end = timestamp
        logged = 0
        for row in results:
            example_id = example_ids.get(row["id"])
            if example_id is None:
                continue
            run = client.experiments.log_run(
                experiment_id=experiment.id, dataset_example_id=example_id,
                output=row["predicted"], start_time=start, end_time=end,
            )
            cls = row["classification"]
            client.experiments.log_evaluation(
                experiment_run_id=run.id, name="contracteval",
                annotator_kind="CODE",
                score=1.0 if cls in ("TP", "TN") else 0.0,
                label="correct" if cls in ("TP", "TN") else "incorrect",
                explanation=f"{cls} (ContractEval verbatim rubric)",
            )
            client.experiments.log_evaluation(
                experiment_run_id=run.id, name="jaccard", annotator_kind="CODE",
                score=float(row["jaccard"]),
                label="correct" if row["jaccard"] >= 0.5 else "incorrect",
                explanation="token-set Jaccard over the positive pair",
            )
            logged += 1
        logger.info("phoenix_experiment_registered",
                    experiment=experiment_name, runs=logged, project=project)
        return True
    except Exception:  # noqa: BLE001 - observability must never break a run
        logger.warning("phoenix_experiment_register_failed", exc_info=True)
        return False