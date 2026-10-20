"""Tests for follow-up requests within a session (Step 8)."""

from agents.specialist import GAP_PREFIX
from graph import build_graph
from state import DelegationPlan, RequestContext, ReviewResult, Task

FIRST = DelegationPlan(
    objective="Evaluate the venture.",
    tasks=[Task(specialist=name, task=f"Handle {name}.") for name in
           ("marketing", "finance", "technical", "risk")],
)
FOLLOW_UP = DelegationPlan(
    objective="Refine the pricing.",
    tasks=[Task(specialist="finance", task="Refine the pricing after review.")],
)


def test_follow_up_reruns_only_the_affected_specialist(fake_llm, thread):
    graph = build_graph()

    fake_llm.plan = FIRST
    first = graph.invoke({"request": "Evaluate an AI tool."}, thread)
    assert set(first["analyses"]) == {"marketing", "finance", "technical", "risk"}
    calls_after_first = dict(fake_llm.specialist_calls)

    fake_llm.plan = FOLLOW_UP
    second = graph.invoke(
        {"request": "Refine the pricing strategy after financial review."}, thread
    )

    # The follow-up reran only finance; the others kept their first report.
    assert fake_llm.specialist_calls["finance"] == calls_after_first["finance"] + 1
    assert fake_llm.specialist_calls["marketing"] == calls_after_first["marketing"]
    # All four reports are still present in the strategy.
    assert set(second["analyses"]) == {"marketing", "finance", "technical", "risk"}


def test_follow_up_builds_on_the_original_request_and_report(fake_llm, thread):
    graph = build_graph()

    fake_llm.plan = FIRST
    first = graph.invoke({"request": "Evaluate an AI tool."}, thread)

    fake_llm.plan = FOLLOW_UP
    second = graph.invoke(
        {"request": "Refine the pricing strategy after financial review."}, thread
    )

    # The fake model echoes the prompt, so the report shows what finance was given.
    refined = second["analyses"]["finance"]
    # The report shows the prompt without its fences (guardrails.unfenced).
    assert "Startup request:\nEvaluate an AI tool." in refined
    assert "Follow-up request:\nRefine the pricing strategy" in refined
    assert first["analyses"]["finance"] in refined


def test_follow_up_critiques_only_the_reassigned_specialist(fake_llm, thread):
    graph = build_graph()
    critique_prompts = []
    critique_for = fake_llm._critique_for
    fake_llm._critique_for = lambda prompt: critique_prompts.append(prompt) or critique_for(prompt)

    fake_llm.plan = FIRST
    graph.invoke({"request": "Evaluate an AI tool."}, thread)
    assert len(critique_prompts) == 4  # every specialist on the first request

    fake_llm.plan = FOLLOW_UP
    critique_prompts.clear()
    graph.invoke({"request": "Refine the pricing strategy after financial review."}, thread)

    # Only finance changed, so only finance critiques, against all three others.
    assert len(critique_prompts) == 1
    assert "You are the finance specialist" in critique_prompts[0]
    for other in ("## marketing", "## technical", "## risk"):
        assert other in critique_prompts[0]


def test_follow_up_reports_only_its_own_reviews_and_cost(fake_llm, thread):
    graph = build_graph()

    fake_llm.plan = FIRST
    graph.invoke({"request": "Evaluate an AI tool."}, thread)

    fake_llm.plan = FOLLOW_UP
    second = graph.invoke(
        {"request": "Refine the pricing strategy after financial review."}, thread
    )

    # Only the follow-up's own review round, covering only finance.
    assert len(second["review_history"]) == 1
    assert set(second["review_history"][0]) == {"finance"}
    # Metrics count this request only: one plan call, and no entry for the
    # specialists that kept their earlier report.
    assert second["metrics"]["plan"].calls == 1
    assert second["metrics"]["finance"].calls == 1
    assert "marketing" not in second["metrics"]


def test_follow_up_restores_every_state_model(fake_llm, thread):
    # The checkpointer only restores registered types; a missing one would come
    # back as a plain dict and break the follow-up.
    graph = build_graph()

    fake_llm.plan = FIRST
    graph.invoke(
        {"request": "Evaluate an AI tool.", "context": RequestContext(target_market="Clinics")},
        thread,
    )

    fake_llm.plan = FOLLOW_UP
    second = graph.invoke({"request": "Refine the pricing."}, thread)

    assert isinstance(second["context"], RequestContext)
    assert all(isinstance(r, ReviewResult) for r in second["reviews"].values())
    assert not second["analyses"]["finance"].startswith(GAP_PREFIX)
    assert "Target market: Clinics" in second["analyses"]["finance"]


def test_a_different_session_starts_clean(fake_llm):
    graph = build_graph()
    fake_llm.plan = FOLLOW_UP  # names only finance

    result = graph.invoke(
        {"request": "Refine the pricing."},
        {"configurable": {"thread_id": "fresh-session"}},
    )

    # No prior reports, so only the finance report exists.
    assert set(result["analyses"]) == {"finance"}
