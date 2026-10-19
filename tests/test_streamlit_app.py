"""Tests for the Streamlit UI, with the backend replaced by canned responses.

They need the `ui` dependency group (uv run --group ui pytest), and are
skipped without it.
"""

import httpx
import pytest
from fpdf import FPDF

from proposal import investment_metrics
from tests.sample_proposal import SAMPLE

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = "../streamlit_app.py"
# The first run after installing imports pandas, pyarrow and the rest of
# Streamlit cold, which can take longer than AppTest's default of 3 seconds.
TIMEOUT = 60

HEALTH = {
    "status": "healthy",
    "service": "test",
    "reasoning": {"adjustable": True, "efforts": ["minimal", "low", "medium", "high"],
                  "specialist": "minimal", "chief": "medium"},
}
RESULT = {
    "session_id": "session-1",
    "objective": "Evaluate an AI scheduling tool.",
    "assignments": {"finance": "Price it."},
    "analyses": {"finance": "Charge $99 a month per clinic."},
    "review_history": [{"finance": {"approved": True, "score": 5, "feedback": ""}}],
    "resolutions": [],
    "metrics": {"plan": {"calls": 1, "seconds": 1.0, "tokens": 500}},
    "final_strategy": "Launch a paid pilot with three clinics at $99 a month, capped at $5k.",
}


@pytest.fixture
def backend(monkeypatch):
    """Answer the app's HTTP calls; returns the /evaluate bodies it was sent."""
    sent = []

    def get(url, timeout):
        return httpx.Response(200, json=HEALTH)

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
        # The sidebar's sliders start at the backend's configured efforts.
        "reasoning": {"specialist": "minimal", "chief": "medium"},
    }
    # Dollar signs are escaped, or Streamlit would render "$99 ... $5k" as a formula.
    assert any(
        "at \\$99 a month, capped at \\$5k" in block.value for block in app.markdown
    )

    app.text_input(key="follow_up").input("Refine the pricing.")
    _button(app, "Send follow-up").click().run()

    assert backend[1]["session_id"] == "session-1"
    assert backend[1]["prompt"] == "Refine the pricing."


def test_the_sliders_set_each_roles_reasoning(backend):
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    app.select_slider(key="effort_specialist").set_value("low")
    app.select_slider(key="effort_chief").set_value("high").run()
    app.text_area(key="prompt").input("Evaluate an AI scheduling tool.")
    _button(app, "Evaluate").click().run()

    assert backend[0]["reasoning"] == {"specialist": "low", "chief": "high"}


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


class FakeReportsBackend:
    """Answers the Reports page's calls like the API, and records what it sent."""

    def __init__(self, reports=True):
        self.report = {
            "session_id": "session-1",
            "title": "An AI scheduling tool",
            "objective": "Evaluate it.",
            "context": "",
            "sections": [
                {"key": "strategy", "title": "Launch Strategy", "body": "Launch a pilot."},
                {"key": "finance", "title": "Financial Planning", "body": "Charge $99."},
            ],
            "version": 1,
            "proposal": None,
            "investment": None,
            "checks": [],
            "edited": False,
            "outdated": False,
            "updated_at": "2026-10-16T10:00:00+00:00",
        }
        self.has_reports = reports
        self.saves = []
        self.posts = []
        self.conflict = False
        # (method, path ending) -> the error status to answer with instead.
        self.failures: dict[tuple[str, str], int] = {}

    def _failure(self, method, path):
        for (failing, ending), status in self.failures.items():
            if failing == method and path.endswith(ending):
                return httpx.Response(status, json={"detail": f"It failed ({status})."})
        return None

    def get(self, url, timeout):
        path = url.split("8000", 1)[1]
        if path == "/health":
            return httpx.Response(200, json=HEALTH)
        if failure := self._failure("GET", path):
            return failure
        if path == "/reports":
            summary = {k: v for k, v in self.report.items()
                       if k not in ("objective", "context", "sections", "proposal", "investment")}
            summary["has_proposal"] = self.report["proposal"] is not None
            return httpx.Response(200, json=[summary] if self.has_reports else [])
        if path.endswith("/pdf"):
            pdf = FPDF()
            pdf.add_page()
            return httpx.Response(200, content=bytes(pdf.output()))
        return httpx.Response(200, json=self.report)

    def _changed(self, **updates):
        self.report = {**self.report, **updates, "version": self.report["version"] + 1}
        return self.report

    def put(self, url, json, timeout):
        self.saves.append(json)
        if failure := self._failure("PUT", url):
            return failure
        if self.conflict or json["version"] != self.report["version"]:
            return httpx.Response(409, json={"detail": "The report changed."})
        if url.endswith("/proposal"):
            return httpx.Response(200, json=self._changed(proposal=json["proposal"], edited=True))
        return httpx.Response(200, json=self._changed(sections=json["sections"], edited=True))

    def post(self, url, json=None, timeout=None):
        self.posts.append((url.split("8000", 1)[1], json))
        if failure := self._failure("POST", url):
            return failure
        if url.endswith("/reset"):
            return httpx.Response(200, json=self._changed(proposal=None, investment=None, edited=False))
        if url.endswith("/proposal"):
            report = self._changed(proposal=SAMPLE.model_dump(mode="json"),
                                   investment=investment_metrics(SAMPLE.financial).model_dump(mode="json"))
            return httpx.Response(200, json={"report": report, "failed": []})
        if url.endswith("/revise"):
            return httpx.Response(200, json={"report": self._changed(), "failed": ["Financial Plan & Projections"]})
        return httpx.Response(404, json={"detail": "Not found"})


