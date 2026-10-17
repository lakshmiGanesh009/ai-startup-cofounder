"""Reports page: each session's report, read on screen and edited in place.

The report is kept by the API (see reports.py), so edits survive a page reload.
Until the agents write the investment proposal, it is the team's report: the
strategy, each specialist's report and the decisions on conflicts. "Write the
investment proposal" has the agents write it up following an investment
proposal template, with charts. Each part shows which agent wrote it, and can be
edited with its "Edit" switch. "Open PDF" shows the document in a pop-up, where
the founder can ask the team to revise a part, or the whole proposal.
"""

import io
from datetime import datetime

import pypdfium2 as pdfium
import streamlit as st

from proposal import OWNERS, TITLES
from ui import api, proposal_view, reasoning
from ui.proposal_view import AGENTS, literal, prose

# Remembers, per session, the report version this page last loaded or saved,
# and the version its text boxes were filled from.
VERSIONS = "report_versions"
FILLED_FROM = "report_filled_from"
NOTICE = "report_notice"
# The session whose PDF pop-up is open; it stays open across reruns until closed.
PDF_OPEN = "report_pdf_open"
# An "Edit" switch to turn off on the next run, once its changes are saved.
CLOSE_EDIT = "report_close_edit"
CLEAR_INSTRUCTION = "report_clear_instruction"
WHOLE = "whole"


def _label(summary: dict) -> str:
    when = datetime.fromisoformat(summary["updated_at"]).strftime("%d %b %H:%M UTC")
    kind = "investment proposal" if summary["has_proposal"] else "team report"
    title = summary["title"] if len(summary["title"]) <= 80 else f"{summary['title'][:77]}..."
    return f"{title} ({kind}, {when})"


@st.cache_data(max_entries=8, show_spinner=False)
def _pdf(session_id: str, version: int) -> bytes:
    """The report's PDF; each version is fetched once."""
    return api.report_pdf(session_id)


@st.cache_data(max_entries=8, show_spinner=False)
def _pages(pdf: bytes) -> list[bytes]:
    """The PDF's pages as PNG images, which scale to the pop-up's width."""
    images = []
    for page in pdfium.PdfDocument(pdf):
        buffer = io.BytesIO()
        page.render(scale=1.6).to_pil().save(buffer, format="PNG")
        images.append(buffer.getvalue())
    return images


def _box(session_id: str, filled_from: int, key: str) -> str:
    return f"report:{session_id}:{filled_from}:{key}"


def _save(session_id: str, filled_from: int, sections: list[dict]) -> None:
    """Save every section of the team's report as the text boxes now show it."""
    edited = [
        {**section, "body": st.session_state[_box(session_id, filled_from, section["key"])]}
        for section in sections
    ]
    try:
        saved = api.save_report(session_id, st.session_state[VERSIONS][session_id], edited)
    except api.ApiError as error:
        if error.status == 409:
            st.session_state[NOTICE] = (
                "warning",
                ("The report changed elsewhere, so it has been reloaded and your last "
                 "edit was not saved. Make it again."),
            )
            st.session_state[VERSIONS].pop(session_id, None)
        else:
            st.session_state[NOTICE] = ("error", f"Not saved. {error}")
        return
    st.session_state[VERSIONS][session_id] = saved["version"]


def _reload(session_id: str, notice: tuple[str, str] | None = None) -> None:
    """Refill the text boxes from the API on the next run."""
    st.session_state[VERSIONS].pop(session_id, None)
    if notice:
        st.session_state[NOTICE] = notice


def _changed_elsewhere(session_id: str) -> None:
    _reload(session_id, ("warning", "The report changed elsewhere, so it has been reloaded. "
                         "Make the request again."))
    st.rerun()


def _write_proposal(session_id: str, version: int) -> None:
    with st.spinner("The specialists are writing their parts of the proposal, then the Chief "
                    f"of Staff the executive summary. {reasoning.wait('proposal')}"):
        try:
            api.write_proposal(session_id, version, reasoning.chosen())
        except api.ApiError as error:
            if error.status == 409:
                _changed_elsewhere(session_id)
            st.error(str(error))
            return
    _reload(session_id, ("success", "The investment proposal is written. Open the PDF to see "
                         "it as a document, and to ask the team for changes."))
    st.rerun()


def _who_revises(part: str) -> str:
    if part == WHOLE:
        return "Every agent is revising its part"
    return f"The {AGENTS[part]} is revising the {TITLES[part]} part, and the parts built on it follow"


