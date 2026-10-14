"""Role definitions for the specialists.

A `Role` is the name a specialist is keyed by in the state, plus the system
prompt that gives it its point of view. Step 2 defines Marketing; the other
three roles arrive in Step 3.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    """A specialist's identity and point of view."""

    name: str
    system_prompt: str


MARKETING = Role(
    name="marketing",
    system_prompt=(
        "You are the Marketing Strategy Agent on a startup founding team. "
        "Judge the idea on customer niches, positioning, demand, and go-to-market. "
        "Recommend one niche to test first and the next step to validate demand. "
        "Stay within marketing; leave finance, technical build, and risk to the others. "
        "Be specific to the request. Answer in a few short, concrete points."
    ),
)
