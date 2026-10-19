"""The written launch report for each session, and the store that keeps them.

After every evaluation the API records the session's latest results here. A
session's report starts as those results: the strategy, each specialist's
report and the Chief of Staff's decisions on conflicts, one editable markdown
section each. It can then be edited, turned into an investment proposal
(agents/proposal_writer.py, proposal.py) or reset to the latest results, and
report_pdf.py renders it as a PDF.

Reports are kept in memory, like the sessions themselves, so they are lost when
the API restarts. Every change to a report's content raises its version, and a
change made from an older version is refused, so two editors cannot silently
overwrite each other.
"""

import threading
from datetime import datetime, timezone

from pydantic import BaseModel, computed_field

from agents.roles import ROLES, SPECIALISTS
from proposal import InvestmentMetrics, Proposal, figure_checks, investment_metrics
from state import DeepResearch, Research, Resolution

STRATEGY = "strategy"
DECISIONS = "decisions"
RESEARCH = "research"


class ReportSection(BaseModel):
    """One part of the report: its key, its heading and its markdown text."""

    key: str
    title: str
    body: str


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

    @classmethod
    def from_state(cls, state: dict) -> "SessionResults":
        context = state.get("context")
        return cls(
            venture=state.get("venture") or state["request"],
            objective=state["plan"].objective,
            context=context.as_prompt() if context else "",
            final_strategy=state["final_strategy"],
            analyses=state["analyses"],
            resolutions=state.get("resolutions", []),
            research=context.research if context else None,
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
        return figure_checks(self.proposal.market, self.proposal.financial) if self.proposal else []


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
    deep = results.deep if results.deep and (results.deep.areas or results.deep.companies) else None
    if deep or (results.research and results.research.findings):
        sections.append(
            ReportSection(key=RESEARCH, title="Web Research", body=research_markdown(results.research, deep))
        )
    return sections


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _changed(report: Report, **updates) -> Report:
    """A copy of `report` with `updates` applied and the next version."""
    return report.model_copy(
        update={**updates, "version": report.version + 1, "updated_at": _now()}
    )


class ReportStore:
    """Keeps each session's latest results and its report, in memory."""

    def __init__(self):
        self._lock = threading.Lock()
        self._results: dict[str, SessionResults] = {}
        self._reports: dict[str, Report] = {}

    def record(self, session_id: str, results: SessionResults) -> None:
        """Keep a session's latest results.

        A report nobody has touched is rebuilt from them. An edited one, or one
        with a proposal, is kept, so no work is lost, and marked outdated instead.
        """
        with self._lock:
            self._results[session_id] = results
            report = self._reports.get(session_id)
            if report and (report.edited or report.proposal):
                self._reports[session_id] = report.model_copy(update={"outdated": True})
            else:
                self._reports[session_id] = self._from_results(session_id, report)

    def summaries(self) -> list[ReportSummary]:
        """Every report, the most recently changed first."""
        with self._lock:
            reports = sorted(self._reports.values(), key=lambda r: r.updated_at, reverse=True)
        return [
            ReportSummary(
                **r.model_dump(
                    exclude={"objective", "context", "sections", "proposal", "investment", "checks"}
                ),
                has_proposal=r.proposal is not None,
            )
            for r in reports
        ]

    def get(self, session_id: str) -> Report:
        with self._lock:
            return self._get(session_id)

    def save(self, session_id: str, version: int, sections: list[ReportSection]) -> Report:
        """Replace the sections with edited ones, if nobody changed them since `version`."""
        with self._lock:
            report = self._current(session_id, version)
            self._reports[session_id] = _changed(report, sections=sections, edited=True)
            return self._reports[session_id]

    def save_proposal(self, session_id: str, version: int, proposal: Proposal,
                      edited: bool = True) -> Report:
        """Replace the proposal, if nobody changed the report since `version`.

        `edited` is False when the agents wrote it rather than the founder.
        """
        with self._lock:
            report = self._current(session_id, version)
            self._reports[session_id] = _changed(
                report, proposal=proposal, edited=report.edited or edited
            )
            return self._reports[session_id]

    def reset(self, session_id: str) -> Report:
        """Rebuild the report from the latest results, dropping edits and the proposal."""
        with self._lock:
            report = self._get(session_id)
            self._reports[session_id] = self._from_results(session_id, report)
            return self._reports[session_id]

    def _get(self, session_id: str) -> Report:
        if session_id not in self._reports:
            raise ReportNotFound(session_id)
        return self._reports[session_id]

    def _current(self, session_id: str, version: int) -> Report:
        report = self._get(session_id)
        if report.version != version:
            raise ReportChanged(f"The report is at version {report.version}, not {version}.")
        return report

    def _from_results(self, session_id: str, previous: Report | None) -> Report:
        results = self._results[session_id]
        return Report(
            session_id=session_id,
            title=results.venture,
            objective=results.objective,
            context=results.context,
            sections=build_sections(results),
            version=previous.version + 1 if previous else 1,
            updated_at=_now(),
        )


store = ReportStore()
