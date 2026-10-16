import asyncio

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_evaluate_returns_marketing_analysis(fake_llm):
    response = client.post(
        "/evaluate",
        json={"prompt": "Evaluate an AI healthcare scheduling tool."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["objective"]
    assert "marketing" in body["assignments"]
    assert "AI healthcare scheduling tool" in body["analyses"]["marketing"]
    assert body["final_strategy"]


def test_evaluate_with_context(fake_llm):
    response = client.post(
        "/evaluate",
        json={
            "prompt": "Evaluate an AI healthcare scheduling tool.",
            "context": {"target_market": "clinics"},
        },
    )

    assert response.status_code == 200
    assert "clinics" in response.json()["analyses"]["marketing"]


def test_evaluate_without_credentials_returns_503():
    response = client.post(
        "/evaluate",
        json={"prompt": "Evaluate an AI healthcare scheduling tool."},
    )

    assert response.status_code == 503


def test_the_frontend_origin_may_call_the_api():
    # The browser's preflight for the Next.js dev server's POST /evaluate.
    response = client.options(
        "/evaluate",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_other_origins_are_not_allowed():
    response = client.get("/health", headers={"Origin": "https://elsewhere.example"})

    assert "access-control-allow-origin" not in response.headers


def test_a_failed_llm_call_returns_502_not_500(fake_llm):
    def unreachable(prompt):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://llm.example"))

    fake_llm._plan_for = unreachable

    response = client.post("/evaluate", json={"prompt": "Evaluate an AI tool."})

    assert response.status_code == 502
    assert "The LLM call failed" in response.json()["detail"]


@pytest.mark.anyio
async def test_health_answers_while_an_evaluation_runs(fake_llm):
    fake_llm.delay = 0.1  # every LLM call takes a while, so the evaluation does too
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        evaluation = asyncio.create_task(
            api.post("/evaluate", json={"prompt": "Evaluate an AI tool."})
        )
        await asyncio.sleep(0.05)  # the evaluation is now waiting on its first call

        health = await api.get("/health")

        # /health was answered while the evaluation was still running, so the
        # evaluation did not block the event loop.
        assert health.status_code == 200
        assert not evaluation.done()
        assert (await evaluation).status_code == 200
