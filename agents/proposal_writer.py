"""The investment proposal, written on demand from a session's report.

Evaluations keep each report short so they stay fast. When the founder asks for
the investment proposal, the agents write it from the report as it now stands
(edits included), each its own part, as structured data (see proposal.py):

1. Marketing, Technical and Risk & Compliance write their parts at the same time.
2. Finance writes the financial plan with the market and technical parts in
   front of it, so the costs agree with the channel budgets, team and stack.
   It starts as soon as those two are done, without waiting for Risk.
3. The Chief of Staff writes the executive summary and success metrics from
   all of them and the investment metrics calculated from Finance's figures.

Finance's figures are checked in code (figure_checks); if a check fails,
Finance gets one more call to correct them before the executive summary is
written, and whatever still fails is shown to the founder. A revision applies
the founder's instruction to one part, or to every part, and then brings the
parts that build on it into line in the same order; or, with revise_text, rewrites one text or one passage of it and leaves
everything else as it is. Every amount is in the report's currency, which the
agents are told and never change (currency.py converts it).
"""

import logging
from concurrent.futures import FIRST_COMPLETED, wait

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables.config import ContextThreadPoolExecutor
from pydantic import BaseModel, Field

import currency
from agents.chief_of_staff import structured_invoke
from agents.roles import ROLES
from document import label, text_at
from guardrails import RULES, fence, unfenced
from llm import CHIEF, LLM_ERRORS, SPECIALIST
from metrics import track
from proposal import (
    OWNERS,
    PARTS,
    TITLES,
    FinancialPlan,
    MarketPlan,
    Proposal,
    describe_break_even,
    describe_irr,
    describe_payback,
    figure_checks,
    investment_metrics,
)
from reports import Report

logger = logging.getLogger(__name__)

SCHEMAS = PARTS
# The order parts are written in. A part starts as soon as the parts it is
# written from (INPUTS) are done, so parts can run beside a later wave's.
WAVES = (("market", "technical", "risk"), ("financial",), ("executive",))
# The parts each part is written from, so its figures agree with them.
INPUTS = {
    "financial": ("market", "technical"),
    "executive": ("market", "technical", "risk", "financial"),
}


class ProposalNotWritten(Exception):
    """A part of a new proposal could not be written, so there is no proposal."""


_STYLE = (
    "Base your part on the team's report below: it went through review and "
    "cross-critique, and the Chief of Staff's decisions on the team's disagreements "
    "are binding. Be specific to this venture: name the customers, prices, tools, "
    "dates and figures. Every figure must agree with the report and with the other "
    "parts you are given; where they give none, estimate it from a stated basis and "
    "mark it '(assumption)'. Write each text field as finished prose for an investor: "
    "markdown with short paragraphs or bullet points and **bold** for the key figures, "
    "but no headings, and no remarks about these instructions, word limits or "
    "revisions. Fields that fill a table cell or label a chart (names, items, stages, "
    "timing, strengths, weaknesses, deliverables, risks and mitigations) are a short "
    "phrase or one sentence of plain text; the reasoning belongs in the prose fields."
)

