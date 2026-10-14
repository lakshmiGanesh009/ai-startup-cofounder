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

    return [SystemMessage(role.system_prompt), HumanMessage(human)]


def specialist_node(role: Role):
    """Build a graph node that answers from `role`'s point of view."""

    def node(state: WorkflowState) -> dict:
        logger.debug("%s specialist analysing the request", role.name)
        reply = get_llm().invoke(_build_prompt(role, state))
        return {"analyses": {role.name: reply.content}}

    return node
