"""Look-ups: official figures and competitors' own pages, read through MCP
servers, for the team to work from.

- FRED (fred_server.py, our own, started as a subprocess and spoken to over
  stdio): after the plan, the Chief of Staff names a few FRED searches for the
  figures the venture turns on. Code takes the most used current series each
  search finds, adds the 10-year Treasury yield and consumer prices, which every
  plan needs, reads a year of each, and works out its latest value and its
  change over the year. Every specialist reads them, citing [FRED · DGS10].
  FRED is free; without FRED_API_KEY the step is skipped.
- Tavily (its hosted MCP server, over HTTPS, the key in a header): with deep
  research on Tavily, each competitor's own pricing page is found and read
  (deep_research.py): about a credit a search, and one for every five pages.

A look-up that fails is left out, with a note, and never fails the request.
"""

import asyncio
import logging
import math
import os
import re
import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

import httpx2
from langchain_core.messages import HumanMessage, SystemMessage
from mcp import Client
from mcp.client.stdio import StdioServerParameters, get_default_environment
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from pydantic import BaseModel, Field

from agents.chief_of_staff import structured_invoke
from config import LOOKUP_TIMEOUT, TAVILY_MCP_URL
from guardrails import RULES, fence
from llm import CHIEF, LLM_ERRORS
from metrics import track
from monitor import Provider, Service, monitor
from state import EconomicData, Figure, RequestContext, WorkflowState

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
MAX_SEARCHES = 4
# Read for every plan, whatever the Chief of Staff searches for, and why.
CORE = {
    "DGS10": "The usual risk-free rate a discount rate starts from.",
    "CPIAUCSL": "Its change over the year is consumer inflation.",
}
# A series whose latest value is older than this is not current, and one whose
# title covers less of a search than this does not answer it.
STALE = timedelta(days=760)
MATCH = 0.6
# The series found for each search that the Chief of Staff chooses among.
CANDIDATES = 6
PAGE_CHARACTERS = 1_200


class LookupFailed(Exception):
    """An MCP server could not be reached, or a tool failed, and why."""


def fred_configured() -> bool:
    return bool(os.getenv("FRED_API_KEY", "").strip())


def tavily_configured() -> bool:
    return bool(os.getenv("TAVILY_API_KEY", "").strip())


# ---- The servers ----

def _fred() -> StdioServerParameters:
    """Our FRED server, as a subprocess of the API; it gets the key and nothing else of the API's settings."""
    return StdioServerParameters(
        command=sys.executable, args=["-m", "fred_server"], cwd=str(HERE),
        env={**get_default_environment(), "FRED_API_KEY": os.getenv("FRED_API_KEY", "").strip()},
    )


def _tavily():
    """Tavily's hosted MCP server, the key in a header rather than the address."""
    key = os.getenv("TAVILY_API_KEY", "").strip()
    client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {key}"}, timeout=LOOKUP_TIMEOUT)
    return streamable_http_client(TAVILY_MCP_URL, http_client=client)


# What each look-up connects to; tests put servers of their own here.
SERVERS: dict[str, Callable[[], Any]] = {"fred": _fred, "tavily": _tavily}


async def _call(client: Client, tool: str, arguments: dict) -> Any:
    """A tool's answer: its structured content if it has some, else its text."""
    result = await client.call_tool(tool, arguments, read_timeout_seconds=LOOKUP_TIMEOUT)
    text = "\n".join(part.text for part in result.content if isinstance(part, TextContent) and part.text)
    if result.is_error:
        raise LookupFailed(text or f"{tool} failed.")
    data = result.structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]
    return data if data is not None else text


def _cause(error: BaseException) -> BaseException:
    """The error itself, out of the groups the MCP client's tasks wrap it in."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = next((each for each in error.exceptions if isinstance(each, LookupFailed)), error.exceptions[0])
    return error


def _run(work, what: str, provider: Provider, service: Service):
    """Run a look-up from a graph node's thread, within its time, counted on the Monitor."""
    try:
        with monitor.calling(provider, service):
            return asyncio.run(asyncio.wait_for(work, LOOKUP_TIMEOUT * 3))
    except Exception as error:
        cause = _cause(error)
        if isinstance(cause, LookupFailed):
            raise cause from None
        if isinstance(cause, (TimeoutError, asyncio.TimeoutError)):
            raise LookupFailed(f"{what} took longer than {LOOKUP_TIMEOUT * 3:.0f} s.") from None
        # The server would not start, or the connection broke.
        raise LookupFailed(f"{what} could not be reached ({type(cause).__name__}).") from error


# ---- FRED ----

class FredSearches(BaseModel):
    searches: list[str] = Field(
        default_factory=list,
        description=f"At most {MAX_SEARCHES} searches of FRED, a few plain words each; none if no official figure bears on it.",
    )


