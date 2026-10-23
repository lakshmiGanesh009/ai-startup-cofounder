"""The written launch report for each session, and the store that keeps them.

After every evaluation the API records the session's latest results here. A
session's report starts as those results: the strategy, each specialist's
report and the Chief of Staff's decisions on conflicts, one editable markdown
section each. It can then be edited, turned into an investment proposal
(agents/proposal_writer.py, proposal.py) or reset to the latest results, and
report_pdf.py renders it as a PDF.

Reports are kept in memory, or in PostgreSQL once the API has a database
(persistence.py), so they survive a restart. Every change to a report's content
raises its version, and a change made from an older version is refused, so two
editors cannot silently overwrite each other. The versions before the current
one are kept (the latest KEEP_VERSIONS), so any can be looked at or restored.
"""

import re
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal, NamedTuple, Protocol

from pydantic import BaseModel, Field, computed_field, field_validator

from agents.roles import ROLES, SPECIALISTS
import currency as money
from currency import CURRENCIES, DEFAULT
from proposal import InvestmentMetrics, Proposal, figure_checks, investment_metrics
from state import Answer, DeepResearch, EconomicData, RequestContext, Research, Resolution, number

STRATEGY = "strategy"
DECISIONS = "decisions"
RESEARCH = "research"
ECONOMIC = "economic"
DOCUMENTS = "documents"


class ReportSection(BaseModel):
    """One part of the report: its key, its heading and its markdown text."""

    key: str
    title: str
    body: str


class DocumentSettings(BaseModel):
    """What is set once for the whole document and applied everywhere by code
    (document.py): the currency of every amount, the system its measurements
    were last converted to, who it is from, and the sections left out."""

    currency: str = Field(DEFAULT, description="The ISO 4217 code of every amount in the document.")
    units: Literal["metric", "imperial"] | None = Field(
        None, description="The system the measurements were last converted to; None while as written."
    )
    prepared_by: str = Field("AI Startup Co-Founder Team", min_length=1, max_length=80)
    hidden: list[str] = Field(
        default_factory=list, max_length=30,
        description="Keys of the team report's sections left out of the document and its PDF.",
    )

    @field_validator("currency")
    @classmethod
    def _known(cls, code: str) -> str:
        if code not in CURRENCIES:
            raise ValueError(f"{code} is not a currency the document can use: {', '.join(CURRENCIES)}.")
        return code


class WorkedFrom(BaseModel):
    """The founder's documents a run worked from, by id."""

    uploads: list[str] = Field(default_factory=list, description="Files the founder uploaded.")
    reports: list[str] = Field(default_factory=list, description="Earlier reports, by session id.")


class Choices(BaseModel):
    """What the founder chose and told the team while the report was built: the
    request and its details, the answers to the Chief of Staff's questions, the
    research facts kept, the documents, and how the team was run."""

    brief: str = Field(description="The founder's first request, as written.")
    follow_up: str | None = Field(None, description="The latest follow-up, when the report answers one.")
    target_market: str | None = None
    constraints: str | None = None
    competitive_landscape: str | None = None
    answers: list[Answer] = Field(default_factory=list, description="The founder's answers to the Chief of Staff's questions.")
    research: Research | None = Field(None, description="The facts from the web research the founder kept, with their sources.")
    documents: list[str] = Field(default_factory=list, description='The founder\'s documents, a line each ("D1: plan.pdf (PDF, 12 pages)").')
    deep_research: bool | None = Field(None, description="Whether the team researched each area on the web first; None when not known.")
    research_provider: str | None = Field(None, description="Where that research ran: azure or tavily.")
    efforts: dict[str, str] = Field(default_factory=dict, description='The reasoning efforts it ran at, by role ("specialist", "chief"); empty when not known.')
    complete: bool = Field(True, description="False for a report built before its choices were kept: only what its results hold.")

    @classmethod
    def from_state(cls, state: dict, documents: list[str], efforts: dict[str, str] | None = None) -> "Choices":
        context = state.get("context") or RequestContext()
        venture = state.get("venture") or state["request"]
        deep = bool(state.get("deep"))
        return cls(
            brief=venture,
            follow_up=state["request"] if state["request"] != venture else None,
            **context.model_dump(include={"target_market", "constraints", "competitive_landscape"}),
            answers=[answer for answer in context.answers if answer.answer.strip()],
            research=context.research if context.research and context.research.findings else None,
            documents=documents,
            deep_research=deep,
            research_provider=state.get("research_provider") if deep else None,
            efforts=efforts or {},
        )


