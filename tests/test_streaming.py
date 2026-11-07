"""Tests for /evaluate/stream: the team's progress as server-sent events."""

import json

import httpx2
import openai
from fastapi.testclient import TestClient

from llm import CHIEF, SPECIALIST
from main import app
from progress import summarize
from state import Conflict, DelegationPlan, Resolution, ReviewResult, SpecialistCritique, Task

client = TestClient(app)
CONFLICT = Conflict(raised_by="finance", about="marketing", issue="The pilot price is too low.")


def _stream(body: dict) -> list[tuple[str, dict]]:
    """The events of one streamed evaluation, as (name, data)."""
    with client.stream("POST", "/evaluate/stream", json=body) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        text = response.read().decode()
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_the_team_reports_each_step_then_the_result(fake_llm):
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT])
    fake_llm.resolution = Resolution(conflict=CONFLICT, decision="Price at $149.", revise="marketing")

    events = _stream({"prompt": "Evaluate an AI scheduling tool."})

    steps = [(name, data["node"]) for name, data in events if name != "result"]
    assert steps[:2] == [("start", "plan"), ("done", "plan")]
    specialists = {"marketing", "finance", "technical", "risk"}
    assert {node for name, node in steps[2:10]} == specialists
    assert [step for step in steps[10:]] == [
        ("start", "review"), ("done", "review"),
        ("start", "critique"), ("done", "critique"),
        ("start", "resolve"), ("done", "resolve"),
        # Marketing revises after the decision, then the strategy is written.
        ("start", "marketing"), ("done", "marketing"),
        ("start", "synthesis"), ("done", "synthesis"),
    ]
    done = {data["node"]: data for name, data in events if name == "done"}
    assert done["plan"]["summary"] == (
        "Planned the work and assigned Marketing Strategy, Financial Planning, "
        "Technical Feasibility and Risk & Compliance."
    )
    assert done["plan"]["assigned"] == ["marketing", "finance", "technical", "risk"]
    assert done["review"]["summary"] == "Reviewed 4 reports: approved 4."
    assert done["critique"]["summary"] == "Cross-checked the reports and raised 1 conflict."
    assert done["resolve"]["summary"] == "Settled 1 conflict; Marketing Strategy to revise."
    assert done["marketing"]["revision"] is True  # the last marketing event is its revision
    assert done["marketing"]["summary"].startswith("Revised its report (")
    assert done["synthesis"]["summary"].startswith("Wrote the launch strategy (")
    times = [data["at"] for name, data in events if name != "result"]
    assert times == sorted(times)

    name, result = events[-1]
    assert name == "result"
    assert result["final_strategy"] and result["objective"] == "Evaluate the request."
    assert result["resolutions"][0]["decision"] == "Price at $149."
    assert client.get(f"/reports/{result['session_id']}").status_code == 200


def test_a_report_sent_back_is_named_and_its_revision_follows(fake_llm):
    def review_for(report: str) -> ReviewResult:
        # Finance's first report is sent back; its revision carries the feedback.
        if "You are the Financial Planning Agent" in report and "Show the arithmetic." not in report:
            return ReviewResult(approved=False, score=3, feedback="Show the arithmetic.")
        return ReviewResult(approved=True, score=5, feedback="")

    fake_llm._review_for = review_for

    events = _stream({"prompt": "Evaluate an AI scheduling tool."})

    reviews = [data for name, data in events if name == "done" and data["node"] == "review"]
    assert reviews[0]["summary"] == "Reviewed 4 reports: approved 3, sent back Financial Planning."
    assert reviews[0]["reviews"]["finance"] == {"approved": False, "score": 3}
    assert reviews[1]["summary"] == "Reviewed 1 report: approved 1."
    finance = [data for name, data in events if name == "done" and data["node"] == "finance"]
    assert [data["revision"] for data in finance] == [False, True]


def test_a_report_still_short_after_its_revision_is_not_sent_back_again(fake_llm):
    def review_for(report: str) -> ReviewResult:
        if "You are the Financial Planning Agent" in report:
            return ReviewResult(approved=False, score=3, feedback="Show the arithmetic.")
        return ReviewResult(approved=True, score=5, feedback="")

    fake_llm._review_for = review_for

    events = _stream({"prompt": "Evaluate an AI scheduling tool."})

    reviews = [data for name, data in events if name == "done" and data["node"] == "review"]
    assert [data["summary"] for data in reviews] == [
        "Reviewed 4 reports: approved 3, sent back Financial Planning.",
        "Reviewed 1 report: Financial Planning still falls short, with no revision left.",
    ]
    assert [data["node"] for name, data in events if name == "start"].count("finance") == 2


def test_a_follow_up_streams_only_the_specialists_it_needs(fake_llm):
    first = _stream({"prompt": "Evaluate an AI scheduling tool."})[-1][1]
    fake_llm.plan = DelegationPlan(objective="Reprice.", tasks=[Task(specialist="finance", task="Reprice.")])

    events = _stream({"prompt": "Refine the pricing.", "session_id": first["session_id"]})

    started = [data["node"] for name, data in events if name == "start"]
    assert started[:2] == ["plan", "finance"]
    assert not {"marketing", "technical", "risk"} & set(started)
    assert started[-1] == "synthesis"
    assert events[-1][1]["session_id"] == first["session_id"]


def test_the_requests_reasoning_reaches_every_call(fake_llm):
    _stream({"prompt": "An idea.", "reasoning": {"specialist": "low", "chief": "high"}})

    assert set(fake_llm.efforts) == {(SPECIALIST, "low"), (CHIEF, "high")}


def test_a_failed_specialist_is_reported_and_the_run_goes_on(fake_llm):
    fake_llm.fail = {"risk"}

    events = _stream({"prompt": "An idea."})

    risk = next(data for name, data in events if name == "done" and data["node"] == "risk")
    assert risk == {"node": "risk", "at": risk["at"], "summary": "Could not write its report: the LLM call failed.", "failed": True}
    assert events[-1][0] == "result"


def test_without_a_model_the_stream_says_so():
    events = _stream({"prompt": "An idea."})

    assert events[-1] == ("error", {"status": 503, "detail": events[-1][1]["detail"]})
    assert "No LLM provider configured" in events[-1][1]["detail"]


def test_a_failed_plan_ends_the_stream_with_its_reason(fake_llm):
    def fail(prompt):
        raise openai.APIConnectionError(request=httpx2.Request("POST", "https://llm.example"))

    fake_llm._plan_for = fail

    events = _stream({"prompt": "An idea."})

    assert [name for name, _ in events] == ["start", "error"]
    assert events[-1][1]["status"] == 502
    assert events[-1][1]["detail"].startswith("The LLM call failed:")


def test_an_unexpected_failure_is_reported_too(fake_llm, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("main.SessionResults.from_state", broken)

    events = _stream({"prompt": "An idea."})

    assert events[-1] == ("error", {"status": 500, "detail": "The evaluation failed unexpectedly."})


def test_a_summary_never_fails_the_request():
    assert summarize("plan", {"unexpected": True}, 1) == {"summary": "Done."}
    assert summarize("somewhere", {}, 1) == {"summary": "Done."}
    assert summarize("resolve", {"resolutions": []}, 1)["summary"] == "Settled 0 conflicts."
    assert summarize("critique", {"conflicts": []}, 1)["summary"] == "Cross-checked the reports: no conflicts."