class FredPick(BaseModel):
    id: str = Field(description="The series' id, exactly as listed.")
    why: str = Field(description="What the team reads it for, in one short sentence.")


class FredPicks(BaseModel):
    picks: list[FredPick] = Field(
        default_factory=list,
        description=f"At most {MAX_SEARCHES} of the listed series; none rather than one that does not fit.",
    )


_FRED_PROMPT = (
    "You are the Chief of Staff of a startup founding team. Before the specialists start, the team "
    "looks up official economic data on FRED, the St. Louis Fed's database of US and international "
    f"statistics. Name at most {MAX_SEARCHES} searches for the figures this venture's decision turns "
    "on: prices and wages in its market, the spending or demand behind it, its customers' industry, "
    "its region. Write each as FRED titles its series, in a few plain words, such as \"average hourly "
    "earnings health care\" or \"producer price index dental offices\". The 10-year Treasury yield and "
    "consumer prices are always read; do not ask for them. Name none if no official figure bears on "
    "the decision."
)


def _current(series: dict, taken: set[str]) -> bool:
    try:
        latest = date.fromisoformat(str(series.get("observation_end", ""))[:10])
    except ValueError:
        return False
    return (series["id"] not in taken and "discontinued" not in series.get("title", "").lower()
            and latest >= date.today() - STALE)


_FILLER = {"the", "and", "for", "all", "rate", "total"}


def _stems(text: str) -> set[str]:
    return {word[:5] for word in re.findall(r"[a-z]+", text.lower()) if len(word) > 2 and word not in _FILLER}


def match(series: dict, text: str) -> float:
    """How much of a search a series' title covers, 0 to 1: FRED's own search
    ranks loosely ("average hourly earnings health care" finds a work-from-home
    rate first)."""
    wanted = _stems(text)
    return len(wanted & _stems(series.get("title", ""))) / len(wanted) if wanted else 0.0


def best(found: list[dict], text: str, taken: set[str]) -> dict | None:
    """The current series that covers most of the search, the most used of
    those; none that covers less than MATCH of it."""
    scored = [(match(series, text), series.get("popularity") or 0, -order, series)
              for order, series in enumerate(found) if _current(series, taken)]
    scored = [entry for entry in scored if entry[0] >= MATCH]
    return max(scored, key=lambda entry: entry[:3])[3] if scored else None


def figure(data: dict, why: str = "") -> Figure | None:
    """A series' latest value and its change over the year, worked out here,
    not by a model: in points for a rate, else in per cent."""
    observations = data.get("observations") or []
    if not observations:
        return None
    series, latest = data["series"], observations[-1]
    when = date.fromisoformat(latest["date"])
    earlier = [row for row in observations if date.fromisoformat(row["date"]) <= when - timedelta(days=358)]
    year_ago = earlier[-1]["value"] if earlier else None
    change = ""
    if year_ago is not None:
        if "percent" in series["units"].lower():
            moved = latest["value"] - year_ago
            change = f"{'up' if moved >= 0 else 'down'} {abs(moved):.2f} points"
        elif year_ago:
            moved = (latest["value"] / year_ago - 1) * 100
            change = f"{'up' if moved >= 0 else 'down'} {abs(moved):.1f}%"
    return Figure(id=series["id"], title=series["title"], units=series["units"], frequency=series["frequency"],
                  date=latest["date"], value=latest["value"], year_ago=year_ago, change=change, why=why,
                  link=data.get("link") or f"https://fred.stlouisfed.org/series/{series['id']}")


async def _search(searches: list[str]) -> dict[str, list[dict] | None]:
    """What FRED finds for each search; None for one that failed."""
    async with Client(SERVERS["fred"](), read_timeout_seconds=LOOKUP_TIMEOUT) as client:
        found = await asyncio.gather(*(_call(client, "search_series", {"text": text, "limit": 20}) for text in searches),
                                     return_exceptions=True)
    return {text: None if isinstance(series, BaseException) else series for text, series in zip(searches, found)}


async def _read(chosen: dict[str, str]) -> tuple[list[Figure], list[str]]:
    """The chosen series read and worked out; and those that could not be."""
    async with Client(SERVERS["fred"](), read_timeout_seconds=LOOKUP_TIMEOUT) as client:
        # Two years, so a yearly series has last year's value to compare with.
        read = await asyncio.gather(*(_call(client, "series_data", {"series_id": key, "days": 800}) for key in chosen),
                                    return_exceptions=True)
    figures, missing = [], []
    for (key, why), data in zip(chosen.items(), read):
        made = None if isinstance(data, BaseException) else figure(data, why)
        if made:
            figures.append(made)
        else:
            missing.append(f"{key} could not be read")
    return figures, missing


