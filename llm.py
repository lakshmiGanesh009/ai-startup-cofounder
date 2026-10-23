"""Chat model client shared by every agent.

The provider is chosen by which credentials are set in the environment:
Azure OpenAI if the Azure variables are present, otherwise OpenAI, otherwise
Groq. The model is created on first use, so the app and the tests start
without credentials.

Groq stands by as a backup when GROQ_API_KEY is set beside another provider:
through its OpenAI-compatible API, its openai/gpt-oss-120b by default
(GROQ_MODEL), it answers any call the main provider cannot serve (unreachable
or too slow, the key refused, no such deployment, rate-limited, or failing on
its side), and the calls after it for BACKUP_COOLDOWN, so a run does not wait
on a provider that is down call after call. A request the main provider
refuses as such (a 400: its content filter, a malformed request) stays refused.
Groq is a free provider with small limits (8K tokens a minute and 200K a day
for gpt-oss-120b), so its calls are slowed down to stay within them, and the
main provider's are left as they are: Groq's calls take turns
(GROQ_MAX_CONCURRENT, one by default); each waits until the tokens Groq's
calls used in the last minute leave room for it (GROQ_TOKENS_PER_MINUTE); a
prompt larger than one call may be (GROQ_PROMPT_TOKENS) is shortened in the
middle of its longest message, as Groq refuses one larger than its minute
outright; and a rate limit that still comes is waited out as long as Groq
says, up to GROQ_MAX_RETRIES times.

Each call asks for the model of a role. On Azure each role has a reasoning
effort: the Chief of Staff's (AZURE_OPENAI_CHIEF_REASONING_EFFORT) can be higher
than the specialists' (AZURE_OPENAI_REASONING_EFFORT), because its calls are the
team's decisions while the specialists' are most of the volume. A request can
set its own efforts with `reasoning(...)`, which is how the UI's sliders work.
"""

import logging
import os
import re
import threading
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from typing import Literal, get_args

import openai

from config import LLM_MAX_RETRIES, LLM_TIMEOUT, LLM_TIMEOUT_HIGH


class LLMNotConfigured(RuntimeError):
    """No LLM provider is configured, or its settings are incomplete."""


class LLMReplyError(Exception):
    """The model replied, but not in a form the workflow can use."""


# What an LLM call raises when it still fails after the client's own retries.
LLM_ERRORS = (openai.OpenAIError, LLMReplyError)

log = logging.getLogger(__name__)

# The backup: Groq, through its OpenAI-compatible API.
GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"
# How long the main provider is passed over after it could not serve a call, in seconds.
BACKUP_COOLDOWN = 300
# Groq's calls at once, and its retries of a rate limit, each waiting as long as Groq's retry-after says.
GROQ_MAX_CONCURRENT = 1
GROQ_MAX_RETRIES = 8
# The tokens Groq's calls may use a minute (its free tier's limit for gpt-oss-120b),
# and the most one call's prompt may be, leaving room in the minute for its reply.
GROQ_TOKENS_PER_MINUTE = 8_000
GROQ_PROMPT_TOKENS = 6_000
# What Groq counts beyond a prompt's own tokens, measured: 4,479 counted as 4,854.
_ALLOWANCE = 400
SHORTENED = "\n\n[… shortened here: Groq, the free backup, takes only so much at once …]\n\n"
NAMES = {"azure": "Azure OpenAI", "openai": "OpenAI", "groq": "Groq"}
# Groq's refusals of what its own model generated, when it did not fit the
# schema asked for: a reply that cannot be used, to ask for again like one that
# does not parse (structured_invoke), not a fault of the provider.
UNUSABLE_REPLY = frozenset({"json_validate_failed", "tool_use_failed"})
# A provider that cannot serve a call at all, which a backup can: unreachable or
# too slow, the key refused, no such deployment, rate-limited, failing on its side.
UNAVAILABLE = (
    openai.APIConnectionError,
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.NotFoundError,
    openai.RateLimitError,
    openai.InternalServerError,
)


def failure(error: Exception) -> str:
    """What to tell the founder when a model call failed. Azure's own content
    filter refuses a prompt it reads as harmful or as a jailbreak: that is
    text for the founder to change, not a fault to retry."""
    if isinstance(error, openai.BadRequestError) and error.code == "content_filter":
        body = error.body if isinstance(error.body, dict) else {}
        results = (body.get("innererror") or {}).get("content_filter_result") or {}
        flagged = [
            name.replace("_", " ") for name, result in results.items()
            if isinstance(result, dict) and (result.get("filtered") or result.get("detected"))
        ]
        why = f" ({', '.join(flagged)})" if flagged else ""
        return (f"Azure OpenAI's content filter refused the request{why}: it read part of it as harmful or as "
                "an attempt to manipulate the model. Take that part out of the brief and try again.")
    return f"The LLM call failed: {error}"

