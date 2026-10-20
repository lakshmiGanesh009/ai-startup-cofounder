"""Tests for the monitor behind the How it works page, and the endpoints that
describe the pipeline and report what the API has done."""

import logging
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import monitor as monitor_module
from main import app
from monitor import Monitor, MonitorHandler, Run
from state import NodeMetric
from tests.conftest import _provider_error

client = TestClient(app)


def _run(session: str, ok: bool = True, **changes) -> Run:
    return Run(session=session, at=datetime.now(timezone.utc), seconds=10.0, ok=ok, **changes)


def test_the_monitor_keeps_totals_and_the_latest_runs_and_events(monkeypatch):
    monkeypatch.setattr(monitor_module, "MAX_EVENTS", 3)
    watch = Monitor()
    for number in range(5):
        watch.event("done", "plan", f"Event {number}", session="session-123456789")
    watch.run(_run("a", calls=3, tokens=100, reviewed=4, approved=3, conflicts=1, searches=12,
                   nodes={"plan": NodeMetric(calls=1, seconds=9.5, tokens=40)}))
    watch.run(_run("b", ok=False, error="boom", nodes={"plan": NodeMetric(calls=1, seconds=2.0, tokens=10)}))
    watch.count("briefs")
    watch.count("proposals")

    seen = watch.snapshot()

    assert [event.message for event in seen.events] == ["Event 4", "Event 3", "Event 2"]
    assert seen.events[0].session == "session-"
    assert [run.session for run in seen.runs] == ["b", "a"]
    totals = seen.totals
    # The failed run counts, but its time and calls do not: it never finished.
    assert (totals.evaluations, totals.failures, totals.calls, totals.tokens) == (2, 1, 3, 100)
    assert (totals.reviewed, totals.approved, totals.conflicts, totals.searches) == (4, 3, 1, 12)
    assert (totals.briefs, totals.proposals, totals.seconds) == (1, 1, 10.0)
    assert seen.nodes[0].model_dump() == {"node": "plan", "runs": 1, "calls": 1, "seconds": 9.5, "tokens": 40}
    watch.reset()
    assert watch.snapshot().totals.evaluations == 0


def test_warnings_errors_and_retries_reach_the_log():
    watch = Monitor()
    handler = MonitorHandler(watch)
    log = logging.getLogger("tests.monitor")
    client_log = logging.getLogger("openai._base_client")
    level = client_log.level
    log.addHandler(handler)
    client_log.addHandler(handler)
    client_log.setLevel(logging.INFO)  # as under the API, which logs at INFO
    try:
        log.info("Routine.")
        log.warning("Search for 'x' failed: Tavily answered 500")
        log.error("Evaluation failed")
        client_log.info("Sending HTTP Request: POST https://example.openai.azure.com")  # routine, so left out
        client_log.info("Retrying request in 0.4 seconds")
    finally:
        log.removeHandler(handler)
        client_log.removeHandler(handler)
        client_log.setLevel(level)

    events = [(event.kind, event.message) for event in reversed(watch.snapshot().events)]
    assert events == [
        ("warning", "Search for 'x' failed: Tavily answered 500"),
        ("error", "Evaluation failed"),
        ("warning", "The model call was retried (Azure stalled or refused it)."),
    ]


def test_the_pipeline_is_described_as_the_code_runs_it():
    described = client.get("/pipeline").json()

    mermaid = described["mermaid"]
    assert "plan -.-> research;" in mermaid and "critique --> resolve;" in mermaid
    assert "__start__([start])" in mermaid and "<p>" not in mermaid
    assert "classDef" not in mermaid and ":::" not in mermaid
    assert [s["title"] for s in described["specialists"]] == [
        "Marketing Strategy", "Financial Planning", "Technical Feasibility", "Risk & Compliance",
    ]
    assert [s["reads_competitors"] for s in described["specialists"]] == [True, True, False, False]
    assert described["rules"] == {
        "approval_score": 4, "max_revisions": 1, "max_critique_rounds": 1, "report_words": 250,
        "strategy_words": 500, "max_questions": 3, "max_facts": 8, "max_competitors": 3,
    }


def test_a_streamed_evaluation_is_logged_step_by_step(fake_llm):
    with client.stream("POST", "/evaluate/stream", json={"prompt": "An idea."}) as response:
        response.read()

    seen = client.get("/monitoring").json()

    run = seen["runs"][0]
    assert run["ok"] and run["specialists"] == ["marketing", "finance", "technical", "risk"]
    assert run["reviewed"] == 4 and run["approved"] == 4 and run["calls"] > 0
    assert run["research"] is None and "plan" in run["nodes"]
    kinds = [(event["kind"], event["source"]) for event in reversed(seen["events"])]
    assert kinds[:2] == [("start", "plan"), ("done", "plan")]
    assert kinds[-1] == ("run", "evaluate")
    assert seen["events"][0]["message"].startswith("Finished in ")
    assert seen["totals"]["evaluations"] == 1
    assert {node["node"] for node in seen["nodes"]} >= {"plan", "review", "synthesis"}


def test_evaluations_that_fail_are_counted_with_their_reason(fake_llm):
    def fail(prompt):
        raise _provider_error()

    fake_llm._plan_for = fail
    assert client.post("/evaluate", json={"prompt": "An idea."}).status_code == 502
    with client.stream("POST", "/evaluate/stream", json={"prompt": "An idea."}) as response:
        response.read()

    seen = client.get("/monitoring").json()
    assert seen["totals"]["failures"] == 2
    assert all(not run["ok"] and run["error"].startswith("The LLM call failed") for run in seen["runs"])
    assert [event["kind"] for event in seen["events"]].count("warning") == 2


def test_without_a_model_the_failure_is_logged():
    assert client.post("/evaluate", json={"prompt": "An idea."}).status_code == 503
    assert client.post("/brief/prepare", json={"prompt": "An idea."}).status_code == 503

    errors = [event["message"] for event in client.get("/monitoring").json()["events"] if event["kind"] == "error"]
    assert errors[0].startswith("No brief could be prepared: No LLM provider configured")
    assert errors[1].startswith("No evaluation could run: No LLM provider configured")


def test_evaluations_briefs_and_proposals_are_counted(fake_llm):
    result = client.post("/evaluate", json={"prompt": "An idea."}).json()
    client.post("/brief/prepare", json={"prompt": "An idea."})
    client.post(f"/reports/{result['session_id']}/proposal", json={"version": 1})

    seen = client.get("/monitoring").json()

    assert (seen["totals"]["evaluations"], seen["totals"]["briefs"], seen["totals"]["proposals"]) == (1, 1, 1)
    messages = [event["message"] for event in seen["events"]]
    assert messages[0].startswith("Wrote the investment proposal in ")
    assert messages[1].startswith("Prepared a brief in ") and "0 facts kept, 1 questions" in messages[1]
    assert messages[2].startswith("Finished in ")


def test_a_proposal_that_fails_is_logged(fake_llm):
    result = client.post("/evaluate", json={"prompt": "An idea."}).json()
    fake_llm.fail_parts = {"executive", "market", "technical", "risk", "financial"}

    response = client.post(f"/reports/{result['session_id']}/proposal", json={"version": 1})

    assert response.status_code == 502
    error = next(event for event in client.get("/monitoring").json()["events"] if event["kind"] == "error")
    assert error["source"] == "proposal" and error["message"].startswith("Writing the proposal failed")
