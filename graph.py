"""LangGraph state machine that wires the agents together.

Step 2 wires one specialist: START -> marketing -> END. Later steps add the
rest of the team around it.
"""

from langgraph.graph import END, START, StateGraph

from agents.roles import MARKETING
from agents.specialist import specialist_node
from state import WorkflowState


def build_graph():
    """Build and compile the workflow graph."""
    builder = StateGraph(WorkflowState)
    builder.add_node(MARKETING.name, specialist_node(MARKETING))
    builder.add_edge(START, MARKETING.name)
    builder.add_edge(MARKETING.name, END)
    return builder.compile()
