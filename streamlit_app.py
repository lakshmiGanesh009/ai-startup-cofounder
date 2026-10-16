"""Streamlit UI for the AI Startup Co-Founder Team.

A thin client over the FastAPI backend: it posts a request to /evaluate and
shows the plan, the specialists' reports, the reviews, the settled conflicts,
the metrics and the launch strategy. A follow-up reuses the session, so only
the specialists it affects rerun. This is the working UI until the Next.js app
in frontend/ is built.

Start the backend (uv run python main.py), then:
    uv run --group ui streamlit run streamlit_app.py
"""

import json
import os
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
# A full evaluation makes many LLM calls and can take a few minutes.
EVALUATE_TIMEOUT = httpx.Timeout(600, connect=5)
SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
NO_SCENARIO = "(none)"
CONTEXT_FIELDS = {
    "target_market": "Target market",
    "constraints": "Constraints (budget, timeline)",
    "competitive_landscape": "Competitive landscape",
}


def backend_service() -> str | None:
    """The backend's service name if /health answers, else None."""
    try:
        response = httpx.get(f"{API_URL}/health", timeout=2)
        return response.json()["service"] if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def evaluate(prompt: str, context: dict, session_id: str | None) -> dict:
    """Run the founding team through the API; raise RuntimeError with the reason."""
    body = {"prompt": prompt, "context": context or None, "session_id": session_id}
    try:
        response = httpx.post(f"{API_URL}/evaluate", json=body, timeout=EVALUATE_TIMEOUT)
    except httpx.HTTPError as error:
        raise RuntimeError(f"Could not reach the backend at {API_URL}: {error}") from error
    if response.status_code != 200:
        try:
            detail = response.json()["detail"]
        except (ValueError, KeyError):
            detail = response.text
        raise RuntimeError(f"The backend returned {response.status_code}: {detail}")
    return response.json()


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


def start_new_session() -> None:
    for key in ("session_id", "runs"):
        st.session_state.pop(key, None)


def run(prompt: str, context: dict) -> bool:
    """Send one request in the current session and keep its result.

    Returns False, with the reason shown, if the request failed.
    """
    with st.spinner("The founding team is working. This takes a minute or two."):
        try:
            result = evaluate(prompt, context, st.session_state.get("session_id"))
        except RuntimeError as error:
            st.error(str(error))
            return False
    st.session_state.session_id = result["session_id"]
    st.session_state.setdefault("runs", []).append({"prompt": prompt, "result": result})
    return True


def show_result(result: dict) -> None:
    metrics = result["metrics"]
    calls = sum(metric["calls"] for metric in metrics.values())
    tokens = sum(metric["tokens"] for metric in metrics.values())
    st.caption(f"Objective: {result['objective']} · {calls} LLM calls · {tokens:,} tokens")
    st.markdown(result["final_strategy"])

    plan, reports, reviews, conflicts, cost = st.tabs(
        ["Plan", "Reports", "Reviews", "Conflicts", "Metrics"]
    )
    with plan:
        for name, task in result["assignments"].items():
            st.markdown(f"**{name.title()}:** {task}")
    with reports:
        for name, report in result["analyses"].items():
            with st.expander(name.title()):
                st.markdown(report)
    with reviews:
        for round_no, verdicts in enumerate(result["review_history"], start=1):
            st.markdown(f"**Round {round_no}**")
            st.table(
                [
                    {
                        "specialist": name,
                        "approved": verdict["approved"],
                        "score": verdict["score"],
                        "feedback": verdict["feedback"],
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
                f"{conflict['issue']}\n\n"
                f"Decision: {resolution['decision']} "
                f"(revises: {resolution['revise'] or 'no one'})"
            )
    with cost:
        st.table([{"node": node, **metric} for node, metric in metrics.items()])


st.set_page_config(page_title="AI Startup Co-Founder Team", layout="wide")
st.title("AI Startup Co-Founder Team")

with st.sidebar:
    st.subheader("Backend")
    service = backend_service()
    if service:
        st.success(f"Connected to {API_URL}")
    else:
        st.error(f"Can't reach {API_URL}. Start it with `uv run python main.py`.")
    if st.session_state.get("session_id"):
        st.caption(f"Session {st.session_state.session_id}")
        st.button("Start a new session", on_click=start_new_session)

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
        with st.expander(f"Request {number}: {past['prompt']}"):
            show_result(past["result"])
    st.subheader(f"Request {len(runs)}: {runs[-1]['prompt']}")
    show_result(runs[-1]["result"])

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
