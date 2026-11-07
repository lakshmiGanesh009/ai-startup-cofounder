"""Tests for what is calculated from a proposal's financial plan: each year's
revenue and costs, and the investment metrics."""

import pytest

from proposal import (
    CostLine,
    FinancialPlan,
    MarketSize,
    YearProjection,
    _npv,
    describe_break_even,
    describe_irr,
    describe_payback,
    figure_checks,
    investment_metrics,
)
from tests.sample_proposal import SAMPLE

# (average customers, one-off revenue, fixed costs a month) for years 1-3.
DRIVERS = [(5, 4_000, 1_000), (20, 0, 1_000), (50, 0, 2_000)]


def _plan(drivers=DRIVERS, price=100.0, cost=20.0, rate=0.1):
    return FinancialPlan(
        capex=[CostLine(item="Build", amount=10_000)],
        monthly_opex=[CostLine(item="Team", amount=1_000)],
        projections=[
            YearProjection(year=year, customers=int(average * 1.5), average_customers=average,
                           one_off_revenue=one_off, fixed_costs_month=fixed, cac=100)
            for year, (average, one_off, fixed) in enumerate(drivers, start=1)
        ],
        price_per_customer_month=price,
        variable_cost_per_customer_month=cost,
        discount_rate=rate,
        assumptions="",
    )


def test_each_years_revenue_and_costs_follow_from_its_drivers():
    m = investment_metrics(_plan())

    # 5 customers × $100 × 12 + $4,000 of pilot fees, then 20 and 50 customers.
    assert m.revenue == [10_000, 24_000, 60_000]
    # ($1,000 fixed + 5 customers × $20 to serve) × 12, and so on.
    assert m.opex == [13_200, 16_800, 36_000]
    assert m.net_cash_flow == [-10_000, -3_200, 7_200, 24_000]
    assert m.net_margin == [-0.32, 0.3, 0.4]


def test_the_investment_metrics_follow_from_the_cash_flows():
    m = investment_metrics(_plan())

    # -10,000 - 3,200/1.1 + 7,200/1.21 + 24,000/1.331
    assert m.npv == pytest.approx(11_072.88, abs=0.01)
    assert m.irr is not None
    assert _npv(m.irr, m.net_cash_flow) == pytest.approx(0, abs=5)
    # 6,000 still to recover after year 2; year 3 brings in 24,000, 2,000 a month.
    assert m.payback_months == pytest.approx(27.0)
    # $1,000 of fixed costs a month over an $80 contribution per customer.
    assert m.break_even_customers == 13


def test_a_venture_that_never_pays_back():
    m = investment_metrics(_plan(drivers=[(0, 0, 1_000), (1, 0, 1_000), (2, 0, 1_000)], cost=150))

    assert m.irr is None
    assert m.payback_months is None
    assert m.net_margin[0] is None  # no revenue, no margin
    assert m.break_even_customers is None  # each customer costs more than it pays
    assert m.npv < 0


def test_the_projections_are_read_in_year_order():
    plan = _plan()
    plan.projections.reverse()

    assert investment_metrics(plan).net_cash_flow == [-10_000, -3_200, 7_200, 24_000]


def test_figures_that_disagree_are_flagged():
    market = SAMPLE.market.model_copy(update={"som": MarketSize(value=50_000, basis="Small.")})
    # Year 1 runs on less than the launch costs, year 3 earns more than the SOM,
    # and year 2's average customers are far above its year-end count.
    plan = _plan(drivers=[(5, 4_000, 500), (40, 0, 1_000), (50, 0, 2_000)])
    plan.projections[1].customers = 10

    issues = figure_checks(market, plan)

    assert issues == [
        "Year 1's fixed costs ($500 a month) are below the monthly OpEx at launch ($1,000).",
        "Year 3's revenue ($60,000) is more than the serviceable obtainable market ($50,000 a year).",
        "Year 2's average customers (40) are far above its year-end count (10).",
    ]
    assert figure_checks(SAMPLE.market, SAMPLE.financial) == []


def test_the_irr_of_a_venture_that_pays_back_in_months():
    # $4,800 in, $89,920 back in year one: an IRR far above 1,000%, not "none".
    plan = _plan(drivers=[(80, 0, 1_000), (80, 0, 1_000), (80, 0, 1_000)])
    plan.capex = [CostLine(item="Setup", amount=4_800)]
    m = investment_metrics(plan)

    assert m.irr is not None and m.irr > 10
    assert _npv(m.irr, m.net_cash_flow) == pytest.approx(0, abs=1)
    assert describe_irr(m) == ("> 1,000%", "on the three-year cash flows")
    assert describe_irr(investment_metrics(_plan(drivers=[(0, 0, 1_000)] * 3)))[1] == (
        "the cash flows never turn positive"
    )


def test_the_metrics_read_as_words():
    plan = _plan(drivers=[(80, 0, 1_000)] * 3)
    plan.capex = [CostLine(item="Setup", amount=4_800)]  # back in 0.9 months
    quick = investment_metrics(plan)

    assert describe_payback(quick) == "Under a month"
    assert describe_break_even(quick.model_copy(update={"break_even_customers": 1})) == "1 customer"
    assert describe_payback(investment_metrics(_plan())) == "27 months"
    assert describe_break_even(investment_metrics(_plan())) == "13 customers"


def test_an_irr_that_cannot_be_worked_out_says_why():
    from proposal import InvestmentMetrics

    def metrics(flows):
        return InvestmentMetrics(capex=0, monthly_fixed_costs=0, revenue=[], opex=[],
                                 net_cash_flow=flows, net_margin=[], npv=0, irr=None,
                                 payback_months=None, break_even_customers=None)

    assert describe_irr(metrics([0, 5_000, 5_000, 5_000]))[1] == "nothing is invested up front"
    # Money in, money out, money in again: more than one rate fits, or none does.
    assert describe_irr(metrics([-1_000, 5_000, -5_000, 0]))[1] == "not defined for these cash flows"
