"""LangGraph state machine that wires the agents together.

The Chief of Staff plans; official figures are looked up on FRED (lookups.py)
while, if the request asks for deep research, each assigned specialist's area
is researched on the web; the assigned specialists run in parallel, the Chief of
Staff reviews their reports and sends weak ones back once, the specialists
cross-critique and the Chief of Staff resolves any conflicts, then the approved
reports are synthesised into one strategy.

The graph is compiled with a checkpointer, so a session's state survives between
requests and a follow-up can reuse the reports that still stand: in memory by
default, or in PostgreSQL when the API has a database (persistence.py), so it
survives a restart too.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
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
from lookups import fred_configured, lookup_node
from state import (
    CompanyProfile,
    Conflict,
    DeepResearch,
    DelegationPlan,
    EconomicData,
    Figure,
    Flag,
    NodeMetric,
    RequestContext,
    RequestInput,
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
        Flag,
        EconomicData,
        Figure,
    )
]
# How a session's state is written and read back, wherever it is kept.
SERDE = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)


def _route_to_assigned(state: WorkflowState) -> list[str]:
    """Send the plan to only the specialists it assigned."""
    return list(state["assignments"])


def _route_after_plan(state: WorkflowState) -> list[str]:
    """Look up the official figures once a session, with FRED set up, and
    research when the request asked for deep research and an assigned
    specialist's area has none yet, at the same time; when neither, straight to
    the specialists, who start once both are done."""
    researched = state.get("deep_research")
    steps = []
    if fred_configured() and not state.get("economic"):
        steps.append("lookup")
    if state.get("deep") and any(name not in (researched.areas if researched else {}) for name in state["assignments"]):
        steps.append("research")
    return steps or _route_to_assigned(state)


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


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build and compile the workflow graph, keeping sessions with `checkpointer`
    (in memory if none is given)."""
    # The graph is started with a request (RequestInput); its nodes share the
    # whole WorkflowState.
    builder = StateGraph(WorkflowState, input_schema=RequestInput)
    builder.add_node("plan", plan_node)
    builder.add_node("research", research_node)
    builder.add_node("lookup", lookup_node)
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
    builder.add_conditional_edges("plan", _route_after_plan, ["lookup", "research", *SPECIALIST_NAMES])
    builder.add_conditional_edges("research", _route_to_assigned, SPECIALIST_NAMES)
    builder.add_conditional_edges("lookup", _route_to_assigned, SPECIALIST_NAMES)
    builder.add_conditional_edges(
        "review", _route_after_review, [*SPECIALIST_NAMES, "critique", "synthesis"]
    )
    builder.add_edge("critique", "resolve")
    builder.add_conditional_edges("resolve", _route_after_resolve, [*SPECIALIST_NAMES, "synthesis"])
    builder.add_edge("synthesis", END)
    # With DEBUG_MODE on, LangGraph prints every step and the state it writes.
    return builder.compile(checkpointer=checkpointer or MemorySaver(serde=SERDE), debug=DEBUG_MODE)
