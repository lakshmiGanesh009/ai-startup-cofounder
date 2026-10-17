"""Charts and visual blocks for the PDF, drawn with fpdf2's own shapes.

Each function draws at the current position across the page's text width and
moves the position below what it drew, starting a new page first if it would
not fit. Colours follow one palette: blue for a single series, blue and orange
for two, a light-to-dark blue ramp for ordered stages, and the status colours
(always beside a text label) for verdicts and risk levels.
"""

import math
import re

from fpdf import FPDF

FONT = "DejaVu"

INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
PLANE = "#f9f9f7"
NEUTRAL = "#f0efec"
WHITE = "#ffffff"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
NEGATIVE = "#e34948"
BLUE = {100: "#cde2fb", 250: "#86b6ef", 350: "#5598e7", 450: "#2a78d6",
        550: "#1c5cab", 650: "#104281", 700: "#0d366b"}
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
# Highlight for figures the agents marked as assumptions.
ASSUMPTION = "#8a5300"


def plain(text: str) -> str:
    """Text without markdown emphasis, for places that cannot render it."""
    return re.sub(r"\*\*|__", "", text)


def tint(color: str, amount: float) -> str:
    """`color` mixed with white; amount 0 is the colour, 1 is white."""
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in rgb)


def money(value: float) -> str:
    """A compact dollar amount: $750, $12k, $1.2M."""
    sign, value = ("-" if value < 0 else ""), abs(value)
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if value >= size:
            number = value / size
            text = f"{number:.0f}" if number >= 100 else f"{number:.1f}".removesuffix(".0")
            return f"{sign}${text}{suffix}"
    return f"{sign}${value:,.0f}"


def room(pdf: FPDF, height: float) -> None:
    """Start a new page unless `height` mm still fit on this one."""
    if pdf.get_y() + height > pdf.page_break_trigger:
        pdf.add_page()


def _font(pdf: FPDF, size: float, style: str = "", color: str = INK) -> None:
    pdf.set_font(FONT, style, size)
    pdf.set_text_color(color)


def fit(pdf: FPDF, text: str, width: float) -> str:
    """`text` cut with an ellipsis to fit `width` in the current font."""
    if pdf.get_string_width(text) <= width:
        return text
    while text and pdf.get_string_width(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _label(pdf: FPDF, x: float, y: float, w: float, h: float, text: str,
           align: str = "L") -> None:
    pdf.set_xy(x, y)
    pdf.cell(w, h, fit(pdf, plain(text), w), align=align)


def _nice_step(span: float, ticks: int = 4) -> float:
    if span <= 0:
        return 1.0
    raw = span / ticks
    power = 10 ** math.floor(math.log10(raw))
    return next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)


def chip(pdf: FPDF, x: float, y: float, text: str, fill: str = BLUE[100],
         color: str = BLUE[700], size: float = 7) -> float:
    """A rounded label; returns its width."""
    _font(pdf, size, "B", color)
    width = pdf.get_string_width(text) + 4
    pdf.set_fill_color(fill)
    pdf.rect(x, y, width, 4.6, style="F", round_corners=True, corner_radius=1.2)
    pdf.set_xy(x, y)
    pdf.cell(width, 4.6, text, align="C")
    return width


def section_heading(pdf: FPDF, number: str, title: str, sources: list[tuple[str, str]]) -> None:
    """A numbered section title, then chips naming where its content comes from.

    `sources` pairs a lead word with a name, for example ("Written by", "the
    Marketing Strategy Agent"); a lead of "Calculated" is shown in grey.
    """
    room(pdf, 30)
    x, y = pdf.l_margin, pdf.get_y()
    pdf.set_fill_color(BLUE[650])
    pdf.rect(x, y, 9, 9, style="F", round_corners=True, corner_radius=2)
    _font(pdf, 11, "B", WHITE)
    pdf.set_xy(x, y)
    pdf.cell(9, 9, number, align="C")
    _font(pdf, 15, "B")
    _label(pdf, x + 12, y, pdf.epw - 12, 9, title)
    cx = x
    for lead, name in sources:
        calculated = lead == "Calculated"
        cx += chip(pdf, cx, y + 11.5, f"{lead} {name}",
                   fill=NEUTRAL if calculated else BLUE[100],
                   color=SECONDARY if calculated else BLUE[700]) + 2
    pdf.set_y(y + 19)


