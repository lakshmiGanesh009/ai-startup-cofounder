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
