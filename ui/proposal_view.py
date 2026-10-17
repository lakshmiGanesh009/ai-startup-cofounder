"""The investment proposal on screen: each part as text, tables and charts,
with a form to edit it.

Every part is marked with where it came from: the agent that wrote it, or
"calculated" for the investment metrics, which the API works out from the
financial plan. Figures the agents marked as assumptions are highlighted.
"""

import re
from typing import Literal, get_args, get_origin

import altair as alt
import pandas as pd
import streamlit as st
from pydantic import BaseModel, ValidationError

from proposal import (
    PARTS,
    InvestmentMetrics,
    describe_break_even,
    describe_irr,
    describe_payback,
)

BLUE = {250: "#86b6ef", 350: "#5598e7", 450: "#2a78d6", 550: "#1c5cab", 650: "#104281"}
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
NEGATIVE = "#e34948"
SEVERITY = {"Low": "#9fd89f", "Moderate": "#fdd98c", "High": "#f5c1ac", "Critical": "#e9a4a4"}
LEVELS = ("Low", "Medium", "High")
SERIES_NAMES = ["Revenue", "Operating costs"]
AGENTS = {
    "executive": "Chief of Staff",
    "market": "Marketing Strategy Agent",
    "technical": "Technical Feasibility Agent",
    "risk": "Risk & Compliance Agent",
    "financial": "Financial Planning Agent",
}
LABELS = {
    "tam": "TAM (total addressable market)",
    "sam": "SAM (serviceable addressable market)",
    "som": "SOM (serviceable obtainable market)",
    "kpis": "Success metrics (KPIs)",
    "capex": "CapEx: one-off costs before launch",
    "monthly_opex": "OpEx: monthly costs at launch",
    "value_usd": "Value ($ a year)",
    "cac_usd": "CAC ($)",
    "count": "FTE",
    "kind": "Type",
    "price_per_customer_month_usd": "Price per customer ($ a month)",
    "variable_cost_per_customer_month_usd": "Cost to serve a customer ($ a month)",
    "discount_rate": "Discount rate (0.30 = 30%)",
    "monthly_volume": "Monthly volume",
    "customers": "Customers (year end)",
    "average_customers": "Average customers",
    "one_off_revenue_usd": "One-off revenue ($)",
    "fixed_costs_month_usd": "Fixed costs ($ a month)",
    "start_month": "Start month",
    "duration_months": "Months",
}
_ASSUMPTION = re.compile(r"\((?:assumption|assumed|estimate|estimated)s?\)", re.IGNORECASE)


def literal(text: str) -> str:
    """Escape `$` so Streamlit shows it rather than starting a LaTeX formula."""
    return text.replace("$", "\\$")


def prose(text: str) -> str:
    """An agent's markdown, ready for st.markdown: dollars shown as dollars and
    the figures it marked as assumptions highlighted."""
    return _ASSUMPTION.sub(":orange-badge[assumption]", literal(text))


def money(value: float) -> str:
    sign, value = ("-" if value < 0 else ""), abs(value)
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if value >= size:
            number = value / size
            text = f"{number:.0f}" if number >= 100 else f"{number:.1f}".removesuffix(".0")
            return f"{sign}${text}{suffix}"
    return f"{sign}${value:,.0f}"


def source(part: str) -> None:
    st.badge(f"Written by the {AGENTS[part]}", icon=":material/smart_toy:", color="blue")


def calculated(what: str) -> None:
    st.badge(f"Calculated {what}", icon=":material/calculate:", color="gray")


def _table(rows: list[dict]) -> None:
    st.table(pd.DataFrame([{k: literal(str(v)) for k, v in row.items()} for row in rows]),
             hide_index=True)


def _tiles(items: list[tuple[str, str, str]], columns: int = 3) -> None:
    for start in range(0, len(items), columns):
        for column, (label, value, note) in zip(st.columns(columns), items[start:start + columns]):
            with column.container(border=True):
                st.metric(label, value)
                st.caption(literal(note))


_DOLLARS = "replace(format(datum.value, '$~s'), 'G', 'B')"


def _chart(chart: alt.Chart) -> None:
    st.altair_chart(chart.configure_view(stroke=None), width="stretch")


