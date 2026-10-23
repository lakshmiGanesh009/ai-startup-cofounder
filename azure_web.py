"""Web search and research with Azure OpenAI's own web search: the Responses
API's web_search tool, which searches Bing, on the deployment the team already
runs, through Azure's v1 endpoint. It is the default; Tavily (search.py) is for
demanding tasks.

It answers in Tavily's shapes, so the rest of the app need not know which ran:
a search gives the pages found, with their snippets; a research task gives a
short report, or the fields of a schema, whose citations (markdown links in
the model's text) become numbered [n], with the sources they number. Each call
can run several Bing searches, which Azure bills per search; the count comes
back so the page can show it. Measured on gpt-5-mini at low reasoning: 11-15 s
a call. Azure's Data Protection Addendum does not cover what is searched.
"""

import json
import logging
import os
import re
from functools import cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import openai
from langchain_core.runnables.config import ContextThreadPoolExecutor

from config import LLM_MAX_RETRIES, LLM_TIMEOUT
from monitor import monitor
from search import CONTENT_CHARS, Hit, Report, SearchFailed

logger = logging.getLogger(__name__)

# Web search does not run at "minimal" reasoning on gpt-5 models.
EFFORT = "low"
REPORT_WORDS = 350
# A brief waits for the slowest of its searches, which answer in 11-30 s, so
# one that stalls is given up on sooner than the model's calls are: once
# retried, then left out. A team run's research keeps the model's timeout.
SEARCH_TIMEOUT = 45.0
SEARCH_RETRIES = 1

_VARIABLES = ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME")

# Set by tests: an object with responses.create(), in place of the real client.
_client = None


def available() -> bool:
    """Whether Azure OpenAI is set up, so it can search the web."""
    return all(os.getenv(name) for name in _VARIABLES)


def search_deployment() -> str:
    """The deployment the web search runs on: AZURE_OPENAI_SEARCH_DEPLOYMENT_NAME,
    so its burst of searches can draw on a quota of its own, else the team's."""
    return os.getenv("AZURE_OPENAI_SEARCH_DEPLOYMENT_NAME") or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]


@cache
def _azure(endpoint: str, key: str, timeout: float = LLM_TIMEOUT, retries: int = LLM_MAX_RETRIES) -> openai.OpenAI:
    return openai.OpenAI(base_url=f"{endpoint.rstrip('/')}/openai/v1/", api_key=key, timeout=timeout, max_retries=retries)


def _create(service: str, timeout: float = LLM_TIMEOUT, retries: int = LLM_MAX_RETRIES, **kwargs):
    """One Responses API call with web search, counted on the Monitor under
    `service` ("web search" or "research"), given up on after `timeout` seconds
    and `retries` more tries; SearchFailed if it cannot be made."""
    if not available():
        raise SearchFailed("Azure OpenAI is not set up")
    client = _client or _azure(os.environ["AZURE_OPENAI_ENDPOINT"], os.environ["AZURE_OPENAI_API_KEY"], timeout, retries)
    try:
        with monitor.calling("azure", service) as call:
            response = client.responses.create(
                model=search_deployment(),
                tools=[{"type": "web_search"}],
                reasoning={"effort": EFFORT},
                **kwargs,
            )
            usage = getattr(response, "usage", None)
            call.used(getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0)
            return response
    except openai.OpenAIError as error:
        raise SearchFailed(f"Azure OpenAI's web search failed ({type(error).__name__})") from error


def _plain(value) -> dict:
    """An item of the response as a dict, whether the SDK typed it or not."""
    if isinstance(value, dict):
        return value
    return value.model_dump() if hasattr(value, "model_dump") else vars(value)


def _clean(url: str) -> str:
    """An address without the tracking the model adds to links (utm_source=openai)."""
    parts = urlsplit(url)
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query) if not key.startswith("utm_")])
    return urlunsplit(parts._replace(query=query))


def _searches(response) -> int:
    """How many Bing searches the call ran, as Azure bills them."""
    usage = _plain(getattr(response, "tool_usage", None) or {})
    count = _plain(usage.get("web_search") or {}).get("num_requests")
    if count is None:
        count = sum(1 for item in response.output if getattr(item, "type", "") == "web_search_call")
    return int(count)


def _message(response) -> tuple[str, list[dict]]:
    """The model's answer, and the citations in it."""
    for item in response.output:
        if getattr(item, "type", "") == "message":
            for part in item.content:
                if getattr(part, "type", "") == "output_text":
                    return part.text, [_plain(note) for note in getattr(part, "annotations", None) or []]
    return "", []


