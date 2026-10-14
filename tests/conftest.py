"""Shared test fixtures.

`strip_credentials` runs for every test so no test can reach a real model.
`fake_llm` replaces the chat model with one that echoes the prompt back, so
graph and API tests are deterministic and need no credentials.
"""

import pytest
from langchain_core.messages import AIMessage, SystemMessage

PROVIDER_VARS = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_REASONING_EFFORT",
    "OPENAI_API_KEY",
    "MODEL_NAME",
]


@pytest.fixture(autouse=True)
def strip_credentials(monkeypatch):
    """Remove every provider variable so tests never hit a real LLM."""
    for name in PROVIDER_VARS:
        monkeypatch.delenv(name, raising=False)


from state import DelegationPlan, Task

SPECIALIST_NAMES = ("marketing", "finance", "technical", "risk")


class FakeModel:
    """A chat model stand-in.

    Specialist calls get an echoed reply. The Chief of Staff's planning call
    uses `with_structured_output`, which returns `plan` (all four specialists by
    default; tests can set a narrower plan).
    """

    def __init__(self):
        self.plan = DelegationPlan(
            objective="Evaluate the request.",
            tasks=[Task(specialist=name, task=f"Handle {name}.") for name in SPECIALIST_NAMES],
        )

    def invoke(self, messages):
        system = next((m.content for m in messages if isinstance(m, SystemMessage)), "")
        human = messages[-1].content
        return AIMessage(f"[role: {system}]\n{human}")

    def with_structured_output(self, schema):
        plan = self.plan
        return _StructuredModel(plan)


class _StructuredModel:
    """What `with_structured_output` returns: invoke yields the fixed plan."""

    def __init__(self, plan):
        self._plan = plan

    def invoke(self, messages):
        return self._plan


@pytest.fixture
def fake_llm(monkeypatch):
    """Make every get_llm() call return the FakeModel (shared by plan and specialists)."""
    model = FakeModel()
    monkeypatch.setattr("agents.specialist.get_llm", lambda: model)
    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda: model)
    return model
