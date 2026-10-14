"""Graph node that answers a request from one specialist's point of view.

`specialist_node` turns a role into a LangGraph node. Every specialist shares
this one implementation and differs only in its role (see decision D4).
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.roles import Role
from llm import get_llm
from state import WorkflowState

logger = logging.getLogger(__name__)


def _build_prompt(role: Role, state: WorkflowState) -> list:
    request = state["request"]
    task = state.get("assignments", {}).get(role.name)
    context = state.get("context")
    context_text = context.as_prompt() if context else ""

    human = f"Startup request:\n{request}"
    if task:
        human += f"\n\nYour assignment:\n{task}"
    if context_text:
        human += f"\n\n{context_text}"

    feedback = state.get("revisions", {}).get(role.name) or state.get(
        "critique_revisions", {}
    ).get(role.name)
    if feedback:
        previous = state["analyses"][role.name]
        human += (
            f"\n\nYour previous report:\n{previous}"
            f"\n\nThe Chief of Staff asks you to revise it:\n{feedback}"
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
        reply = get_llm().invoke(_build_prompt(role, state))
        return {"analyses": {role.name: reply.content}}

    return node