def candidates(found: list[dict], text: str, most: int = CANDIDATES) -> list[dict]:
    """A search's current series that cover enough of it, the closest and then
    the most used first; the series every plan reads are not among them."""
    current = [series for series in found if _current(series, set(CORE)) and match(series, text) >= MATCH / 2]
    return sorted(current, key=lambda series: (-match(series, text), -(series.get("popularity") or 0)))[:most]


Choose = Callable[[dict[str, list[dict]]], dict[str, str] | None]


def look_up_economy(searches: list[str], choose: Choose | None = None) -> EconomicData:
    """The session's official figures: the ones every plan needs, and those
    `choose` picks from what FRED finds for the searches (by id, with why), or,
    without a choice, the closest current series for each search. A note says
    what is missing."""
    searches = [text.strip()[:120] for text in searches if text.strip()][:MAX_SEARCHES]
    missing: list[str] = []
    try:
        found = _run(_search(searches), "FRED", "fred", "figures") if searches else {}
        listed = {text: candidates(series or [], text) for text, series in found.items()}
        missing += [f"no series that fits \"{text}\"" for text, series in listed.items() if not series]
        picked = choose({text: series for text, series in listed.items() if series}) if choose and any(listed.values()) else None
        if picked is None:
            picked = {}
            for text, series in listed.items():
                pick = best(series, text, {*CORE, *picked})
                if pick:
                    picked[pick["id"]] = f"Found for \"{text}\"."
        offered = {series["id"] for series in sum(listed.values(), [])}
        picked = {key: why for key, why in picked.items() if key in offered and key not in CORE}
        figures, unread = _run(_read({**CORE, **dict(list(picked.items())[:MAX_SEARCHES])}), "FRED", "fred", "figures")
    except LookupFailed as error:
        logger.warning("Looking up FRED failed: %s", error)
        return EconomicData(searches=searches, note=str(error))
    missing += unread
    return EconomicData(figures=figures, searches=searches, note=f"Left out: {'; '.join(missing)}." if missing else None)


def _plan_text(state: WorkflowState) -> str:
    venture = state.get("venture") or state["request"]
    context = state.get("context") or RequestContext()
    details = RequestContext(**context.model_dump(exclude={"research"})).as_prompt()
    plan = state.get("plan")
    tasks = "\n".join(f"- {name}: {task}" for name, task in state.get("assignments", {}).items())
    return (f"The venture:\n{fence(venture + (chr(10) + details if details else ''), 'founder')}"
            + (f"\n\nThe objective: {plan.objective}" if plan else "")
            + (f"\n\nThe specialists' tasks:\n{tasks}" if tasks else ""))


_PICK_PROMPT = (
    "You are the Chief of Staff of a startup founding team. These are the series FRED, the St. Louis "
    f"Fed's database, found for your searches. Pick at most {MAX_SEARCHES} that this venture's decision "
    "turns on, by id exactly as listed: each must measure what its search meant, for the venture's own "
    "market and place (a US venture needs US figures, not another country's; a state's or a city's "
    "figure only where the venture is), and say in a sentence what the team reads it for. Pick none "
    "rather than one that does not fit."
)


def _listing(found: dict[str, list[dict]]) -> str:
    return "\n\n".join(
        f"Found for \"{text}\":\n" + "\n".join(
            f"- {series['id']}: {series['title']} ({series['units']}, {series['frequency']}, "
            f"latest {series['observation_end']})" for series in listed)
        for text, listed in found.items()
    )


def lookup_node(state: WorkflowState) -> dict:
    """Look up the official figures the venture turns on, once a session: the
    Chief of Staff names the searches, then picks from what FRED finds."""
    metrics: dict = {}
    with track("lookup", metrics) as tracker:
        searches: list[str] = []
        plan = _plan_text(state)
        try:
            searches = structured_invoke(
                FredSearches, [SystemMessage(_FRED_PROMPT + RULES), HumanMessage(plan)], tracker, CHIEF, "lookups/fred-searches"
            ).searches
        except LLM_ERRORS as error:  # the figures every plan needs are still read
            logger.warning("Choosing what to look up failed: %s", error)

        def choose(found: dict[str, list[dict]]) -> dict[str, str] | None:
            human = f"{plan}\n\nThe series found:\n{fence(_listing(found), 'FRED')}"
            try:
                picks = structured_invoke(
                    FredPicks, [SystemMessage(_PICK_PROMPT + RULES), HumanMessage(human)], tracker, CHIEF, "lookups/fred-picks"
                ).picks
            except LLM_ERRORS as error:  # the closest series are read instead
                logger.warning("Picking the series failed: %s", error)
                return None
            return {pick.id.strip(): pick.why.strip() for pick in picks}

        economic = look_up_economy(searches, choose)
    return {"economic": economic, "metrics": metrics}


# ---- Tavily: competitors' own pages ----

class Page(NamedTuple):
    url: str
    title: str
    text: str


