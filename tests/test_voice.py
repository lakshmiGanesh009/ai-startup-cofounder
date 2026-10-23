"""Dictation: the recording written down in English by Whisper (its
translation route), on Azure OpenAI or, standing by, on Groq, through POST
/transcribe, and nothing else of it kept."""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

import llm
import main
import voice

client = TestClient(main.app)
WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 64
TRANSLATIONS = "/openai/deployments/whisper/audio/translations"


@pytest.fixture
def azure(monkeypatch):
    """Azure OpenAI and Groq, answered by a stand-in that keeps each request it
    is sent and answers each route as `answers` says: by its last part
    ("translations"), or on Groq "groq:" and that."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://cofounder.openai.azure.com/")
    monkeypatch.delenv(voice.DEPLOYMENT, raising=False)
    sent: list[httpx.Request] = []
    answers: dict[str, tuple[int, dict]] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        route = request.url.path.rsplit("/", 1)[-1]
        if request.url.host == "api.groq.com":
            route = f"groq:{route}"
        status, body = answers.get(route, (200, {"text": " Launch at $99 a month. "}))
        return httpx.Response(status, json=body)

    def client_():
        return openai.AzureOpenAI(api_key="key", azure_endpoint="https://cofounder.openai.azure.com/",
                                  api_version=voice.API_VERSION, max_retries=0,
                                  http_client=httpx.Client(transport=httpx.MockTransport(handle)))

    def groq_client():
        return openai.OpenAI(api_key="gsk", base_url=llm.GROQ_URL, max_retries=0,
                             http_client=httpx.Client(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr(voice, "_client", client_)
    monkeypatch.setattr(voice, "_groq_client", groq_client)
    return sent, answers


def test_a_recording_is_written_down_in_english_by_whisper(azure):
    sent, _ = azure
    response = client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm;codecs=opus"})

    assert response.status_code == 200 and response.json() == {"text": "Launch at $99 a month."}
    (request,) = sent
    # Whisper's translation route: whatever language was spoken, English comes back.
    assert request.url.path == TRANSLATIONS
    assert request.url.params["api-version"] == "2024-10-21"
    body = request.read()
    assert b'filename="dictation.webm"' in body and b"Content-Type: audio/webm" in body and WEBM in body
    assert b'name="model"\r\n\r\nwhisper' in body
    assert b'name="prompt"\r\n\r\nA founder describing a startup decision' in body


def test_another_deployment_is_used_when_named(azure, monkeypatch):
    sent, _ = azure
    monkeypatch.setenv(voice.DEPLOYMENT, "whisper-eu")
    assert client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/mp4"}).status_code == 200
    assert sent[-1].url.path == "/openai/deployments/whisper-eu/audio/translations"
    assert b'filename="dictation.mp4"' in sent[-1].read()


def test_a_setting_left_empty_is_its_default(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://cofounder.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_TRANSCRIPTION_API_VERSION", "")
    monkeypatch.setenv(voice.DEPLOYMENT, "")
    assert voice._client()._custom_query["api-version"] == "2024-10-21"
    assert voice.deployment() == "whisper"


def test_a_model_that_cannot_translate_writes_it_down_as_spoken(azure, monkeypatch):
    sent, answers = azure
    monkeypatch.setenv(voice.DEPLOYMENT, "gpt-4o-transcribe")
    answers["translations"] = (400, {"error": {"code": "OperationNotSupported", "message":
                                     "The audioTranslation operation does not work with the specified model."}})
    response = client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert response.status_code == 200 and response.json() == {"text": "Launch at $99 a month."}
    assert [request.url.path.rsplit("/", 1)[-1] for request in sent] == ["translations", "transcriptions"]


def test_each_format_a_browser_records_is_named_for_what_it_is(azure):
    sent, _ = azure
    for kind, extension in (("audio/mp4", "mp4"), ("audio/ogg;codecs=opus", "ogg"), ("audio/wav", "wav")):
        assert client.post("/transcribe", content=WEBM, headers={"Content-Type": kind}).status_code == 200
        assert f'filename="dictation.{extension}"'.encode() in sent[-1].read()


def test_what_cannot_be_written_down_says_why(azure, monkeypatch):
    sent, answers = azure
    empty = client.post("/transcribe", content=b"", headers={"Content-Type": "audio/webm"})
    text = client.post("/transcribe", content=b"hello", headers={"Content-Type": "text/plain"})
    assert (empty.status_code, text.status_code) == (422, 415)
    assert "cannot be written down" in text.json()["detail"]
    assert sent == []

    answers["translations"] = (401, {"error": {"code": "401", "message": "Access denied due to invalid subscription key."}})
    failed = client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert failed.status_code == 502
    assert failed.json()["detail"] == ("The speech-to-text call failed: Azure OpenAI answered 401: "
                                       "Access denied due to invalid subscription key.")

    # No Whisper deployment by that name: what to deploy, or where to name another.
    answers["translations"] = (404, {"error": {"code": "DeploymentNotFound", "message": "The API deployment does not exist."}})
    missing = client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert missing.status_code == 502
    assert "no deployment named whisper: deploy Whisper there" in missing.json()["detail"]

    monkeypatch.delenv("AZURE_OPENAI_API_KEY")
    unset = client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert unset.status_code == 503 and unset.json()["detail"].startswith("Dictation needs Azure OpenAI")


def test_groq_writes_down_what_azure_cannot(azure, monkeypatch):
    sent, answers = azure
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    answers["translations"] = (404, {"error": {"code": "DeploymentNotFound", "message": "The API deployment does not exist."}})

    response = client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"})

    assert response.status_code == 200 and response.json() == {"text": "Launch at $99 a month."}
    azure_request, groq_request = sent
    assert azure_request.url.path == TRANSLATIONS
    # Groq's Whisper that translates, on its OpenAI-compatible route.
    assert str(groq_request.url) == "https://api.groq.com/openai/v1/audio/translations"
    assert b'name="model"\r\n\r\nwhisper-large-v3' in groq_request.read()


def test_groq_alone_writes_it_down(azure, monkeypatch):
    sent, _ = azure
    monkeypatch.delenv("AZURE_OPENAI_API_KEY")
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    assert client.get("/health").json()["voice"] == {"dictation": True}
    assert client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"}).status_code == 200
    assert [request.url.host for request in sent] == ["api.groq.com"]


def test_while_groq_stands_in_for_the_team_azure_is_passed_over(azure, monkeypatch):
    sent, _ = azure
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    llm._pass_over_main()
    assert client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"}).status_code == 200
    assert [request.url.host for request in sent] == ["api.groq.com"]


def test_when_neither_can_write_it_down_each_says_why(azure, monkeypatch):
    _, answers = azure
    monkeypatch.setenv("GROQ_API_KEY", "gsk")
    answers["translations"] = (401, {"error": {"code": "401", "message": "Access denied due to invalid subscription key."}})
    answers["groq:translations"] = (429, {"error": {"message": "Rate limit reached for model whisper-large-v3."}})

    failed = client.post("/transcribe", content=WEBM, headers={"Content-Type": "audio/webm"})

    assert failed.status_code == 502
    assert failed.json()["detail"] == (
        "The speech-to-text call failed: Azure OpenAI answered 401: Access denied due to invalid subscription key. "
        "Then Groq answered 429: Rate limit reached for model whisper-large-v3.")


def test_a_recording_may_be_as_large_as_an_upload(azure, monkeypatch):
    monkeypatch.setattr(main.guard, "max_bytes", 100)
    monkeypatch.setattr(main.guard, "upload_bytes", 1_000)
    recorded = client.post("/transcribe", content=b"\x1a" * 800, headers={"Content-Type": "audio/webm"})
    too_large = client.post("/transcribe", content=b"\x1a" * 1_001, headers={"Content-Type": "audio/webm"})
    assert (recorded.status_code, too_large.status_code) == (200, 413)


def test_health_says_whether_dictation_can_run(azure, monkeypatch):
    # Azure OpenAI is enough: the Whisper deployment goes by its default name.
    assert client.get("/health").json()["voice"] == {"dictation": True}
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT")
    assert client.get("/health").json()["voice"] == {"dictation": False}
