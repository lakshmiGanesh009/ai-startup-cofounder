"""Every scenario file loads and passes request validation (Step 9)."""

import json
from pathlib import Path

import pytest

from main import EvaluateRequest

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"
SCENARIOS = sorted(SCENARIO_DIR.glob("*.json"))


def test_at_least_three_scenarios_exist():
    assert len(SCENARIOS) >= 3


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.name)
def test_scenario_loads_and_validates(path):
    data = json.loads(path.read_text(encoding="utf-8"))

    request = EvaluateRequest(prompt=data["prompt"], context=data.get("context"))

    assert request.prompt
    assert request.context is not None


def test_the_demo_walks_through_a_scenario_and_its_follow_up(fake_llm, capsys):
    import demo

    demo.main(str(SCENARIO_DIR / "healthcare_scheduling.json"))

    printed = capsys.readouterr().out
    for stage in ("REQUEST", "PLAN", "SPECIALIST REPORTS", "REVIEW HISTORY", "FINAL STRATEGY",
                  "FOLLOW-UP"):
        assert stage in printed
    assert "Refine the pricing strategy after financial review." in printed


def test_the_demo_shows_conflicts_and_their_resolution(fake_llm, capsys, tmp_path):
    import demo
    from state import Conflict, Resolution, SpecialistCritique

    conflict = Conflict(raised_by="finance", about="marketing", issue="The pilot price is too low.")
    fake_llm.critique = SpecialistCritique(conflicts=[conflict])
    fake_llm.resolution = Resolution(conflict=conflict, decision="Price at $149.", revise="")
    scenario = tmp_path / "idea.json"
    scenario.write_text(json.dumps({"prompt": "Evaluate an AI scheduling tool."}))

    demo.main(str(scenario))

    printed = capsys.readouterr().out
    assert "CROSS-CRITIQUE RESOLUTIONS" in printed
    assert "finance vs marketing: The pilot price is too low." in printed
    assert "-> Price at $149. (revise: none)" in printed
    assert "FOLLOW-UP" not in printed


def test_the_demo_explains_how_to_run_it(monkeypatch, capsys):
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["demo.py"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(SCENARIO_DIR.parent / "demo.py"), run_name="__main__")

    assert stopped.value.code == 1
    assert "Usage: uv run python demo.py" in capsys.readouterr().out

