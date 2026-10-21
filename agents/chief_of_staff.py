"""Chief of Staff (manager agent): plans, delegates, reviews, resolves and synthesises.

The planning node decides which specialists a request needs and gives each one
a task. The review node checks each report against its task, the critique and
resolve nodes surface and settle conflicts between specialists, and the
synthesis node merges their reports into one launch strategy.
"""

import logging

import openai
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import ContextThreadPoolExecutor
from langgraph.types import Overwrite

from agents.roles import SPECIALISTS
from agents.specialist import GAP_PREFIX
from config import MAX_CRITIQUE_ROUNDS, MAX_ITERATIONS
from guardrails import RULES, context_for_prompt, fence, unfenced
from llm import CHIEF, LLM_ERRORS, SPECIALIST, LLMReplyError, get_llm
from metrics import track
from state import (
    DelegationPlan,
    Resolution,
    Resolutions,
    ReviewResult,
    SpecialistCritique,
    WorkflowState,
)

logger = logging.getLogger(__name__)

SPECIALIST_NAMES = [role.name for role in SPECIALISTS]

# The longest the final strategy may be; it is written last, so its length adds
# straight to the response time.
STRATEGY_WORDS = 500

# The review score (1 to 5) a report needs to be approved without revision.
APPROVAL_SCORE = 4


def structured_invoke(schema, messages, tracker, role=CHIEF):
    """Invoke `role`'s model for a structured `schema`, counting each call on `tracker`.

    A reply that does not parse into the schema is retried once, and so is one
    the provider's content filter withheld, which is usually a false positive
    that a second attempt clears. Other API errors are not retried here: the
    client has already retried them (LLM_MAX_RETRIES).
    """
    model = get_llm(role).with_structured_output(schema, include_raw=True)
    for _ in range(2):
        try:
            reply = model.invoke(messages)
        except openai.ContentFilterFinishReasonError as error:
            tracker.record(None)
            logger.warning("The content filter withheld a %s reply (%s).",
                           schema.__name__, _filtered(error))
            problem = error
            continue
        tracker.record(reply["raw"])  # the raw reply carries the token usage
        if reply["parsed"] is not None:
            return reply["parsed"]
        problem = reply["parsing_error"]
    raise LLMReplyError(f"No usable {schema.__name__} reply: {problem}")


def _filtered(error: openai.ContentFilterFinishReasonError) -> str:
    """The content-filter categories that withheld a reply, as Azure reports them."""
    completion = error.completion
    if not completion or not completion.choices:
        return "categories not reported"
    results = (completion.choices[0].model_extra or {}).get("content_filter_results") or {}
    flagged = [name for name, result in results.items()
               if isinstance(result, dict) and result.get("filtered")]
    return ", ".join(flagged) or "categories not reported"


def _attempt(call, what: str):
    """Make one review, critique or resolve call; if it fails, log it and return None.

    These checks refine reports that already exist, so a failed one is skipped
    rather than failing the whole run.
    """
    try:
        return call()
    except LLM_ERRORS as error:
        logger.warning("%s failed and was skipped: %s", what, error)
        return None


def _ask_each(schema, prompts: dict[str, list], tracker, what: str, role=CHIEF) -> dict:
    """Ask for a structured `schema` reply to every prompt at the same time.

    The calls are independent, so they run in parallel rather than one after
    another. Returns the replies keyed and ordered like `prompts`, leaving out
    any call that failed. The pool copies the context into each thread, so
    LangChain callbacks and tracing still see every call.
    """
    if not prompts:
        return {}

    def ask(key):
        return _attempt(
            lambda: structured_invoke(schema, prompts[key], tracker, role), f"{what} {key}"
        )

    with ContextThreadPoolExecutor(max_workers=len(prompts)) as pool:
        replies = dict(zip(prompts, pool.map(ask, list(prompts))))
    return {key: reply for key, reply in replies.items() if reply is not None}


_PLANNER_PROMPT = (
    "You are the Chief of Staff of a startup founding team. You turn the founder's "
    "request into a plan the specialists can execute, and you answer for the strategy "
    "that comes out of it. The specialists are: "
    + "; ".join(f"{role.name} ({role.focus})" for role in SPECIALISTS)
    + ". Before you delegate, work out what the founder actually needs: the decision "
    "at stake, the constraints that bind it (budget, timeline, team, regulation, "
    "competition) and what is still uncertain. State the objective as that decision, "
    "in one sentence. Evaluating a startup idea as a whole needs all four specialists. "
    "A narrower request needs only the specialist whose area it asks about, plus the "
    "one who owns the plan or decision it refers to; leave out the rest even if their "
    "area is loosely related. Give each assigned specialist one or two sentences: the "
    "specific question to answer for this venture and the constraint its answer must "
    "respect. Never ask a specialist for work outside its area; the specialists know "
    "their own craft."
)


