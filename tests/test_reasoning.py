"""Tests for how the Chief of Staff reasons: on its own model, with the founder's
constraints in front of it."""

from graph import build_graph
from llm import CHIEF, SPECIALIST
from state import (
    Conflict,
    DelegationPlan,
    RequestContext,
    Resolution,
    SpecialistCritique,
    Task,
)

PLAN = DelegationPlan(
    objective="Decide how to price the pilot.",
    tasks=[
        Task(specialist="marketing", task="Position the product."),
        Task(specialist="finance", task="Price the pilot."),
    ],
)
CONFLICT = Conflict(raised_by="finance", about="marketing", issue="$99 against $149.")
REQUEST = {
    "request": "Evaluate an AI scheduling tool.",
    "context": RequestContext(constraints="Under $15k to launch"),
}


def _with_a_conflict(fake_llm):
    fake_llm.plan = PLAN
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT])
    fake_llm.resolution = Resolution(conflict=CONFLICT, decision="Price at $149.", revise="")


def test_the_chief_of_staffs_decisions_run_on_its_own_model(fake_llm, thread):
    _with_a_conflict(fake_llm)

    build_graph().invoke(REQUEST, thread)

    roles = {}
    for role, what in fake_llm.calls:
        kind = "synthesis" if "launch strategy" in what else (
            "specialist report" if "Agent on a startup founding team" in what else what
        )
        roles.setdefault(kind, set()).add(role)
    assert roles == {
        "DelegationPlan": {CHIEF},
        "ReviewResult": {CHIEF},
        "Resolutions": {CHIEF},
        "synthesis": {CHIEF},
        # The specialists, and their critiques of each other, keep their own model.
        "specialist report": {SPECIALIST},
        "SpecialistCritique": {SPECIALIST},
    }


def test_the_chief_of_staff_sees_the_founders_request_and_constraints(fake_llm, thread):
    _with_a_conflict(fake_llm)
    prompts = {"review": [], "resolve": []}
    review_for, resolutions_for = fake_llm._review_for, fake_llm._resolutions_for
    fake_llm._review_for = lambda prompt: prompts["review"].append(prompt) or review_for(prompt)
    fake_llm._resolutions_for = (
        lambda prompt: prompts["resolve"].append(prompt) or resolutions_for(prompt)
    )

    result = build_graph().invoke(REQUEST, thread)

    for prompt in [*prompts["review"], *prompts["resolve"], result["final_strategy"]]:
        assert "Founder request:\nEvaluate an AI scheduling tool." in prompt
        assert "Constraints: Under $15k to launch" in prompt
    # Conflicts are decided with the reports themselves in view, not just the
    # one-line summary of each clash.
    assert "## marketing" in prompts["resolve"][0]
    assert "## finance" in prompts["resolve"][0]


def test_a_request_sets_how_hard_each_role_reasons(fake_llm, monkeypatch):
    # The efforts must reach the calls made in the graph's worker threads.
    from fastapi.testclient import TestClient

    from main import app

    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "minimal")
    monkeypatch.setenv("AZURE_OPENAI_CHIEF_REASONING_EFFORT", "medium")
    client = TestClient(app)

    response = client.post("/evaluate", json={
        "prompt": "Evaluate an AI scheduling tool.",
        "reasoning": {"specialist": "low", "chief": "high"},
    })

    assert response.status_code == 200
    assert set(fake_llm.efforts) == {(SPECIALIST, "low"), (CHIEF, "high")}

    fake_llm.efforts.clear()
    session_id = response.json()["session_id"]
    version = client.get(f"/reports/{session_id}").json()["version"]
    written = client.post(f"/reports/{session_id}/proposal",
                          json={"version": version, "reasoning": {"chief": "low"}})
    assert written.status_code == 200
    # A role left out keeps the configured effort.
    assert set(fake_llm.efforts) == {(SPECIALIST, "minimal"), (CHIEF, "low")}

    fake_llm.efforts.clear()
    client.post("/evaluate", json={"prompt": "Refine the pricing.", "session_id": session_id})
    assert set(fake_llm.efforts) <= {(SPECIALIST, "minimal"), (CHIEF, "medium")}


def test_only_the_efforts_that_reason_can_be_chosen(fake_llm, monkeypatch):
    from fastapi.testclient import TestClient

    from main import app

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_CHIEF_REASONING_EFFORT", "medium")
    client = TestClient(app)

    # "xhigh" is accepted by the deployment but does no reasoning at all.
    response = client.post("/evaluate", json={"prompt": "Idea", "reasoning": {"chief": "xhigh"}})
    assert response.status_code == 422

    reasoning = client.get("/health").json()["reasoning"]
    assert reasoning == {"adjustable": True, "efforts": ["minimal", "low", "medium", "high"],
                         "specialist": None, "chief": "medium"}
