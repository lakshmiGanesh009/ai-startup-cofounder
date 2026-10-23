import asyncio
import json
import logging
import re
import threading
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi import Path as InPath
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from prometheus_client.exposition import choose_encoder
from pydantic import BaseModel, Field, field_validator

import brief as brief_module
import deep_research
from agents.chief_of_staff import APPROVAL_SCORE, STRATEGY_WORDS, structured_invoke
import document
import library
from agents.proposal_writer import ProposalNotWritten, parts_to_write, revise_text, write_proposal
from agents.roles import COMPANY_READERS, REPORT_WORDS, SPECIALISTS
from agents.specialist import GAP_PREFIX
from brief import PreparedBrief, Template, load_templates, prepare_brief
from config import (
    API_KEY,
    CORS_ORIGINS,
    DATABASE_URL,
    DEBUG_MODE,
    LOG_FORMAT,
    MAX_CONCURRENT_RUNS,
    MAX_CRITIQUE_ROUNDS,
    MAX_ITERATIONS,
    MAX_REQUEST_BYTES,
    REQUESTS_PER_MINUTE,
    RUNS_PER_HOUR,
)
from extract import MAX_BYTES as MAX_UPLOAD_BYTES
from extract import Unreadable, extract
from graph import SERDE, build_graph
from library import Answer, Answered, UploadNotFound, UploadSummary, summary_of, uploads
from llm import (
    CHIEF,
    EFFORTS,
    LLM_ERRORS,
    SPECIALIST,
    Effort,
    LLMNotConfigured,
    failure,
    default_effort,
    reasoning,
    reasoning_effort,
    takes_reasoning_effort,
)
from metrics import track
from monitor import MAX_EVENTS, MAX_RUNS, Monitoring, MonitorHandler, Run, monitor
from observability import REQUEST_HEADER, RequestContextMiddleware, bind_session, configure_logging
from persistence import open_storage
from guardrails import log_flags, scan, scan_context
from progress import summarize
from currency import CURRENCIES
from document import Draft
from proposal import OWNERS, TITLES, Proposal
from report_pdf import render_pdf
from reports import (
    Choices,
    DocumentSettings,
    Report,
    ReportChanged,
    ReportContent,
    ReportNotFound,
    ReportSection,
    ReportSummary,
    SessionResults,
    VersionSummary,
    store,
)
import judge
import voice
import lookups
import providers
import tracing
from rates import Rates, RatesUnavailable, rates_from
from security import (
    MAX_FIELD_CHARS,
    MAX_PROMPT_CHARS,
    MAX_SECTIONS,
    SESSION_ID,
    Guard,
    GuardMiddleware,
    check_context,
    check_sections,
)
from state import DeepResearch, EconomicData, Flag, NodeMetric, RequestContext, Resolution, ReviewResult

SERVICE_NAME = "AI Startup Co-Founder Team"
SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"

configure_logging(logging.DEBUG if DEBUG_MODE else logging.INFO, LOG_FORMAT)
logger = logging.getLogger(__name__)
# The monitor's log gets the app's warnings and errors, and the model client's retries.
logging.getLogger().addHandler(MonitorHandler(monitor))

