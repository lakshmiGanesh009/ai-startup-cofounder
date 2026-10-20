"""Tests for preparing a brief: the decision templates, the web research, the
Chief of Staff's questions, and the research and answers reaching the team."""

import re

import pytest
from fastapi.testclient import TestClient

import brief
from brief import RESEARCH_OFF, BriefReview, Question, SearchPlan, load_templates, prepare_brief
from llm import CHIEF, SPECIALIST
from main import app
from search import Hit
from state import Finding, RequestContext
from tests.conftest import _provider_error

client = TestClient(app)

HITS = [
    Hit("Scheduling software prices", "https://prices.example", "Tools cost $20-$300 per provider a month."),
    Hit("AMA practice survey", "https://ama.example", "147,000 office-based primary care physicians."),
    Hit("Clinic market report", "https://market.example", "The market grows 8% a year."),
]


@pytest.fixture
def web(monkeypatch):
    """Search turned on, answering every brief with HITS; records the queries."""
    searched: list[list[str]] = []

    def search_all(queries, provider):
        searched.append(queries)
        assert provider == "tavily"  # the only provider set up in these tests
        return HITS, None

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(brief, "search_all", search_all)
    return searched


def test_a_brief_is_researched_then_read_by_the_chief_of_staff(fake_llm, web):
    fake_llm.search_plan = SearchPlan(queries=["market size", " market size ", "prices", "", "rules", "buyers", "extra"])
    fake_llm.brief_review = BriefReview(
        findings=[
            Finding(point=" The market grows 8% a year. ", sources=[3, 3, 1]),
            Finding(point="A figure from nowhere.", sources=[9]),
            Finding(point="An uncited claim.", sources=[]),
            Finding(point="  ", sources=[2]),
            Finding(point="147,000 primary care physicians.", sources=[2]),
        ],
        questions=[
            Question(question="What budget do you have?", why="It sets the pilot.", suggestions=["Under $15k"]),
            Question(question=" ", why="", suggestions=[]),
            Question(question="Who is on the team?", why="It sets the build plan.", suggestions=["Solo"]),
            Question(question="What is the timeline?", why="It sets the scope.", suggestions=["Six months"]),
            Question(question="One too many?", why="Only three are asked.", suggestions=[]),
        ],
    )

    prepared = prepare_brief("An assistant for clinics.", RequestContext(target_market="US clinics"), None)

    assert web == [["market size", "prices", "rules", "buyers"]]
    assert prepared.queries == ["market size", "prices", "rules", "buyers"]
    # Only cited, real results are kept, numbered in order of first citation.
    assert [(f.point, f.sources) for f in prepared.research.findings] == [
        ("The market grows 8% a year.", [1, 2]),
        ("147,000 primary care physicians.", [3]),
    ]
    assert [s.url for s in prepared.research.sources] == ["https://market.example", "https://prices.example", "https://ama.example"]
    assert prepared.research_note is None
    assert [q.question for q in prepared.questions] == ["What budget do you have?", "Who is on the team?", "What is the timeline?"]
    # The searches are planned at the specialists' effort; the reading is the Chief of Staff's.
    assert fake_llm.calls == [(SPECIALIST, "SearchPlan"), (CHIEF, "BriefReview")]
    review = dict(fake_llm.brief_prompts)["review"]
    assert "An assistant for clinics." in review and "Target market: US clinics" in review
    assert "[2] AMA practice survey (https://ama.example)\n147,000 office-based" in review


def test_without_a_search_key_the_brief_is_still_checked(fake_llm):
    prepared = prepare_brief("An idea.", None, None)

    assert prepared.research is None and prepared.queries == []
    assert prepared.research_note == RESEARCH_OFF
    assert [q.question for q in prepared.questions] == ["What budget do you have to first launch?"]
    assert fake_llm.calls == [(CHIEF, "BriefReview")]
    assert "The web search found no results." in dict(fake_llm.brief_prompts)["review"]


@pytest.mark.parametrize(("found", "note"), [
    (([], "The web search failed: Tavily answered 500."), "The web search failed: Tavily answered 500."),
    (([], None), "The web search found nothing for this brief."),
    ((HITS, None), "The search results held nothing the Chief of Staff could cite for this decision."),
])
def test_research_that_comes_to_nothing_says_why(fake_llm, monkeypatch, found, note):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(brief, "search_all", lambda queries, provider: found)
    fake_llm.brief_review = BriefReview(findings=[Finding(point="Uncited.", sources=[7])], questions=[])

    prepared = prepare_brief("An idea.", None, None)

    assert prepared.research is None
    assert prepared.research_note == note
    assert prepared.questions == []


def test_a_template_says_what_to_look_up_and_what_to_ask(fake_llm, web, monkeypatch):
    systems = {}
    real = brief.structured_invoke

    def spy(schema, messages, tracker, role):
        systems[schema.__name__] = messages[0].content
        return real(schema, messages, tracker, role)

    monkeypatch.setattr(brief, "structured_invoke", spy)
    template = next(t for t in load_templates() if t.name == "pricing")

    prepare_brief("Price our tool.", None, template)

    assert systems["SearchPlan"].endswith(
        "look up: what competitors charge and how they package it; what buyers like these pay for "
        "similar tools; typical costs to serve and margins in the category."
    )
    assert "make sure you know: the cost to serve one customer;" in systems["BriefReview"]


