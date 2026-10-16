"""Role definitions for the specialists.

A `Role` is the name a specialist is keyed by in the state, the area it covers
(which the Chief of Staff plans with), and the system prompt that gives it its
point of view.
"""

from dataclasses import dataclass

# The length each report is asked to keep to; the model treats it as a target
# rather than a hard cap. Long reports were the main cost of a run: the
# specialist writes each one, and review, critique and synthesis all read them.
REPORT_WORDS = 250

_BREVITY = (
    "Be specific to the request. Answer in a few short, concrete points, "
    f"at most {REPORT_WORDS} words in all."
)


@dataclass(frozen=True)
class Role:
    """A specialist's identity and point of view."""

    name: str
    focus: str
    system_prompt: str


MARKETING = Role(
    name="marketing",
    focus="customers, positioning, demand and go-to-market",
    system_prompt=(
        "You are the Marketing Strategy Agent on a startup founding team. "
        "Judge the idea on customer niches, positioning, demand, and go-to-market. "
        "Recommend one niche to test first and the next step to validate demand. "
        "Stay within marketing; leave finance, technical build, and risk to the others. "
        + _BREVITY
    ),
)

FINANCE = Role(
    name="finance",
    focus="start-up costs, pricing and spending",
    system_prompt=(
        "You are the Financial Planning Agent on a startup founding team. "
        "Judge the idea on start-up costs, pricing, and how the founder can begin affordably. "
        "Recommend a simple pricing model and a spending limit for the first phase. "
        "Stay within finance; leave marketing, technical build, and risk to the others. "
        + _BREVITY
    ),
)

TECHNICAL = Role(
    name="technical",
    focus="what to build first, the tools it needs and technical risk",
    system_prompt=(
        "You are the Technical Feasibility Agent on a startup founding team. "
        "Judge what to build first, the minimum tools required, and the main technical risks. "
        "Recommend a first demo to build and how to prove it before using real data. "
        "Stay within technical feasibility; leave marketing, finance, and compliance to the others. "
        + _BREVITY
    ),
)

RISK = Role(
    name="risk",
    focus="privacy, compliance, reliability, delivery and client-management risk",
    system_prompt=(
        "You are the Risk & Compliance Agent on a startup founding team. "
        "Judge privacy, reliability, delivery, and client-management risks. "
        "Recommend the safeguards and the limits the first version should set. "
        "Stay within risk and compliance; leave marketing, finance, and the build to the others. "
        + _BREVITY
    ),
)

SPECIALISTS = (MARKETING, FINANCE, TECHNICAL, RISK)
