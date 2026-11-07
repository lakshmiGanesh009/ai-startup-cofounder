"""MCP servers for the tests, so no look-up leaves the machine: our FRED server
(fred_server.py) answering from FRED data made up here, and a stand-in for
Tavily's server that answers in Tavily's text format. A test puts them in
lookups.SERVERS, and the client connects to them in-process."""

from datetime import date

import httpx
from mcp.server.mcpserver import MCPServer

import fred_server

TODAY = date.today()


def series(series_id: str, title: str, units: str = "Percent", frequency: str = "Monthly",
           ended: date = TODAY, popularity: int = 50) -> dict:
    return {"id": series_id, "title": title, "units": units, "frequency": frequency,
            "observation_end": ended.isoformat(), "popularity": popularity}


def monthly(*values: float) -> list[tuple[str, str]]:
    """Monthly values ending this month, oldest first."""
    first = TODAY.replace(day=1)
    months = [(first.year * 12 + first.month - 1) - back for back in range(len(values) - 1, -1, -1)]
    return [(date(month // 12, month % 12 + 1, 1).isoformat(), str(value)) for month, value in zip(months, values)]


# The figures every plan reads, a year and a month of them.
CORE = {
    "DGS10": (series("DGS10", "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity", frequency="Daily", popularity=95),
              monthly(3.98, *[4.0] * 11, 4.12)),
    "CPIAUCSL": (series("CPIAUCSL", "Consumer Price Index for All Urban Consumers: All Items", units="Index 1982-1984=100", popularity=94),
                 monthly(314.0, *[318.0] * 11, 323.42)),
}


def fred_api(searches: dict[str, list[dict]], data: dict[str, tuple[dict, list[tuple[str, str]]]],
             calls: list, failing: bool = False) -> httpx.MockTransport:
    """FRED's API, answering searches and series from what it is given."""

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path.split("/fred/", 1)[1]
        params = dict(request.url.params)
        calls.append((path, params))
        if failing:
            return httpx.Response(500, json={"error_message": "Internal Server Error"})
        if path == "series/search":
            return httpx.Response(200, json={"seriess": searches.get(params["search_text"], [])})
        found = data.get(params.get("series_id", ""))
        if path == "series":
            return httpx.Response(200, json={"seriess": [found[0]] if found else []})
        return httpx.Response(200, json={"observations": [{"date": day, "value": value} for day, value in (found[1] if found else [])]})

    return httpx.MockTransport(handle)


def use_fred(monkeypatch, searches=None, data=None, failing=False) -> list:
    """Our FRED server, in-process, on a FRED made up of `searches` and `data`
    (the core series always); returns the requests FRED was sent."""
    import lookups

    calls: list = []
    monkeypatch.setenv("FRED_API_KEY", "fred-test-key")
    monkeypatch.setattr(fred_server, "_transport", fred_api(searches or {}, {**CORE, **(data or {})}, calls, failing))
    monkeypatch.setitem(lookups.SERVERS, "fred", lambda: fred_server.server)
    return calls


def tavily_server(results: dict[str, list[tuple[str, str, str]]], pages: dict[str, str], calls: list) -> MCPServer:
    """Tavily's MCP server: its search and extract tools, answering in its text format."""
    server = MCPServer("tavily-test")

    @server.tool(name="tavily_search")
    def tavily_search(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
        calls.append(("search", query))
        lines = ["Detailed Results:"]
        for title, url, content in results.get(query, [])[:max_results]:
            lines += [f"\nTitle: {title}", f"URL: {url}", f"Content: {content}"]
        return "\n".join(lines)

    @server.tool(name="tavily_extract")
    def tavily_extract(urls: list[str], extract_depth: str = "basic", format: str = "markdown", query: str = "") -> str:
        calls.append(("extract", tuple(urls)))
        lines = ["Detailed Results:"]
        for url in urls:
            lines += ["\nTitle: undefined", f"URL: {url}", "Content: undefined", f"Raw Content: {pages.get(url, '')}"]
        return "\n".join(lines)

    return server


def use_tavily(monkeypatch, results, pages) -> list:
    """The stand-in for Tavily's MCP server; returns the calls made to it."""
    import lookups

    calls: list = []
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    server = tavily_server(results, pages, calls)
    monkeypatch.setitem(lookups.SERVERS, "tavily", lambda: server)
    return calls
