import logging
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import DEBUG_MODE
from graph import build_graph
from state import NodeMetric, RequestContext, Resolution, ReviewResult

SERVICE_NAME = "AI Startup Co-Founder Team"

logging.basicConfig(
    level=logging.DEBUG if DEBUG_MODE else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(
    title=SERVICE_NAME,
    description="Multi-agent founding team that evaluates startup ideas",
    version="0.1.0",
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
    """Run the founding team against a startup request and return the analyses."""
    session_id = request.session_id or str(uuid.uuid4())
    state = {"request": request.prompt}
    if request.context:
        state["context"] = request.context

    config = {"configurable": {"thread_id": session_id}}
    try:
        result = graph.invoke(state, config)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
