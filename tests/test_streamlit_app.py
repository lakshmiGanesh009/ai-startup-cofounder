"""Tests for the Streamlit UI, with the backend replaced by canned responses.

They need the `ui` dependency group (uv run --group ui pytest), and are
skipped without it.
"""

import httpx
import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = "../streamlit_app.py"
# The first run after installing imports pandas, pyarrow and the rest of
# Streamlit cold, which can take longer than AppTest's default of 3 seconds.
TIMEOUT = 60

RESULT = {
    "session_id": "session-1",
    "objective": "Evaluate an AI scheduling tool.",
    "assignments": {"finance": "Price it."},
    "analyses": {"finance": "Charge $99 a month per clinic."},
    "review_history": [{"finance": {"approved": True, "score": 5, "feedback": ""}}],
    "resolutions": [],
    "metrics": {"plan": {"calls": 1, "seconds": 1.0, "tokens": 500}},
    "final_strategy": "Launch a paid pilot with three clinics.",
}


@pytest.fixture
def backend(monkeypatch):
    """Answer the app's HTTP calls; returns the /evaluate bodies it was sent."""
    sent = []

    def get(url, timeout):
        return httpx.Response(200, json={"status": "healthy", "service": "test"})

    def post(url, json, timeout):
        sent.append(json)
        return httpx.Response(200, json=RESULT)

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(httpx, "post", post)
    return sent


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def test_an_evaluation_shows_the_strategy_and_a_follow_up_reuses_the_session(backend):
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    app.text_area(key="prompt").input("Evaluate an AI scheduling tool.")
    app.text_input(key="target_market").input("Small clinics")
    _button(app, "Evaluate").click().run()

    assert not app.exception
    assert backend[0] == {
        "prompt": "Evaluate an AI scheduling tool.",
        "context": {"target_market": "Small clinics"},
        "session_id": None,
    }
    assert any("Launch a paid pilot" in block.value for block in app.markdown)

    app.text_input(key="follow_up").input("Refine the pricing.")
    _button(app, "Send follow-up").click().run()

    assert backend[1]["session_id"] == "session-1"
    assert backend[1]["prompt"] == "Refine the pricing."


def test_a_backend_error_is_shown(monkeypatch):
    def post(url, json, timeout):
        return httpx.Response(502, json={"detail": "The LLM call failed: timeout"})

    monkeypatch.setattr(httpx, "get", lambda url, timeout: httpx.Response(503))
    monkeypatch.setattr(httpx, "post", post)

    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    app.text_area(key="prompt").input("Evaluate an AI scheduling tool.")
    _button(app, "Evaluate").click().run()

    assert not app.exception
    assert any("502: The LLM call failed" in error.value for error in app.error)