# The roles a model is asked for: the specialists, including their critiques of
# each other, and the Chief of Staff (planning, review, resolve and synthesis).
SPECIALIST = "specialist"
CHIEF = "chief"

# The efforts a request may choose, least to most. The deployment also accepts
# "xhigh", but then does no reasoning at all, so "high" is the real maximum.
Effort = Literal["minimal", "low", "medium", "high"]
EFFORTS: tuple[str, ...] = get_args(Effort)

# The efforts the current request chose, by role. A context variable, so each
# request has its own and the worker threads it starts see them too.
_chosen: ContextVar[dict[str, str] | None] = ContextVar("reasoning", default=None)


def too_large(error: Exception) -> str | None:
    """Why a call can never fit the provider's plan, when that is why it
    failed: a request larger than the tokens a minute it allows (Groq answers
    413; its free tier allows 8K for gpt-oss-120b). Waiting does not help."""
    if not (isinstance(error, openai.APIStatusError) and error.status_code == 413):
        return None
    on_groq = error.request is not None and error.request.url.host == "api.groq.com"
    plan = "Groq's plan" if on_groq else "The provider's plan"
    sizes = re.search(r"Limit (\d+), Requested (\d+)", str(error))
    needs = (f" allows {int(sizes[1]):,} tokens a minute, and this call needs {int(sizes[2]):,}" if sizes
             else " does not allow a request this large")
    return f"{plan}{needs}: " + ("Groq's Dev tier, or the main provider working again, can make it." if on_groq
                                  else "a larger plan can make it.")


def _missing(names):
    """Return the names from `names` that are unset or empty in the environment."""
    return [name for name in names if not os.getenv(name)]


def default_effort(role: str) -> str | None:
    """The configured effort: the Chief of Staff's own if set, else the general one."""
    if role == CHIEF and os.getenv("AZURE_OPENAI_CHIEF_REASONING_EFFORT"):
        return os.getenv("AZURE_OPENAI_CHIEF_REASONING_EFFORT")
    return os.getenv("AZURE_OPENAI_REASONING_EFFORT") or None


def reasoning_effort(role: str) -> str | None:
    """The effort `role`'s calls use now: the request's choice, else the default."""
    return (_chosen.get() or {}).get(role) or default_effort(role)


def takes_reasoning_effort() -> bool:
    """Whether the team's model is given a reasoning effort: on Azure, or on
    Groq's gpt-oss when Groq is the only provider."""
    return bool(os.getenv("AZURE_OPENAI_API_KEY")) or (main_provider() == "groq" and "gpt-oss" in _groq_model())


def main_provider() -> str | None:
    """The provider the team's calls go to first, by the credentials set."""
    if os.getenv("AZURE_OPENAI_API_KEY"):
        return "azure"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    return None


def backup_provider() -> str | None:
    """Groq, standing by for the main provider, when its key is set beside another's."""
    return "groq" if os.getenv("GROQ_API_KEY") and main_provider() != "groq" else None


# Until when the main provider is passed over, on the monotonic clock.
_passed_over_until = 0.0
_passing = threading.Lock()


def standing_in() -> bool:
    """Whether the backup answers for the main provider now, which failed lately."""
    return backup_provider() is not None and time.monotonic() < _passed_over_until


def _pass_over_main() -> None:
    global _passed_over_until
    with _passing:
        _passed_over_until = time.monotonic() + BACKUP_COOLDOWN


def reset_backup() -> None:
    """Try the main provider first again, Groq's minute unspent (the tests start each from here)."""
    global _passed_over_until
    with _passing:
        _passed_over_until = 0.0
    _minute.clear()


@contextmanager
def reasoning(**efforts: str | None):
    """Use these efforts, by role (specialist=..., chief=...), for the calls made
    inside the block; a role left out or None keeps its default."""
    token = _chosen.set({role: effort for role, effort in efforts.items() if effort})
    try:
        yield
    finally:
        _chosen.reset(token)