def _hbars(rows: list[tuple[str, float]], color: str, height: int = 34) -> None:
    rows = sorted(rows, key=lambda row: row[1], reverse=True)
    frame = pd.DataFrame(rows, columns=["item", "usd"])
    base = alt.Chart(frame).encode(
        y=alt.Y("item:N", sort=[item for item, _ in rows], title=None, axis=alt.Axis(labelLimit=260)),
        x=alt.X("usd:Q", title=None, axis=alt.Axis(labelExpr=_DOLLARS, grid=True)),
        tooltip=[alt.Tooltip("item:N", title="Item"), alt.Tooltip("usd:Q", title="$", format="$,.0f")],
    )
    bars = base.mark_bar(color=color, cornerRadiusEnd=4, size=16)
    labels = base.mark_text(align="left", dx=4, fontWeight="bold").encode(
        text=alt.Text("usd:Q", format="$,.0f"))
    _chart((bars + labels).properties(height=height * len(frame) + 30))


def _executive(p: dict, m: dict) -> None:
    e, f = p["executive"], p["financial"]
    metrics = InvestmentMetrics.model_validate(m)
    years = sorted(f["projections"], key=lambda y: y["year"])[:3]
    source("executive")
    tone = {"Go": st.success, "Go with conditions": st.warning, "Not yet": st.error}[e["verdict"]]
    tone(f"**Recommendation: {e['verdict']}.** {prose(e['recommendation'])}",
         icon=":material/flag:")
    for title, field in (("Project overview", "overview"), ("The opportunity", "opportunity"),
                         ("Strategic alignment", "strategic_alignment")):
        st.markdown(f"#### {title}")
        st.markdown(prose(e[field]))
    st.markdown("#### Financial snapshot")
    calculated("from the financial plan")
    _tiles([
        ("Total CapEx", money(m["capex_usd"]), "one-off, before launch"),
        ("Revenue, years 1-3",
         f"{money(m['revenue_usd'][0])} → {money(m['revenue_usd'][-1])}" if years else "-",
         "from the Financial Planning Agent's drivers"),
        ("NPV", money(m["npv_usd"]), f"at a {f['discount_rate']:.0%} discount rate"),
        ("IRR", *describe_irr(metrics)),
        ("Payback", describe_payback(metrics), "from the start of the project"),
        ("Break-even", describe_break_even(metrics), "paying customers to cover the fixed costs"),
    ])
    st.info(f"**What the numbers say.** {prose(e['financial_case'])}", icon=":material/insights:")


