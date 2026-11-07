"""Render a session's report as a PDF.

Once the agents have written the investment proposal, the PDF is the proposal:
a cover with the document control and the recommendation, then the template's
sections with charts drawn from the figures (report_charts.py), each marked
with the agent it came from, and the team's report as an appendix. Before that,
it is the team's report: the strategy, each specialist's report and the
decisions on conflicts.

Text is markdown, as the agents write it. markdown-it turns it into HTML and
fpdf2 lays that out in the bundled DejaVu Sans font (assets/fonts), because the
PDF core fonts cannot show characters the agents use all the time, such as ≈,
≤, → or curly quotes. Raw HTML in a section is printed as text and images are
not loaded, so nothing in a report can make the server fetch a URL.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from fpdf import FPDF
from fpdf.fonts import FontFace, TextStyle
from markdown_it import MarkdownIt

import currency
import report_charts as chart
from agents.roles import ROLES
from proposal import (
    OWNERS,
    Proposal,
    describe_break_even,
    describe_irr,
    describe_payback,
    figure_checks,
    investment_metrics,
)
from report_charts import ASSUMPTION, BLUE, FONT, GRID, INK, MUTED, SECONDARY, STATUS, money
from reports import DECISIONS, RESEARCH, STRATEGY, Report

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_FILES = {
    "": "DejaVuSans.ttf",
    "B": "DejaVuSans-Bold.ttf",
    "I": "DejaVuSans-Oblique.ttf",
    "BI": "DejaVuSans-BoldOblique.ttf",
}
PREPARED_BY = "AI Startup Co-Founder Team"
VERDICT_COLORS = {"Go": STATUS["good"], "Go with conditions": STATUS["warning"],
                  "Not yet": STATUS["critical"]}

# The agents often put a heading or a point on its own line without a blank line
# before the next; "breaks" keeps those lines apart, as the editor shows them.
_markdown = (
    MarkdownIt("commonmark", {"html": False, "breaks": True})
    .enable(["table", "strikethrough"])
    .disable("image")
)
# Figures the agents mark as assumptions or estimates are highlighted.
_ASSUMPTION = re.compile(r"\((?:assumption|assumed|estimate|estimated)s?\)", re.IGNORECASE)


def _heading(size: float, top: float) -> TextStyle:
    # fpdf2 multiplies a heading's bottom margin by its font size.
    return TextStyle(font_family=FONT, font_style="B", font_size_pt=size, color=INK,
                     t_margin=top, b_margin=0.25)


_HTML_OPTIONS = {
    "font_family": FONT,
    "ul_bullet_char": "•",
    "li_prefix_color": BLUE[450],
    "tag_styles": {
        "h1": _heading(15, 0),
        "h2": _heading(12.5, 5),
        "h3": _heading(11, 4),
        "h4": _heading(10.5, 3),
        "h5": _heading(10, 3),
        "h6": _heading(10, 3),
        "p": TextStyle(t_margin=1.2, b_margin=1.2),
        # The default code font, Courier, cannot show characters such as ≈ or →.
        "code": FontFace(family=FONT, color=INK),
        "pre": TextStyle(font_family=FONT, t_margin=2),
        "blockquote": TextStyle(color=SECONDARY, t_margin=2, l_margin=6, b_margin=2),
        "a": FontFace(color=BLUE[550], emphasis="UNDERLINE"),
    },
}


class _ReportPDF(FPDF):
    def __init__(self, footer_text: str):
        super().__init__(format="A4")
        self.footer_text = footer_text
        for style, name in _FONT_FILES.items():
            self.add_font(FONT, style, FONT_DIR / name)
        self.set_margins(20, 18, 20)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_font(FONT, size=10)
        self.set_title(footer_text)
        self.set_creator(PREPARED_BY)

    def footer(self):
        self.set_y(-12)
        self.set_font(FONT, size=7.5)
        self.set_text_color(MUTED)
        self.cell(0, 5, f"{self.footer_text}  ·  page {self.page_no()} of {{nb}}", align="C")
        self.set_text_color(0)


def _html(body: str, shift: int = 1) -> str:
    """Markdown as HTML, its headings moved down `shift` levels so they sit
    under the PDF's own, and assumptions highlighted."""
    tokens = _markdown.parse(body)
    for token in tokens:
        if token.type in ("heading_open", "heading_close"):
            token.tag = f"h{min(int(token.tag[1]) + shift, 6)}"
    html = _markdown.renderer.render(tokens, _markdown.options, {})
    # fpdf2 sets text at one line per font size unless a block says otherwise.
    html = re.sub(r"<(p|ul|ol)([ >])", r'<\1 line-height="1.35"\2', html)
    return _ASSUMPTION.sub(lambda m: f'<font color="{ASSUMPTION}"><i>{m.group(0)}</i></font>', html)


