"""Today's exchange rates, to fill in when the founder converts a report's
currency: the European Central Bank's daily reference rates (in euros, about
30 currencies, published each working day around 16:00 CET), with the UAE
dirham and the Saudi riyal from their fixed pegs to the US dollar, which the
ECB does not publish. Fetched at most every few hours, and never needed: the
founder can always type a bank's rate instead, and the conversion itself is
done by code at whatever rate is given (currency.py)."""

import logging
import re
import time

import httpx
from pydantic import BaseModel

from currency import CURRENCIES

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
SOURCE = "European Central Bank reference rates"
# Units of each currency per US dollar, fixed by its central bank.
PEGS = {"AED": 3.6725, "SAR": 3.75}
CACHE_SECONDS = 6 * 3600
TIMEOUT = 10

log = logging.getLogger(__name__)

# Tests answer for the ECB through this (an httpx.MockTransport).
_transport: httpx.BaseTransport | None = None
# (when fetched, the day the rates are for, units of each currency per euro)
_cache: tuple[float, str, dict[str, float]] | None = None

_DAY = re.compile(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]")
_RATE = re.compile(r"currency=['\"]([A-Z]{3})['\"]\s+rate=['\"]([0-9.]+)['\"]")


class RatesUnavailable(Exception):
    """The rates could not be had, and why."""


class Rates(BaseModel):
    base: str
    date: str
    source: str
    # Units of each other currency for one unit of `base`.
    rates: dict[str, float]
    # The currencies worked out from their peg to the dollar, not published by the ECB.
    pegged: list[str]


def _per_euro() -> tuple[str, dict[str, float]]:
    global _cache
    if _cache and time.monotonic() - _cache[0] < CACHE_SECONDS:
        return _cache[1], _cache[2]
    try:
        with httpx.Client(timeout=TIMEOUT, transport=_transport) as client:
            response = client.get(ECB_URL)
            response.raise_for_status()
    except httpx.HTTPError as error:
        log.warning("The ECB's exchange rates could not be fetched: %s", type(error).__name__)
        raise RatesUnavailable(f"The ECB's rates could not be fetched ({type(error).__name__}).") from None
    day = _DAY.search(response.text)
    rates = {code: float(rate) for code, rate in _RATE.findall(response.text)}
    if not day or "USD" not in rates:
        raise RatesUnavailable("The ECB answered without its rates.")
    rates["EUR"] = 1.0
    for code, per_dollar in PEGS.items():
        rates[code] = per_dollar * rates["USD"]
    _cache = (time.monotonic(), day.group(1), rates)
    return day.group(1), rates


def rates_from(base: str) -> Rates:
    """One `base` in each of the app's other currencies, to six significant figures."""
    day, per_euro = _per_euro()
    if base not in per_euro:
        raise RatesUnavailable(f"The ECB has no rate for {base}.")
    rates = {
        code: float(f"{per_euro[code] / per_euro[base]:.6g}")
        for code in CURRENCIES
        if code != base and code in per_euro
    }
    return Rates(base=base, date=day, source=SOURCE, rates=rates, pegged=sorted(PEGS))
