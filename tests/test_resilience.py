"""Tests for metrics and graceful failure (Step 10)."""

from agents.specialist import GAP_PREFIX
from graph import build_graph
from state import DelegationPlan, Task


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
