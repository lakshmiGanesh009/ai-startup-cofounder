"""Render a session's report as a PDF.

Each section is markdown, as the agents write it. markdown-it turns it into HTML
and fpdf2 lays that out in the bundled DejaVu Sans font (assets/fonts), because
the PDF core fonts cannot show characters the agents use all the time, such as
≈, ≤, → or curly quotes. Raw HTML in a section is printed as text and images are
not loaded, so nothing in a report can make the server fetch a URL.
"""

from html import escape
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace, TextStyle
from markdown_it import MarkdownIt

from reports import Report

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT = "DejaVu"
_FONT_FILES = {
    "": "DejaVuSans.ttf",
    "B": "DejaVuSans-Bold.ttf",
    "I": "DejaVuSans-Oblique.ttf",
    "BI": "DejaVuSans-BoldOblique.ttf",
}
_INK = "#1f2937"
_MUTED = "#6b7280"
_ACCENT = "#1d4ed8"

# The agents often put a heading or a point on its own line without a blank line
# before the next; "breaks" keeps those lines apart, as the editor shows them.
_markdown = (
    MarkdownIt("commonmark", {"html": False, "breaks": True})
    .enable(["table", "strikethrough"])
    .disable("image")
)


def _heading(size: float, top: float) -> TextStyle:
    # fpdf2 multiplies a heading's bottom margin by its font size.
    return TextStyle(font_family=_FONT, font_style="B", font_size_pt=size, color=_INK,
                     t_margin=top, b_margin=0.25)


_HTML_OPTIONS = {
    "font_family": _FONT,
    "ul_bullet_char": "•",
    "li_prefix_color": _ACCENT,
    "tag_styles": {
        # Section titles are h1; the agents' own headings are moved down a level.
        "h1": _heading(17, 0),
        "h2": _heading(13, 5),
        "h3": _heading(11.5, 4),
        "h4": _heading(10.5, 3),
        "h5": _heading(10, 3),
        "h6": _heading(10, 3),
        # The default code font, Courier, cannot show characters such as ≈ or →.
        "code": FontFace(family=_FONT, color=_INK),
        "pre": TextStyle(font_family=_FONT, t_margin=2),
        "blockquote": TextStyle(color=_MUTED, t_margin=2, l_margin=6, b_margin=2),
        "a": FontFace(color=_ACCENT, emphasis="UNDERLINE"),
    },
}


class _ReportPDF(FPDF):
    def __init__(self, footer_text: str):
        super().__init__(format="A4")
        self.footer_text = footer_text
        for style, name in _FONT_FILES.items():
            self.add_font(_FONT, style, FONT_DIR / name)
        self.set_margins(20, 18, 20)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_font(_FONT, size=10)

    def footer(self):
        self.set_y(-12)
        self.set_font(_FONT, size=8)
        self.set_text_color(_MUTED)
        self.cell(0, 5, f"{self.footer_text}  ·  page {self.page_no()} of {{nb}}", align="C")
        self.set_text_color(0)


def _section_html(body: str) -> str:
    tokens = _markdown.parse(body)
    for token in tokens:
        if token.type in ("heading_open", "heading_close"):
            token.tag = f"h{min(int(token.tag[1]) + 1, 6)}"
    return _markdown.renderer.render(tokens, _markdown.options, {})


def _cover_html(report: Report) -> str:
    lines = [
        '<h1>Launch Report</h1>',
        f"<p><b>Idea:</b> {escape(report.title)}</p>",
        f"<p><b>Objective:</b> {escape(report.objective)}</p>",
    ]
    for line in report.context.splitlines():
        label, _, value = line.partition(": ")
        lines.append(f"<p><b>{escape(label)}:</b> {escape(value)}</p>")
    version = "Detailed version" if report.detailed else "Version as generated"
    if report.edited:
        version += ", edited"
    lines.append(
        f'<p><font color="{_MUTED}">{version} · {report.updated_at:%d %b %Y, %H:%M} UTC · '
        f"session {escape(report.session_id[:8])}</font></p><hr>"
    )
    return "".join(lines)


def render_pdf(report: Report) -> bytes:
    """The report as PDF bytes: a cover block and the strategy on page one,
    then each other section on a page of its own."""
    title = report.title if len(report.title) <= 70 else f"{report.title[:67]}..."
    pdf = _ReportPDF(title)
    pdf.add_page()
    pdf.write_html(_cover_html(report), **_HTML_OPTIONS)
    for number, section in enumerate(report.sections):
        if number:
            pdf.add_page()
        heading = f"<h1>{escape(section.title)}</h1>"
        pdf.write_html(heading + _section_html(section.body), **_HTML_OPTIONS)
    return bytes(pdf.output())
