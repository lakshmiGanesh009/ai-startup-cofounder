"""Tests for following a request through the API: its ID on the response and
on every log line and event, worker threads included; the logs as text or JSON;
the access log; the Prometheus metrics; and the unexpected errors and closed
connections the monitor records."""

import asyncio
import json
import logging
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

import main
import search
from monitor import monitor
from observability import TEXT_FORMAT, JsonFormatter, RequestContextMiddleware, configure_logging

client = TestClient(main.app)


def test_every_response_names_its_request():
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert len(first) == 16 and first != second

    # One a proxy sent is kept; one that could not be quoted safely is replaced.
    assert client.get("/health", headers={"X-Request-ID": "proxy-abc.123"}).headers["X-Request-ID"] == "proxy-abc.123"
    for unusable in ("short", "has spaces in it", "x" * 65):
        assert client.get("/health", headers={"X-Request-ID": unusable}).headers["X-Request-ID"] != unusable


def test_a_browser_on_another_origin_can_read_the_request_id():
    response = client.get("/health", headers={"Origin": main.CORS_ORIGINS[0]})

    assert response.headers["access-control-expose-headers"] == "X-Request-ID"


def test_the_access_log_names_the_route_status_and_time(caplog):
    with caplog.at_level(logging.DEBUG, logger="access"):
        missing = client.get("/reports/no-such-session")
        client.get("/monitoring")
        client.get("/nowhere")

    lines = [record for record in caplog.records if record.name == "access"]
    # Polled routes are logged at DEBUG; a path no route matched is "unmatched".
    assert [(record.levelno, record.route, record.status) for record in lines] == [
        (logging.INFO, "/reports/{session_id}", 404),
        (logging.DEBUG, "/monitoring", 200),
        (logging.INFO, "unmatched", 404),
    ]
    assert lines[0].getMessage().startswith("GET /reports/no-such-session 404 in ")
    assert lines[0].request_id == missing.headers["X-Request-ID"]
    line = json.loads(JsonFormatter().format(lines[0]))
    assert {key: line[key] for key in ("method", "route", "path", "status")} == {
        "method": "GET", "route": "/reports/{session_id}", "path": "/reports/no-such-session", "status": 404,
    }
    assert isinstance(line["duration_ms"], int)


def test_log_lines_name_the_session_once_it_is_known(fake_llm, caplog):
    with caplog.at_level(logging.INFO, logger="access"):
        result = client.post("/evaluate", json={"prompt": "An idea."}).json()

    access = next(record for record in caplog.records if record.name == "access")
    assert access.session_id == result["session_id"][:8]


def test_log_lines_from_worker_threads_name_their_request(fake_llm, monkeypatch):
    # Tavily answers every search with a 500, so each search's thread logs a warning.
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(search, "_transport", httpx.MockTransport(lambda request: httpx.Response(500, json={})))

    response = client.post("/brief/prepare", json={"prompt": "An idea."})

    assert response.status_code == 200
    warnings = [event for event in monitor.snapshot().events if event.kind == "warning"]
    assert len(warnings) == 2  # one a search
    assert {event.request for event in warnings} == {response.headers["X-Request-ID"]}


def test_logs_are_text_or_json_lines_that_name_the_request():
    record = logging.LogRecord("main", logging.ERROR, __file__, 1, "Failed for %s", ("a reason",), None)
    record.request_id, record.session_id = "abc123abc123abcd", "d8f7066e"
    try:
        raise ValueError("boom")
    except ValueError:
        record.exc_info = sys.exc_info()

    line = json.loads(JsonFormatter().format(record))

    assert (line["level"], line["logger"], line["message"]) == ("error", "main", "Failed for a reason")
    assert (line["request_id"], line["session_id"]) == ("abc123abc123abcd", "d8f7066e")
    assert "ValueError: boom" in line["exception"] and line["time"].endswith("+00:00")
    assert "ERROR main [abc123abc123abcd d8f7066e] Failed for a reason" in logging.Formatter(TEXT_FORMAT).format(record)
    # Outside a request the fields are empty rather than "-".
    outside = logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1, "Started.", None, None)
    outside.request_id = outside.session_id = "-"
    assert json.loads(JsonFormatter().format(outside))["request_id"] is None


