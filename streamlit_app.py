"""Streamlit UI for the AI Startup Co-Founder Team.

A thin client over the FastAPI backend, in two pages:

- Evaluate (ui/evaluate_page.py): run the founding team on an idea and send
  follow-ups in the same session.
- Reports (ui/reports_page.py): edit each session's written report beside a
  live PDF preview, have the agents write a detailed version, and download it.

This is the working UI until the Next.js app in frontend/ is built.

Start the backend (uv run python main.py), then:
    uv run --group ui streamlit run streamlit_app.py
"""

import streamlit as st

from ui import api


def start_new_session() -> None:
    for key in ("session_id", "runs"):
        st.session_state.pop(key, None)


st.set_page_config(page_title="AI Startup Co-Founder Team", layout="wide")
page = st.navigation(
    [
        st.Page("ui/evaluate_page.py", title="Evaluate", icon=":material/groups:", default=True),
        st.Page("ui/reports_page.py", title="Reports", icon=":material/description:"),
    ]
)

with st.sidebar:
    st.subheader("Backend")
    if api.backend_service():
        st.success(f"Connected to {api.API_URL}")
    else:
        st.error(f"Can't reach {api.API_URL}. Start it with `uv run python main.py`.")
    if st.session_state.get("session_id"):
        st.caption(f"Session {st.session_state.session_id}")
        st.button("Start a new session", on_click=start_new_session)

page.run()
