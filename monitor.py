"""What the API has been doing, for the How it works page's monitor and for
Prometheus: the evaluations it ran, what each step took and cost, the briefs
and proposals it prepared, the requests it answered, which providers it called
for what (Azure OpenAI, Tavily, FRED: their calls, failures, tokens and
credits), and a log of recent events, warnings and errors.

The endpoints record into one `Monitor`; a logging handler adds the app's
warnings and errors, and the model client's retries, which show where Azure
stalled. Its statistics and the Prometheus metrics (GET /metrics) count since
the API started; Prometheus keeps the history it scrapes. The latest
evaluations and events are history: with a database (persistence.py) they are
kept there too, and read back when the API starts.
"""

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    disable_created_metrics,
)
from pydantic import BaseModel, Field

from observability import QUIET_ROUTES, request_id
from state import NodeMetric

MAX_EVENTS = 300
MAX_RUNS = 50
# Per-evaluation times kept for each step's percentiles.
MAX_SAMPLES = 200
# The window the health status looks back over, and the problems kept for it.
HEALTH_MINUTES = 15
MAX_PROBLEMS = 1000

EventKind = Literal["start", "done", "run", "brief", "proposal", "document", "warning", "error", "system"]

# Buckets for the time histograms, in seconds: requests run from milliseconds
# to the ten minutes an evaluation can take at high reasoning.
REQUEST_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600)
EVALUATION_BUCKETS = (15, 30, 45, 60, 90, 120, 150, 180, 240, 300, 450, 600, 900)
NODE_BUCKETS = (1, 2.5, 5, 10, 15, 20, 30, 45, 60, 120, 300)

# The `_created` series double what a scrape sends and say little here.
disable_created_metrics()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def percentile(values: Sequence[float], share: float) -> float:
    """The value `share` of the way through `values` in order (0.5 is the
    median), between the two nearest when it falls between them."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * share
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


class Event(BaseModel):
    """One line of the log."""

    at: datetime
    kind: EventKind
    source: str = Field(description="The step, endpoint or module it came from.")
    message: str
    session: str | None = Field(default=None, description="The first 8 characters of the session's id.")
    request: str | None = Field(default=None, description="The ID of the request it happened in (X-Request-ID).")


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
    research: str | None = Field(default=None, description="Who did the deep research, if any.")
    searches: int = 0
    credits: int = 0
    nodes: dict[str, NodeMetric] = Field(default_factory=dict)


class NodeStats(BaseModel):
    """One step of the graph, over the evaluations that finished: its totals,
    and the median and 95th percentile of its time in one evaluation."""

    node: str
    runs: int
    calls: int
    seconds: float
    tokens: int
    p50: float = 0
    p95: float = 0


class Spread(BaseModel):
    """How long the latest finished evaluations took, in seconds."""

    p50: float
    p95: float
    max: float
    samples: int


class Health(BaseModel):
    """Whether anything went wrong lately: "errors" if an error was logged in
    the last `minutes`, "warnings" if only warnings were (a retried model call
    among them), else "healthy"."""

    status: Literal["healthy", "warnings", "errors"]
    warnings: int
    errors: int
    minutes: int = HEALTH_MINUTES


class Totals(BaseModel):
    """Everything since the API started. The time, calls and costs are those of
    the evaluations that finished, so an average over them means something.
    `requests` and `server_errors` leave out the polled routes (QUIET_ROUTES)."""

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
    brief_failures: int = 0
    proposals: int = 0
    proposal_failures: int = 0
    requests: int = 0
    server_errors: int = 0
    refused: int = 0
    flagged: int = 0
    retries: int = 0
    warnings: int = 0
    errors: int = 0


Provider = Literal["azure", "openai", "tavily", "fred"]
Service = Literal["model", "web search", "research", "speech", "figures", "competitor pages"]
PROVIDER_ORDER: tuple[str, ...] = ("azure", "openai", "tavily", "fred")
SERVICE_ORDER: tuple[str, ...] = ("model", "web search", "research", "speech", "figures", "competitor pages")


class ServiceUse(BaseModel):
    """What the API asked of one provider's service since it started."""

    service: Service
    calls: int = 0
    failed: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = Field(default=0, description="Time in its calls.")
    credits: int = Field(default=0, description="Credits its calls spent (Tavily's).")
    last_at: datetime | None = None
    last_failure: str | None = Field(default=None, description="Why its last failed call failed.")
    last_failure_at: datetime | None = None


class ProviderUse(BaseModel):
    """One provider: whether it is set up, what the app uses it for, how it
    stands now, and what each of its services did."""

    provider: Provider
    set_up: bool = True
    role: str = ""
    status: Literal["answering", "ready", "failing", "not set up"] = "ready"
    services: list[ServiceUse] = Field(default_factory=list)


