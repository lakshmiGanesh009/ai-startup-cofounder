"""Tests for web research on Azure OpenAI's own web search (azure_web.py), with
a stand-in for the Responses API, and for choosing where research runs
(providers.py)."""

import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

import azure_web
import brief
import providers
from deep_research import COMPANY_SCHEMA
from main import app
from search import SearchFailed

client = TestClient(app)
AZURE = ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME")


def answer(text="", notes=(), results=None, searches=None, calls=1):
    """A Responses API reply: its web search calls, then the message."""
    output = [SimpleNamespace(type="reasoning")]
    output += [SimpleNamespace(type="web_search_call", results=results) for _ in range(calls)]
    output.append(SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text, annotations=list(notes))]))
    usage = {"web_search": {"num_requests": searches}} if searches is not None else None
    return SimpleNamespace(output=output, tool_usage=usage)


@pytest.fixture
def azure(monkeypatch):
    """Azure OpenAI set up, its web search answered by `replies` (a function of
    the request's keyword arguments); `requests` records them."""
    state = {"requests": [], "replies": lambda **kwargs: answer("Nothing found.")}

    class Client:
        class responses:
            @staticmethod
            def create(**kwargs):
                state["requests"].append(kwargs)
                return state["replies"](**kwargs)

    for name in AZURE:
        monkeypatch.setenv(name, "https://azure.example" if name.endswith("ENDPOINT") else "deployment")
    monkeypatch.setattr(azure_web, "_client", Client)
    return state


def test_a_search_gives_the_pages_found_with_their_snippets(azure):
    azure["replies"] = lambda **kwargs: answer(results=[
        {"type": "text_result", "title": "Pricing 2026", "url": "https://a.example/p?utm_source=openai", "snippet": "Plans  from\n$49." + "x" * 900},
        {"type": "text_result", "title": "", "url": "https://b.example/"},
        {"type": "text_result", "title": "Again", "url": "https://a.example/p"},
        {"type": "text_result", "title": "No address"},
    ])

    hits = azure_web.search("scheduling software prices")

    assert [(hit.title, hit.url) for hit in hits] == [("Pricing 2026", "https://a.example/p"), ("https://b.example/", "https://b.example/")]
    assert hits[0].content == ("Plans from $49." + "x" * 900)[:700]
    request = azure["requests"][0]
    assert request["model"] == "deployment" and request["tools"] == [{"type": "web_search"}]
    assert request["reasoning"] == {"effort": "low"}
    assert request["include"] == ["web_search_call.results"]
    assert request["input"] == "Search the web for: scheduling software prices"


def test_without_raw_results_a_search_takes_the_pages_the_answer_cites(azure):
    text = "Intro.\n- SimplePractice costs $49 a month ([schedulingkit.com](https://s.example/p?utm_source=openai)).\nMore."
    start = text.index("(")
    azure["replies"] = lambda **kwargs: answer(text, notes=[
        {"type": "url_citation", "title": "SimplePractice pricing", "url": "https://s.example/p?utm_source=openai", "start_index": start, "end_index": start + 40},
    ])

    hits = azure_web.search("prices")

    assert [(hit.title, hit.url, hit.content) for hit in hits] == [
        ("SimplePractice pricing", "https://s.example/p", "SimplePractice costs $49 a month"),
    ]


REPORT = (
    "Tools cost $50 a month ([prices.example](https://prices.example/a?utm_source=openai)). "
    "Margins run 70% ([cloud.example](https://cloud.example/m), [prices.example](https://prices.example/a)). "
    "See [the survey](https://survey.example)."
)


def test_a_research_report_cites_its_sources_by_number(azure):
    azure["replies"] = lambda **kwargs: answer(REPORT, searches=5, notes=[
        {"type": "url_citation", "title": "Scheduling prices 2026", "url": "https://prices.example/a?utm_source=openai"},
    ])

    report = azure_web.research("What do the tools cost?")

    assert report.content == "Tools cost $50 a month [1]. Margins run 70% [2][1]. See [3]."
    assert report.sources == [
        ("Scheduling prices 2026", "https://prices.example/a"),
        ("cloud.example", "https://cloud.example/m"),
        ("the survey", "https://survey.example"),
    ]
    assert (report.credits, report.searches) == (0, 5)
    assert "at most 350 words" in azure["requests"][0]["input"]
    assert "text" not in azure["requests"][0]


def test_a_profile_fills_its_fields_with_numbered_citations(azure):
    fields = {key: f"{key} ([site](https://{key}.example))" for key in COMPANY_SCHEMA["properties"]}
    azure["replies"] = lambda **kwargs: answer(json.dumps(fields), calls=3)

    report = azure_web.research("Profile Klara.", COMPANY_SCHEMA)

    assert report.content["pricing"] == "pricing [3]"
    assert len(report.sources) == len(COMPANY_SCHEMA["properties"])
    assert report.searches == 3  # counted from the calls when Azure does not report them
    schema = azure["requests"][0]["text"]["format"]
    assert schema["type"] == "json_schema" and schema["strict"] is True
    assert schema["schema"]["required"] == list(COMPANY_SCHEMA["properties"])
    assert schema["schema"]["additionalProperties"] is False