def _revise(session_id: str, version: int) -> None:
    """The inline prompt: an instruction for one part of the proposal, or all of it."""
    if st.session_state.pop(CLEAR_INSTRUCTION, False):
        st.session_state["revise_instruction"] = ""
    with st.form("revise"):
        st.markdown("**Ask the team to revise the proposal**")
        part = st.selectbox(
            "Part", [WHOLE, *TITLES], key="revise_part",
            format_func=lambda key: "The whole proposal" if key == WHOLE
            else f"{TITLES[key]} ({AGENTS[key]})",
        )
        instruction = st.text_area(
            "What to change", key="revise_instruction", height=90,
            placeholder="Make the year-one figures more conservative and add a referral channel.",
        )
        sent = st.form_submit_button("Revise", type="primary", icon=":material/auto_awesome:")
    if not sent:
        return
    if not instruction.strip():
        st.warning("Say what to change.")
        return
    with st.spinner(f"{_who_revises(part)}. {reasoning.wait('proposal')}"):
        try:
            result = api.revise_proposal(session_id, version, instruction.strip(),
                                         None if part == WHOLE else part, reasoning.chosen())
        except api.ApiError as error:
            if error.status == 409:
                _changed_elsewhere(session_id)
            st.error(str(error))
            return
    failed = result["failed"]
    st.session_state[CLEAR_INSTRUCTION] = True
    if failed:
        _reload(session_id, ("warning", f"Could not revise: {', '.join(failed)}. They keep their text."))
    else:
        _reload(session_id, ("success", "The proposal was revised."))
    st.rerun()  # the pop-up stays open and shows the new version


def _close_pdf() -> None:
    st.session_state.pop(PDF_OPEN, None)


@st.dialog("Report PDF", width="large", on_dismiss=_close_pdf)
def _pdf_dialog(session_id: str, report: dict, notice: tuple[str, str] | None) -> None:
    if notice:
        getattr(st, notice[0])(notice[1])
    if report["proposal"]:
        _revise(session_id, report["version"])
    else:
        st.info("This is the team's report. Write the investment proposal to get the full "
                "document with charts, and to ask the team for changes here.")
    try:
        pdf = _pdf(session_id, report["version"])
    except api.ApiError as error:
        st.error(f"The PDF could not be made. {error}")
        return
    kind = "investment-proposal" if report["proposal"] else "launch-report"
    st.download_button("Download PDF", pdf, file_name=f"{kind}-{session_id[:8]}.pdf",
                       mime="application/pdf", icon=":material/download:")
    try:
        pages = _pages(pdf)
    except pdfium.PdfiumError as error:
        st.error(f"The preview could not be drawn ({error}); the download still works.")
        return
    st.caption(f"{len(pages)} page{'' if len(pages) == 1 else 's'}")
    for page in pages:
        st.image(page, width="stretch")


def _source(key: str) -> None:
    if key in ("strategy", "decisions"):
        verb = "Written" if key == "strategy" else "Decided"
        st.badge(f"{verb} by the Chief of Staff", icon=":material/smart_toy:", color="blue")
    elif key in OWNERS.values():
        part = next(part for part, owner in OWNERS.items() if owner == key)
        proposal_view.source(part)


def _team_report(session_id: str, report: dict, filled_from: int) -> None:
    """The strategy, the specialists' reports and the decisions, as text; the
    "Edit" switch turns them into text boxes, each saved when you leave it."""
    if st.toggle("Edit", key=f"team-edit:{session_id}"):
        st.caption("Sections are markdown. A change is saved when you click outside the box.")
        for section in report["sections"]:
            body = section["body"]
            st.text_area(
                section["title"], value=body, key=_box(session_id, filled_from, section["key"]),
                height=min(600, max(160, 22 * body.count("\n") + 90)),
                on_change=_save, args=(session_id, filled_from, report["sections"]),
            )
        return
    for section in report["sections"]:
        st.subheader(literal(section["title"]))
        _source(section["key"])
        st.markdown(prose(section["body"]))


def _save_part(session_id: str, report: dict, part: str, edited: dict, switch: str) -> None:
    try:
        api.save_proposal(session_id, report["version"], {**report["proposal"], part: edited})
    except api.ApiError as error:
        if error.status == 409:
            _changed_elsewhere(session_id)
        st.error(str(error))
        return
    st.session_state[CLOSE_EDIT] = switch
    _reload(session_id, ("success", f"Saved your changes to the {TITLES[part]} part."))
    st.rerun()