def _founder_brief(state: WorkflowState) -> str:
    """The request and what the founder told us, as every Chief of Staff call
    sees it: fenced as the founder's (guardrails.py)."""
    venture = state.get("venture") or state["request"]
    brief = f"Founder request:\n{fence(venture, 'founder')}"
    if state["request"] != venture:
        brief += f"\n\nFollow-up request:\n{fence(state['request'], 'founder')}"
    context_text = context_for_prompt(state.get("context"), f"{venture} {state['request']}")
    if context_text:
        brief += f"\n\nWhat the founder told us:\n{context_text}"
    return brief


def _build_prompt(state: WorkflowState, prior: dict[str, str], venture: str) -> list:
    request = state["request"]
    context_text = context_for_prompt(state.get("context"), f"{venture} {request}")

    if prior:
        human = f"Original request:\n{fence(venture, 'founder')}\n\nFollow-up request:\n{fence(request, 'founder')}"
    else:
        human = f"Founder request:\n{fence(request, 'founder')}"
    if context_text:
        human += f"\n\n{context_text}"
    if prior:
        human += (
            "\n\nThis is a follow-up. These specialists already reported: "
            f"{', '.join(prior)}. Assign only the specialists who own what the "
            "follow-up asks to change, usually one or two; the rest keep their "
            "earlier report, and cross-critique checks the changed reports against "
            "them. The rule that a whole evaluation needs all four does not apply "
            "to a follow-up."
        )

    return [SystemMessage(_PLANNER_PROMPT + RULES), HumanMessage(human)]


# Fields from a previous request that must not leak into a new one.
_RESET = {
    "reviews": {},
    "revisions": {},
    "iteration": 0,
    "conflicts": [],
    "critique_revisions": {},
    "critique_round": 0,
}


def plan_node(state: WorkflowState) -> dict:
    """Produce the delegation plan and resolve who gets which task.

    On a follow-up, only the specialists the request affects are reassigned; the
    others keep the report they already gave.
    """
    prior = state.get("analyses", {})
    venture = state.get("venture") or state["request"]
    metrics: dict = {}
    with track("plan", metrics) as t:
        plan: DelegationPlan = structured_invoke(
            DelegationPlan, _build_prompt(state, prior, venture), t
        )

    assignments = plan.assignments()
    if not assignments:
        logger.debug("Empty plan; assigning all specialists")
        assignments = {name: state["request"] for name in SPECIALIST_NAMES}

    logger.debug("Delegating to: %s", ", ".join(assignments))
    # The accumulating fields restart too. Overwrite bypasses their reducers, so a
    # follow-up reports only its own reviews, resolutions and cost.
    return {
        "plan": plan,
        "assignments": assignments,
        "venture": venture,
        "metrics": Overwrite(metrics),
        "review_history": Overwrite([]),
        "resolutions": Overwrite([]),
        **_RESET,
    }


_REVIEW_PROMPT = (
    "You are the Chief of Staff reviewing one specialist's report before it goes into "
    "the launch strategy. The report is a brief of at most 250 words: judge whether it "
    "makes the right calls for this venture with the key numbers behind them, not "
    "whether it covers everything. Check four things: it answers the task it was "
    "given; it is specific to this venture (named customers, prices, tools, "
    "safeguards, dates) rather than generic advice; its figures respect the founder's "
    "constraints and agree with each other; and its recommendations are concrete "
    "enough to act on. Score it: 5 ready to use as it is; 4 useful and specific, with "
    "minor gaps; 3 missing something the task asked for, or with figures that "
    "contradict each other or the constraints; 2 largely generic or off-task; 1 wrong "
    f"or unusable. A report scoring {APPROVAL_SCORE} or more is approved; give it no "
    "feedback. For a lower score, say in one to three sentences exactly what to fix or "
    "add, asking only for what fits in a brief: no contract wording, vendor quotes or "
    "full cash-flow tables."
)


