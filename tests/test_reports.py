"""Tests for the written reports: the store, the investment proposal and the PDF."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from llm import CHIEF, SPECIALIST
from main import app
from proposal import investment_metrics
from report_pdf import render_pdf
from reports import Report, ReportChanged, ReportSection, ReportStore, SessionResults
from state import Conflict, DelegationPlan, Resolution, SpecialistCritique, Task
from tests.sample_proposal import SAMPLE

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
    assert report["version"] == 1 and not report["edited"]
    assert report["proposal"] is None and report["investment"] is None
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


def _write(session_id: str, **body) -> dict:
    version = client.get(f"/reports/{session_id}").json()["version"]
    response = client.post(f"/reports/{session_id}/proposal", json={"version": version, **body})
    assert response.status_code == 200, response.text
    return response.json()


def _revise(session_id: str, instruction: str, part=None):
    version = client.get(f"/reports/{session_id}").json()["version"]
    return client.post(
        f"/reports/{session_id}/proposal/revise",
        json={"version": version, "instruction": instruction, "part": part},
    )


def test_the_agents_write_the_proposal_from_the_report_as_it_stands(fake_llm):
    session_id = _evaluate()
    report = client.get(f"/reports/{session_id}").json()
    _sections(report)["finance"]["body"] = "Charge $149 a month."
    client.put(f"/reports/{session_id}", json=report)

    result = _write(session_id)

    assert result["failed"] == []
    written = result["report"]
    assert written["proposal"] == SAMPLE.model_dump(mode="json")
    assert written["investment"]["npv_usd"] == investment_metrics(SAMPLE.financial).npv_usd
    summary = next(s for s in client.get("/reports").json() if s["session_id"] == session_id)
    assert summary["has_proposal"]
    prompts = fake_llm.part_prompts
    assert set(prompts) == {"market", "technical", "risk", "financial", "executive"}
    # Every part is written from the report as edited, with the venture as background.
    for (prompt,) in prompts.values():
        assert "Charge $149 a month." in prompt
        assert "Startup request:\nEvaluate an AI scheduling tool." in prompt
    # Finance works from the market and technical parts; the Chief of Staff from
    # all four and the metrics calculated from Finance's figures.
    assert "## Market & Marketing Strategy" in prompts["financial"][0]
    assert "## Technical & Operational Architecture" in prompts["financial"][0]
    assert "## Security, Compliance & Risk" not in prompts["financial"][0]
    # The costs the other parts commit to are summed for Finance to cover.
    assert "The channels in the market part cost $500 a month in all" in prompts["financial"][0]
    assert "The staffing in the technical part is 1.5 FTE" in prompts["financial"][0]
    assert "## Security, Compliance & Risk" in prompts["executive"][0]
    assert "Investment metrics, calculated from the financial plan" in prompts["executive"][0]
    roles = {what: role for role, what in fake_llm.calls if what in ("ExecutivePlan", "MarketPlan")}
    assert roles == {"ExecutivePlan": CHIEF, "MarketPlan": SPECIALIST}


def test_finance_corrects_figures_that_fail_a_check_once(fake_llm):
    years = SAMPLE.financial.years
    low = [years[0].model_copy(update={"fixed_costs_month_usd": 100.0}), *years[1:]]
    fake_llm.proposal = SAMPLE.model_copy(
        update={"financial": SAMPLE.financial.model_copy(update={"projections": low})}
    )
    session_id = _evaluate()

    report = _write(session_id)["report"]

    first, correction = fake_llm.part_prompts["financial"]
    assert "Your figures fail these checks" not in first
    assert "Your figures fail these checks, calculated from them:\n- Year 1's fixed costs" in correction
    # The fake model makes the same mistake again, so the check is left for the
    # founder to see, and the Chief of Staff is told about it.
    assert report["checks"] == ["Year 1's fixed costs ($100 a month) are below the monthly "
                                "OpEx at launch ($850)."]
    assert "Checks on the financial figures that still fail" in fake_llm.part_prompts["executive"][0]


def test_revising_a_part_brings_the_parts_built_on_it_into_line(fake_llm):
    session_id = _evaluate()
    _write(session_id)
    fake_llm.part_prompts.clear()

    response = _revise(session_id, "Add a referral channel.", part="market")

    assert response.status_code == 200
    prompts = fake_llm.part_prompts
    assert set(prompts) == {"market", "financial", "executive"}
    assert "The founder asks for this change:\nAdd a referral channel." in prompts["market"][0]
    assert "Your part as it stands:" in prompts["market"][0]
    assert "Add a referral channel." not in prompts["financial"][0]
    assert "These parts were just revised: Market & Marketing Strategy." in prompts["financial"][0]
    assert response.json()["report"]["version"] == client.get(f"/reports/{session_id}").json()["version"]


def test_an_instruction_for_the_whole_proposal_goes_to_every_part(fake_llm):
    session_id = _evaluate()
    _write(session_id)
    fake_llm.part_prompts.clear()

    assert _revise(session_id, "Plan for a slower ramp.").status_code == 200

    assert set(fake_llm.part_prompts) == {"market", "technical", "risk", "financial", "executive"}
    for (prompt,) in fake_llm.part_prompts.values():
        assert "Plan for a slower ramp." in prompt


def test_a_part_that_cannot_be_revised_keeps_its_text(fake_llm):
    session_id = _evaluate()
    _write(session_id)
    fake_llm.fail_parts = {"financial"}

    response = _revise(session_id, "Cut the marketing budget.", part="market")

    assert response.status_code == 200
    assert response.json()["failed"] == ["Financial Plan & Projections"]
    assert response.json()["report"]["proposal"]["financial"] == SAMPLE.financial.model_dump(mode="json")


def test_a_new_proposal_with_a_part_missing_is_not_saved(fake_llm):
    session_id = _evaluate()
    fake_llm.fail_parts = {"risk"}
    version = client.get(f"/reports/{session_id}").json()["version"]

    response = client.post(f"/reports/{session_id}/proposal", json={"version": version})

    assert response.status_code == 502
    assert "Security, Compliance & Risk" in response.json()["detail"]
    assert client.get(f"/reports/{session_id}").json()["proposal"] is None


def test_proposal_requests_are_checked_against_the_report(fake_llm):
    session_id = _evaluate()
    version = client.get(f"/reports/{session_id}").json()["version"]

    assert _revise(session_id, "Anything.").status_code == 404  # no proposal yet
    stale = client.post(f"/reports/{session_id}/proposal", json={"version": version - 1})
    assert stale.status_code == 409
    _write(session_id)
    assert _revise(session_id, "").status_code == 422
    assert _revise(session_id, "Anything.", part="legal").status_code == 422


def test_an_edited_proposal_is_saved(fake_llm):
    session_id = _evaluate()
    report = _write(session_id)["report"]
    proposal = report["proposal"]
    proposal["financial"]["discount_rate"] = 0.15

    saved = client.put(f"/reports/{session_id}/proposal",
                       json={"version": report["version"], "proposal": proposal})

    assert saved.status_code == 200
    assert saved.json()["edited"] and saved.json()["version"] == report["version"] + 1
    assert saved.json()["investment"]["npv_usd"] != report["investment"]["npv_usd"]
    proposal["financial"]["projections"] = "three years"
    invalid = client.put(f"/reports/{session_id}/proposal",
                         json={"version": saved.json()["version"], "proposal": proposal})
    assert invalid.status_code == 422


def test_a_newer_evaluation_keeps_the_proposal_but_marks_it_outdated(fake_llm):
    session_id = _evaluate()
    _write(session_id)

    _evaluate("Refine the pricing.", session_id)

    report = client.get(f"/reports/{session_id}").json()
    assert report["outdated"] and report["proposal"] is not None
    reset = client.post(f"/reports/{session_id}/reset").json()
    assert reset["proposal"] is None and not reset["outdated"]


def test_the_pdf_is_served(fake_llm):
    session_id = _evaluate()

    response = client.get(f"/reports/{session_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert f'filename="launch-report-{session_id[:8]}.pdf"' in response.headers["content-disposition"]
    _write(session_id)
    proposal_pdf = client.get(f"/reports/{session_id}/pdf")
    assert proposal_pdf.content.startswith(b"%PDF")
    assert "investment-proposal-" in proposal_pdf.headers["content-disposition"]


@pytest.mark.parametrize("path", ["", "/pdf", "/proposal", "/proposal/revise", "/reset"])
def test_an_unknown_session_has_no_report(path):
    body = {"version": 1, "instruction": "Anything."}
    if path == "/reset":
        response = client.post(f"/reports/no-such-session{path}")
    elif path.startswith("/proposal"):
        response = client.post(f"/reports/no-such-session{path}", json=body)
    else:
        response = client.get(f"/reports/no-such-session{path}")

    assert response.status_code == 404


def test_a_proposal_written_meanwhile_does_not_overwrite_a_newer_edit():
    store = ReportStore()
    store.record("s", SessionResults(
        venture="Idea", objective="Goal", context="", final_strategy="Plan",
        analyses={"finance": "Price"}, resolutions=[],
    ))
    started_from = store.get("s").version
    store.save("s", started_from, [ReportSection(key="strategy", title="T", body="Edited")])

    with pytest.raises(ReportChanged):
        store.save_proposal("s", started_from, SAMPLE, edited=False)


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


def _proposal_report(**changes) -> Report:
    financial = SAMPLE.financial.model_copy(update=changes)
    proposal = SAMPLE.model_copy(update={"financial": financial})
    return Report(
        session_id="abc", title="Idea", objective="Goal", context="",
        sections=[ReportSection(key="strategy", title="Launch Strategy", body="Plan")],
        version=1, updated_at=datetime.now(timezone.utc), proposal=proposal,
    )


def test_the_proposal_pdf_draws_charts_for_any_figures():
    # Figures that turn every chart negative or empty must still draw.
    loss = [p.model_copy(update={"average_customers": 0.0, "fixed_costs_month_usd": 5_000.0})
            for p in SAMPLE.financial.projections]
    reports = [
        _proposal_report(),
        _proposal_report(projections=loss, variable_cost_per_customer_month_usd=500.0),
        _proposal_report(capex=[], monthly_opex=[]),
        _proposal_report(projections=[]),
        _proposal_report(projections=SAMPLE.financial.projections * 2),
    ]

    for report in reports:
        assert render_pdf(report).startswith(b"%PDF")


def test_the_chief_of_staff_is_told_to_face_weak_returns():
    from agents.proposal_writer import metrics_text

    loss = [p.model_copy(update={"average_customers": 0.0}) for p in SAMPLE.financial.projections]
    weak = metrics_text(SAMPLE.financial.model_copy(update={"projections": loss}))

    assert "Note: the NPV is negative" in weak
    assert "not paid back within three years" in weak
    assert investment_metrics(SAMPLE.financial).npv_usd > 0
    assert "Note:" not in metrics_text(SAMPLE.financial)


def test_revising_the_risks_leaves_the_financial_plan_alone(fake_llm):
    session_id = _evaluate()
    _write(session_id)
    fake_llm.part_prompts.clear()

    assert _revise(session_id, "Add a key-person risk.", part="risk").status_code == 200

    # Finance does not build on the risk part, so its wave is skipped.
    assert set(fake_llm.part_prompts) == {"risk", "executive"}


def test_a_revision_where_every_call_fails_changes_nothing(fake_llm):
    session_id = _evaluate()
    version = _write(session_id)["report"]["version"]
    fake_llm.fail_parts = {"risk", "executive"}

    response = _revise(session_id, "Add a key-person risk.", part="risk")

    assert response.status_code == 502
    assert "every LLM call failed" in response.json()["detail"]
    assert client.get(f"/reports/{session_id}").json()["version"] == version


def test_a_proposal_needs_a_configured_model():
    from reports import store

    store.record("unconfigured", SessionResults(
        venture="Idea", objective="Goal", context="", final_strategy="Plan",
        analyses={"finance": "Price"}, resolutions=[],
    ))

    response = client.post("/reports/unconfigured/proposal", json={"version": 1})

    assert response.status_code == 503
    assert "No LLM provider configured" in response.json()["detail"]