def search(query: str) -> list[Hit]:
    """The pages a web search for `query` found, with their snippets."""
    response = _create("web search", SEARCH_TIMEOUT, SEARCH_RETRIES,
                       input=f"Search the web for: {query}", include=["web_search_call.results"])
    hits: dict[str, Hit] = {}
    for item in response.output:
        if getattr(item, "type", "") != "web_search_call":
            continue
        for result in getattr(item, "results", None) or []:
            found = _plain(result)
            if found.get("url"):
                url = _clean(found["url"])
                snippet = " ".join((found.get("snippet") or "").split())[:CONTENT_CHARS]
                hits.setdefault(url, Hit(title=(found.get("title") or url).strip(), url=url, content=snippet))
    if not hits:  # no raw results: the pages its answer cites, with the line citing each
        text, notes = _message(response)
        for note in notes:
            if note.get("url"):
                url = _clean(note["url"])
                line = text[: note.get("start_index", 0)].rsplit("\n", 1)[-1]
                content = _LINK.sub(r"\1", line).strip(" -([")[:CONTENT_CHARS]
                hits.setdefault(url, Hit(title=(note.get("title") or url).strip(), url=url, content=content))
    return list(hits.values())


def search_all(queries: list[str]) -> tuple[list[Hit], str | None]:
    """Run the searches at the same time and pool their results, each page once;
    with why there are none when every search failed."""
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


# A citation as the model writes it: a markdown link, "[ama-assn.org](https://...)".
_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^\s)]+)\)")
# Citations left in brackets once numbered: "([1])" or "([1], [2])".
_BRACKETED = re.compile(r"\(\s*((?:\[\d+\][\s,;]*)+)\)")


def _cited(text: str, titles: dict[str, str], sources: list[tuple[str, str]]) -> str:
    """The text with each cited link as [n], numbering new pages onto `sources`."""
    numbers = {url: number for number, (_, url) in enumerate(sources, start=1)}

    def cite(match: re.Match) -> str:
        url = _clean(match[2])
        if url not in numbers:
            sources.append((titles.get(url) or match[1] or url, url))
            numbers[url] = len(sources)
        return f"[{numbers[url]}]"

    text = _LINK.sub(cite, text)
    return _BRACKETED.sub(lambda match: "".join(re.findall(r"\[\d+\]", match[1])), text)


# What a chat answer ends with that a report should not: an offer of more help,
# a question to the reader, or a list of the sources it has already cited.
_TRAILING = re.compile(
    r"\n+\s*(?:if you(?:'d)? (?:want|like)|would you like|want me to|do you want|let me know|"
    r"sources?\s*:)[^\n]*(?:\n[^\n]+)*\s*$",
    re.IGNORECASE,
)


def _finished(text: str) -> str:
    """A report without the chat that can close it, paragraph by paragraph."""
    text = text.strip()
    while (trimmed := _TRAILING.sub("", text).strip()) != text:
        text = trimmed
    return text


def _strict(schema: dict) -> dict:
    """A schema as Azure's strict structured output needs it: every field required, no others."""
    return {
        "type": "object",
        "properties": schema["properties"],
        "required": list(schema["properties"]),
        "additionalProperties": False,
    }


def research(task: str, schema: dict | None = None) -> Report:
    """Research `task` on the web and report it with numbered citations: a short
    report, or with `schema`, its fields."""
    if schema:
        prompt = (
            f"{task}\n\nSearch the web, then fill in every field in one or two sentences with "
            "specific figures, citing each source inline."
        )
        response = _create(
            "research",
            input=prompt,
            text={"format": {"type": "json_schema", "name": "profile", "schema": _strict(schema), "strict": True}},
        )
    else:
        prompt = (
            f"{task}\n\nSearch the web, then write a short report of at most {REPORT_WORDS} words with "
            "specific figures, citing each source inline where you use it. Write it as a finished "
            "report: no list of sources at the end, no questions to the reader, and no offer of "
            "further help."
        )
        response = _create("research", input=prompt)
    text, notes = _message(response)
    if not text.strip():
        raise SearchFailed("Azure OpenAI's research gave no answer")
    titles = {_clean(note["url"]): note.get("title") or "" for note in notes if note.get("url")}
    sources: list[tuple[str, str]] = []
    if schema:
        try:
            fields = json.loads(text)
        except ValueError as error:
            raise SearchFailed("Azure OpenAI's profile could not be read") from error
        content: str | dict = {key: _cited(str(value), titles, sources) for key, value in fields.items()}
    else:
        content = _finished(_cited(text, titles, sources))
    return Report(content=content, sources=sources, credits=0, searches=_searches(response))


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
