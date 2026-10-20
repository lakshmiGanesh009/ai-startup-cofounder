"""What the API has been doing, for the How it works page's monitor: the
evaluations it ran, what each step took and cost, the briefs and proposals it
prepared, and a log of recent events, warnings and errors.

The endpoints record into one `Monitor`, and a logging handler adds the app's
warnings and errors, and the model client's retries, which show where Azure
stalled. It is kept in memory, like the sessions, so it starts empty whenever
the API does.
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from state import NodeMetric

MAX_EVENTS = 300
MAX_RUNS = 50

EventKind = Literal["start", "done", "run", "brief", "proposal", "warning", "error"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """One line of the log."""

    at: datetime
    kind: EventKind
    source: str = Field(description="The step, endpoint or module it came from.")
    message: str
    session: str | None = Field(None, description="The first 8 characters of the session's id.")


class Run(BaseModel):
    """One evaluation, as it ended."""

    session: str
    at: datetime
    seconds: float
    ok: bool
    error: str | None = None
    specialists: list[str] = Field(default_factory=list)
    calls: int = 0
    tokens: int = 0
    reviewed: int = 0
    approved: int = 0
    conflicts: int = 0
    research: str | None = Field(None, description="Who did the deep research, if any.")
    searches: int = 0
    credits: int = 0
    nodes: dict[str, NodeMetric] = Field(default_factory=dict)


class NodeStats(BaseModel):
    """One step of the graph, over the evaluations run."""

    node: str
    runs: int
    calls: int
    seconds: float
    tokens: int


class Totals(BaseModel):
    """Everything since the API started. The time, calls and costs are those of
    the evaluations that finished, so an average over them means something."""

    evaluations: int = 0
    failures: int = 0
    seconds: float = 0
    calls: int = 0
    tokens: int = 0
    reviewed: int = 0
    approved: int = 0
    conflicts: int = 0
    searches: int = 0
    credits: int = 0
    briefs: int = 0
    proposals: int = 0


class Monitoring(BaseModel):
    started_at: datetime
    totals: Totals
    nodes: list[NodeStats]
    runs: list[Run] = Field(description="The latest evaluations, newest first.")
    events: list[Event] = Field(description="The latest events, newest first.")


class Monitor:
    """A thread-safe record of recent activity. Totals cover everything since
    the API started; the runs and events kept are the latest only."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        """Start again, as at the API's start."""
        with self._lock:
            self.started_at = _now()
            self._events: deque[Event] = deque(maxlen=MAX_EVENTS)
            self._runs: deque[Run] = deque(maxlen=MAX_RUNS)
            self._totals = Totals()
            self._nodes: dict[str, NodeStats] = {}

    def event(self, kind: EventKind, source: str, message: str, session: str | None = None) -> None:
        with self._lock:
            self._events.append(Event(at=_now(), kind=kind, source=source, message=message, session=session and session[:8]))

    def run(self, run: Run) -> None:
        """Record an evaluation that ended, well or not. Only one that finished
        adds its time, calls and costs to the totals and to the steps."""
        with self._lock:
            self._runs.append(run)
            totals = self._totals
            totals.evaluations += 1
            if not run.ok:
                totals.failures += 1
                return
            totals.seconds = round(totals.seconds + run.seconds, 1)
            totals.calls += run.calls
            totals.tokens += run.tokens
            totals.reviewed += run.reviewed
            totals.approved += run.approved
            totals.conflicts += run.conflicts
            totals.searches += run.searches
            totals.credits += run.credits
            for node, metric in run.nodes.items():
                stats = self._nodes.setdefault(node, NodeStats(node=node, runs=0, calls=0, seconds=0, tokens=0))
                stats.runs += 1
                stats.calls += metric.calls
                stats.seconds = round(stats.seconds + metric.seconds, 2)
                stats.tokens += metric.tokens

    def count(self, what: Literal["briefs", "proposals"]) -> None:
        with self._lock:
            setattr(self._totals, what, getattr(self._totals, what) + 1)

    def snapshot(self) -> Monitoring:
        with self._lock:
            return Monitoring(
                started_at=self.started_at,
                totals=self._totals.model_copy(),
                nodes=[stats.model_copy() for stats in self._nodes.values()],
                runs=list(reversed(self._runs)),
                events=list(reversed(self._events)),
            )


class MonitorHandler(logging.Handler):
    """Puts the app's warnings and errors, and the model client's retries, in the log."""

    def __init__(self, monitor: Monitor):
        super().__init__(level=logging.INFO)
        self.monitor = monitor

    def emit(self, record: logging.LogRecord) -> None:
        retry = record.name.startswith("openai") and "Retrying" in record.getMessage()
        if record.levelno < logging.WARNING and not retry:
            return
        kind: EventKind = "error" if record.levelno >= logging.ERROR else "warning"
        message = "The model call was retried (Azure stalled or refused it)." if retry else record.getMessage()
        self.monitor.event(kind, record.name, message[:500])


monitor = Monitor()