@pytest.fixture
def reports_backend(monkeypatch):
    backend = FakeReportsBackend()
    monkeypatch.setattr(httpx, "get", backend.get)
    monkeypatch.setattr(httpx, "put", backend.put)
    monkeypatch.setattr(httpx, "post", backend.post)
    return backend


def _reports_page():
    app = AppTest.from_file(APP, default_timeout=TIMEOUT)
    app.session_state["session_id"] = "session-1"
    return app.switch_page("ui/reports_page.py").run()


def _toggle(app, label, index=0):
    return [toggle for toggle in app.toggle if toggle.label == label][index]


def test_the_team_report_is_shown_as_text_and_saved_when_edited(reports_backend):
    app = _reports_page()
    assert not app.exception
    assert any("Charge \\$99." in block.value for block in app.markdown)
    assert not app.text_area

    _toggle(app, "Edit").set_value(True).run()
    assert [box.label for box in app.text_area] == ["Launch Strategy", "Financial Planning"]
    app.text_area(key="report:session-1:1:strategy").input("Launch a paid pilot.").run()

    assert not app.exception
    assert reports_backend.saves[-1]["version"] == 1
    assert reports_backend.saves[-1]["sections"][0]["body"] == "Launch a paid pilot."
    assert reports_backend.saves[-1]["sections"][1]["body"] == "Charge $99."
    # A second edit is saved against the version the first one produced.
    app.text_area(key="report:session-1:1:finance").input("Charge $149.").run()
    assert reports_backend.saves[-1]["version"] == 2
    assert not app.warning


def test_a_save_after_the_report_changed_elsewhere_reloads_it(reports_backend):
    app = _reports_page()
    _toggle(app, "Edit").set_value(True).run()
    reports_backend.conflict = True

    app.text_area(key="report:session-1:1:strategy").input("My edit.").run()

    assert any("changed elsewhere" in w.value for w in app.warning)


def test_writing_the_proposal_shows_it_with_the_sliders_efforts(reports_backend):
    app = _reports_page()
    app.select_slider(key="effort_chief").set_value("high").run()

    _button(app, "Write the investment proposal").click().run()

    assert not app.exception
    path, body = reports_backend.posts[-1]
    assert path == "/reports/session-1/proposal"
    assert body == {"version": 1, "reasoning": {"specialist": "minimal", "chief": "high"}}
    assert any("Recommendation: Go with conditions" in block.value for block in app.warning)
    assert [tab.label for tab in app.tabs] == [
        "Executive summary", "Market", "Technical", "Financial", "Risk & compliance", "KPIs",
        "Team report",
    ]
    assert any(metric.label == "NPV" for metric in app.metric)


def test_an_edited_proposal_part_is_saved(reports_backend):
    app = _reports_page()
    _button(app, "Write the investment proposal").click().run()

    _toggle(app, "Edit", index=0).set_value(True).run()  # the executive summary
    app.text_area(key="form:session-1:2:Executive summary:overview").input("A sharper overview.")
    _button(app, "Save changes").click().run()

    assert not app.exception
    saved = reports_backend.saves[-1]
    assert saved["version"] == 2
    assert saved["proposal"]["executive"]["overview"] == "A sharper overview."
    assert saved["proposal"]["market"] == SAMPLE.market.model_dump(mode="json")
    assert any("Saved your changes" in s.value for s in app.success)