def subheading(pdf: FPDF, text: str, source: tuple[str, str] | None = None,
               then: float = 0) -> None:
    """A numbered subsection title with a rule under it, and a chip naming its
    source. `then` is the height of what follows that must stay with it."""
    room(pdf, 18 + then)
    y = pdf.get_y() + 2
    _font(pdf, 11.5, "B", BLUE[700])
    pdf.set_xy(pdf.l_margin, y)
    pdf.cell(pdf.get_string_width(text) + 3, 6, text)
    if source:
        lead, name = source
        calculated = lead == "Calculated"
        chip(pdf, pdf.get_x(), y + 0.7, f"{lead} {name}",
             fill=NEUTRAL if calculated else BLUE[100],
             color=SECONDARY if calculated else BLUE[700], size=6.5)
    pdf.set_draw_color(GRID)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, y + 7, pdf.l_margin + pdf.epw, y + 7)
    pdf.set_y(y + 9)


def label_line(pdf: FPDF, text: str) -> None:
    """A small bold label above a block of text."""
    room(pdf, 14)
    _font(pdf, 9, "B", SECONDARY)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")


def callout(pdf: FPDF, label: str, text: str, accent: str, fill: str | None = None) -> None:
    """A tinted box with a coloured bar on its left: a label, then the text
    (bold with **...**)."""
    width = pdf.epw - 9
    _font(pdf, 9.5)
    text_h = pdf.multi_cell(width, 5, text, markdown=True, dry_run=True, output="HEIGHT")
    height = text_h + 13
    room(pdf, height + 3)
    x, y = pdf.l_margin, pdf.get_y()
    pdf.set_fill_color(fill or tint(accent, 0.86))
    pdf.rect(x, y, pdf.epw, height, style="F", round_corners=True, corner_radius=2)
    pdf.set_fill_color(accent)
    pdf.rect(x, y, 2.2, height, style="F", round_corners=("TOP_LEFT", "BOTTOM_LEFT"),
             corner_radius=2)
    _font(pdf, 10, "B")
    pdf.set_xy(x + 6, y + 3)
    pdf.cell(width, 5, label)
    _font(pdf, 9.5)
    pdf.set_xy(x + 6, y + 9)
    pdf.multi_cell(width, 5, text, markdown=True, align="L")
    pdf.set_y(y + height + 4)


