"""Real OpenTelemetry SDK backend for Noesek's telemetry layer.

Replaces the interface-shaped otel_sdk.Tracer with the pinned
opentelemetry-sdk: real W3C trace/span IDs, real span processors, and a real
export pipeline (in-memory for tests and local use, OTLP/HTTP when an endpoint
is configured). Noesek's redaction policy is applied before any attribute
reaches the SDK, so secrets never enter the export path.
"""
from __future__ import annotations

from typing import Any

from opentelemetry import trace as ot_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from .telemetry import redact


def create_provider(endpoint: str | None = None, headers: dict[str, str] | None = None):
    """Build a TracerProvider. With no endpoint, spans land in an in-memory
    exporter (returned alongside). With an endpoint, a real OTLP/HTTP exporter
    is attached; HTTPS is required, matching Noesek's exporter policy."""
    provider = TracerProvider()
    memory = None
    if endpoint:
        if not endpoint.startswith("https://"):
            raise ValueError("OTLP endpoint must use HTTPS")
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers or {})))
    else:
        memory = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(memory))
    return provider, memory


class RealTracer:
    """Drop-in tracer with the same surface as otel_sdk.Tracer, backed by the real SDK."""

    def __init__(self, provider: TracerProvider | None = None, name: str = "noesek"):
        if provider is None:
            provider, self.memory = create_provider()
        else:
            self.memory = None
        self.provider = provider
        self._tracer = provider.get_tracer(name)

    def start_span(self, name: str, attributes: dict | None = None, **kw) -> "RealSpan":
        span = self._tracer.start_span(name, attributes=dict(redact(attributes or {})))
        return RealSpan(span)

    def finished_spans(self) -> list:
        if self.memory is None:
            raise RuntimeError("no in-memory exporter attached (endpoint-configured provider)")
        return list(self.memory.get_finished_spans())


class RealSpan:
    """SDK-backed span with Noesek's redaction on every attribute write."""

    def __init__(self, span: ot_trace.Span):
        self._span = span

    @property
    def name(self) -> str:
        return self._span.name

    @property
    def trace_id(self) -> str:
        return ot_trace.format_trace_id(self._span.get_span_context().trace_id)

    @property
    def span_id(self) -> str:
        return ot_trace.format_span_id(self._span.get_span_context().span_id)

    def event(self, name: str, attributes: dict | None = None) -> None:
        self._span.add_event(name, attributes=dict(redact(attributes or {})))

    def set_attribute(self, key: str, value: Any) -> None:
        self._span.set_attribute(key, dict(redact({key: value}))[key])

    def end(self, status: str = "OK") -> None:
        code = ot_trace.StatusCode.OK if status == "OK" else (
            ot_trace.StatusCode.ERROR if status == "ERROR" else ot_trace.StatusCode.UNSET)
        self._span.set_status(ot_trace.Status(code))
        self._span.end()
