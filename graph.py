"""LangGraph state machine that wires the agents together.

The Chief of Staff plans first, then only the specialists it assigned run in
parallel. Later steps add review and synthesis around them.
"""

from langgraph.graph import END, START, StateGraph

from agents.chief_of_staff import SPECIALIST_NAMES, plan_node
from agents.roles import SPECIALISTS
from agents.specialist import specialist_node
from state import WorkflowState


def _route_to_assigned(state: WorkflowState) -> list[str]:
    """Send the plan to only the specialists it assigned."""
    return list(state["assignments"])


def build_graph():
    """Build and compile the workflow graph."""
    builder = StateGraph(WorkflowState)
    builder.add_node("plan", plan_node)
    for role in SPECIALISTS:
        builder.add_node(role.name, specialist_node(role))
        builder.add_edge(role.name, END)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", _route_to_assigned, SPECIALIST_NAMES)
    return builder.compile()
