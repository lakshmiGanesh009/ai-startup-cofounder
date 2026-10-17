"""Shared test fixtures.

`strip_credentials` runs for every test so no test can reach a real model.
`fake_llm` replaces the chat model with one that echoes the prompt back, so
graph and API tests are deterministic and need no credentials.
"""

import time

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, SystemMessage

import llm
from agents.proposal_writer import SCHEMAS as PROPOSAL_SCHEMAS
from state import (
    DelegationPlan,
    Resolution,
    Resolutions,
    ReviewResult,
    SpecialistCritique,
    Task,
)
from tests.sample_proposal import SAMPLE

PROVIDER_VARS = [
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "AZURE_OPENAI_REASONING_EFFORT",
    "AZURE_OPENAI_CHIEF_REASONING_EFFORT",
    "OPENAI_API_KEY",
    "MODEL_NAME",
]

SPECIALIST_NAMES = ("marketing", "finance", "technical", "risk")

# The unique agent title in each role's system prompt, used to attribute a
# specialist call to the right role (role prompts mention each other by name).
SPECIALIST_TITLES = {
    "Marketing Strategy Agent": "marketing",
    "Financial Planning Agent": "finance",
    "Technical Feasibility Agent": "technical",
    "Risk & Compliance Agent": "risk",
}


@pytest.fixture(autouse=True)
def strip_credentials(monkeypatch):
    """Remove every provider variable, and any model already built from them, so
    tests never hit a real LLM."""
    for name in PROVIDER_VARS:
        monkeypatch.delenv(name, raising=False)
    llm._model.cache_clear()


class FakeModel:
    """A chat model stand-in.

    Specialist and synthesis calls get an echoed reply. Each structured call
    gets its reply from a `_*_for(prompt)` method, which a test can replace:
    `_plan_for` (planning), `_review_for` (review), `_critique_for` (critique)
    and `_resolutions_for` (resolve). By default those return `plan`, an
    approval unless `reviews` names the report, the `critique`'s conflicts, and
    the one `resolution` if set. Every reply reports `USAGE` tokens.

    A proposal part is taken from `proposal` (the sample one), and the prompt
    it was written from is kept in `part_prompts`; `fail_parts` names parts
    whose call raises.

    `synthesis_calls` and `specialist_calls` record how often each ran, `fail`
    names specialists whose call raises, and `delay` makes every call take that
    many seconds.
    """

    USAGE = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}

    def __init__(self):
        self.plan = DelegationPlan(
            objective="Evaluate the request.",
            tasks=[Task(specialist=name, task=f"Handle {name}.") for name in SPECIALIST_NAMES],
        )
        self.reviews: dict[str, ReviewResult] = {}
        self.critique = SpecialistCritique()
        self.resolution: Resolution | None = None
        self.synthesis_calls = 0
        self.specialist_calls: dict[str, int] = {}
        self.fail: set[str] = set()  # specialist names whose call should raise
        self.delay = 0.0
        self.proposal = SAMPLE
        self.part_prompts: dict[str, list[str]] = {}
        self.fail_parts: set[str] = set()

    def _plan_for(self, prompt: str) -> DelegationPlan:
        return self.plan

    def _review_for(self, report: str) -> ReviewResult:
        # The verdict depends on the report text in the prompt, so a report can be
        # rejected on the first pass and approved after it is revised.
        for name, review in self.reviews.items():
            if name in report:
                return review
        return ReviewResult(approved=True, score=5, feedback="")

    def _critique_for(self, prompt: str) -> SpecialistCritique:
        # Only the specialist that raises the conflict reports it, so the same
        # conflict is not counted once per specialist.
        raisers = {c.raised_by for c in self.critique.conflicts}
        mine = [c for c in self.critique.conflicts if f"the {c.raised_by} specialist" in prompt]
        return SpecialistCritique(conflicts=mine) if raisers else SpecialistCritique()

    def _resolutions_for(self, prompt: str) -> Resolutions:
        return Resolutions(resolutions=[self.resolution] if self.resolution else [])

    def invoke(self, messages):
        time.sleep(self.delay)
        system = next((m.content for m in messages if isinstance(m, SystemMessage)), "")
        human = messages[-1].content
        if "launch strategy" in system:
            self.synthesis_calls += 1
        else:
            for title, name in SPECIALIST_TITLES.items():
                if title in system:
                    self.specialist_calls[name] = self.specialist_calls.get(name, 0) + 1
                    if name in self.fail:  # as the provider fails, after its retries
                        raise _provider_error()
        return AIMessage(f"[role: {system}]\n{human}", usage_metadata=self.USAGE)

    def _part_for(self, key: str):
        def produce(prompt: str):
            self.part_prompts.setdefault(key, []).append(prompt)
            if key in self.fail_parts:
                raise _provider_error()
            return getattr(self.proposal, key)

        return produce

    def with_structured_output(self, schema, include_raw=False):
        produce = {
            DelegationPlan: self._plan_for,
            ReviewResult: self._review_for,
            SpecialistCritique: self._critique_for,
            Resolutions: self._resolutions_for,
            **{part: self._part_for(key) for key, part in PROPOSAL_SCHEMAS.items()},
        }[schema]
        return _StructuredModel(self, produce, include_raw)


def _provider_error():
    """What a provider call raises once the client has given up retrying."""
    return openai.APIConnectionError(request=httpx.Request("POST", "https://llm.example"))


class _StructuredModel:
    """What `with_structured_output(schema)` returns.

    The reply is produced from the prompt. With `include_raw` it is wrapped as
    LangChain wraps it: the raw message (with its token usage), the parsed
    object, and no parsing error.
    """

    def __init__(self, fake, produce, include_raw):
        self._fake = fake
        self._produce = produce
        self._include_raw = include_raw

    def invoke(self, messages):
        time.sleep(self._fake.delay)
        parsed = self._produce(messages[-1].content)
        if not self._include_raw:
            return parsed
        raw = AIMessage("", usage_metadata=self._fake.USAGE)
        return {"raw": raw, "parsed": parsed, "parsing_error": None}


class _AsRole:
    """What get_llm(role) returns in tests: the FakeModel, noting in its `calls`
    which role's model each call was made on and what for, and in its `efforts`
    the reasoning effort the call would have used."""

    def __init__(self, model, role):
        self._model = model
        self._role = role

    def invoke(self, messages):
        system = next((m.content for m in messages if isinstance(m, SystemMessage)), "")
        self._model.calls.append((self._role, system))
        self._model.efforts.append((self._role, llm.reasoning_effort(self._role)))
        return self._model.invoke(messages)

    def with_structured_output(self, schema, include_raw=False):
        self._model.calls.append((self._role, schema.__name__))
        self._model.efforts.append((self._role, llm.reasoning_effort(self._role)))
        return self._model.with_structured_output(schema, include_raw)


@pytest.fixture
def fake_llm(monkeypatch):
    """Make every get_llm(role) call return the FakeModel, whichever role asks."""
    model = FakeModel()
    model.calls = []
    model.efforts = []

    def get_llm(role=llm.SPECIALIST):
        return _AsRole(model, role)

    monkeypatch.setattr("agents.specialist.get_llm", get_llm)
    monkeypatch.setattr("agents.chief_of_staff.get_llm", get_llm)
    return model


@pytest.fixture
def thread():
    """A fresh session config for invoking the checkpointer-backed graph."""
    import uuid

    return {"configurable": {"thread_id": str(uuid.uuid4())}}
