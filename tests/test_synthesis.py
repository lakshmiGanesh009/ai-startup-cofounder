"""Tests for the Chief of Staff's synthesis (Step 5)."""

from graph import build_graph
from state import DelegationPlan, Task


def test_synthesis_runs_once_and_sees_every_report(fake_llm):
    graph = build_graph()

    result = graph.invoke({"request": "Evaluate an AI healthcare scheduling tool."})

    assert fake_llm.synthesis_calls == 1
    strategy = result["final_strategy"]
    for name in result["analyses"]:
        assert f"## {name}" in strategy


def test_two_specialist_delegation_still_produces_a_strategy(fake_llm):
    fake_llm.plan = DelegationPlan(
        objective="Assess go-to-market risk.",
        tasks=[
            Task(specialist="risk", task="Flag the risks."),
            Task(specialist="marketing", task="Review the plan."),
        ],
    )
    graph = build_graph()

    result = graph.invoke({"request": "Identify risks in our go-to-market plan."})

    assert fake_llm.synthesis_calls == 1
    assert set(result["analyses"]) == {"risk", "marketing"}
    assert result["final_strategy"]
    assert "## risk" in result["final_strategy"]
    assert "## marketing" in result["final_strategy"]
