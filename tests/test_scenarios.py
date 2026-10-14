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
