"""LangGraph state machine that wires the agents together.

The four specialists fan out from START, run in parallel, and end. Later steps
add the Chief of Staff around them.
"""

from langgraph.graph import END, START, StateGraph

from agents.roles import SPECIALISTS
from agents.specialist import specialist_node
from state import WorkflowState


def build_graph():
    """Build and compile the workflow graph.

    The specialists fan out from START and run in parallel, then end.
    """
    builder = StateGraph(WorkflowState)
    for role in SPECIALISTS:
        builder.add_node(role.name, specialist_node(role))
        builder.add_edge(START, role.name)
        builder.add_edge(role.name, END)
    return builder.compile()
