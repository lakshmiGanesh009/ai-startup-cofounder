"""Chief of Staff (manager agent): plans, delegates and synthesises.

The planning node decides which specialists a request needs and gives each one
a task. The synthesis node merges their reports into one launch strategy.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.roles import SPECIALISTS
from config import MAX_CRITIQUE_ROUNDS, MAX_ITERATIONS
from llm import get_llm
from state import (
    DelegationPlan,
    Resolution,
    ReviewResult,
    SpecialistCritique,
    WorkflowState,
)

logger = logging.getLogger(__name__)

SPECIALIST_NAMES = [role.name for role in SPECIALISTS]

_PLANNER_PROMPT = (
    "You are the Chief of Staff of a startup founding team. Read the founder's "
    "request and decide which specialists it needs. The specialists are: "
    f"{', '.join(SPECIALIST_NAMES)}. State the objective, and give a task only to "
    "the specialists the request actually needs. Leave the rest out."
)


def _build_prompt(state: WorkflowState) -> list:
    request = state["request"]
    context = state.get("context")
    context_text = context.as_prompt() if context else ""

    human = f"Founder request:\n{request}"
    if context_text:
        human += f"\n\n{context_text}"

    return [SystemMessage(_PLANNER_PROMPT), HumanMessage(human)]


def plan_node(state: WorkflowState) -> dict:
    """Produce the delegation plan and resolve who gets which task."""
    model = get_llm().with_structured_output(DelegationPlan)
    plan: DelegationPlan = model.invoke(_build_prompt(state))

    assignments = {
        name: task
        for name, task in plan.assignments().items()
        if name in SPECIALIST_NAMES
    }
    if not assignments:
        logger.debug("Empty plan; assigning all specialists")
        assignments = {name: state["request"] for name in SPECIALIST_NAMES}

    logger.debug("Delegating to: %s", ", ".join(assignments))
    return {"plan": plan, "assignments": assignments}


_REVIEW_PROMPT = (
    "You are the Chief of Staff reviewing a specialist's report against its task. "
    "Approve it if it is specific, on-task, and useful. Otherwise reject it and say "
    "what to improve. Give a score from 1 to 5."
)


def review_node(state: WorkflowState) -> dict:
    """Check each report against its task and decide which need another pass.

    On a later round only the just-revised reports are reviewed; reports already
    approved are kept, so an approved report never costs a second review call.
    """
    model = get_llm().with_structured_output(ReviewResult)
    assignments = state["assignments"]
    previous = state.get("reviews", {})
    to_review = state.get("revisions") or {name: "" for name in state["analyses"]}

    reviews: dict[str, ReviewResult] = dict(previous)
    for name in to_review:
        human = (
            f"Task: {assignments.get(name, state['request'])}\n\n"
            f"Report:\n{state['analyses'][name]}"
        )
        reviews[name] = model.invoke([SystemMessage(_REVIEW_PROMPT), HumanMessage(human)])

    iteration = state.get("iteration", 0) + 1
    revisions = (
        {name: r.feedback for name, r in reviews.items() if not r.approved}
        if iteration < MAX_ITERATIONS + 1
        else {}
    )

    logger.debug("Review round %d: %d need work", iteration, len(revisions))
    return {
        "reviews": reviews,
        "revisions": revisions,
        "iteration": iteration,
        "review_history": [reviews],
    }


_CRITIQUE_PROMPT = (
    "You are a specialist on a startup founding team. Read the other specialists' "
    "reports and flag only genuine conflicts between their claims and your own area. "
    "If you see none, return an empty list."
)


def critique_node(state: WorkflowState) -> dict:
    """Each assigned specialist flags conflicts with the others' reports."""
    model = get_llm().with_structured_output(SpecialistCritique)
    analyses = state["analyses"]

    conflicts = []
    for name in analyses:
        others = {other: text for other, text in analyses.items() if other != name}
        if not others:
            continue
        human = (
            f"You are the {name} specialist. Your report:\n{analyses[name]}\n\n"
            f"The other reports:\n\n{_reports_text(others)}"
        )
        critique: SpecialistCritique = model.invoke(
            [SystemMessage(_CRITIQUE_PROMPT), HumanMessage(human)]
        )
        conflicts.extend(critique.conflicts)

    logger.debug("Critique round: %d conflicts raised", len(conflicts))
    return {"conflicts": conflicts}


_RESOLVE_PROMPT = (
    "You are the Chief of Staff. Settle this conflict between two specialists with a "
    "clear decision, and name the one specialist (if any) who should revise their "
    "report to match the decision."
)


def resolve_node(state: WorkflowState) -> dict:
    """Resolve each conflict and decide which specialists must revise."""
    model = get_llm().with_structured_output(Resolution)
    assigned = set(state["assignments"])
    round_no = state.get("critique_round", 0) + 1

    resolutions = []
    for conflict in state.get("conflicts", []):
        human = (
            f"Conflict raised by {conflict.raised_by} about {conflict.about}:\n"
            f"{conflict.issue}"
        )
        resolution: Resolution = model.invoke(
            [SystemMessage(_RESOLVE_PROMPT), HumanMessage(human)]
        )
        resolutions.append(resolution)

    revisions = {}
    if round_no <= MAX_CRITIQUE_ROUNDS:
        for resolution in resolutions:
            if resolution.revise in assigned:
                revisions[resolution.revise] = resolution.decision

    logger.debug("Resolved %d conflicts; %d to revise", len(resolutions), len(revisions))
    return {
        "resolutions": resolutions,
        "critique_revisions": revisions,
        "critique_round": round_no,
    }


_SYNTHESIS_PROMPT = (
    "You are the Chief of Staff of a startup founding team. Merge the specialist "
    "reports below into one launch strategy. Give a clear recommendation, the "
    "reasoning behind it, where the specialists pull in different directions, and "
    "prioritised next steps. Use only what the specialists reported; add nothing new."
)


def _reports_text(analyses: dict[str, str]) -> str:
    return "\n\n".join(f"## {name}\n{report}" for name, report in analyses.items())


def synthesis_node(state: WorkflowState) -> dict:
    """Merge the specialist reports into one unified launch strategy."""
    logger.debug("Synthesising %d reports", len(state["analyses"]))
    human = (
        f"Objective: {state['plan'].objective}\n\n"
        f"Specialist reports:\n\n{_reports_text(state['analyses'])}"
    )
    reply = get_llm().invoke([SystemMessage(_SYNTHESIS_PROMPT), HumanMessage(human)])
    return {"final_strategy": reply.content}
