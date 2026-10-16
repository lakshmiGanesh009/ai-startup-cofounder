"""The written launch report for each session, and the store that keeps them.

After every evaluation the API records the session's latest results here. A
session's report starts as those results: the strategy, each specialist's
report and the Chief of Staff's decisions on conflicts, one editable markdown
section each. It can then be edited, expanded into a detailed version
(agents/report_writer.py) or reset to the latest results, and report_pdf.py
renders it as a PDF.

Reports are kept in memory, like the sessions themselves, so they are lost when
the API restarts. Every change to a report's content raises its version, and a
change made from an older version is refused, so two editors cannot silently
overwrite each other.
"""

import threading
from datetime import datetime, timezone

from pydantic import BaseModel

from agents.roles import ROLES, SPECIALISTS
from state import Resolution

STRATEGY = "strategy"
DECISIONS = "decisions"


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
        )


class Report(BaseModel):
    """A session's written report, as last saved."""

    session_id: str
    title: str
    objective: str
    context: str
    sections: list[ReportSection]
    version: int
    detailed: bool = False
    edited: bool = False
    # Newer results arrived after the report was edited or expanded, so they
    # were not applied; resetting the report applies them.
    outdated: bool = False
    updated_at: datetime


class ReportSummary(BaseModel):
    session_id: str
    title: str
    version: int
    detailed: bool
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


def build_sections(results: SessionResults) -> list[ReportSection]:
    """The strategy, each specialist's report, then the decisions on conflicts."""
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

        A report nobody has touched is rebuilt from them. An edited or detailed
        one is kept, so no work is lost, and marked outdated instead.
        """
        with self._lock:
            self._results[session_id] = results
            report = self._reports.get(session_id)
            if report and (report.edited or report.detailed):
                self._reports[session_id] = report.model_copy(update={"outdated": True})
            else:
                self._reports[session_id] = self._from_results(session_id, report)

    def summaries(self) -> list[ReportSummary]:
        """Every report, the most recently changed first."""
        with self._lock:
            reports = sorted(self._reports.values(), key=lambda r: r.updated_at, reverse=True)
        return [ReportSummary(**r.model_dump(exclude={"objective", "context", "sections"}))
                for r in reports]

    def get(self, session_id: str) -> Report:
        with self._lock:
            return self._get(session_id)

    def save(self, session_id: str, version: int, sections: list[ReportSection]) -> Report:
        """Replace the sections with edited ones, if nobody changed them since `version`."""
        with self._lock:
            report = self._current(session_id, version)
            self._reports[session_id] = _changed(report, sections=sections, edited=True)
            return self._reports[session_id]

    def apply_detailed(self, session_id: str, version: int, bodies: dict[str, str]) -> Report:
        """Swap in the detailed text of each section in `bodies`."""
        with self._lock:
            report = self._current(session_id, version)
            sections = [
                section.model_copy(update={"body": bodies[section.key]})
                if section.key in bodies else section
                for section in report.sections
            ]
            self._reports[session_id] = _changed(report, sections=sections, detailed=True)
            return self._reports[session_id]

    def reset(self, session_id: str) -> Report:
        """Rebuild the report from the latest results, dropping edits and detail."""
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
