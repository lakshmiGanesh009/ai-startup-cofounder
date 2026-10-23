"""Tests for provider selection in llm.get_llm().

No real model is created: each provider class is replaced with a stub that
records the arguments it was built with.
"""

import pytest

import llm


class StubModel:
    """Stands in for a chat model, capturing its constructor arguments."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def capture_models(monkeypatch):
    """Replace both provider classes with StubModel and record which was used."""
    built = {}

    def make(provider):
        def factory(**kwargs):
            model = StubModel(**kwargs)
            built[provider] = model
            return model

        return factory

    monkeypatch.setattr("langchain_openai.AzureChatOpenAI", make("azure"), raising=False)
    monkeypatch.setattr("langchain_openai.ChatOpenAI", make("openai"), raising=False)
    return built


def test_selects_azure_when_azure_credentials_set(monkeypatch, capture_models):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")

    model = llm.get_llm()

    assert model is capture_models["azure"]
    assert "openai" not in capture_models
    assert model.kwargs["azure_deployment"] == "gpt-5-mini"


def test_selects_openai_when_only_openai_credentials_set(monkeypatch, capture_models):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("MODEL_NAME", "gpt-4o-mini")

    model = llm.get_llm()

    assert model is capture_models["openai"]
    assert "azure" not in capture_models
    assert model.kwargs["model"] == "gpt-4o-mini"


def test_the_chief_of_staff_can_reason_harder_than_the_specialists(monkeypatch, capture_models):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "minimal")
    monkeypatch.setenv("AZURE_OPENAI_CHIEF_REASONING_EFFORT", "high")

    assert llm.get_llm(llm.SPECIALIST).kwargs["reasoning_effort"] == "minimal"
    assert llm.get_llm(llm.CHIEF).kwargs["reasoning_effort"] == "high"


def test_the_chief_of_staff_uses_the_general_effort_when_its_own_is_unset(
    monkeypatch, capture_models
):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "low")

    assert llm.get_llm(llm.CHIEF).kwargs["reasoning_effort"] == "low"


def test_the_model_is_built_once_and_reused(monkeypatch, capture_models):
    # One model means one HTTP connection pool for every call of a run.
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    assert llm.get_llm() is llm.get_llm()


def test_error_when_no_provider_configured(capture_models):
    with pytest.raises(RuntimeError) as exc:
        llm.get_llm()

    message = str(exc.value)
    assert "AZURE_OPENAI_API_KEY" in message
    assert "OPENAI_API_KEY" in message


def test_error_names_missing_azure_variable(monkeypatch, capture_models):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    # endpoint and deployment name left unset

    with pytest.raises(RuntimeError) as exc:
        llm.get_llm()

    message = str(exc.value)
    assert "AZURE_OPENAI_ENDPOINT" in message
    assert "AZURE_OPENAI_DEPLOYMENT_NAME" in message


def _azure(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")


def test_a_request_can_choose_each_roles_effort(monkeypatch, capture_models):
    _azure(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "minimal")
    monkeypatch.setenv("AZURE_OPENAI_CHIEF_REASONING_EFFORT", "medium")

    with llm.reasoning(specialist="low", chief=None):
        # A role left out keeps the configured effort.
        assert llm.get_llm(llm.SPECIALIST).kwargs["reasoning_effort"] == "low"
        assert llm.get_llm(llm.CHIEF).kwargs["reasoning_effort"] == "medium"
    assert llm.get_llm(llm.SPECIALIST).kwargs["reasoning_effort"] == "minimal"


def test_calls_at_high_effort_get_the_longer_timeout(monkeypatch, capture_models):
    _azure(monkeypatch)

    with llm.reasoning(chief="high"):
        chief = llm.get_llm(llm.CHIEF)
    specialist = llm.get_llm(llm.SPECIALIST)

    assert chief.kwargs["timeout"] == llm.LLM_TIMEOUT_HIGH
    assert specialist.kwargs["timeout"] == llm.LLM_TIMEOUT
    assert "reasoning_effort" not in specialist.kwargs


def test_openai_takes_no_reasoning_effort(monkeypatch, capture_models):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "medium")

    with llm.reasoning(specialist="high", chief="high"):
        model = llm.get_llm(llm.CHIEF)

    assert "reasoning_effort" not in model.kwargs
    assert model is llm.get_llm(llm.SPECIALIST)


def test_error_names_the_missing_openai_key(capture_models):
    with pytest.raises(llm.LLMNotConfigured, match="OPENAI_API_KEY"):
        llm._openai_llm()


# ---- Groq, standing by ----

import json  # noqa: E402
import time  # noqa: E402

import httpx  # noqa: E402
import openai  # noqa: E402
from pydantic import BaseModel  # noqa: E402


def _azure(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")


def _status(kind, status, message):
    request = httpx.Request("POST", "https://example.openai.azure.com/openai/deployments/gpt-5-mini/chat/completions")
    return kind(message, response=httpx.Response(status, request=request), body={"code": str(status), "message": message})


class Answering:
    """A model stand-in that answers, or raises `error`, and counts its calls."""

    def __init__(self, answer="answered", error=None):
        self.answer, self.error, self.calls, self.structured = answer, error, 0, []

    def invoke(self, input, config=None, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer

    def with_structured_output(self, schema, **kwargs):
        self.structured.append(kwargs)
        return self


def test_groq_alone_is_the_main_provider_and_reasons_at_its_own_efforts(monkeypatch, capture_models):
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "minimal")

    model = llm.get_llm()

    assert isinstance(model, llm.Paced) and model.model is capture_models["openai"]
    assert model.model.kwargs["base_url"] == "https://api.groq.com/openai/v1"
    assert (model.model.kwargs["model"], model.model.kwargs["api_key"]) == ("openai/gpt-oss-120b", "gsk")
    # gpt-oss reasons at low, medium or high: the app's "minimal" is its low.
    assert model.model.kwargs["reasoning_effort"] == "low"
    # A rate limit is waited out, many times over.
    assert model.model.kwargs["max_retries"] == 8
    assert (llm.main_provider(), llm.backup_provider(), llm.standing_in()) == ("groq", None, False)


def test_beside_azure_groq_stands_by(monkeypatch, capture_models):
    _azure(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "medium")

    model = llm.get_llm()

    assert isinstance(model, llm.WithBackup)
    assert model.main is capture_models["azure"] and model.main.kwargs["reasoning_effort"] == "medium"
    assert model.backup.model.kwargs["model"] == "llama-3.3-70b-versatile"
    assert "reasoning_effort" not in model.backup.model.kwargs  # a model that does not reason
    assert (llm.main_provider(), llm.backup_provider()) == ("azure", "groq")


def test_an_azure_half_set_up_leaves_the_calls_to_groq(monkeypatch, capture_models):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")  # no endpoint, no deployment
    monkeypatch.setenv("GROQ_API_KEY", "gsk")

    model = llm.get_llm()

    assert model.model is capture_models["openai"] and model.model.kwargs["base_url"] == llm.GROQ_URL


def test_a_call_azure_cannot_serve_goes_to_groq_and_so_do_the_next_for_a_while(monkeypatch):
    _azure(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    now = [1000.0]
    monkeypatch.setattr(llm.time, "monotonic", lambda: now[0])
    main = Answering(error=_status(openai.AuthenticationError, 401, "Access denied due to invalid subscription key."))
    backup = Answering("from groq")
    model = llm.WithBackup(main, backup)

    assert model.invoke("hello") == "from groq"
    assert llm.standing_in()
    # While it stands in, the main provider is not tried.
    assert model.invoke("again") == "from groq" and (main.calls, backup.calls) == (1, 2)
    # After the cool-down it is tried first again.
    now[0] += llm.BACKUP_COOLDOWN + 1
    assert not llm.standing_in()
    main.error = None
    assert model.invoke("later") == "answered" and main.calls == 2


@pytest.mark.parametrize("error", [
    openai.APIConnectionError(request=httpx.Request("POST", "https://example.openai.azure.com/")),
    _status(openai.NotFoundError, 404, "The API deployment for this resource does not exist."),
    _status(openai.RateLimitError, 429, "Rate limit reached."),
    _status(openai.InternalServerError, 503, "The service is unavailable."),
])
def test_each_kind_of_outage_goes_to_groq(monkeypatch, error):
    _azure(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    assert llm.WithBackup(Answering(error=error), Answering("from groq")).invoke("hello") == "from groq"


def test_what_azure_refuses_as_such_is_not_sent_to_groq(monkeypatch):
    _azure(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    refused = _status(openai.BadRequestError, 400, "The response was filtered due to the prompt triggering the content filter.")
    backup = Answering("from groq")

    with pytest.raises(openai.BadRequestError):
        llm.WithBackup(Answering(error=refused), backup).invoke("hello")
    assert backup.calls == 0 and not llm.standing_in()


def test_groqs_calls_take_turns(monkeypatch):
    import threading

    monkeypatch.setenv("GROQ_MAX_CONCURRENT", "1")
    at_once = [0, 0]  # now, most

    class Slow:
        def invoke(self, input, config=None):
            at_once[0] += 1
            at_once[1] = max(at_once[1], at_once[0])
            time.sleep(0.05)
            at_once[0] -= 1
            return input

    paced = llm.Paced(Slow())
    threads = [threading.Thread(target=paced.invoke, args=(f"call {n}",)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert at_once[1] == 1


def test_a_prompt_too_large_for_groq_loses_the_middle_of_its_longest_message():
    from langchain_core.messages import HumanMessage, SystemMessage

    system = SystemMessage("Write the financial plan, as the schema asks.")
    report = " ".join(f"word{n}" for n in range(6_000))
    shortened = llm.fit([system, HumanMessage(f"BEGIN {report} END")], 2_000)

    assert shortened[0] is system  # the instructions stay whole
    text = shortened[1].content
    assert text.startswith("BEGIN word0") and text.endswith("word5999 END") and llm.SHORTENED in text
    assert 1_700 <= llm.tokens(system.content) + llm.tokens(text) <= 2_000
    # What fits is left as it is, a plain prompt too.
    assert llm.fit("Reply in a word.", 2_000) == "Reply in a word."
    assert llm.SHORTENED in llm.fit(report, 500) and llm.tokens(llm.fit(report, 500)) <= 500


def test_groqs_calls_wait_for_room_in_its_minute(monkeypatch):
    now = [0.0]
    slept = []
    monkeypatch.setattr(llm.time, "monotonic", lambda: now[0])

    def sleep(seconds):
        slept.append(round(seconds, 2))
        now[0] += seconds

    monkeypatch.setattr(llm.time, "sleep", sleep)
    monkeypatch.setenv("GROQ_TOKENS_PER_MINUTE", "8000")

    class Answering:
        def invoke(self, input, config=None):
            from langchain_core.messages import AIMessage

            return AIMessage("ok", usage_metadata={"input_tokens": 5_800, "output_tokens": 2_000, "total_tokens": 7_800})

    paced = llm.Paced(Answering())
    paced.invoke("first")  # 7,800 of the minute's 8,000 spent
    assert slept == []
    now[0] = 20.0
    paced.invoke("second")  # does not fit until the first leaves the minute
    assert slept == [40.25] and now[0] == 60.25


def test_a_structured_reply_from_groq_comes_through_a_json_schema():
    main, backup = Answering(), Answering()
    llm.WithBackup(main, backup).with_structured_output(dict, include_raw=True)
    assert main.structured == [{"include_raw": True}]
    assert backup.structured == [{"include_raw": True, "method": "json_schema"}]


class Verdict(BaseModel):
    verdict: str
    reason: str


def test_a_reply_groq_refused_as_not_fitting_the_schema_is_asked_for_again(monkeypatch):
    from agents.chief_of_staff import structured_invoke

    class Tracker:
        def __init__(self):
            self.records = []

        def record(self, raw):
            self.records.append(raw)

    refused = _status(openai.BadRequestError, 400, "Tool choice is required, but model did not call a tool")
    refused.code = "tool_use_failed"
    replies = [refused, {"raw": "raw", "parsed": Verdict(verdict="Go", reason="Pilots pay."), "parsing_error": None}]

    class Model:
        def with_structured_output(self, schema, **kwargs):
            return self

        def invoke(self, messages):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

    monkeypatch.setattr("agents.chief_of_staff.get_llm", lambda role: Model())
    tracker = Tracker()
    assert structured_invoke(Verdict, ["Should we launch?"], tracker) == Verdict(verdict="Go", reason="Pilots pay.")
    assert tracker.records == [None, "raw"]

    # A 400 of another kind (the content filter's) is not asked for again.
    filtered = _status(openai.BadRequestError, 400, "The response was filtered.")
    filtered.code = "content_filter"
    replies[:] = [filtered]
    with pytest.raises(openai.BadRequestError):
        structured_invoke(Verdict, ["Should we launch?"], Tracker())


def test_through_the_real_clients_a_refused_azure_hands_a_structured_call_to_groq(monkeypatch):
    from langchain_openai import AzureChatOpenAI, ChatOpenAI

    _azure(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    sent: list[dict] = []

    def azure(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "401", "message": "Access denied due to invalid subscription key."}})

    def groq(request: httpx.Request) -> httpx.Response:
        sent.append({"url": str(request.url), "body": json.loads(request.content)})
        return httpx.Response(200, json={
            "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": "openai/gpt-oss-120b",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"verdict": "Go", "reason": "Pilots pay."})}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        })

    main = AzureChatOpenAI(api_key="key", azure_endpoint="https://example.openai.azure.com/", azure_deployment="gpt-5-mini",
                           api_version="2025-04-01-preview", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(azure)))
    backup = ChatOpenAI(api_key="gsk", base_url=llm.GROQ_URL, model="openai/gpt-oss-120b", reasoning_effort="low",
                        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(groq)))

    reply = llm.WithBackup(main, backup).with_structured_output(Verdict, include_raw=True).invoke("Should we launch?")

    assert reply["parsed"] == Verdict(verdict="Go", reason="Pilots pay.")
    (request,) = sent
    assert request["url"] == "https://api.groq.com/openai/v1/chat/completions"
    body = request["body"]
    assert body["model"] == "openai/gpt-oss-120b" and body["reasoning_effort"] == "low"
    assert body["response_format"]["type"] == "json_schema" and body["response_format"]["json_schema"]["name"] == "Verdict"
    assert "tools" not in body
    assert llm.standing_in()


def test_health_says_which_provider_answers_and_which_stands_by(monkeypatch):
    from fastapi.testclient import TestClient

    import main

    client = TestClient(main.app)
    _azure(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    assert client.get("/health").json()["llm"] == {"main": "azure", "backup": "groq", "standing_in": False}
    llm._pass_over_main()
    assert client.get("/health").json()["llm"]["standing_in"] is True
