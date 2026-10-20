import json
import logging
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agents.proposal_writer import ProposalNotWritten, parts_to_write, write_proposal
from brief import PreparedBrief, Template, load_templates, prepare_brief
from config import CORS_ORIGINS, DEBUG_MODE
from graph import build_graph
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
from state import DeepResearch, NodeMetric, RequestContext, Resolution, ReviewResult

SERVICE_NAME = "AI Startup Co-Founder Team"
SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"

logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=SERVICE_NAME,
    description="Multi-agent founding team that evaluates startup ideas",
    version="0.1.0",
)
# Lets a browser frontend on another origin (the Next.js app) call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)

graph = build_graph()


class Reasoning(BaseModel):
    """How hard the models reason for one request; a role left out keeps the
    configured effort. Higher efforts give more considered answers but take
    longer: at "high" an evaluation takes 5 to 10 minutes. Azure OpenAI only."""

    specialist: Effort | None = Field(None, description="The four specialists, and their critiques.")
    chief: Effort | None = Field(None, description="The Chief of Staff's plan, reviews, decisions and summaries.")


def _efforts(choice: Reasoning | None) -> dict:
    return choice.model_dump() if choice else {}


class EvaluateRequest(BaseModel):
    prompt: str
    context: RequestContext | None = None
    session_id: str | None = None
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
    configured ones it gets by default, and where web research can run
    (Azure OpenAI, Tavily) and does by default."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
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


class PrepareRequest(BaseModel):
    prompt: str = Field(min_length=1, description="The founder's brief.")
    context: RequestContext | None = None
    template: str | None = Field(None, description="The template the brief was written from, by name.")
    reasoning: Reasoning | None = None
    research_provider: providers.Provider | None = Field(
        None, description="Where the web search runs: azure (the default) or tavily."
    )


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
    try:
        with reasoning(**_efforts(request.reasoning)):
            return await run_in_threadpool(
                prepare_brief, request.prompt.strip(), request.context, template, request.research_provider
            )
    except LLMNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLM_ERRORS as error:
        logger.warning("Preparing a brief failed on an LLM call: %s", error)
        raise HTTPException(status_code=502, detail=f"The LLM call failed: {error}") from error


def _start(request: EvaluateRequest) -> tuple[str, dict, dict]:
    """The session, the graph's input and its config for one request."""
    session_id = request.session_id or str(uuid.uuid4())
    use = providers.chosen(request.research_provider)
    state = {"request": request.prompt, "deep": request.deep_research and use is not None}
    if use:
        state["research_provider"] = use
    if request.context:
        state["context"] = request.context
    return session_id, state, {"configurable": {"thread_id": session_id}}


def _finish(session_id: str, result: dict) -> EvaluateResponse:
    """Record the session's report and answer with its results."""
    store.record(session_id, SessionResults.from_state(result))
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


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest):
    """Run the founding team against a startup request and return the analyses.

    Missing credentials return 503. An LLM call that still fails after its
    retries returns 502, so a provider problem never shows up as a 500.
    """
    session_id, state, config = _start(request)
    try:
        # ainvoke runs the nodes in worker threads, so a run that takes minutes
        # does not block the event loop, and other requests are still served.
        # The threads inherit the request's reasoning efforts.
        with reasoning(**_efforts(request.reasoning)):
            result = await graph.ainvoke(state, config)
    except LLMNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLM_ERRORS as error:
        logger.warning("Evaluation failed on an LLM call: %s", error)
        raise HTTPException(status_code=502, detail=f"The LLM call failed: {error}") from error
    return _finish(session_id, result)


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
                        yield _event("start", {"node": node, "at": at()})
                    elif not task.get("error"):
                        summary = summarize(node, task.get("result"), runs[node], given.get(node))
                        yield _event("done", {"node": node, "at": at(), **summary})
            response = _finish(session_id, (await graph.aget_state(config)).values)
        except LLMNotConfigured as error:
            yield _event("error", {"status": 503, "detail": str(error)})
            return
        except LLM_ERRORS as error:
            logger.warning("Evaluation failed on an LLM call: %s", error)
            yield _event("error", {"status": 502, "detail": f"The LLM call failed: {error}"})
            return
        except Exception:  # the status is already sent, so say what happened instead
            logger.exception("Evaluation failed")
            yield _event("error", {"status": 500, "detail": "The evaluation failed unexpectedly."})
            return
        yield _event("result", response.model_dump(mode="json"))

    # No caching or proxy buffering, so each event reaches the browser as it happens.
    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ReportEdit(BaseModel):
    version: int = Field(description="The report version the edits were made to.")
    sections: list[ReportSection] = Field(min_length=1)


PartKey = Literal["executive", "market", "technical", "risk", "financial"]


class ProposalRequest(BaseModel):
    version: int = Field(description="The report version the request was made from.")
    reasoning: Reasoning | None = None


class ProposalRevision(ProposalRequest):
    instruction: str = Field(min_length=1, description="What to change, in the founder's words.")
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


@app.get("/reports", response_model=list[ReportSummary])
async def list_reports():
    """Every session's report, the most recently changed first."""
    return store.summaries()


@app.get("/reports/{session_id}", response_model=Report)
async def get_report(session_id: str):
    """A session's report: one markdown section each for the strategy, the
    specialists' reports and the decisions on conflicts."""
    return store.get(session_id)


@app.put("/reports/{session_id}", response_model=Report)
async def save_report(session_id: str, edit: ReportEdit):
    """Save edited sections. Returns 409 if the report changed since `version`."""
    return store.save(session_id, edit.version, edit.sections)


@app.post("/reports/{session_id}/reset", response_model=Report)
async def reset_report(session_id: str):
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
    with reasoning(**_efforts(choice)):
        try:
            proposal, failed = await run_in_threadpool(write_proposal, report, instruction, part)
        except LLMNotConfigured as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except ProposalNotWritten as error:
            raise HTTPException(status_code=502, detail=f"{error} Try again.") from error
    if report.proposal and len(failed) == len(parts_to_write(report.proposal, part)):
        raise HTTPException(status_code=502, detail="Nothing could be revised: every LLM call failed.")
    saved = store.save_proposal(report.session_id, report.version, proposal, edited=False)
    return ProposalResult(report=saved, failed=failed)


@app.post("/reports/{session_id}/proposal", response_model=ProposalResult)
async def write_report_proposal(session_id: str, request: ProposalRequest):
    """Have the agents write the investment proposal from the report as it stands,
    replacing any proposal it has. Takes about two minutes."""
    report = _report_at(session_id, request.version)
    return await _write(report.model_copy(update={"proposal": None}), request.reasoning)


@app.post("/reports/{session_id}/proposal/revise", response_model=ProposalResult)
async def revise_report_proposal(session_id: str, revision: ProposalRevision):
    """Apply the founder's instruction to one part of the proposal (or all of it):
    the part's agent rewrites it, then the parts written from it are brought into
    line. A part whose call fails keeps its text and is listed in `failed`."""
    report = _report_at(session_id, revision.version)
    if not report.proposal:
        raise HTTPException(status_code=404, detail="This report has no proposal yet; write it first.")
    return await _write(report, revision.reasoning, revision.instruction, revision.part)


@app.put("/reports/{session_id}/proposal", response_model=Report)
async def save_report_proposal(session_id: str, edit: ProposalEdit):
    """Save an edited proposal. Returns 409 if the report changed since `version`."""
    return store.save_proposal(session_id, edit.version, edit.proposal)


@app.get(
    "/reports/{session_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_report(session_id: str):
    """The report as a PDF: the investment proposal once it is written, else the
    team's report."""
    report = store.get(session_id)
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