class Pages(NamedTuple):
    found: dict[str, Page]
    searches: int
    credits: int
    note: str | None = None


def _tool(names: list[str], action: str) -> str:
    for name in names:
        if re.fullmatch(rf"(tavily[-_])?{action}", name):
            return name
    raise LookupFailed(f"Tavily's MCP server has no {action} tool.")


def results(text: str) -> list[dict[str, str]]:
    """Tavily's MCP answer, which is text ("Title: ... URL: ... Content: ..."),
    as one entry a page."""
    found = []
    for block in re.split(r"\n(?=Title: )", text):
        url = re.search(r"^URL: (\S+)", block, re.MULTILINE)
        if not url:
            continue
        title = re.search(r"^Title: (.*)$", block, re.MULTILINE)
        raw = re.search(r"^Raw Content: (.*?)(?=\nFavicon: |\Z)", block, re.MULTILINE | re.DOTALL)
        content = re.search(r"^Content: (.*?)(?=\n(?:Raw Content|Favicon): |\Z)", block, re.MULTILINE | re.DOTALL)
        found.append({
            "url": url[1],
            "title": title[1].strip() if title and title[1].strip() not in ("", "undefined") else "",
            "text": (raw[1] if raw else content[1] if content else "").strip(),
        })
    return found


def own_page(name: str, found: list[dict[str, str]]) -> dict[str, str] | None:
    """The result on the company's own site, its pricing page first; none
    rather than another site's page about it."""
    words = [word for word in re.findall(r"[a-z0-9]+", name.lower()) if len(word) > 2]
    if not words:
        return None
    joined = "".join(re.findall(r"[a-z0-9]+", name.lower()))
    own = [result for result in found
           if (host := (urlsplit(result["url"]).hostname or "").removeprefix("www."))
           and (joined in host.replace("-", "") or host.split(".")[0] == words[0])]
    own.sort(key=lambda result: "pric" not in urlsplit(result["url"]).path.lower())
    return own[0] if own else None


_PRICE = re.compile(r"[$€£₹]\s?\d|\d\s?(?:usd|eur|gbp)\b|per (?:month|year|user|seat|provider)|/\s?(?:mo|month|yr|year|user|seat)\b"
                    r"|\b(?:pricing|plans?|free trial|starter|pro|enterprise|billed)\b", re.IGNORECASE)


def excerpt(text: str, most: int = PAGE_CHARACTERS) -> str:
    """The paragraphs of a page that speak of its prices, in their order,
    within `most` characters, links and images reduced to their words."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", text) if part.strip()]
    scored = sorted(((len(_PRICE.findall(part)), order) for order, part in enumerate(paragraphs)), reverse=True)
    chosen, used = set(), 0
    for score, order in scored:
        if not score or used + len(paragraphs[order]) > most:
            continue
        chosen.add(order)
        used += len(paragraphs[order]) + 1
    return "\n".join(paragraphs[order] for order in sorted(chosen))


async def _pages(names: list[str]) -> Pages:
    async with Client(SERVERS["tavily"](), read_timeout_seconds=LOOKUP_TIMEOUT) as client:
        tools = [tool.name for tool in (await client.list_tools()).tools]
        search, extract = _tool(tools, "search"), _tool(tools, "extract")
        answers = await asyncio.gather(
            *(_call(client, search, {"query": f"{name} pricing", "max_results": 5, "search_depth": "basic"})
              for name in names),
            return_exceptions=True,
        )
        own = {}
        for name, answer in zip(names, answers):
            page = None if isinstance(answer, BaseException) else own_page(name, results(str(answer)))
            if page:
                own[name] = page
        read: dict[str, str] = {}
        if own:
            answer = await _call(client, extract, {
                "urls": [page["url"] for page in own.values()], "extract_depth": "basic", "format": "markdown",
                "query": "pricing plans and prices",
            })
            read = {result["url"]: result["text"] for result in results(str(answer))}
    found = {
        name: Page(page["url"], page["title"] or f"{name}: pricing", excerpt(read[page["url"]]))
        for name, page in own.items() if excerpt(read.get(page["url"], ""))
    }
    left = [name for name in names if name not in found]
    return Pages(found, len(names), len(names) + math.ceil(len(own) / 5),
                 f"No pricing page of their own read for {', '.join(left)}." if left else None)


def read_competitor_pages(names: list[str]) -> Pages:
    """Each competitor's own pricing page, found and read through Tavily's MCP
    server: the passages on its prices. Never raises: what failed is in `note`."""
    if not names:
        return Pages({}, 0, 0)
    try:
        return _run(_pages(names), "Tavily's MCP server", "tavily", "competitor pages")
    except LookupFailed as error:
        logger.warning("Reading the competitors' pages failed: %s", error)
        return Pages({}, 0, 0, str(error))