_PARTS = {
    "market": (
        "Write the Market & Marketing Strategy part of the founder's investment "
        "proposal, which goes to investors and the founder's leadership.\n"
        "- personas: two or three buyer personas. For each, a bold name, then who they "
        "are (role, organisation size or demographics), what they value, their pain "
        "points and what makes them buy now.\n"
        "- tam, sam, som: annual market value, each with its basis showing "
        "the arithmetic (for example '12,000 clinics × 1,800 a year'). SAM is the "
        "part of TAM the launch scope can serve; SOM is what this team can realistically "
        "win within three years, and agrees with the customer numbers in the report. "
        "SOM ≤ SAM ≤ TAM.\n"
        "- competitors: three to five direct and indirect alternatives, including what "
        "customers do today (spreadsheets, an incumbent, nothing), each with an "
        "estimated market share or 'Unknown', and its real strengths and weaknesses "
        "against this offer.\n"
        "- value_proposition: one or two sentences: for whom, the outcome they get, and "
        "why this beats the alternatives.\n"
        "- channels: the two to four channels the launch uses, how each is used and its "
        "monthly budget; together they fit the founder's marketing budget.\n"
        "- pricing_strategy: the model (subscription, usage-based, freemium, enterprise "
        "licence), the price points, and why: the value delivered, competitors' prices "
        "and willingness to pay.\n"
        "- funnel: four to six stages from awareness to retained customers, with monthly "
        "volumes at the end of year one; each stage smaller than the one before, at "
        "conversion rates typical for this market and these channels."
    ),
    "technical": (
        "Write the Technical & Operational Architecture part of the founder's "
        "investment proposal, which goes to investors and the founder's leadership.\n"
        "- infrastructure: the components and how they connect (clients, API, workers, "
        "data stores, third-party services), the cloud provider and services, and the "
        "environments.\n"
        "- stack: languages, frameworks, databases, AI or ML components and third-party "
        "APIs, each with why it was chosen over the obvious alternative; prefer managed "
        "services a small team can run.\n"
        "- scalability: the expected load in year one and year three, how the system "
        "scales and absorbs spikes, the latency target, and the main cost drivers as it "
        "grows.\n"
        "- roadmap: three to five phases covering the first 12 to 24 months (for example "
        "MVP, pilot, general availability, scale), each with its start month, duration "
        "in months and the deliverables that end it; it fits the timeline in the report.\n"
        "- staffing: each role the plan needs, in full-time equivalents (contractors and "
        "part-time roles as fractions), and when; it fits the budget in the report."
    ),
    "risk": (
        "Write the Security, Compliance & Risk part of the founder's investment "
        "proposal, which goes to investors and the founder's leadership.\n"
        "- data_protection: what data the product holds and how sensitive it is; "
        "encryption at rest and in transit (name the standards, such as AES-256 and TLS "
        "1.2+); access control (role-based access, least privilege, multi-factor "
        "authentication); key management, audit logging, backups and data residency.\n"
        "- compliance: which laws and frameworks apply (for example GDPR, HIPAA, SOC 2, "
        "ISO 27001, PCI DSS, sector or local rules) and why, which do not and why, and "
        "what must be in place before launch and what can follow, with costs where the "
        "report gives them.\n"
        "- risks: six to ten risks across the categories that apply (Technical, "
        "Financial, Marketing, Regulatory, Operational). Rate probability and impact "
        "honestly for this venture rather than all High. Each mitigation is a concrete "
        "action with an owner or a trigger, not an intention."
    ),
    "financial": (
        "Write the Financial Plan part of the founder's investment proposal, which goes "
        "to investors and the founder's leadership. Each year's revenue and OpEx, and the "
        "NPV, IRR, payback and break-even, are calculated from your figures, so give the "
        "figures, not those results.\n"
        "- capex: the one-off costs before launch (build, legal and compliance, "
        "equipment, setup), one line each.\n"
        "- monthly_opex: the recurring monthly costs at launch (salaries and "
        "contractors, cloud and tools, marketing, compliance), one line each. They cover "
        "every channel budget and every role in the staffing you are given below; if the "
        "founder's budget cannot pay for them, keep them and show the funding gap in the "
        "assumptions, or cut them and say which.\n"
        "- projections: exactly three years of drivers. Revenue is calculated as the "
        "average paying customers × the monthly price × 12 + the one-off revenue, and OpEx "
        "as (the fixed costs a month + the average paying customers × the variable cost) "
        "× 12. Year one's fixed costs a month start from your monthly OpEx at launch; "
        "later years grow with the team and the channels. The average customers sit "
        "between the counts at the start and the end of the year, and the counts stay "
        "within what the funnel, the channels and the SOM can deliver. CAC is the year's "
        "sales and marketing spend divided by the customers won that year.\n"
        "- price_per_customer_month: the average monthly price per paying customer.\n"
        "- variable_cost_per_customer_month: what one customer costs to serve per "
        "month (hosting, AI calls, payment fees, support).\n"
        "- discount_rate: the annual rate to discount the cash flows, for the venture's "
        "risk: about 0.10 to 0.15 for a project of an established company, 0.25 to 0.40 "
        "for an early-stage startup.\n"
        "- assumptions: bullet points with numbers: the customer ramp, conversion, "
        "churn, hires, salaries and price changes behind each year's drivers. If the plan "
        "needs more money than the founder's budget, state the funding gap and when it "
        "opens."
    ),
}