def test_the_pdf_pop_up_sends_an_instruction_to_the_team(reports_backend):
    app = _reports_page()
    _button(app, "Write the investment proposal").click().run()

    _button(app, "Open PDF").click().run()
    assert any(caption.value == "1 page" for caption in app.caption)
    app.selectbox(key="revise_part").set_value("market")
    app.text_area(key="revise_instruction").input("Add a referral channel.")
    _button(app, "Revise").click().run()

    assert not app.exception
    path, body = reports_backend.posts[-1]
    assert path == "/reports/session-1/proposal/revise"
    assert body["part"] == "market" and body["instruction"] == "Add a referral channel."
    assert body["version"] == 2
    assert any("Could not revise: Financial Plan & Projections" in w.value for w in app.warning)
    # The pop-up stays open on the new version, its instruction box cleared.
    assert app.text_area(key="revise_instruction").value == ""


def test_the_reports_page_explains_when_there_are_none(monkeypatch):
    backend = FakeReportsBackend(reports=False)
    monkeypatch.setattr(httpx, "get", backend.get)

    app = _reports_page()

    assert not app.exception
    assert any("No reports yet" in info.value for info in app.info)


def _with_proposal(app):
    _button(app, "Write the investment proposal").click().run()
    return app


def _texts(elements):
    return [element.value for element in elements]


def test_a_scenario_fills_the_request_form(backend):
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    app.selectbox(key="scenario").set_value("healthcare_scheduling").run()

    assert "follow-up appointments" in app.text_area(key="prompt").value
    assert app.text_input(key="target_market").value == "Small outpatient clinics in the US"


def test_an_empty_request_is_not_sent(backend):
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()

    _button(app, "Evaluate").click().run()

    assert backend == []
    assert any("Describe the idea" in text for text in _texts(app.warning))


def test_conflicts_and_their_decisions_are_shown(monkeypatch):
    conflict = {"raised_by": "finance", "about": "marketing", "issue": "The price is too low."}
    result = {**RESULT, "resolutions": [{"conflict": conflict, "decision": "Charge $149.",
                                         "revise": "marketing"}]}
    monkeypatch.setattr(httpx, "get", lambda url, timeout: httpx.Response(200, json=HEALTH))
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: httpx.Response(200, json=result))
    app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    app.text_area(key="prompt").input("Evaluate an AI scheduling tool.")

    _button(app, "Evaluate").click().run()

    shown = " ".join(_texts(app.markdown))
    assert "Finance vs Marketing:" in shown and "Charge \\$149." in shown


def test_the_reports_page_says_why_it_cannot_load(reports_backend):
    reports_backend.failures[("GET", "/reports")] = 503
    app = _reports_page()
    assert any("503" in text for text in _texts(app.error))

    reports_backend.failures = {("GET", "/session-1"): 500}
    app = _reports_page()
    assert any("500" in text for text in _texts(app.error))


def test_an_outdated_report_says_so(reports_backend):
    reports_backend.report["outdated"] = True

    app = _reports_page()

    assert any("newer results" in text for text in _texts(app.warning))


def test_writing_the_proposal_can_fail(reports_backend):
    reports_backend.failures[("POST", "/proposal")] = 409
    app = _with_proposal(_reports_page())
    assert any("changed elsewhere" in text for text in _texts(app.warning))

    reports_backend.failures[("POST", "/proposal")] = 502
    app = _with_proposal(_reports_page())
    assert any("502" in text for text in _texts(app.error))
    assert reports_backend.report["proposal"] is None


def test_a_failed_save_of_the_team_report_is_shown(reports_backend):
    reports_backend.failures[("PUT", "/session-1")] = 500
    app = _reports_page()
    _toggle(app, "Edit").set_value(True).run()

    app.text_area(key="report:session-1:1:strategy").input("My edit.").run()

    assert any("Not saved." in text for text in _texts(app.error))


def test_saving_a_proposal_part_can_fail(reports_backend):
    app = _with_proposal(_reports_page())
    _toggle(app, "Edit", index=0).set_value(True).run()
    reports_backend.failures[("PUT", "/proposal")] = 500

    _button(app, "Save changes").click().run()
    assert any("500" in text for text in _texts(app.error))

    reports_backend.failures = {}
    reports_backend.conflict = True
    _button(app, "Save changes").click().run()
    assert any("changed elsewhere" in text for text in _texts(app.warning))


