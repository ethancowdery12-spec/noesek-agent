"""The real OpenTelemetry SDK backs the telemetry layer."""
from noesek.core.otel_real import RealTracer, create_provider


def test_real_sdk_ids_and_redaction():
    t = RealTracer()
    s = t.start_span("turn", attributes={"user": "u1", "api_key": "sk-secret"})
    s.event("tool_call", {"token": "abc"})
    s.set_attribute("password", "hunter2")
    s.end()
    assert len(s.trace_id) == 32 and len(s.span_id) == 16
    finished = t.finished_spans()
    assert len(finished) == 1
    span = finished[0]
    blob = str(span.attributes) + str(span.events)
    assert "sk-secret" not in blob and "abc" not in blob and "hunter2" not in blob
    assert span.status.status_code.name == "OK"

def test_endpoint_requires_https():
    import pytest
    with pytest.raises(ValueError):
        create_provider("http://collector:4318/v1/traces")

def test_provider_name_and_error_status():
    t = RealTracer(name="noesek-test")
    s = t.start_span("job")
    s.end("ERROR")
    span = t.finished_spans()[0]
    assert span.instrumentation_scope.name == "noesek-test"
    assert span.status.status_code.name == "ERROR"
