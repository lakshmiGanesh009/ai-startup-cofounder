"""The investment proposal: a structured version of a session's report.

It follows an investment-proposal template (executive summary, market,
technical and operational architecture, financial plan, risk matrix, success
metrics). Each part is written by the agent that owns it, as structured data
(figures, tables) plus narrative markdown, so the PDF can draw charts from the
figures. Finance gives the drivers of each year (customers, fixed costs, one-off
fees); each year's revenue and costs, and the investment metrics (NPV, IRR,
payback, break-even), are calculated here from them rather than written by a
model, so the figures always add up.
"""

import math
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["Low", "Medium", "High"]


class MarketSize(BaseModel):
    value_usd: float = Field(description="Annual market value in US dollars.")
    basis: str = Field(description="How the figure was estimated, in one sentence.")


class Competitor(BaseModel):
    name: str = Field(description="The competitor or alternative, in a few words.")
    kind: Literal["Direct", "Indirect"]
    market_share: str = Field(description='An estimate such as "~15%", or "Unknown".')
    strengths: str = Field(description="A short phrase.")
    weaknesses: str = Field(description="A short phrase.")


class Channel(BaseModel):
    channel: str = Field(description="A short name, at most five words, such as 'Founder-led outbound'.")
    approach: str = Field(description="How the channel is used, in one sentence.")
    monthly_budget_usd: float


class FunnelStage(BaseModel):
    stage: str = Field(description="A short name, one to three words, such as Awareness, Lead, Demo, Paid.")
    monthly_volume: float = Field(description="People or companies reaching this stage per month.")


class MarketPlan(BaseModel):
    """Section 2, written by the Marketing Strategy Agent."""

    personas: str = Field(description="Buyer personas: demographics, psychographics, pain points (markdown).")
    tam: MarketSize = Field(description="Total addressable market.")
    sam: MarketSize = Field(description="Serviceable addressable market: the part of the TAM within reach.")
    som: MarketSize = Field(description="Serviceable obtainable market: the part of the SAM realistically won.")
    competitors: list[Competitor]
    value_proposition: str = Field(description="Why customers choose this over the alternatives.")
    channels: list[Channel]
    pricing_strategy: str = Field(description="The pricing model and price points, and why (markdown).")
    funnel: list[FunnelStage] = Field(description="From awareness to retention, largest stage first.")


class Phase(BaseModel):
    name: str = Field(description='For example "Phase 1: MVP".')
    start_month: int = Field(description="Month the phase starts, counting the project start as 1.")
    duration_months: int
    deliverables: str = Field(description="What ends the phase, in one sentence.")


class StaffLine(BaseModel):
    role: str = Field(description="The role, in a few words.")
    count: float = Field(description="Full-time equivalents.")
    timing: str = Field(description="When the role is needed, only that: for example 'Months 1-6'.")


class TechnicalPlan(BaseModel):
    """Sections 3.1 and 3.3, written by the Technical Feasibility Agent."""

    infrastructure: str = Field(description="System topology and cloud infrastructure (markdown).")
    stack: str = Field(description="Languages, databases, frameworks and APIs (markdown).")
    scalability: str = Field(description="How it handles growth, data spikes and latency (markdown).")
    roadmap: list[Phase]
    staffing: list[StaffLine]


class RiskItem(BaseModel):
    category: Literal["Technical", "Financial", "Marketing", "Regulatory", "Operational"]
    description: str = Field(description="The risk, in one sentence.")
    probability: Level
    impact: Level
    mitigation: str = Field(description="One or two sentences: the action, its owner and its trigger.")


class RiskPlan(BaseModel):
    """Sections 3.2 and 5, written by the Risk & Compliance Agent."""

    data_protection: str = Field(description="Encryption at rest and in transit, access control (markdown).")
    compliance: str = Field(description="The frameworks that apply (GDPR, HIPAA, SOC 2...) and why (markdown).")
    risks: list[RiskItem]


class CostLine(BaseModel):
    item: str = Field(description="A short name, at most six words; details go in the assumptions.")
    amount_usd: float


