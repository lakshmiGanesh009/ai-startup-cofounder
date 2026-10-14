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


class FakeModel:
    """A chat model stand-in whose reply echoes the prompt it was given."""

    def invoke(self, messages):
        system = next(
            (m.content for m in messages if isinstance(m, SystemMessage)), ""
        )
        human = messages[-1].content
        return AIMessage(f"[role: {system}]\n{human}")


@pytest.fixture
def fake_llm(monkeypatch):
    """Make every get_llm() call return the FakeModel."""
    model = FakeModel()
    monkeypatch.setattr("agents.specialist.get_llm", lambda: model)
    return model