def _proposal(session_id: str, report: dict, filled_from: int) -> None:
    tabs = st.tabs([name for name, _, _ in proposal_view.TABS] + ["Team report"])
    for (name, part, fields), tab in zip(proposal_view.TABS, tabs):
        with tab:
            switch = f"edit:{session_id}:{name}"
            if st.toggle("Edit", key=switch):
                form = f"form:{session_id}:{report['version']}:{name}"
                edited = proposal_view.edit_form(part, report["proposal"][part], fields, form)
                if edited:
                    _save_part(session_id, report, part, edited, switch)
            else:
                proposal_view.show(name, report["proposal"], report["investment"], report["checks"])
    with tabs[-1]:
        st.caption("The reviewed reports and decisions the proposal was written from.")
        _team_report(session_id, report, filled_from)


st.title("Reports")
st.session_state.setdefault(VERSIONS, {})
st.session_state.setdefault(FILLED_FROM, {})
if CLOSE_EDIT in st.session_state:
    st.session_state[st.session_state.pop(CLOSE_EDIT)] = False

try:
    summaries = api.list_reports()
except api.ApiError as error:
    st.error(str(error))
    st.stop()
if not summaries:
    st.info("No reports yet. Run an evaluation on the Evaluate page, and its report appears here.")
    st.stop()

ids = [summary["session_id"] for summary in summaries]
labels = {summary["session_id"]: _label(summary) for summary in summaries}
if st.session_state.get("report_choice") not in ids:
    current = st.session_state.get("session_id")
    st.session_state.report_choice = current if current in ids else ids[0]
session_id = st.selectbox("Report", ids, format_func=labels.get, key="report_choice")

try:
    report = api.get_report(session_id)
except api.ApiError as error:
    st.error(str(error))
    st.stop()

# A report that changed outside this page (a proposal, a reset, a newer
# evaluation) refills the text boxes; this page's own saves do not.
if st.session_state[VERSIONS].get(session_id) != report["version"]:
    st.session_state[VERSIONS][session_id] = report["version"]
    st.session_state[FILLED_FROM][session_id] = report["version"]
filled_from = st.session_state[FILLED_FROM][session_id]

notice = st.session_state.pop(NOTICE, None)
if notice:
    getattr(st, notice[0])(notice[1])
if report["outdated"]:
    st.warning(
        "A later evaluation in this session produced newer results, which this report does "
        "not include. Reset it to use them; that drops your edits and the proposal."
    )

has_proposal = report["proposal"] is not None
badges = st.container(horizontal=True)
with badges:
    if has_proposal:
        st.badge("Investment proposal", icon=":material/request_quote:", color="green")
    else:
        st.badge("Team report", icon=":material/groups:", color="gray")
    if report["edited"]:
        st.badge("Edited", icon=":material/edit:", color="orange")
    st.caption(f"Version {report['version']} · objective: {literal(report['objective'])}")

write, open_pdf, reset = st.columns([2.2, 1.3, 2])
with write:
    if not has_proposal:
        if st.button("Write the investment proposal", type="primary", icon=":material/auto_awesome:",
                     help="The specialists write their parts of an investment proposal from the "
                     "report as it stands, edits included, and the Chief of Staff the executive "
                     "summary. Charts are drawn from their figures."):
            _write_proposal(session_id, report["version"])
    else:
        with st.popover("Rewrite the proposal", icon=":material/refresh:"):
            st.write("The agents write the proposal again from the team's report as it stands. "
                     "This replaces it, with your edits and revisions to it.")
            if st.button("Rewrite it", type="primary"):
                _write_proposal(session_id, report["version"])
with open_pdf:
    if st.button("Open PDF", icon=":material/picture_as_pdf:",
                 help="See the document as it will print, download it, and ask the team for changes."):
        st.session_state[PDF_OPEN] = session_id
with reset:
    with st.popover("Reset to the latest results", icon=":material/restart_alt:"):
        st.write("This rebuilds the report from the session's latest results and drops "
                 "your edits and the proposal.")
        if st.button("Reset the report"):
            try:
                api.reset_report(session_id)
            except api.ApiError as error:
                st.error(str(error))
            else:
                _reload(session_id)
                st.rerun()

if st.session_state.get(PDF_OPEN) == session_id:
    _pdf_dialog(session_id, report, notice)

st.divider()
if has_proposal:
    _proposal(session_id, report, filled_from)
else:
    st.info("This is the team's report. **Write the investment proposal** to have the agents "
            "turn it into a full proposal: market sizing, a competitor matrix, the roadmap, "
            "three-year projections with NPV, IRR and payback, a risk matrix and KPIs, with "
            "charts.", icon=":material/lightbulb:")
    _team_report(session_id, report, filled_from)
