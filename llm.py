"""Chat model client shared by every agent.

The provider is chosen by which credentials are set in the environment:
Azure OpenAI if the Azure variables are present, otherwise OpenAI. The model
is created on first use, so the app and the tests start without credentials.
"""

import os


def _missing(names):
    """Return the names from `names` that are unset or empty in the environment."""
    return [name for name in names if not os.getenv(name)]


def _azure_llm():
    from langchain_openai import AzureChatOpenAI

    missing = _missing(
        ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME"]
    )
    if missing:
        raise RuntimeError(f"Azure OpenAI is missing: {', '.join(missing)}")

    kwargs = {
        "api_key": os.environ["AZURE_OPENAI_API_KEY"],
        "azure_endpoint": os.environ["AZURE_OPENAI_ENDPOINT"],
        "azure_deployment": os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        "api_version": os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    }
    effort = os.getenv("AZURE_OPENAI_REASONING_EFFORT")
    if effort:
        kwargs["reasoning_effort"] = effort
    return AzureChatOpenAI(**kwargs)


def _openai_llm():
    from langchain_openai import ChatOpenAI

    missing = _missing(["OPENAI_API_KEY"])
    if missing:
        raise RuntimeError(f"OpenAI is missing: {', '.join(missing)}")

    return ChatOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
    )


def get_llm():
    """Return the chat model for the provider whose credentials are set.

    Azure OpenAI takes precedence when its variables are present; otherwise
    OpenAI is used. Raises a RuntimeError that names the missing variables when
    no provider is configured.
    """
    if os.getenv("AZURE_OPENAI_API_KEY"):
        return _azure_llm()
    if os.getenv("OPENAI_API_KEY"):
        return _openai_llm()
    raise RuntimeError(
        "No LLM provider configured. Set AZURE_OPENAI_API_KEY (with "
        "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME) or OPENAI_API_KEY."
    )


if __name__ == "__main__":
    from config import DEBUG_MODE  # noqa: F401 - loads .env

    reply = get_llm().invoke("Reply with one short sentence confirming you are reachable.")
    print(reply.content)
