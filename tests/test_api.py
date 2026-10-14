from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


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
