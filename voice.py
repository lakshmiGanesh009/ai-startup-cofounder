"""The founder's dictation, written down in English by Whisper, on Azure
OpenAI or, standing by, on Groq, for the mic beside the app's input boxes.

Whisper is the speech-to-text model that also translates: spoken in any
language, the words come back in English, the language the team works in
(the audio translation route). It runs as a deployment on the same Azure
OpenAI resource as the team's model, named `whisper` (Azure's default name for
it) unless AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT names another. A deployment of
a model that cannot translate (gpt-4o-transcribe, say) writes the words down as
spoken instead.

With GROQ_API_KEY set, Groq's whisper-large-v3 (GROQ_WHISPER_MODEL), which
translates too, writes down what Azure cannot (unreachable, the key refused, no
Whisper deployment, rate-limited, failing), or all of it without Azure, or
while the team's calls go to Groq because Azure failed lately (llm.py). The
recording is sent and forgotten: nothing of it is kept.
"""

import logging
import os

import openai
from openai import APIConnectionError, APIStatusError, APITimeoutError, AzureOpenAI, BadRequestError

import llm

log = logging.getLogger(__name__)

DEPLOYMENT = "AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT"
DEFAULT_DEPLOYMENT = "whisper"
# The audio routes' API version (GA); AZURE_OPENAI_TRANSCRIPTION_API_VERSION overrides it.
API_VERSION = "2024-10-21"
TIMEOUT = 60
# The Whisper of Groq's that translates (its turbo does not).
GROQ_WHISPER = "whisper-large-v3"
# Words the founder is likely to say, so Whisper spells them as the team does (it reads an English prompt).
PROMPT = "A founder describing a startup decision: pricing, budget, customers, pilots, CAC, NPV, IRR, churn, MRR."
# The recordings a browser makes (MediaRecorder: WebM or Ogg with Opus, MP4 on
# Safari) and the files the service takes, by media type, with the extension
# it reads the format from.
AUDIO_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
}


class VoiceNotConfigured(RuntimeError):
    """Neither Azure OpenAI nor Groq is set up, so there is nowhere to send a recording."""


class VoiceFailed(RuntimeError):
    """No provider could write the recording down; says what each answered."""


class UnsupportedAudio(ValueError):
    """A recording in a format the service does not take."""


def deployment() -> str:
    return os.getenv(DEPLOYMENT) or DEFAULT_DEPLOYMENT


def _on_azure() -> bool:
    return all(os.getenv(name) for name in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"))


def available() -> bool:
    """Whether dictation can run: Azure OpenAI's key and endpoint, or Groq's key."""
    return _on_azure() or bool(os.getenv("GROQ_API_KEY"))


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.getenv("AZURE_OPENAI_TRANSCRIPTION_API_VERSION") or API_VERSION,
        timeout=TIMEOUT,
        max_retries=1,
    )


def _groq_client() -> openai.OpenAI:
    return openai.OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url=llm.GROQ_URL, timeout=TIMEOUT, max_retries=1)


def why(error: Exception, provider: str = "azure") -> str:
    """A failed call in a sentence: what `provider` answered, else what went wrong."""
    name = llm.NAMES[provider]
    if isinstance(error, APIStatusError):
        body = error.body if isinstance(error.body, dict) else {}
        # The SDK hands over the {"error": {...}} unwrapped, or not.
        said = body["error"] if isinstance(body.get("error"), dict) else body
        if said.get("code") == "DeploymentNotFound":
            return (f"this Azure OpenAI resource has no deployment named {deployment()}: deploy Whisper there "
                    f"under that name, or name your Whisper deployment in {DEPLOYMENT}.")
        return f"{name} answered {error.status_code}" + (f": {said['message']}" if said.get("message") else ".")
    if isinstance(error, APITimeoutError):
        return f"{name} did not answer in time."
    if isinstance(error, APIConnectionError):
        return f"{name} could not be reached."
    return str(error)


def _cannot_translate(error: BadRequestError) -> bool:
    """Whether Azure refused because the deployment's model does not translate."""
    body = error.body if isinstance(error.body, dict) else {}
    said = body["error"] if isinstance(body.get("error"), dict) else body
    return said.get("code") == "OperationNotSupported" or "translation" in str(said.get("message", "")).lower()


def _on_azure_whisper(file) -> str:
    client = _client()
    try:
        result = client.audio.translations.create(model=deployment(), file=file, prompt=PROMPT)
    except BadRequestError as error:
        if not _cannot_translate(error):
            raise
        result = client.audio.transcriptions.create(model=deployment(), file=file, prompt=PROMPT)
    return result.text


def _on_groq_whisper(file) -> str:
    model = os.getenv("GROQ_WHISPER_MODEL") or GROQ_WHISPER
    return _groq_client().audio.translations.create(model=model, file=file, prompt=PROMPT).text


def transcribe(audio: bytes, content_type: str) -> str:
    """The words spoken in `audio`, a recording of the media type
    `content_type`, in English: translated by Whisper from whatever language
    was spoken, or as spoken by a model that cannot translate. Azure first,
    unless it failed the team lately; Groq when Azure cannot."""
    if not available():
        raise VoiceNotConfigured(
            "Dictation needs Azure OpenAI (AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT, with a Whisper "
            f"deployment named {DEFAULT_DEPLOYMENT}, or the one named in {DEPLOYMENT}) or Groq (GROQ_API_KEY)."
        )
    kind = content_type.split(";")[0].strip().lower()
    if kind not in AUDIO_TYPES:
        raise UnsupportedAudio(f"A recording in {kind or 'an unnamed format'} cannot be written down; "
                               f"send {', '.join(sorted(set(AUDIO_TYPES.values())))}.")
    file = (f"dictation.{AUDIO_TYPES[kind]}", audio, kind)
    providers = [("azure", _on_azure_whisper)] if _on_azure() and not llm.standing_in() else []
    if os.getenv("GROQ_API_KEY"):
        providers.append(("groq", _on_groq_whisper))
    answered: list[str] = []
    for index, (provider, write) in enumerate(providers):
        try:
            return write(file).strip()
        except openai.OpenAIError as error:
            answered.append(why(error, provider))
            if index == len(providers) - 1 or not isinstance(error, llm.UNAVAILABLE):
                break
            log.warning("Dictation: %s Groq, the backup, writes it down.", answered[-1])
    raise VoiceFailed(" Then ".join(answered))