class YearProjection(BaseModel):
    """The drivers of one year; its revenue and costs are calculated from them."""

    year: int = Field(description="1, 2 or 3.")
    customers: int = Field(description="Paying customers at the end of the year.")
    average_customers: float = Field(description="Average paying customers during the year.")
    one_off_revenue_usd: float = Field(
        description="Revenue outside the monthly price in the year, such as pilot or setup fees; 0 if none."
    )
    fixed_costs_month_usd: float = Field(
        description="Average fixed costs a month during the year (team, tools, hosting, marketing), "
        "without the cost to serve customers."
    )
    cac_usd: float = Field(description="Customer acquisition cost.")


class FinancialPlan(BaseModel):
    """Section 4, written by the Financial Planning Agent."""

    capex: list[CostLine] = Field(description="One-off costs before launch.")
    monthly_opex: list[CostLine] = Field(description="Recurring monthly costs at launch.")
    projections: list[YearProjection] = Field(description="Exactly three years.")
    price_per_customer_month_usd: float
    variable_cost_per_customer_month_usd: float
    discount_rate: float = Field(description="Annual rate for the NPV, for example 0.12.")
    assumptions: str = Field(description="The assumptions behind the figures (markdown).")

    @property
    def years(self) -> list[YearProjection]:
        """The projections in year order, at most three."""
        return sorted(self.projections, key=lambda p: p.year)[:3]

    def revenue(self, year: YearProjection) -> float:
        """Subscriptions over the year, plus its one-off fees."""
        return year.average_customers * self.price_per_customer_month_usd * 12 + year.one_off_revenue_usd

    def opex(self, year: YearProjection) -> float:
        """Fixed costs over the year, plus the cost to serve its customers."""
        return 12 * (year.fixed_costs_month_usd
                     + year.average_customers * self.variable_cost_per_customer_month_usd)


class Kpi(BaseModel):
    category: Literal["Financial", "Technical", "Marketing"]
    metric: str
    target: str


class ExecutivePlan(BaseModel):
    """Sections 1 and 6, written by the Chief of Staff."""

    project_name: str = Field(description="A short name for the project, two to five words.")
    verdict: Literal["Go", "Go with conditions", "Not yet"]
    recommendation: str = Field(
        description="The decision's main reason and its conditions, in 2-3 sentences, without restating the verdict."
    )
    overview: str = Field(description="What the project is and its primary objective, in 2-3 sentences.")
    opportunity: str = Field(description="The market gap or pain point it addresses.")
    strategic_alignment: str = Field(description="How it serves the founder's wider goals.")
    financial_case: str = Field(
        description="What the investment metrics say and what follows from them, in 2-3 sentences. "
        "If the NPV is negative or there is no payback within three years, say so plainly and "
        "why going ahead is still right, or why it is not."
    )
    kpis: list[Kpi]


class Proposal(BaseModel):
    executive: ExecutivePlan
    market: MarketPlan
    technical: TechnicalPlan
    risk: RiskPlan
    financial: FinancialPlan


# Each part's model, by its key in `Proposal`.
PARTS: dict[str, type[BaseModel]] = {
    "executive": ExecutivePlan,
    "market": MarketPlan,
    "technical": TechnicalPlan,
    "risk": RiskPlan,
    "financial": FinancialPlan,
}
# Which agent owns each part.
OWNERS = {
    "executive": "chief",
    "market": "marketing",
    "technical": "technical",
    "risk": "risk",
    "financial": "finance",
}
TITLES = {
    "executive": "Executive Summary and Success Metrics",
    "market": "Market & Marketing Strategy",
    "technical": "Technical & Operational Architecture",
    "risk": "Security, Compliance & Risk",
    "financial": "Financial Plan & Projections",
}


class InvestmentMetrics(BaseModel):
    capex_usd: float
    monthly_fixed_costs_usd: float
    revenue_usd: list[float] = Field(description="Years 1-3.")
    opex_usd: list[float] = Field(description="Years 1-3, including the cost to serve customers.")
    net_cash_flow_usd: list[float] = Field(description="Year 0 (the CapEx) to year 3.")
    net_margin: list[float | None] = Field(description="Years 1-3; None without revenue.")
    npv_usd: float
    irr: float | None = Field(description="None when the cash flows never turn positive.")
    payback_months: float | None = Field(description="None when not paid back within three years.")
    break_even_customers: int | None = Field(description="None when each customer loses money.")


def _npv(rate: float, cash_flows: list[float]) -> float:
    return sum(cash / (1 + rate) ** year for year, cash in enumerate(cash_flows))