class SessionResults(BaseModel):
    """What a session's latest evaluation produced; reports are built from it."""

    venture: str
    objective: str
    context: str
    final_strategy: str
    analyses: dict[str, str]
    resolutions: list[Resolution]
    research: Research | None = None
    deep: DeepResearch | None = None
    economic: EconomicData | None = None
    # The founder's documents the team worked from, a line each ("D1: plan.pdf (PDF, 12 pages)").
    documents: list[str] = []
    worked_from: WorkedFrom = Field(default_factory=WorkedFrom)
    # What the founder chose and gave; None on results kept before it was.
    choices: Choices | None = None

    @classmethod
    def from_state(cls, state: dict, efforts: dict[str, str] | None = None) -> "SessionResults":
        from library import describe, sources  # library reads this module's store

        context = state.get("context")
        try:
            documents = describe(sources(context.uploads, context.reports)) if context else []
        except KeyError:
            documents = []
        return cls(
            documents=documents,
            worked_from=WorkedFrom(uploads=context.uploads, reports=context.reports) if documents else WorkedFrom(),
            venture=state.get("venture") or state["request"],
            objective=state["plan"].objective,
            context=context.as_prompt() if context else "",
            final_strategy=state["final_strategy"],
            analyses=state["analyses"],
            resolutions=state.get("resolutions", []),
            research=context.research if context else None,
            economic=state.get("economic"),
            deep=state.get("deep_research"),
            choices=Choices.from_state(state, documents, efforts),
        )


class Report(BaseModel):
    """A session's written report, as last saved."""

    session_id: str
    title: str
    objective: str
    context: str
    sections: list[ReportSection]
    version: int
    # The investment proposal, once the agents have written it.
    proposal: Proposal | None = None
    settings: DocumentSettings = Field(default_factory=DocumentSettings)
    # How this version came about, for the report's history.
    change: str | None = None
    worked_from: WorkedFrom = Field(default_factory=WorkedFrom)
    edited: bool = False
    # Newer results arrived after the report was edited or got its proposal, so
    # they were not applied; resetting the report applies them.
    outdated: bool = False
    updated_at: datetime

    @computed_field
    @property
    def investment(self) -> InvestmentMetrics | None:
        """NPV, IRR, payback and break-even, calculated from the proposal's figures."""
        return investment_metrics(self.proposal.financial) if self.proposal else None

    @computed_field
    @property
    def checks(self) -> list[str]:
        """Where the proposal's figures disagree, calculated from them."""
        if not self.proposal:
            return []
        return figure_checks(self.proposal.market, self.proposal.financial, self.settings.currency)


class ReportContent(BaseModel):
    """What the founder can change in a report and save together: a draft they
    accept (document.py), or an earlier version they restore."""

    title: str = Field(min_length=1, max_length=4000)
    objective: str = Field(max_length=4000)
    sections: list[ReportSection]
    proposal: Proposal | None = None
    settings: DocumentSettings = Field(default_factory=DocumentSettings)


class VersionSummary(BaseModel):
    version: int
    updated_at: datetime
    change: str | None
    has_proposal: bool
    current: bool
    changed: int | None = Field(None, description="How many fields differ from the version before it; None when "
                                "there is none kept to compare with.")
    areas: list[str] = Field(default_factory=list, description='The parts of the report those changes are in, '
                             'once each: "Strategy", "Financial plan", "Currency".')