def _market(p: dict) -> None:
    mk = p["market"]
    source("market")
    st.markdown("#### Target audience and buyer personas")
    st.markdown(prose(mk["personas"]))

    st.markdown("#### Market size")
    sizes = [("TAM", mk["tam"]), ("SAM", mk["sam"]), ("SOM", mk["som"])]
    frame = pd.DataFrame([{"market": name, "usd": size["value_usd"]} for name, size in sizes])
    base = alt.Chart(frame).encode(
        y=alt.Y("market:N", sort=["TAM", "SAM", "SOM"], title=None),
        x=alt.X("usd:Q", title=None, axis=alt.Axis(labelExpr=_DOLLARS)),
        tooltip=[alt.Tooltip("market:N", title="Market"), alt.Tooltip("usd:Q", title="$ a year", format="$,.0f")],
    )
    bars = base.mark_bar(cornerRadiusEnd=4, size=22).encode(
        color=alt.Color("market:N", legend=None, scale=alt.Scale(
            domain=["TAM", "SAM", "SOM"], range=[BLUE[250], BLUE[450], BLUE[650]])))
    labels = base.mark_text(align="left", dx=4, fontWeight="bold").encode(
        text=alt.Text("usd:Q", format="$,.3~s"))
    _chart((bars + labels).properties(height=130))
    shares = ["", f" · {mk['sam']['value_usd'] / mk['tam']['value_usd']:.1%} of TAM" if mk["tam"]["value_usd"] else "",
              f" · {mk['som']['value_usd'] / mk['sam']['value_usd']:.1%} of SAM" if mk["sam"]["value_usd"] else ""]
    for (name, size), share in zip(sizes, shares):
        st.markdown(f"- **{name} {literal(money(size['value_usd']))}**{share}: {prose(size['basis'])}")

    st.markdown("#### Competitive landscape")
    _table([{"Competitor": c["name"], "Type": c["kind"], "Est. share": c["market_share"],
             "Strengths": c["strengths"], "Weaknesses": c["weaknesses"]} for c in mk["competitors"]])
    st.markdown("#### Unique value proposition")
    st.info(prose(mk["value_proposition"]), icon=":material/star:")

    st.markdown("#### Go-to-market channels")
    _table([{"Channel": c["channel"], "How it is used": c["approach"],
             "Monthly budget": f"${c['monthly_budget_usd']:,.0f}"} for c in mk["channels"]])
    if mk["channels"]:
        _hbars([(c["channel"], c["monthly_budget_usd"]) for c in mk["channels"]], SERIES[0])
    st.markdown("#### Pricing strategy")
    st.markdown(prose(mk["pricing_strategy"]))

    st.markdown("#### Sales funnel")
    st.badge("Estimated monthly volumes at the end of year 1", icon=":material/info:", color="orange")
    stages = mk["funnel"]
    rows = []
    for index, stage in enumerate(stages):
        before = stages[index - 1]["monthly_volume"] if index else 0
        note = f"{stage['monthly_volume']:,.1f}".removesuffix(".0") + " a month"
        if before:
            note += f" · {stage['monthly_volume'] / before:.0%} convert"
        half = stage["monthly_volume"] / 2
        rows.append({"stage": stage["stage"], "order": index, "low": -half, "half": half,
                     "note": note})
    frame = pd.DataFrame(rows)
    top = frame["half"].max() if len(frame) else 1
    steps = [BLUE[s] for s in (250, 350, 450, 550, 650)]
    base = alt.Chart(frame).encode(y=alt.Y("stage:N", sort=[r["stage"] for r in rows], title=None))
    bars = base.mark_bar(cornerRadius=4, size=24).encode(
        x=alt.X("low:Q", axis=None, scale=alt.Scale(domain=[-top, top * 2.1])), x2="half:Q",
        color=alt.Color("order:O", legend=None, scale=alt.Scale(range=steps)),
        tooltip=[alt.Tooltip("stage:N", title="Stage"), alt.Tooltip("note:N", title="Volume")],
    )
    labels = base.mark_text(align="left").encode(x=alt.datum(top * 1.1), text="note:N")
    _chart((bars + labels).properties(height=40 * len(frame) + 10))


def _technical(p: dict) -> None:
    t = p["technical"]
    source("technical")
    for title, field in (("Infrastructure", "infrastructure"), ("Technology stack", "stack"),
                         ("Scalability and performance", "scalability")):
        st.markdown(f"#### {title}")
        st.markdown(prose(t[field]))
    st.markdown("#### Implementation roadmap")
    phases = sorted(t["roadmap"], key=lambda ph: ph["start_month"])
    frame = pd.DataFrame([{"phase": ph["name"], "start": ph["start_month"] - 1,
                           "end": ph["start_month"] - 1 + ph["duration_months"],
                           "mid": ph["start_month"] - 1 + ph["duration_months"] / 2,
                           "months": f"{ph['duration_months']} mo"} for ph in phases])
    base = alt.Chart(frame).encode(y=alt.Y("phase:N", sort=[ph["name"] for ph in phases], title=None,
                                          axis=alt.Axis(labelLimit=220)))
    bars = base.mark_bar(color=SERIES[0], cornerRadius=4, size=20).encode(
        x=alt.X("start:Q", title="Month", axis=alt.Axis(tickMinStep=1, labelExpr="datum.value + 1")),
        x2="end:Q", tooltip=["phase:N", "months:N"])
    labels = base.mark_text(color="white", fontWeight="bold").encode(x=alt.X("mid:Q"), text="months:N")
    _chart((bars + labels).properties(height=36 * len(frame) + 40))
    _table([{"Phase": ph["name"],
             "Months": f"{ph['start_month']}-{ph['start_month'] + ph['duration_months'] - 1}",
             "Deliverables": ph["deliverables"]} for ph in phases])
    st.markdown("#### Resource and staffing plan")
    _table([{"Role": s["role"], "FTE": f"{s['count']:g}", "When": s["timing"]} for s in t["staffing"]])
    st.caption(f"{sum(s['count'] for s in t['staffing']):g} full-time equivalents in all.")


