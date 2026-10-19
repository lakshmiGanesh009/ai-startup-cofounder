"""Web search for preparing a brief, through Tavily (https://tavily.com).

Search is optional. Without TAVILY_API_KEY the brief is prepared without it,
and a failed search never fails the request: the brief goes ahead without the
results, saying why.
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

from config import SEARCH_TIMEOUT

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"

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
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise SearchFailed("no TAVILY_API_KEY is set")
    body = {"query": query, "search_depth": "basic", "max_results": RESULTS_PER_SEARCH, "topic": "general"}
    try:
        with httpx.Client(transport=_transport, timeout=SEARCH_TIMEOUT) as client:
            response = client.post(TAVILY_URL, json=body, headers={"Authorization": f"Bearer {key}"})
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
            logger.warning("Search for %r failed: %s", query, error)
            return error

    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
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