class Figures(BaseModel):
    """The proposal's headline figures, calculated from its financial plan."""

    npv: float
    irr: float | None
    payback_months: float | None
    break_even_customers: int | None


Verdict = Literal["Go", "Go with conditions", "Not yet"]


class KeyFigure(BaseModel):
    """A figure to see at a glance, with what it is: "Price", "$149 a month"."""

    label: str
    value: str


class ReportSummary(BaseModel):
    """What the founder needs to tell one report from another, and choose."""

    session_id: str
    title: str
    version: int
    has_proposal: bool
    edited: bool
    outdated: bool
    updated_at: datetime
    objective: str = Field("", description="The decision the team was asked to make.")
    project_name: str | None = Field(None, description="The proposal's name for the project, once written.")
    verdict: Verdict | None = Field(None, description="The recommendation: the proposal's, else the strategy's.")
    currency: str = DEFAULT
    prepared_by: str = "AI Startup Co-Founder Team"
    team: list[str] = Field(default_factory=list, description="The specialists whose reports it holds.")
    sections: int = 0
    documents: int = Field(0, description="The founder's files and earlier reports it worked from.")
    figures: Figures | None = None
    checks: int = Field(0, description="How many of the proposal's figures disagree.")
    change: str | None = Field(None, description="What made this version.")
    brief: str = Field("", description="The report in a few lines, as markdown: the proposal's recommendation and "
                       "financial case, else the opening of the strategy.")
    key_figures: list[KeyFigure] = Field(default_factory=list, description="Figures to see at a glance: the "
                                         "proposal's, calculated; else the ones the strategy and Finance name.")


class ReportNotFound(KeyError):
    """No evaluation has been recorded for this session."""


class ReportChanged(Exception):
    """The report has changed since the version the caller started from."""


def decisions_markdown(resolutions: list[Resolution]) -> str:
    return "\n".join(
        f"- **{ROLES[r.conflict.raised_by].title} vs {ROLES[r.conflict.about].title}:** "
        f"{r.conflict.issue} **Decision:** {r.decision}"
        for r in resolutions
    )


def _cites(numbers: list[int]) -> str:
    return "".join(f"[{n}]" for n in numbers)


def _cite_range(numbers: list[int]) -> str:
    """A run of three or more sources reads as a range: "[38]–[48]"."""
    ordered = sorted(numbers)
    if len(ordered) > 2 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"[{ordered[0]}]–[{ordered[-1]}]"
    return _cites(ordered)


def research_markdown(brief: Research | None, deep: DeepResearch | None = None) -> str:
    """The research the team worked from, citing its sources by number, then the
    sources. With deep research: the brief's facts, each area's report and the
    competitors, under their own headings, and the session's sources."""
    facts = "\n".join(f"- {finding.point} {_cites(finding.sources)}" for finding in brief.findings) if brief else ""
    sources = deep.sources if deep else brief.sources if brief else []
    listed = "\n".join(f"{number}. [{source.title}]({source.url})" for number, source in enumerate(sources, start=1))
    if not deep:
        return f"{facts}\n\n**Sources**\n\n{listed}"
    parts = [f"### Before the team started\n\n{facts}"] if facts else []
    parts += [f"### {ROLES[name].title}\n\n{report}" for name, report in deep.areas.items()]
    if deep.companies:
        parts.append("### Competitors\n\n" + "\n".join(
            f"- **{company.name}**: {company.summary} "
            + " ".join(f"{label}: {value}" for label, value in (
                ("Pricing", company.pricing), ("Customers", company.customers), ("Funding", company.funding),
                ("Recent moves", company.recent_moves), ("Strengths", company.strengths),
                ("Weaknesses", company.weaknesses)) if value)
            + f" {_cite_range(company.sources)}"
            for company in deep.companies
        ))
    parts.append(f"### Sources\n\n{listed}")
    return "\n\n".join(parts)


