"""Chief of Staff (manager agent): plans, delegates and synthesises.

The planning node decides which specialists a request needs and gives each one
a task. The synthesis node merges their reports into one launch strategy.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.roles import SPECIALISTS
from config import MAX_ITERATIONS
from llm import get_llm
from state import DelegationPlan, ReviewResult, WorkflowState

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
