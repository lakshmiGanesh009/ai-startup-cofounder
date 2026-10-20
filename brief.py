"""Preparing a brief before the team runs it.

A brief can start from a decision template (templates/*.json): a fill-in
request, with what that kind of decision needs looked up and asked. Before the
team starts, the Chief of Staff plans a few web searches about the brief,
Tavily runs them (search.py), and the Chief of Staff reads the results: it
keeps the facts that bear on the decision, each citing its sources, and asks
the founder up to three questions, only about what is missing and would change
the recommendation. The founder reviews both, and the facts and the answers
travel with the request in its context, so every agent works from them.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.chief_of_staff import structured_invoke
from guardrails import RULES, context_for_prompt, fence, log_flags, scan, scan_context
from llm import CHIEF, SPECIALIST
from metrics import track
from providers import NAMES, chosen, search_all
from search import Hit
from state import Finding, Flag, RequestContext, Research, Source

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

MAX_QUERIES = 4
MAX_FINDINGS = 8
MAX_QUESTIONS = 3

RESEARCH_OFF = "Web research is off: neither Azure OpenAI nor Tavily is set up."


class TemplateField(BaseModel):
    key: str = Field(description="The name of its {placeholder} in the template's prompt.")
    label: str
    placeholder: str = ""
    long: bool = Field(False, description="Whether the answer runs to a sentence or more.")


class Template(BaseModel):
    """A kind of decision a founder brings: a brief to fill in, and what the
    Chief of Staff should look up and make sure it knows for it."""

    name: str = Field(description="The template file's name, without its order prefix or .json.")
    title: str
    summary: str = Field(description="The decision it helps with, in a line.")
    prompt: str = Field(description="The brief, with a {key} for each field.")
    fields: list[TemplateField]
    research: list[str] = Field(default_factory=list, description="What to look up on the web.")
    ask: list[str] = Field(default_factory=list, description="What the Chief of Staff must know.")


def load_templates() -> list[Template]:
    """The decision templates, in their files' order (1_evaluate_idea.json first)."""
    templates = []
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        templates.append(Template(name=re.sub(r"^\d+_", "", path.stem), **data))
    return templates


class SearchPlan(BaseModel):
    """The web searches to run for a brief."""

    queries: list[str] = Field(description="Two to four web searches, each under twelve words.")


class Question(BaseModel):
    """One thing the Chief of Staff needs from the founder before the team starts."""

    question: str = Field(description="The question, in plain words.")
    why: str = Field(description="What the answer changes, in one sentence.")
    suggestions: list[str] = Field(description="Two to four likely answers, a few words each.")


class BriefReview(BaseModel):
    """The Chief of Staff's reading of the brief and the search results."""

    findings: list[Finding] = Field(
        default_factory=list,
        description=f"Up to {MAX_FINDINGS} facts from the search results, each citing its results; none without results.",
    )
    questions: list[Question] = Field(
        default_factory=list,
        description=f"Up to {MAX_QUESTIONS} questions, only where a missing fact would change the recommendation; none when the brief is enough.",
    )


class PreparedBrief(BaseModel):
    queries: list[str] = Field(description="The web searches that were run.")
    provider: str | None = Field(None, description="Who searched the web: Azure OpenAI or Tavily.")
    research: Research | None = Field(description="The facts found and their sources; None without any.")
    research_note: str | None = Field(description="Why there is no research, when there is none.")
    questions: list[Question]
    guardrails: list[Flag] = Field(
        default_factory=list,
        description="Text that tried to instruct the agents, in the brief or on a web page: cut out of what they read.",
    )


_SEARCH_PROMPT = (
    "You research the market for a startup founding team before it starts work on the "
    "founder's brief. Write two to four web searches whose results would most change the "
    "team's decision: the size and growth of this market, the main competitors and what "
    "they charge, what the buyers spend on the problem today, and any regulation the idea "
    "must meet. Make each specific to this venture and its market, under twelve words, "
    "with no quotation marks or search operators."
)

