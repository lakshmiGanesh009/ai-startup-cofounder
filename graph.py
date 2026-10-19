"""LangGraph state machine that wires the agents together.

The Chief of Staff plans, Tavily researches each assigned specialist's area
when the request asks for deep research, the assigned specialists run in parallel, the Chief of
Staff reviews their reports and sends weak ones back once, the specialists
cross-critique and the Chief of Staff resolves any conflicts, then the approved
reports are synthesised into one strategy.

The graph is compiled with a checkpointer, so a session's state survives between
requests and a follow-up can reuse the reports that still stand.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from agents.chief_of_staff import (
    SPECIALIST_NAMES,
    critique_node,
    plan_node,
    resolve_node,
    review_node,
    synthesis_node,
)
from agents.roles import SPECIALISTS
from agents.specialist import specialist_node
from config import DEBUG_MODE, MAX_CRITIQUE_ROUNDS
from deep_research import research_node
from state import (
    CompanyProfile,
    Conflict,
    DeepResearch,
    DelegationPlan,
    NodeMetric,
    RequestContext,
    Resolution,
    ReviewResult,
    Source,
    Task,
    WorkflowState,
)

# The state models the checkpointer stores between requests. LangGraph warns
# when it loads a type that is not registered, and will block it in a future
# version, which would break follow-ups, so they are registered explicitly.
_CHECKPOINT_TYPES = [
    (model.__module__, model.__name__)
    for model in (
        RequestContext,
        DelegationPlan,
        Task,
        ReviewResult,
        Conflict,
        Resolution,
        NodeMetric,
        DeepResearch,
        CompanyProfile,
        Source,
    )
]


def _route_to_assigned(state: WorkflowState) -> list[str]:
    """Send the plan to only the specialists it assigned."""
    return list(state["assignments"])


def _route_after_plan(state: WorkflowState) -> list[str] | str:
    """Research first when the request asked for deep research and an assigned
    specialist's area has none yet; otherwise straight to the specialists."""
    researched = state.get("deep_research")
    if state.get("deep") and any(name not in (researched.areas if researched else {}) for name in state["assignments"]):
        return "research"
    return _route_to_assigned(state)


def _route_after_review(state: WorkflowState) -> list[str] | str:
    """Send rejected reports back, else critique, else straight to synthesis.

    With a single specialist there is no one to cross-critique against, so the
    critique and resolve pass is skipped.
    """
    revisions = state.get("revisions", {})
    if revisions:
        return list(revisions)
    return "critique" if len(state["analyses"]) > 1 else "synthesis"


def _route_after_specialist(role_name: str):
    """A fresh report goes to review. A report revised after critique goes back to
    critique while another round is allowed, otherwise straight to synthesis, so
    no critique call is spent on a round that could not change anything.
    """

    def route(state: WorkflowState) -> str:
        if role_name not in state.get("critique_revisions", {}):
            return "review"
        if state.get("critique_round", 0) < MAX_CRITIQUE_ROUNDS:
            return "critique"
        return "synthesis"

    return route


def _route_after_resolve(state: WorkflowState) -> list[str] | str:
    """Send specialists with a resolution back to revise, or move to synthesis."""
    revisions = state.get("critique_revisions", {})
    return list(revisions) if revisions else "synthesis"


def build_graph():
    """Build and compile the workflow graph."""
    builder = StateGraph(WorkflowState)
    builder.add_node("plan", plan_node)
    builder.add_node("research", research_node)
    builder.add_node("review", review_node)
    builder.add_node("critique", critique_node)
    builder.add_node("resolve", resolve_node)
    builder.add_node("synthesis", synthesis_node)
    for role in SPECIALISTS:
        builder.add_node(role.name, specialist_node(role))
        builder.add_conditional_edges(
            role.name, _route_after_specialist(role.name), ["review", "critique", "synthesis"]
        )

    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", _route_after_plan, ["research", *SPECIALIST_NAMES])
    builder.add_conditional_edges("research", _route_to_assigned, SPECIALIST_NAMES)
    builder.add_conditional_edges(
        "review", _route_after_review, [*SPECIALIST_NAMES, "critique", "synthesis"]
    )
    builder.add_edge("critique", "resolve")
    builder.add_conditional_edges("resolve", _route_after_resolve, [*SPECIALIST_NAMES, "synthesis"])
    builder.add_edge("synthesis", END)
    serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)
    # With DEBUG_MODE on, LangGraph prints every step and the state it writes.
    return builder.compile(checkpointer=MemorySaver(serde=serde), debug=DEBUG_MODE)