def test_every_log_line_goes_through_one_handler():
    try:
        configure_logging(logging.INFO, "json")
        configure_logging(logging.INFO, "json")

        ours = [handler for handler in logging.getLogger().handlers if handler.get_name() == "cofounder"]
        assert len(ours) == 1 and isinstance(ours[0].formatter, JsonFormatter)
        server = logging.getLogger("uvicorn.error")
        assert server.propagate and not server.handlers
        assert not logging.getLogger("uvicorn.access").propagate  # the access log replaces it
    finally:
        configure_logging(logging.INFO, "text")


def test_an_unexpected_error_answers_500_with_the_request_id(fake_llm, monkeypatch, caplog):
    def broken(session_id, results):
        raise RuntimeError("A bug")

    monkeypatch.setattr(main.store, "record", broken)

    response = client.post("/evaluate", json={"prompt": "An idea."})

    rid = response.headers["X-Request-ID"]
    assert response.status_code == 500
    assert response.json() == {"detail": "The server failed unexpectedly.", "request_id": rid}
    seen = monitor.snapshot()
    assert seen.runs[0].error == "The evaluation failed unexpectedly." and seen.running == 0
    error = next(event for event in seen.events if event.kind == "error")
    assert (error.message, error.request) == ("Unhandled error answering POST /evaluate", rid)
    assert (seen.totals.server_errors, seen.health.status) == (1, "errors")
    assert any(record.exc_info and record.request_id == rid for record in caplog.records)


def test_a_stream_the_browser_leaves_is_recorded(fake_llm):
    async def leave():
        response = await main.evaluate_stream(main.EvaluateRequest(prompt="An idea."))
        events = response.body_iterator
        assert (await anext(events)).startswith("event: start")
        await events.aclose()

    asyncio.run(leave())

    seen = monitor.snapshot()
    assert seen.runs[0].error == "The connection closed before the evaluation finished."
    assert (seen.totals.failures, seen.running) == (1, 0)


def test_the_metrics_are_ready_for_prometheus(fake_llm):
    with client.stream("POST", "/evaluate/stream", json={"prompt": "An idea."}) as response:
        response.read()

    scraped = client.get("/metrics")

    assert scraped.headers["content-type"].startswith("text/plain; version=0.0.4")
    for line in (
        'cofounder_evaluations_total{outcome="finished"} 1.0',
        "cofounder_evaluations_in_progress 0.0",
        'cofounder_node_duration_seconds_count{node="plan"} 1.0',
        'cofounder_reports_reviewed_total{verdict="approved"} 4.0',
        'cofounder_http_requests_total{method="POST",route="/evaluate/stream",status="200"} 1.0',
    ):
        assert line in scraped.text, line
    assert "_created" not in scraped.text
    # OpenMetrics for a scraper that asks for it; and no place in the API's docs.
    asked = client.get("/metrics", headers={"Accept": "application/openmetrics-text; version=1.0.0"})
    assert asked.headers["content-type"].startswith("application/openmetrics-text")
    assert asked.text.rstrip().endswith("# EOF")
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def _through_middleware(app, kind="http"):
    """Run `app` behind the middleware for one GET /x: what was sent, and what it reported."""
    sent, finished = [], []
    middleware = RequestContextMiddleware(app, on_finish=lambda *request: finished.append(request))

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware({"type": kind, "method": "GET", "path": "/x", "headers": []}, receive, send))
    return sent, finished


def test_the_middleware_lets_other_traffic_by_and_tells_a_disconnect_from_a_failure():
    async def lifespan(scope, receive, send):
        await send({"type": "lifespan.startup.complete"})

    assert _through_middleware(lifespan, "lifespan") == ([{"type": "lifespan.startup.complete"}], [])

    async def left(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise ClientDisconnect()

    sent, finished = _through_middleware(left)
    assert len(sent) == 1 and finished[0][:3] == ("GET", "unmatched", 499)

    async def broke_midway(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("A bug")

    with pytest.raises(RuntimeError):  # too late for a 500: the server closes the connection
        _through_middleware(broke_midway)
