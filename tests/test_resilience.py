"""Tests for metrics, speed and graceful failure (Step 10)."""

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage

from agents.chief_of_staff import _SYNTHESIS_PROMPT, STRATEGY_WORDS, structured_invoke
from agents.roles import REPORT_WORDS, SPECIALISTS
from agents.specialist import GAP_PREFIX
from graph import build_graph
from llm import LLMReplyError
from metrics import track
from state import Conflict, DelegationPlan, ReviewResult, SpecialistCritique, Task

APPROVED = ReviewResult(approved=True, score=5, feedback="")
OFFLINE = openai.APIConnectionError(request=httpx.Request("POST", "https://llm.example"))


class _ScriptedModel:
    """A model whose structured replies are scripted; an exception is raised."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def with_structured_output(self, schema, include_raw=False):
        return self

    def invoke(self, messages):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _reply(parsed, error=None):
    """A structured reply as LangChain returns it with include_raw=True."""
    raw = AIMessage("", usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    return {"raw": raw, "parsed": parsed, "parsing_error": error}


def test_metrics_are_recorded_per_node(fake_llm, thread):
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    metrics = result["metrics"]
    assert "plan" in metrics
    assert "synthesis" in metrics
    assert metrics["plan"].calls >= 1
    # Every assigned specialist recorded a node metric.
    for name in result["assignments"]:
        assert metrics[name].calls >= 1


def test_structured_calls_count_their_tokens(fake_llm, thread):
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    per_call = fake_llm.USAGE["total_tokens"]
    assert result["metrics"]["plan"].tokens == per_call
    # One review call for each of the four reports.
    assert result["metrics"]["review"].tokens == 4 * per_call


def test_review_and_critique_calls_run_at_the_same_time(fake_llm, thread):
    fake_llm.delay = 0.25
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    # Four calls in each node, yet each node took about as long as one call.
    for node in ("review", "critique"):
        assert result["metrics"][node].calls == 4
        assert result["metrics"][node].seconds < 2 * fake_llm.delay


def test_reports_and_the_strategy_have_a_word_limit():
    for role in SPECIALISTS:
        assert f"at most {REPORT_WORDS} words" in role.system_prompt
    assert f"at most {STRATEGY_WORDS} words" in _SYNTHESIS_PROMPT


def test_an_unusable_reply_is_retried_once(monkeypatch):
    model = _ScriptedModel(_reply(None, ValueError("not JSON")), _reply(APPROVED))
    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda role=None: model)
    metrics: dict = {}

    with track("review", metrics) as t:
        review = structured_invoke(ReviewResult, [], t)

    assert review == APPROVED
    # Both attempts are counted, with their tokens.
    assert metrics["review"].calls == 2
    assert metrics["review"].tokens == 4


def test_a_reply_that_never_parses_raises(monkeypatch):
    model = _ScriptedModel(_reply(None, ValueError("x")), _reply(None, ValueError("x")))
    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda role=None: model)

    with track("review", {}) as t, pytest.raises(LLMReplyError):
        structured_invoke(ReviewResult, [], t)


def test_a_reply_the_content_filter_withheld_is_retried_once(monkeypatch):
    # Azure's filter sometimes withholds a harmless reply; a second attempt clears it.
    filtered = openai.ContentFilterFinishReasonError()
    model = _ScriptedModel(filtered, _reply(APPROVED))
    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda role=None: model)

    with track("review", {}) as t:
        assert structured_invoke(ReviewResult, [], t) == APPROVED

    model = _ScriptedModel(filtered, openai.ContentFilterFinishReasonError())
    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda role=None: model)
    with track("review", {}) as t, pytest.raises(LLMReplyError):
        structured_invoke(ReviewResult, [], t)


def test_an_api_error_is_not_retried_on_top_of_the_client(monkeypatch):
    # The client already retries API errors (LLM_MAX_RETRIES); retrying them
    # again here would multiply the wait.
    model = _ScriptedModel(OFFLINE)
    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda role=None: model)

    with track("review", {}) as t, pytest.raises(openai.APIConnectionError):
        structured_invoke(ReviewResult, [], t)
    assert model.calls == 1


def test_a_failed_specialist_does_not_sink_the_run(fake_llm, thread):
    fake_llm.plan = DelegationPlan(
        objective="Evaluate the venture.",
        tasks=[
            Task(specialist="marketing", task="Position it."),
            Task(specialist="finance", task="Price it."),
        ],
    )
    fake_llm.fail = {"finance"}
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    # The run still finished with a strategy, and the gap is named.
    assert result["final_strategy"]
    assert GAP_PREFIX in result["analyses"]["finance"]
    assert GAP_PREFIX in result["final_strategy"]
    # The healthy specialist still produced a real report.
    assert GAP_PREFIX not in result["analyses"]["marketing"]


def test_a_failed_review_leaves_the_report_unreviewed(fake_llm, thread):
    def review_for(report):
        if "Financial Planning Agent" in report:
            raise OFFLINE
        return APPROVED

    fake_llm._review_for = review_for
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    assert result["final_strategy"]
    assert "finance" not in result["reviews"]
    assert fake_llm.specialist_calls["finance"] == 1  # not sent back to revise


def test_a_failed_resolve_call_does_not_sink_the_run(fake_llm, thread):
    fake_llm.plan = DelegationPlan(
        objective="Launch on a small budget.",
        tasks=[
            Task(specialist="marketing", task="Position it."),
            Task(specialist="risk", task="Flag the risks."),
        ],
    )
    fake_llm.critique = SpecialistCritique(
        conflicts=[Conflict(raised_by="risk", about="marketing", issue="Too expensive.")]
    )

    def resolutions_for(prompt):
        raise OFFLINE

    fake_llm._resolutions_for = resolutions_for
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    assert result["final_strategy"]
    assert result["resolutions"] == []
