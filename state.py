"""Shared state passed between the nodes of the workflow.

`RequestContext` is the optional detail a founder can attach to a request.
`WorkflowState` is what flows through the graph: the request, that context, the
delegation plan, the analyses the specialists produce (keyed by specialist
name), the reviews, conflicts and resolutions, and per-node metrics.
"""

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

# The specialists' keys, as in agents/roles.py. Structured outputs that name a
# specialist use this type, so the model can only name one of the four.
SpecialistName = Literal["marketing", "finance", "technical", "risk"]


class Task(BaseModel):
    """One specialist's assignment within a delegation plan."""

    specialist: SpecialistName = Field(description="The specialist to assign.")
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


class NodeMetric(BaseModel):
    """What one node cost: LLM calls, wall-clock seconds, and tokens."""

    calls: int = 0
    seconds: float = 0.0
    tokens: int = 0

    def add(self, other: "NodeMetric") -> "NodeMetric":
        return NodeMetric(
            calls=self.calls + other.calls,
            seconds=round(self.seconds + other.seconds, 3),
            tokens=self.tokens + other.tokens,
        )


class ReviewResult(BaseModel):
    """The Chief of Staff's verdict on one specialist report."""

    approved: bool = Field(description="True if the report is good enough to keep.")
    score: int = Field(description="Quality from 1 (poor) to 5 (excellent).")
    feedback: str = Field(description="What to improve; empty when approved.")


class Conflict(BaseModel):
    """A clash one specialist sees between its area and another's report."""

    raised_by: SpecialistName = Field(description="The specialist flagging the conflict.")
    about: SpecialistName = Field(description="The specialist whose report it clashes with.")
    issue: str = Field(description="The clash, in one sentence.")


class SpecialistCritique(BaseModel):
    """One specialist's conflicts with the others; empty when it sees none."""

    conflicts: list[Conflict] = Field(default_factory=list)


class Resolution(BaseModel):
    """The Chief of Staff's decision on one conflict."""

    conflict: Conflict
    decision: str = Field(description="How the clash is settled.")
    revise: Literal[SpecialistName, ""] = Field(
        description="The specialist who should revise their report, or empty if none."
    )


class Resolutions(BaseModel):
    """The Chief of Staff's decisions on one critique round's conflicts."""

    resolutions: list[Resolution] = Field(
        default_factory=list,
        description="One decision per distinct conflict; a clash raised twice is one conflict.",
    )


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


def _append(current: list, update: list) -> list:
    """Append each round's entries, so earlier rounds of a request are kept."""
    return current + update


def _merge_metrics(current: dict, update: dict) -> dict:
    """Sum each node's metrics as the nodes report them."""
    merged = dict(current)
    for node, metric in update.items():
        merged[node] = merged[node].add(metric) if node in merged else metric
    return merged


class WorkflowState(TypedDict, total=False):
    """The state that flows through the graph."""

    request: str
    # The session's first request, kept so a follow-up knows what it refines.
    venture: str
    context: RequestContext
    plan: DelegationPlan
    assignments: dict[str, str]
    analyses: Annotated[dict[str, str], _merge_analyses]
    reviews: dict[str, ReviewResult]
    revisions: dict[str, str]
    iteration: int
    review_history: Annotated[list[dict[str, ReviewResult]], _append]
    conflicts: list[Conflict]
    resolutions: Annotated[list[Resolution], _append]
    critique_revisions: dict[str, str]
    critique_round: int
    metrics: Annotated[dict[str, NodeMetric], _merge_metrics]
    final_strategy: str