def _azure_llm(effort: str | None):
    from langchain_openai import AzureChatOpenAI

    missing = _missing(
        ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME"]
    )
    if missing:
        raise LLMNotConfigured(f"Azure OpenAI is missing: {', '.join(missing)}")

    kwargs = {
        "api_key": os.environ["AZURE_OPENAI_API_KEY"],
        "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
        "azure_deployment": os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        "timeout": LLM_TIMEOUT_HIGH if effort == "high" else LLM_TIMEOUT,
        "max_retries": LLM_MAX_RETRIES,
    }
    if effort:
        kwargs["reasoning_effort"] = effort
    return AzureChatOpenAI(**kwargs)


def _openai_llm():
    from langchain_openai import ChatOpenAI

    missing = _missing(["OPENAI_API_KEY"])
    if missing:
        raise LLMNotConfigured(f"OpenAI is missing: {', '.join(missing)}")

    return ChatOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
        timeout=LLM_TIMEOUT,
        max_retries=LLM_MAX_RETRIES,
    )


def _groq_model() -> str:
    return os.getenv("GROQ_MODEL") or GROQ_MODEL


@cache
def _groq_turns() -> threading.BoundedSemaphore:
    """The turns Groq's calls take: GROQ_MAX_CONCURRENT at once."""
    return threading.BoundedSemaphore(int(os.getenv("GROQ_MAX_CONCURRENT") or GROQ_MAX_CONCURRENT))


def _setting(name: str, default: int) -> int:
    return int(os.getenv(name) or default)


@cache
def _encoding():
    import tiktoken

    return tiktoken.get_encoding("o200k_base")  # gpt-oss's


def tokens(text: str) -> int:
    """About how many tokens `text` is, as Groq counts them for gpt-oss."""
    try:
        return len(_encoding().encode(text))
    except Exception:  # the encoding could not be had: a word is about a token and a third
        return len(text) // 3


def groq_answers() -> bool:
    """Whether the team's calls go to Groq now: on its own, or standing in."""
    return main_provider() == "groq" or standing_in()


def _texts(input) -> list[str]:
    if isinstance(input, str):
        return [input]
    return [message.content for message in input if isinstance(getattr(message, "content", None), str)]