def _text(pdf: FPDF, body: str, shift: int = 3) -> None:
    """A block of the agents' markdown at the current position."""
    pdf.set_x(pdf.l_margin)
    pdf.set_font(FONT, "", 9.5)
    pdf.set_text_color(INK)
    pdf.write_html(_html(body, shift), **_HTML_OPTIONS)
    pdf.ln(2)


def _agent(key: str) -> str:
    return "the Chief of Staff" if key == "chief" else f"the {ROLES[key].title} Agent"


def _full(value: float) -> str:
    return currency.full(value)


def _months(start: int, length: int) -> str:
    """The months a roadmap phase spans: "1-4", or "1" for a month or less."""
    end = start + max(length, 1) - 1
    return f"{start}-{end}" if end > start else f"{start}"


def _written_by(part: str) -> tuple[str, str]:
    return ("Written by", _agent(OWNERS[part]))


def _table(pdf: FPDF, headings: list[str], rows: list[list], widths: Sequence[float],
           align: list[str] | None = None) -> None:
    """A table with a tinted heading row and hairlines between rows. A cell is
    text, or (text, FontFace) to colour it."""
    chart.room(pdf, 22)
    pdf.set_font(FONT, size=8.3)
    pdf.set_text_color(INK)
    pdf.set_draw_color(GRID)
    pdf.set_line_width(0.2)
    # Cells without a fill of their own take the current fill colour.
    pdf.set_fill_color(chart.WHITE)
    with pdf.table(
        col_widths=widths, text_align=align or "LEFT", line_height=4.3, padding=(1.6, 2),
        headings_style=FontFace(emphasis="BOLD", color=BLUE[700], fill_color=BLUE[100]),
        borders_layout="HORIZONTAL_LINES", width=pdf.epw, v_align="TOP",
        cell_fill_color=chart.PLANE, cell_fill_mode="ROWS",
    ) as table:
        table.row(headings)
        for values in rows:
            row = table.row()
            for value in values:
                if isinstance(value, tuple):
                    row.cell(chart.plain(value[0]), style=value[1])
                else:
                    row.cell(chart.plain(str(value)))
    pdf.ln(4)


