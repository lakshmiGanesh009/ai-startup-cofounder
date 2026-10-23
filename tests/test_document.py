"""Tests for the founder's control of the document (currency.py, units.py,
document.py and the routes on them): amounts and measurements converted by
code, text replaced, redacted or removed, the settings, a revision of one
passage, every change a draft to preview and accept, and the versions kept."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont

import document
from currency import CURRENCIES, compact, convert_text, full, using
from guardrails import fence
from main import app
from proposal import MarketSize, Proposal, investment_metrics
from reports import KEEP_VERSIONS, DocumentSettings, Report, ReportSection, ReportStore
from tests.sample_proposal import SAMPLE
from units import convert_units

client = TestClient(app)


def _report(**changes) -> Report:
    sections = [
        ReportSection(key="strategy", title="Launch Strategy",
                      body="Charge $149/mo per clinic [finance].\n\n- A 2,000 sq ft office.\n- Hire Dana Reyes."),
        ReportSection(key="research", title="Web Research", body="Clinics spend $1.2M a year."),
    ]
    return Report(session_id="s1", title="Clinic follow-ups under $15k", objective="Decide on a <$15k launch",
                  context="", sections=sections, version=3, updated_at=datetime.now(timezone.utc),
                  proposal=SAMPLE, **changes)


# ---- Money and measurements ----

def test_amounts_are_shown_in_the_documents_currency():
    assert (full(-6000, "EUR"), full(1500, "CHF"), compact(12_500, "GBP"), compact(1_234_000, "INR")) == (
        "-€6,000", "CHF 1,500", "£12.5k", "₹1.2M")
    with using("EUR"):
        assert (full(12_000), compact(750)) == ("€12,000", "€750")
    assert full(12_000) == "$12,000"  # the default outside


def test_amounts_in_text_are_converted_where_they_are_money():
    text = ("Launch at $149/mo; build: 20 hr/wk @ $60/hr = $7,200, under a <$15k cap; TAM $4.8B; "
            "pilots $10–20k or $5 to $8 a seat; 2 million dollars raised; 1,500 USD in fees; $0.05 a call.")
    converted, count = convert_text(text, "USD", "EUR", 0.92)
    assert converted == (
        "Launch at €137/mo; build: 20 hr/wk @ €55/hr = €6,624, under a <€13.8k cap; TAM €4.4B; "
        "pilots €9.2–€18.4k or €4.60 to €7.36 a seat; 1.8 million euros raised; 1,380 EUR in fees; €0.05 a call.")
    assert count == 12


def test_other_currencies_years_and_counts_are_left_alone():
    text = "CA$500 and US$1,000 in 2026, for 20 clinics; -$6,000 net."
    assert convert_text(text, "USD", "GBP", 0.8) == ("CA$500 and £800 in 2026, for 20 clinics; -£4,800 net.", 2)


def test_relabelling_keeps_the_numbers():
    assert convert_text("A $12k budget", "USD", "INR", 1) == ("A ₹12k budget", 1)


def test_measurements_convert_both_ways_and_ambiguous_ones_stay():
    assert convert_units("A 2,000 sq ft clinic 5 miles away, 150 lb of kit at 72°F, 12 gallons.", "metric") == (
        "A 186 m² clinic 8.05 km away, 68 kg of kit at 22.2°C, 45.4 L.", 5)
    assert convert_units("5m users on a 5G network, 12 in total, a $5k budget.", "metric")[1] == 0
    assert convert_units("A 186 m² office 8 km away at 22°C, 45 litres.", "imperial") == (
        "A 2,002 sq ft office 4.97 mi away at 71.6°F, 11.9 gal.", 4)


def test_a_rate_per_unit_converts_the_other_way():
    assert convert_units("Rent 1,200 sqft @ €0.69/sqft, or $7.43 per square foot; 20 per mile.", "metric") == (
        "Rent 111 m² @ €7.43/m², or $80 per m²; 12.4 per km.", 4)
    assert convert_units("Office at €7.43/m²", "imperial") == ("Office at €0.69/sq ft", 1)


def test_the_pdf_font_draws_every_currency_symbol():
    font = TTFont(Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans.ttf")
    glyphs = font.getBestCmap()
    missing = {code: char for code, c in CURRENCIES.items() for char in c.symbol if ord(char) not in glyphs}
    assert not missing


# ---- The changes, as drafts ----

def test_a_currency_change_converts_every_figure_and_amount_and_the_metrics_follow():
    report = _report()
    draft = document.convert_currency(report, "EUR", 0.92)

    after = draft.report
    assert after.settings.currency == "EUR"
    assert after.proposal.market.tam.value == round(SAMPLE.market.tam.value * 0.92, 2)
    assert after.proposal.financial.capex[0].amount == round(SAMPLE.financial.capex[0].amount * 0.92, 2)
    assert after.proposal.financial.price_per_customer_month == round(SAMPLE.financial.price_per_customer_month * 0.92, 2)
    # Counts and rates are not money.
    assert after.proposal.financial.projections[0].customers == SAMPLE.financial.projections[0].customers
    assert after.proposal.financial.discount_rate == SAMPLE.financial.discount_rate
    assert after.investment.npv == pytest.approx(investment_metrics(SAMPLE.financial).npv * 0.92, rel=1e-3)
    assert after.title == "Clinic follow-ups under €13.8k"
    assert "$" not in after.sections[0].body and "€137/mo" in after.sections[0].body
    assert draft.summary.startswith("Converted 22 figures and ") and "from USD to EUR at 1 USD = 0.92 EUR" in draft.summary
    # Nothing is saved, and the original is untouched.
    assert report.settings.currency == "USD" and report.proposal == SAMPLE
    assert draft.base_version == 3


def test_relabelling_changes_the_currency_but_not_the_figures():
    draft = document.convert_currency(_report(), "GBP", 0.79, relabel=True)
    after = draft.report.proposal
    assert after.financial == SAMPLE.financial.model_copy(update={"assumptions": after.financial.assumptions})
    assert after.market.tam.value == SAMPLE.market.tam.value
    assert draft.report.settings.currency == "GBP"
    assert "£149/mo" in draft.report.sections[0].body
    assert draft.summary.startswith("Relabelled")


def test_a_change_that_changes_nothing_says_why():
    with pytest.raises(document.Unchanged, match="already in USD"):
        document.convert_currency(_report(), "USD", 1)
    with pytest.raises(document.Unchanged, match="no measurement"):
        document.convert_units(_report(), "imperial")
    with pytest.raises(document.Unchanged, match="does not appear"):
        document.replace(_report(), "Zebra", "Horse")


def test_each_change_is_listed_where_it_is():
    draft = document.convert_units(_report(), "metric")
    assert [(c.label, c.before, c.after) for c in draft.changes] == [
        ("Team report · Launch Strategy", _report().sections[0].body, _report().sections[0].body.replace("2,000 sq ft", "186 m²")),
        ("Settings · Units", None, "metric"),
    ]
    capex = document.convert_currency(_report(), "EUR", 0.92).changes
    labels = {c.label for c in capex}
    assert f"Financial plan · CapEx · {SAMPLE.financial.capex[0].item} · Amount" in labels
    assert "Market & marketing · TAM · Value" in labels
    assert all(c.money for c in capex if c.path.startswith("proposal.financial.capex"))
    assert not any(c.money for c in capex if c.path.startswith(("sections", "title", "settings")))


def test_text_is_replaced_and_redacted_everywhere_but_choices_are_not():
    whole = document.replace(_report(), "clinic", "practice")
    assert "per practice" in whole.report.sections[0].body
    assert "5 clinics" in whole.report.proposal.executive.recommendation  # a whole word only
    replaced = document.replace(_report(), "clinic", "practice", whole_words=False)
    assert "5 practices" in replaced.report.proposal.executive.recommendation
    assert replaced.report.proposal.executive.verdict == SAMPLE.executive.verdict

    redacted = document.redact(_report(), ["Dana Reyes", "$149/mo"])
    body = redacted.report.sections[0].body
    assert "Dana Reyes" not in body and "██████████" in body and "$149/mo" not in body
    assert redacted.summary == "Redacted 2 occurrences of 2 terms."


def test_a_passage_is_removed_with_its_line():
    draft = document.remove_passage(_report(), "sections.strategy", "Hire Dana Reyes.")
    assert draft.report.sections[0].body == "Charge $149/mo per clinic [finance].\n\n- A 2,000 sq ft office."
    with pytest.raises(document.Unchanged, match="no longer"):
        document.remove_passage(_report(), "sections.strategy", "Not there.")


def test_settings_say_who_it_is_from_and_what_is_left_out():
    draft = document.settings(_report(), DocumentSettings(prepared_by="Acme Ventures", hidden=["research"]))
    assert draft.summary == "The document is now prepared by Acme Ventures and leaves out Web Research."
    assert draft.report.settings.currency == "USD"


def test_a_field_is_read_and_set_by_its_path():
    report = _report()
    assert document.text_at(report, "proposal.market.pricing_strategy") == SAMPLE.market.pricing_strategy
    changed = document.set_text(report, "proposal.risk.risks.0.mitigation", "Sign a BAA first.")
    assert changed.proposal.risk.risks[0].mitigation == "Sign a BAA first."
    with pytest.raises(KeyError):
        document.text_at(report, "proposal.market.nothing")


def test_reports_saved_before_the_currency_setting_still_load():
    old = SAMPLE.model_dump(mode="json")
    old["market"]["tam"] = {"value_usd": 5.0, "basis": "x"}
    old["financial"]["capex"] = [{"item": "Build", "amount_usd": 100.0}]
    proposal = Proposal.model_validate(old)
    assert proposal.market.tam.value == 5.0 and proposal.financial.capex[0].amount == 100.0
    assert Report.model_validate({**_report().model_dump(exclude={"settings", "change"})}).settings.currency == "USD"
    assert MarketSize(value=7, basis="y").model_dump() == {"value": 7.0, "basis": "y"}


# ---- Through the API ----

def _session(fake_llm) -> tuple[str, int]:
    session = client.post("/evaluate", json={"prompt": "Evaluate a clinic follow-up tool for $15k."}).json()["session_id"]
    version = client.get(f"/reports/{session}").json()["version"]
    written = client.post(f"/reports/{session}/proposal", json={"version": version})
    assert written.status_code == 200, written.text
    return session, written.json()["report"]["version"]


def _accept(session: str, draft: dict):
    content = {key: draft["report"][key] for key in ("title", "objective", "sections", "proposal", "settings")}
    return client.post(f"/reports/{session}/accept",
                       json={"version": draft["base_version"], "content": content, "change": draft["summary"]})


def test_a_draft_is_saved_only_when_accepted_and_the_old_version_is_kept(fake_llm):
    session, version = _session(fake_llm)
    made = client.post(f"/reports/{session}/drafts",
                       json={"version": version, "change": {"kind": "currency", "to": "EUR", "rate": 0.92}})
    assert made.status_code == 200, made.text
    draft = made.json()
    assert draft["report"]["settings"]["currency"] == "EUR" and draft["changes"]
    assert client.get(f"/reports/{session}").json()["version"] == version  # nothing saved yet

    saved = _accept(session, draft).json()
    assert saved["version"] == version + 1 and saved["settings"]["currency"] == "EUR"
    assert saved["change"] == draft["summary"] and saved["edited"]
    assert saved["investment"]["npv"] == pytest.approx(draft["report"]["investment"]["npv"])

    versions = client.get(f"/reports/{session}/versions").json()
    assert [(v["version"], v["current"]) for v in versions[:2]] == [(version + 1, True), (version, False)]
    assert versions[1]["change"] == "The agents wrote the investment proposal in USD"
    assert client.get(f"/reports/{session}/versions/{version}").json()["settings"]["currency"] == "USD"


def test_each_version_says_what_changed_since_the_one_before(fake_llm):
    session, version = _session(fake_llm)
    draft = client.post(f"/reports/{session}/drafts",
                        json={"version": version, "change": {"kind": "currency", "to": "EUR", "rate": 0.92}}).json()
    assert _accept(session, draft).status_code == 200

    newest, written, *_, first = client.get(f"/reports/{session}/versions").json()
    # The list says how many fields each version changed, and where.
    assert newest["changed"] == len(draft["changes"])
    assert "Currency" in newest["areas"] and "Financial plan" in newest["areas"]
    assert written["changed"] > 0 and written["areas"][:2] == ["Executive summary", "Market & marketing"]
    assert first["version"] == 1 and first["changed"] is None and first["areas"] == []

    # And each change field by field: what the draft showed, with each amount's currency.
    changes = client.get(f"/reports/{session}/versions/{version + 1}/changes").json()
    assert changes == {"version": version + 1, "since": version, "currency_before": "USD", "currency": "EUR",
                       "changes": draft["changes"]}
    assert client.get(f"/reports/{session}/versions/1/changes").json()["since"] is None
    assert client.get(f"/reports/{session}/versions/1/changes").json()["changes"] == []
    assert client.get(f"/reports/{session}/versions/99/changes").status_code == 404


def test_a_stale_draft_is_refused_and_a_version_restored(fake_llm):
    session, version = _session(fake_llm)
    first = client.post(f"/reports/{session}/drafts", json={
        "version": version, "change": {"kind": "replace", "find": "clinic", "by": "practice"}}).json()
    second = client.post(f"/reports/{session}/drafts", json={
        "version": version, "change": {"kind": "redact", "terms": ["clinic"]}}).json()
    assert _accept(session, first).status_code == 200
    assert _accept(session, second).status_code == 409  # made from a version that is gone

    restored = client.post(f"/reports/{session}/versions/{version}/restore", json={"version": version + 1})
    assert restored.status_code == 200
    assert restored.json()["version"] == version + 2 and restored.json()["change"] == f"Restored version {version}"
    assert restored.json()["proposal"] == client.get(f"/reports/{session}/versions/{version}").json()["proposal"]


def test_a_draft_explains_a_change_it_cannot_make(fake_llm):
    session, version = _session(fake_llm)
    for change, words in [
        ({"kind": "currency", "to": "USD", "rate": 1}, "already in USD"),
        ({"kind": "currency", "to": "XYZ", "rate": 1}, "not a currency"),
        ({"kind": "remove", "path": "proposal.market.nothing", "passage": "x"}, "no such text"),
    ]:
        response = client.post(f"/reports/{session}/drafts", json={"version": version, "change": change})
        assert response.status_code in (404, 422) and words in response.json()["detail"], response.text
    stale = client.post(f"/reports/{session}/drafts",
                        json={"version": version - 1, "change": {"kind": "units", "to": "metric"}})
    assert stale.status_code == 409


def test_one_passage_is_revised_by_its_writer_and_the_rest_left_alone(fake_llm):
    session, version = _session(fake_llm)
    passage = SAMPLE.market.pricing_strategy.split("\n")[0]
    response = client.post(f"/reports/{session}/revise", json={
        "version": version, "path": "proposal.market.pricing_strategy", "passage": passage,
        "instruction": "Make it shorter."})
    assert response.status_code == 200, response.text
    draft = response.json()["draft"]

    prompt = fake_llm.rewrite_prompts[-1]
    assert "The part to revise is Market & marketing · Pricing strategy." in prompt
    assert "Rewrite only this passage of it" in prompt and fence(passage, "the team report") in prompt
    assert fence("Make it shorter.", "founder") in prompt
    assert [c["path"] for c in draft["changes"]] == ["proposal.market.pricing_strategy"]
    assert draft["report"]["proposal"]["market"]["pricing_strategy"] == SAMPLE.market.pricing_strategy.replace(
        passage, "A sharper passage.", 1)
    assert client.get(f"/reports/{session}").json()["version"] == version


def test_a_passage_that_moved_or_a_text_that_is_not_there_is_refused(fake_llm):
    session, version = _session(fake_llm)
    gone = client.post(f"/reports/{session}/revise", json={
        "version": version, "path": "proposal.market.pricing_strategy", "passage": "Not in it.", "instruction": "x"})
    assert gone.status_code == 409
    nowhere = client.post(f"/reports/{session}/revise", json={
        "version": version, "path": "proposal.market.nothing", "instruction": "x"})
    assert nowhere.status_code == 404
    odd = client.post(f"/reports/{session}/revise", json={"version": version, "path": "../x", "instruction": "x"})
    assert odd.status_code == 422


def test_a_proposal_is_written_in_the_currency_asked_for(fake_llm):
    session = client.post("/evaluate", json={"prompt": "Evaluate a bakery app."}).json()["session_id"]
    version = client.get(f"/reports/{session}").json()["version"]
    written = client.post(f"/reports/{session}/proposal", json={"version": version, "currency": "EUR"}).json()
    assert written["report"]["settings"]["currency"] == "EUR"
    assert written["report"]["checks"] == [] or all("€" in check for check in written["report"]["checks"])


def test_the_agents_are_told_the_currency_and_never_to_convert_it():
    from agents.proposal_writer import _system

    with using("EUR"):
        prompt = _system("financial")
    assert "Every amount in this document is in EUR (euro)" in prompt and "'€'" in prompt
    assert "Never convert between currencies" in prompt


def test_the_preview_pdf_is_made_from_a_draft_without_saving_it(fake_llm):
    session, version = _session(fake_llm)
    draft = client.post(f"/reports/{session}/drafts", json={
        "version": version, "change": {"kind": "currency", "to": "INR", "rate": 83}}).json()
    content = {key: draft["report"][key] for key in ("title", "objective", "sections", "proposal", "settings")}
    pdf = client.post(f"/reports/{session}/pdf", json=content)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/reports/{session}").json()["version"] == version


def test_only_the_latest_versions_are_kept():
    store = ReportStore()
    from reports import SessionResults

    results = SessionResults(venture="v", objective="o", context="", final_strategy="s", analyses={}, resolutions=[])
    store.record("s1", results)
    for _ in range(KEEP_VERSIONS + 5):
        report = store.get("s1")
        store.save("s1", report.version, report.sections)
    assert len(store.versions("s1")) == KEEP_VERSIONS + 1