def build_sections(results: SessionResults) -> list[ReportSection]:
    """The strategy, each specialist's report, the decisions on conflicts, then
    the web research the team started from."""
    sections = [ReportSection(key=STRATEGY, title="Launch Strategy", body=results.final_strategy)]
    for role in SPECIALISTS:
        if role.name in results.analyses:
            sections.append(
                ReportSection(key=role.name, title=role.title, body=results.analyses[role.name])
            )
    if results.resolutions:
        sections.append(
            ReportSection(
                key=DECISIONS,
                title="Conflicts and Decisions",
                body=decisions_markdown(results.resolutions),
            )
        )
    if results.documents:
        sections.append(ReportSection(
            key=DOCUMENTS, title="The Founder's Documents",
            body="The team worked from these, citing them by their marks ([D1 · page 3]):\n\n"
                 + "\n".join(f"- {line}" for line in results.documents),
        ))
    deep = results.deep if results.deep and (results.deep.areas or results.deep.companies) else None
    if deep or (results.research and results.research.findings):
        sections.append(
            ReportSection(key=RESEARCH, title="Web Research", body=research_markdown(results.research, deep))
        )
    if results.economic and results.economic.figures:
        sections.append(ReportSection(key=ECONOMIC, title="Economic Data", body=economic_markdown(results.economic)))
    return sections


def economic_markdown(economic: EconomicData) -> str:
    """The official figures the team worked from, each with its change over the
    year and a link to its page on FRED."""
    lines = [
        f"- **{figure.title}**: {number(figure.value)} ({figure.units}) on {figure.date}"
        + (f", {figure.change} over the year" if figure.change else "")
        + f". [FRED · {figure.id}]({figure.link})"
        for figure in economic.figures
    ]
    return ("Official figures from FRED, the St. Louis Fed's database, read for this plan and cited in the "
            "team's reports as [FRED · DGS10]:\n\n" + "\n".join(lines))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _changed(report: Report, **updates) -> Report:
    """A copy of `report` with `updates` applied and the next version."""
    return report.model_copy(
        update={**updates, "version": report.version + 1, "updated_at": _now()}
    )


class Stored(NamedTuple):
    """A session's latest results and its report, as kept."""

    results: SessionResults
    report: Report


# The recommendation a strategy leads with ("Recommendation: Go with conditions",
# "**Verdict:** Not yet"); never the "go" of "go-to-market".
_VERDICT = re.compile(r"\b(?:recommendation|verdict)\W{1,6}(go with conditions|not yet|no[- ]go|go)(?![-\w])",
                      re.IGNORECASE)


def verdict_of(report: Report) -> Verdict | None:
    """The report's recommendation: the proposal's own, else the one its
    strategy leads with; None when it states none."""
    if report.proposal:
        return report.proposal.executive.verdict
    strategy = next((s.body for s in report.sections if s.key == STRATEGY), "")
    found = _VERDICT.search(strategy[:600])
    if not found:
        return None
    word = found.group(1).lower()
    return "Go with conditions" if word == "go with conditions" else "Go" if word == "go" else "Not yet"


# ---- A report in a few lines, and its figures at a glance ----

BRIEF_CHARS = 640
BRIEF_POINTS = 3
LEAD_CHARS = 320
POINT_CHARS = 150
KEY_FIGURES = 4

_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s")
# "Recommendation: Go —", which the verdict shown beside the brief already says.
_RESTATED = re.compile(r"^\**(?:recommendation|verdict)(?::\**|\**:)\s*\**(?:go with conditions|not yet|no[- ]go|go)\b\**"
                       r"\s*[—–:.;,-]?\s*", re.IGNORECASE)
_SIGNS = sorted({currency.symbol.strip() for currency in CURRENCIES.values()}
                | {prefix for currency in CURRENCIES.values() for prefix in currency.prefixes}, key=len, reverse=True)
