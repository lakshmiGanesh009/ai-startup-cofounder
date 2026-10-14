"""Shared test fixtures.

`strip_credentials` runs for every test so no test can reach a real model.
`fake_llm` replaces the chat model with one that echoes the prompt back, so
graph and API tests are deterministic and need no credentials.
"""

import pytest
from langchain_core.messages import AIMessage, SystemMessage

from state import DelegationPlan, ReviewResult, Task

PROVIDER_VARS = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_REASONING_EFFORT",
    "OPENAI_API_KEY",
    "MODEL_NAME",
]

SPECIALIST_NAMES = ("marketing", "finance", "technical", "risk")


@pytest.fixture(autouse=True)
def strip_credentials(monkeypatch):
    """Remove every provider variable so tests never hit a real LLM."""
    for name in PROVIDER_VARS:
        monkeypatch.delenv(name, raising=False)


class FakeModel:
    """A chat model stand-in.

    Specialist and synthesis calls get an echoed reply. Structured calls return
    a `DelegationPlan` (planning) or a `ReviewResult` (review). Tests can set a
    narrower `plan` and per-specialist `reviews`; reports default to approved.
    `synthesis_calls` and `specialist_calls` record how often each ran.
    """

    def __init__(self):
        self.plan = DelegationPlan(
            objective="Evaluate the request.",
            tasks=[Task(specialist=name, task=f"Handle {name}.") for name in SPECIALIST_NAMES],
        )
        self.reviews: dict[str, ReviewResult] = {}
        self.synthesis_calls = 0
        self.specialist_calls: dict[str, int] = {}

    def _review_for(self, report: str) -> ReviewResult:
        for name, review in self.reviews.items():
            if name in report:
                return review
        return ReviewResult(approved=True, score=5, feedback="")

    def invoke(self, messages):
        system = next((m.content for m in messages if isinstance(m, SystemMessage)), "")
        human = messages[-1].content
        if "launch strategy" in system:
            self.synthesis_calls += 1
        else:
            for name in SPECIALIST_NAMES:
                if name in system.lower():
                    self.specialist_calls[name] = self.specialist_calls.get(name, 0) + 1
        return AIMessage(f"[role: {system}]\n{human}")

    def with_structured_output(self, schema):
        if schema is ReviewResult:
            return _ReviewModel(self._review_for)
        return _StructuredModel(self.plan)


class _StructuredModel:
    """What `with_structured_output(DelegationPlan)` returns."""

    def __init__(self, plan):
        self._plan = plan

    def invoke(self, messages):
        return self._plan


class _ReviewModel:
    """What `with_structured_output(ReviewResult)` returns.

    The verdict depends on the report text in the prompt, so a report can be
    rejected on the first pass and approved after it is revised.
    """

    def __init__(self, review_for):
        self._review_for = review_for

    def invoke(self, messages):
        return self._review_for(messages[-1].content)


@pytest.fixture
def fake_llm(monkeypatch):
    """Make every get_llm() call return the FakeModel (shared by plan and specialists)."""
    model = FakeModel()
    monkeypatch.setattr("agents.specialist.get_llm", lambda: model)
    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda: model)
    return model
