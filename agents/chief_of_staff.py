"""Chief of Staff (manager agent): plans, delegates, reviews, resolves and synthesises.

The planning node decides which specialists a request needs and gives each one
a task. The review node checks each report against its task, the critique and
resolve nodes surface and settle conflicts between specialists, and the
synthesis node merges their reports into one launch strategy.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Overwrite

from agents.roles import SPECIALISTS
from agents.specialist import GAP_PREFIX
from config import MAX_CRITIQUE_ROUNDS, MAX_ITERATIONS
from llm import get_llm
from metrics import track
from state import (
    DelegationPlan,
    Resolution,
    ReviewResult,
    SpecialistCritique,
    WorkflowState,
)

logger = logging.getLogger(__name__)

SPECIALIST_NAMES = [role.name for role in SPECIALISTS]


def structured_invoke(schema, messages):
    """Invoke the model for a structured `schema`, retrying once if the first
    reply does not parse into the schema."""
    model = get_llm().with_structured_output(schema)
    try:
        return model.invoke(messages)
    except Exception:  # malformed structured output: one more try
        return model.invoke(messages)

_PLANNER_PROMPT = (
    "You are the Chief of Staff of a startup founding team. Read the founder's "
    "request and decide which specialists it needs. The specialists are: "
    + "; ".join(f"{role.name} ({role.focus})" for role in SPECIALISTS)
    + ". Evaluating a startup idea as a whole needs all four. A narrower request "
    "needs every specialist whose area it touches, including the one who owns the "
    "plan or decision it asks about. State the objective, and give a task only to "
    "the specialists the request needs. Leave the rest out. Keep each task to one "
    "or two sentences; the specialists know their own area."
)


def _build_prompt(state: WorkflowState, prior: dict[str, str], venture: str) -> list:
    request = state["request"]
    context = state.get("context")
    context_text = context.as_prompt() if context else ""

    if prior:
        human = f"Original request:\n{venture}\n\nFollow-up request:\n{request}"
    else:
        human = f"Founder request:\n{request}"
    if context_text:
        human += f"\n\n{context_text}"
    if prior:
        human += (
            "\n\nThis is a follow-up. These specialists already reported: "
            f"{', '.join(prior)}. Assign only the ones this follow-up affects; "
            "the rest keep their earlier report."
        )

    return [SystemMessage(_PLANNER_PROMPT), HumanMessage(human)]


# Fields from a previous request that must not leak into a new one.
_RESET = {
    "reviews": {},
    "revisions": {},
    "iteration": 0,
    "conflicts": [],
    "critique_revisions": {},
    "critique_round": 0,
}


def plan_node(state: WorkflowState) -> dict:
    """Produce the delegation plan and resolve who gets which task.

    On a follow-up, only the specialists the request affects are reassigned; the
    others keep the report they already gave.
    """
    prior = state.get("analyses", {})
    venture = state.get("venture") or state["request"]
    metrics: dict = {}
    with track("plan", metrics) as t:
        plan: DelegationPlan = structured_invoke(
            DelegationPlan, _build_prompt(state, prior, venture)
        )
        t.record(plan)

    assignments = {
        name: task
        for name, task in plan.assignments().items()
        if name in SPECIALIST_NAMES
    }
    if not assignments:
        logger.debug("Empty plan; assigning all specialists")
        assignments = {name: state["request"] for name in SPECIALIST_NAMES}

    logger.debug("Delegating to: %s", ", ".join(assignments))
    # The accumulating fields restart too. Overwrite bypasses their reducers, so a
    # follow-up reports only its own reviews, resolutions and cost.
    return {
        "plan": plan,
        "assignments": assignments,
        "venture": venture,
        "metrics": Overwrite(metrics),
        "review_history": Overwrite([]),
        "resolutions": Overwrite([]),
        **_RESET,
    }


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
    assignments = state["assignments"]
    previous = state.get("reviews", {})
    # First round reviews the specialists assigned this request; a later round
    # reviews only the just-revised reports.
    to_review = state.get("revisions") or {name: "" for name in assignments}

    reviews: dict[str, ReviewResult] = dict(previous)
    metrics: dict = {}
    with track("review", metrics) as t:
        for name in to_review:
            report = state["analyses"][name]
            if report.startswith(GAP_PREFIX):  # nothing to review for a gap
                reviews[name] = ReviewResult(approved=True, score=1, feedback="")
                continue
            human = f"Task: {assignments.get(name, state['request'])}\n\nReport:\n{report}"
            reviews[name] = structured_invoke(
                ReviewResult, [SystemMessage(_REVIEW_PROMPT), HumanMessage(human)]
            )
            t.record(reviews[name])

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
        "metrics": metrics,
    }


_CRITIQUE_PROMPT = (
    "You are a specialist on a startup founding team. Compare the other specialists' "
    "reports with your own. Flag a disagreement only when another specialist "
    "recommends something different from you on a question inside your own area, "
    "such as a price, a budget, a timeline or the scope of the first offer, so that "
    "the founder could not follow both. Ignore differences in emphasis or detail. "
    "Flag at most two, the most important first. If there are none, return an "
    "empty list."
)


def critique_node(state: WorkflowState) -> dict:
    """Each assigned specialist flags conflicts with the others' reports.

    On a follow-up only the reassigned specialists critique, each reading every
    other report; the unchanged reports were already cross-checked.
    """
    analyses = state["analyses"]

    conflicts = []
    metrics: dict = {}
    with track("critique", metrics) as t:
        for name in state["assignments"]:
            if analyses[name].startswith(GAP_PREFIX):  # a gap cannot critique
                continue
            others = {o: text for o, text in analyses.items() if o != name}
            if not others:
                continue
            human = (
                f"You are the {name} specialist. Your report:\n{analyses[name]}\n\n"
                f"The other reports:\n\n{_reports_text(others)}"
            )
            critique: SpecialistCritique = structured_invoke(
                SpecialistCritique, [SystemMessage(_CRITIQUE_PROMPT), HumanMessage(human)]
            )
            t.record(critique)
            conflicts.extend(critique.conflicts)

    logger.debug("Critique round: %d conflicts raised", len(conflicts))
    return {"conflicts": conflicts, "metrics": metrics}


_RESOLVE_PROMPT = (
    "You are the Chief of Staff. Settle this conflict between two specialists with a "
    "clear decision, and name the one specialist (if any) who should revise their "
    "report to match the decision."
)


def _specialist_key(name: str) -> str:
    """Map a name as the model writes it, e.g. "Finance specialist", to its key."""
    lowered = name.lower()
    return next((key for key in SPECIALIST_NAMES if key in lowered), "")


def resolve_node(state: WorkflowState) -> dict:
    """Resolve each conflict and decide which specialists must revise."""
    assigned = set(state["assignments"])
    round_no = state.get("critique_round", 0) + 1

    resolutions = []
    metrics: dict = {}
    with track("resolve", metrics) as t:
        for conflict in state.get("conflicts", []):
            human = (
                f"Conflict raised by {conflict.raised_by} about {conflict.about}:\n"
                f"{conflict.issue}"
            )
            resolution: Resolution = structured_invoke(
                Resolution, [SystemMessage(_RESOLVE_PROMPT), HumanMessage(human)]
            )
            t.record(resolution)
            resolutions.append(resolution)

    revisions = {}
    if round_no <= MAX_CRITIQUE_ROUNDS:
        for resolution in resolutions:
            target = _specialist_key(resolution.revise)
            if target in assigned:  # one specialist may have several decisions to apply
                earlier = revisions.get(target)
                revisions[target] = (
                    f"{earlier}\n{resolution.decision}" if earlier else resolution.decision
                )

    logger.debug("Resolved %d conflicts; %d to revise", len(resolutions), len(revisions))
    return {
        "resolutions": resolutions,
        "critique_revisions": revisions,
        "critique_round": round_no,
        "metrics": metrics,
    }


_SYNTHESIS_PROMPT = (
    "You are the Chief of Staff of a startup founding team. Merge the specialist "
    "reports below into one launch strategy. Give a clear recommendation, the "
    "reasoning behind it, where the specialists pull in different directions, and "
    "prioritised next steps. Use only what the specialists reported; add nothing new. "
    "Where you have already settled a disagreement, follow your decision and say "
    "how it was settled. "
    "If a report is marked unavailable, name that gap in the strategy and proceed "
    "with the reports you do have."
)


def _reports_text(analyses: dict[str, str]) -> str:
    return "\n\n".join(f"## {name}\n{report}" for name, report in analyses.items())


def _decisions_text(resolutions: list[Resolution]) -> str:
    return "\n".join(
        f"- {r.conflict.raised_by} vs {r.conflict.about}: {r.conflict.issue} "
        f"Decision: {r.decision}"
        for r in resolutions
    )


def synthesis_node(state: WorkflowState) -> dict:
    """Merge the specialist reports, and any conflict decisions, into one strategy."""
    logger.debug("Synthesising %d reports", len(state["analyses"]))
    human = (
        f"Objective: {state['plan'].objective}\n\n"
        f"Specialist reports:\n\n{_reports_text(state['analyses'])}"
    )
    resolutions = state.get("resolutions", [])
    if resolutions:
        human += f"\n\nDisagreements you settled:\n{_decisions_text(resolutions)}"
    metrics: dict = {}
    with track("synthesis", metrics) as t:
        reply = get_llm().invoke([SystemMessage(_SYNTHESIS_PROMPT), HumanMessage(human)])
        t.record(reply)
    return {"final_strategy": reply.content, "metrics": metrics}