def review_node(state: WorkflowState) -> dict:
    """Check each report against its task and decide which need another pass.

    On a later round only the just-revised reports are reviewed; reports already
    approved are kept, so an approved report never costs a second review call.
    The reports of one round are reviewed at the same time.
    """
    assignments = state["assignments"]
    previous = state.get("reviews", {})
    # First round reviews the specialists assigned this request; a later round
    # reviews only the just-revised reports.
    to_review = state.get("revisions") or {name: "" for name in assignments}

    reviews: dict[str, ReviewResult] = dict(previous)
    prompts = {}
    for name in to_review:
        report = state["analyses"][name]
        if report.startswith(GAP_PREFIX):  # nothing to review for a gap
            reviews[name] = ReviewResult(approved=True, score=1, feedback="")
            continue
        human = (
            f"{_founder_brief(state)}\n\n"
            f"Task given to the {name} specialist:\n{assignments.get(name, state['request'])}"
            f"\n\nReport:\n{fence(report, f'the {name} report')}"
        )
        prompts[name] = [SystemMessage(_REVIEW_PROMPT + RULES), HumanMessage(human)]

    metrics: dict = {}
    with track("review", metrics) as t:
        replies = _ask_each(ReviewResult, prompts, t, "Review of")
    for name in prompts:
        if name in replies:
            # The score decides, so the verdict always follows the rubric; models
            # have scored a report 4 and still rejected it.
            approved = replies[name].score >= APPROVAL_SCORE
            reviews[name] = replies[name].model_copy(
                update={"approved": approved, "feedback": "" if approved else replies[name].feedback}
            )
        else:  # a failed review leaves the report unreviewed
            reviews.pop(name, None)

    iteration = state.get("iteration", 0) + 1
    revisions = (
        {name: r.feedback for name, r in reviews.items() if not r.approved}
        if iteration < MAX_ITERATIONS + 1
        else {}
    )

    logger.debug("Review round %d: %d need work", iteration, len(revisions))
    return {
        "reviews": reviews,
        "revisions": revisions,
        "iteration": iteration,
        "review_history": [reviews],
        "metrics": metrics,
    }


_CRITIQUE_PROMPT = (
    "You are a specialist on a startup founding team, checking your colleagues' "
    "reports against your own before they are merged into one strategy. Flag a "
    "disagreement only when another specialist recommends something that contradicts "
    "your recommendation on a question inside your own area, so the founder could not "
    "follow both: for example a price, a budget, a timeline, the scope of the first "
    "offer, a channel or a safeguard. Describe each in one sentence that states both "
    "positions and why they cannot both hold. Ignore differences in emphasis, wording "
    "or detail, and points outside your area. Flag at most two, the most consequential "
    "first. If there are none, return an empty list."
)


def critique_node(state: WorkflowState) -> dict:
    """Each assigned specialist flags conflicts with the others' reports.

    On a follow-up only the reassigned specialists critique, each reading every
    other report; the unchanged reports were already cross-checked. The
    specialists critique at the same time.
    """
    analyses = state["analyses"]

    prompts = {}
    for name in state["assignments"]:
        if analyses[name].startswith(GAP_PREFIX):  # a gap cannot critique
            continue
        # Nor can a gap be critiqued: it makes no claims to disagree with.
        others = {
            other: text
            for other, text in analyses.items()
            if other != name and not text.startswith(GAP_PREFIX)
        }
        if not others:
            continue
        human = (
            f"You are the {name} specialist. Your report:\n{fence(analyses[name], 'your report')}\n\n"
            f"The other reports:\n\n{_reports_text(others)}"
        )
        prompts[name] = [SystemMessage(_CRITIQUE_PROMPT + RULES), HumanMessage(human)]

    metrics: dict = {}
    with track("critique", metrics) as t:
        # The specialists critique each other, so this is their model, not the Chief's.
        critiques = _ask_each(SpecialistCritique, prompts, t, "Critique by", SPECIALIST)
    conflicts = [conflict for critique in critiques.values() for conflict in critique.conflicts]

    logger.debug("Critique round: %d conflicts raised", len(conflicts))
    return {"conflicts": conflicts, "metrics": metrics}


