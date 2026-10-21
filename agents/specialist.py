"""Graph node that answers a request from one specialist's point of view.

`specialist_node` turns a role into a LangGraph node. Every specialist shares
this one implementation and differs only in its role (see decision D4).
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.roles import COMPANY_READERS, Role
from guardrails import context_for_prompt, fence, unfenced
from llm import get_llm
from metrics import track
from state import WorkflowState

logger = logging.getLogger(__name__)

# Marks a report a specialist could not produce, so synthesis can name the gap.
GAP_PREFIX = "[unavailable]"


def _build_prompt(role: Role, state: WorkflowState) -> list:
    request = state["request"]
    venture = state.get("venture") or request
    task = state.get("assignments", {}).get(role.name)
    # Of the founder's documents, the passages on this specialist's own work.
    context_text = context_for_prompt(state.get("context"), f"{task or ''} {role.title} {request}")

    human = f"Startup request:\n{fence(venture, 'founder')}"
    if venture != request:
        human += f"\n\nFollow-up request:\n{fence(request, 'founder')}"
    if task:
        human += f"\n\nYour assignment from the Chief of Staff:\n{task}"
    if context_text:
        human += f"\n\nWhat the founder told us:\n{context_text}"
    deep = state.get("deep_research")
    research = deep.for_specialist(role.name, role.name in COMPANY_READERS) if deep else ""
    if research:
        human += f"\n\n{fence(research, 'web research')}"

    feedback = state.get("revisions", {}).get(role.name) or state.get(
        "critique_revisions", {}
    ).get(role.name)
    previous = state.get("analyses", {}).get(role.name)
    if feedback:
        human += (
            f"\n\nYour previous report:\n{previous}"
            f"\n\nThe Chief of Staff asks you to revise it:\n{feedback}"
            "\n\nRewrite the whole report so it stands on its own: apply every point "
            "above, keep what was already right, and make the figures agree."
        )
    elif previous:  # a follow-up: refine the earlier report, don't start over
        human += (
            f"\n\nYour earlier report:\n{previous}"
            "\n\nRevise it to answer the follow-up. Keep what still holds, change what "
            "the follow-up calls for, and rewrite the whole report so it stands on its own."
        )

    return [SystemMessage(role.system_prompt), HumanMessage(human)]


def _is_revising(role: Role, state: WorkflowState) -> bool:
    return role.name in state.get("revisions", {}) or role.name in state.get(
        "critique_revisions", {}
    )


def specialist_node(role: Role):
    """Build a graph node that answers from `role`'s point of view, or revises it."""

    def node(state: WorkflowState) -> dict:
        action = "revising" if _is_revising(role, state) else "analysing"
        logger.debug("%s specialist %s", role.name, action)

        metrics: dict = {}
        with track(role.name, metrics) as t:
            try:
                reply = get_llm().invoke(_build_prompt(role, state))
                t.record(reply)
                analysis = unfenced(reply.content)
            except Exception as error:  # a failed specialist must not sink the run
                logger.warning("%s specialist failed: %s", role.name, error)
                analysis = f"{GAP_PREFIX} The {role.name} analysis could not be produced."

        return {"analyses": {role.name: analysis}, "metrics": metrics}

    return node
