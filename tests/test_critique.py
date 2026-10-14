"""Tests for the cross-specialist critique (Step 7)."""

from graph import build_graph
from state import Conflict, DelegationPlan, Resolution, SpecialistCritique, Task

PLAN = DelegationPlan(
    objective="Launch on a small budget.",
    tasks=[
        Task(specialist="marketing", task="Position the product."),
        Task(specialist="risk", task="Flag the risks."),
    ],
)

CONFLICT = Conflict(
    raised_by="risk",
    about="marketing",
    issue="Premium pricing clashes with the tiny budget.",
)


def test_conflict_is_flagged_resolved_and_reaches_the_specialist(fake_llm):
    fake_llm.plan = PLAN
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT])
    fake_llm.resolution = Resolution(
        conflict=CONFLICT,
        decision="Start with a lean pilot price.",
        revise="marketing",
    )
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."})

    # The conflict was resolved and recorded.
    assert len(result["resolutions"]) == 1
    assert result["resolutions"][0].decision == "Start with a lean pilot price."
    # The affected specialist revised using the decision.
    assert fake_llm.specialist_calls["marketing"] == 2
    assert "Start with a lean pilot price." in result["analyses"]["marketing"]
    # The unaffected specialist did not revise.
    assert fake_llm.specialist_calls["risk"] == 1
    assert result["final_strategy"]


def test_no_conflicts_means_no_extra_round(fake_llm):
    fake_llm.plan = PLAN
    # Default critique raises nothing.
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."})

    assert result.get("resolutions", []) == []
    assert fake_llm.specialist_calls["marketing"] == 1
    assert fake_llm.specialist_calls["risk"] == 1
    assert fake_llm.synthesis_calls == 1
