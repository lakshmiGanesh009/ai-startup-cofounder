"""Shared test fixtures.

`strip_credentials` runs for every test so no test can reach a real model.
`fake_llm` replaces the chat model with one that echoes the prompt back, so
graph and API tests are deterministic and need no credentials.
"""

# ruff: noqa: E402
# (the environment is set before the app's modules are imported)

import os

# Whatever .env says (config.py reads it on import, so this comes first), the
# tests keep sessions and reports in memory (test_persistence.py uses
# TEST_DATABASE_URL), need no API key, and meet no rate limit; test_security.py
# sets those on the API's guard itself.
os.environ["DATABASE_URL"] = ""
os.environ["API_KEY"] = ""
os.environ["REQUESTS_PER_MINUTE"] = "1000000"
os.environ["RUNS_PER_HOUR"] = "1000000"

import time

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, SystemMessage

import llm
from agents.proposal_writer import SCHEMAS as PROPOSAL_SCHEMAS
from agents.proposal_writer import Rewritten
from brief import BriefReview, Question, SearchPlan
from deep_research import Competitor, Competitors
from library import Answer
from state import (
    DelegationPlan,
    Finding,
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
    "TAVILY_API_KEY",
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
    tests never hit a real LLM or a real web search."""
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

    Preparing a brief, the searches come from `search_plan` and the Chief of
    Staff's reading from `brief_review` (by default two cited facts and one
    question); `brief_prompts` keeps what each call was given. For deep
    research, the Chief of Staff names the `competitors` (by default one).
    A question about documents is answered with `answer`, and its prompt kept
    in `answer_prompts`.

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
        # A passage or field rewritten on request: the text it comes back as, and the prompts.
        self.rewrite = "A sharper passage."
        self.rewrite_prompts: list[str] = []
        self.fail_parts: set[str] = set()
        self.search_plan = SearchPlan(queries=["clinic scheduling software market size", "clinic scheduling software prices"])
        self.brief_review = BriefReview(
            findings=[
                Finding(point="About 147,000 office-based primary care physicians practised in 2019.", sources=[2]),
                Finding(point="Scheduling tools cost $20-$300 per provider a month in 2025.", sources=[1, 2]),
            ],
            questions=[Question(question="What budget do you have to first launch?",
                                why="It decides whether a paid pilot is affordable.",
                                suggestions=["Under $15k", "$15k-$50k", "Over $50k"])],
        )
        self.brief_prompts: list[tuple[str, str]] = []
        self.competitors = Competitors(companies=[Competitor(name="Klara", what="patient messaging for clinics")])
        self.answer = Answer(answer="Churn is 4% a month [D1 · page 2].", cited=["[D1 · page 2]"])
        self.answer_prompts: list[str] = []

    def _plan_for(self, prompt: str) -> DelegationPlan:
        return self.plan

    def _search_plan_for(self, prompt: str) -> SearchPlan:
        self.brief_prompts.append(("search", prompt))
        return self.search_plan

    def _brief_review_for(self, prompt: str) -> BriefReview:
        self.brief_prompts.append(("review", prompt))
        return self.brief_review

    def _competitors_for(self, prompt: str) -> Competitors:
        self.brief_prompts.append(("competitors", prompt))
        return self.competitors

    def _answer_for(self, prompt: str) -> Answer:
        self.answer_prompts.append(prompt)
        return self.answer

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

    def _rewritten_for(self, prompt: str) -> Rewritten:
        self.rewrite_prompts.append(prompt)
        return Rewritten(text=self.rewrite)

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
            SearchPlan: self._search_plan_for,
            BriefReview: self._brief_review_for,
            Competitors: self._competitors_for,
            Rewritten: self._rewritten_for,
            Answer: self._answer_for,
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


@pytest.fixture(autouse=True)
def fresh_monitor():
    """Each test starts with an empty monitor."""
    from monitor import monitor

    monitor.reset()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Neither Tavily nor Azure OpenAI's web search is called for real: a test
    that searches or researches answers through search._transport or
    azure_web._client, or replaces the calls."""
    import azure_web
    import search

    def refuse(request):
        raise AssertionError(f"A test tried to reach {request.url}")

    class Refusing:
        class responses:
            @staticmethod
            def create(**kwargs):
                raise AssertionError("A test tried to reach Azure OpenAI's web search")

    monkeypatch.setattr(search, "_transport", httpx.MockTransport(refuse))
    monkeypatch.setattr(search, "POLL_SECONDS", 0)
    monkeypatch.setattr(azure_web, "_client", Refusing)


@pytest.fixture
def thread():
    """A fresh session config for invoking the checkpointer-backed graph."""
    import uuid

    return {"configurable": {"thread_id": str(uuid.uuid4())}}
