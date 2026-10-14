"""Shared state passed between the nodes of the workflow.

`RequestContext` is the optional detail a founder can attach to a request.
`WorkflowState` is what flows through the graph: the request, that context, and
the analyses the specialists produce, keyed by specialist name.
"""

from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class RequestContext(BaseModel):
    """Optional detail that sharpens a founder's request."""

    target_market: str | None = Field(default=None)
    constraints: str | None = Field(default=None)
    competitive_landscape: str | None = Field(default=None)

    def as_prompt(self) -> str:
        """Render the set fields as prompt lines, or an empty string if none are set."""
        labels = {
            "target_market": "Target market",
            "constraints": "Constraints",
            "competitive_landscape": "Competitive landscape",
        }
        lines = [f"{labels[name]}: {value}" for name, value in self.model_dump().items() if value]
        return "\n".join(lines)


def _merge_analyses(current: dict, update: dict) -> dict:
    """Combine analyses by specialist name, so parallel specialists can each add one."""
    return {**current, **update}


class WorkflowState(TypedDict, total=False):
    """The state that flows through the graph."""

    request: str
    context: RequestContext
    analyses: Annotated[dict[str, str], _merge_analyses]
