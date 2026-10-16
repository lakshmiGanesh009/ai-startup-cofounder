"""Reports page: each session's written report, edited beside a live PDF preview.

The report is kept by the API (see reports.py), so edits survive a page reload.
An edit is saved when you leave its text box, and the preview is redrawn from
the saved report. "Write the detailed version" has each agent expand its
section, which takes about a minute.
"""

import io
from datetime import datetime

import pypdfium2 as pdfium
import streamlit as st

from ui import api

# Remembers, per session, the report version this page last loaded or saved,
# and the version its text boxes were filled from.
VERSIONS = "report_versions"
FILLED_FROM = "report_filled_from"
NOTICE = "report_notice"


def _label(summary: dict) -> str:
    when = datetime.fromisoformat(summary["updated_at"]).strftime("%d %b %H:%M UTC")
    kind = "detailed" if summary["detailed"] else "as generated"
    title = summary["title"] if len(summary["title"]) <= 80 else f"{summary['title'][:77]}..."
    return f"{title} ({kind}, {when})"


@st.cache_data(max_entries=8, show_spinner=False)
def _pages(pdf: bytes) -> list[bytes]:
    """The PDF's pages as PNG images. A PDF viewer draws A4 pages at a fixed
    width and cuts them off in a narrow column; images scale to fit."""
    images = []
    for page in pdfium.PdfDocument(pdf):
        buffer = io.BytesIO()
        page.render(scale=1.5).to_pil().save(buffer, format="PNG")
        images.append(buffer.getvalue())
    return images


def _box(session_id: str, filled_from: int, key: str) -> str:
    return f"report:{session_id}:{filled_from}:{key}"


def _save(session_id: str, filled_from: int, sections: list[dict]) -> None:
    """Save every section as the text boxes now show it."""
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
                "The report changed elsewhere, so it has been reloaded and your last "
                "edit was not saved. Make it again.",
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


st.title("Reports")
st.session_state.setdefault(VERSIONS, {})
st.session_state.setdefault(FILLED_FROM, {})

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

# A report that changed outside this page (a detailed version, a reset, a newer
# evaluation) refills the text boxes; this page's own saves do not.
if st.session_state[VERSIONS].get(session_id) != report["version"]:
    st.session_state[VERSIONS][session_id] = report["version"]
    st.session_state[FILLED_FROM][session_id] = report["version"]
filled_from = st.session_state[FILLED_FROM][session_id]

if NOTICE in st.session_state:
    kind, message = st.session_state.pop(NOTICE)
    getattr(st, kind)(message)
if report["outdated"]:
    st.warning(
        "A later evaluation in this session produced newer results, which this edited "
        "report does not include. Reset it to use them; that drops your edits."
    )

state = "Detailed version" if report["detailed"] else "Version as generated"
if report["edited"]:
    state += ", edited"
st.caption(f"{state} · version {report['version']} · objective: {report['objective']}")

try:
    pdf = api.report_pdf(session_id)
except api.ApiError as error:
    pdf = None
    st.error(f"The PDF could not be made. {error}")

detail, reset, download = st.columns([2, 2, 1.4])
with detail:
    if st.button(
        "Write the detailed version",
        type="primary",
        help="Each specialist expands its section from the text as it stands now, edits "
        "included, then the Chief of Staff rewrites the strategy. About a minute.",
    ):
        with st.spinner("The specialists are expanding their sections, then the Chief of "
                        "Staff the strategy. This takes about a minute."):
            try:
                result = api.detail_report(session_id)
            except api.ApiError as error:
                st.error(str(error))
            else:
                failed = result["failed"]
                _reload(session_id, ("warning", f"Could not expand: {', '.join(failed)}. "
                                     "They keep their text.") if failed else None)
                st.rerun()
with reset:
    with st.popover("Reset to the latest results"):
        st.write("This rebuilds the report from the session's latest results and drops "
                 "your edits and the detailed version.")
        if st.button("Reset the report"):
            try:
                api.reset_report(session_id)
            except api.ApiError as error:
                st.error(str(error))
            else:
                _reload(session_id)
                st.rerun()
with download:
    if pdf:
        st.download_button(
            "Download PDF", pdf, file_name=f"launch-report-{session_id[:8]}.pdf",
            mime="application/pdf", icon=":material/download:",
        )

editor, preview = st.columns(2, gap="large")
with editor:
    st.caption("Sections are markdown. A change is saved when you click outside the box, "
               "and the preview then updates.")
    with st.container(height=900):
        for section in report["sections"]:
            body = section["body"]
            st.text_area(
                section["title"],
                value=body,
                key=_box(session_id, filled_from, section["key"]),
                height=min(520, max(160, 22 * body.count("\n") + 90)),
                on_change=_save,
                args=(session_id, filled_from, report["sections"]),
            )
with preview:
    if pdf:
        try:
            pages = _pages(pdf)
        except pdfium.PdfiumError as error:
            st.error(f"The preview could not be drawn ({error}); the download still works.")
        else:
            st.caption(f"Preview · {len(pages)} page{'' if len(pages) == 1 else 's'}")
            with st.container(height=900):
                for page in pages:
                    st.image(page, width="stretch")
