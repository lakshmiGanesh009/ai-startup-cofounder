"""LLM-as-a-judge: an independent reading of a launch strategy against its
brief, as scores in Langfuse.

The team's own review checks each report on its way to the strategy; this
reads the strategy the founder gets, on four things a founder would hold it
to, each from 1 to 5, with what lowers them most. The experiments
(experiments.py) judge every run; a live evaluation is judged too when
LANGFUSE_JUDGE is on, after its answer has gone, at the cost of one more call
to the Chief of Staff's model.
"""

import logging
import os
import threading

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import tracing
from guardrails import RULES, fence
from llm import CHIEF, LLM_ERRORS
from metrics import track

log = logging.getLogger(__name__)


class Judgement(BaseModel):
    constraints: int = Field(description="1 to 5: it respects the founder's budget, team, runway and deadlines.")
    consistency: int = Field(description="1 to 5: its prices, budget, timeline and scope agree everywhere.")
    actionability: int = Field(description="1 to 5: concrete next steps with owners and timeframes, and early metrics.")
    grounding: int = Field(description="1 to 5: its claims come from the specialists' reports and cited figures.")
    comment: str = Field(description="What lowers the scores most, in one or two sentences.")


JUDGE_PROMPT = (
    "You judge a launch strategy a startup's founding team wrote for its founder. Read the founder's "
    "brief and the strategy, and score the strategy from 1 (poor) to 5 (excellent) on four things: "
    "constraints, whether it respects every limit the brief states (budget, team, runway, deadlines); "
    "consistency, whether its prices, budget, timeline and scope agree wherever they appear; "
    "actionability, whether its next steps name owners and timeframes and it says how success will be "
    "measured early; grounding, whether its claims rest on the specialists' work it cites, not on "
    "assertion. Be strict: 3 is adequate, 5 rare. Then say in one or two sentences what lowers the "
    "scores most."
)

CRITERIA = ("constraints", "consistency", "actionability", "grounding")


def judge(brief: str, strategy: str) -> Judgement:
    """The judge's scores for `strategy`, written for `brief`. Raises an LLM error if the call fails."""
    from agents.chief_of_staff import structured_invoke

    human = f"The founder's brief:\n{fence(brief, 'founder')}\n\nThe launch strategy:\n{fence(strategy, 'the team report')}"
    with track("judge", {}) as tracker:
        return structured_invoke(Judgement, [SystemMessage(JUDGE_PROMPT + RULES), HumanMessage(human)],
                                 tracker, CHIEF, "judge/strategy")


def scores(judgement: Judgement) -> dict[str, int]:
    """The judgement as scores, named as in Langfuse; each kept between 1 and 5."""
    return {f"judge-{name}": min(5, max(1, getattr(judgement, name))) for name in CRITERIA}


def enabled() -> bool:
    return tracing.enabled() and os.getenv("LANGFUSE_JUDGE", "").strip().lower() in {"1", "true", "yes", "on"}


def judge_later(trace_id: str, session_id: str, brief: str, strategy: str) -> None:
    """Judge a live evaluation in a thread of its own, after its answer has
    gone, and score its trace; the judge's own call is traced on its own."""

    def run():
        try:
            with tracing.trace("judge", session_id=session_id, tags=["judge"]):
                judgement = judge(brief, strategy)
        except LLM_ERRORS as error:
            log.warning("The judge could not read the strategy: %s", error)
            return
        for name, value in scores(judgement).items():
            tracing.score(name, value, trace_id=trace_id, comment=judgement.comment)

    threading.Thread(target=run, name="langfuse-judge", daemon=True).start()