# A sign that is a word ("CHF", "R") is followed by a space, so "R2" is not an amount.
_SYMBOLS = "|".join(re.escape(sign) for sign in _SIGNS if not sign[-1].isalpha())
_WORDED = "|".join(re.escape(sign) for sign in _SIGNS if sign[-1].isalpha())
_CODES = "|".join(CURRENCIES)
# "15,000", "1,00,000", "2.4"; not the comma after it.
_NUMBER = r"\d+(?:,\d{2,3})*(?:\.\d+)?"
_SCALE = r"(?:\s?(?:[kKmMbB]|million|billion)\b)?"
_PER = r"(?:\s?(?:/|per |a |an )(?:month|mo|year|yr|customer|client|clinic|practice|user|seat|sprint|pilot)s?\b){0,2}"
# What a figure is, best first: an amount ("$15,000", "€12k", "AED 4,000 a
# month", "$150-$200", "$300+"), a share ("84%", "8-10%"), or a span of time or
# a count ("90 days", "1–2 pilots").
_AMOUNT = rf"(?:(?:{_SYMBOLS})\s?|(?:{_WORDED}|{_CODES})\s){_NUMBER}{_SCALE}"
_FIGURES = (
    rf"(?:{_AMOUNT}(?:\s?[–-]\s?(?:{_AMOUNT}|{_NUMBER}{_SCALE}))?\+?|{_NUMBER}{_SCALE}\s?(?:{_CODES})\b){_PER}",
    rf"{_NUMBER}(?:\s?[–-]\s?{_NUMBER})?\s?%",
    rf"{_NUMBER}(?:\s?[–-]\s?{_NUMBER})?\s(?:days?|weeks?|months?|years?|hrs|hours|customers|clients|clinics|"
    r"practices|pilots|users|seats|sprints)\b",
)
# A figure the agents named: "Price = $15,000", "launch budget: $3,000",
# "direct costs ≈ $2,400/sprint".
_NAMED = re.compile(rf"(?P<label>[A-Za-z][A-Za-z'’ /&-]{{1,48}}?)\s*(?:=|≈|:)\s*(?:[~≈]\s?)?"
                    rf"(?P<value>{'|'.join(f'(?P<kind{rank}>{figure})' for rank, figure in enumerate(_FIGURES))})")
_FILLER = {"and", "the", "a", "an", "with", "at", "of", "for", "to", "its", "our", "your", "their", "is", "are", "be", "per"}


