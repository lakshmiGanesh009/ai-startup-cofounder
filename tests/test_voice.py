"""Dictation: the recording written down in English by Azure OpenAI's Whisper
(its translation route), through POST /transcribe, and nothing else of it kept."""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

import main
import voice

client = TestClient(main.app)
WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 64
TRANSLATIONS = "/openai/deployments/whisper/audio/translations"


@pytest.fixture
def azure(monkeypatch):
    """Azure OpenAI, answered by a stand-in that keeps each request it is sent
    and answers each route as `answers` says."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://cofounder.openai.azure.com/")
    monkeypatch.delenv(voice.DEPLOYMENT, raising=False)
    sent: list[httpx.Request] = []
    answers: dict[str, tuple[int, dict]] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        status, body = answers.get(request.url.path.rsplit("/", 1)[-1], (200, {"text": " Launch at $99 a month. "}))
        return httpx.Response(status, json=body)

    def client_():
        return openai.AzureOpenAI(api_key="key", azure_endpoint="https://cofounder.openai.azure.com/",
                                  api_version=voice.API_VERSION, max_retries=0,
                                  http_client=httpx.Client(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr(voice, "_client", client_)
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
    # The Monitor counts the call, and why it failed.
    from monitor import monitor

    (azure,) = monitor.usage()
    speech = azure.services[0]
    assert (speech.service, speech.calls, speech.failed) == ("speech", 1, 1)
    assert speech.last_failure == "401: Access denied due to invalid subscription key."
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
