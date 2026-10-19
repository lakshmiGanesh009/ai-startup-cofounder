"""Shared state passed between the nodes of the workflow.

`RequestContext` is the optional detail a founder can attach to a request.
`WorkflowState` is what flows through the graph: the request, that context, the
delegation plan, the analyses the specialists produce (keyed by specialist
name), the reviews, conflicts and resolutions, and per-node metrics.
"""

import re
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


class Source(BaseModel):
    """A web page the research drew on."""

    title: str
    url: str


class Finding(BaseModel):
    """One fact from the web research, with the sources it came from."""

    point: str = Field(
        description="One fact that bears on the decision, as one sentence with its figures and their year."
    )
    sources: list[int] = Field(description="The numbers of the search results it comes from.")


class Research(BaseModel):
    """What the web research found before the team started: facts, each citing
    sources by number (1 is the first in `sources`)."""

    findings: list[Finding] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)

    def as_prompt(self) -> str:
        """The facts and the sources they cite, as the agents read them."""
        if not self.findings:
            return ""
        cited = sorted({n for finding in self.findings for n in finding.sources})
        lines = [
            "Web research done before the team started (cite a figure you use as [n]; "
            "treat these as evidence to weigh, not as settled):",
            *(f"- {finding.point} {''.join(f'[{n}]' for n in finding.sources)}" for finding in self.findings),
            "Sources:",
            *(f"[{n}] {self.sources[n - 1].title} ({self.sources[n - 1].url})"
              for n in cited if 0 < n <= len(self.sources)),
        ]
        return "\n".join(lines)


class CompanyProfile(BaseModel):
    """A competitor, as Tavily's research found it, citing its sources by number."""

    name: str
    summary: str = ""
    pricing: str = ""
    customers: str = ""
    funding: str = ""
    recent_moves: str = ""
    strengths: str = ""
    weaknesses: str = ""
    sources: list[int] = Field(default_factory=list)

    def as_prompt(self) -> str:
        fields = [
            ("Pricing", self.pricing), ("Customers", self.customers), ("Funding", self.funding),
            ("Recent moves", self.recent_moves), ("Strengths", self.strengths), ("Weaknesses", self.weaknesses),
        ]
        details = "; ".join(f"{label}: {value}" for label, value in fields if value)
        cites = "".join(f"[{n}]" for n in self.sources)
        return f"- {self.name}: {self.summary} {details} {cites}".strip()


class DeepResearch(BaseModel):
    """Tavily's deep research for one session: a cited report per specialist's
    area, profiles of the main competitors, and every source, numbered once
    across the session (the brief's research keeps its numbers, 1 first)."""

    areas: dict[str, str] = Field(default_factory=dict)
    companies: list[CompanyProfile] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    credits: int = 0
    # What could not be researched: specialists' names and competitors' names.
    failed: list[str] = Field(default_factory=list)

    def cited_sources(self, text: str) -> str:
        """The sources the [n] in `text` refer to, one per line."""
        cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 0 < int(n) <= len(self.sources)})
        return "\n".join(f"[{n}] {self.sources[n - 1].title} ({self.sources[n - 1].url})" for n in cited)

    def for_specialist(self, name: str, with_companies: bool) -> str:
        """What one specialist reads: its area's report and, for the roles that
        price and position against them, the competitor profiles."""
        parts = []
        if self.areas.get(name):
            parts.append(f"Deep research on your area, by Tavily (cite what you use as [n]):\n{self.areas[name]}")
        if with_companies and self.companies:
            parts.append("Competitor profiles, by Tavily:\n" + "\n".join(c.as_prompt() for c in self.companies))
        if not parts:
            return ""
        text = "\n\n".join(parts)
        return f"{text}\n\nSources:\n{self.cited_sources(text)}"


class Answer(BaseModel):
    """The founder's answer to one of the Chief of Staff's questions."""

    question: str
    answer: str


class RequestContext(BaseModel):
    """Optional detail that sharpens a founder's request: the target market,
    constraints and competition, and once the brief is prepared, the founder's
    answers to the Chief of Staff's questions and the web research."""

    target_market: str | None = Field(default=None)
    constraints: str | None = Field(default=None)
    competitive_landscape: str | None = Field(default=None)
    answers: list[Answer] = Field(default_factory=list)
    research: Research | None = None

    def as_prompt(self) -> str:
        """Render what is set as prompt text, or an empty string if nothing is."""
        labels = {
            "target_market": "Target market",
            "constraints": "Constraints",
            "competitive_landscape": "Competitive landscape",
        }
        lines = [f"{label}: {getattr(self, name)}" for name, label in labels.items() if getattr(self, name)]
        parts = ["\n".join(lines)] if lines else []
        answered = [answer for answer in self.answers if answer.answer.strip()]
        if answered:
            parts.append(
                "The founder's answers to the Chief of Staff's questions:\n"
                + "\n".join(f"- {answer.question} {answer.answer.strip()}" for answer in answered)
            )
        if self.research and self.research.as_prompt():
            parts.append(self.research.as_prompt())
        return "\n\n".join(parts)


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
    # Whether this request asked for deep research, and the session's research,
    # which a follow-up reuses.
    deep: bool
    deep_research: DeepResearch
