"""The founder's dictation, written down in English by Azure OpenAI's Whisper,
for the mic beside the app's input boxes.

Whisper is the speech-to-text model that also translates: spoken in any
language, the words come back in English, the language the team works in
(the audio translation route). It runs as a deployment on the same Azure
OpenAI resource as the team's model, named `whisper` (Azure's default name for
it) unless AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT names another. A deployment of
a model that cannot translate (gpt-4o-transcribe, say) writes the words down as
spoken instead. The recording is sent and forgotten: nothing of it is kept.
"""

import os

from openai import APIConnectionError, APIStatusError, APITimeoutError, AzureOpenAI, BadRequestError

DEPLOYMENT = "AZURE_OPENAI_TRANSCRIPTION_DEPLOYMENT"
DEFAULT_DEPLOYMENT = "whisper"
# The audio routes' API version (GA); AZURE_OPENAI_TRANSCRIPTION_API_VERSION overrides it.
API_VERSION = "2024-10-21"
TIMEOUT = 60
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
    """Azure OpenAI is not set up, so there is nowhere to send a recording."""


class UnsupportedAudio(ValueError):
    """A recording in a format the service does not take."""


def deployment() -> str:
    return os.getenv(DEPLOYMENT) or DEFAULT_DEPLOYMENT


def available() -> bool:
    """Whether dictation can run: the Azure OpenAI key and endpoint the team's model uses."""
    return all(os.getenv(name) for name in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"))


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.getenv("AZURE_OPENAI_TRANSCRIPTION_API_VERSION") or API_VERSION,
        timeout=TIMEOUT,
        max_retries=1,
    )


def why(error: Exception) -> str:
    """A failed call in a sentence: what Azure OpenAI answered, else what went wrong."""
    if isinstance(error, APIStatusError):
        body = error.body if isinstance(error.body, dict) else {}
        # The SDK hands over Azure's {"error": {...}} unwrapped, or not.
        said = body["error"] if isinstance(body.get("error"), dict) else body
        if said.get("code") == "DeploymentNotFound":
            return (f"this Azure OpenAI resource has no deployment named {deployment()}: deploy Whisper there "
                    f"under that name, or name your Whisper deployment in {DEPLOYMENT}.")
        return f"Azure OpenAI answered {error.status_code}" + (f": {said['message']}" if said.get("message") else ".")
    if isinstance(error, APITimeoutError):
        return "Azure OpenAI did not answer in time."
    if isinstance(error, APIConnectionError):
        return "Azure OpenAI could not be reached."
    return str(error)


def _cannot_translate(error: BadRequestError) -> bool:
    """Whether Azure refused because the deployment's model does not translate."""
    body = error.body if isinstance(error.body, dict) else {}
    said = body["error"] if isinstance(body.get("error"), dict) else body
    return said.get("code") == "OperationNotSupported" or "translation" in str(said.get("message", "")).lower()


def transcribe(audio: bytes, content_type: str) -> str:
    """The words spoken in `audio`, a recording of the media type
    `content_type`, in English: translated by Whisper from whatever language
    was spoken, or as spoken by a model that cannot translate."""
    if not available():
        raise VoiceNotConfigured(
            "Dictation needs Azure OpenAI: set AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT, with a Whisper "
            f"deployment named {DEFAULT_DEPLOYMENT} (or the one named in {DEPLOYMENT})."
        )
    kind = content_type.split(";")[0].strip().lower()
    if kind not in AUDIO_TYPES:
        raise UnsupportedAudio(f"A recording in {kind or 'an unnamed format'} cannot be written down; "
                               f"send {', '.join(sorted(set(AUDIO_TYPES.values())))}.")
    client = _client()
    file = (f"dictation.{AUDIO_TYPES[kind]}", audio, kind)
    try:
        result = client.audio.translations.create(model=deployment(), file=file, prompt=PROMPT)
    except BadRequestError as error:
        if not _cannot_translate(error):
            raise
        result = client.audio.transcriptions.create(model=deployment(), file=file, prompt=PROMPT)
    return result.text.strip()