class Call:
    """What a call to a provider used, for its caller to say."""

    def __init__(self):
        self.tokens_in = self.tokens_out = self.credits = 0

    def used(self, tokens_in: int = 0, tokens_out: int = 0, credits: int = 0) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.credits += credits


def failure_reason(error: BaseException) -> str:
    """A failed call in a line: the status and message a provider answered, else the error."""
    status = getattr(error, "status_code", None)
    body = getattr(error, "body", None)
    said = (body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else body) if body else None
    message = said.get("message") if isinstance(said, dict) else None
    if status and message:
        return f"{status}: {message}"[:300]
    return (f"{type(error).__name__}: {error}" if str(error) else type(error).__name__)[:300]


class Monitoring(BaseModel):
    started_at: datetime
    kept_in: Literal["memory", "postgres"] = Field(
        default="memory", description="Where the latest evaluations and events are kept: lost on a restart, or in PostgreSQL."
    )
    health: Health
    running: int = Field(default=0, description="Evaluations running now.")
    totals: Totals
    evaluation_seconds: Spread | None = Field(
        default=None, description="How long the evaluations finished since the API started took; none until one has."
    )
    nodes: list[NodeStats]
    providers: list[ProviderUse] = Field(
        default_factory=list, description="The providers the API calls, how each stands, and what it used them for."
    )
    runs: list[Run] = Field(description="The latest evaluations, newest first.")
    events: list[Event] = Field(description="The latest events, newest first.")


class Metrics:
    """The monitor's Prometheus metrics, in a registry of their own, with the
    process's (memory, CPU, open files; on Linux) and Python's."""

    def __init__(self):
        self.registry = registry = CollectorRegistry()
        ProcessCollector(registry=registry)
        PlatformCollector(registry=registry)
        GCCollector(registry=registry)

        def counter(name, about, labels=()):
            return Counter(f"cofounder_{name}", about, labels, registry=registry)

        def histogram(name, about, buckets, labels=()):
            return Histogram(f"cofounder_{name}", about, labels, buckets=buckets, registry=registry)

        self.requests = counter("http_requests", "HTTP requests answered, by route and status.",
                                ["method", "route", "status"])
        self.request_seconds = histogram("http_request_duration_seconds", "Time to answer an HTTP request.",
                                         REQUEST_BUCKETS, ["method", "route"])
        self.evaluations = counter("evaluations", "Evaluations that ended, by outcome.", ["outcome"])
        self.evaluation_seconds = histogram("evaluation_duration_seconds",
                                            "Time from a request to its strategy, for evaluations that finished.",
                                            EVALUATION_BUCKETS)
        self.running = Gauge("cofounder_evaluations_in_progress", "Evaluations running now.", registry=registry)
        self.node_seconds = histogram("node_duration_seconds", "Time a step of the graph took in one evaluation.",
                                      NODE_BUCKETS, ["node"])
        self.model_calls = counter("model_calls", "Model calls, by step of the graph.", ["node"])
        self.tokens = counter("model_tokens", "Tokens used, by step of the graph.", ["node"])
        self.reviews = counter("reports_reviewed", "Reports the Chief of Staff reviewed, by verdict.", ["verdict"])
        self.conflicts = counter("conflicts_settled", "Conflicts between specialists the Chief of Staff settled.")
        self.searches = counter("research_searches", "Web searches Azure OpenAI ran for deep research.")
        self.credits = counter("research_credits", "Tavily credits deep research spent.")
        self.briefs = counter("briefs", "Briefs prepared, by outcome.", ["outcome"])
        self.proposals = counter("proposals", "Investment proposals written or revised, by outcome.", ["outcome"])
        self.retries = counter("model_retries", "Model calls retried after Azure stalled or refused them.")
        self.log_events = counter("log_events", "Warnings and errors logged.", ["kind"])
        self.refused = counter("refused_requests", "Requests refused: no key, too large, too many, or the team busy.",
                               ["reason"])
        self.flagged = counter("guardrail_flags", "Text that tried to instruct the agents, cut out of what they read.",
                               ["origin", "kind"])
        self.provider_calls = counter("provider_calls", "Calls to a provider's service, by outcome.",
                                      ["provider", "service", "outcome"])
        self.provider_tokens = counter("provider_tokens", "Tokens a provider's models read and wrote.",
                                       ["provider", "direction"])
        self.provider_credits = counter("provider_credits", "Credits a provider's calls spent.", ["provider"])