def _financial(p: dict, m: dict, checks: list[str]) -> None:
    f = p["financial"]
    metrics = InvestmentMetrics.model_validate(m)
    years = sorted(f["projections"], key=lambda y: y["year"])[:3]
    source("financial")
    if checks:
        st.warning("**Checks on the figures** (calculated from them):\n"
                   + "\n".join(f"- {literal(issue)}" for issue in checks), icon=":material/rule:")
    st.markdown("#### Capital and operating expenditures")
    capex, opex = st.columns(2, gap="large")
    with capex:
        st.markdown(f"**CapEx: {literal(money(m['capex_usd']))} one-off**")
        _hbars([(c["item"], c["amount_usd"]) for c in f["capex"]], SERIES[0])
    with opex:
        st.markdown(f"**OpEx at launch: {literal(money(m['monthly_fixed_costs_usd']))} a month**")
        _hbars([(c["item"], c["amount_usd"]) for c in f["monthly_opex"]], SERIES[1])

    st.markdown("#### Three-year projections")
    frame = pd.DataFrame(
        [{"year": f"Year {y['year']}", "series": name, "usd": m[field][index]}
         for index, y in enumerate(years)
         for name, field in (("Revenue", "revenue_usd"), ("Operating costs", "opex_usd"))]
    )
    base = alt.Chart(frame).encode(
        x=alt.X("year:N", title=None, axis=alt.Axis(labelAngle=0)), xOffset=alt.XOffset("series:N", sort=SERIES_NAMES),
        y=alt.Y("usd:Q", title=None, axis=alt.Axis(labelExpr=_DOLLARS)),
        tooltip=["year:N", "series:N", alt.Tooltip("usd:Q", format="$,.0f")],
    )
    bars = base.mark_bar(cornerRadiusEnd=4, size=34).encode(color=alt.Color(
        "series:N", sort=SERIES_NAMES, title=None, legend=alt.Legend(orient="top"),
        scale=alt.Scale(domain=SERIES_NAMES, range=list(SERIES[:2]))))
    labels = base.mark_text(dy=-8, fontSize=11).encode(text=alt.Text("usd:Q", format="$.3~s"))
    if years:
        _chart((bars + labels).properties(height=300))
    margins = [f"{n:.0%}" if n is not None else "-" for n in m["net_margin"]]

    def usd(value: float) -> str:
        return f"-${-value:,.0f}" if value < 0 else f"${value:,.0f}"

    drivers = [("Paying customers (year end)", [f"{y['customers']:,}" for y in years]),
               ("Average paying customers", [f"{y['average_customers']:,.1f}".removesuffix(".0") for y in years]),
               ("Fixed costs a month", [usd(y["fixed_costs_month_usd"]) for y in years]),
               ("One-off revenue", [usd(y["one_off_revenue_usd"]) for y in years]),
               ("Customer acquisition cost", [usd(y["cac_usd"]) for y in years])]
    results = [("Revenue", [usd(v) for v in m["revenue_usd"]]),
               ("Operating costs (OpEx), with the cost to serve", [usd(v) for v in m["opex_usd"]]),
               ("Net cash flow", [usd(c) for c in m["net_cash_flow_usd"][1:]]),
               ("Net margin", margins)]
    st.caption("Drivers from the Financial Planning Agent")
    _table([{"": name, **{f"Year {y['year']}": v for y, v in zip(years, values)}} for name, values in drivers])
    calculated("from the drivers: revenue = average customers × price × 12 + one-off revenue; "
               "OpEx = (fixed costs + average customers × cost to serve) × 12")
    _table([{"": name, **{f"Year {y['year']}": v for y, v in zip(years, values)}} for name, values in results])

    st.markdown("#### Investment metrics")
    calculated("from the figures above")
    contribution = f["price_per_customer_month_usd"] - f["variable_cost_per_customer_month_usd"]
    _tiles([
        ("NPV", money(m["npv_usd"]), f"at a {f['discount_rate']:.0%} discount rate"),
        ("IRR", *describe_irr(metrics)),
        ("Payback", describe_payback(metrics), "cumulative cash back to zero"),
        ("Break-even", describe_break_even(metrics), f"at {money(m['monthly_fixed_costs_usd'])} fixed costs a month"),
        ("Contribution", f"{money(contribution)}/mo", "per customer, after the cost to serve"),
        ("Price", f"{money(f['price_per_customer_month_usd'])}/mo",
         f"per customer; {money(f['variable_cost_per_customer_month_usd'])} to serve"),
    ])
    total, cumulative = 0.0, []
    for index, cash in enumerate(m["net_cash_flow_usd"]):
        total += cash
        cumulative.append({"when": "Start" if index == 0 else f"End of year {index}",
                           "usd": total, "position": "Above zero" if total >= 0 else "Below zero"})
    frame = pd.DataFrame(cumulative)
    # Each label sits just beyond its bar's end, above or below zero.
    pad = 0.07 * ((frame["usd"].max() - frame["usd"].min()) or 1)
    frame["label_at"] = frame["usd"] + frame["usd"].map(lambda v: pad if v >= 0 else -pad)
    base = alt.Chart(frame).encode(
        x=alt.X("when:N", sort=[c["when"] for c in cumulative], title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("usd:Q", title="Cumulative cash position", axis=alt.Axis(labelExpr=_DOLLARS)),
        tooltip=["when:N", alt.Tooltip("usd:Q", format="$,.0f")],
    )
    bars = base.mark_bar(cornerRadiusEnd=4, size=40).encode(color=alt.Color(
        "position:N", title=None, legend=alt.Legend(orient="top"),
        scale=alt.Scale(domain=["Above zero", "Below zero"], range=[SERIES[0], NEGATIVE])))
    labels = base.mark_text(fontWeight="bold").encode(
        y=alt.Y("label_at:Q"), text=alt.Text("usd:Q", format="$.3~s"))
    _chart((bars + labels).properties(height=260))
    st.markdown("#### Assumptions")
    st.markdown(prose(f["assumptions"]))


def _risk(p: dict) -> None:
    r = p["risk"]
    source("risk")
    st.markdown("#### Data protection")
    st.markdown(prose(r["data_protection"]))
    st.markdown("#### Compliance")
    st.markdown(prose(r["compliance"]))
    st.markdown("#### Risk matrix")
    risks = [(f"R{n}", x) for n, x in enumerate(r["risks"], start=1)]
    names = ("Low", "Low", "Moderate", "High", "Critical")
    cells = [
        {"probability": prob, "impact": imp,
         "severity": names[LEVELS.index(prob) + LEVELS.index(imp)],
         "risks": " ".join(rid for rid, x in risks if x["probability"] == prob and x["impact"] == imp)}
        for prob in LEVELS for imp in LEVELS
    ]
    base = alt.Chart(pd.DataFrame(cells)).encode(
        x=alt.X("probability:N", sort=list(LEVELS), title="Probability", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("impact:N", sort=list(reversed(LEVELS)), title="Impact"),
    )
    grid = base.mark_rect(stroke="white", strokeWidth=3, cornerRadius=4).encode(
        color=alt.Color("severity:N", title="Severity", scale=alt.Scale(
            domain=list(SEVERITY), range=list(SEVERITY.values()))),
        tooltip=["probability:N", "impact:N", "severity:N", "risks:N"])
    labels = base.mark_text(fontWeight="bold", fontSize=14, color="#0b0b0b").encode(text="risks:N")
    _chart((grid + labels).properties(height=260))
    tones = {"Low": "green", "Medium": "orange", "High": "red"}
    for rid, x in risks:
        level = names[LEVELS.index(x["probability"]) + LEVELS.index(x["impact"])]
        with st.container(border=True):
            st.markdown(
                f"**{rid} · {x['category']}** "
                f":{tones[x['probability']]}-badge[Probability: {x['probability']}] "
                f":{tones[x['impact']]}-badge[Impact: {x['impact']}] "
                f":gray-badge[Severity: {level}]  \n"
                f"**{literal(x['description'])}**  \n"
                f"Mitigation: {prose(x['mitigation'])}"
            )


def _kpis(p: dict) -> None:
    source("executive")
    kpis = p["executive"]["kpis"]
    categories = [c for c in ("Financial", "Technical", "Marketing") if any(k["category"] == c for k in kpis)]
    for column, category in zip(st.columns(max(len(categories), 1)), categories):
        with column:
            st.markdown(f"**{category}**")
            for k in kpis:
                if k["category"] == category:
                    with st.container(border=True):
                        st.markdown(f"**{literal(k['metric'])}**  \n{literal(k['target'])}")


# The proposal's tabs: their title, the part they edit and the fields of it they
# show in the edit form.
TABS = (
    ("Executive summary", "executive", ("project_name", "verdict", "recommendation", "overview",
                                        "opportunity", "strategic_alignment", "financial_case")),
    ("Market", "market", None),
    ("Technical", "technical", None),
    ("Financial", "financial", None),
    ("Risk & compliance", "risk", None),
    ("KPIs", "executive", ("kpis",)),
)


def show(tab: str, proposal: dict, metrics: dict, checks: list[str]) -> None:
    """Draw one tab of the proposal."""
    {
        "Executive summary": lambda: _executive(proposal, metrics),
        "Market": lambda: _market(proposal),
        "Technical": lambda: _technical(proposal),
        "Financial": lambda: _financial(proposal, metrics, checks),
        "Risk & compliance": lambda: _risk(proposal),
        "KPIs": lambda: _kpis(proposal),
    }[tab]()


def _label(name: str) -> str:
    return LABELS.get(name) or name.removesuffix("_usd").replace("_", " ").capitalize()


def _height(text: str) -> int:
    lines = sum(1 + len(line) // 95 for line in text.splitlines()) or 1
    return min(400, max(80, 24 * lines + 20))


def _column(name: str, field) -> object:
    kind = field.annotation
    if get_origin(kind) is Literal:
        return st.column_config.SelectboxColumn(_label(name), options=list(get_args(kind)), required=True)
    if kind in (int, float):
        return st.column_config.NumberColumn(_label(name), required=True,
                                             format="%d" if kind is int else None)
    return st.column_config.TextColumn(_label(name), required=True, help=field.description)


def _rows(frame: pd.DataFrame) -> list[dict]:
    """The rows of an edited table, without empty ones."""
    rows = []
    for row in frame.to_dict("records"):
        row = {k: (None if not isinstance(v, str) and pd.isna(v) else v) for k, v in row.items()}
        if any(v not in (None, "") for v in row.values()):
            rows.append(row)
    return rows


def _input(name: str, field, value, key: str):
    kind, label = field.annotation, _label(name)
    if kind is str:
        if "\n" not in value and len(value) < 80:  # a name or a short phrase
            return st.text_input(label, value, key=key, help=field.description)
        return st.text_area(label, value, key=key, help=field.description, height=_height(value))
    if kind in (int, float):
        return st.number_input(label, value=value, key=key, help=field.description,
                               step=1 if kind is int else None)
    if get_origin(kind) is Literal:
        options = list(get_args(kind))
        return st.selectbox(label, options, index=options.index(value), key=key, help=field.description)
    if isinstance(kind, type) and issubclass(kind, BaseModel):
        st.markdown(f"**{label}**")
        return {sub: _input(sub, f, value[sub], f"{key}:{sub}") for sub, f in kind.model_fields.items()}
    item = get_args(kind)[0]
    st.markdown(f"**{label}**")
    frame = pd.DataFrame(value, columns=list(item.model_fields))
    edited = st.data_editor(
        frame, key=key, num_rows="dynamic", hide_index=True, width="stretch",
        column_config={sub: _column(sub, f) for sub, f in item.model_fields.items()},
    )
    return _rows(edited)


def edit_form(part: str, data: dict, fields: tuple[str, ...] | None, key: str) -> dict | None:
    """A form for `fields` of the proposal part (all of them if None), filled
    from `data`. Returns the edited part once it is saved and valid."""
    model = PARTS[part]
    with st.form(key, border=False):
        values = dict(data)
        for name in fields or model.model_fields:
            values[name] = _input(name, model.model_fields[name], data[name], f"{key}:{name}")
        saved = st.form_submit_button("Save changes", type="primary", icon=":material/save:")
    if not saved:
        return None
    try:
        return model.model_validate(values).model_dump()
    except ValidationError as error:
        problems = "; ".join(
            f"{' › '.join(_label(str(p)) if isinstance(p, str) else f'row {p + 1}' for p in e['loc'])}: {e['msg']}"
            for e in error.errors()[:4]
        )
        st.error(f"Not saved. {problems}")
        return None