def _band(pdf: FPDF, kicker: str, title: str, subtitle: str) -> None:
    """The cover's coloured band: what the document is, its name and the request."""
    pdf.set_fill_color(BLUE[700])
    pdf.rect(0, 0, pdf.w, 52, style="F")
    pdf.set_text_color(BLUE[100])
    pdf.set_font(FONT, "B", 8.5)
    pdf.set_xy(pdf.l_margin, 13)
    pdf.cell(0, 5, kicker.upper(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color("#ffffff")
    pdf.set_font(FONT, "B", 21)
    pdf.cell(0, 11, chart.fit(pdf, title, pdf.epw), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(BLUE[100])
    pdf.set_font(FONT, "", 9)
    lines = cast(list[str], pdf.multi_cell(pdf.epw, 4.6, subtitle, dry_run=True, output="LINES"))
    shown = " ".join(lines[:3]) + (" …" if len(lines) > 3 else "")
    pdf.multi_cell(pdf.epw, 4.6, shown, align="L")
    pdf.set_y(60)


def _status(report: Report) -> str:
    status = "Edited by the founder" if report.edited else "Draft for review"
    return f"{status}{' (newer results not included)' if report.outdated else ''}"


def _document_control(pdf: FPDF, report: Report, label: str, value: str) -> None:
    _table(
        pdf,
        [label, "Prepared by", "Date", "Version", "Status"],
        [[value, report.settings.prepared_by, f"{report.updated_at:%d %b %Y}", f"v{report.version}",
          _status(report)]],
        [28, 26, 15, 11, 20],
    )


def _executive(pdf: FPDF, report: Report, p: Proposal) -> None:
    e, f = p.executive, p.financial
    m = investment_metrics(f)
    years = f.years
    chart.callout(pdf, f"Recommendation: {e.verdict}", e.recommendation,
                  VERDICT_COLORS[e.verdict])
    chart.section_heading(pdf, "1", "Executive Summary", [_written_by("executive")])
    for title, body in (("1.1 Project Overview", e.overview),
                        ("1.2 The Opportunity", e.opportunity),
                        ("1.3 Strategic Alignment", e.strategic_alignment)):
        chart.subheading(pdf, title)
        _text(pdf, body)
    chart.subheading(pdf, "1.4 Financial Snapshot", ("Calculated", "from the financial plan"),
                     then=48)
    chart.tiles(pdf, [
        ("Total CapEx", money(m.capex), "one-off, before launch"),
        ("Revenue, years 1-3",
         f"{money(m.revenue[0])} → {money(m.revenue[-1])}" if years else "-",
         "Finance agent's projection"),
        ("NPV", money(m.npv), f"at a {f.discount_rate:.0%} discount rate"),
        ("IRR", *describe_irr(m)),
        ("Payback", describe_payback(m), "from the start of the project"),
        ("Break-even", describe_break_even(m), "paying customers cover fixed costs"),
    ])
    chart.callout(pdf, "What the numbers say", e.financial_case, BLUE[450])


def _market(pdf: FPDF, p: Proposal) -> None:
    mk = p.market
    pdf.add_page()
    chart.section_heading(pdf, "2", "Market & Marketing Strategy", [_written_by("market")])
    chart.subheading(pdf, "2.1 Target Audience & Buyer Personas")
    _text(pdf, mk.personas)
    chart.subheading(pdf, "2.2 Market Size", then=50)
    chart.market_circles(pdf, [
        ("TAM", "Total addressable market", mk.tam.value, mk.tam.basis),
        ("SAM", "Serviceable addressable market", mk.sam.value, mk.sam.basis),
        ("SOM", "Serviceable obtainable market", mk.som.value, mk.som.basis),
    ])
    chart.subheading(pdf, "2.3 Competitive Landscape", then=30)
    _table(pdf, ["Competitor", "Type", "Est. share", "Strengths", "Weaknesses"],
           [[c.name, c.kind, c.market_share, c.strengths, c.weaknesses] for c in mk.competitors],
           [24, 13, 13, 25, 25])
    chart.subheading(pdf, "2.4 Unique Value Proposition")
    chart.callout(pdf, "Why customers choose us", mk.value_proposition, BLUE[450])
    chart.subheading(pdf, "2.5 Go-to-Market Channels", then=30)
    total = sum(c.monthly_budget for c in mk.channels)
    _table(pdf, ["Channel", "How it is used", "Monthly budget"],
           [[c.channel, c.approach, _full(c.monthly_budget)] for c in mk.channels]
           + [[("Total", FontFace(emphasis="BOLD")), "", (_full(total), FontFace(emphasis="BOLD"))]],
           [30, 52, 18], ["LEFT", "LEFT", "RIGHT"])
    chart.subheading(pdf, "2.6 Pricing Strategy")
    _text(pdf, mk.pricing_strategy)
    chart.subheading(pdf, "2.7 Sales Funnel", ("Estimated", "monthly volumes at the end of year 1"),
                     then=8 * len(mk.funnel))
    chart.funnel(pdf, [(s.stage, s.monthly_volume) for s in mk.funnel])


def _technical(pdf: FPDF, p: Proposal) -> None:
    t, r = p.technical, p.risk
    pdf.add_page()
    chart.section_heading(pdf, "3", "Technical & Operational Architecture",
                          [_written_by("technical"), _written_by("risk")])
    chart.subheading(pdf, "3.1 Infrastructure & Technology Stack", _written_by("technical"))
    for label, body in (("Infrastructure", t.infrastructure), ("Technology stack", t.stack),
                        ("Scalability & performance", t.scalability)):
        chart.label_line(pdf, label)
        _text(pdf, body)
    chart.subheading(pdf, "3.2 Security & Compliance", _written_by("risk"))
    for label, body in (("Data protection", r.data_protection), ("Compliance", r.compliance)):
        chart.label_line(pdf, label)
        _text(pdf, body)
    chart.subheading(pdf, "3.3 Implementation Roadmap", _written_by("technical"),
                     then=8 + 7.5 * len(t.roadmap))
    phases = sorted(t.roadmap, key=lambda phase: phase.start_month)
    chart.gantt(pdf, [(ph.name, ph.start_month, ph.duration_months) for ph in phases])
    _table(pdf, ["Phase", "Months", "Deliverables"],
           [[ph.name, _months(ph.start_month, ph.duration_months), ph.deliverables] for ph in phases],
           [28, 12, 60])
    chart.label_line(pdf, "Resource & staffing plan")
    fte = sum(s.count for s in t.staffing)
    _table(pdf, ["Role", "FTE", "When"],
           [[s.role, f"{s.count:g}", s.timing] for s in t.staffing]
           + [[("Total", FontFace(emphasis="BOLD")), (f"{fte:g}", FontFace(emphasis="BOLD")), ""]],
           [50, 12, 38], ["LEFT", "RIGHT", "LEFT"])


def _financial(pdf: FPDF, p: Proposal) -> None:
    f = p.financial
    m = investment_metrics(f)
    years = f.years
    pdf.add_page()
    chart.section_heading(pdf, "4", "Financial Plan & Projections",
                          [_written_by("financial"), ("Calculated", "investment metrics")])
    half = (pdf.epw - 8) / 2
    chart.subheading(pdf, "4.1 Capital & Operating Expenditures",
                     then=chart.hbars_height(max(len(f.capex), len(f.monthly_opex))))
    top = pdf.get_y()
    left = chart.hbars(pdf, f"CapEx: {money(m.capex)} one-off",
                       [(c.item, c.amount) for c in f.capex], width=half)
    pdf.set_y(top)
    right = chart.hbars(pdf, f"OpEx at launch: {money(m.monthly_fixed_costs)} a month",
                        [(c.item, c.amount) for c in f.monthly_opex],
                        x=pdf.l_margin + half + 8, width=half, color=chart.SERIES[1])
    pdf.set_y(top + max(left, right) + 4)
    chart.subheading(pdf, "4.2 Three-Year Projections", _written_by("financial"), then=70)
    labels = [f"Year {y.year}" for y in years]
    if years:
        chart.grouped_bars(pdf, labels, [("Revenue", m.revenue),
                                         ("Operating costs (OpEx)", m.opex)])
    margins = [f"{n:.0%}" if n is not None else "-" for n in m.net_margin]
    calculated = FontFace(color=SECONDARY, emphasis="ITALICS")
    bold = FontFace(emphasis="BOLD")
    _table(pdf, ["Drivers from the Financial Planning Agent", *labels], [
        ["Paying customers (year end)", *(f"{y.customers:,}" for y in years)],
        ["Average paying customers", *(f"{y.average_customers:,.1f}".removesuffix(".0") for y in years)],
        ["Fixed costs a month", *(_full(y.fixed_costs_month) for y in years)],
        ["One-off revenue", *(_full(y.one_off_revenue) for y in years)],
        ["Customer acquisition cost", *(_full(y.cac) for y in years)],
        [("Calculated from them", calculated), *[("", calculated)] * len(years)],
        ["Revenue", *(_full(v) for v in m.revenue)],
        ["Operating costs (OpEx), with the cost to serve", *(_full(v) for v in m.opex)],
        [("Net cash flow", bold), *((_full(c), bold) for c in m.net_cash_flow[1:])],
        ["Net margin", *margins],
    ], [44] + [18] * len(years), ["LEFT"] + ["RIGHT"] * len(years))
    chart.subheading(pdf, "4.3 Investment Metrics", ("Calculated", "from the figures above"),
                     then=48)
    contribution = f.price_per_customer_month - f.variable_cost_per_customer_month
    chart.tiles(pdf, [
        ("NPV", money(m.npv), f"at a {f.discount_rate:.0%} discount rate"),
        ("IRR", *describe_irr(m)),
        ("Payback", describe_payback(m), "cumulative cash back to zero"),
        ("Break-even", describe_break_even(m), f"at {money(m.monthly_fixed_costs)} fixed costs a month"),
        ("Contribution", f"{money(contribution)}/mo", "per customer, after cost to serve"),
        ("Price", f"{money(f.price_per_customer_month)}/mo",
         f"per customer; {money(f.variable_cost_per_customer_month)} to serve"),
    ])
    cumulative, total = [], 0.0
    for cash in m.net_cash_flow:
        total += cash
        cumulative.append(total)
    note = (f"Paid back: {describe_payback(m).lower()}" if m.payback_months is not None
            else "Not paid back within three years")
    chart.cash_position(pdf, cumulative, note)
    issues = figure_checks(p.market, f)
    if issues:
        chart.callout(pdf, "Checks on the figures",
                      "\n".join(f"• {issue}" for issue in issues), STATUS["warning"])
    chart.subheading(pdf, "Assumptions", _written_by("financial"))
    _text(pdf, f.assumptions)


def _risks(pdf: FPDF, p: Proposal) -> None:
    risks = p.risk.risks
    pdf.add_page()
    chart.section_heading(pdf, "5", "Risk Assessment & Mitigation", [_written_by("risk")])
    ids = [f"R{n}" for n in range(1, len(risks) + 1)]
    chart.risk_heatmap(pdf, [(rid, r.probability, r.impact) for rid, r in zip(ids, risks)])
    chart.risk_cards(pdf, [(rid, r.category, r.description, r.probability, r.impact, r.mitigation)
                           for rid, r in zip(ids, risks)])


def _kpis(pdf: FPDF, p: Proposal) -> None:
    chart.section_heading(pdf, "6", "Success Metrics (KPIs)", [_written_by("executive")])
    groups = []
    for category in ("Financial", "Technical", "Marketing"):
        kpis = [(k.metric, k.target) for k in p.executive.kpis if k.category == category]
        if kpis:
            groups.append((category, kpis))
    chart.kpi_cards(pdf, groups)


def _source(key: str) -> tuple[str, str]:
    """Who wrote a section of the team's report."""
    if key == STRATEGY:
        return ("Written by", _agent("chief"))
    if key == DECISIONS:
        return ("Decided by", _agent("chief"))
    if key == RESEARCH:
        return ("Found on", "the web")
    return ("Written by", _agent(key)) if key in ROLES else ("Edited by", "the founder")


def _team_sections(pdf: FPDF, report: Report, numbered: bool, new_pages: bool) -> None:
    shown = [section for section in report.sections if section.key not in report.settings.hidden]
    for index, section in enumerate(shown):
        if new_pages and index:
            pdf.add_page()
        number = str(index + 1) if numbered else chr(ord("A") + index)
        chart.section_heading(pdf, number, section.title, [_source(section.key)])
        _text(pdf, section.body, shift=2)


def render_pdf(report: Report) -> bytes:
    """The report as PDF bytes: the investment proposal if it has one, else
    the team's report with each section on a page of its own; every amount in
    the report's currency."""
    with currency.using(report.settings.currency):
        return _render(report)


def _render(report: Report) -> bytes:
    proposal = report.proposal
    if proposal is None:
        title = report.title if len(report.title) <= 70 else f"{report.title[:67]}..."
        pdf = _ReportPDF(f"{title}  ·  Launch report")
        pdf.add_page()
        _band(pdf, "Launch report", "The founding team's report", report.title)
        _document_control(pdf, report, "Objective", report.objective)
        _team_sections(pdf, report, numbered=True, new_pages=True)
        return bytes(pdf.output())

    project = proposal.executive.project_name
    pdf = _ReportPDF(f"{project}  ·  Investment proposal")
    pdf.add_page()
    _band(pdf, "Investment proposal", project, report.title)
    _document_control(pdf, report, "Project name", project)
    _executive(pdf, report, proposal)
    _market(pdf, proposal)
    _technical(pdf, proposal)
    _financial(pdf, proposal)
    _risks(pdf, proposal)
    _kpis(pdf, proposal)
    pdf.add_page()
    _band(pdf, "Appendix", "The founding team's report",
          "The reviewed reports and decisions the proposal was written from.")
    _team_sections(pdf, report, numbered=False, new_pages=False)
    return bytes(pdf.output())
