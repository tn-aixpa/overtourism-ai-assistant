import json
import logging
import logging.config
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.trace import TracerProvider

with open(
    os.environ.get("LOG_CONFIG_FILE", "/etc/app-logging/logging.json"), encoding="utf-8"
) as f:
    logging.config.dictConfig(json.loads(os.path.expandvars(f.read())))


application_log = logging.getLogger(__name__)
security_audit_log = logging.getLogger("audit.security")
ai_audit_log = logging.getLogger("audit.ai")


def _add_trace_fields(span, record) -> None:
    ctx = span.get_span_context()
    setattr(record, "trace.id", format(ctx.trace_id, "032x"))
    setattr(record, "span.id", format(ctx.span_id, "016x"))


def setup_tracing(app: FastAPI) -> None:
    trace.set_tracer_provider(TracerProvider())
    LoggingInstrumentor().instrument(
        set_logging_format=False, log_hook=_add_trace_fields
    )
    HTTPXClientInstrumentor().instrument()  # Anthropic SDK runs on httpx
    RequestsInstrumentor().instrument()  # calls to the other backends
    FastAPIInstrumentor.instrument_app(app)
