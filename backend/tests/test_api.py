import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import CheckRequest, Decision, UseCaseProfile

client = TestClient(app)


def test_health_endpoint():
    """Verify that GET /health returns 200 and expected metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ControlPlane.ai"
    assert "version" in data
    assert "timestamp" in data


def test_list_use_cases():
    """Verify that GET /v1/use-cases returns pre-configured profiles."""
    response = client.get("/v1/use-cases")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    ids = [item["id"] for item in data]
    assert "customer_support_bot" in ids
    assert "wealth_advisor_copilot" in ids
    assert "internal_hr_assistant" in ids


def test_check_endpoint_valid_request():
    """Verify POST /v1/check compiles and returns a valid Decision."""
    payload = {
        "id": "req-test-001",
        "use_case_id": "customer_support_bot",
        "prompt": "How do I reset my password?",
        "ai_response": "You can reset your password by navigating to Settings > Account > Security.",
        "retrieved_context": [
            "Password reset instructions: Navigate to Settings > Account > Security."
        ],
        "conversation_history": [
            "User: Hello",
            "AI: Hi there! How can I help you today?"
        ],
        "metadata": {
            "user_id": "user-4821",
            "channel": "web_chat",
            "model": "gpt-4o"
        }
    }

    response = client.post("/v1/check", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    # Validate against Pydantic Decision model
    decision = Decision.model_validate(data)
    assert decision.request_id == "req-test-001"
    assert decision.tier in ["allow", "edit", "flag_for_review", "block"]
    assert 0.0 <= decision.aggregate_confidence <= 1.0
    assert len(decision.contributing_signals) > 0
    detector_names = [s.detector_name for s in decision.contributing_signals]
    assert "pii_entity_detector" in detector_names or "retrieval_verification_detector" in detector_names


def test_check_endpoint_schema_validation_error():
    """Verify POST /v1/check enforces required fields in Pydantic schema."""
    # Missing required prompt and ai_response
    invalid_payload = {
        "id": "req-invalid-001",
        "use_case_id": "customer_support_bot",
    }
    response = client.post("/v1/check", json=invalid_payload)
    assert response.status_code == 422
