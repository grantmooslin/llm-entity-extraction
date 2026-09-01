"""Network-free unit tests for the real Phoenix span emission.

``src/phoenix_tracing.py`` initialises a real OpenTelemetry provider at import;
these tests monkeypatch the module's provider + tracer with a fake in-memory
tracer and assert the span shape (root document span, nested agent span,
output + score events) plus the disabled no-op behavior. No network, no OTel
exporter.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest

import src.phoenix_tracing as pt


@dataclass
class FakeSpan:
    name: str
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    parent: "FakeSpan | None" = None
    ended: bool = False

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def add_event(self, name, attrs=None):
        self.events.append({"event": name, "attributes": dict(attrs or {})})

    def end(self):
        self.ended = True

    @property
    def context(self):
        return "fake-ctx"


class FakeTracer:
    """In-memory OTel tracer with an open-span stack for nesting."""

    def __init__(self):
        self.spans: list[FakeSpan] = []
        self._open: list[FakeSpan] = []

    @contextmanager
    def start_as_current_span(self, name, attributes=None):
        parent = self._open[-1] if self._open else None
        span = FakeSpan(name=name, attributes=dict(attributes or {}), parent=parent)
        self.spans.append(span)
        self._open.append(span)
        try:
            yield span
        finally:
            self._open.pop()
            span.end()


@pytest.fixture
def fake_otel(monkeypatch):
    """Replace the module's provider + tracer with the in-memory fake."""
    tracer = FakeTracer()
    monkeypatch.setattr(pt, "_provider", object())
    monkeypatch.setattr(pt, "_tracer", lambda: tracer)
    monkeypatch.setenv("PHOENIX_TRACING", "enabled")
    return tracer


def test_trace_document_opens_root_span(fake_otel):
    tracer = pt.PhoenixTracer(session_id="exp_ce", tags=["contracteval:contracteval_v0", "qwen"],
                              trace_name="contracteval")
    assert tracer.disabled is False
    with tracer.trace_document(
        "acme__Anti-Assignment", expected="Anti-Assignment",
        metadata={"dataset": "contracteval-cuad-test", "prompt_version": "contracteval_v0",
                  "model": "qwen/qwen3.7-flash", "category": "Anti-Assignment"},
    ):
        pass
    assert len(fake_otel.spans) == 1
    span = fake_otel.spans[0]
    assert span.name == "contracteval"
    assert span.parent is None
    assert span.attributes["session_id"] == "exp_ce"
    assert span.attributes["tags"] == "contracteval:contracteval_v0,qwen"
    assert span.attributes["filename"] == "acme__Anti-Assignment"
    assert span.attributes["expected"] == "Anti-Assignment"
    assert span.attributes["prompt_version"] == "contracteval_v0"
    assert span.attributes["model"] == "qwen/qwen3.7-flash"
    assert span.ended is True


def test_agent_observation_nests_under_document_span(fake_otel):
    tracer = pt.PhoenixTracer(session_id="exp_ce", tags=["t"], trace_name="contracteval")
    with tracer.trace_document("doc", "Anti-Assignment", {"category": "Anti-Assignment"}):
        with tracer.agent_observation("contracteval", {"model": "qwen/qwen3.7-flash"}):
            pass
    assert len(fake_otel.spans) == 2
    root, agent = fake_otel.spans
    assert agent.name == "contracteval"
    assert agent.parent is root
    assert agent.attributes["agent"] == "contracteval"
    assert agent.attributes["model"] == "qwen/qwen3.7-flash"


def test_output_and_score_events_recorded(fake_otel):
    tracer = pt.PhoenixTracer(session_id="exp_ce", tags=["t"], trace_name="contracteval")
    with tracer.trace_document("doc", "Anti-Assignment", {"category": "Anti-Assignment"}) as trace_handle:
        with tracer.agent_observation("contracteval", {"model": "m"}) as agent_handle:
            assert trace_handle.disabled is False
            assert agent_handle.handler is None
            agent_handle.set_output({"category": "Anti-Assignment", "predicted": "X", "classification": "TP"})
            agent_handle.score("classification", 1.0, comment="TP (ContractEval verbatim rubric)")
            agent_handle.score("jaccard", 0.5, comment="token-set Jaccard")
            trace_handle.set_output({"predicted": "X", "classification": "TP"})
    root, agent = fake_otel.spans
    outputs = [e for e in agent.events if e["event"] == "output"]
    scores = [e for e in agent.events if e["event"] == "score"]
    assert len(outputs) == 1
    assert '"classification": "TP"' in outputs[0]["attributes"]["payload"]
    assert [e["attributes"]["name"] for e in scores] == ["classification", "jaccard"]
    assert scores[0]["attributes"]["value"] == "1.0"
    assert scores[0]["attributes"]["comment"] == "TP (ContractEval verbatim rubric)"
    assert any(e["event"] == "output" for e in root.events)


def test_scores_emitted_as_openinference_annotations(fake_otel):
    """Scores become flattened annotations.* attributes on the spans, so
    Phoenix renders each entry as a correct/incorrect CODE annotation."""
    tracer = pt.PhoenixTracer(session_id="exp_ce", tags=["t"], trace_name="contracteval")
    with tracer.trace_document("doc", "Anti-Assignment", {"category": "Anti-Assignment"}) as trace_handle:
        with tracer.agent_observation("contracteval", {"model": "m"}) as agent_handle:
            agent_handle.score("classification", 1.0, comment="TP (ContractEval verbatim rubric)")
            agent_handle.score("jaccard", 0.42, comment="token-set Jaccard")
            trace_handle.score("classification", 0.0, comment="FN")
    root, agent = fake_otel.spans
    assert agent.attributes["annotations.0.name"] == "classification"
    assert agent.attributes["annotations.0.score"] == 1.0
    assert agent.attributes["annotations.0.label"] == "correct"
    assert agent.attributes["annotations.0.annotator_kind"] == "CODE"
    assert agent.attributes["annotations.0.explanation"] == "TP (ContractEval verbatim rubric)"
    assert agent.attributes["annotations.1.name"] == "jaccard"
    assert agent.attributes["annotations.1.label"] == "incorrect"
    assert root.attributes["annotations.0.name"] == "classification"
    assert root.attributes["annotations.0.label"] == "incorrect"


def test_phoenix_endpoint_reachable_false_on_refused(monkeypatch):
    """A down Phoenix must not attach a BatchSpanProcessor (KANBAN-103)."""
    import urllib.error

    def boom(*_a, **_k):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert pt.phoenix_endpoint_reachable(timeout=0.05) is False


def test_phoenix_endpoint_reachable_true_on_200(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _Resp())
    assert pt.phoenix_endpoint_reachable(timeout=0.05) is True


def test_disabled_tracer_is_noop(fake_otel, monkeypatch):
    monkeypatch.setattr(pt, "phoenix_enabled", lambda: False)
    tracer = pt.PhoenixTracer(session_id="exp_ce", tags=["t"], trace_name="contracteval")
    assert tracer.disabled is True
    with tracer.trace_document("doc", "X", {"category": "X"}) as handle:
        assert handle.disabled is True
        handle.set_output({"predicted": "x"})
        handle.score("classification", 1.0)
        with tracer.agent_observation("agent", {}) as agent_handle:
            agent_handle.set_output({"predicted": "x"})
            agent_handle.score("jaccard", 0.0)
    assert fake_otel.spans == []