def test_every_part_can_be_edited_and_saved_as_it_is(reports_backend):
    # The forms show text, numbers, choices, nested figures and editable tables.
    _with_proposal(_reports_page())
    for index, part in enumerate(("executive", "market", "technical", "financial", "risk", "executive")):
        app = _reports_page()
        _toggle(app, "Edit", index=index).set_value(True).run()
        assert not app.exception
        _button(app, "Save changes").click().run()
        assert not app.exception
        assert reports_backend.saves[-1]["proposal"][part] == SAMPLE.model_dump(mode="json")[part]


def test_the_pop_up_needs_an_instruction_and_reports_failures(reports_backend):
    app = _with_proposal(_reports_page())
    _button(app, "Open PDF").click().run()

    _button(app, "Revise").click().run()
    assert any("Say what to change." in text for text in _texts(app.warning))
    assert not any(path.endswith("/revise") for path, _ in reports_backend.posts)

    reports_backend.failures[("POST", "/revise")] = 502
    app.text_area(key="revise_instruction").input("Plan for a slower ramp.")
    _button(app, "Revise").click().run()
    assert any("502" in text for text in _texts(app.error))
    path, body = reports_backend.posts[-1]
    assert path.endswith("/revise") and body["part"] is None  # the whole proposal

    reports_backend.failures[("POST", "/revise")] = 409
    _button(app, "Revise").click().run()
    assert any("changed elsewhere" in text for text in _texts(app.warning))


def test_the_pop_up_for_a_team_report(reports_backend):
    app = _reports_page()
    _button(app, "Open PDF").click().run()
    assert any("Write the investment proposal to get the full document" in text
               for text in _texts(app.info))

    # Another version, so the PDF is not already cached.
    reports_backend.report["version"] = 41
    reports_backend.failures[("GET", "/pdf")] = 500
    app = _reports_page()
    _button(app, "Open PDF").click().run()
    assert any("The PDF could not be made" in text for text in _texts(app.error))


def test_rewriting_and_resetting_the_report(reports_backend):
    app = _with_proposal(_reports_page())

    _button(app, "Rewrite it").click().run()
    assert [path for path, _ in reports_backend.posts].count("/reports/session-1/proposal") == 2

    _button(app, "Reset the report").click().run()
    assert reports_backend.posts[-1][0] == "/reports/session-1/reset"
    assert any("Write the investment proposal" in text for text in _texts(app.info))

    reports_backend.failures[("POST", "/reset")] = 500
    _button(app, "Reset the report").click().run()
    assert any("500" in text for text in _texts(app.error))


def _invalid_edit():
    from ui.proposal_view import edit_form

    from tests.sample_proposal import SAMPLE

    financial = SAMPLE.financial.model_dump(mode="json")
    financial["projections"][0]["customers"] = "a dozen"
    edit_form("financial", financial, ("discount_rate",), "bad")


def test_an_invalid_edit_is_not_saved():
    app = AppTest.from_function(_invalid_edit, default_timeout=TIMEOUT).run()

    _button(app, "Save changes").click().run()

    assert any("Not saved." in text and "Customers (year end)" in text for text in _texts(app.error))


class TestApiClient:
    """The Streamlit pages' client for the API."""

    def test_an_unreachable_backend_is_named(self, monkeypatch):
        from ui import api

        def refuse(url, timeout):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "get", refuse)

        with pytest.raises(api.ApiError, match="Could not reach the backend") as raised:
            api.list_reports()
        assert raised.value.status is None
        assert api.health() is None

    def test_an_error_without_json_shows_its_text(self, monkeypatch):
        from ui import api

        monkeypatch.setattr(httpx, "get", lambda url, timeout: httpx.Response(500, text="Bad gateway"))

        with pytest.raises(api.ApiError, match="500: Bad gateway") as raised:
            api.get_report("s")
        assert raised.value.status == 500
        assert api.health() is None

    def test_the_pdf_comes_back_as_bytes(self, monkeypatch):
        from ui import api

        monkeypatch.setattr(httpx, "get", lambda url, timeout: httpx.Response(200, content=b"%PDF-1.7"))

        assert api.report_pdf("s") == b"%PDF-1.7"