_EXECUTIVE = (
    "You are the Chief of Staff of a startup founding team. Write the Executive "
    "Summary and the Success Metrics of the founder's investment proposal, which goes "
    "to investors and the founder's leadership, from the team's report, the proposal "
    "parts the specialists wrote and the investment metrics calculated from their "
    "figures, all below. Use only what they say and add no new figures.\n"
    "- verdict: Go, Go with conditions, or Not yet, judged on the evidence: the market, "
    "the unit economics, the investment metrics and the risks. If the NPV is negative "
    "or there is no payback within three years and you still recommend going ahead, "
    "the recommendation must say so and why (for example, that a cheap pilot buys the "
    "evidence before the larger investment); without such a reason the verdict is Not "
    "yet.\n"
    "- recommendation: the decision's main reason and its conditions, in two or three "
    "sentences. The verdict is shown above it, so do not restate it.\n"
    "- overview: what the project is and its primary objective, in two or three "
    "sentences.\n"
    "- opportunity: the gap or pain point it addresses, with the evidence from the "
    "market part.\n"
    "- strategic_alignment: how it serves the founder's wider goals and the "
    "constraints in the request.\n"
    "- financial_case: what the investment metrics say and what follows from them. If "
    "the NPV is negative or there is no payback within three years, say so plainly, "
    "and say why going ahead is still right (for example, that a cheap pilot buys the "
    "evidence before the larger investment) or why it is not.\n"
    "- kpis: six to nine success metrics, two or three each Financial, Technical and "
    "Marketing, each measurable with a target and a date (for example 'Monthly churn: "
    "under 3% by month 6'), taken from the plan's own figures.\n"
    "Write each text field as finished prose for an investor: markdown with short "
    "paragraphs or bullet points and **bold** for the key figures, but no headings, "
    "and no remarks about these instructions, word limits or revisions."
)


def _currency_rule() -> str:
    """Every amount in the document's currency, which only the founder changes."""
    money = currency.current()
    return (
        f"\n\nEvery amount in this document is in {money.code} ({money.name}): write "
        f"each figure as a plain number in it, and amounts in the text with "
        f"'{money.symbol.strip()}'. Never convert between currencies or change the "
        f"currency: the founder does that in the document's settings, where code "
        f"converts every figure."
    )


def _system(part: str, currency_rule: str | None = None) -> str:
    """A part's system prompt, in the document's currency, or with
    `currency_rule` in its place (the template prompt_library.py registers)."""
    rule = _currency_rule() if currency_rule is None else currency_rule
    if part == "executive":
        return _EXECUTIVE + rule + RULES
    return f"{ROLES[OWNERS[part]].brief} {_PARTS[part]}\n{_STYLE}{rule}{RULES}"


def _rewrite_system(role: str, document: str, rule: str) -> str:
    """The system prompt for rewriting one passage, by `role`, of `document`."""
    return (
        f"{role} Revise one passage of the founder's {document} "
        f"exactly as the founder asks, and nothing else. Keep its facts and figures unless the change asks "
        f"for others, keep its markdown style, and add no remarks about the change.{rule}{RULES}"
    )