def tiles(pdf: FPDF, items: list[tuple[str, str, str]], columns: int = 3) -> None:
    """Stat tiles in a grid: each a label, a big value and a short note."""
    gap, height = 4, 22
    width = (pdf.epw - gap * (columns - 1)) / columns
    rows = math.ceil(len(items) / columns)
    room(pdf, rows * (height + gap))
    top = pdf.get_y()
    for index, (label, value, note) in enumerate(items):
        x = pdf.l_margin + (index % columns) * (width + gap)
        y = top + (index // columns) * (height + gap)
        pdf.set_fill_color(PLANE)
        pdf.set_draw_color(GRID)
        pdf.set_line_width(0.25)
        pdf.rect(x, y, width, height, style="DF", round_corners=True, corner_radius=2)
        _font(pdf, 7.5, "", SECONDARY)
        _label(pdf, x + 3.5, y + 2.5, width - 7, 4, label.upper())
        size = 15
        _font(pdf, size, "B")
        while size > 10 and pdf.get_string_width(value) > width - 7:
            size -= 0.5
            _font(pdf, size, "B")
        _label(pdf, x + 3.5, y + 7.5, width - 7, 8, value)
        _font(pdf, 7, "", MUTED)
        _label(pdf, x + 3.5, y + 16, width - 7, 4, note)
    pdf.set_y(top + rows * (height + gap))


_HBAR_ROW = 10.5


def hbars_height(count: int) -> float:
    return 7 + count * _HBAR_ROW


def hbars(pdf: FPDF, title: str, items: list[tuple[str, float]], x: float | None = None,
          width: float | None = None, color: str = SERIES[0]) -> float:
    """A horizontal bar per item, largest first: its name above it and its value
    at its end. Returns the height drawn; the position is left below it when
    drawn full width."""
    x = pdf.l_margin if x is None else x
    width = pdf.epw if width is None else width
    items = sorted(items, key=lambda item: item[1], reverse=True)
    height = hbars_height(len(items))
    full = width == pdf.epw
    if full:
        room(pdf, height + 4)
    top = pdf.get_y()
    _font(pdf, 8.5, "B", SECONDARY)
    _label(pdf, x, top, width, 5, title)
    largest = max((value for _, value in items), default=0) or 1
    track = width - 16
    for index, (name, value) in enumerate(items):
        y = top + 7 + index * _HBAR_ROW
        _font(pdf, 8, "", INK)
        _label(pdf, x, y, width, 4, name)
        length = max(track * max(value, 0) / largest, 0.8)
        pdf.set_fill_color(color)
        pdf.rect(x, y + 4.4, length, 4, style="F",
                 round_corners=("TOP_RIGHT", "BOTTOM_RIGHT") if length > 2 else False,
                 corner_radius=1)
        _font(pdf, 7.5, "B", SECONDARY)
        _label(pdf, x + length + 1.5, y + 4.4, width - length - 1.5, 4, money(value))
    if full:
        pdf.set_y(top + height + 3)
    return height


def market_circles(pdf: FPDF, sizes: list[tuple[str, str, float, str]]) -> None:
    """TAM, SAM and SOM as nested circles, area to scale, with a key beside
    them. `sizes` holds (short name, long name, value, basis), largest first."""
    radius, key_x = 24, pdf.l_margin + 58
    room(pdf, 2 * radius + 6)
    top = pdf.get_y()
    base = top + 2 * radius
    cx = pdf.l_margin + radius + 1
    largest = sizes[0][2] or 1
    colors = (BLUE[250], BLUE[450], BLUE[650])
    for (_, _, value, _), color in zip(sizes, colors):
        r = max(radius * math.sqrt(max(value, 0) / largest), 1.2)
        pdf.set_fill_color(color)
        pdf.set_draw_color(WHITE)
        pdf.set_line_width(0.5)  # a surface ring keeps nested circles apart
        pdf.circle(cx, base - r, r, style="DF")
    y = top + 1
    width = pdf.l_margin + pdf.epw - key_x - 6
    for index, ((short, long, value, basis), color) in enumerate(zip(sizes, colors)):
        pdf.set_fill_color(color)
        pdf.rect(key_x, y + 1, 4, 4, style="F", round_corners=True, corner_radius=0.8)
        _font(pdf, 10, "B")
        share = ""
        if index:
            parent_value = sizes[index - 1][2]
            if parent_value:
                share = f"  ·  {value / parent_value:.1%} of {sizes[index - 1][0]}"
        _label(pdf, key_x + 6, y, width, 6, f"{short}  {money(value)}{share}")
        _font(pdf, 8, "", SECONDARY)
        pdf.set_xy(key_x + 6, y + 6)
        pdf.multi_cell(width, 4, plain(f"{long}: {basis}"), align="L")
        y = pdf.get_y() + 2.5
    pdf.set_y(max(base, y) + 4)


def funnel(pdf: FPDF, stages: list[tuple[str, float]]) -> None:
    """The sales funnel: a centred bar per stage, width to scale, with each
    stage's volume and its conversion from the stage before."""
    bar_h, gap, label_w, value_w = 7, 1, 44, 50
    height = len(stages) * (bar_h + gap)
    room(pdf, height + 4)
    top = pdf.get_y()
    track = pdf.epw - label_w - value_w
    centre = pdf.l_margin + label_w + track / 2
    largest = max((volume for _, volume in stages), default=0) or 1
    steps = [250, 350, 450, 550, 650]
    for index, (stage, volume) in enumerate(stages):
        y = top + index * (bar_h + gap)
        step = steps[round(index * (len(steps) - 1) / max(len(stages) - 1, 1))]
        length = max(track * max(volume, 0) / largest, 3)
        pdf.set_fill_color(BLUE[step])
        pdf.rect(centre - length / 2, y, length, bar_h, style="F", round_corners=True,
                 corner_radius=1)
        _font(pdf, 8.5, "B")
        _label(pdf, pdf.l_margin, y, label_w - 2, bar_h, stage)
        note = f"{volume:,.1f}".removesuffix(".0") + " a month"
        if index and stages[index - 1][1]:
            note += f"  ·  {volume / stages[index - 1][1]:.0%} convert"
        _font(pdf, 8, "", SECONDARY)
        _label(pdf, pdf.l_margin + label_w + track + 2, y, value_w - 2, bar_h, note)
    pdf.set_y(top + height + 4)


def _legend(pdf: FPDF, x: float, y: float, entries: list[tuple[str, str]]) -> None:
    for name, color in entries:
        pdf.set_fill_color(color)
        pdf.rect(x, y + 1, 3, 3, style="F", round_corners=True, corner_radius=0.6)
        _font(pdf, 8, "", SECONDARY)
        pdf.set_xy(x + 4, y)
        pdf.cell(pdf.get_string_width(name) + 1, 5, name)
        x += pdf.get_string_width(name) + 10


def _value_axis(pdf: FPDF, left: float, top: float, width: float, height: float,
                low: float, high: float) -> tuple[float, callable]:
    """Gridlines and labels for a value scale; returns the step and a function
    from a value to its y position."""
    step = _nice_step(high - low)
    low = step * math.floor(low / step)
    high = step * math.ceil(high / step) or step

    def y_of(value: float) -> float:
        return top + height * (high - value) / (high - low)

    pdf.set_line_width(0.2)
    value = low
    while value <= high + step / 2:
        y = y_of(value)
        pdf.set_draw_color(BASELINE if abs(value) < step / 1000 else GRID)
        pdf.line(left, y, left + width, y)
        _font(pdf, 7, "", MUTED)
        pdf.set_xy(left - 16, y - 2)
        pdf.cell(14, 4, money(value), align="R")
        value += step
    return step, y_of


def _bar(pdf: FPDF, x: float, w: float, y_zero: float, y_value: float, color: str) -> None:
    """A bar from the baseline, its far end rounded."""
    top, height = min(y_zero, y_value), abs(y_value - y_zero)
    if height < 0.2:
        return
    ends = ("TOP_LEFT", "TOP_RIGHT") if y_value < y_zero else ("BOTTOM_LEFT", "BOTTOM_RIGHT")
    pdf.set_fill_color(color)
    pdf.rect(x, top, w, height, style="F", round_corners=ends if height > 2 else False,
             corner_radius=1)


def grouped_bars(pdf: FPDF, categories: list[str], series: list[tuple[str, list[float]]],
                 height: float = 52) -> None:
    """Vertical bars grouped by category, one colour per series, with a legend
    and each bar's value above it."""
    room(pdf, height + 20)
    top = pdf.get_y()
    _legend(pdf, pdf.l_margin, top, [(name, SERIES[i]) for i, (name, _) in enumerate(series)])
    left, plot_top = pdf.l_margin + 17, top + 9
    width = pdf.epw - 17
    values = [v for _, vs in series for v in vs]
    _, y_of = _value_axis(pdf, left, plot_top, width, height, min(0, *values), max(0, *values))
    group_w = width / len(categories)
    bar_w = min(13, group_w * 0.3)
    for c, category in enumerate(categories):
        start = left + c * group_w + (group_w - len(series) * bar_w - (len(series) - 1) * 0.6) / 2
        for s, (_, vs) in enumerate(series):
            x = start + s * (bar_w + 0.6)
            _bar(pdf, x, bar_w, y_of(0), y_of(vs[c]), SERIES[s])
            _font(pdf, 6.5, "", SECONDARY)
            pdf.set_xy(x - 3, min(y_of(vs[c]), y_of(0)) - 4)
            pdf.cell(bar_w + 6, 3.5, money(vs[c]), align="C")
        _font(pdf, 8, "B", SECONDARY)
        pdf.set_xy(left + c * group_w, plot_top + height + 1.5)
        pdf.cell(group_w, 5, category, align="C")
    pdf.set_y(plot_top + height + 9)


def cash_position(pdf: FPDF, cumulative: list[float], note: str, height: float = 44) -> None:
    """The cumulative cash position at the start and the end of each year:
    blue above zero, red below, each bar labelled."""
    room(pdf, height + 20)
    top = pdf.get_y()
    _legend(pdf, pdf.l_margin, top, [("Cash position above zero", SERIES[0]),
                                    ("Below zero", NEGATIVE)])
    _font(pdf, 8, "B")
    _label(pdf, pdf.l_margin + pdf.epw / 2, top, pdf.epw / 2, 5, note, align="R")
    left, plot_top = pdf.l_margin + 17, top + 9
    width = pdf.epw - 17
    span = max(cumulative) - min(cumulative) or 1
    _, y_of = _value_axis(pdf, left, plot_top, width, height,
                          min(0, *cumulative) - span * 0.08, max(0, *cumulative) + span * 0.08)
    slot = width / len(cumulative)
    bar_w = min(16, slot * 0.42)
    labels = ["Start"] + [f"End of year {n}" for n in range(1, len(cumulative))]
    for i, value in enumerate(cumulative):
        x = left + i * slot + (slot - bar_w) / 2
        _bar(pdf, x, bar_w, y_of(0), y_of(value), SERIES[0] if value >= 0 else NEGATIVE)
        _font(pdf, 7, "B", INK)
        label_y = y_of(value) - 4.2 if value >= 0 else y_of(value) + 0.6
        pdf.set_xy(x - 4, label_y)
        pdf.cell(bar_w + 8, 3.6, money(value), align="C")
        _font(pdf, 8, "", SECONDARY)
        pdf.set_xy(left + i * slot, plot_top + height + 1.5)
        pdf.cell(slot, 5, labels[i], align="C")
    pdf.set_y(plot_top + height + 9)


def gantt(pdf: FPDF, phases: list[tuple[str, int, int]]) -> None:
    """The roadmap: one row per phase (name, start month, duration in months)
    on a timeline marked every three months."""
    row_h, label_w = 7.5, 52
    last = max((start + months - 1 for _, start, months in phases), default=12)
    months = max(3 * math.ceil(last / 3), 3)
    height = 6 + len(phases) * row_h
    room(pdf, height + 6)
    top = pdf.get_y()
    left, width = pdf.l_margin + label_w, pdf.epw - label_w
    per_month = width / months
    pdf.set_line_width(0.2)
    for month in range(0, months + 1, 3):
        x = left + month * per_month
        pdf.set_draw_color(GRID)
        pdf.line(x, top + 5, x, top + height)
        if month < months:
            _font(pdf, 7, "", MUTED)
            pdf.set_xy(x, top)
            pdf.cell(3 * per_month, 4.5, f"Month {month + 1}", align="L")
    for index, (name, start, length) in enumerate(phases):
        y = top + 6 + index * row_h
        _font(pdf, 8.5, "B")
        _label(pdf, pdf.l_margin, y + 0.8, label_w - 3, 5.5, name)
        x = left + (max(start, 1) - 1) * per_month
        w = max(length, 1) * per_month
        pdf.set_fill_color(SERIES[0])
        pdf.rect(x, y + 1, w, 5.5, style="F", round_corners=True, corner_radius=1)
        text = f"{length} mo"
        _font(pdf, 7, "B", WHITE)
        if pdf.get_string_width(text) + 3 < w:
            pdf.set_xy(x, y + 1)
            pdf.cell(w, 5.5, text, align="C")
    pdf.set_y(top + height + 5)


_LEVELS = ("Low", "Medium", "High")
SEVERITY = (("Low", STATUS["good"]), ("Low", STATUS["good"]), ("Moderate", STATUS["warning"]),
            ("High", STATUS["serious"]), ("Critical", STATUS["critical"]))


def severity(probability: str, impact: str) -> tuple[str, str]:
    """A risk's severity label and colour, from its probability and impact."""
    return SEVERITY[_LEVELS.index(probability) + _LEVELS.index(impact)]


def risk_heatmap(pdf: FPDF, risks: list[tuple[str, str, str]]) -> None:
    """Risks placed by probability (across) and impact (up), each a numbered
    marker; the cells are shaded by severity, with a key."""
    cell_w, cell_h, label_w = 26, 14, 20
    height = 3 * cell_h + 16
    room(pdf, height + 4)
    top = pdf.get_y()
    left = pdf.l_margin + label_w
    _font(pdf, 7.5, "B", SECONDARY)
    _label(pdf, pdf.l_margin, top, label_w, 4, "Impact")
    for row, impact in enumerate(reversed(_LEVELS)):
        y = top + 5 + row * cell_h
        _font(pdf, 8, "", SECONDARY)
        _label(pdf, pdf.l_margin, y, label_w - 2, cell_h, impact, align="R")
        for col, probability in enumerate(_LEVELS):
            x = left + col * cell_w
            _, color = severity(probability, impact)
            pdf.set_fill_color(tint(color, 0.7))
            pdf.set_draw_color(WHITE)
            pdf.set_line_width(0.6)
            pdf.rect(x, y, cell_w, cell_h, style="DF")
            here = [rid for rid, p, i in risks if p == probability and i == impact]
            for n, rid in enumerate(here[:8]):
                mx = x + 4.2 + (n % 4) * 5.8
                my = y + 4.2 + (n // 4) * 5.8
                pdf.set_fill_color(INK)
                pdf.set_draw_color(WHITE)
                pdf.set_line_width(0.4)
                pdf.circle(mx, my, 2.5, style="DF")
                _font(pdf, 6, "B", WHITE)
                pdf.set_xy(mx - 2.5, my - 2.5)
                pdf.cell(5, 5, rid, align="C")
    for col, probability in enumerate(_LEVELS):
        _font(pdf, 8, "", SECONDARY)
        pdf.set_xy(left + col * cell_w, top + 5 + 3 * cell_h + 1)
        pdf.cell(cell_w, 4.5, probability, align="C")
    _font(pdf, 7.5, "B", SECONDARY)
    pdf.set_xy(left, top + 5 + 3 * cell_h + 5.5)
    pdf.cell(3 * cell_w, 4.5, "Probability", align="C")
    key_x, y = left + 3 * cell_w + 10, top + 6
    _font(pdf, 8, "B", SECONDARY)
    _label(pdf, key_x, y, 50, 5, "Severity")
    for name, color in ({name: color for name, color in SEVERITY}).items():
        y += 6.5
        pdf.set_fill_color(tint(color, 0.7))
        pdf.set_draw_color(color)
        pdf.set_line_width(0.3)
        pdf.rect(key_x, y + 0.5, 6, 4, style="DF", round_corners=True, corner_radius=0.8)
        _font(pdf, 8, "", INK)
        _label(pdf, key_x + 8, y, 40, 5, name)
    pdf.set_y(top + height + 2)


_LEVEL_COLORS = {"Low": STATUS["good"], "Medium": STATUS["warning"], "High": STATUS["critical"]}


def risk_cards(pdf: FPDF, risks: list[tuple[str, str, str, str, str, str]]) -> None:
    """A full-width card per risk (id, category, risk, probability, impact,
    mitigation): a bar coloured by severity, the ratings as labelled chips, the
    risk in bold and its mitigation below."""
    inner = pdf.epw - 9
    for rid, category, description, probability, impact, mitigation in risks:
        description, mitigation = plain(description), plain(mitigation)
        _font(pdf, 9, "B")
        h_risk = pdf.multi_cell(inner, 4.4, description, dry_run=True, output="HEIGHT")
        _font(pdf, 8.5)
        h_mit = pdf.multi_cell(inner, 4.2, f"Mitigation: {mitigation}", dry_run=True, output="HEIGHT")
        height = 9 + h_risk + h_mit + 4
        room(pdf, height + 3)
        x, y = pdf.l_margin, pdf.get_y()
        level, color = severity(probability, impact)
        pdf.set_fill_color(PLANE)
        pdf.set_draw_color(GRID)
        pdf.set_line_width(0.25)
        pdf.rect(x, y, pdf.epw, height, style="DF", round_corners=True, corner_radius=1.5)
        pdf.set_fill_color(color)
        pdf.rect(x, y, 1.8, height, style="F", round_corners=("TOP_LEFT", "BOTTOM_LEFT"),
                 corner_radius=1.5)
        _font(pdf, 9, "B")
        pdf.set_xy(x + 5, y + 2.4)
        pdf.cell(pdf.get_string_width(f"{rid}  {category}") + 3, 4.6, f"{rid}  {category}")
        cx = pdf.get_x() + 1
        for label, value in (("Probability", probability), ("Impact", impact),
                             ("Severity", level)):
            tone = color if label == "Severity" else _LEVEL_COLORS[value]
            cx += chip(pdf, cx, y + 2.4, f"{label}: {value}", fill=tint(tone, 0.72),
                       color=INK, size=6.5) + 1.5
        _font(pdf, 9, "B")
        pdf.set_xy(x + 5, y + 8.5)
        pdf.multi_cell(inner, 4.4, description, align="L")
        _font(pdf, 8.5, "", SECONDARY)
        pdf.set_x(x + 5)
        pdf.multi_cell(inner, 4.2, f"Mitigation: {mitigation}", align="L")
        pdf.set_y(y + height + 2.5)


def kpi_cards(pdf: FPDF, groups: list[tuple[str, list[tuple[str, str]]]]) -> None:
    """Success metrics in a column per category: a card per metric with its target."""
    gap = 4
    width = (pdf.epw - gap * (len(groups) - 1)) / max(len(groups), 1)
    inner = width - 7

    groups = [(category, [(plain(m), plain(t)) for m, t in kpis]) for category, kpis in groups]

    def card_height(metric: str, target: str) -> float:
        _font(pdf, 8.5, "B")
        h = pdf.multi_cell(inner, 4.2, metric, dry_run=True, output="HEIGHT")
        _font(pdf, 8)
        return h + pdf.multi_cell(inner, 4, target, dry_run=True, output="HEIGHT") + 5

    tallest = max((8 + sum(card_height(m, t) + 2.5 for m, t in kpis) for _, kpis in groups),
                  default=0)
    room(pdf, tallest + 2)
    top, bottom = pdf.get_y(), pdf.get_y()
    for index, (category, kpis) in enumerate(groups):
        x = pdf.l_margin + index * (width + gap)
        color = SERIES[index % len(SERIES)]
        pdf.set_fill_color(color)
        pdf.rect(x, top + 1, 3, 3, style="F", round_corners=True, corner_radius=0.6)
        _font(pdf, 9.5, "B")
        _label(pdf, x + 5, top, width - 5, 5, category)
        y = top + 8
        for metric, target in kpis:
            h = card_height(metric, target)
            pdf.set_fill_color(PLANE)
            pdf.set_draw_color(GRID)
            pdf.set_line_width(0.25)
            pdf.rect(x, y, width, h, style="DF", round_corners=True, corner_radius=1.5)
            pdf.set_fill_color(color)
            pdf.rect(x, y, 1.6, h, style="F", round_corners=("TOP_LEFT", "BOTTOM_LEFT"),
                     corner_radius=1.5)
            _font(pdf, 8.5, "B")
            pdf.set_xy(x + 4, y + 2.2)
            pdf.multi_cell(inner, 4.2, metric, align="L")
            _font(pdf, 8, "", SECONDARY)
            pdf.set_x(x + 4)
            pdf.multi_cell(inner, 4, target, align="L")
            y += h + 2.5
        bottom = max(bottom, y)
    pdf.set_y(bottom + 2)
