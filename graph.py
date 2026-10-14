"""LangGraph state machine that wires the agents together.

The Chief of Staff plans, the assigned specialists run in parallel, the Chief of
Staff reviews their reports and sends weak ones back once, then synthesises the
approved reports into one strategy.
"""

from langgraph.graph import END, START, StateGraph

from agents.chief_of_staff import (
    SPECIALIST_NAMES,
    plan_node,
    review_node,
    synthesis_node,
)
from agents.roles import SPECIALISTS
from agents.specialist import specialist_node
from state import WorkflowState


def _route_to_assigned(state: WorkflowState) -> list[str]:
    """Send the plan to only the specialists it assigned."""
    return list(state["assignments"])


def _route_after_review(state: WorkflowState) -> list[str] | str:
    """Send rejected reports back to their specialists, or move to synthesis."""
    revisions = state.get("revisions", {})
    return list(revisions) if revisions else "synthesis"


def build_graph():
    """Build and compile the workflow graph."""
    builder = StateGraph(WorkflowState)
    builder.add_node("plan", plan_node)
    builder.add_node("review", review_node)
    builder.add_node("synthesis", synthesis_node)
    for role in SPECIALISTS:
        builder.add_node(role.name, specialist_node(role))
        builder.add_edge(role.name, "review")

    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", _route_to_assigned, SPECIALIST_NAMES)
    builder.add_conditional_edges("review", _route_after_review, [*SPECIALIST_NAMES, "synthesis"])
    builder.add_edge("synthesis", END)
    return builder.compile()
