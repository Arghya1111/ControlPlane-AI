import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import DecisionTier

client = TestClient(app)


def test_audit_recording_and_query():
    """Verify that interaction checks create immutable audit logs queryable via GET /v1/audit."""
    req_id = "test-audit-req-001"
    payload = {
        "id": req_id,
        "use_case_id": "customer_support_bot",
        "prompt": "How do I update my shipping address?",
        "ai_response": "Navigate to Account > Addresses and click Edit.",
        "retrieved_context": ["Address updates are made in the Account portal."],
        "conversation_history": [],
        "metadata": {"session_id": "sess-9912", "user_role": "customer"}
    }

    # Execute check
    check_resp = client.post("/v1/check", json=payload)
    assert check_resp.status_code == 200

    # Query audit log for this use case
    audit_resp = client.get("/v1/audit?use_case_id=customer_support_bot")
    assert audit_resp.status_code == 200
    data = audit_resp.json()
    assert "total" in data
    assert data["total"] >= 1
    assert "items" in data

    # Find the specific record
    record = next((item for item in data["items"] if item["request_id"] == req_id), None)
    assert record is not None
    assert record["prompt"] == payload["prompt"]
    assert record["ai_response"] == payload["ai_response"]
    assert record["tier"] in ["allow", "edit", "flag_for_review", "block"]
    assert len(record["contributing_signals"]) > 0
    assert record["override"] is False


def test_audit_filter_by_tier():
    """Verify filtering GET /v1/audit by tier."""
    resp = client.get("/v1/audit?tier=allow")
    assert resp.status_code == 200
    data = resp.json()
    for item in data["items"]:
        assert item["tier"] == "allow"


def test_audit_human_override():
    """Verify human reviewer override modifies audit log and appends justification."""
    req_id = "test-override-req-002"
    payload = {
        "id": req_id,
        "use_case_id": "internal_hr_assistant",
        "prompt": "Who is eligible for wellness stipend?",
        "ai_response": "All full-time staff with 90+ days of tenure.",
        "retrieved_context": ["Wellness stipend is for full-time staff."],
        "conversation_history": [],
    }

    # Create check
    check_resp = client.post("/v1/check", json=payload)
    assert check_resp.status_code == 200
    decision_id = f"dec_{req_id}"

    # Submit human override
    override_payload = {
        "reviewer_id": "auditor_sarah_connor",
        "override_tier": "allow",
        "notes": "Reviewed context manually. Claim is valid under policy section 4.1."
    }

    override_resp = client.post(f"/v1/audit/{decision_id}/override", json=override_payload)
    assert override_resp.status_code == 200
    override_data = override_resp.json()

    assert override_data["id"] == decision_id
    assert override_data["override"] is True
    assert override_data["reviewed_by"] == "auditor_sarah_connor"
    assert override_data["override_tier"] == "allow"
    assert override_data["override_notes"] == override_payload["notes"]
    assert "OVERRIDE by auditor_sarah_connor" in override_data["rationale"]


def test_audit_override_nonexistent_record():
    """Verify override on invalid decision ID returns 404."""
    override_payload = {
        "reviewer_id": "auditor_99",
        "override_tier": "allow",
        "notes": "No record exists."
    }
    resp = client.post("/v1/audit/dec_nonexistent_9999/override", json=override_payload)
    assert resp.status_code == 404


def test_audit_count_endpoint():
    """Verify lightweight GET /v1/audit/count returns total count."""
    resp = client.get("/v1/audit/count")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert isinstance(data["total"], int)
    assert data["total"] >= 0