def _clip(line: str, most: int) -> str:
    if len(line) <= most:
        return line
    cut = line[:most]
    if " " in cut[most // 2:]:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(",;:—- ") + "…"


def _introduces(line: str) -> bool:
    """Whether a line only introduces what follows: "Key facts", "Why:"."""
    return line.endswith(":") or (len(line) < 60 and line[-1] not in ".!?…)")


def brief_of(text: str) -> str:
    """The opening of a strategy, as markdown: its lead (the recommendation and
    the main reason), the paragraph after it, and the first few points, each
    clipped, within a few lines. What only restates the verdict (its heading,
    "Recommendation: Go —") is left out, and so is a line that introduces
    points not there."""
    lead = intro = None
    points: list[str] = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if lead:
                break  # the next part
            continue
        if _ITEM.match(stripped):
            point = _clip(stripped, POINT_CHARS)
            if len(points) == BRIEF_POINTS or len("".join([lead or "", intro or "", *points, point])) > BRIEF_CHARS:
                break
            points.append(point)
        elif points or intro:
            break  # past the opening
        elif lead:
            intro = _clip(stripped, POINT_CHARS)
        elif stripped := _RESTATED.sub("", stripped):
            lead = _clip(stripped[0].upper() + stripped[1:], LEAD_CHARS)
    if intro and not points and _introduces(intro):
        intro = None
    return "\n\n".join(part for part in (lead, "\n".join(filter(None, [intro, *points]))) if part)


def _plain(text: str) -> str:
    """Text without markdown emphasis, what it cites or its odd hyphens, for
    reading figures from."""
    text = text.replace("**", "").replace("__", "").replace("\u2011", "-").replace("\u2010", "-")
    return re.sub(r"\[[^\]\n]{1,240}\]", "", text)


def _label(raw: str) -> str | None:
    words = re.split(r"[;,(—–]|\s-\s", raw)[-1].split()
    while words and words[0].lower() in _FILLER:
        words.pop(0)
    words = words[-4:]
    if not words or not any(len(word) > 2 for word in words):
        return None
    label = " ".join(words)
    return label[0].upper() + label[1:]


def named_figures(*texts: str) -> list[KeyFigure]:
    """The figures the agents named in `texts` ("Price = $15,000"), up to
    KEY_FIGURES: amounts before shares, shares before spans, each label and
    value once, then in the order written. A nil one ("setup fee: $0") is not
    one to see at a glance."""
    found: list[tuple[int, int, KeyFigure]] = []
    labels: set[str] = set()
    values: set[str] = set()
    for text in texts:
        for match in _NAMED.finditer(_plain(text)):
            label, value = _label(match["label"]), match["value"].strip()
            if label and label not in labels and value not in values and re.search(r"[1-9]", value):
                rank = next(rank for rank in range(len(_FIGURES)) if match[f"kind{rank}"])
                found.append((rank, len(found), KeyFigure(label=label, value=value)))
                labels.add(label)
                values.add(value)
    best = sorted(found, key=lambda entry: entry[:2])[:KEY_FIGURES]
    return [figure for _, _, figure in sorted(best, key=lambda entry: entry[1])]


def _proposal_figures(report: Report) -> list[KeyFigure]:
    """The proposal's own figures, calculated from its financial plan."""
    plan = report.proposal.financial
    code = report.settings.currency
    figures = [
        KeyFigure(label="Price", value=f"{money.full(plan.price_per_customer_month, code)} a month"),
        KeyFigure(label="Start-up cost", value=money.compact(sum(item.amount for item in plan.capex), code)),
        KeyFigure(label="Fixed costs", value=f"{money.compact(sum(item.amount for item in plan.monthly_opex), code)} a month"),
    ]
    if report.investment and report.investment.revenue:
        figures.append(KeyFigure(label="Year-3 revenue", value=money.compact(report.investment.revenue[-1], code)))
    return figures


def summary(report: Report) -> ReportSummary:
    metrics = report.investment
    present = {section.key for section in report.sections}
    return ReportSummary(
        **report.model_dump(include={"session_id", "title", "version", "edited", "outdated", "updated_at",
                                     "objective", "change"}),
        has_proposal=report.proposal is not None,
        project_name=report.proposal.executive.project_name if report.proposal else None,
        verdict=verdict_of(report),
        currency=report.settings.currency,
        prepared_by=report.settings.prepared_by,
        # In the team's own order, whatever the sections' order.
        team=[role.name for role in SPECIALISTS if role.name in present],
        sections=len(report.sections),
        documents=len(report.worked_from.uploads) + len(report.worked_from.reports),
        figures=Figures(**metrics.model_dump(include={"npv", "irr", "payback_months", "break_even_customers"}))
        if metrics else None,
        checks=len(report.checks),
        brief=_brief(report),
        key_figures=_proposal_figures(report) if report.proposal else named_figures(
            *(section.body for key in (STRATEGY, "finance") for section in report.sections if section.key == key)
        ),
    )


def _brief(report: Report) -> str:
    if report.proposal:
        executive = report.proposal.executive
        return f"{executive.recommendation}\n\n{executive.financial_case}".strip()
    return brief_of(next((section.body for section in report.sections if section.key == STRATEGY), ""))


class ReportBackend(Protocol):
    """Where the reports are kept. `update` reads a session's report, applies
    `change` and writes the result as one step, so two changes cannot interleave;
    if `change` raises, nothing is written."""

    def get(self, session_id: str) -> Stored | None: ...

    def update(self, session_id: str, change: Callable[[Stored | None], Stored]) -> Stored: ...

    def summaries(self) -> list[ReportSummary]: ...

    def history(self, session_id: str) -> list[Report]:
        """The versions before the current one, newest first."""
        ...

    def delete(self, session_id: str) -> bool:
        """Remove a session's report and its versions; whether there was one."""
        ...


# Versions kept before the current one, per report.
KEEP_VERSIONS = 30


class MemoryReports:
    """The reports in this process's memory: lost when the API restarts."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stored: dict[str, Stored] = {}
        self._history: dict[str, list[Report]] = {}

    def get(self, session_id: str) -> Stored | None:
        with self._lock:
            return self._stored.get(session_id)

    def update(self, session_id: str, change: Callable[[Stored | None], Stored]) -> Stored:
        with self._lock:
            before = self._stored.get(session_id)
            stored = change(before)
            if before and before.report.version != stored.report.version:
                kept = [before.report, *self._history.get(session_id, [])]
                self._history[session_id] = kept[:KEEP_VERSIONS]
            self._stored[session_id] = stored
            return stored

    def history(self, session_id: str) -> list[Report]:
        with self._lock:
            return list(self._history.get(session_id, []))

    def delete(self, session_id: str) -> bool:
        with self._lock:
            self._history.pop(session_id, None)
            return self._stored.pop(session_id, None) is not None

    def summaries(self) -> list[ReportSummary]:
        with self._lock:
            reports = sorted((each.report for each in self._stored.values()), key=lambda r: r.updated_at, reverse=True)
        return [summary(report) for report in reports]


def _from_results(session_id: str, results: SessionResults, previous: Report | None) -> Report:
    return Report(
        session_id=session_id,
        title=results.venture,
        objective=results.objective,
        context=results.context,
        sections=build_sections(results),
        worked_from=results.worked_from,
        version=previous.version + 1 if previous else 1,
        updated_at=_now(),
    )


def _at_version(stored: Stored | None, session_id: str, version: int) -> Stored:
    """The session's report, if nobody has changed it since `version`."""
    if stored is None:
        raise ReportNotFound(session_id)
    if stored.report.version != version:
        raise ReportChanged(f"The report is at version {stored.report.version}, not {version}.")
    return stored


class ReportStore:
    """Keeps each session's latest results and its report, in the backend it is
    given: memory by default, PostgreSQL once the API has a database."""

    def __init__(self, backend: ReportBackend | None = None):
        self.backend: ReportBackend = backend or MemoryReports()

    def use(self, backend: ReportBackend) -> None:
        self.backend = backend

    def record(self, session_id: str, results: SessionResults) -> None:
        """Keep a session's latest results.

        A report nobody has touched is rebuilt from them. An edited one, or one
        with a proposal, is kept, so no work is lost, and marked outdated instead.
        """

        def change(stored: Stored | None) -> Stored:
            report = stored.report if stored else None
            if report and (report.edited or report.proposal):
                return Stored(results, report.model_copy(update={"outdated": True}))
            built = _from_results(session_id, results, report)
            change = "Rebuilt from the latest evaluation" if report else "Written by the team"
            return Stored(results, built.model_copy(update={"change": change}))

        self.backend.update(session_id, change)

    def summaries(self) -> list[ReportSummary]:
        """Every report, the most recently changed first."""
        return self.backend.summaries()

    def delete(self, session_id: str) -> None:
        """Delete a session's report, with its versions and the results it was built from."""
        if not self.backend.delete(session_id):
            raise ReportNotFound(session_id)

    def get(self, session_id: str) -> Report:
        stored = self.backend.get(session_id)
        if stored is None:
            raise ReportNotFound(session_id)
        return stored.report

    def results(self, session_id: str) -> SessionResults:
        """The results the session's report was built from."""
        stored = self.backend.get(session_id)
        if stored is None:
            raise ReportNotFound(session_id)
        return stored.results

    def save(self, session_id: str, version: int, sections: list[ReportSection]) -> Report:
        """Replace the sections with edited ones, if nobody changed them since `version`."""

        def change(stored: Stored | None) -> Stored:
            stored = _at_version(stored, session_id, version)
            report = _changed(stored.report, sections=sections, edited=True, change="Edited the team's report")
            return stored._replace(report=report)

        return self.backend.update(session_id, change).report

    def save_proposal(self, session_id: str, version: int, proposal: Proposal, edited: bool = True,
                      change: str = "Edited the proposal", settings: DocumentSettings | None = None) -> Report:
        """Replace the proposal, if nobody changed the report since `version`;
        with `settings`, those too (the currency a new proposal is written in).

        `edited` is False when the agents wrote it rather than the founder.
        """

        def apply(stored: Stored | None) -> Stored:
            stored = _at_version(stored, session_id, version)
            report = stored.report
            return stored._replace(report=_changed(
                report, proposal=proposal, edited=report.edited or edited, change=change,
                settings=settings or report.settings,
            ))

        return self.backend.update(session_id, apply).report

    def accept(self, session_id: str, version: int, content: ReportContent, change: str) -> Report:
        """Save a draft the founder accepted, or an earlier version they restored,
        if nobody changed the report since `version`."""

        def apply(stored: Stored | None) -> Stored:
            stored = _at_version(stored, session_id, version)
            report = _changed(stored.report, **dict(content), edited=True, change=change)
            return stored._replace(report=report)

        return self.backend.update(session_id, apply).report

    def kept(self, session_id: str) -> list[Report]:
        """The current version and those kept before it, newest first."""
        return [self.get(session_id), *self.backend.history(session_id)]

    def versions(self, session_id: str,
                 compare: Callable[[Report, Report], list[str]] | None = None) -> list[VersionSummary]:
        """The current version and those kept before it, newest first. With
        `compare` (the version before, a version: where each field that differs
        is), each says what changed since the version before it."""
        kept = self.kept(session_id)
        summaries = []
        for index, report in enumerate(kept):
            before = kept[index + 1] if index + 1 < len(kept) else None
            places = compare(before, report) if compare and before else None
            summaries.append(VersionSummary(
                version=report.version, updated_at=report.updated_at, change=report.change,
                has_proposal=report.proposal is not None, current=index == 0,
                changed=None if places is None else len(places), areas=list(dict.fromkeys(places or [])),
            ))
        return summaries

    def version(self, session_id: str, version: int) -> Report:
        """The report as it was at `version`."""
        for report in self.kept(session_id):
            if report.version == version:
                return report
        raise ReportNotFound(f"{session_id} v{version}")

    def with_before(self, session_id: str, version: int) -> tuple[Report, Report | None]:
        """The report at `version`, and the version kept before it, if there is one."""
        kept = self.kept(session_id)
        index = next((index for index, report in enumerate(kept) if report.version == version), None)
        if index is None:
            raise ReportNotFound(f"{session_id} v{version}")
        return kept[index], kept[index + 1] if index + 1 < len(kept) else None

    def restore(self, session_id: str, version: int, wanted: int) -> Report:
        """The content of version `wanted` saved as the newest version, if
        nobody changed the report since `version`."""
        old = self.version(session_id, wanted)
        content = ReportContent(**old.model_dump(include=set(ReportContent.model_fields)))
        return self.accept(session_id, version, content, f"Restored version {wanted}")

    def reset(self, session_id: str) -> Report:
        """Rebuild the report from the latest results, dropping edits and the proposal."""

        def change(stored: Stored | None) -> Stored:
            if stored is None:
                raise ReportNotFound(session_id)
            rebuilt = _from_results(session_id, stored.results, stored.report)
            return stored._replace(report=rebuilt.model_copy(update={"change": "Reset to the latest results"}))

        return self.backend.update(session_id, change).report


store = ReportStore()
