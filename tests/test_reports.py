"""Tests for the written reports: the store, the detailed version and the PDF."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from main import app
from report_pdf import render_pdf
from reports import Report, ReportChanged, ReportSection, ReportStore, SessionResults
from state import Conflict, DelegationPlan, Resolution, SpecialistCritique, Task

client = TestClient(app)

CONFLICT = Conflict(raised_by="finance", about="marketing", issue="The pilot price is too low.")


def _evaluate(prompt="Evaluate an AI scheduling tool.", session_id=None) -> str:
    body = {"prompt": prompt, "context": {"target_market": "Small clinics"}}
    if session_id:
        body["session_id"] = session_id
    response = client.post("/evaluate", json=body)
    assert response.status_code == 200
    return response.json()["session_id"]


def _sections(report: dict) -> dict[str, dict]:
    return {section["key"]: section for section in report["sections"]}


def test_an_evaluation_records_a_report(fake_llm):
    fake_llm.critique = SpecialistCritique(conflicts=[CONFLICT])
    fake_llm.resolution = Resolution(conflict=CONFLICT, decision="Price at $149.", revise="")
    session_id = _evaluate()

    assert session_id in [summary["session_id"] for summary in client.get("/reports").json()]
    report = client.get(f"/reports/{session_id}").json()
    assert report["title"] == "Evaluate an AI scheduling tool."
    assert report["context"] == "Target market: Small clinics"
    assert report["version"] == 1 and not report["edited"] and not report["detailed"]
    sections = _sections(report)
    assert list(sections) == ["strategy", "marketing", "finance", "technical", "risk", "decisions"]
    assert sections["finance"]["title"] == "Financial Planning"
    assert sections["decisions"]["body"] == (
        "- **Financial Planning vs Marketing Strategy:** The pilot price is too low. "
        "**Decision:** Price at $149."
    )


def test_edits_are_saved_and_a_stale_save_is_refused(fake_llm):
    session_id = _evaluate()
    report = client.get(f"/reports/{session_id}").json()
    report["sections"][0]["body"] = "Our edited strategy."

    saved = client.put(f"/reports/{session_id}", json=report)

    assert saved.status_code == 200
    assert saved.json()["version"] == 2 and saved.json()["edited"]
    assert client.get(f"/reports/{session_id}").json()["sections"][0]["body"] == "Our edited strategy."
    # Saving again from version 1 would overwrite the edit just made.
    stale = client.put(f"/reports/{session_id}", json=report)
    assert stale.status_code == 409


def test_a_follow_up_refreshes_an_untouched_report_but_keeps_an_edited_one(fake_llm):
    session_id = _evaluate()
    fake_llm.plan = DelegationPlan(
        objective="Refine the pricing.", tasks=[Task(specialist="finance", task="Reprice.")]
    )
    _evaluate("Refine the pricing.", session_id)
    refreshed = client.get(f"/reports/{session_id}").json()
    assert refreshed["version"] == 2 and refreshed["objective"] == "Refine the pricing."

    refreshed["sections"][0]["body"] = "Edited."
    client.put(f"/reports/{session_id}", json=refreshed)
    _evaluate("Refine the pricing again.", session_id)
    kept = client.get(f"/reports/{session_id}").json()
    assert kept["outdated"] and kept["sections"][0]["body"] == "Edited."

    reset = client.post(f"/reports/{session_id}/reset").json()
    assert not reset["outdated"] and not reset["edited"]
    assert reset["sections"][0]["body"] != "Edited."


def test_the_detailed_version_expands_each_section_from_its_current_text(fake_llm):
    session_id = _evaluate()
    report = client.get(f"/reports/{session_id}").json()
    _sections(report)["finance"]["body"] = "Charge $149 a month."
    client.put(f"/reports/{session_id}", json=report)
    calls_before = dict(fake_llm.specialist_calls)

    response = client.post(f"/reports/{session_id}/detailed")

    assert response.status_code == 200
    detailed = response.json()
    assert detailed["failed"] == []
    assert detailed["report"]["detailed"]
    sections = _sections(detailed["report"])
    # The fake model echoes its prompt: finance expanded its edited text,
    # with the venture as background, and the strategy saw the expansions.
    assert "Your report:\nCharge $149 a month." in sections["finance"]["body"]
    assert "Startup request:\nEvaluate an AI scheduling tool." in sections["finance"]["body"]
    assert "The specialists' detailed sections:" in sections["strategy"]["body"]
    for name in ("marketing", "finance", "technical", "risk"):
        assert fake_llm.specialist_calls[name] == calls_before[name] + 1


def test_a_section_that_cannot_be_expanded_keeps_its_text(fake_llm):
    session_id = _evaluate()
    finance_before = _sections(client.get(f"/reports/{session_id}").json())["finance"]["body"]
    fake_llm.fail = {"finance"}

    detailed = client.post(f"/reports/{session_id}/detailed").json()

    assert detailed["failed"] == ["Financial Planning"]
    sections = _sections(detailed["report"])
    assert sections["finance"]["body"] == finance_before
    assert "Your report:" in sections["marketing"]["body"]


def test_the_pdf_is_served(fake_llm):
    session_id = _evaluate()

    response = client.get(f"/reports/{session_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert f'filename="launch-report-{session_id[:8]}.pdf"' in response.headers["content-disposition"]


@pytest.mark.parametrize("path", ["", "/pdf", "/detailed", "/reset"])
def test_an_unknown_session_has_no_report(path):
    method = client.post if path in ("/detailed", "/reset") else client.get

    assert method(f"/reports/no-such-session{path}").status_code == 404


def test_a_detailed_version_does_not_overwrite_a_newer_edit():
    store = ReportStore()
    store.record("s", SessionResults(
        venture="Idea", objective="Goal", context="", final_strategy="Plan",
        analyses={"finance": "Price"}, resolutions=[],
    ))
    started_from = store.get("s").version
    store.save("s", started_from, [ReportSection(key="strategy", title="T", body="Edited")])

    with pytest.raises(ReportChanged):
        store.apply_detailed("s", started_from, {"strategy": "Detailed"})


def test_the_pdf_renders_what_the_agents_write():
    # Characters the PDF core fonts lack, nested lists, a table, code, raw HTML
    # and an image link: all must render without loading anything.
    body = (
        "# Pricing\nCharge **$149/month** ≈ $1.8k/yr; pilot ≤ $5k → “warm” leads — ✓ ✅\n\n"
        "1. Legal\n   - nested `x ≈ 1`\n\n| Option | Price |\n| --- | --- |\n| Flat | $149 |\n\n"
        "```\ncode ≈ block\n```\n\n<img src='http://169.254.169.254/'> ![x](http://example.com/x.png)"
    )
    report = Report(
        session_id="abc", title="Idea ≈", objective="Goal", context="Target market: Clinics",
        sections=[ReportSection(key="strategy", title="Launch Strategy", body=body)],
        version=1, updated_at=datetime.now(timezone.utc),
    )

    assert render_pdf(report).startswith(b"%PDF")