@pytest.mark.parametrize(("reply", "reason"), [
    (lambda **kwargs: answer("not json"), "profile could not be read"),
    (lambda **kwargs: answer(""), "gave no answer"),
])
def test_research_that_cannot_be_read_fails(azure, reply, reason):
    azure["replies"] = reply

    with pytest.raises(SearchFailed, match=reason):
        azure_web.research("Profile Klara.", COMPANY_SCHEMA)


def test_a_failed_or_unconfigured_call_fails_cleanly(azure, monkeypatch):
    def fail(**kwargs):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://azure.example"))

    azure["replies"] = fail
    with pytest.raises(SearchFailed, match=r"web search failed \(APIConnectionError\)"):
        azure_web.search("prices")
    hits, note = azure_web.search_all(["one", "two"])
    assert hits == [] and note == "The web search failed: Azure OpenAI's web search failed (APIConnectionError)."
    assert isinstance(azure_web.research_all({"a": ("task", None)})["a"], SearchFailed)

    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT")
    assert not azure_web.available()
    with pytest.raises(SearchFailed, match="not set up"):
        azure_web.research("A question")


def test_searches_and_research_run_together(azure):
    def reply(**kwargs):
        query = kwargs["input"]
        if "broken" in query:
            raise openai.APIConnectionError(request=httpx.Request("POST", "https://azure.example"))
        return answer("A fact ([s](https://s.example)).", results=[{"title": query, "url": f"https://{len(query)}.example"}])

    azure["replies"] = reply

    hits, note = azure_web.search_all(["Search one", "broken search"])
    assert [hit.url for hit in hits] == [f"https://{len('Search the web for: Search one')}.example"] and note is None
    reports = azure_web.research_all({"a": ("A task", None), "b": ("broken", None)})
    assert reports["a"].content == "A fact [1]." and isinstance(reports["b"], SearchFailed)
    assert azure_web.search_all([]) == ([], None) and azure_web.research_all({}) == {}


def test_the_client_is_built_once_for_the_v1_endpoint(monkeypatch):
    for name in AZURE:
        monkeypatch.setenv(name, "https://azure.example/" if name.endswith("ENDPOINT") else "key")
    monkeypatch.setattr(azure_web, "_client", None)
    azure_web._azure.cache_clear()
    built = azure_web._azure("https://azure.example/", "key")
    assert str(built.base_url) == "https://azure.example/openai/v1/"
    assert azure_web._azure("https://azure.example/", "key") is built


# ---- Choosing where research runs ----

def test_azure_is_the_default_and_tavily_is_used_when_asked(monkeypatch):
    assert providers.default() is None and providers.chosen("tavily") is None
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    assert providers.chosen(None) == "tavily" and providers.chosen("azure") == "tavily"
    for name in AZURE:
        monkeypatch.setenv(name, "set")
    assert providers.default() == "azure"
    assert providers.chosen(None) == "azure" and providers.chosen("tavily") == "tavily"


def test_a_brief_is_researched_where_the_founder_chose(fake_llm, azure, monkeypatch):
    searched = []
    monkeypatch.setattr(brief, "search_all", lambda queries, provider: (searched.append(provider), ([], None))[1])
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    client.post("/brief/prepare", json={"prompt": "An idea."})
    prepared = client.post("/brief/prepare", json={"prompt": "An idea.", "research_provider": "tavily"}).json()

    assert searched == ["azure", "tavily"]
    assert prepared["provider"] == "Tavily"


def test_deep_research_on_azure_counts_its_searches(fake_llm, azure):
    def reply(**kwargs):
        if "text" in kwargs:
            fields = {key: f"{key} ([klara](https://klara.example))" for key in COMPANY_SCHEMA["properties"]}
            return answer(json.dumps(fields), searches=2)
        return answer("Grows 8% ([report](https://report.example)).", searches=3)

    azure["replies"] = reply

    result = client.post("/evaluate", json={"prompt": "An idea.", "deep_research": True}).json()

    research = result["research"]
    assert sorted(research["areas"]) == ["finance", "marketing", "risk", "technical"]
    assert research["areas"]["finance"] == "Grows 8% [1]."
    assert research["companies"][0]["pricing"] == "pricing [2]"
    assert (research["credits"], research["searches"], research["providers"]) == (0, 4 * 3 + 2, ["Azure OpenAI"])
    with client.stream("POST", "/evaluate/stream", json={"prompt": "An idea.", "deep_research": True}) as response:
        text = response.read().decode()
    assert "(2 sources, 14 web searches)" in text and '"provider": "Azure OpenAI"' in text


def test_each_provider_runs_its_own_searches(azure):
    azure["replies"] = lambda **kwargs: answer(results=[{"title": "Page", "url": "https://page.example"}])

    hits, note = providers.search_all(["prices"], "azure")

    assert [hit.url for hit in hits] == ["https://page.example"] and note is None
    assert providers.research_all({}, "tavily") == {}


def test_a_report_ends_as_a_report(azure):
    azure["replies"] = lambda **kwargs: answer(
        "Tools cost $50 a month ([p](https://p.example)).\n\nPilots convert at 40%.\n\n"
        "Sources: CDC, industry surveys.\nMore of them.\n\nIf you want, I'll turn this into a plan."
    )

    report = azure_web.research("What do the tools cost?")

    assert report.content == "Tools cost $50 a month [1].\n\nPilots convert at 40%."
    assert "no offer of further help" in azure["requests"][0]["input"]
    assert azure_web._finished("Would you like more?") == "Would you like more?"  # a report that is only a question stays
