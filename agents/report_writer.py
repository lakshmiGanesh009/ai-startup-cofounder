"""Detailed version of a session's report, written on demand.

Evaluations keep each report short so they stay fast. When the founder asks for
a detailed report, each specialist expands its own section from the report as it
now stands (edits included), all of them at the same time, and the Chief of
Staff then rewrites the strategy from the expanded sections. The decisions on
conflicts are kept as they are. A section whose call fails keeps its text.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import ContextThreadPoolExecutor

from agents.roles import ROLES
from agents.specialist import GAP_PREFIX
from llm import LLM_ERRORS, get_llm
from metrics import track
from reports import DECISIONS, STRATEGY, Report

logger = logging.getLogger(__name__)

_EXPAND = (
    "Write your section of the founder's written launch report. Expand your report "
    "below into a complete section: keep every recommendation, figure and decision in "
    "it, and add the reasoning, assumptions, numbers and next steps behind them. Do not "
    "contradict the decisions the Chief of Staff made. Write it as a finished document "
    "for the founder: leave out remarks about word limits, revisions or what changed. "
    "Use markdown: start each part with a '### ' heading and use bullet points. About "
    "600 to 900 words. Start with the content, not a title for the whole section."
)

_STRATEGY = (
    "You are the Chief of Staff of a startup founding team. Write the launch strategy "
    "section of the founder's written report from the specialists' detailed sections "
    "below: a short executive summary, the recommendation and the reasoning behind it, "
    "how the specialists' disagreements were settled, the main risks, and prioritised "
    "next steps. Use only what the sections say; add nothing new, and leave out remarks "
    "about word limits, revisions or what changed. Use markdown: start "
    "each part with a '### ' heading and use bullet points. About 800 to 1,200 words. "
    "Start with the content, not a title for the whole section."
)


def _background(report: Report) -> str:
    """What every writer is told about the venture."""
    text = f"Startup request:\n{report.title}\n\nObjective: {report.objective}"
    if report.context:
        text += f"\n\n{report.context}"
    decisions = next((s.body for s in report.sections if s.key == DECISIONS), "")
    if decisions:
        text += f"\n\nDecisions the Chief of Staff made on the team's disagreements:\n{decisions}"
    return text


def _write(messages: list, tracker, what: str) -> str | None:
    """One LLM call; None, logged, if it fails."""
    try:
        reply = get_llm().invoke(messages)
    except LLM_ERRORS as error:
        logger.warning("%s failed: %s", what, error)
        return None
    tracker.record(reply)
    return reply.content


def write_detailed(report: Report) -> tuple[dict[str, str], list[str]]:
    """Expand the report's specialist sections and strategy.

    Returns the new text keyed by section, and the titles of the sections that
    could not be expanded.
    """
    sections = {section.key: section for section in report.sections}
    background = _background(report)
    # An unavailable report has nothing to expand.
    specialists = [
        key for key, section in sections.items()
        if key in ROLES and not section.body.startswith(GAP_PREFIX)
    ]

    def expand(key: str) -> str | None:
        role = ROLES[key]
        human = f"{background}\n\nYour report:\n{sections[key].body}"
        return _write(
            [SystemMessage(f"{role.brief} {_EXPAND}"), HumanMessage(human)],
            tracker, f"Detailed {role.title} section",
        )

    metrics: dict = {}
    with track("detailed", metrics) as tracker:
        with ContextThreadPoolExecutor(max_workers=max(len(specialists), 1)) as pool:
            expanded = dict(zip(specialists, pool.map(expand, specialists)))
        bodies = {key: text for key, text in expanded.items() if text}

        if STRATEGY in sections:
            parts = "\n\n".join(
                f"## {section.title}\n{bodies.get(key, section.body)}"
                for key, section in sections.items() if key in ROLES
            )
            human = f"{background}\n\nThe specialists' detailed sections:\n\n{parts}"
            strategy = _write(
                [SystemMessage(_STRATEGY), HumanMessage(human)], tracker, "Detailed strategy"
            )
            if strategy:
                bodies[STRATEGY] = strategy

    attempted = [*specialists, STRATEGY] if STRATEGY in sections else specialists
    failed = [sections[key].title for key in attempted if key not in bodies]
    metric = metrics["detailed"]
    logger.info(
        "Detailed report for %s: %d calls, %d tokens, %.1f s",
        report.session_id, metric.calls, metric.tokens, metric.seconds,
    )
    return bodies, failed
