import asyncio
import json
import logging
import re
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi import Path as InPath
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_client.exposition import choose_encoder
from pydantic import BaseModel, Field, field_validator

import brief as brief_module
import deep_research
from agents.chief_of_staff import APPROVAL_SCORE, STRATEGY_WORDS
from agents.proposal_writer import ProposalNotWritten, parts_to_write, write_proposal
from agents.roles import COMPANY_READERS, REPORT_WORDS, SPECIALISTS
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
from graph import SERDE, build_graph
from llm import (
    CHIEF,
    EFFORTS,
    LLM_ERRORS,
    SPECIALIST,
    Effort,
    LLMNotConfigured,
    default_effort,
    reasoning,
    takes_reasoning_effort,
)
from monitor import MAX_EVENTS, MAX_RUNS, Monitoring, MonitorHandler, Run, monitor
from observability import REQUEST_HEADER, RequestContextMiddleware, bind_session, configure_logging
from persistence import open_storage
from progress import summarize
from proposal import Proposal
from report_pdf import render_pdf
from reports import (
    Report,
    ReportChanged,
    ReportNotFound,
    ReportSection,
    ReportSummary,
    SessionResults,
    store,
)
import providers
from security import (
    MAX_PROMPT_CHARS,
    MAX_SECTIONS,
    SESSION_ID,
    Guard,
    GuardMiddleware,
    check_context,
    check_sections,
)
from state import DeepResearch, NodeMetric, RequestContext, Resolution, ReviewResult

SERVICE_NAME = "AI Startup Co-Founder Team"
SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"

configure_logging(logging.DEBUG if DEBUG_MODE else logging.INFO, LOG_FORMAT)
logger = logging.getLogger(__name__)
# The monitor's log gets the app's warnings and errors, and the model client's retries.
logging.getLogger().addHandler(MonitorHandler(monitor))

# Sessions, reports and the Monitor's history: in PostgreSQL when DATABASE_URL
# is set, so they survive a restart, else in memory.
storage = open_storage(DATABASE_URL, SERDE)
store.use(storage.reports)
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
    logger.info("Sessions and reports are kept in %s; the API is %s.", storage.where, access)
    yield
    await storage.close()


app = FastAPI(
    title=SERVICE_NAME,
    description="Multi-agent founding team that evaluates startup ideas",
    version="0.1.0",
    lifespan=lifespan,
)
# The key, the size, the rates and the runs, checked before a route (security.py).
guard = Guard(API_KEY, MAX_REQUEST_BYTES, REQUESTS_PER_MINUTE, RUNS_PER_HOUR, MAX_CONCURRENT_RUNS)
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


@app.get("/health")
async def health():
    """Health check, with the reasoning efforts a request can choose, the
    configured ones it gets by default, where web research can run (Azure
    OpenAI, Tavily) and does by default, and where sessions and reports are kept.
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
    started = time.perf_counter()
    try:
        with reasoning(**_efforts(request.reasoning)):
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
        raise HTTPException(status_code=502, detail=f"The LLM call failed: {error}") from error
    monitor.count("briefs")
    facts = len(prepared.research.findings) if prepared.research else 0
    by = f" with {prepared.provider}" if prepared.provider else ""
    monitor.event(
        "brief", "brief",
        f"Prepared a brief{by} in {time.perf_counter() - started:.0f} s: "
        f"{facts} facts kept, {len(prepared.questions)} questions.",
    )
    return prepared


def _start(request: EvaluateRequest) -> tuple[str, dict, dict]:
    """The session, the graph's input and its config for one request."""
    session_id = request.session_id or str(uuid.uuid4())
    bind_session(session_id)
    use = providers.chosen(request.research_provider)
    state = {"request": request.prompt, "deep": request.deep_research and use is not None}
    if use:
        state["research_provider"] = use
    if request.context:
        state["context"] = request.context
    return session_id, state, {"configurable": {"thread_id": session_id}}


