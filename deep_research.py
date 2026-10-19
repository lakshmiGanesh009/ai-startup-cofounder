"""Deep research for the specialists, by Tavily's Research API (search.py).

When a request asks for it, a research step runs between the plan and the
specialists: one research task per assigned specialist, written from its
assignment, and a profile of each of the main competitors, whom the Chief of
Staff names. The tasks run at the same time; with the "mini" model one takes
20-90 s and costs 20-80 Tavily credits.

Each report numbers its own sources from 1, so every source gets one number for
the whole session, after the brief's research (whose numbers stand), and the
reports' citations are renumbered to match: a specialist's [n] means the same
page everywhere. A specialist reads its area's report, and Marketing and
Finance the competitor profiles too. A follow-up reuses the session's research.
A task that fails leaves its area without deep research, and never fails the
request.
"""

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.chief_of_staff import structured_invoke
from agents.roles import ROLES
from llm import CHIEF, LLM_ERRORS
from metrics import track
from search import Report, SearchFailed, research_all
from state import CompanyProfile, DeepResearch, RequestContext, Source, WorkflowState

logger = logging.getLogger(__name__)

MAX_COMPANIES = 3
# Tavily's research answers in this shape for a competitor. It requires a
# description for every field.
COMPANY_SCHEMA = {
    "properties": {
        "name": {"type": "string", "description": "The company's name"},
        "summary": {"type": "string", "description": "What it sells, and to whom, in one or two sentences"},
        "pricing": {"type": "string", "description": "Its prices and plans, with figures"},
        "customers": {"type": "string", "description": "Who buys it, and how many customers it reports"},
        "funding": {"type": "string", "description": "Funding raised, investors, revenue or valuation if public"},
        "recent_moves": {"type": "string", "description": "Launches, price changes, acquisitions or partnerships in the last year"},
        "strengths": {"type": "string", "description": "Where it is strong against a new entrant"},
        "weaknesses": {"type": "string", "description": "Where a new entrant could beat it"},
    },
    "required": ["name", "summary", "pricing", "customers", "strengths", "weaknesses"],
}


class Competitor(BaseModel):
    name: str = Field(description="The name the company trades under.")
    what: str = Field(description="What it sells, in a few words, to tell it from others of the same name.")


class Competitors(BaseModel):
    """The companies to profile for a venture."""

    companies: list[Competitor] = Field(
        default_factory=list,
        description=f"At most {MAX_COMPANIES} real companies; none rather than a guess.",
    )


_COMPETITORS_PROMPT = (
    "You are the Chief of Staff of a startup founding team. Name the existing companies "
    f"this venture would compete with most directly, at most {MAX_COMPANIES}: those the "
    "brief or its research names first, then the ones its buyers would compare it with. "
    "Name only real companies you are sure exist, by the name they trade under, and say in "
    "a few words what each sells; name none rather than guess."
)


class SourceBook:
    """Numbers each source once: the session's sources keep their numbers, and a
    new page gets the next one."""

    def __init__(self, sources: list[Source]):
        self.sources = list(sources)
        self._numbers = {source.url: number for number, source in enumerate(self.sources, start=1)}

    def number(self, title: str, url: str) -> int:
        if url not in self._numbers:
            self.sources.append(Source(title=title, url=url))
            self._numbers[url] = len(self.sources)
        return self._numbers[url]

    def renumber(self, report: Report) -> dict[int, int]:
        """The report's own numbers, 1 first, mapped to the session's."""
        return {local: self.number(title, url) for local, (title, url) in enumerate(report.sources, start=1)}


def _brackets(text: str, numbers: dict[int, int]) -> str:
    """[3] in the session's numbers; a citation to no listed source is dropped."""
    return re.sub(r"\[(\d+)\]", lambda match: f"[{numbers[int(match[1])]}]" if int(match[1]) in numbers else "", text)


