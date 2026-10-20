"""Chat model client shared by every agent.

The provider is chosen by which credentials are set in the environment:
Azure OpenAI if the Azure variables are present, otherwise OpenAI. The model
is created on first use, so the app and the tests start without credentials.

Each call asks for the model of a role. On Azure each role has a reasoning
effort: the Chief of Staff's (AZURE_OPENAI_CHIEF_REASONING_EFFORT) can be higher
than the specialists' (AZURE_OPENAI_REASONING_EFFORT), because its calls are the
team's decisions while the specialists' are most of the volume. A request can
set its own efforts with `reasoning(...)`, which is how the UI's sliders work.
"""

import os
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
    """Whether the configured provider is given a reasoning effort (Azure only)."""
    return bool(os.getenv("AZURE_OPENAI_API_KEY"))


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


@cache
def _model(effort: str | None):
    if os.getenv("AZURE_OPENAI_API_KEY"):
        return _azure_llm(effort)
    if os.getenv("OPENAI_API_KEY"):
        return _openai_llm()
    raise LLMNotConfigured(
        "No LLM provider configured. Set AZURE_OPENAI_API_KEY (with "
        "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME) or OPENAI_API_KEY."
    )


def get_llm(role: str = SPECIALIST):
    """Return the chat model for `role`, from the provider whose credentials are set.

    Azure OpenAI takes precedence when its variables are present; otherwise
    OpenAI is used. Raises LLMNotConfigured, naming the missing variables, when
    no provider is configured.

    The model for each reasoning effort is built once and then reused, so its
    calls share one HTTP connection pool instead of opening a new connection. A
    failure is not cached, so the next call checks the environment again.
    """
    return _model(reasoning_effort(role) if takes_reasoning_effort() else None)


if __name__ == "__main__":
    from config import DEBUG_MODE  # noqa: F401 - loads .env

    reply = get_llm().invoke("Reply with one short sentence confirming you are reachable.")
    print(reply.content)