# Sessions, reports, uploads and the Monitor's history: in PostgreSQL when
# DATABASE_URL is set, so they survive a restart, else in memory.
storage = open_storage(DATABASE_URL, SERDE)
store.use(storage.reports)
uploads.use(storage.uploads)
monitor.attach(storage.archive)
# In memory until the storage opens: PostgreSQL's saver belongs to the event
# loop that serves the requests, so the lifespan builds the graph on it.
graph = build_graph()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the storage before the first request, and close it after the last.
    The API does not start without the database it was given."""
    global graph
    await storage.open()
    if storage.checkpointer:
        graph = build_graph(storage.checkpointer)
    if storage.archive:
        monitor.preload(*await run_in_threadpool(storage.archive.load, MAX_RUNS, MAX_EVENTS))
    access = "callers need its key" if API_KEY else "open to anyone who can reach it (no API_KEY)"
    monitor.event("system", "api", f"The API started, keeping sessions and reports in {storage.where}; {access}.")
    logger.info("Sessions and reports are kept in %s; %s.", storage.where, access)
    if tracing.enabled():
        # The prompts are registered off the start-up path; until they are, calls are traced unlinked.
        threading.Thread(target=tracing.register_prompts, name="langfuse-prompts", daemon=True).start()
        monitor.event("system", "api", "Model calls are traced in Langfuse.")
    yield
    await storage.close()
    tracing.flush()


app = FastAPI(
    title=SERVICE_NAME,
    description="Multi-agent founding team that evaluates startup ideas",
    version="0.1.0",
    lifespan=lifespan,
)
# The key, the size, the rates and the runs, checked before a route (security.py).
guard = Guard(API_KEY, MAX_REQUEST_BYTES, REQUESTS_PER_MINUTE, RUNS_PER_HOUR, MAX_CONCURRENT_RUNS, MAX_UPLOAD_BYTES)
app.add_middleware(GuardMiddleware, guard=guard, on_refuse=monitor.refused)
# Each request gets an ID, an access log line and its place in the metrics,
# refusals included.
app.add_middleware(RequestContextMiddleware, on_finish=monitor.request)
# Lets a browser frontend on another origin (the Next.js app) call the API, and
# read a response's request ID to show with an error. Added last, so it wraps
# every response, the 500s the request middleware makes included.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", REQUEST_HEADER],
    expose_headers=[REQUEST_HEADER],
)


class Reasoning(BaseModel):
    """How hard the models reason for one request; a role left out keeps the
    configured effort. Higher efforts give more considered answers but take
    longer: at "high" an evaluation takes 5 to 10 minutes. Azure OpenAI only."""

    specialist: Effort | None = Field(None, description="The four specialists, and their critiques.")
    chief: Effort | None = Field(None, description="The Chief of Staff's plan, reviews, decisions and summaries.")


def _efforts(choice: Reasoning | None) -> dict:
    return choice.model_dump() if choice else {}


# A session's id, wherever a request names one.
SessionId = Annotated[str, InPath(pattern=SESSION_ID, description="The session's id.")]


class EvaluateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    context: RequestContext | None = None
    session_id: str | None = Field(None, pattern=SESSION_ID)
    reasoning: Reasoning | None = None
    deep_research: bool = Field(
        False,
        description="Research each assigned specialist's area and the main competitors on the web "
        "first: on Azure OpenAI about 20 s and a few dozen Bing searches; on Tavily 1-2 minutes and "
        "150-450 credits. A follow-up reuses its session's research.",
    )
    research_provider: providers.Provider | None = Field(
        None, description="Where web research runs: azure (the default) or tavily, for demanding tasks."
    )

    @field_validator("context")
    @classmethod
    def _context_within_limits(cls, context):
        return check_context(context)


class EvaluateResponse(BaseModel):
    session_id: str
    objective: str
    assignments: dict[str, str]
    analyses: dict[str, str]
    review_history: list[dict[str, ReviewResult]]
    resolutions: list[Resolution]
    metrics: dict[str, NodeMetric]
    final_strategy: str
    research: DeepResearch | None = Field(None, description="The session's deep research, if any.")
    economic: EconomicData | None = Field(
        None, description="The official figures the session looked up on FRED, if FRED is set up."
    )
    guardrails: list[Flag] = Field(
        default_factory=list,
        description="Text that tried to instruct the agents, in the request or in the session's research: "
        "cut out of what the agents read.",
    )
    trace_id: str | None = Field(None, description="The run's trace in Langfuse, when it is set up (tracing.py).")
    trace_url: str | None = Field(None, description="Where to open that trace in Langfuse.")


@app.get("/health")
async def health():
    """Health check, with the reasoning efforts a request can choose, the
    configured ones it gets by default, where web research can run (Azure
    OpenAI, Tavily) and does by default, which look-ups are set up (FRED's
    figures, competitors' pages), and where sessions and reports are kept.
    The status is "degraded" while that database does not answer."""
    stored = await run_in_threadpool(storage.ping)
    return {
        "status": "healthy" if stored else "degraded",
        "service": SERVICE_NAME,
        "storage": {"kind": storage.kind, "ok": stored},
        "reasoning": {
            "adjustable": takes_reasoning_effort(),
            "efforts": list(EFFORTS),
            "specialist": default_effort(SPECIALIST),
            "chief": default_effort(CHIEF),
        },
        "research": {
            "providers": providers.available(),
            "default": providers.default(),
        },
        # Look-ups through MCP servers: FRED's official figures, and competitors' own pages (on Tavily).
        "lookups": {"fred": lookups.fred_configured(), "competitor_pages": lookups.tavily_configured()},
        # Model calls traced in Langfuse, with the prompts registered there (tracing.py).
        "tracing": {"langfuse": tracing.enabled(), "prompts": len(tracing.versions())},
        "voice": {"dictation": voice.available()},
    }


class Scenario(BaseModel):
    name: str = Field(description="The scenario file's name, without .json.")
    title: str = Field(description="A short title to show for it.")
    prompt: str
    context: RequestContext | None = None
    follow_up: str | None = Field(None, description="A follow-up to send after the first request.")


@app.get("/scenarios", response_model=list[Scenario])
async def list_scenarios():
    """The example startup scenarios (scenarios/*.json) a request can start from."""
    scenarios = []
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("title", path.stem.replace("_", " ").capitalize())
        scenarios.append(Scenario(name=path.stem, **data))
    return scenarios


@app.get("/templates", response_model=list[Template])
async def list_templates():
    """The decision templates (templates/*.json) a brief can be written from:
    each a request to fill in, with what to look up and ask for that decision."""
    return load_templates()


class Feedback(BaseModel):
    session_id: str = Field(pattern=SESSION_ID)
    trace_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$", description="The run's trace, from its response.")
    useful: bool = Field(description="Whether the founder found the strategy useful.")
    comment: str = Field("", max_length=MAX_FIELD_CHARS)


@app.post("/feedback", status_code=202)
def feedback(given: Feedback):
    """The founder's verdict on a strategy, as a score in Langfuse: `useful`
    (1 or 0) with the comment, on the run's trace, or on its session. Recorded
    only when Langfuse is set up; `recorded` says whether it was."""
    if not tracing.enabled():
        return {"recorded": False}
    comment = tracing.mask_text(given.comment.strip()) or None
    tracing.score("founder-feedback", 1 if given.useful else 0, trace_id=given.trace_id,
                  session_id=given.session_id, comment=comment, data_type="BOOLEAN")
    monitor.event("run", "feedback", f"The founder found the strategy {'useful' if given.useful else 'not useful'}.",
                  given.session_id)
    return {"recorded": True}


@app.get("/rates/{base}", response_model=Rates)
def exchange_rates(base: str):
    """Today's rates from `base` to the app's other currencies (rates.py), to
    fill in when the founder converts a report; the founder can change them."""
    if base not in CURRENCIES:
        raise HTTPException(status_code=422, detail=f"There is no currency called {base!r} here.")
    try:
        return rates_from(base)
    except RatesUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _diagram() -> str:
    """The graph as Mermaid, without LangGraph's own colours and markup, which the page styles."""
    text = graph.get_graph().draw_mermaid()
    text = re.sub(r"<p>__(start|end)__</p>", r"\1", text)
    text = re.sub(r":::\w+", "", text)
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("classDef"))


@app.get("/pipeline")
async def pipeline():
    """How the team works, for the How it works page: the graph as a Mermaid
    diagram, the specialists, and the rules and settings in force, so the page
    always shows what the code does."""
    return {
        "mermaid": _diagram(),
        "specialists": [
            {"name": role.name, "title": role.title, "focus": role.focus, "reads_competitors": role.name in COMPANY_READERS}
            for role in SPECIALISTS
        ],
        "rules": {
            "approval_score": APPROVAL_SCORE,
            "max_revisions": MAX_ITERATIONS,
            "max_critique_rounds": MAX_CRITIQUE_ROUNDS,
            "report_words": REPORT_WORDS,
            "strategy_words": STRATEGY_WORDS,
            "max_questions": brief_module.MAX_QUESTIONS,
            "max_facts": brief_module.MAX_FINDINGS,
            "max_competitors": deep_research.MAX_COMPANIES,
        },
    }


@app.get("/monitoring", response_model=Monitoring)
async def monitoring():
    """What the API has done since it started: evaluations, briefs and proposals,
    the time, calls and tokens of each step of the graph, and a log of recent
    events, warnings and errors. Kept in memory, so a restart empties it."""
    return monitor.snapshot()


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    """The monitor's counters and timings for Prometheus to scrape, in the
    text format, or OpenMetrics when the scraper asks for it."""
    encode, content_type = choose_encoder(request.headers.get("accept", ""))
    return Response(encode(monitor.metrics.registry), media_type=content_type)


class PrepareRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS, description="The founder's brief.")
    context: RequestContext | None = None
    template: str | None = Field(None, max_length=64, description="The template the brief was written from, by name.")
    reasoning: Reasoning | None = None
    research_provider: providers.Provider | None = Field(
        None, description="Where the web search runs: azure (the default) or tavily."
    )

    @field_validator("context")
    @classmethod
    def _context_within_limits(cls, context):
        return check_context(context)


@app.post("/brief/prepare", response_model=PreparedBrief)
async def prepare(request: PrepareRequest):
    """Prepare a brief before the team runs it. The Chief of Staff researches it
    on the web (Azure OpenAI's web search, or Tavily when asked), keeps the facts that bear on the
    decision with their sources, and asks up to three questions about what is
    missing; none when the brief is enough. Send the facts the founder keeps and
    their answers in the evaluation's `context`. About 20-30 s at the default
    efforts. A failed search does not fail the request: `research_note` says why
    there is no research. Missing credentials return 503, a failed LLM call 502.
    """
    template = None
    if request.template:
        template = next((each for each in load_templates() if each.name == request.template), None)
        if template is None:
            raise HTTPException(status_code=422, detail=f"There is no template called {request.template!r}.")
    await run_in_threadpool(_documents_found, request.context)
    started = time.perf_counter()
    try:
        tags = ["brief", *([f"template:{template.name}"] if template else [])]
        with reasoning(**_efforts(request.reasoning)), tracing.trace("brief", input=request.prompt, tags=tags):
            prepared = await run_in_threadpool(
                prepare_brief, request.prompt.strip(), request.context, template, request.research_provider
            )
    except LLMNotConfigured as error:
        monitor.count("briefs", ok=False)
        monitor.event("error", "brief", f"No brief could be prepared: {error}")
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLM_ERRORS as error:
        monitor.count("briefs", ok=False)
        logger.warning("Preparing a brief failed on an LLM call: %s", error)
        raise HTTPException(status_code=502, detail=failure(error)) from error
    monitor.count("briefs")
    facts = len(prepared.research.findings) if prepared.research else 0
    by = f" with {prepared.provider}" if prepared.provider else ""
    monitor.event(
        "brief", "brief",
        f"Prepared a brief{by} in {time.perf_counter() - started:.0f} s: "
        f"{facts} facts kept, {len(prepared.questions)} questions.",
    )
    return prepared


def _documents_found(context: RequestContext | None, upload_ids: list[str] = (), report_ids: list[str] = ()) -> None:
    """A 404 for a document a request names that is not there, before anything runs."""
    upload_ids = [*upload_ids, *(context.uploads if context else [])]
    report_ids = [*report_ids, *(context.reports if context else [])]
    try:
        library.sources(upload_ids, report_ids)
    except UploadNotFound as error:
        raise HTTPException(status_code=404, detail="One of the files is no longer kept; upload it again.") from error
    except ReportNotFound as error:
        raise HTTPException(status_code=404, detail="One of the earlier reports is not there.") from error


def _start(request: EvaluateRequest) -> tuple[str, dict, dict, list[Flag]]:
    """The session, the graph's input and its config for one request, and what
    in the request tried to instruct the agents (guardrails.py)."""
    session_id = request.session_id or str(uuid.uuid4())
    bind_session(session_id)
    flags = log_flags(
        scan(request.prompt, "your follow-up" if request.session_id else "your brief") + scan_context(request.context)
    )
    use = providers.chosen(request.research_provider)
    state = {"request": request.prompt, "deep": request.deep_research and use is not None}
    if use:
        state["research_provider"] = use
    if request.context:
        state["context"] = request.context
    return session_id, state, {"configurable": {"thread_id": session_id}}, flags


def _traced(request: EvaluateRequest, session_id: str) -> dict:
    """What an evaluation's trace in Langfuse is filed under: its session, the
    request, and tags and metadata to filter by (tracing.py)."""
    efforts = _efforts(request.reasoning)
    tags = ["evaluate", "follow-up" if request.session_id else "first-request"]
    if request.deep_research:
        tags.append(f"deep-research:{request.research_provider or providers.default()}")
    metadata = {f"reasoning_{role}": effort for role, effort in efforts.items() if effort}
    return {"session_id": session_id, "input": {"prompt": request.prompt, "context": request.context},
            "tags": tags, "metadata": metadata}


# The recommendation the strategy leads with, as Langfuse's verdict score.
_VERDICT = re.compile(r"\b(go with conditions|not yet|no[- ]go|go)\b", re.IGNORECASE)


def _verdict(strategy: str) -> str:
    found = _VERDICT.search(strategy[:300])
    return found.group(1).lower().replace(" ", "-") if found else "unclear"


def _score(run: tracing.Trace, result: dict, flags: list[Flag]) -> None:
    """The team's own judgements on the run, as scores on its trace: the Chief
    of Staff's review of each report (its last), whether every report passed
    first time, how many were revised, the conflicts settled, the verdict, the
    specialists that failed, and text that tried to instruct the agents."""
    if not run.id:
        return
    history = result.get("review_history") or []
    latest: dict = {}
    for round_ in history:
        latest.update(round_)
    for name, review in latest.items():
        run.score(f"review-{name}", review.score, comment=review.feedback or None)
    if latest:
        run.score("review-average", round(sum(r.score for r in latest.values()) / len(latest), 2))
    if history:
        first = history[0]
        run.score("approved-first-time", 1 if all(r.approved for r in first.values()) else 0, data_type="BOOLEAN")
    resolutions = result.get("resolutions") or []
    revised = {name for round_ in history[1:] for name in round_} | {
        resolution.revise for resolution in resolutions if resolution.revise
    }
    run.score("revisions", len(revised), comment=", ".join(sorted(revised)) or None)
    run.score("conflicts", len(resolutions))
    run.score("verdict", _verdict(result.get("final_strategy", "")), data_type="CATEGORICAL")
    failed = [name for name, text in (result.get("analyses") or {}).items() if text.startswith(GAP_PREFIX)]
    run.score("failed-specialists", len(failed), comment=", ".join(failed) or None)
    run.score("guardrail-flags", len(flags))


async def _finish(session_id: str, result: dict, flags: list[Flag], run: tracing.Trace | None = None) -> EvaluateResponse:
    """Record the session's report and answer with its results; on Langfuse,
    score the run and give the way to its trace."""
    # In a worker thread: the results name the founder's documents, read from the database.
    efforts = {role: effort for role in (SPECIALIST, CHIEF) if (effort := reasoning_effort(role))} \
        if takes_reasoning_effort() else {}
    await run_in_threadpool(lambda: store.record(session_id, SessionResults.from_state(result, efforts)))
    deep = result.get("deep_research")
    trace_id = trace_url = None
    if run is not None and run.id:
        run.output({"objective": result["plan"].objective, "strategy": result["final_strategy"]})
        await run_in_threadpool(_score, run, result, flags)
        trace_id, trace_url = run.id, await run_in_threadpool(run.url)
        if judge.enabled():
            judge.judge_later(run.id, session_id, result.get("venture") or result["request"], result["final_strategy"])
    return EvaluateResponse(
        trace_id=trace_id,
        trace_url=trace_url,
        session_id=session_id,
        objective=result["plan"].objective,
        assignments=result["assignments"],
        analyses=result["analyses"],
        review_history=result["review_history"],
        resolutions=result.get("resolutions", []),
        metrics=result.get("metrics", {}),
        final_strategy=result["final_strategy"],
        research=deep,
        economic=result.get("economic"),
        guardrails=[*flags, *(deep.flags if deep else [])],
    )


def _record(request: EvaluateRequest, session_id: str, started: float,
            response: EvaluateResponse | None = None, error: str | None = None) -> None:
    """Put an evaluation that ended in the monitor: what it ran, took and cost."""
    seconds = round(time.perf_counter() - started, 1)
    at = datetime.now(timezone.utc)
    if response is None:
        monitor.run(Run(session=session_id[:8], at=at, seconds=seconds, ok=False, error=error))
        return
    verdicts: dict[str, ReviewResult] = {}
    for review_round in response.review_history:
        verdicts.update(review_round)
    deep = response.research if request.deep_research else None
    calls = sum(metric.calls for metric in response.metrics.values())
    tokens = sum(metric.tokens for metric in response.metrics.values())
    monitor.run(Run(
        session=session_id[:8], at=at, seconds=seconds, ok=True,
        specialists=list(response.assignments), calls=calls, tokens=tokens,
        reviewed=len(verdicts), approved=sum(1 for review in verdicts.values() if review.approved),
        conflicts=len(response.resolutions),
        research=deep.providers[-1] if deep and deep.providers else None,
        searches=deep.searches if deep else 0, credits=deep.credits if deep else 0,
        nodes=response.metrics,
    ))
    monitor.event(
        "run", "evaluate",
        f"Finished in {seconds:.0f} s: {len(response.assignments)} specialists, {calls} model calls, {tokens:,} tokens.",
        session_id,
    )


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest):
    """Run the founding team against a startup request and return the analyses.

    Missing credentials return 503. An LLM call that still fails after its
    retries returns 502, so a provider problem never shows up as a 500. A file
    or earlier report in the context that is not there returns 404.
    """
    await run_in_threadpool(_documents_found, request.context)
    session_id, state, config, flags = _start(request)
    started = time.perf_counter()
    monitor.begin()
    try:
        # ainvoke runs the nodes in worker threads, so a run that takes minutes
        # does not block the event loop, and other requests are still served.
        # The threads inherit the request's reasoning efforts.
        with reasoning(**_efforts(request.reasoning)), tracing.trace("evaluate", **_traced(request, session_id)) as run:
            result = await graph.ainvoke(state, config)
            response = await _finish(session_id, result, flags, run)
    except LLMNotConfigured as error:
        monitor.event("error", "evaluate", f"No evaluation could run: {error}", session_id)
        _record(request, session_id, started, error=str(error))
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLM_ERRORS as error:
        logger.warning("Evaluation failed on an LLM call: %s", error)
        _record(request, session_id, started, error=failure(error))
        raise HTTPException(status_code=502, detail=failure(error)) from error
    except BaseException:  # anything else, a cancellation too: recorded, then raised (an error becomes a 500)
        _record(request, session_id, started, error="The evaluation failed unexpectedly.")
        raise
    _record(request, session_id, started, response)
    return response


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


@app.post("/evaluate/stream", response_class=StreamingResponse, responses={200: {"content": {"text/event-stream": {}}}})
async def evaluate_stream(request: EvaluateRequest):
    """Run the founding team like /evaluate, reporting its progress as it goes.

    The answer is a stream of server-sent events: `start` when an agent begins
    (`node`, and `at`, the seconds since the request began), `done` when it
    finishes (with a `summary` of what it did and the figures behind it), then
    one `result` with what /evaluate returns. A failure arrives as an `error`
    event (`status` 503 or 502, as /evaluate would answer, and `detail`), since
    the response has already begun.
    """
    await run_in_threadpool(_documents_found, request.context)
    session_id, state, config, flags = _start(request)

    async def events():
        began = time.perf_counter()
        monitor.begin()
        runs: Counter[str] = Counter()
        given: dict[str, dict] = {}  # the state each running node was given

        def at() -> float:
            return round(time.perf_counter() - began, 1)

        try:
            with reasoning(**_efforts(request.reasoning)), tracing.trace("evaluate", **_traced(request, session_id)) as run:
                async for _, task in graph.astream(state, config, stream_mode=["tasks"]):
                    node = task["name"]
                    if "input" in task:
                        runs[node] += 1
                        given[node] = task["input"]
                        monitor.event("start", node, "Started." if runs[node] == 1 else "Started again.", session_id)
                        yield _event("start", {"node": node, "at": at()})
                    elif not task.get("error"):
                        summary = summarize(node, task.get("result"), runs[node], given.get(node))
                        monitor.event("done", node, summary["summary"], session_id)
                        yield _event("done", {"node": node, "at": at(), **summary})
                response = await _finish(session_id, (await graph.aget_state(config)).values, flags, run)
        except LLMNotConfigured as error:
            monitor.event("error", "evaluate", f"No evaluation could run: {error}", session_id)
            _record(request, session_id, began, error=str(error))
            yield _event("error", {"status": 503, "detail": str(error)})
            return
        except LLM_ERRORS as error:
            logger.warning("Evaluation failed on an LLM call: %s", error)
            _record(request, session_id, began, error=failure(error))
            yield _event("error", {"status": 502, "detail": failure(error)})
            return
        except Exception:  # the status is already sent, so say what happened instead
            logger.exception("Evaluation failed")
            _record(request, session_id, began, error="The evaluation failed unexpectedly.")
            yield _event("error", {"status": 500, "detail": "The evaluation failed unexpectedly."})
            return
        except (asyncio.CancelledError, GeneratorExit):  # the browser went away mid-run
            _record(request, session_id, began, error="The connection closed before the evaluation finished.")
            raise
        _record(request, session_id, began, response)
        yield _event("result", response.model_dump(mode="json"))

    # No caching or proxy buffering, so each event reaches the browser as it happens.
    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ReportEdit(BaseModel):
    version: int = Field(description="The report version the edits were made to.")
    sections: list[ReportSection] = Field(min_length=1, max_length=MAX_SECTIONS)

    @field_validator("sections")
    @classmethod
    def _sections_within_limits(cls, sections):
        return check_sections(sections)


PartKey = Literal["executive", "market", "technical", "risk", "financial"]


class ProposalRequest(BaseModel):
    version: int = Field(description="The report version the request was made from.")
    reasoning: Reasoning | None = None
    currency: str | None = Field(
        None, description="For a new proposal: the currency to write it in (ISO 4217); else the report's."
    )

    @field_validator("currency")
    @classmethod
    def _known_currency(cls, code: str | None) -> str | None:
        if code is not None and code not in CURRENCIES:
            raise ValueError(f"{code} is not a currency the document can use.")
        return code


class ProposalRevision(ProposalRequest):
    instruction: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS, description="What to change, in the founder's words.")
    part: PartKey | None = Field(
        None, description="The part to revise; the parts written from it follow. None for all."
    )


class ProposalEdit(BaseModel):
    version: int = Field(description="The report version the edits were made to.")
    proposal: Proposal


class RevisionResult(BaseModel):
    draft: Draft = Field(description="The report as the revision would leave it; nothing is saved until accepted.")
    failed: list[str] = Field(
        default_factory=list, description="Titles of the parts that could not be revised; they keep their text."
    )
    guardrails: list[Flag] = Field(default_factory=list)


# Where a text is in a report: "title", "sections.strategy", "proposal.market.pricing_strategy".
TextPath = Annotated[
    str, Field(max_length=200, pattern=r"^(title|objective|sections\.[A-Za-z0-9_-]+|proposal(\.[A-Za-z0-9_]+)+)$")
]


class TextRevision(BaseModel):
    version: int
    path: TextPath
    instruction: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    passage: str | None = Field(None, max_length=MAX_FIELD_CHARS, description="Only this part of the text.")
    reasoning: Reasoning | None = None


class CurrencyChange(BaseModel):
    kind: Literal["currency"]
    to: str = Field(description="ISO 4217 code.")
    rate: float = Field(gt=0, lt=1e6, description="One unit of the document's currency, in `to`.")
    relabel: bool = Field(False, description="Show the amounts in `to` without converting them.")


class UnitsChange(BaseModel):
    kind: Literal["units"]
    to: Literal["metric", "imperial"]


class ReplaceChange(BaseModel):
    kind: Literal["replace"]
    find: str = Field(min_length=1, max_length=200)
    by: str = Field(max_length=200)
    match_case: bool = False
    whole_words: bool = True


class RedactChange(BaseModel):
    kind: Literal["redact"]
    terms: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=1, max_length=20)


class RemoveChange(BaseModel):
    kind: Literal["remove"]
    path: TextPath
    passage: str = Field(min_length=1, max_length=MAX_FIELD_CHARS)


class SettingsChange(BaseModel):
    kind: Literal["settings"]
    prepared_by: str = Field(min_length=1, max_length=80)
    hidden: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=30)


class DraftRequest(BaseModel):
    version: int = Field(description="The report version the change is made to.")
    change: Annotated[
        CurrencyChange | UnitsChange | ReplaceChange | RedactChange | RemoveChange | SettingsChange,
        Field(discriminator="kind"),
    ]


class Acceptance(BaseModel):
    version: int = Field(description="The report version the draft was made from.")
    content: ReportContent
    change: str = Field(min_length=1, max_length=300, description="What the change was, for the history.")

    @field_validator("content")
    @classmethod
    def _sections_within_limits(cls, content: ReportContent) -> ReportContent:
        check_sections(content.sections)
        return content


class Restore(BaseModel):
    version: int = Field(description="The report's current version.")


class ProposalResult(BaseModel):
    report: Report
    failed: list[str] = Field(
        description="Titles of the parts that could not be revised; they keep their text."
    )
    guardrails: list[Flag] = Field(
        default_factory=list,
        description="Text in the requested change or the edited report that tried to instruct the agents: "
        "cut out of what the agents read.",
    )


@app.exception_handler(ReportNotFound)
async def report_not_found(request, error: ReportNotFound):
    return JSONResponse(
        status_code=404,
        content={"detail": "No report for this session yet; run an evaluation first."},
    )


@app.exception_handler(ReportChanged)
async def report_changed(request, error: ReportChanged):
    return JSONResponse(
        status_code=409, content={"detail": f"{error} Reload it and make the change again."}
    )


# The report endpoints are plain functions, so FastAPI runs them in its thread
# pool: with a database each is a round trip, which must not hold up the loop.
@app.get("/reports", response_model=list[ReportSummary])
def list_reports():
    """Every session's report, the most recently changed first."""
    return store.summaries()


@app.get("/reports/{session_id}", response_model=Report)
def get_report(session_id: SessionId):
    """A session's report: one markdown section each for the strategy, the
    specialists' reports and the decisions on conflicts."""
    return store.get(session_id)


@app.delete("/reports/{session_id}", status_code=204)
async def delete_report(session_id: SessionId):
    """Delete a session's report, with its versions, the results it was built
    from and the team's saved state for the session, so nothing of it is kept
    to rebuild it from. 404 if there is no such report. The founder's uploaded
    files stay: another report may have worked from them."""
    bind_session(session_id)
    await run_in_threadpool(store.delete, session_id)
    if graph.checkpointer is not None:
        await graph.checkpointer.adelete_thread(session_id)
    monitor.event("document", "reports", "Deleted a report, with its versions and the session's saved state.", session_id)
    return Response(status_code=204)


@app.put("/reports/{session_id}", response_model=Report)
def save_report(session_id: SessionId, edit: ReportEdit):
    """Save edited sections. Returns 409 if the report changed since `version`."""
    return store.save(session_id, edit.version, edit.sections)


@app.post("/reports/{session_id}/reset", response_model=Report)
def reset_report(session_id: SessionId):
    """Rebuild the report from the session's latest results, dropping edits."""
    return store.reset(session_id)


def _report_at(session_id: str, version: int) -> Report:
    report = store.get(session_id)
    if report.version != version:
        raise ReportChanged(f"The report is at version {report.version}, not {version}.")
    return report


async def _write(report: Report, choice: Reasoning | None, instruction: str = "",
                 part: str | None = None) -> ProposalResult | RevisionResult:
    """Run the proposal writer off the event loop. A new proposal is saved; a
    revision comes back as a draft, to be seen before it is accepted."""
    started = time.perf_counter()
    doing = "Revising" if report.proposal else "Writing"
    # What the founder wrote that the writers read: the change asked for, and the edits.
    edits = "\n\n".join(section.body for section in report.sections) if report.edited else ""
    flags = log_flags(scan(instruction, "your requested change") + scan(edits, "your edits to the report"))
    name = "proposal-revision" if report.proposal else "proposal"
    with reasoning(**_efforts(choice)), tracing.trace(
        name, session_id=report.session_id, input=instruction or None, tags=[name, *([f"part:{part}"] if part else [])]
    ):
        try:
            proposal, failed = await run_in_threadpool(write_proposal, report, instruction, part)
        except LLMNotConfigured as error:
            monitor.count("proposals", ok=False)
            monitor.event("error", "proposal", f"{doing} the proposal could not start: {error}", report.session_id)
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ProposalNotWritten as error:
            monitor.count("proposals", ok=False)
            monitor.event("error", "proposal", f"{doing} the proposal failed: {error}", report.session_id)
            raise HTTPException(status_code=502, detail=f"{error} Try again.") from error
    if report.proposal and len(failed) == len(parts_to_write(report.proposal, part)):
        monitor.count("proposals", ok=False)
        monitor.event("error", "proposal", "Nothing could be revised: every LLM call failed.", report.session_id)
        raise HTTPException(status_code=502, detail="Nothing could be revised: every LLM call failed.")
    monitor.count("proposals")
    done = "Revised" if report.proposal else "Wrote"
    monitor.event(
        "proposal", "proposal",
        f"{done} the investment proposal in {time.perf_counter() - started:.0f} s"
        + (f"; {len(failed)} parts kept their text." if failed else "."),
        report.session_id,
    )
    if report.proposal:
        draft = document.draft(report, report.model_copy(update={"proposal": proposal}), _revised(part, failed),
                               allow_unchanged=True)
        return RevisionResult(draft=draft, failed=failed, guardrails=flags)
    saved = await run_in_threadpool(
        store.save_proposal, report.session_id, report.version, proposal, False,
        f"The agents wrote the investment proposal in {report.settings.currency}", report.settings,
    )
    return ProposalResult(report=saved, failed=failed, guardrails=flags)


def _revised(part: str | None, failed: list[str]) -> str:
    """What a revision did, for the preview and the history."""
    if part is None:
        said = "Every agent revised its part as you asked"
    else:
        followed = [TITLES[key] for key in parts_to_write(None, None) if key != part
                    and key in parts_to_write(Proposal.model_construct(), part)]
        said = f"The {OWNERS[part]} agent revised {TITLES[part]} as you asked"
        if followed:
            said += f", and {', '.join(followed)} followed"
    return said + (f"; {', '.join(failed)} kept their text." if failed else ".")


@app.post("/reports/{session_id}/proposal", response_model=ProposalResult)
async def write_report_proposal(session_id: SessionId, request: ProposalRequest):
    """Have the agents write the investment proposal from the report as it stands,
    replacing any proposal it has, in `currency` if given. Takes about two minutes."""
    bind_session(session_id)
    report = await run_in_threadpool(_report_at, session_id, request.version)
    settings = report.settings.model_copy(update={"currency": request.currency or report.settings.currency})
    return await _write(report.model_copy(update={"proposal": None, "settings": settings}), request.reasoning)


@app.post("/reports/{session_id}/proposal/revise", response_model=RevisionResult)
async def revise_report_proposal(session_id: SessionId, revision: ProposalRevision):
    """Apply the founder's instruction to one part of the proposal (or all of it):
    the part's agent rewrites it, then the parts written from it are brought into
    line. Returns a draft, saved only when accepted. A part whose call fails keeps
    its text and is listed in `failed`."""
    bind_session(session_id)
    report = await run_in_threadpool(_report_at, session_id, revision.version)
    if not report.proposal:
        raise HTTPException(status_code=404, detail="This report has no proposal yet; write it first.")
    return await _write(report, revision.reasoning, revision.instruction, revision.part)


@app.put("/reports/{session_id}/proposal", response_model=Report)
def save_report_proposal(session_id: SessionId, edit: ProposalEdit):
    """Save an edited proposal. Returns 409 if the report changed since `version`."""
    return store.save_proposal(session_id, edit.version, edit.proposal)


@app.post("/reports/{session_id}/revise", response_model=RevisionResult)
async def revise_report_text(session_id: SessionId, revision: TextRevision):
    """Rewrite one text of the report, or only a passage of it, as the founder
    asks: the agent who wrote it rewrites just that and leaves everything else
    alone. Returns a draft, saved only when accepted."""
    bind_session(session_id)
    report = await run_in_threadpool(_report_at, session_id, revision.version)
    try:
        current = document.text_at(report, revision.path)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="The report has no such text.") from error
    if revision.passage and revision.passage not in current:
        raise HTTPException(status_code=409, detail="That passage is no longer in the report. Reload it.")
    flags = log_flags(scan(revision.instruction, "your requested change"))
    with reasoning(**_efforts(revision.reasoning)), tracing.trace(
        "passage-revision", session_id=session_id, input=revision.instruction, tags=["passage-revision"]
    ):
        try:
            text = await run_in_threadpool(revise_text, report, revision.path, revision.instruction, revision.passage)
        except LLMNotConfigured as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except LLM_ERRORS as error:
            monitor.event("error", "proposal", f"Revising a passage failed: {error}", session_id)
            raise HTTPException(status_code=502, detail=failure(error)) from error
    where = document.label(report, revision.path)
    draft = document.draft(report, document.set_text(report, revision.path, text),
                           f"Rewrote {'a passage of ' if revision.passage else ''}{where} as you asked.",
                           allow_unchanged=True)
    monitor.event("proposal", "proposal", draft.summary, session_id)
    return RevisionResult(draft=draft, guardrails=flags)


@app.post("/reports/{session_id}/drafts", response_model=Draft)
def make_draft(session_id: SessionId, request: DraftRequest):
    """A change made exactly by code, as a draft to preview: the currency or the
    units converted, text replaced or redacted, a passage removed, or the
    document's settings. Nothing is saved until the draft is accepted."""
    report = _report_at(session_id, request.version)
    change = request.change
    try:
        match change:
            case CurrencyChange():
                if change.to not in CURRENCIES:
                    raise HTTPException(status_code=422, detail=f"{change.to} is not a currency the document can use.")
                return document.convert_currency(report, change.to, change.rate, change.relabel)
            case UnitsChange():
                return document.convert_units(report, change.to)
            case ReplaceChange():
                return document.replace(report, change.find, change.by, change.match_case, change.whole_words)
            case RedactChange():
                return document.redact(report, change.terms)
            case RemoveChange():
                return document.remove_passage(report, change.path, change.passage)
            case SettingsChange():
                settings = DocumentSettings(currency=report.settings.currency, prepared_by=change.prepared_by,
                                            hidden=change.hidden)
                return document.settings(report, settings)
    except document.Unchanged as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail="The report has no such text.") from error


@app.post("/reports/{session_id}/accept", response_model=Report)
def accept_draft(session_id: SessionId, acceptance: Acceptance):
    """Save a draft the founder accepted. Returns 409 if the report changed
    since the version the draft was made from; the version it replaces is kept."""
    return store.accept(session_id, acceptance.version, acceptance.content, acceptance.change)


@app.get("/reports/{session_id}/choices", response_model=Choices)
async def report_choices(session_id: SessionId):
    """What the founder chose and told the team while the report was built: the
    request and its details (target market, constraints, competition), their
    answers to the Chief of Staff's questions, the research facts they kept, their
    documents, and whether the team researched first and at what efforts. A report
    built before these were kept has them from the session's saved state, where
    there is one, else only what its results hold (`complete` false)."""
    results = await run_in_threadpool(store.results, session_id)
    if results.choices:
        return results.choices
    state = (await graph.aget_state({"configurable": {"thread_id": session_id}})).values if graph.checkpointer else {}
    if state.get("request"):
        return Choices.from_state(state, results.documents)
    return Choices(brief=results.venture, research=results.research, documents=results.documents, complete=False)


@app.get("/reports/{session_id}/versions", response_model=list[VersionSummary])
def report_versions(session_id: SessionId):
    """The report's current version and those kept before it, newest first,
    each with how it came about and how many fields it changed, where."""
    return store.versions(session_id, compare=document.places)


@app.get("/reports/{session_id}/versions/{version}/changes", response_model=document.VersionChanges)
def report_version_changes(session_id: SessionId, version: int):
    """What changed in a version, field by field, from the version before it."""
    return document.version_changes(*store.with_before(session_id, version))


@app.get("/reports/{session_id}/versions/{version}", response_model=Report)
def report_version(session_id: SessionId, version: int):
    """The report as it was at an earlier version."""
    return store.version(session_id, version)


@app.post("/reports/{session_id}/versions/{version}/restore", response_model=Report)
def restore_version(session_id: SessionId, version: int, restore: Restore):
    """Make an earlier version the newest. Returns 409 if the report changed
    since `restore.version`; the version it replaces is kept too."""
    return store.restore(session_id, restore.version, version)


@app.get(
    "/reports/{session_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_report(session_id: SessionId):
    """The report as a PDF: the investment proposal once it is written, else the
    team's report."""
    report = await run_in_threadpool(store.get, session_id)
    pdf = await run_in_threadpool(render_pdf, report)
    name = re.sub(r"[^A-Za-z0-9-]", "", session_id)[:8] or "report"
    kind = "investment-proposal" if report.proposal else "launch-report"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{kind}-{name}.pdf"'},
    )


@app.post(
    "/reports/{session_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def preview_report(session_id: SessionId, content: ReportContent):
    """A draft, or an earlier version, as a PDF, without saving anything."""
    report = await run_in_threadpool(store.get, session_id)
    check_sections(content.sections)
    pdf = await run_in_threadpool(render_pdf, report.model_copy(update=dict(content)))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="preview.pdf"'})


# ---- The founder's documents (library.py, extract.py) ----

class UploadResult(BaseModel):
    upload: UploadSummary
    guardrails: list[Flag] = Field(
        default_factory=list,
        description="Text in the file that tried to instruct the agents: cut out of what they read.",
    )


@app.post("/uploads", response_model=UploadResult, status_code=201)
async def upload_file(
    request: Request,
    name: Annotated[str, Query(min_length=1, max_length=255, description="The file's name, with its extension.")],
):
    """Upload a file for the team to work from: its bytes as the body, up to
    10 MB. PDF, Word, PowerPoint, Excel, OpenDocument, CSV, RTF, HTML, Markdown
    or text, told from the content. Only its text is kept, as passages with
    where each is. Returns its id, to name in a request's `context.uploads` or
    a question's `uploads`, and what was read. A file that cannot be read
    returns 422 with why."""
    data = await request.body()
    try:
        read = await run_in_threadpool(extract, name, data)
    except Unreadable as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    upload = await run_in_threadpool(uploads.add, name, len(data), read)
    text = "\n\n".join(passage.text for passage in read.passages)
    flags = log_flags(scan(text, f"your file {upload.name}"))
    monitor.event("document", "uploads", f"Read {upload.name}: {read.kind}, {read.parts}.")
    return UploadResult(upload=summary_of(upload), guardrails=flags)


@app.get("/uploads/{upload_id}", response_model=UploadSummary)
def get_upload(upload_id: Annotated[str, InPath(pattern=library.UPLOAD_ID)]):
    """What was read of an uploaded file."""
    try:
        return summary_of(uploads.get(upload_id))
    except UploadNotFound as error:
        raise HTTPException(status_code=404, detail="This file is no longer kept; upload it again.") from error


class Transcript(BaseModel):
    text: str


@app.post("/transcribe", response_model=Transcript)
async def transcribe(request: Request):
    """The founder's dictation, written down in English: the recording as the
    body (WebM, Ogg, MP4 or M4A, MP3, WAV or FLAC, as its Content-Type says), up
    to 10 MB, sent to Azure OpenAI's Whisper deployment, which translates speech
    in any language into English text, and not kept. 503 without Azure OpenAI,
    415 for a format it does not take, 422 for an empty recording, 502 when the
    call fails, with what Azure answered."""
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=422, detail="The recording is empty.")
    kind = request.headers.get("content-type", "")
    try:
        with tracing.trace("transcribe", input={"audio": f"{len(audio):,} bytes of {kind or 'audio'}"},
                           tags=["voice"]) as run:
            text = await run_in_threadpool(voice.transcribe, audio, kind)
            run.output(text)
    except voice.VoiceNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except voice.UnsupportedAudio as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except LLM_ERRORS as error:
        monitor.event("error", "voice", f"Dictation failed: {error}"[:500])
        raise HTTPException(status_code=502, detail=f"The speech-to-text call failed: {voice.why(error)}") from error
    monitor.event("run", "voice", f"Wrote down {len(text.split())} words from {len(audio):,} bytes of audio.")
    return Transcript(text=text)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_FIELD_CHARS)
    uploads: list[Annotated[str, Field(pattern=library.UPLOAD_ID)]] = Field(default_factory=list, max_length=5)
    reports: list[Annotated[str, Field(pattern=SESSION_ID)]] = Field(default_factory=list, max_length=5)
    reasoning: Reasoning | None = None


class AskResult(Answered):
    guardrails: list[Flag] = Field(default_factory=list)


def _ask(system: str, human: str) -> Answer:
    with track("ask", {}) as tracker:
        return structured_invoke(Answer, [SystemMessage(system), HumanMessage(human)], tracker, CHIEF, "documents/answer")


@app.post("/ask", response_model=AskResult)
async def ask(question: Question):
    """Ask the Chief of Staff a question about uploaded files and reports from
    this app. It answers from their passages alone, citing each one it uses
    ([D1 · page 3], [R1 · Launch Strategy]), and says what they do not cover.
    About 10-20 s at the default efforts."""
    if not question.uploads and not question.reports:
        raise HTTPException(status_code=422, detail="Name at least one file or report to ask about.")
    await run_in_threadpool(_documents_found, None, question.uploads, question.reports)
    flags = log_flags(scan(question.question, "your question"))
    started = time.perf_counter()
    with reasoning(**_efforts(question.reasoning)), tracing.trace("question", input=question.question, tags=["question"]):
        try:
            answered = await run_in_threadpool(
                library.answer, question.question.strip(), question.uploads, question.reports, _ask
            )
        except LLMNotConfigured as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except LLM_ERRORS as error:
            monitor.event("error", "ask", f"Answering a question failed: {error}")
            raise HTTPException(status_code=502, detail=failure(error)) from error
    count = len(question.uploads) + len(question.reports)
    monitor.event(
        "document", "ask",
        f"Answered a question about {count} document{'s' if count != 1 else ''} in "
        f"{time.perf_counter() - started:.0f} s, citing {len(answered.sources)} passages.",
    )
    return AskResult(**answered.model_dump(), guardrails=flags)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
