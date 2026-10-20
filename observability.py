"""What lets an operator follow a request through the API: an ID for every
request, on every log line written while it is handled and on its response;
the session it works on, once known; logs as text, or as JSON lines for a log
collector; and an access log line for each request, with its route, status and
time.

A request keeps the ID in its `X-Request-ID` header when it sends a usable one
(a proxy or another service may set it), else gets a new one. Both live in
context variables, so the worker threads that run the agents, which copy the
context, log them too.
"""

import json
import logging
import re
import sys
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Literal

from starlette.datastructures import MutableHeaders
from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_HEADER = "X-Request-ID"
# Routes polled by probes, scrapers and the Monitor: their access lines are
# logged at DEBUG, and the Monitor's totals leave them out.
QUIET_ROUTES = frozenset({"/health", "/metrics", "/monitoring"})

_USABLE_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
_request: ContextVar[str | None] = ContextVar("request_id", default=None)
_session: ContextVar[str | None] = ContextVar("session_id", default=None)

logger = logging.getLogger(__name__)
access_log = logging.getLogger("access")


def request_id() -> str | None:
    """The ID of the request being handled, if any."""
    return _request.get()


def bind_session(session_id: str) -> None:
    """Name the session the current request works on, for its log lines."""
    _session.set(session_id)


_make_record = logging.getLogRecordFactory()


def _record_in_context(*args, **kwargs) -> logging.LogRecord:
    """A log record that names its request and session, "-" outside a request.
    Made where the line is logged, so every handler sees them."""
    record = _make_record(*args, **kwargs)
    record.request_id = _request.get() or "-"
    session = _session.get()
    record.session_id = session[:8] if session else "-"
    return record


TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s %(session_id)s] %(message)s"


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for a log collector."""

    # What an access line adds, from its `extra`.
    ACCESS_FIELDS = ("method", "route", "path", "status", "duration_ms")

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _present(getattr(record, "request_id", None)),
            "session_id": _present(getattr(record, "session_id", None)),
        }
        for field in self.ACCESS_FIELDS:
            if hasattr(record, field):
                line[field] = getattr(record, field)
        if record.exc_info:
            line["exception"] = self.formatException(record.exc_info)
        return json.dumps(line, ensure_ascii=False, default=str)


def _present(value: str | None) -> str | None:
    return None if value in (None, "-") else value


def configure_logging(level: int, style: Literal["text", "json"]) -> None:
    """Send every log line, the server's own included, through one handler on
    the root logger, as text or JSON, with the request's ID and session. The
    access log replaces uvicorn's, which knows neither."""
    logging.setLogRecordFactory(_record_in_context)
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name("cofounder")
    handler.setFormatter(JsonFormatter() if style == "json" else logging.Formatter(TEXT_FORMAT))
    root = logging.getLogger()
    for old in [each for each in root.handlers if each.get_name() == "cofounder"]:
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        server = logging.getLogger(name)
        server.handlers.clear()
        server.propagate = True
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = False


class RequestContextMiddleware:
    """Gives each HTTP request its ID, logs an access line when it ends, and
    reports its route, status and time to `on_finish` (the monitor). An error
    nothing else handled becomes a JSON 500 that carries the request's ID, so
    the person who saw it can name it, and is logged with its traceback."""

    def __init__(self, app: ASGIApp, on_finish: Callable[[str, str, int, float], None] | None = None):
        self.app = app
        self.on_finish = on_finish

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sent = dict(scope["headers"]).get(REQUEST_HEADER.lower().encode(), b"").decode("latin-1")
        rid = sent if _USABLE_ID.fullmatch(sent) else uuid.uuid4().hex[:16]
        request_token = _request.set(rid)
        session_token = _session.set(None)
        started = time.perf_counter()
        status = 500
        responded = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, responded
            if message["type"] == "http.response.start":
                status = message["status"]
                responded = True
                MutableHeaders(scope=message).append(REQUEST_HEADER, rid)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except ClientDisconnect:
            # The browser went away mid-response: nothing to answer, and not a
            # server error. 499 is the status proxies log for it.
            status = 499
        except Exception:
            logger.exception("Unhandled error answering %s %s", scope["method"], scope["path"])
            if responded:
                raise
            status = 500
            body = json.dumps({"detail": "The server failed unexpectedly.", "request_id": rid}).encode()
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (REQUEST_HEADER.lower().encode(), rid.encode()),
                ],
            })
            await send({"type": "http.response.body", "body": body})
        finally:
            seconds = time.perf_counter() - started
            # The route's template, such as /reports/{session_id}, keeps the
            # metrics' labels few; a path no route matched is "unmatched".
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            duration_ms = round(seconds * 1000)
            access_log.log(
                logging.DEBUG if route in QUIET_ROUTES else logging.INFO,
                "%s %s %d in %d ms", scope["method"], scope["path"], status, duration_ms,
                extra={"method": scope["method"], "route": route, "path": scope["path"],
                       "status": status, "duration_ms": duration_ms},
            )
            if self.on_finish:
                self.on_finish(scope["method"], route, status, seconds)
            _session.reset(session_token)
            _request.reset(request_token)