def fit(input, most: int):
    """`input` (a prompt, or its messages) at about `most` tokens: when it is
    longer, the middle of its longest message (the founder's or the team's
    text, not the instructions) is left out, with a note saying so, so that the
    call can go to Groq at all."""
    total = sum(tokens(text) for text in _texts(input))
    if total <= most:
        return input
    messages = [input] if isinstance(input, str) else list(input)

    def length(index):
        message = messages[index]
        content = message if isinstance(message, str) else getattr(message, "content", "")
        return (getattr(message, "type", "human") == "human", len(content) if isinstance(content, str) else 0)

    index = max(range(len(messages)), key=length)
    message = messages[index]
    text = message if isinstance(message, str) else message.content
    over = total - most + tokens(SHORTENED)
    keep = max(0, len(text) - int(len(text) * over / max(tokens(text), 1)))
    shortened = text[: keep // 2] + SHORTENED + text[len(text) - keep // 2:]
    log.info("A prompt of about %d tokens was shortened to about %d for Groq.", total, most)
    if isinstance(message, str):
        return shortened if isinstance(input, str) else [*messages[:index], shortened, *messages[index + 1:]]
    messages[index] = message.model_copy(update={"content": shortened})
    return messages


class _Minute:
    """The tokens Groq's calls used in the last minute, to wait for room in."""

    def __init__(self):
        self._spent: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def _used(self, now: float) -> int:
        while self._spent and self._spent[0][0] <= now - 60:
            self._spent.popleft()
        return sum(count for _, count in self._spent)

    def wait_for(self, count: int, most: int) -> None:
        """Wait until `count` more tokens fit in the minute's `most`."""
        while True:
            with self._lock:
                now = time.monotonic()
                if not self._spent or self._used(now) + count <= most:
                    return
                wait = self._spent[0][0] + 60 - now
            time.sleep(max(wait, 0) + 0.25)

    def spend(self, count: int) -> None:
        with self._lock:
            self._spent.append((time.monotonic(), count))

    def clear(self) -> None:
        with self._lock:
            self._spent.clear()


_minute = _Minute()


def _used(reply) -> int | None:
    """The tokens a reply says its call used, prompt and answer."""
    raw = reply.get("raw") if isinstance(reply, dict) else reply
    usage = getattr(raw, "usage_metadata", None)
    return usage.get("total_tokens") if usage else None


class Paced:
    """A Groq model slowed down to Groq's free tier: its calls take turns, each
    shortened to what one call may be and waiting until the minute's tokens
    leave room for it, then for as long as a rate limit says (the client's
    retries), so a burst of the team's parallel calls does not spend Groq's
    minute at once and fail."""

    def __init__(self, model):
        self.model = model

    def invoke(self, input, config=None, **kwargs):
        with _groq_turns():
            input = fit(input, _setting("GROQ_PROMPT_TOKENS", GROQ_PROMPT_TOKENS))
            estimate = sum(tokens(text) for text in _texts(input)) + _ALLOWANCE
            _minute.wait_for(estimate, _setting("GROQ_TOKENS_PER_MINUTE", GROQ_TOKENS_PER_MINUTE))
            reply = self.model.invoke(input, config, **kwargs)
            _minute.spend(_used(reply) or estimate)
            return reply

    def with_structured_output(self, schema, **kwargs):
        return Paced(self.model.with_structured_output(schema, **kwargs))


def _groq_llm(effort: str | None) -> Paced:
    from langchain_openai import ChatOpenAI

    model = _groq_model()
    kwargs = {
        "api_key": os.environ["GROQ_API_KEY"],
        "base_url": GROQ_URL,
        "model": model,
        "timeout": LLM_TIMEOUT_HIGH if effort == "high" else LLM_TIMEOUT,
        "max_retries": int(os.getenv("GROQ_MAX_RETRIES") or GROQ_MAX_RETRIES),
    }
    # Groq's gpt-oss models reason at low, medium or high: "minimal" is their low.
    if effort and "gpt-oss" in model:
        kwargs["reasoning_effort"] = "low" if effort == "minimal" else effort
    return Paced(ChatOpenAI(**kwargs))


_BUILDERS = {"azure": _azure_llm, "openai": lambda effort: _openai_llm(), "groq": _groq_llm}


@cache
def _models(effort: str | None):
    """The main provider's model for `effort`, and the backup's, if one stands by."""
    main = main_provider()
    if main is None:
        raise LLMNotConfigured(
            "No LLM provider configured. Set AZURE_OPENAI_API_KEY (with AZURE_OPENAI_ENDPOINT "
            "and AZURE_OPENAI_DEPLOYMENT_NAME), OPENAI_API_KEY or GROQ_API_KEY."
        )
    backup = backup_provider()
    try:
        model = _BUILDERS[main](effort)
    except LLMNotConfigured as error:
        if not backup:
            raise
        log.warning("%s is not set up (%s), so Groq answers every call.", NAMES[main], error)
        return _groq_llm(effort), None
    return model, _groq_llm(effort) if backup else None


class WithBackup:
    """The main provider's model, with the backup's to answer for it: a call
    the main provider cannot serve goes to the backup, and so do the calls
    after it for BACKUP_COOLDOWN. A structured reply from the backup comes
    through a JSON schema, as from Azure: measured on Groq's gpt-oss-120b, its
    tool calling skipped the tool for small schemas (the brief's search plan,
    0 of 3), where the JSON schema held (3 of 3)."""

    def __init__(self, main, backup):
        self.main = main
        self.backup = backup

    def invoke(self, input, config=None, **kwargs):
        if standing_in():
            return self.backup.invoke(input, config, **kwargs)
        try:
            return self.main.invoke(input, config, **kwargs)
        except UNAVAILABLE as error:
            _pass_over_main()
            log.warning("%s could not answer (%s: %s), so Groq, the backup, answers for the next %d minutes.",
                        NAMES[main_provider()], type(error).__name__, error, BACKUP_COOLDOWN // 60)
            return self.backup.invoke(input, config, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        return WithBackup(
            self.main.with_structured_output(schema, **kwargs),
            self.backup.with_structured_output(schema, **{**kwargs, "method": "json_schema"}),
        )


def get_llm(role: str = SPECIALIST):
    """Return the chat model for `role`, from the provider whose credentials are set.

    Azure OpenAI takes precedence when its variables are present; otherwise
    OpenAI, otherwise Groq. With Groq's key beside another's, the model comes
    with Groq standing by (WithBackup). Raises LLMNotConfigured, naming the
    missing variables, when no provider is configured.

    The model for each reasoning effort is built once and then reused, so its
    calls share one HTTP connection pool instead of opening a new connection. A
    failure is not cached, so the next call checks the environment again.
    """
    main, backup = _models(reasoning_effort(role) if takes_reasoning_effort() else None)
    return WithBackup(main, backup) if backup else main


if __name__ == "__main__":
    from config import DEBUG_MODE  # noqa: F401 - loads .env

    reply = get_llm().invoke("Reply with one short sentence confirming you are reachable.")
    print(reply.content)
