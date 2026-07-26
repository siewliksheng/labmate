"""M1: every tool call gets an OTel span.

If LANGFUSE_PUBLIC_KEY/SECRET_KEY are set, spans export to Langfuse over
OTLP. Otherwise they're written locally to var/spans.jsonl -- tracing is
visibly working from the start, without requiring a Langfuse account to
develop against. Swapping in real credentials later changes nothing at the
call site.
"""

import base64
import json
import os
import time
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExportResult,
)
from opentelemetry.trace import Status, StatusCode

from labmate.paths import VAR_DIR

_provider = None


class _JsonlSpanExporter:
    """Fallback exporter used when no Langfuse credentials are configured."""

    def __init__(self, path):
        self._path = path

    def export(self, spans):
        self._path.parent.mkdir(exist_ok=True, parents=True)
        with self._path.open("a", encoding="utf-8") as f:
            for span in spans:
                f.write(
                    json.dumps(
                        {
                            "name": span.name,
                            "duration_ms": (span.end_time - span.start_time) / 1e6,
                            "attributes": dict(span.attributes or {}),
                            "status": span.status.status_code.name,
                        }
                    )
                    + "\n"
                )
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


def _init_provider():
    global _provider
    if _provider is not None:
        return _provider

    provider = TracerProvider(resource=Resource.create({"service.name": "labmate"}))

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if public_key and secret_key:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        exporter = OTLPSpanExporter(
            endpoint=f"{host}/api/public/otel/v1/traces",
            headers={"Authorization": f"Basic {auth}"},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(SimpleSpanProcessor(_JsonlSpanExporter(VAR_DIR / "spans.jsonl")))

    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


@contextmanager
def traced_tool_call(tool_name: str, **attributes):
    _init_provider()
    tracer = trace.get_tracer("labmate")
    start = time.perf_counter()
    with tracer.start_as_current_span(f"tool:{tool_name}") as span:
        for key, value in attributes.items():
            span.set_attribute(key, str(value))
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error", str(exc))
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            span.set_attribute("duration_ms", (time.perf_counter() - start) * 1000)