def _mentions(text: str, numbers: dict[int, int]) -> str:
    """A profile cites loosely, as "(source9)": those become citations in the
    report's own numbers, and then all are put in the session's."""
    text = re.sub(r"\s*\(?\bsource\s?(\d+)\)?", lambda match: f" [{match[1]}]", text, flags=re.IGNORECASE)
    return _brackets(text, numbers).strip()


def _brief(state: WorkflowState) -> str:
    """The venture as a research task needs it: the idea, the founder's details and answers."""
    venture = state.get("venture") or state["request"]
    context = state.get("context") or RequestContext()
    details = RequestContext(**context.model_dump(exclude={"research"})).as_prompt()
    return f"The startup: {venture}" + (f"\n{details}" if details else "")


def _area_task(name: str, task: str, brief: str) -> str:
    role = ROLES[name]
    return (
        f"Research for the {role.title} specialist of a startup founding team.\n{brief}\n"
        f"The specialist's task: {task}\n"
        f"Find current facts and figures on {role.focus} that bear on this task, for this "
        "venture's market, with their sources."
    )


def _company_task(company: Competitor, brief: str) -> str:
    return (
        f"Profile the company {company.name} ({company.what}) as a competitor to this startup.\n{brief}\n"
        "Cover what it sells and to whom, its pricing, its customers, its funding, its moves in "
        "the last year, and its strengths and weaknesses against a new entrant. Use only facts "
        "about this company, not about others with a similar name."
    )


def _profile(company: Competitor, report: Report, book: SourceBook) -> CompanyProfile:
    numbers = book.renumber(report)
    fields = report.content if isinstance(report.content, dict) else {}
    text = {key: _mentions(str(fields.get(key) or ""), numbers) for key in COMPANY_SCHEMA["properties"]}
    text["name"] = text["name"] or company.name
    cited = sorted({int(n) for value in text.values() for n in re.findall(r"\[(\d+)\]", value)})
    return CompanyProfile(**text, sources=cited or sorted(numbers.values()))


def research_node(state: WorkflowState) -> dict:
    """Research each assigned specialist's area not yet researched in this
    session, and, the first time, the main competitors."""
    context = state.get("context")
    deep = state.get("deep_research") or DeepResearch(
        sources=list(context.research.sources) if context and context.research else []
    )
    book = SourceBook(deep.sources)
    brief = _brief(state)
    areas = [name for name in state["assignments"] if name not in deep.areas]
    metrics: dict = {}
    with track("research", metrics) as tracker:
        competitors: list[Competitor] = []
        if not deep.companies:
            known = context.research.as_prompt() if context and context.research else ""
            messages = [SystemMessage(_COMPETITORS_PROMPT), HumanMessage(f"{brief}\n\n{known}".strip())]
            try:
                competitors = structured_invoke(Competitors, messages, tracker, CHIEF).companies[:MAX_COMPANIES]
            except LLM_ERRORS as error:  # the specialists' research still goes ahead
                logger.warning("Naming the competitors failed: %s", error)
        tasks = {f"area:{name}": (_area_task(name, state["assignments"][name], brief), None) for name in areas}
        tasks |= {f"company:{company.name}": (_company_task(company, brief), COMPANY_SCHEMA) for company in competitors}
        reports = research_all(tasks)

    found = dict(deep.areas)
    companies = list(deep.companies)
    tried = {*areas, *(company.name for company in competitors)}
    failed = [name for name in deep.failed if name not in tried]
    credits = deep.credits
    for name in areas:
        report = reports[f"area:{name}"]
        if isinstance(report, SearchFailed) or not isinstance(report.content, str) or not report.content:
            failed.append(name)
            continue
        found[name] = _brackets(report.content, book.renumber(report))
        credits += report.credits
    for company in competitors:
        report = reports[f"company:{company.name}"]
        if isinstance(report, SearchFailed) or not isinstance(report.content, dict):
            failed.append(company.name)
            continue
        companies.append(_profile(company, report, book))
        credits += report.credits
    return {
        "deep_research": DeepResearch(
            areas=found, companies=companies, sources=book.sources, credits=credits, failed=failed
        ),
        "metrics": metrics,
    }
