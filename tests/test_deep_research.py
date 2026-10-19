"""Tests for the specialists' deep research: Tavily's Research API (answered by
a mock transport, or replaced), the sources numbered once per session, and the
research step in the graph."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

import deep_research
import search
from deep_research import SourceBook, _brackets, _mentions
from main import app
from search import Report, SearchFailed
from state import DelegationPlan, Source, Task
from tests.conftest import _provider_error

client = TestClient(app)


# ---- The Research API client ----

def _tavily(monkeypatch, answers):
    """Answer the research calls in turn from `answers`, and record the requests."""
    requests = []
    replies = iter(answers)

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return next(replies)

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(search, "_transport", httpx.MockTransport(handle))
    return requests


CREATED = httpx.Response(201, json={"request_id": "task-1", "status": "pending"})
RUNNING = httpx.Response(202, json={"request_id": "task-1", "status": "in_progress"})
DONE = httpx.Response(200, json={
    "request_id": "task-1",
    "status": "completed",
    "content": "Tools cost $50 a month [1][2].\n\n---\n\n### Sources\n- [1] https://a.example\n- [2] https://b.example",
    "sources": [
        {"title": "[PDF] Prices 2026", "url": "https://a.example", "favicon": ""},
        {"title": "", "url": "https://b.example"},
        {"title": "No address"},
    ],
    "usage": {"credits": 42},
})


def test_a_research_task_is_started_then_awaited(monkeypatch):
    requests = _tavily(monkeypatch, [CREATED, RUNNING, DONE])

    report = search.research("What do scheduling tools cost?", {"properties": {}})

    assert report == Report(
        content="Tools cost $50 a month [1][2].",  # its own reference list is dropped
        sources=[("Prices 2026", "https://a.example"), ("https://b.example", "https://b.example")],
        credits=42,
    )
    assert json.loads(requests[0].content) == {
        "input": "What do scheduling tools cost?", "model": "mini", "citation_format": "numbered",
        "output_length": "short", "output_schema": {"properties": {}},
    }
    assert requests[0].headers["Authorization"] == "Bearer tvly-test"
    assert str(requests[1].url) == "https://api.tavily.com/research/task-1?include_usage=true"
    assert len(requests) == 3


@pytest.mark.parametrize(("answers", "reason"), [
    ([httpx.Response(400, json={"detail": {"error": "bad schema"}})], "Tavily answered 400"),
    ([httpx.Response(432)], "the Tavily plan's monthly limit is used up"),
    ([CREATED, httpx.Response(200, json={"request_id": "task-1", "status": "failed"})], "research task failed"),
    ([CREATED, httpx.Response(500)], "Tavily answered 500"),
    ([httpx.Response(201, content=b"not json")], "could not be read"),
])
def test_a_research_task_that_fails_says_why(monkeypatch, answers, reason):
    _tavily(monkeypatch, answers)

    with pytest.raises(SearchFailed, match=reason):
        search.research("A question")


def test_research_that_runs_too_long_or_cannot_be_reached_fails(monkeypatch):
    _tavily(monkeypatch, [CREATED, RUNNING, RUNNING, RUNNING])
    monkeypatch.setattr(search, "RESEARCH_TIMEOUT", 0)
    with pytest.raises(SearchFailed, match="took longer than 0 s"):
        search.research("A question")

    def unreachable(request):
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr(search, "_transport", httpx.MockTransport(unreachable))
    with pytest.raises(SearchFailed, match=r"could not be reached \(ConnectError\)"):
        search.research("A question")
    monkeypatch.delenv("TAVILY_API_KEY")
    with pytest.raises(SearchFailed, match="no TAVILY_API_KEY"):
        search.research("A question")


def test_research_tasks_run_together_and_a_failure_is_kept_apart(monkeypatch):
    def research(task, schema):
        if task == "bad":
            raise SearchFailed("Tavily answered 500")
        return Report(content=task, sources=[], credits=1)

    monkeypatch.setattr(search, "research", research)

    results = search.research_all({"one": ("good", None), "two": ("bad", None)})

    assert results["one"].content == "good"
    assert isinstance(results["two"], SearchFailed)
    assert search.research_all({}) == {}


# ---- Sources numbered once ----

def test_sources_keep_their_numbers_and_new_ones_follow():
    book = SourceBook([Source(title="Brief source", url="https://brief.example")])
    report = Report(content="", sources=[("Market", "https://m.example"), ("Brief again", "https://brief.example")], credits=0)

    numbers = book.renumber(report)

    assert numbers == {1: 2, 2: 1}
    assert [source.url for source in book.sources] == ["https://brief.example", "https://m.example"]
    assert _brackets("Grows 8% [1]; see [2] and [7].", numbers) == "Grows 8% [2]; see [1] and ."
    assert _mentions("Raised $17M (source2). Customers: 200 (Source 1)", numbers) == "Raised $17M [1]. Customers: 200 [2]"


# ---- The research step ----

AREA = "The {name} market grows 8% a year [1], and tools cost $50 a month [2]."


@pytest.fixture
def tavily(monkeypatch):
    """Deep research turned on, answered per task: `failing` names task keys that fail."""
    calls: list[dict] = []
    failing: set[str] = set()

    def research_all(tasks):
        calls.append(tasks)
        reports = {}
        for key, (task, schema) in tasks.items():
            kind, name = key.split(":")
            if key in failing:
                reports[key] = SearchFailed("Tavily answered 500")
            elif schema:
                reports[key] = Report(
                    content={"name": f"{name} Inc.", "summary": "Patient messaging for clinics.",
                             "pricing": "$15 per user a month (source2)", "customers": "219 practices [1]",
                             "strengths": "Integrations", "weaknesses": "Fragmented pricing"},
                    sources=[("Profile", f"https://{name.lower()}.example"), ("Shared prices", "https://shared.example")],
                    credits=22,
                )
            else:
                reports[key] = Report(
                    content=AREA.format(name=name),
                    sources=[(f"{name} report", f"https://{name}.example"), ("Shared prices", "https://shared.example")],
                    credits=80,
                )
        return reports

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(deep_research, "research_all", research_all)
    return {"calls": calls, "failing": failing}


BRIEF_RESEARCH = {
    "findings": [{"point": "Tools cost $20-$300 a month.", "sources": [1]}],
    "sources": [{"title": "Brief source", "url": "https://brief.example"}],
}


def _evaluate(**body):
    return client.post("/evaluate", json={"prompt": "Evaluate a scheduling assistant for clinics.", **body}).json()


def test_deep_research_covers_each_specialist_and_the_competitors(fake_llm, tavily):
    result = _evaluate(deep_research=True, context={"target_market": "US clinics", "research": BRIEF_RESEARCH})

    tasks = tavily["calls"][0]
    assert sorted(tasks) == ["area:finance", "area:marketing", "area:risk", "area:technical", "company:Klara"]
    assert "Research for the Financial Planning specialist" in tasks["area:finance"][0]
    assert "The specialist's task: Handle finance." in tasks["area:finance"][0]
    assert "Target market: US clinics" in tasks["area:finance"][0]
    assert "Web research" not in tasks["area:finance"][0]  # the brief's research is not sent again
    assert "Profile the company Klara (patient messaging for clinics)" in tasks["company:Klara"][0]
    assert tasks["company:Klara"][1] == deep_research.COMPANY_SCHEMA

    research = result["research"]
    # The brief's source keeps [1]; each new page gets one number, shared pages one between them.
    assert [s["url"] for s in research["sources"]] == [
        "https://brief.example", "https://marketing.example", "https://shared.example",
        "https://finance.example", "https://technical.example", "https://risk.example", "https://klara.example",
    ]
    assert research["areas"]["finance"] == "The finance market grows 8% a year [4], and tools cost $50 a month [3]."
    assert research["companies"] == [{
        "name": "Klara Inc.", "summary": "Patient messaging for clinics.", "pricing": "$15 per user a month [3]",
        "customers": "219 practices [7]", "funding": "", "recent_moves": "", "strengths": "Integrations",
        "weaknesses": "Fragmented pricing", "sources": [3, 7],
    }]
    assert research["credits"] == 4 * 80 + 22
    assert research["failed"] == []
    assert result["metrics"]["research"]["calls"] == 1  # naming the competitors

    # Each specialist reads its own area; Marketing and Finance read the competitors too.
    finance, technical = result["analyses"]["finance"], result["analyses"]["technical"]
    assert "Deep research on your area, by Tavily" in finance and "The finance market grows" in finance
    assert "Competitor profiles, by Tavily:\n- Klara Inc.: Patient messaging for clinics." in finance
    assert "[3] Shared prices (https://shared.example)" in finance
    assert "The technical market grows" in technical and "Competitor profiles" not in technical
    assert "The finance market grows" not in technical


def test_the_report_lists_the_research_with_one_set_of_sources(fake_llm, tavily):
    result = _evaluate(deep_research=True, context={"research": BRIEF_RESEARCH})

    report = client.get(f"/reports/{result['session_id']}").json()
    body = next(section["body"] for section in report["sections"] if section["key"] == "research")
    assert body.startswith("### Before the team started\n\n- Tools cost $20-$300 a month. [1]")
    assert "### Financial Planning\n\nThe finance market grows 8% a year [4]" in body
    assert "### Competitors\n\n- **Klara Inc.**: Patient messaging for clinics. Pricing: $15 per user a month [3]" in body
    assert body.endswith("7. [Profile](https://klara.example)")
    assert client.get(f"/reports/{result['session_id']}/pdf").content.startswith(b"%PDF")


def test_the_stream_reports_the_research(fake_llm, tavily):
    tavily["failing"].add("area:risk")
    with client.stream("POST", "/evaluate/stream", json={"prompt": "An idea.", "deep_research": True}) as response:
        text = response.read().decode()

    events = [dict(line.split(": ", 1) for line in block.splitlines()) for block in text.strip().split("\n\n")]
    done = next(json.loads(e["data"]) for e in events if e["event"] == "done" and '"research"' in e["data"])
    assert done["summary"] == (
        "Researched 3 areas and 1 competitor (5 sources, 262 credits); "
        "could not research Risk & Compliance."
    )
    assert done["not_researched"] == ["risk"] and done["companies"] == ["Klara Inc."]
    starts = [json.loads(e["data"])["node"] for e in events if e["event"] == "start"]
    assert starts[:2] == ["plan", "research"]


def test_without_asking_or_without_a_key_there_is_no_deep_research(fake_llm, tavily, monkeypatch):
    assert _evaluate()["research"] is None
    monkeypatch.delenv("TAVILY_API_KEY")
    assert _evaluate(deep_research=True)["research"] is None
    assert tavily["calls"] == []


def test_a_follow_up_reuses_the_research_and_researches_only_new_areas(fake_llm, tavily):
    fake_llm.plan = DelegationPlan(objective="Evaluate.", tasks=[Task(specialist="marketing", task="Pick a niche.")])
    first = _evaluate(deep_research=True)
    assert sorted(tavily["calls"][0]) == ["area:marketing", "company:Klara"]

    # A follow-up without deep research reuses it.
    fake_llm.plan = DelegationPlan(objective="Reprice.", tasks=[Task(specialist="marketing", task="Reprice.")])
    again = client.post("/evaluate", json={"prompt": "Refine.", "session_id": first["session_id"]}).json()
    assert len(tavily["calls"]) == 1
    assert "The marketing market grows" in again["analyses"]["marketing"]
    assert again["research"]["areas"].keys() == {"marketing"}

    # One that asks again researches only the area not yet covered, not the competitors.
    fake_llm.plan = DelegationPlan(objective="Cost it.", tasks=[
        Task(specialist="marketing", task="Keep the niche."), Task(specialist="finance", task="Cost it."),
    ])
    client.post("/evaluate", json={"prompt": "Cost it.", "session_id": first["session_id"], "deep_research": True})
    assert list(tavily["calls"][1]) == ["area:finance"]


def test_research_that_fails_leaves_the_team_to_work_without_it(fake_llm, tavily):
    def fail(prompt):
        raise _provider_error()

    fake_llm._competitors_for = fail
    tavily["failing"].update({"area:technical"})

    result = _evaluate(deep_research=True)

    assert sorted(result["research"]["areas"]) == ["finance", "marketing", "risk"]
    assert result["research"]["companies"] == []
    assert result["research"]["failed"] == ["technical"]
    assert "Deep research on your area" not in result["analyses"]["technical"]
    assert result["final_strategy"]


def test_a_profile_that_comes_back_without_fields_is_counted_as_failed(fake_llm, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(deep_research, "research_all", lambda tasks: {
        key: Report(content="Not a profile." if key.startswith("company") else "", sources=[], credits=5)
        for key in tasks
    })

    result = _evaluate(deep_research=True)

    assert result["research"]["companies"] == [] and result["research"]["areas"] == {}
    assert sorted(result["research"]["failed"]) == ["Klara", "finance", "marketing", "risk", "technical"]


def test_a_run_of_sources_reads_as_a_range():
    from reports import _cite_range

    assert _cite_range([40, 38, 39]) == "[38]–[40]"
    assert _cite_range([3, 7]) == "[3][7]"