def prompts() -> dict[str, str]:
    """The proposal's prompts as templates, for Langfuse (prompt_library.py)."""
    templates = {f"proposal/{part}": _system(part, "{{currency_rule}}") for part in SCHEMAS}
    templates["proposal/rewrite"] = _rewrite_system("{{role}}", "{{document}}", "{{currency_rule}}")
    return templates


def _background(report: Report) -> str:
    """The venture and the team's report, as every writer sees them: fenced, as
    the founder wrote or edited them (guardrails.py)."""
    text = f"Startup request:\n{fence(report.title, 'founder')}\n\nObjective: {report.objective}"
    if report.context:
        text += f"\n\n{fence(report.context, 'founder')}"
    sections = "\n\n".join(f"## {s.title}\n{s.body}" for s in report.sections)
    return f"{text}\n\nThe team's report:\n\n{fence(sections, 'the team report')}"


def _money(value: float) -> str:
    return currency.full(value)


def metrics_text(plan: FinancialPlan, market: MarketPlan | None = None) -> str:
    """The calculated investment metrics, as the Chief of Staff is given them,
    and any checks on the figures that still fail."""
    m = investment_metrics(plan)
    revenue = ", ".join(f"year {n}: {_money(v)}" for n, v in enumerate(m.revenue, start=1))
    opex = ", ".join(f"year {n}: {_money(v)}" for n, v in enumerate(m.opex, start=1))
    flows = ", ".join(f"year {year}: {_money(cash)}" for year, cash in enumerate(m.net_cash_flow))
    shown, note = describe_irr(m)
    irr = f"{shown} ({note})"
    payback = (describe_payback(m).lower() if m.payback_months is not None
               else "not within the three years projected")
    break_even = (describe_break_even(m).replace(" customer", " paying customer") if m.break_even_customers
                  else "never (each customer costs more to serve than it pays)")
    return (
        "Investment metrics, calculated from the financial plan:\n"
        f"- Total CapEx: {_money(m.capex)}\n"
        f"- Fixed costs at launch: {_money(m.monthly_fixed_costs)} a month\n"
        f"- Revenue: {revenue}\n"
        f"- OpEx, including the cost to serve customers: {opex}\n"
        f"- Net cash flow (year 0 is the CapEx): {flows}\n"
        f"- NPV at a {plan.discount_rate:.0%} discount rate: {_money(m.npv)}\n"
        f"- IRR: {irr}\n"
        f"- Payback: {payback}\n"
        f"- Break-even: {break_even}"
    ) + _weak_returns(m) + _failing(figure_checks(market, plan) if market else [])


def _weak_returns(m) -> str:
    """A reminder the executive summary must face, when the returns are weak."""
    weak = []
    if m.npv < 0:
        weak.append(f"the NPV is negative ({_money(m.npv)})")
    if m.payback_months is None:
        weak.append("the investment is not paid back within three years")
    if not weak:
        return ""
    return (f"\n\nNote: {' and '.join(weak)}. The financial case must say so plainly, and "
            "if you still recommend going ahead, the recommendation must give the reason.")


def _failing(issues: list[str]) -> str:
    if not issues:
        return ""
    return ("\n\nChecks on the financial figures that still fail (the founder sees them too):\n"
            + "\n".join(f"- {issue}" for issue in issues))


def _costs_to_cover(parts: dict) -> str:
    """What the market and technical parts commit to spending, summed, so the
    financial plan can cover it."""
    lines = []
    if "market" in parts:
        channels = parts["market"].channels
        total = sum(c.monthly_budget for c in channels)
        lines.append(f"- The channels in the market part cost {_money(total)} a month in all: "
                     + "; ".join(f"{c.channel} {_money(c.monthly_budget)}" for c in channels))
    if "technical" in parts:
        technical = parts["technical"]
        fte = sum(s.count for s in technical.staffing)
        lines.append(f"- The staffing in the technical part is {fte:g} FTE: "
                     + "; ".join(f"{s.role}, {s.count:g} FTE, {s.timing}" for s in technical.staffing))
        months = max((p.start_month + p.duration_months - 1 for p in technical.roadmap), default=0)
        lines.append(f"- The technical roadmap runs {months} months.")
    return "What the other parts commit to, which your plan must pay for:\n" + "\n".join(lines)


