"""The reasoning sliders in the sidebar, and the efforts they set.

The specialists and the Chief of Staff each get a slider. Every request a page
sends (an evaluation, writing or revising the proposal) carries the efforts
they show. The sliders start at the efforts the backend is configured with, and
are disabled when its provider takes no reasoning effort (only Azure does).
"""

import streamlit as st

EFFORTS = ["minimal", "low", "medium", "high"]
KEYS = {"specialist": "effort_specialist", "chief": "effort_chief"}
ADJUSTABLE = "effort_adjustable"
# Measured per call on the team's Azure gpt-5-mini deployment (docs/performance.md).
PER_CALL = {"minimal": "~4 s", "low": "~6 s", "medium": "~9 s", "high": "~27 s"}


def sidebar(health: dict | None) -> None:
    """Draw the sliders, starting from the backend's configured efforts."""
    settings = (health or {}).get("reasoning") or {}
    adjustable = bool(settings.get("adjustable"))
    st.session_state[ADJUSTABLE] = adjustable
    st.subheader("Reasoning")
    labels = {
        "specialist": ("Specialists", ("Marketing, finance, technical and risk: their reports, "
                                       "critiques and proposal parts.")),
        "chief": ("Chief of Staff", ("Planning, reviews, decisions on conflicts, the strategy "
                                     "and the proposal's executive summary.")),
    }
    for role, (label, help_text) in labels.items():
        default = settings.get(role)
        st.session_state.setdefault(KEYS[role], default if default in EFFORTS else EFFORTS[0])
        st.select_slider(label, EFFORTS, key=KEYS[role], disabled=not adjustable,
                         help=f"{help_text} Per call: " + ", ".join(
                             f"{effort} {seconds}" for effort, seconds in PER_CALL.items()))
    if adjustable:
        st.caption("Higher reasoning gives more considered answers but slower calls. "
                   f"{wait('evaluation')}")
    else:
        st.caption("This provider takes no reasoning setting; only Azure OpenAI does.")


def chosen() -> dict | None:
    """The efforts to send with a request, or None to use the backend's own."""
    if not st.session_state.get(ADJUSTABLE):
        return None
    return {role: st.session_state.get(key) for role, key in KEYS.items()}


# How long a request takes, by the highest effort chosen.
WAITS = {
    "high": {"evaluation": "An evaluation at high reasoning takes 5 to 10 minutes.",
             "proposal": "Writing the proposal at high reasoning takes several minutes."},
    "medium": {"evaluation": "An evaluation takes about two minutes.",
               "proposal": "Writing the proposal takes about two minutes."},
    "low": {"evaluation": "An evaluation takes about a minute.",
            "proposal": "Writing the proposal takes a minute or two."},
}


def wait(what: str) -> str:
    """How long `what` ("evaluation" or "proposal") takes at the chosen efforts."""
    efforts = set((chosen() or {}).values())
    level = next((e for e in ("high", "medium") if e in efforts), "low")
    return WAITS[level][what]
