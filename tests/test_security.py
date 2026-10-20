"""Tests for who may call the API and how much (security.py): the key, the size
limit, the per-caller rates, the cap on runs at once, the limits on what a
request may hold, and keeping the brief out of the logs."""

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

import main
import search
from monitor import monitor
from security import RateLimiter, RunSlots, check_context

client = TestClient(main.app)
KEY = "s3cret-key-for-tests"


@pytest.fixture
def guard(monkeypatch):
    """The API's guard, put back after the test."""
    for name in ("api_key", "max_bytes", "requests", "runs_rate", "slots"):
        monkeypatch.setattr(main.guard, name, getattr(main.guard, name))
    return main.guard


def test_a_rate_limit_slides_and_says_how_long_to_wait():
    now = [0.0]
    limit = RateLimiter(2, 60, clock=lambda: now[0])
    assert (limit.take("a"), limit.take("a"), limit.take("b")) == (0.0, 0.0, 0.0)
    assert limit.take("a") == 60.0
    now[0] = 30.0
    assert limit.take("a") == 30.0  # the first event leaves the window at 60 s
    now[0] = 60.0
    assert limit.take("a") == 0.0


def test_idle_callers_are_forgotten_once_there_are_many(monkeypatch):
    monkeypatch.setattr(RateLimiter, "MAX_KEYS", 2)
    now = [0.0]
    limit = RateLimiter(1, 60, clock=lambda: now[0])
    for caller in ("a", "b", "c"):
        limit.take(caller)
    now[0] = 61.0
    limit.take("d")
    assert set(limit._events) == {"d"}


def test_run_slots_fill_and_free():
    slots = RunSlots(1)
    assert slots.take() and not slots.take()
    slots.give_back()
    slots.give_back()  # never below none
    assert slots.running == 0 and slots.take()


def test_with_a_key_set_only_health_is_open(guard):
    guard.api_key = KEY

    assert client.get("/health").status_code == 200
    refused = client.get("/scenarios")
    wrong = client.get("/scenarios", headers={"Authorization": "Bearer nope"})
    bearer = client.get("/scenarios", headers={"Authorization": f"Bearer {KEY}"})
    header = client.get("/scenarios", headers={"X-API-Key": KEY})

    assert (refused.status_code, wrong.status_code, bearer.status_code, header.status_code) == (401, 401, 200, 200)
    assert refused.json() == {"detail": "This API needs its key: send it as Authorization: Bearer <key>."}
    assert refused.headers["www-authenticate"].startswith("Bearer") and refused.headers["x-request-id"]
    assert monitor.snapshot().totals.refused == 2
    assert monitor.metrics.registry.get_sample_value("cofounder_refused_requests_total", {"reason": "key"}) == 2


def test_a_body_over_the_limit_is_refused_whether_or_not_it_says_its_size(guard, fake_llm):
    guard.max_bytes = 100

    said = client.post("/brief/prepare", json={"prompt": "x" * 200})

    def chunks():
        yield b'{"prompt": "'
        yield b"x" * 200
        yield b'"}'

    unsaid = client.post("/brief/prepare", content=chunks(), headers={"Content-Type": "application/json"})

    assert (said.status_code, unsaid.status_code) == (413, 413)
    assert said.json()["detail"] == "The request is larger than the 100 bytes the API accepts."
    assert guard.slots.running == 0  # the run's slot came back


def test_each_caller_has_a_rate_of_requests_and_of_runs(guard, fake_llm):
    guard.requests = RateLimiter(3, 60)
    guard.runs_rate = RateLimiter(1, 3600)

    first_run = client.post("/brief/prepare", json={"prompt": "An idea."})
    second_run = client.post("/brief/prepare", json={"prompt": "An idea."})
    a_read = client.get("/templates")
    too_many = client.get("/templates")

    assert (first_run.status_code, second_run.status_code, a_read.status_code) == (200, 429, 200)
    assert second_run.json()["detail"].startswith("Too many evaluations, briefs and proposals from this address")
    assert int(second_run.headers["retry-after"]) > 3500
    assert too_many.status_code == 429 and too_many.json()["detail"].startswith("Too many requests")


def test_behind_the_proxy_each_browser_has_its_own_rate(guard):
    guard.api_key = KEY
    guard.requests = RateLimiter(1, 60)
    keyed = {"Authorization": f"Bearer {KEY}"}

    one = client.get("/templates", headers={**keyed, "X-Forwarded-For": "203.0.113.7"})
    other = client.get("/templates", headers={**keyed, "X-Forwarded-For": "198.51.100.2, 10.0.0.1"})
    again = client.get("/templates", headers={**keyed, "X-Forwarded-For": "203.0.113.7"})

    assert (one.status_code, other.status_code, again.status_code) == (200, 200, 429)


