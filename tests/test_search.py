"""Tests for the web search behind a brief's research (search.py), with Tavily
answered by a mock transport."""

import json
import re

import httpx
import pytest

import search
from search import Hit, SearchFailed, search_all, search_configured


def _tavily(monkeypatch, answer):
    """Answer every Tavily request with `answer(request)`, and record the requests."""
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return answer(request)

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(search, "_transport", httpx.MockTransport(handle))
    return requests


def _results(*urls):
    return httpx.Response(200, json={"results": [
        {"title": f"Page {url}", "url": url, "content": f"What {url}   says\nabout it."} for url in urls
    ]})


def test_a_search_sends_the_query_and_reads_the_results(monkeypatch):
    requests = _tavily(monkeypatch, lambda request: httpx.Response(200, json={"results": [
        {"title": "AMA survey", "url": "https://ama.example/survey", "content": "Physicians  in\nprivate practice " + "x" * 900},
        {"title": "", "url": "https://untitled.example"},
        {"title": "[PDF] Practice characteristics", "url": "https://ama.example/2024.pdf", "content": "Tables."},
        {"title": "No address"},
    ]}))

    hits = search.search("clinic scheduling market size")

    assert hits[0] == Hit("AMA survey", "https://ama.example/survey", ("Physicians in private practice " + "x" * 900)[:700])
    assert hits[1] == Hit("https://untitled.example", "https://untitled.example", "")
    assert hits[2] == Hit("Practice characteristics", "https://ama.example/2024.pdf", "Tables.")
    assert len(hits) == 3  # a result without an address is dropped
    request = requests[0]
    assert str(request.url) == "https://api.tavily.com/search"
    assert request.headers["Authorization"] == "Bearer tvly-test"
    assert json.loads(request.content) == {
        "query": "clinic scheduling market size", "search_depth": "basic", "max_results": 5, "topic": "general",
    }


@pytest.mark.parametrize(("status", "reason"), [
    (401, "Tavily refused the API key; check TAVILY_API_KEY"),
    (429, "Tavily's rate limit was reached; try again in a minute"),
    (432, "the Tavily plan's monthly limit is used up"),
    (433, "the Tavily pay-as-you-go limit is reached"),
    (500, "Tavily answered 500"),
])
def test_a_refused_search_says_why(monkeypatch, status, reason):
    _tavily(monkeypatch, lambda request: httpx.Response(status, json={"detail": "no"}))

    with pytest.raises(SearchFailed, match=re.escape(reason)):
        search.search("anything")


def test_an_unreachable_or_unreadable_search_fails_cleanly(monkeypatch):
    def unreachable(request):
        raise httpx.ConnectTimeout("too slow", request=request)

    _tavily(monkeypatch, unreachable)
    with pytest.raises(SearchFailed, match=r"Tavily could not be reached \(ConnectTimeout\)"):
        search.search("anything")

    _tavily(monkeypatch, lambda request: httpx.Response(200, content=b"<html>not json</html>"))
    with pytest.raises(SearchFailed, match="could not be read"):
        search.search("anything")


def test_without_a_key_there_is_no_search(monkeypatch):
    assert not search_configured()
    with pytest.raises(SearchFailed, match="no TAVILY_API_KEY"):
        search.search("anything")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    assert search_configured()


def test_searches_run_together_and_each_page_is_kept_once(monkeypatch):
    pages = {"market": ["https://a.example", "https://b.example"], "prices": ["https://b.example", "https://c.example"]}
    _tavily(monkeypatch, lambda request: _results(*pages[json.loads(request.content)["query"]]))

    hits, note = search_all(["market", "prices"])

    assert [hit.url for hit in hits] == ["https://a.example", "https://b.example", "https://c.example"]
    assert note is None
    assert search_all([]) == ([], None)


def test_one_failed_search_is_skipped_but_all_failing_says_why(monkeypatch):
    _tavily(monkeypatch, lambda request: (
        _results("https://a.example") if json.loads(request.content)["query"] == "works" else httpx.Response(429)
    ))
    hits, note = search_all(["works", "limited"])
    assert [hit.url for hit in hits] == ["https://a.example"] and note is None

    _tavily(monkeypatch, lambda request: httpx.Response(432))
    hits, note = search_all(["one", "two"])
    assert hits == []
    assert note == "The web search failed: the Tavily plan's monthly limit is used up."


def test_the_monitor_counts_tavilys_searches_and_the_credits_they_spend(monkeypatch):
    from monitor import monitor

    _tavily(monkeypatch, lambda request: _results("https://a.example"))
    search.search("clinic scheduling")
    _tavily(monkeypatch, lambda request: httpx.Response(401, json={"detail": {"error": "Unauthorized"}}))
    with pytest.raises(SearchFailed):
        search.search("clinic scheduling")

    (tavily,) = monitor.usage()
    used = tavily.services[0]
    assert (tavily.provider, used.service, used.calls, used.failed, used.credits) == ("tavily", "web search", 2, 1, 1)
    assert "API key" in (used.last_failure or "")
