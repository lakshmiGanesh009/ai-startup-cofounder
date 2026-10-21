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

import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal, NamedTuple, Protocol

from pydantic import BaseModel, Field, computed_field, field_validator

from agents.roles import ROLES, SPECIALISTS
from currency import CURRENCIES, DEFAULT
from proposal import InvestmentMetrics, Proposal, figure_checks, investment_metrics
from state import DeepResearch, EconomicData, Research, Resolution, number

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

    @classmethod
    def from_state(cls, state: dict) -> "SessionResults":
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


class ReportSummary(BaseModel):
    session_id: str
    title: str
    version: int
    has_proposal: bool
    edited: bool
    outdated: bool
    updated_at: datetime


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


def summary(report: Report) -> ReportSummary:
    return ReportSummary(
        **report.model_dump(include={"session_id", "title", "version", "edited", "outdated", "updated_at"}),
        has_proposal=report.proposal is not None,
    )


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

    def get(self, session_id: str) -> Report:
        stored = self.backend.get(session_id)
        if stored is None:
            raise ReportNotFound(session_id)
        return stored.report

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

    def versions(self, session_id: str) -> list[VersionSummary]:
        """The current version and those kept before it, newest first."""
        current = self.get(session_id)
        return [
            VersionSummary(version=report.version, updated_at=report.updated_at, change=report.change,
                           has_proposal=report.proposal is not None, current=report is current)
            for report in [current, *self.backend.history(session_id)]
        ]

    def version(self, session_id: str, version: int) -> Report:
        """The report as it was at `version`."""
        current = self.get(session_id)
        if version == current.version:
            return current
        for report in self.backend.history(session_id):
            if report.version == version:
                return report
        raise ReportNotFound(f"{session_id} v{version}")

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
