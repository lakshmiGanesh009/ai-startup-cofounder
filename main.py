import json
import logging
import re
import uuid
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agents.proposal_writer import ProposalNotWritten, parts_to_write, write_proposal
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
from state import NodeMetric, RequestContext, Resolution, ReviewResult

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


class EvaluateResponse(BaseModel):
    session_id: str
    objective: str
    assignments: dict[str, str]
    analyses: dict[str, str]
    review_history: list[dict[str, ReviewResult]]
    resolutions: list[Resolution]
    metrics: dict[str, NodeMetric]
    final_strategy: str


@app.get("/health")
async def health():
    """Health check, with the reasoning efforts a request can choose and the
    configured ones it gets by default."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "reasoning": {
            "adjustable": takes_reasoning_effort(),
            "efforts": list(EFFORTS),
            "specialist": default_effort(SPECIALIST),
            "chief": default_effort(CHIEF),
        },
    }


class Scenario(BaseModel):
    name: str = Field(description="The scenario file's name, without .json.")
    prompt: str
    context: RequestContext | None = None
    follow_up: str | None = Field(None, description="A follow-up to send after the first request.")


@app.get("/scenarios", response_model=list[Scenario])
async def list_scenarios():
    """The example startup scenarios (scenarios/*.json) a request can start from."""
    return [
        Scenario(name=path.stem, **json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(SCENARIO_DIR.glob("*.json"))
    ]


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest):
    """Run the founding team against a startup request and return the analyses.

    Missing credentials return 503. An LLM call that still fails after its
    retries returns 502, so a provider problem never shows up as a 500.
    """
    session_id = request.session_id or str(uuid.uuid4())
    state = {"request": request.prompt}
    if request.context:
        state["context"] = request.context

    config = {"configurable": {"thread_id": session_id}}
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