def test_the_templates_are_decisions_to_fill_in():
    templates = load_templates()

    assert [t.name for t in templates] == ["evaluate_idea", "go_to_market", "pricing", "fundraising", "competitor"]
    for template in templates:
        assert set(re.findall(r"\{(\w+)\}", template.prompt)) == {field.key for field in template.fields}
        assert template.research and template.ask and template.summary
    served = client.get("/templates")
    assert served.status_code == 200
    assert served.json()[0]["title"] == "Evaluate a new idea"
    assert served.json()[0]["fields"][0] == {
        "key": "idea", "label": "The idea",
        "placeholder": "An assistant that drafts patient follow-ups from clinical notes", "long": True,
    }


def test_the_api_prepares_a_brief_at_the_chosen_efforts(fake_llm, web):
    response = client.post("/brief/prepare", json={
        "prompt": "  Evaluate a scheduling assistant.  ",
        "context": {"constraints": "Under $15k"},
        "template": "evaluate_idea",
        "reasoning": {"specialist": "low", "chief": "high"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["queries"] == ["clinic scheduling software market size", "clinic scheduling software prices"]
    assert body["research"]["sources"][0] == {"title": "AMA practice survey", "url": "https://ama.example"}
    assert body["research"]["findings"][1] == {"point": "Scheduling tools cost $20-$300 per provider a month in 2025.", "sources": [2, 1]}
    assert body["questions"][0]["suggestions"] == ["Under $15k", "$15k-$50k", "Over $50k"]
    assert body["research_note"] is None
    assert fake_llm.efforts == [(SPECIALIST, "low"), (CHIEF, "high")]
    assert "Evaluate a scheduling assistant.\n\nWhat the founder told us:\nConstraints: Under $15k" in dict(fake_llm.brief_prompts)["search"]


def test_the_api_refuses_what_it_cannot_prepare(fake_llm):
    assert client.post("/brief/prepare", json={"prompt": "An idea.", "template": "nope"}).status_code == 422
    assert client.post("/brief/prepare", json={"prompt": ""}).status_code == 422

    def fail(prompt):
        raise _provider_error()

    fake_llm._brief_review_for = fail
    failed = client.post("/brief/prepare", json={"prompt": "An idea."})
    assert failed.status_code == 502
    assert failed.json()["detail"].startswith("The LLM call failed:")


def test_without_a_model_the_api_says_so():
    response = client.post("/brief/prepare", json={"prompt": "An idea."})

    assert response.status_code == 503
    assert "No LLM provider configured" in response.json()["detail"]


def test_the_health_check_says_where_research_can_run(monkeypatch):
    assert client.get("/health").json()["research"] == {"providers": {"azure": False, "tavily": False}, "default": None}
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    assert client.get("/health").json()["research"] == {"providers": {"azure": False, "tavily": True}, "default": "tavily"}
    for name in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME"):
        monkeypatch.setenv(name, "set")
    # Azure OpenAI's own web search is the default once it is set up.
    assert client.get("/health").json()["research"] == {"providers": {"azure": True, "tavily": True}, "default": "azure"}


def test_the_research_and_answers_reach_the_team_and_the_report(fake_llm):
    context = {
        "target_market": "US clinics",
        "answers": [
            {"question": "What budget do you have?", "answer": "Under $15k"},
            {"question": "Who is on the team?", "answer": "  "},
        ],
        "research": {
            "findings": [{"point": "Tools cost $20-$300 per provider a month.", "sources": [1]}],
            "sources": [{"title": "Scheduling software prices", "url": "https://prices.example"}],
        },
    }

    result = client.post("/evaluate", json={"prompt": "Evaluate a scheduling assistant.", "context": context}).json()

    finance = result["analyses"]["finance"]  # the fake model echoes what it was given
    assert "The founder's answers to the Chief of Staff's questions:\n- What budget do you have? Under $15k" in finance
    assert "Who is on the team?" not in finance  # an unanswered question is left out
    assert "- Tools cost $20-$300 per provider a month. [1]" in finance
    assert "[1] Scheduling software prices (https://prices.example)" in finance
    report = client.get(f"/reports/{result['session_id']}").json()
    research = next(section for section in report["sections"] if section["key"] == "research")
    assert research["title"] == "Web Research"
    assert research["body"] == (
        "- Tools cost $20-$300 per provider a month. [1]\n\n**Sources**\n\n"
        "1. [Scheduling software prices](https://prices.example)"
    )
    pdf = client.get(f"/reports/{result['session_id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_a_report_without_research_has_no_research_section(fake_llm):
    result = client.post("/evaluate", json={"prompt": "An idea.", "context": {"target_market": "Clinics"}}).json()

    report = client.get(f"/reports/{result['session_id']}").json()

    assert "research" not in [section["key"] for section in report["sections"]]


def test_at_most_eight_facts_are_kept_and_empty_research_says_nothing(fake_llm, web):
    fake_llm.brief_review = BriefReview(
        findings=[Finding(point=f"Fact {n}.", sources=[1]) for n in range(1, 11)], questions=[]
    )

    prepared = prepare_brief("An idea.", None, None)

    assert [f.point for f in prepared.research.findings] == [f"Fact {n}." for n in range(1, 9)]
    assert RequestContext(research={"findings": [], "sources": []}).as_prompt() == ""
