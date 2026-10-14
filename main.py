import logging

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import DEBUG_MODE
from graph import build_graph
from state import RequestContext

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


class EvaluateResponse(BaseModel):
    objective: str
    assignments: dict[str, str]
    analyses: dict[str, str]


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": SERVICE_NAME}


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest):
    """Run the founding team against a startup request and return the analyses."""
    state = {"request": request.prompt}
    if request.context:
        state["context"] = request.context

    try:
        result = graph.invoke(state)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return EvaluateResponse(
        objective=result["plan"].objective,
        assignments=result["assignments"],
        analyses=result["analyses"],
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
