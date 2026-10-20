"""Web search and research through Tavily (https://tavily.com): quick searches
for preparing a brief, and research tasks for the specialists' deep research.

Both are optional. Without TAVILY_API_KEY a brief is prepared without search
and the team works without deep research, and a failed search or research
task never fails the request: the work goes ahead without it, saying why.
"""

import logging
import os
import re
import time
from dataclasses import dataclass

import httpx
from langchain_core.runnables.config import ContextThreadPoolExecutor

from config import RESEARCH_TIMEOUT, SEARCH_TIMEOUT

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
RESEARCH_URL = "https://api.tavily.com/research"

# Tavily's research model: "mini" for targeted research, at 4-110 credits a
# task (measured: 20-80); "pro" costs 15-250.
RESEARCH_MODEL = "mini"
# Seconds between checks on a research task; set to 0 by tests.
POLL_SECONDS = 3.0

# Results per search, and how much of each result's text the model reads.
RESULTS_PER_SEARCH = 5
CONTENT_CHARS = 700

# Set by tests to answer requests without the network.
_transport: httpx.BaseTransport | None = None


class SearchFailed(Exception):
    """A search could not be made, or Tavily refused it; the message says why."""


@dataclass(frozen=True)
class Hit:
    """One search result: the page and the passage of it that matched."""

    title: str
    url: str
    content: str


def search_configured() -> bool:
    """Whether a search key is set, so a brief can be researched."""
    return bool(os.getenv("TAVILY_API_KEY"))


def _key() -> str:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise SearchFailed("no TAVILY_API_KEY is set")
    return key


def _refusal(response: httpx.Response) -> str:
    reasons = {
        401: "Tavily refused the API key; check TAVILY_API_KEY",
        429: "Tavily's rate limit was reached; try again in a minute",
        432: "the Tavily plan's monthly limit is used up",
        433: "the Tavily pay-as-you-go limit is reached",
    }
    return reasons.get(response.status_code, f"Tavily answered {response.status_code}")


def search(query: str) -> list[Hit]:
    """The top results for `query`. Raises SearchFailed when there is no key,
    Tavily cannot be reached in time, or it refuses the request."""
    body = {"query": query, "search_depth": "basic", "max_results": RESULTS_PER_SEARCH, "topic": "general"}
    try:
        with httpx.Client(transport=_transport, timeout=SEARCH_TIMEOUT) as client:
            response = client.post(TAVILY_URL, json=body, headers={"Authorization": f"Bearer {_key()}"})
    except httpx.HTTPError as error:
        raise SearchFailed(f"Tavily could not be reached ({type(error).__name__})") from error
    if response.status_code != 200:
        raise SearchFailed(_refusal(response))
    try:
        results = response.json().get("results") or []
    except ValueError as error:
        raise SearchFailed("Tavily's answer could not be read") from error
    return [
        Hit(title=_title(result), url=result["url"],
            content=" ".join((result.get("content") or "").split())[:CONTENT_CHARS])
        for result in results
        if result.get("url")
    ]


def _title(result: dict) -> str:
    """A result's title without the "[PDF]" Tavily puts before a document's,
    which would read like a citation; its address if it has none."""
    title = re.sub(r"^\s*\[PDF\]\s*", "", result.get("title") or "").strip()
    return title or result["url"]


def search_all(queries: list[str]) -> tuple[list[Hit], str | None]:
    """Run the searches at the same time and pool their results, each page once.

    Returns the results, and why there are none when every search failed (a
    search that fails while others succeed is only logged).
    """
    if not queries:
        return [], None

    def run(query: str) -> list[Hit] | SearchFailed:
        try:
            return search(query)
        except SearchFailed as error:
            logger.warning("A search failed: %s", error)  # not the query: it comes from the brief
            return error

    # At once; each thread keeps the request's context, so its log lines name the request.
    with ContextThreadPoolExecutor(max_workers=len(queries)) as pool:
        outcomes = list(pool.map(run, queries))
    hits: dict[str, Hit] = {}
    for outcome in outcomes:
        if not isinstance(outcome, SearchFailed):
            for hit in outcome:
                hits.setdefault(hit.url, hit)
    failures = [outcome for outcome in outcomes if isinstance(outcome, SearchFailed)]
    if len(failures) == len(outcomes):
        return [], f"The web search failed: {failures[0]}."
    return list(hits.values()), None


@dataclass(frozen=True)
class Report:
    """A finished research task: a report citing its sources as [n] (or, with an
    output schema, its fields), the sources those numbers refer to, 1 first,
    and what it cost: Tavily credits, or the web searches Azure OpenAI ran."""

    content: str | dict
    sources: list[tuple[str, str]]
    credits: int
    searches: int = 0


# The reference list a report ends with, which repeats its sources.
_REFERENCES = re.compile(
    r"\n+(?:-{3,}\s*\n+)?#{0,6}\s*\**\s*(?:sources|references)\s*:?\s*\**\s*\n(?:\s*[-*]?\s*\[\d+\].*(?:\n|$))+\s*$",
    re.IGNORECASE,
)


def research(task: str, schema: dict | None = None) -> Report:
    """Run one Tavily research task and wait for its report.

    Raises SearchFailed when there is no key, Tavily refuses the task or cannot
    be reached, the task fails, or it takes longer than RESEARCH_TIMEOUT.
    """
    body: dict = {"input": task, "model": RESEARCH_MODEL, "citation_format": "numbered", "output_length": "short"}
    if schema:
        body["output_schema"] = schema
    headers = {"Authorization": f"Bearer {_key()}"}
    deadline = time.monotonic() + RESEARCH_TIMEOUT
    try:
        with httpx.Client(transport=_transport, timeout=SEARCH_TIMEOUT) as client:
            created = client.post(RESEARCH_URL, json=body, headers=headers)
            if created.status_code not in (200, 201):
                raise SearchFailed(_refusal(created))
            task_url = f"{RESEARCH_URL}/{created.json()['request_id']}"
            while True:
                if time.monotonic() > deadline:
                    raise SearchFailed(f"Tavily's research took longer than {RESEARCH_TIMEOUT:.0f} s")
                time.sleep(POLL_SECONDS)
                answer = client.get(task_url, params={"include_usage": "true"}, headers=headers)
                if answer.status_code == 202:
                    continue
                if answer.status_code != 200:
                    raise SearchFailed(_refusal(answer))
                data = answer.json()
                if data.get("status") == "failed":
                    raise SearchFailed("Tavily's research task failed")
                if data.get("status") == "completed":
                    break
    except httpx.HTTPError as error:
        raise SearchFailed(f"Tavily could not be reached ({type(error).__name__})") from error
    except (ValueError, KeyError) as error:
        raise SearchFailed("Tavily's answer could not be read") from error
    content = data.get("content") or ""
    if isinstance(content, str):
        content = _REFERENCES.sub("", content).strip()
    sources = [(_title(source), source["url"]) for source in data.get("sources") or [] if source.get("url")]
    return Report(content=content, sources=sources, credits=int((data.get("usage") or {}).get("credits") or 0))


def research_all(tasks: dict[str, tuple[str, dict | None]]) -> dict[str, Report | SearchFailed]:
    """Run research tasks at the same time: each key gets its report, or the
    reason it failed (logged)."""
    if not tasks:
        return {}

    def run(key: str) -> Report | SearchFailed:
        try:
            return research(*tasks[key])
        except SearchFailed as error:
            logger.warning("Research for %s failed: %s", key, error)
            return error

    with ContextThreadPoolExecutor(max_workers=len(tasks)) as pool:
        return dict(zip(tasks, pool.map(run, list(tasks))))