def test_without_the_key_a_caller_cannot_pose_as_another(guard):
    guard.requests = RateLimiter(1, 60)

    first = client.get("/templates", headers={"X-Forwarded-For": "203.0.113.7"})
    posing = client.get("/templates", headers={"X-Forwarded-For": "198.51.100.2"})

    assert (first.status_code, posing.status_code) == (200, 429)


def test_a_busy_team_turns_runs_away_without_counting_them(guard, fake_llm):
    guard.slots = RunSlots(1)
    guard.runs_rate = RateLimiter(1, 3600)
    assert guard.slots.take()  # a run already going

    busy = client.post("/evaluate", json={"prompt": "An idea."})
    guard.slots.give_back()
    after = client.post("/evaluate", json={"prompt": "An idea."})

    assert busy.status_code == 429 and busy.headers["retry-after"] == "30"
    assert busy.json()["detail"] == "The team is busy with 1 runs; try again in a minute."
    assert after.status_code == 200  # the busy refusal did not use the caller's one run
    assert guard.slots.running == 0
    assert monitor.metrics.registry.get_sample_value("cofounder_refused_requests_total", {"reason": "busy"}) == 1


def test_a_streamed_or_failed_run_gives_its_slot_back(guard, fake_llm, monkeypatch):
    guard.slots = RunSlots(1)
    with client.stream("POST", "/evaluate/stream", json={"prompt": "An idea."}) as response:
        response.read()
    assert guard.slots.running == 0

    def broken(session_id, results):
        raise RuntimeError("A bug")

    monkeypatch.setattr(main.store, "record", broken)
    assert client.post("/evaluate", json={"prompt": "An idea."}).status_code == 500
    assert guard.slots.running == 0


@pytest.mark.parametrize(("body", "message"), [
    ({"prompt": "x" * 8_001}, "String should have at most 8000 characters"),
    ({"prompt": ""}, "String should have at least 1 character"),
    ({"prompt": "An idea.", "session_id": "../../etc"}, "String should match pattern"),
    ({"prompt": "An idea.", "context": {"target_market": "x" * 4_001}}, "Target market is longer than 4,000 characters."),
    ({"prompt": "An idea.", "context": {"answers": [{"question": "Q?", "answer": "A."}] * 11}}, "At most 10 answers."),
    ({"prompt": "An idea.", "context": {"answers": [{"question": "Q?", "answer": "x" * 2_001}]}},
     "An answer is longer than 2,000 characters."),
    ({"prompt": "An idea.", "context": {"research": {"findings": [{"point": "A fact.", "sources": [1]}],
                                                     "sources": [{"title": "Page", "url": "javascript:alert(1)"}]}}},
     "A source's address must start with http:// or https://."),
    ({"prompt": "An idea.", "context": {"research": {"findings": [{"point": "x" * 1_001, "sources": [1]}],
                                                     "sources": [{"title": "Page", "url": "https://example.com"}]}}},
     "A fact is longer than 1,000 characters."),
    ({"prompt": "An idea.", "context": {"research": {"findings": [{"point": "A fact.", "sources": [1]}] * 21,
                                                     "sources": []}}},
     "At most 20 facts and 50 sources."),
])
def test_a_request_may_hold_only_what_a_brief_needs(body, message):
    response = client.post("/evaluate", json=body)

    assert response.status_code == 422
    assert any(problem["msg"].startswith(message) for problem in response.json()["detail"]), response.json()


def test_no_context_is_within_the_limits():
    assert check_context(None) is None


def test_a_report_edit_and_a_session_in_a_path_are_checked_too():
    long = client.put("/reports/s1", json={"version": 1, "sections": [{"key": "k", "title": "T", "body": "x" * 60_001}]})
    many = client.put("/reports/s1", json={"version": 1, "sections": [{"key": "k", "title": "T", "body": "B"}] * 31})
    odd = client.get("/reports/not a session")

    assert long.status_code == 422 and "A section is longer than 60,000 characters." in long.text
    assert many.status_code == 422 and "at most 30 items" in many.text
    assert odd.status_code == 422


def test_a_failed_search_keeps_the_brief_out_of_the_log(fake_llm, monkeypatch, caplog):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(search, "_transport", httpx.MockTransport(lambda request: httpx.Response(500, json={})))
    fake_llm.search_plan.queries = ["acme-confidential-launch-plan pricing"]

    with caplog.at_level(logging.WARNING):
        client.post("/brief/prepare", json={"prompt": "An idea."})

    said = " ".join(record.getMessage() for record in caplog.records)
    assert "A search failed" in said and "acme-confidential" not in said
