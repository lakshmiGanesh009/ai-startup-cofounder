"""Where the web research runs: on Azure OpenAI's own web search (Bing, through
the team's deployment; azure_web.py), the default, or on Tavily (search.py),
for demanding tasks. The founder picks one in the sidebar, and each request
names its choice; a provider that is not set up is never used.
"""

from typing import Literal

import azure_web
import search
from search import Hit, Report, SearchFailed

Provider = Literal["azure", "tavily"]
NAMES: dict[str, str] = {"azure": "Azure OpenAI", "tavily": "Tavily"}


def available() -> dict[str, bool]:
    """Which providers are set up."""
    return {"azure": azure_web.available(), "tavily": search.search_configured()}


def default() -> Provider | None:
    """Azure OpenAI when it is set up, else Tavily, else none."""
    ready = available()
    return "azure" if ready["azure"] else "tavily" if ready["tavily"] else None


def chosen(provider: str | None) -> Provider | None:
    """The provider to use for a request: the one it asks for if that is set up,
    else the default; None when neither is."""
    if provider and available().get(provider):
        return provider  # type: ignore[return-value]
    return default()


def _client(provider: Provider):
    return azure_web if provider == "azure" else search


def search_all(queries: list[str], provider: Provider) -> tuple[list[Hit], str | None]:
    """The provider's searches, pooled; with why there are none when all failed."""
    return _client(provider).search_all(queries)


def research_all(tasks: dict[str, tuple[str, dict | None]], provider: Provider) -> dict[str, Report | SearchFailed]:
    """The provider's research tasks, run at the same time."""
    return _client(provider).research_all(tasks)
