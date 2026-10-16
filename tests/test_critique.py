"""Tests for the cross-specialist critique (Step 7)."""

from types import SimpleNamespace

from graph import build_graph
from state import (
    Conflict,
    DelegationPlan,
    Resolution,
    Resolutions,
    SpecialistCritique,
    Task,
)

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


def test_conflict_is_flagged_resolved_and_reaches_the_specialist(fake_llm, thread):
    fake_llm.plan = PLAN
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT])
    fake_llm.resolution = Resolution(
        conflict=CONFLICT,
        decision="Start with a lean pilot price.",
        revise="marketing",
    )
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    # The conflict was resolved and recorded.
    assert len(result["resolutions"]) == 1
    assert result["resolutions"][0].decision == "Start with a lean pilot price."
    # The affected specialist revised using the decision.
    assert fake_llm.specialist_calls["marketing"] == 2
    assert "Start with a lean pilot price." in result["analyses"]["marketing"]
    # The unaffected specialist did not revise.
    assert fake_llm.specialist_calls["risk"] == 1
    # Synthesis is told how the conflict was settled.
    assert "Disagreements you settled:\n- risk vs marketing" in result["final_strategy"]


def test_no_critique_pass_after_the_last_allowed_round(fake_llm, thread):
    fake_llm.plan = PLAN
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT])
    fake_llm.resolution = Resolution(
        conflict=CONFLICT,
        decision="Start with a lean pilot price.",
        revise="marketing",
    )
    critique_calls = []
    critique_for = fake_llm._critique_for
    fake_llm._critique_for = lambda prompt: critique_calls.append(prompt) or critique_for(prompt)
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    # One critique call per specialist; the revision goes straight to synthesis
    # because MAX_CRITIQUE_ROUNDS (1) allows no further revision.
    assert len(critique_calls) == 2
    assert result["critique_round"] == 1
    # The round that caused the revision stays in the response.
    assert [r.decision for r in result["resolutions"]] == ["Start with a lean pilot price."]
    assert fake_llm.synthesis_calls == 1


def test_revise_target_is_matched_however_the_model_writes_it(fake_llm, thread):
    fake_llm.plan = PLAN
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT])
    fake_llm.resolution = Resolution(
        conflict=CONFLICT,
        decision="Start with a lean pilot price.",
        revise="Marketing specialist",
    )
    graph = build_graph()

    graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    assert fake_llm.specialist_calls["marketing"] == 2


def test_every_decision_for_one_specialist_reaches_it(fake_llm, thread):
    second = Conflict(raised_by="risk", about="marketing", issue="The pilot is too long.")
    fake_llm.plan = PLAN
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT, second])
    decisions = Resolutions(
        resolutions=[
            Resolution(conflict=CONFLICT, decision="Lower the pilot price.", revise="marketing"),
            Resolution(conflict=second, decision="Shorten the pilot.", revise="marketing"),
        ]
    )
    resolve_prompts = []
    structured = fake_llm.with_structured_output
    fake_llm.with_structured_output = lambda schema: (
        SimpleNamespace(invoke=lambda messages: resolve_prompts.append(messages) or decisions)
        if schema is Resolutions
        else structured(schema)
    )
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    # Both conflicts were settled together, in one call.
    assert len(resolve_prompts) == 1
    assert "The pilot is too long." in resolve_prompts[0][-1].content
    revised = result["analyses"]["marketing"]
    assert "Lower the pilot price." in revised
    assert "Shorten the pilot." in revised


def test_no_conflicts_means_no_extra_round(fake_llm, thread):
    fake_llm.plan = PLAN
    # Default critique raises nothing.
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    assert result.get("resolutions", []) == []
    assert fake_llm.specialist_calls["marketing"] == 1
    assert fake_llm.specialist_calls["risk"] == 1
    assert fake_llm.synthesis_calls == 1
