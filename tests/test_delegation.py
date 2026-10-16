"""Tests for the Chief of Staff's planning and delegation (Step 4)."""

from graph import build_graph
from state import DelegationPlan, Task

REQUEST = "Identify risks in our go-to-market plan."


def test_narrow_plan_runs_only_assigned_specialists(fake_llm, thread):
    fake_llm.plan = DelegationPlan(
        objective="Assess go-to-market risk.",
        tasks=[
            Task(specialist="risk", task="Flag the risks."),
            Task(specialist="marketing", task="Review the plan."),
        ],
    )
    graph = build_graph()

    result = graph.invoke({"request": REQUEST}, thread)

    assert set(result["analyses"]) == {"risk", "marketing"}


def test_two_tasks_for_one_specialist_are_merged(fake_llm, thread):
    fake_llm.plan = DelegationPlan(
        objective="Assess go-to-market risk.",
        tasks=[
            Task(specialist="risk", task="Flag privacy risks."),
            Task(specialist="risk", task="Flag delivery risks."),
        ],
    )
    graph = build_graph()

    result = graph.invoke({"request": REQUEST}, thread)

    assert set(result["analyses"]) == {"risk"}
    assert "Flag privacy risks." in result["analyses"]["risk"]
    assert "Flag delivery risks." in result["analyses"]["risk"]


def test_empty_plan_falls_back_to_all_four(fake_llm, thread):
    fake_llm.plan = DelegationPlan(objective="Evaluate everything.", tasks=[])
    graph = build_graph()

    result = graph.invoke({"request": REQUEST}, thread)

    assert set(result["analyses"]) == {"marketing", "finance", "technical", "risk"}


def test_unassigned_specialist_gets_no_analysis(fake_llm, thread):
    fake_llm.plan = DelegationPlan(
        objective="Assess go-to-market risk.",
        tasks=[Task(specialist="risk", task="Flag the risks.")],
    )
    graph = build_graph()

    result = graph.invoke({"request": REQUEST}, thread)

    assert set(result["analyses"]) == {"risk"}
    assert "finance" not in result["analyses"]


def test_planner_knows_what_each_specialist_covers():
    from agents.chief_of_staff import _PLANNER_PROMPT
    from agents.roles import SPECIALISTS

    for role in SPECIALISTS:
        assert f"{role.name} ({role.focus})" in _PLANNER_PROMPT
