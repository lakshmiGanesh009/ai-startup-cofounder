"""An MCP server for FRED, the St. Louis Fed's database of economic data:
search its series, and read a series' recent values. The team's look-ups
(lookups.py) start it as a subprocess and talk to it over stdio; any MCP
client can use it the same way: `python -m fred_server`, with FRED_API_KEY set.

FRED takes its key in the query string, so the key is cut out of the request
lines httpx logs (wherever this module is loaded, the API's tests included),
and an error names what FRED said, never the URL.
"""

import logging
import os
import re
from datetime import date, timedelta

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

API = "https://api.stlouisfed.org/fred"
TIMEOUT = 20
SERIES_ID = re.compile(r"^[A-Za-z0-9_.]{1,40}$")
# Tests replace the transport, so no request leaves the machine.
_transport: httpx.BaseTransport | None = None


class _HideKey(logging.Filter):
    """Cut the key out of the request lines httpx logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "api_key=" in message:
            record.msg, record.args = re.sub(r"api_key=[^&\s\"']+", "api_key=[hidden]", message), ()
        return True


logging.getLogger("httpx").addFilter(_HideKey())

server = MCPServer(
    "fred",
    title="FRED economic data",
    instructions="Search FRED's series by what they measure, then read a series' recent values.",
)


class Series(BaseModel):
    id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str = ""
    observation_end: str = Field(description="The date of its latest value.")
    last_updated: str = ""
    popularity: int = 0


class Observation(BaseModel):
    date: str
    value: float


class SeriesData(BaseModel):
    series: Series
    observations: list[Observation] = Field(description="Oldest first; missing values left out.")
    link: str


class FredError(ToolError):
    """FRED refused or failed a request, and why; the client is told the why."""


def _get(path: str, **params) -> dict:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise FredError("FRED_API_KEY is not set.")
    try:
        with httpx.Client(timeout=TIMEOUT, transport=_transport) as client:
            response = client.get(f"{API}/{path}", params={**params, "api_key": key, "file_type": "json"})
    except httpx.HTTPError as error:
        raise FredError(f"FRED could not be reached ({type(error).__name__}).") from None
    if response.status_code != 200:
        try:
            said = response.json().get("error_message", "")
        except ValueError:
            said = ""
        said = " ".join(said.split()).rstrip(".")
        raise FredError(f"FRED answered {response.status_code}{': ' + said if said else ''}.")
    return response.json()


def _series(raw: dict) -> Series:
    return Series(
        id=raw["id"],
        title=raw.get("title", raw["id"]),
        units=raw.get("units", ""),
        frequency=raw.get("frequency", ""),
        seasonal_adjustment=raw.get("seasonal_adjustment_short", ""),
        observation_end=raw.get("observation_end", ""),
        last_updated=raw.get("last_updated", ""),
        popularity=int(raw.get("popularity") or 0),
    )


@server.tool()
def search_series(text: str, limit: int = 8) -> list[Series]:
    """FRED's series that match `text`, the most used first: each with its id,
    title, units, frequency and the date of its latest value."""
    data = _get("series/search", search_text=text[:200], limit=max(1, min(limit, 20)),
                order_by="popularity", sort_order="desc")
    return [_series(raw) for raw in data.get("seriess", [])]


@server.tool()
def series_data(series_id: str, days: int = 400) -> SeriesData:
    """A series' description and its values over the last `days` days (a year
    and a little more by default), oldest first, with its page on FRED."""
    if not SERIES_ID.match(series_id):
        raise FredError(f"{series_id!r} is not a FRED series id.")
    found = _get("series", series_id=series_id).get("seriess") or []
    if not found:
        raise FredError(f"FRED has no series {series_id}.")
    start = (date.today() - timedelta(days=max(30, min(days, 3650)))).isoformat()
    observations = _get("series/observations", series_id=series_id, observation_start=start).get("observations", [])
    values = [
        Observation(date=row["date"], value=float(row["value"]))
        for row in observations
        if re.fullmatch(r"-?\d+(\.\d+)?", str(row.get("value", "")))
    ]
    return SeriesData(series=_series(found[0]), observations=values,
                      link=f"https://fred.stlouisfed.org/series/{series_id}")


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