async def _finish(session_id: str, result: dict) -> EvaluateResponse:
    """Record the session's report and answer with its results."""
    await run_in_threadpool(store.record, session_id, SessionResults.from_state(result))
    return EvaluateResponse(
        session_id=session_id,
        objective=result["plan"].objective,
        assignments=result["assignments"],
        analyses=result["analyses"],
        review_history=result["review_history"],
        resolutions=result.get("resolutions", []),
        metrics=result.get("metrics", {}),
        final_strategy=result["final_strategy"],
        research=result.get("deep_research"),
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
    retries returns 502, so a provider problem never shows up as a 500.
    """
    session_id, state, config = _start(request)
    started = time.perf_counter()
    monitor.begin()
    try:
        # ainvoke runs the nodes in worker threads, so a run that takes minutes
        # does not block the event loop, and other requests are still served.
        # The threads inherit the request's reasoning efforts.
        with reasoning(**_efforts(request.reasoning)):
            result = await graph.ainvoke(state, config)
        response = await _finish(session_id, result)
    except LLMNotConfigured as error:
        monitor.event("error", "evaluate", f"No evaluation could run: {error}", session_id)
        _record(request, session_id, started, error=str(error))
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLM_ERRORS as error:
        logger.warning("Evaluation failed on an LLM call: %s", error)
        _record(request, session_id, started, error=f"The LLM call failed: {error}")
        raise HTTPException(status_code=502, detail=f"The LLM call failed: {error}") from error
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
    session_id, state, config = _start(request)

    async def events():
        began = time.perf_counter()
        monitor.begin()
        runs: Counter[str] = Counter()
        given: dict[str, dict] = {}  # the state each running node was given

        def at() -> float:
            return round(time.perf_counter() - began, 1)

        try:
            with reasoning(**_efforts(request.reasoning)):
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
            response = await _finish(session_id, (await graph.aget_state(config)).values)
        except LLMNotConfigured as error:
            monitor.event("error", "evaluate", f"No evaluation could run: {error}", session_id)
            _record(request, session_id, began, error=str(error))
            yield _event("error", {"status": 503, "detail": str(error)})
            return
        except LLM_ERRORS as error:
            logger.warning("Evaluation failed on an LLM call: %s", error)
            _record(request, session_id, began, error=f"The LLM call failed: {error}")
            yield _event("error", {"status": 502, "detail": f"The LLM call failed: {error}"})
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


class ProposalRevision(ProposalRequest):
    instruction: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS, description="What to change, in the founder's words.")
    part: PartKey | None = Field(
        None, description="The part to revise; the parts written from it follow. None for all."
    )


class ProposalEdit(BaseModel):
    version: int = Field(description="The report version the edits were made to.")
    proposal: Proposal


class ProposalResult(BaseModel):
    report: Report
    failed: list[str] = Field(
        description="Titles of the parts that could not be revised; they keep their text."
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
                 part: str | None = None) -> ProposalResult:
    """Run the proposal writer off the event loop and save what it wrote."""
    started = time.perf_counter()
    doing = "Revising" if report.proposal else "Writing"
    with reasoning(**_efforts(choice)):
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
    saved = await run_in_threadpool(store.save_proposal, report.session_id, report.version, proposal, False)
    monitor.count("proposals")
    done = "Revised" if report.proposal else "Wrote"
    monitor.event(
        "proposal", "proposal",
        f"{done} the investment proposal in {time.perf_counter() - started:.0f} s"
        + (f"; {len(failed)} parts kept their text." if failed else "."),
        report.session_id,
    )
    return ProposalResult(report=saved, failed=failed)


@app.post("/reports/{session_id}/proposal", response_model=ProposalResult)
async def write_report_proposal(session_id: SessionId, request: ProposalRequest):
    """Have the agents write the investment proposal from the report as it stands,
    replacing any proposal it has. Takes about two minutes."""
    bind_session(session_id)
    report = await run_in_threadpool(_report_at, session_id, request.version)
    return await _write(report.model_copy(update={"proposal": None}), request.reasoning)


@app.post("/reports/{session_id}/proposal/revise", response_model=ProposalResult)
async def revise_report_proposal(session_id: SessionId, revision: ProposalRevision):
    """Apply the founder's instruction to one part of the proposal (or all of it):
    the part's agent rewrites it, then the parts written from it are brought into
    line. A part whose call fails keeps its text and is listed in `failed`."""
    bind_session(session_id)
    report = await run_in_threadpool(_report_at, session_id, revision.version)
    if not report.proposal:
        raise HTTPException(status_code=404, detail="This report has no proposal yet; write it first.")
    return await _write(report, revision.reasoning, revision.instruction, revision.part)


@app.put("/reports/{session_id}/proposal", response_model=Report)
def save_report_proposal(session_id: SessionId, edit: ProposalEdit):
    """Save an edited proposal. Returns 409 if the report changed since `version`."""
    return store.save_proposal(session_id, edit.version, edit.proposal)


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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
