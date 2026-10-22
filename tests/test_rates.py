"""Tests for today's exchange rates (rates.py and GET /rates/{base}), on a
made-up ECB: nothing leaves the machine."""

import httpx
from fastapi.testclient import TestClient

import rates
from main import app

client = TestClient(app)

ECB = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time='2026-10-21'>
      <Cube currency='USD' rate='1.1234'/>
      <Cube currency='JPY' rate='177.36'/>
      <Cube currency='GBP' rate='0.83825'/>
      <Cube currency='INR' rate='106.1265'/>
      <Cube currency='HUF' rate='365.00'/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


def use_ecb(monkeypatch, answer=lambda request: httpx.Response(200, text=ECB)) -> list:
    """A made-up ECB; returns the requests it was sent."""
    calls: list = []

    def handle(request):
        calls.append(str(request.url))
        return answer(request)

    monkeypatch.setattr(rates, "_transport", httpx.MockTransport(handle))
    return calls


def test_rates_from_the_dollar_with_the_pegs_and_only_the_apps_currencies(monkeypatch):
    use_ecb(monkeypatch)
    answer = client.get("/rates/USD")
    assert answer.status_code == 200
    body = answer.json()
    assert body["base"] == "USD" and body["date"] == "2026-10-21"
    assert body["source"] == "European Central Bank reference rates"
    assert body["rates"]["EUR"] == 0.890155  # 1 / 1.1234
    assert body["rates"]["INR"] == 94.4690  # 106.1265 / 1.1234
    assert body["rates"]["AED"] == 3.6725 and body["rates"]["SAR"] == 3.75
    # The ECB's forint is not one of the app's currencies, nor is the base itself.
    assert "HUF" not in body["rates"] and "USD" not in body["rates"]
    assert "CHF" not in body["rates"]  # not in this made-up day's file
    assert body["pegged"] == ["AED", "SAR"]


def test_from_a_pegged_currency_and_from_the_euro(monkeypatch):
    use_ecb(monkeypatch)
    assert client.get("/rates/AED").json()["rates"]["USD"] == 0.272294  # 1 / 3.6725
    assert client.get("/rates/EUR").json()["rates"]["GBP"] == 0.83825


def test_the_rates_are_fetched_once_for_hours(monkeypatch):
    calls = use_ecb(monkeypatch)
    client.get("/rates/USD")
    client.get("/rates/GBP")
    assert calls == [rates.ECB_URL]


def test_an_unknown_currency_and_an_unreachable_ecb_say_so(monkeypatch):
    use_ecb(monkeypatch)
    assert client.get("/rates/XYZ").status_code == 422

    def down(request):
        raise httpx.ConnectTimeout("too slow")

    use_ecb(monkeypatch, down)
    failed = client.get("/rates/USD")
    assert failed.status_code == 503
    assert failed.json()["detail"] == "The ECB's rates could not be fetched (ConnectTimeout)."

    use_ecb(monkeypatch, lambda request: httpx.Response(200, text="<html>Maintenance</html>"))
    assert client.get("/rates/USD").json()["detail"] == "The ECB answered without its rates."
