"""A filled-in investment proposal, as the agents would write it, for tests."""

from proposal import (
    Channel,
    Competitor,
    CostLine,
    ExecutivePlan,
    FinancialPlan,
    FunnelStage,
    Kpi,
    MarketPlan,
    MarketSize,
    Phase,
    Proposal,
    RiskItem,
    RiskPlan,
    StaffLine,
    TechnicalPlan,
    YearProjection,
)

EXECUTIVE = ExecutivePlan(
    project_name="FollowUp Assist",
    verdict="Go with conditions",
    recommendation=(
        "Launch a **paid pilot with 5 clinics at $149 a month** within the $15k budget, "
        "and commit to a wider launch only if 3 of 5 convert to paid by month 4."
    ),
    overview=(
        "An assistant that drafts patient follow-up appointments from clinical notes and "
        "books them into the clinic's calendar. The objective is to prove that small "
        "clinics pay for fewer missed follow-ups within six months."
    ),
    opportunity=(
        "Small outpatient clinics lose **10-20% of follow-ups** to manual scheduling; EHR "
        "add-ons are priced for large groups and reminder tools do not read notes."
    ),
    strategic_alignment=(
        "Fits a solo founder's **six-month runway**: a narrow product sold to a niche the "
        "founder can reach directly, with no hardware and managed services only."
    ),
    financial_case=(
        "The plan earns back its **$12k** within two years and has a positive NPV at a 30% "
        "discount rate; the pilot gate limits the loss to the pilot budget if clinics do not convert."
    ),
    kpis=[
        Kpi(category="Financial", metric="Monthly recurring revenue", target="$745 by month 6"),
        Kpi(category="Financial", metric="Gross margin", target="Above 80% by month 6"),
        Kpi(category="Technical", metric="Draft accuracy", target="90% accepted unedited by month 4"),
        Kpi(category="Technical", metric="Uptime", target="99.5% from launch"),
        Kpi(category="Marketing", metric="Pilot conversion", target="3 of 5 clinics paying by month 4"),
        Kpi(category="Marketing", metric="Monthly churn", target="Under 3% by month 9"),
    ],
)

MARKET = MarketPlan(
    personas=(
        "**Practice manager Maria** runs a 3-doctor clinic; values calm days and full "
        "calendars; loses an hour a day chasing follow-ups.\n\n"
        "**Dr. Okafor, owner-physician**, wants fewer no-shows without new software to learn."
    ),
    tam=MarketSize(value=216_000_000, basis="120,000 US outpatient clinics × $1,800 a year"),
    sam=MarketSize(value=32_400_000, basis="18,000 independent clinics with 1-5 doctors × $1,800"),
    som=MarketSize(value=540_000, basis="300 clinics won in three years × $1,800"),
    competitors=[
        Competitor(name="EHR scheduling add-ons", kind="Direct", market_share="~40%",
                   strengths="Already installed", weaknesses="Costly, built for large groups"),
        Competitor(name="Reminder tools", kind="Indirect", market_share="~15%",
                   strengths="Cheap, simple", weaknesses="Do not read clinical notes"),
        Competitor(name="Front-desk staff", kind="Indirect", market_share="Unknown",
                   strengths="Flexible", weaknesses="Slow, error-prone"),
    ],
    value_proposition=(
        "For small clinics, follow-ups booked from the note in seconds, so fewer patients "
        "fall through the cracks, at a tenth of an EHR add-on's price."
    ),
    channels=[
        Channel(channel="Direct outreach", approach="Founder calls 20 clinics a week", monthly_budget=200),
        Channel(channel="Practice-manager communities", approach="Posts and a webinar a month",
                monthly_budget=300),
    ],
    pricing_strategy="**$149 per clinic per month**, flat; pilot at $49 for the first two months.",
    funnel=[
        FunnelStage(stage="Awareness", monthly_volume=400),
        FunnelStage(stage="Lead", monthly_volume=60),
        FunnelStage(stage="Demo", monthly_volume=20),
        FunnelStage(stage="Paid", monthly_volume=8),
        FunnelStage(stage="Retained", monthly_volume=7),
    ],
)

TECHNICAL = TechnicalPlan(
    infrastructure="A web app and API on **Azure App Service**, a Postgres database and a queue for drafting jobs.",
    stack="Python and FastAPI, Postgres, Azure OpenAI for drafting, Google and Outlook calendar APIs.",
    scalability="Year one: 50 clinics, ~2,000 notes a day; the drafting workers scale out on queue length.",
    roadmap=[
        Phase(name="Phase 1: MVP", start_month=1, duration_months=2, deliverables="Drafts from notes, manual approval"),
        Phase(name="Phase 2: Pilot", start_month=3, duration_months=3, deliverables="5 clinics live, calendar booking"),
        Phase(name="Phase 3: Launch", start_month=6, duration_months=6, deliverables="Self-serve sign-up, billing"),
    ],
    staffing=[
        StaffLine(role="Founder (product and sales)", count=1, timing="Months 1-12"),
        StaffLine(role="Contract developer", count=0.5, timing="Months 1-6"),
    ],
)

RISK = RiskPlan(
    data_protection="Notes are PHI: **AES-256 at rest, TLS 1.2+ in transit**, role-based access with MFA.",
    compliance="**HIPAA applies**: BAAs with Azure and every vendor before any real patient data.",
    risks=[
        RiskItem(category="Regulatory", description="PHI handled without a BAA", probability="Low",
                 impact="High", mitigation="No real data until BAAs are signed"),
        RiskItem(category="Technical", description="Drafts misread the note", probability="Medium",
                 impact="Medium", mitigation="Staff approve every draft in the pilot"),
        RiskItem(category="Marketing", description="Clinics will not pay after the pilot", probability="Medium",
                 impact="High", mitigation="Pilot priced, with a conversion gate at month 4"),
        RiskItem(category="Financial", description="Runway ends before revenue", probability="Medium",
                 impact="High", mitigation="Spending capped at $15k; stop at month 4 without 3 paying"),
        RiskItem(category="Operational", description="Solo founder is a single point of failure",
                 probability="High", impact="Medium", mitigation="Contractor documents and can run the system"),
    ],
)

FINANCIAL = FinancialPlan(
    capex=[
        CostLine(item="MVP build (contract developer)", amount=9_000),
        CostLine(item="HIPAA review and BAAs", amount=2_500),
        CostLine(item="Setup and tools", amount=500),
    ],
    monthly_opex=[
        CostLine(item="Cloud and AI", amount=250),
        CostLine(item="Marketing", amount=500),
        CostLine(item="Software tools", amount=100),
    ],
    projections=[
        YearProjection(year=1, customers=12, average_customers=6, one_off_revenue=490,
                       fixed_costs_month=850, cac=500),
        YearProjection(year=2, customers=60, average_customers=36, one_off_revenue=0,
                       fixed_costs_month=3_000, cac=400),
        YearProjection(year=3, customers=160, average_customers=110, one_off_revenue=0,
                       fixed_costs_month=8_000, cac=350),
    ],
    price_per_customer_month=149,
    variable_cost_per_customer_month=20,
    discount_rate=0.3,
    assumptions="- Year 1: 12 clinics by year end, averaging 6.7 paying × $149 × 12 ≈ **$12k**.\n- Churn 3% a month.",
)

SAMPLE = Proposal(
    executive=EXECUTIVE, market=MARKET, technical=TECHNICAL, risk=RISK, financial=FINANCIAL
)
