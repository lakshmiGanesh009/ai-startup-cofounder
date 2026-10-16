"""Tests for follow-up requests within a session (Step 8)."""

from graph import build_graph
from state import DelegationPlan, Task

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


def test_a_different_session_starts_clean(fake_llm):
    graph = build_graph()
    fake_llm.plan = FOLLOW_UP  # names only finance

    result = graph.invoke(
        {"request": "Refine the pricing."},
        {"configurable": {"thread_id": "fresh-session"}},
    )

    # No prior reports, so only the finance report exists.
    assert set(result["analyses"]) == {"finance"}
