import logging
import re
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agents.report_writer import write_detailed
from config import CORS_ORIGINS, DEBUG_MODE
from graph import build_graph
from llm import LLM_ERRORS, LLMNotConfigured
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


class EvaluateRequest(BaseModel):
    prompt: str
    context: RequestContext | None = None
    session_id: str | None = None


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
    """Health check endpoint."""
    return {"status": "healthy", "service": SERVICE_NAME}


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


class DetailedReport(BaseModel):
    report: Report
    failed: list[str] = Field(
        description="Titles of the sections that could not be expanded; they keep their text."
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


@app.post("/reports/{session_id}/detailed", response_model=DetailedReport)
async def detail_report(session_id: str):
    """Have each specialist expand its section and the Chief of Staff the
    strategy. Takes about a minute; a section whose call fails keeps its text."""
    report = store.get(session_id)
    try:
        bodies, failed = await run_in_threadpool(write_detailed, report)
    except LLMNotConfigured as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not bodies:
        raise HTTPException(
            status_code=502, detail="The detailed version could not be written: every LLM call failed."
        )
    return DetailedReport(
        report=store.apply_detailed(session_id, report.version, bodies), failed=failed
    )


@app.get(
    "/reports/{session_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_report(session_id: str):
    """The report as a PDF."""
    report = store.get(session_id)
    pdf = await run_in_threadpool(render_pdf, report)
    name = re.sub(r"[^A-Za-z0-9-]", "", session_id)[:8] or "report"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="launch-report-{name}.pdf"'},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