def _prompt(part: str, background: str, parts: dict, own, instruction: str,
            changed: list[str], issues: list[str] = ()) -> list:
    """The messages for writing `part`; `own` is its current version, if any."""
    human = background
    inputs = [key for key in INPUTS.get(part, ()) if key in parts]
    if inputs:
        written = "\n\n".join(
            f"## {TITLES[key]}\n{parts[key].model_dump_json(indent=1)}" for key in inputs
        )
        human += f"\n\nThe proposal parts the specialists wrote:\n\n{written}"
    if part == "financial":
        human += f"\n\n{_costs_to_cover(parts)}"
    if part == "executive" and "financial" in parts:
        human += f"\n\n{metrics_text(parts['financial'], parts.get('market'))}"
    if own:
        human += f"\n\nYour part as it stands:\n{own.model_dump_json(indent=1)}"
    if instruction:
        human += (f"\n\nThe founder asks for this change:\n{fence(instruction, 'founder')}\n\nApply it "
                  "wherever it concerns your part, and keep the rest as it stands.")
    if changed:
        human += (f"\n\nThese parts were just revised: {', '.join(TITLES[k] for k in changed)}. "
                  "Bring your part into line with them where it must change, and keep the "
                  "rest as it stands.")
    if issues:
        human += ("\n\nYour figures fail these checks, calculated from them:\n"
                  + "\n".join(f"- {issue}" for issue in issues)
                  + "\n\nCorrect the figures so they pass, and keep the rest as it stands.")
    return [SystemMessage(_system(part)), HumanMessage(human)]


def _ask(key: str, messages: list, tracker):
    """One structured call for a part; None, logged, if it fails."""
    role = CHIEF if key == "executive" else SPECIALIST
    try:
        return structured_invoke(SCHEMAS[key], messages, tracker, role, f"proposal/{key}")
    except LLM_ERRORS as error:
        logger.warning("Proposal part %s failed: %s", key, error)
        return None


def parts_to_write(current: Proposal | None, part: str | None) -> list[str]:
    """Every part for a new proposal or a whole-proposal revision; else `part`
    and the parts written from it, in writing order."""
    if current is None or part is None:
        return [key for wave in WAVES for key in wave]
    redo = {part}
    for wave in WAVES:
        for key in wave:
            if redo & set(INPUTS.get(key, ())):
                redo.add(key)
    return [key for wave in WAVES for key in wave if key in redo]


def write_proposal(report: Report, instruction: str = "",
                   part: str | None = None) -> tuple[Proposal, list[str]]:
    """Write the report's investment proposal, or revise the one it has.

    Without a proposal every part is written; `instruction`, if given, applies to
    all of them. With one, `instruction` is applied to `part` (every part if
    None) and the parts written from it are brought into line. Returns the
    proposal and the titles of the parts that could not be revised, which keep
    their text. Raises ProposalNotWritten if a part of a new proposal fails.
    Every amount is in the report's currency.
    """
    with currency.using(report.settings.currency):
        return _write_proposal(report, instruction, part)


