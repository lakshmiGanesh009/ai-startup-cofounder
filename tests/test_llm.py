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


def built(model):
    """The provider's own model inside the app's wrapper, which counts its calls."""
    return model.model if isinstance(model, llm.Counted) else model


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

    model = built(llm.get_llm())

    assert model is capture_models["azure"]
    assert "openai" not in capture_models
    assert model.kwargs["azure_deployment"] == "gpt-5-mini"


def test_selects_openai_when_only_openai_credentials_set(monkeypatch, capture_models):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("MODEL_NAME", "gpt-4o-mini")

    model = built(llm.get_llm())

    assert model is capture_models["openai"]
    assert "azure" not in capture_models
    assert model.kwargs["model"] == "gpt-4o-mini"


def test_the_chief_of_staff_can_reason_harder_than_the_specialists(monkeypatch, capture_models):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "minimal")
    monkeypatch.setenv("AZURE_OPENAI_CHIEF_REASONING_EFFORT", "high")

    assert built(llm.get_llm(llm.SPECIALIST)).kwargs["reasoning_effort"] == "minimal"
    assert built(llm.get_llm(llm.CHIEF)).kwargs["reasoning_effort"] == "high"


def test_the_chief_of_staff_uses_the_general_effort_when_its_own_is_unset(
    monkeypatch, capture_models
):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "low")

    assert built(llm.get_llm(llm.CHIEF)).kwargs["reasoning_effort"] == "low"


def test_the_model_is_built_once_and_reused(monkeypatch, capture_models):
    # One model means one HTTP connection pool for every call of a run.
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    assert built(llm.get_llm()) is built(llm.get_llm())


def test_error_when_no_provider_configured(capture_models):
    with pytest.raises(RuntimeError) as exc:
        built(llm.get_llm())

    message = str(exc.value)
    assert "AZURE_OPENAI_API_KEY" in message
    assert "OPENAI_API_KEY" in message


def test_error_names_missing_azure_variable(monkeypatch, capture_models):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    # endpoint and deployment name left unset

    with pytest.raises(RuntimeError) as exc:
        built(llm.get_llm())

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
        assert built(llm.get_llm(llm.SPECIALIST)).kwargs["reasoning_effort"] == "low"
        assert built(llm.get_llm(llm.CHIEF)).kwargs["reasoning_effort"] == "medium"
    assert built(llm.get_llm(llm.SPECIALIST)).kwargs["reasoning_effort"] == "minimal"


def test_calls_at_high_effort_get_the_longer_timeout(monkeypatch, capture_models):
    _azure(monkeypatch)

    with llm.reasoning(chief="high"):
        chief = built(llm.get_llm(llm.CHIEF))
    specialist = built(llm.get_llm(llm.SPECIALIST))

    assert chief.kwargs["timeout"] == llm.LLM_TIMEOUT_HIGH
    assert specialist.kwargs["timeout"] == llm.LLM_TIMEOUT
    assert "reasoning_effort" not in specialist.kwargs


def test_openai_takes_no_reasoning_effort(monkeypatch, capture_models):
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "medium")

    with llm.reasoning(specialist="high", chief="high"):
        model = built(llm.get_llm(llm.CHIEF))

    assert "reasoning_effort" not in model.kwargs
    assert model is built(llm.get_llm(llm.SPECIALIST))


def test_error_names_the_missing_openai_key(capture_models):
    with pytest.raises(llm.LLMNotConfigured, match="OPENAI_API_KEY"):
        llm._openai_llm()


def test_the_monitor_counts_the_providers_model_calls_and_why_one_failed():
    import httpx
    import openai
    from langchain_core.messages import AIMessage

    from monitor import monitor

    class Replying:
        def __init__(self, reply=None, error=None):
            self.reply, self.error = reply, error

        def invoke(self, input, config=None):
            if self.error:
                raise self.error
            return self.reply

        def with_structured_output(self, schema, **kwargs):
            return Replying({"raw": self.reply, "parsed": None, "parsing_error": None}, self.error)

    replied = AIMessage("ok", usage_metadata={"input_tokens": 900, "output_tokens": 100, "total_tokens": 1_000})
    llm.Counted(Replying(replied), "azure").invoke("hello")
    llm.Counted(Replying(replied), "azure").with_structured_output(dict, include_raw=True).invoke("again")
    refused = openai.AuthenticationError(
        "Error code: 401", response=httpx.Response(401, request=httpx.Request("POST", "https://azure.example")),
        body={"code": "401", "message": "Access denied due to invalid subscription key."})
    with pytest.raises(openai.AuthenticationError):
        llm.Counted(Replying(error=refused), "azure").invoke("hello")

    (azure,) = monitor.usage()
    model = azure.services[0]
    assert (azure.provider, model.service, model.calls, model.failed) == ("azure", "model", 3, 1)
    assert (model.tokens_in, model.tokens_out) == (1_800, 200)
    assert model.last_failure == "401: Access denied due to invalid subscription key."