def _irr(cash_flows: list[float]) -> float | None:
    """The rate where the NPV is zero, by bisection; None if there is none,
    as when nothing is invested up front or the cash flows never turn positive."""
    low, high = -0.99, 1.0
    while _npv(high, cash_flows) > 0 and high < 1e6:
        high *= 4  # a venture that pays back within months has a very high IRR
    if _npv(low, cash_flows) * _npv(high, cash_flows) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        if _npv(low, cash_flows) * _npv(mid, cash_flows) <= 0:
            high = mid
        else:
            low = mid
    return round((low + high) / 2, 4)


def _payback_months(cash_flows: list[float]) -> float | None:
    """Months until the cumulative cash flow turns non-negative, assuming each
    year's cash arrives evenly; None if it does not within the projection."""
    cumulative = cash_flows[0]
    if cumulative >= 0:
        return 0.0
    for year, cash in enumerate(cash_flows[1:], start=1):
        if cumulative + cash >= 0 and cash > 0:
            return round(12 * (year - 1) + 12 * (-cumulative / cash), 1)
        cumulative += cash
    return None


def describe_irr(metrics: InvestmentMetrics) -> tuple[str, str]:
    """The IRR as shown to a reader, and a note on what it rests on."""
    irr, flows = metrics.irr, metrics.net_cash_flow_usd
    if irr is None:
        if all(cash >= 0 for cash in flows):
            return "None", "nothing is invested up front"
        if all(cash <= 0 for cash in flows):
            return "None", "the cash flows never turn positive"
        return "None", "not defined for these cash flows"
    return ("> 1,000%" if irr > 10 else f"{irr:.0%}"), "on the three-year cash flows"


def describe_payback(metrics: InvestmentMetrics) -> str:
    months = metrics.payback_months
    if months is None:
        return "After year 3"
    if months < 1:
        return "Under a month"
    return f"{months:.0f} month{'' if round(months) == 1 else 's'}"


def describe_break_even(metrics: InvestmentMetrics) -> str:
    customers = metrics.break_even_customers
    if customers is None:
        return "Never"
    return f"{customers:,} customer{'' if customers == 1 else 's'}"


def investment_metrics(plan: FinancialPlan) -> InvestmentMetrics:
    years = plan.years
    capex = sum(line.amount_usd for line in plan.capex)
    fixed = sum(line.amount_usd for line in plan.monthly_opex)
    revenue = [round(plan.revenue(p), 2) for p in years]
    opex = [round(plan.opex(p), 2) for p in years]
    cash_flows = [-capex] + [r - o for r, o in zip(revenue, opex)]
    margin_per_customer = plan.price_per_customer_month_usd - plan.variable_cost_per_customer_month_usd
    return InvestmentMetrics(
        capex_usd=capex,
        monthly_fixed_costs_usd=fixed,
        revenue_usd=revenue,
        opex_usd=opex,
        net_cash_flow_usd=cash_flows,
        net_margin=[round((r - o) / r, 4) if r > 0 else None for r, o in zip(revenue, opex)],
        npv_usd=round(_npv(plan.discount_rate, cash_flows), 2),
        irr=_irr(cash_flows),
        payback_months=_payback_months(cash_flows),
        break_even_customers=math.ceil(fixed / margin_per_customer) if margin_per_customer > 0 else None,
    )


def figure_checks(market: MarketPlan, financial: FinancialPlan) -> list[str]:
    """Where the financial plan's figures disagree with themselves or with the
    market, each as a sentence; empty when they agree."""
    m = investment_metrics(financial)
    years = financial.years
    issues = []
    if years and years[0].fixed_costs_month_usd < 0.9 * m.monthly_fixed_costs_usd:
        issues.append(
            f"Year 1's fixed costs (${years[0].fixed_costs_month_usd:,.0f} a month) are below "
            f"the monthly OpEx at launch (${m.monthly_fixed_costs_usd:,.0f})."
        )
    if years and m.revenue_usd[-1] > 1.1 * market.som.value_usd:
        issues.append(
            f"Year {years[-1].year}'s revenue (${m.revenue_usd[-1]:,.0f}) is more than the "
            f"serviceable obtainable market (${market.som.value_usd:,.0f} a year)."
        )
    for year in years:
        if year.average_customers > 1.5 * max(year.customers, 1):
            issues.append(
                f"Year {year.year}'s average customers ({year.average_customers:g}) are far above "
                f"its year-end count ({year.customers})."
            )
    return issues