_RESOLVE_PROMPT = (
    "You are the Chief of Staff. Your specialists disagree on the points below, and "
    "the launch strategy can follow only one position on each. Treat the same clash "
    "raised by more than one specialist as one conflict, and decide each one. Weigh "
    "the options in this order: the founder's hard constraints (budget, runway, team, "
    "legal requirements); then the evidence and reasoning in the specialists' reports; "
    "then which option keeps the most choices open at the lowest cost. A legal or "
    "safety requirement outranks speed or revenue. State each decision concretely (a "
    "figure, a scope, a date) with its main reason, in one or two sentences, and name "
    "the one specialist whose report must change to match it, or none. Keep the "
    "decisions consistent with each other."
)


def resolve_node(state: WorkflowState) -> dict:
    """Settle the round's conflicts and decide which specialists must revise.

    All conflicts go to the Chief of Staff in one call, so a clash raised from
    both sides is decided once and the decisions stay consistent.
    """
    assigned = set(state["assignments"])
    round_no = state.get("critique_round", 0) + 1
    conflicts = state.get("conflicts", [])

    resolutions: list[Resolution] = []
    metrics: dict = {}
    with track("resolve", metrics) as t:
        if conflicts:
            human = (
                f"{_founder_brief(state)}\n\n"
                f"The specialists' reports:\n\n{_reports_text(state['analyses'])}\n\n"
                "Conflicts raised:\n"
                + "\n".join(f"- {c.raised_by} about {c.about}: {c.issue}" for c in conflicts)
            )
            messages = [SystemMessage(_RESOLVE_PROMPT + RULES), HumanMessage(human)]
            decided: Resolutions | None = _attempt(
                lambda: structured_invoke(Resolutions, messages, t), "Resolving the conflicts"
            )
            if decided is not None:
                resolutions = decided.resolutions

    revisions = {}
    if round_no <= MAX_CRITIQUE_ROUNDS:
        for resolution in resolutions:
            target = resolution.revise
            if target in assigned:  # one specialist may have several decisions to apply
                earlier = revisions.get(target)
                revisions[target] = (
                    f"{earlier}\n{resolution.decision}" if earlier else resolution.decision
                )

    logger.debug("Resolved %d conflicts; %d to revise", len(resolutions), len(revisions))
    return {
        "resolutions": resolutions,
        "critique_revisions": revisions,
        "critique_round": round_no,
        "metrics": metrics,
    }


_SYNTHESIS_PROMPT = (
    "You are the Chief of Staff of a startup founding team. Merge the specialist "
    "reports below into one launch strategy the founder can act on. Lead with the "
    "recommendation: go, go with conditions, or not yet, and the main reason. Then give "
    "the few facts from the reports that drive it; how each disagreement you settled "
    "was decided; the key risks and how the plan contains them; prioritised next "
    "steps, each with the area that owns it and a timeframe; and the early metrics that "
    "will show whether it is working. Make the parts agree: the budget, prices, scope "
    "and timeline must be the same wherever they appear. Use only what the specialists "
    "reported; add nothing new, and keep the source citation, such as [2], on any figure "
    "that carries one. Where you have already settled a disagreement, follow "
    "your decision. If a report is marked unavailable, name that gap in the strategy "
    "and proceed with the reports you do have. Use short markdown headings and bullet "
    f"points. Keep the strategy to at most {STRATEGY_WORDS} words."
)


def _reports_text(analyses: dict[str, str]) -> str:
    """The reports as another agent reads them: written from the founder's and
    the web's text, so fenced like it."""
    return "\n\n".join(f"## {name}\n{fence(report, f'the {name} report')}" for name, report in analyses.items())


def _decisions_text(resolutions: list[Resolution]) -> str:
    return "\n".join(
        f"- {r.conflict.raised_by} vs {r.conflict.about}: {r.conflict.issue} "
        f"Decision: {r.decision}"
        for r in resolutions
    )


def synthesis_node(state: WorkflowState) -> dict:
    """Merge the specialist reports, and any conflict decisions, into one strategy."""
    logger.debug("Synthesising %d reports", len(state["analyses"]))
    human = (
        f"{_founder_brief(state)}\n\nObjective: {state['plan'].objective}\n\n"
        f"Specialist reports:\n\n{_reports_text(state['analyses'])}"
    )
    resolutions = state.get("resolutions", [])
    if resolutions:
        human += f"\n\nDisagreements you settled:\n{_decisions_text(resolutions)}"
    metrics: dict = {}
    with track("synthesis", metrics) as t:
        reply = get_llm(CHIEF).invoke([SystemMessage(_SYNTHESIS_PROMPT + RULES), HumanMessage(human)])
        t.record(reply)
    return {"final_strategy": unfenced(reply.content), "metrics": metrics}