class Monitor:
    """A thread-safe record of recent activity. Totals cover everything since
    the API started; the runs and events kept are the latest only."""

    def __init__(self):
        self._lock = threading.Lock()
        self._archive = None  # where the history is kept too (persistence.MonitorArchive)
        self.reset()

    def reset(self) -> None:
        """Start again, as at the API's start."""
        with self._lock:
            self.started_at = _now()
            self._events: deque[Event] = deque(maxlen=MAX_EVENTS)
            self._runs: deque[Run] = deque(maxlen=MAX_RUNS)
            self._problems: deque[tuple[datetime, EventKind]] = deque(maxlen=MAX_PROBLEMS)
            self._totals = Totals()
            self._nodes: dict[str, NodeStats] = {}
            self._samples: dict[str, deque[float]] = {}
            self._usage: dict[tuple[Provider, Service], ServiceUse] = {}
            self._running = 0
            self.metrics = Metrics()

    def attach(self, archive) -> None:
        """Keep the history in `archive` too (persistence.MonitorArchive)."""
        self._archive = archive

    def preload(self, runs: list[Run], events: list[Event]) -> None:
        """Put back the history kept before the API started, oldest first. The
        statistics still count from now; a warning or error in the last
        HEALTH_MINUTES counts towards the health."""
        with self._lock:
            self._runs.extend(runs)
            self._events.extend(events)
            self._problems.extend((event.at, event.kind) for event in events if event.kind in ("warning", "error"))

    def event(self, kind: EventKind, source: str, message: str, session: str | None = None) -> None:
        """Log an event, in the request it happened in."""
        rid = request_id()
        with self._lock:
            event = Event(at=_now(), kind=kind, source=source, message=message,
                          session=session and session[:8], request=rid)
            self._events.append(event)
            if kind in ("warning", "error"):
                self._problems.append((event.at, kind))
                setattr(self._totals, f"{kind}s", getattr(self._totals, f"{kind}s") + 1)
                self.metrics.log_events.labels(kind).inc()
        if self._archive:
            self._archive.add_event(event)

    def refused(self, reason: str) -> None:
        """Count a request refused before it reached a route (security.py)."""
        with self._lock:
            self._totals.refused += 1
            self.metrics.refused.labels(reason).inc()

    def flagged(self, origin: str, kind: str) -> None:
        """Count text that tried to instruct the agents (guardrails.py)."""
        with self._lock:
            self._totals.flagged += 1
            self.metrics.flagged.labels(origin, kind).inc()

    def retried(self) -> None:
        """Count a model call the client retried."""
        with self._lock:
            self._totals.retries += 1
            self.metrics.retries.inc()

    def begin(self) -> None:
        """An evaluation started; `run` records its end."""
        with self._lock:
            self._running += 1
            self.metrics.running.set(self._running)

    def run(self, run: Run) -> None:
        """Record an evaluation that ended, well or not. Only one that finished
        adds its time, calls and costs to the totals and to the steps."""
        with self._lock:
            metrics = self.metrics
            self._running = max(self._running - 1, 0)
            metrics.running.set(self._running)
            self._runs.append(run)
            if self._archive:
                self._archive.add_run(run)
            totals = self._totals
            totals.evaluations += 1
            if not run.ok:
                totals.failures += 1
                metrics.evaluations.labels("failed").inc()
                return
            metrics.evaluations.labels("finished").inc()
            metrics.evaluation_seconds.observe(run.seconds)
            totals.seconds = round(totals.seconds + run.seconds, 1)
            totals.calls += run.calls
            totals.tokens += run.tokens
            totals.reviewed += run.reviewed
            totals.approved += run.approved
            totals.conflicts += run.conflicts
            totals.searches += run.searches
            totals.credits += run.credits
            metrics.reviews.labels("approved").inc(run.approved)
            metrics.reviews.labels("not approved").inc(run.reviewed - run.approved)
            metrics.conflicts.inc(run.conflicts)
            metrics.searches.inc(run.searches)
            metrics.credits.inc(run.credits)
            for node, metric in run.nodes.items():
                stats = self._nodes.setdefault(node, NodeStats(node=node, runs=0, calls=0, seconds=0, tokens=0))
                stats.runs += 1
                stats.calls += metric.calls
                stats.seconds = round(stats.seconds + metric.seconds, 2)
                stats.tokens += metric.tokens
                self._samples.setdefault(node, deque(maxlen=MAX_SAMPLES)).append(metric.seconds)
                metrics.node_seconds.labels(node).observe(metric.seconds)
                metrics.model_calls.labels(node).inc(metric.calls)
                metrics.tokens.labels(node).inc(metric.tokens)

    @contextmanager
    def calling(self, provider: Provider, service: Service) -> Iterator[Call]:
        """Count a call to `provider`'s `service`: its time, and whether it
        failed and why. The caller says what it used on the Call yielded."""
        started = time.monotonic()
        call = Call()
        try:
            yield call
        except Exception as error:
            self._used(provider, service, call, time.monotonic() - started, error)
            raise
        self._used(provider, service, call, time.monotonic() - started, None)

    def _used(self, provider: Provider, service: Service, call: Call, seconds: float, error: BaseException | None) -> None:
        with self._lock:
            use = self._usage.setdefault((provider, service), ServiceUse(service=service))
            use.calls += 1
            use.seconds = round(use.seconds + seconds, 2)
            use.tokens_in += call.tokens_in
            use.tokens_out += call.tokens_out
            use.credits += call.credits
            use.last_at = _now()
            if error is not None:
                use.failed += 1
                use.last_failure = failure_reason(error)
                use.last_failure_at = use.last_at
            self.metrics.provider_calls.labels(provider, service, "failed" if error else "answered").inc()
            if call.tokens_in or call.tokens_out:
                self.metrics.provider_tokens.labels(provider, "in").inc(call.tokens_in)
                self.metrics.provider_tokens.labels(provider, "out").inc(call.tokens_out)
            if call.credits:
                self.metrics.provider_credits.labels(provider).inc(call.credits)

    def usage(self) -> list[ProviderUse]:
        """What each provider was called for since the API started, in a steady order."""
        with self._lock:
            return self._providers()

    def _providers(self) -> list[ProviderUse]:
        providers: dict[Provider, ProviderUse] = {}
        for (provider, service), use in sorted(
            self._usage.items(), key=lambda item: (PROVIDER_ORDER.index(item[0][0]), SERVICE_ORDER.index(item[0][1]))
        ):
            providers.setdefault(provider, ProviderUse(provider=provider)).services.append(use.model_copy())
        return list(providers.values())

    def count(self, what: Literal["briefs", "proposals"], ok: bool = True) -> None:
        """Count a brief or a proposal, prepared or failed."""
        with self._lock:
            field = what if ok else f"{what[:-1]}_failures"
            setattr(self._totals, field, getattr(self._totals, field) + 1)
            getattr(self.metrics, what).labels("finished" if ok else "failed").inc()

    def request(self, method: str, route: str, status: int, seconds: float) -> None:
        """Count an HTTP request the API answered."""
        with self._lock:
            self.metrics.requests.labels(method, route, str(status)).inc()
            self.metrics.request_seconds.labels(method, route).observe(seconds)
            if route not in QUIET_ROUTES:
                self._totals.requests += 1
                self._totals.server_errors += 1 if status >= 500 else 0

    def snapshot(self) -> Monitoring:
        with self._lock:
            since = _now() - timedelta(minutes=HEALTH_MINUTES)
            recent = [kind for at, kind in self._problems if at >= since]
            errors, warnings = recent.count("error"), recent.count("warning")
            times = [run.seconds for run in self._runs if run.ok and run.at >= self.started_at]
            return Monitoring(
                started_at=self.started_at,
                kept_in="postgres" if self._archive else "memory",
                health=Health(status="errors" if errors else "warnings" if warnings else "healthy",
                              warnings=warnings, errors=errors),
                running=self._running,
                totals=self._totals.model_copy(),
                evaluation_seconds=Spread(
                    p50=round(percentile(times, 0.5), 1), p95=round(percentile(times, 0.95), 1),
                    max=max(times), samples=len(times),
                ) if times else None,
                nodes=[
                    stats.model_copy(update={
                        "p50": round(percentile(self._samples[stats.node], 0.5), 2),
                        "p95": round(percentile(self._samples[stats.node], 0.95), 2),
                    })
                    for stats in self._nodes.values()
                ],
                runs=list(reversed(self._runs)),
                events=list(reversed(self._events)),
            ).model_copy(update={"providers": self._providers()})


class MonitorHandler(logging.Handler):
    """Puts the app's warnings and errors, and the model client's retries, in the log."""

    def __init__(self, monitor: Monitor):
        super().__init__(level=logging.INFO)
        self.monitor = monitor

    def emit(self, record: logging.LogRecord) -> None:
        retry = record.name.startswith("openai") and "Retrying" in record.getMessage()
        if record.levelno < logging.WARNING and not retry:
            return
        if retry:
            self.monitor.retried()
        kind: EventKind = "error" if record.levelno >= logging.ERROR else "warning"
        message = "The model call was retried (Azure stalled or refused it)." if retry else record.getMessage()
        self.monitor.event(kind, record.name, message[:500])


monitor = Monitor()
