"""Chief of Staff (manager agent): plans and delegates.

The planning node reads the founder's request and decides which specialists it
needs, giving each one a task. If it names none, every specialist is assigned
so a request is never dropped.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.roles import SPECIALISTS
from llm import get_llm
from state import DelegationPlan, WorkflowState

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
