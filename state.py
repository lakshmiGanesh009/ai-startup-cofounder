"""Shared state passed between the nodes of the workflow.

`RequestContext` is the optional detail a founder can attach to a request.
`WorkflowState` is what flows through the graph: the request, that context, and
the analyses the specialists produce, keyed by specialist name.
"""

from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class Task(BaseModel):
    """One specialist's assignment within a delegation plan."""

    specialist: str = Field(description="The specialist's name, e.g. marketing.")
    task: str = Field(description="What that specialist should work on.")


class DelegationPlan(BaseModel):
    """The Chief of Staff's plan: an objective and one task per needed specialist."""

    objective: str = Field(description="The goal of the whole evaluation.")
    tasks: list[Task] = Field(
        default_factory=list,
        description="One entry per specialist the request needs; omit the rest.",
    )

    def assignments(self) -> dict[str, str]:
        """Tasks keyed by specialist, with repeats for one specialist joined."""
        merged: dict[str, str] = {}
        for item in self.tasks:
            if item.specialist in merged:
                merged[item.specialist] = f"{merged[item.specialist]}\n{item.task}"
            else:
                merged[item.specialist] = item.task
        return merged


class ReviewResult(BaseModel):
    """The Chief of Staff's verdict on one specialist report."""

    approved: bool = Field(description="True if the report is good enough to keep.")
    score: int = Field(description="Quality from 1 (poor) to 5 (excellent).")
    feedback: str = Field(description="What to improve; empty when approved.")


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


def _append_review(current: list, update: list) -> list:
    """Append each review round to the history."""
    return current + update


class WorkflowState(TypedDict, total=False):
    """The state that flows through the graph."""

    request: str
    context: RequestContext
    plan: DelegationPlan
    assignments: dict[str, str]
    analyses: Annotated[dict[str, str], _merge_analyses]
    reviews: dict[str, ReviewResult]
    revisions: dict[str, str]
    iteration: int
    review_history: Annotated[list[dict[str, ReviewResult]], _append_review]
    final_strategy: str