_REVIEW_PROMPT = (
    "You are the Chief of Staff of a startup founding team, preparing the founder's brief "
    "before the team starts work. You have the brief and, when the web search found any, "
    "numbered search results.\n\n"
    f"First, keep up to {MAX_FINDINGS} facts from the search results that bear on the "
    "decision: the market's size and growth, competitors and their prices, what buyers "
    "spend, costs, regulation. Write each as one sentence with its figures and the year "
    "they refer to, and cite the numbers of the results it comes from. Use only what the "
    "results say: leave out anything you cannot cite, vendors' marketing claims, and facts "
    "that do not bear on this decision. With no results, keep none.\n\n"
    "Then decide whether the founder must answer anything before the team starts. Ask "
    "only for facts that only the founder knows (their budget and runway, their team, "
    "their customers and traction so far, their goals and limits) when the brief leaves "
    "them out, the results cannot supply them, and the answer would change the "
    "recommendation. Never ask the founder to make a choice the team is there to "
    "recommend, such as which customers, channels, price, product scope or architecture "
    "to pick; the specialists work those out. Never ask about something the brief "
    f"already says. Ask at most {MAX_QUESTIONS} questions; a detailed brief often needs "
    "none, and asking nothing is better than asking for what the team can decide. Put "
    "each plainly, say in one short sentence what its answer changes, and offer two to "
    "four likely answers of a few words each."
)


def _brief_text(prompt: str, context: RequestContext | None) -> str:
    details = context_for_prompt(context)
    return f"The founder's brief:\n{fence(prompt, 'founder')}" + (f"\n\nWhat the founder told us:\n{details}" if details else "")


def _results_text(hits: list[Hit]) -> str:
    if not hits:
        return "The web search found no results."
    return "Search results:\n\n" + fence(
        "\n\n".join(f"[{number}] {hit.title} ({hit.url})\n{hit.content}" for number, hit in enumerate(hits, start=1)),
        "web search results",
    )


def _renumbered(findings: list[Finding], hits: list[Hit]) -> Research | None:
    """Keep the findings that cite a real result, and number their sources 1, 2,
    3 in order of first citation, listing only the sources cited."""
    order: dict[int, int] = {}
    kept = []
    for finding in findings:
        cited = [n for n in dict.fromkeys(finding.sources) if 0 < n <= len(hits)]
        if not cited or not finding.point.strip():
            continue
        for n in cited:
            order.setdefault(n, len(order) + 1)
        kept.append(Finding(point=finding.point.strip(), sources=[order[n] for n in cited]))
        if len(kept) == MAX_FINDINGS:
            break
    if not kept:
        return None
    sources = [Source(title=hits[n - 1].title, url=hits[n - 1].url) for n in sorted(order, key=order.get)]
    return Research(findings=kept, sources=sources)


def prepare_brief(
    prompt: str, context: RequestContext | None, template: Template | None, provider: str | None = None
) -> PreparedBrief:
    """Research the brief on the web, with the provider asked for (or the
    default), and have the Chief of Staff read it: the facts that bear on the
    decision, and its questions."""
    metrics: dict = {}
    brief = _brief_text(prompt, context)
    flags = log_flags(scan(prompt, "your brief") + scan_context(context))
    queries: list[str] = []
    hits: list[Hit] = []
    note: str | None = RESEARCH_OFF
    use = chosen(provider)
    if use:
        topics = f"\n\nFor this kind of decision, look up: {'; '.join(template.research)}." if template and template.research else ""
        with track("research", metrics) as tracker:
            plan = structured_invoke(
                SearchPlan, [SystemMessage(_SEARCH_PROMPT + topics + RULES), HumanMessage(brief)], tracker, SPECIALIST
            )
        queries = list(dict.fromkeys(query.strip() for query in plan.queries if query.strip()))[:MAX_QUERIES]
        hits, note = search_all(queries, use)
        flags += log_flags([
            flag for hit in hits
            for flag in scan(f"{hit.title}\n{hit.content}", f"a web page ({urlsplit(hit.url).netloc or hit.url})", "web")
        ])
        if not hits and not note:
            note = "The web search found nothing for this brief."

    must_know = f"\n\nFor this kind of decision, make sure you know: {'; '.join(template.ask)}." if template and template.ask else ""
    with track("brief", metrics) as tracker:
        review = structured_invoke(
            BriefReview,
            [SystemMessage(_REVIEW_PROMPT + must_know + RULES), HumanMessage(f"{brief}\n\n{_results_text(hits)}")],
            tracker,
            CHIEF,
        )
    research = _renumbered(review.findings, hits)
    if hits and not research:
        note = "The search results held nothing the Chief of Staff could cite for this decision."
    questions = [question for question in review.questions if question.question.strip()][:MAX_QUESTIONS]
    return PreparedBrief(
        queries=queries,
        provider=NAMES[use] if use else None,
        research=research,
        research_note=None if research else note,
        questions=questions,
        guardrails=flags,
    )
