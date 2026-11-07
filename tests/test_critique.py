"""Tests for the cross-specialist critique (Step 7)."""

from typing import get_args

import pytest
from pydantic import ValidationError

from agents.roles import SPECIALISTS
from graph import build_graph
from state import (
    Conflict,
    DelegationPlan,
    Resolution,
    Resolutions,
    SpecialistCritique,
    SpecialistName,
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


def test_structured_outputs_can_only_name_the_four_specialists():
    # The model fills these fields through a strict JSON schema, so a name it
    # writes another way ("Finance specialist") cannot get through.
    assert set(get_args(SpecialistName)) == {role.name for role in SPECIALISTS}
    with pytest.raises(ValidationError):
        Task.model_validate({"specialist": "Finance specialist", "task": "Price it."})
    with pytest.raises(ValidationError):
        Resolution.model_validate({"conflict": CONFLICT, "decision": "Lower the price.", "revise": "Marketing"})
    # Empty means no specialist has to revise.
    assert Resolution(conflict=CONFLICT, decision="Keep both.", revise="").revise == ""


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
    fake_llm._resolutions_for = lambda prompt: resolve_prompts.append(prompt) or decisions
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    # Both conflicts were settled together, in one call.
    assert len(resolve_prompts) == 1
    assert "The pilot is too long." in resolve_prompts[0]
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


def test_no_one_critiques_against_an_unavailable_report(fake_llm, thread):
    fake_llm.plan = PLAN
    fake_llm.fail = {"marketing"}
    critique_prompts = []
    critique_for = fake_llm._critique_for
    fake_llm._critique_for = lambda prompt: critique_prompts.append(prompt) or critique_for(prompt)
    graph = build_graph()

    result = graph.invoke({"request": "Premium pricing on a very small budget."}, thread)

    # Risk's only counterpart is a gap, so there is nothing to critique.
    assert critique_prompts == []
    assert result["final_strategy"]
