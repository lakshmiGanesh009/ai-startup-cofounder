"""Chat model client shared by every agent.

The provider is chosen by which credentials are set in the environment:
Azure OpenAI if the Azure variables are present, otherwise OpenAI. The model
is created on first use, so the app and the tests start without credentials.

Each call asks for the model of a role. On Azure the Chief of Staff can run
on a deployment of its own (AZURE_OPENAI_CHIEF_DEPLOYMENT_NAME; else the
team's, AZURE_OPENAI_DEPLOYMENT_NAME), and each role has a reasoning effort: the Chief of Staff's (AZURE_OPENAI_CHIEF_REASONING_EFFORT) can be higher
than the specialists' (AZURE_OPENAI_REASONING_EFFORT), because its calls are the
team's decisions while the specialists' are most of the volume. A request can
set its own efforts with `reasoning(...)`, which is how the UI's sliders work.
"""

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from typing import Literal, get_args

import openai

from config import LLM_MAX_RETRIES, LLM_TIMEOUT, LLM_TIMEOUT_HIGH
from monitor import monitor


class LLMNotConfigured(RuntimeError):
    """No LLM provider is configured, or its settings are incomplete."""


class LLMReplyError(Exception):
    """The model replied, but not in a form the workflow can use."""


# What an LLM call raises when it still fails after the client's own retries.
LLM_ERRORS = (openai.OpenAIError, LLMReplyError)


# What a model's own usage policy refused a request as, by Azure's code for it.
_POLICIES = {"cyber_policy": "a possible cybersecurity risk or illegal activity"}


def refused(error: Exception) -> bool:
    """Whether Azure refused the request for what it asks: its content filter
    ("content_filter"), or a model's own usage policy ("cyber_policy" and the
    like). That is for the founder to change, not a fault to retry."""
    if not isinstance(error, openai.BadRequestError):
        return False
    code = error.code or ""
    return code == "content_filter" or code.endswith("_policy")


def failure(error: Exception) -> str:
    """What to tell the founder when a model call failed: for a refusal, why,
    in plain words, without the provider's own links."""
    if refused(error) and error.code != "content_filter":
        what = _POLICIES.get(error.code, "a breach of its usage policy")
        return (f"Azure OpenAI's safety policy refused this request: it read it as {what}. The team does not "
                "help with that; if the idea is legitimate, rephrase it and try again.")
    if refused(error):
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


def deployment(role: str) -> str | None:
    """The Azure deployment `role`'s calls go to: the Chief of Staff's own, if
    one is named, else the team's."""
    if role == CHIEF and os.getenv("AZURE_OPENAI_CHIEF_DEPLOYMENT_NAME"):
        return os.environ["AZURE_OPENAI_CHIEF_DEPLOYMENT_NAME"]
    return os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")


# The models after gpt-5 (gpt-5.1 on, such as gpt-5.6-luna) take "none" where gpt-5 took "minimal".
_NONE_FOR_MINIMAL = re.compile(r"gpt-5\.\d")


def _azure_llm(effort: str | None, name: str | None):
    from langchain_openai import AzureChatOpenAI

    missing = _missing(
        ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME"]
    )
    if missing:
        raise LLMNotConfigured(f"Azure OpenAI is missing: {', '.join(missing)}")

    name = name or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
    kwargs = {
        "api_key": os.environ["AZURE_OPENAI_API_KEY"],
        "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
        "azure_deployment": name,
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        "timeout": LLM_TIMEOUT_HIGH if effort == "high" else LLM_TIMEOUT,
        "max_retries": LLM_MAX_RETRIES,
    }
    if effort:
        kwargs["reasoning_effort"] = "none" if effort == "minimal" and _NONE_FOR_MINIMAL.search(name) else effort
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


def main_provider() -> str | None:
    """The provider the team's calls go to, by the credentials set: "azure" or "openai"."""
    if os.getenv("AZURE_OPENAI_API_KEY"):
        return "azure"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return None


def _usage(reply) -> tuple[int, int]:
    """The tokens a reply says its call read and wrote."""
    raw = reply.get("raw") if isinstance(reply, dict) else reply
    usage = getattr(raw, "usage_metadata", None) or {}
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0)


class Counted:
    """A provider's model whose calls the Monitor counts: the tokens each read
    and wrote, how long it took, and why one failed."""

    def __init__(self, model, provider: str):
        self.model = model
        self.provider = provider

    def invoke(self, input, config=None, **kwargs):
        with monitor.calling(self.provider, "model") as call:
            reply = self.model.invoke(input, config, **kwargs)
            call.used(*_usage(reply))
        return reply

    def with_structured_output(self, schema, **kwargs):
        return Counted(self.model.with_structured_output(schema, **kwargs), self.provider)


@cache
def _model(effort: str | None, name: str | None = None):
    if os.getenv("AZURE_OPENAI_API_KEY"):
        return Counted(_azure_llm(effort, name), "azure")
    if os.getenv("OPENAI_API_KEY"):
        return Counted(_openai_llm(), "openai")
    raise LLMNotConfigured(
        "No LLM provider configured. Set AZURE_OPENAI_API_KEY (with "
        "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME) or OPENAI_API_KEY."
    )


def get_llm(role: str = SPECIALIST):
    """Return the chat model for `role`, from the provider whose credentials are
    set, counted on the Monitor (Counted).

    Azure OpenAI takes precedence when its variables are present; otherwise
    OpenAI is used. Raises LLMNotConfigured, naming the missing variables, when
    no provider is configured.

    The model for each reasoning effort is built once and then reused, so its
    calls share one HTTP connection pool instead of opening a new connection. A
    failure is not cached, so the next call checks the environment again.
    """
    effort = reasoning_effort(role) if takes_reasoning_effort() else None
    return _model(effort, deployment(role) if os.getenv("AZURE_OPENAI_API_KEY") else None)


if __name__ == "__main__":
    from config import DEBUG_MODE  # noqa: F401 - loads .env

    reply = get_llm().invoke("Reply with one short sentence confirming you are reachable.")
    print(reply.content)
