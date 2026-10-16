"""Evaluate page: run the founding team on an idea, then send follow-ups.

It shows the plan, the specialists' reports, the reviews, the settled conflicts,
the metrics and the launch strategy. A follow-up reuses the session, so only the
specialists it affects rerun.
"""

import json
from pathlib import Path

import streamlit as st

from ui import api

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"
NO_SCENARIO = "(none)"
CONTEXT_FIELDS = {
    "target_market": "Target market",
    "constraints": "Constraints (budget, timeline)",
    "competitive_landscape": "Competitive landscape",
}


def load_scenario() -> None:
    """Copy the chosen scenario into the request fields."""
    name = st.session_state.scenario
    if name == NO_SCENARIO:
        return
    scenario = json.loads((SCENARIO_DIR / f"{name}.json").read_text(encoding="utf-8"))
    st.session_state.prompt = scenario["prompt"]
    for field in CONTEXT_FIELDS:
        st.session_state[field] = scenario.get("context", {}).get(field, "")
    st.session_state.follow_up = scenario.get("follow_up", "")


def literal(text: str) -> str:
    """Escape `$` so Streamlit shows it rather than starting a LaTeX formula.

    Reports and strategies are full of prices; unescaped, the text between two
    dollar signs ("$7k vs $12k") is rendered as a formula.
    """
    return text.replace("$", "\\$")


def run(prompt: str, context: dict) -> bool:
    """Send one request in the current session and keep its result.

    Returns False, with the reason shown, if the request failed.
    """
    with st.spinner("The founding team is working. This takes a minute or two."):
        try:
            result = api.evaluate(prompt, context, st.session_state.get("session_id"))
        except api.ApiError as error:
            st.error(str(error))
            return False
    st.session_state.session_id = result["session_id"]
    st.session_state.setdefault("runs", []).append({"prompt": prompt, "result": result})
    return True


def show_result(result: dict) -> None:
    metrics = result["metrics"]
    calls = sum(metric["calls"] for metric in metrics.values())
    tokens = sum(metric["tokens"] for metric in metrics.values())
    st.caption(
        f"Objective: {literal(result['objective'])} · {calls} LLM calls · {tokens:,} tokens"
    )
    st.markdown(literal(result["final_strategy"]))

    plan, reports, reviews, conflicts, cost = st.tabs(
        ["Plan", "Reports", "Reviews", "Conflicts", "Metrics"]
    )
    with plan:
        for name, task in result["assignments"].items():
            st.markdown(f"**{name.title()}:** {literal(task)}")
    with reports:
        for name, report in result["analyses"].items():
            with st.expander(name.title()):
                st.markdown(literal(report))
    with reviews:
        for round_no, verdicts in enumerate(result["review_history"], start=1):
            st.markdown(f"**Round {round_no}**")
            st.table(
                [
                    {
                        "specialist": name,
                        "approved": verdict["approved"],
                        "score": verdict["score"],
                        "feedback": literal(verdict["feedback"]),
                    }
                    for name, verdict in verdicts.items()
                ]
            )
    with conflicts:
        if not result["resolutions"]:
            st.write("No conflicts were raised.")
        for resolution in result["resolutions"]:
            conflict = resolution["conflict"]
            st.markdown(
                f"**{conflict['raised_by'].title()} vs {conflict['about'].title()}:** "
                f"{literal(conflict['issue'])}\n\n"
                f"Decision: {literal(resolution['decision'])} "
                f"(revises: {resolution['revise'] or 'no one'})"
            )
    with cost:
        st.table([{"node": node, **metric} for node, metric in metrics.items()])


st.title("AI Startup Co-Founder Team")
runs = st.session_state.get("runs", [])

if not runs:
    st.selectbox(
        "Start from a scenario",
        [NO_SCENARIO, *(path.stem for path in sorted(SCENARIO_DIR.glob("*.json")))],
        key="scenario",
        on_change=load_scenario,
    )
    with st.form("request"):
        prompt = st.text_area("Startup idea or request", key="prompt", height=100)
        with st.expander("Context (optional)"):
            context = {
                field: st.text_input(label, key=field) for field, label in CONTEXT_FIELDS.items()
            }
        submitted = st.form_submit_button("Evaluate", type="primary")
    if submitted:
        if not prompt.strip():
            st.warning("Describe the idea or what you want the team to do.")
        elif run(prompt.strip(), {k: v.strip() for k, v in context.items() if v.strip()}):
            st.rerun()  # show the result in place of the form
else:
    # Earlier requests stay available but collapsed; the latest is shown in full.
    for number, past in enumerate(runs[:-1], start=1):
        with st.expander(f"Request {number}: {literal(past['prompt'])}"):
            show_result(past["result"])
    st.subheader(f"Request {len(runs)}: {literal(runs[-1]['prompt'])}")
    show_result(runs[-1]["result"])
    st.page_link(
        "ui/reports_page.py",
        label="Edit this session's report and download it as a PDF",
        icon=":material/description:",
    )

    st.divider()
    with st.form("follow-up", clear_on_submit=True):
        follow_up = st.text_input(
            "Follow-up in this session",
            key="follow_up",
            placeholder="Refine the pricing strategy after financial review.",
        )
        sent = st.form_submit_button("Send follow-up", type="primary")
    if sent and follow_up.strip() and run(follow_up.strip(), {}):
        st.rerun()