def _write_proposal(report: Report, instruction: str, part: str | None) -> tuple[Proposal, list[str]]:
    current = report.proposal
    redo = parts_to_write(current, part)
    background = _background(report)
    parts = {key: getattr(current, key) for key in SCHEMAS} if current else {}
    failed: list[str] = []

    metrics: dict = {}
    with track("proposal", metrics) as tracker:

        def write(key: str):
            told = instruction if (part is None or key == part) else ""
            changed = [k for k in INPUTS.get(key, ()) if k in redo] if current else []
            own = getattr(current, key) if current else None
            value = _ask(key, _prompt(key, background, parts, own, told, changed), tracker)
            if key == "financial" and value is not None:
                # Check: Finance corrects figures that disagree, once.
                issues = figure_checks(parts["market"], value)
                if issues:
                    logger.info("Financial figures fail checks, asking for a correction: %s", issues)
                    messages = _prompt("financial", background, parts, value, "", [], issues)
                    value = _ask("financial", messages, tracker) or value
            return value

        # Each part waits only for the parts it is written from that are being
        # rewritten; `parts` changes only here, never in the workers.
        waiting = {key: set(INPUTS.get(key, ())) & set(redo) for key in redo}
        running: dict = {}
        with ContextThreadPoolExecutor(max_workers=len(redo)) as pool:
            while waiting or running:
                for key in [key for key, needs in waiting.items() if not needs]:
                    del waiting[key]
                    running[pool.submit(write, key)] = key
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    key = running.pop(future)
                    value = future.result()
                    if value is not None:
                        parts[key] = value
                    elif current is None:
                        raise ProposalNotWritten(f"The {TITLES[key]} part could not be written.")
                    else:
                        failed.append(TITLES[key])
                    for needs in waiting.values():
                        needs.discard(key)
    failed = [TITLES[key] for key in redo if TITLES[key] in failed]  # in writing order

    metric = metrics["proposal"]
    logger.info(
        "Proposal for %s (%s): %d calls, %d tokens, %.1f s",
        report.session_id, ", ".join(redo), metric.calls, metric.tokens, metric.seconds,
    )
    return Proposal(**parts), failed


class Rewritten(BaseModel):
    text: str = Field(description="The rewritten text, as finished markdown in the same style.")


# Who rewrites a section of the team's report: its writer, or the Chief of Staff.
SECTION_OWNERS = {name: name for name in ("marketing", "finance", "technical", "risk")}


def _owner(path: str) -> str:
    parts = path.split(".")
    if parts[0] == "proposal" and len(parts) > 1 and parts[1] in OWNERS:
        return OWNERS[parts[1]]
    if parts[0] == "sections" and len(parts) > 1:
        return SECTION_OWNERS.get(parts[1], "chief")
    return "chief"


def revise_text(report: Report, path: str, instruction: str, passage: str | None = None) -> str:
    """One field of the report rewritten as the founder asks by the agent who
    wrote it, or only `passage` of it; returns the field's new text, the rest
    of it as it was. Every other field is left alone: a granular change, unlike
    revising a whole part. Raises an LLM error if the call fails."""
    with currency.using(report.settings.currency):
        current = text_at(report, path)
        owner = _owner(path)
        role = "You are the Chief of Staff of a startup founding team." if owner == "chief" else ROLES[owner].brief
        document = "investment proposal" if path.startswith("proposal") else "report"
        system = _rewrite_system(role, document, _currency_rule())
        where = label(report, path)
        human = f"{_background(report)}\n\nThe part to revise is {where}. It reads:\n{fence(current, 'the team report')}"
        if passage:
            human += (f"\n\nRewrite only this passage of it, and return just the passage rewritten:\n"
                      f"{fence(passage, 'the team report')}")
        else:
            human += "\n\nReturn the whole of it rewritten."
        human += f"\n\nThe founder asks for this change:\n{fence(instruction, 'founder')}"
        role_kind = CHIEF if owner == "chief" else SPECIALIST
        metrics: dict = {}
        with track("revise", metrics) as tracker:
            rewritten = structured_invoke(Rewritten, [SystemMessage(system), HumanMessage(human)], tracker, role_kind, "proposal/rewrite")
        text = unfenced(rewritten.text).strip()
        logger.info("Revised %s for %s: %d calls, %d tokens", where, report.session_id,
                    metrics["revise"].calls, metrics["revise"].tokens)
        if passage:
            return current.replace(passage, text, 1)
        return text
