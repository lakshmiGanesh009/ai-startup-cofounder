"""Client for the FastAPI backend, shared by the Streamlit pages.

Every call raises ApiError, with the reason, when the backend cannot be reached
or answers with an error, so a page can show it.
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
# An evaluation or a detailed report makes many LLM calls and can take minutes.
LONG_TIMEOUT = httpx.Timeout(600, connect=5)
SHORT_TIMEOUT = httpx.Timeout(30, connect=5)


class ApiError(RuntimeError):
    """The backend could not be reached or answered with an error."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _send(method: str, path: str, body: dict | None = None, timeout=SHORT_TIMEOUT):
    url = f"{API_URL}{path}"
    try:
        if method == "GET":
            response = httpx.get(url, timeout=timeout)
        else:
            send = httpx.post if method == "POST" else httpx.put
            response = send(url, json=body, timeout=timeout)
    except httpx.HTTPError as error:
        raise ApiError(f"Could not reach the backend at {API_URL}: {error}") from error
    if response.status_code != 200:
        try:
            detail = response.json()["detail"]
        except (ValueError, KeyError, TypeError):
            detail = response.text
        raise ApiError(f"The backend returned {response.status_code}: {detail}", response.status_code)
    return response


def backend_service() -> str | None:
    """The backend's service name if /health answers, else None."""
    try:
        response = httpx.get(f"{API_URL}/health", timeout=2)
        return response.json()["service"] if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def evaluate(prompt: str, context: dict, session_id: str | None) -> dict:
    """Run the founding team on a request, or a follow-up in `session_id`."""
    body = {"prompt": prompt, "context": context or None, "session_id": session_id}
    return _send("POST", "/evaluate", body, LONG_TIMEOUT).json()


def list_reports() -> list[dict]:
    return _send("GET", "/reports").json()


def get_report(session_id: str) -> dict:
    return _send("GET", f"/reports/{session_id}").json()


def save_report(session_id: str, version: int, sections: list[dict]) -> dict:
    """Save edited sections; ApiError with status 409 if the report changed since `version`."""
    body = {"version": version, "sections": sections}
    return _send("PUT", f"/reports/{session_id}", body).json()


def reset_report(session_id: str) -> dict:
    return _send("POST", f"/reports/{session_id}/reset").json()


def detail_report(session_id: str) -> dict:
    """Have the agents write the detailed version: {"report": ..., "failed": [...]}."""
    return _send("POST", f"/reports/{session_id}/detailed", timeout=LONG_TIMEOUT).json()


def report_pdf(session_id: str) -> bytes:
    return _send("GET", f"/reports/{session_id}/pdf").content
