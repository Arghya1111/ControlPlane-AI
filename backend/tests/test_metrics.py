import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import Base, get_db
from app.models import CheckRequest, Decision, DecisionTier, RiskSignal
from app.governance.audit import record_audit_event, record_human_override, OverrideRequest
from app.governance.metrics import compute_governance_metrics

# In-memory SQLite for testing
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def test_metrics_computation_empty_db():
    """Verify metrics calculation returns valid structure on clean state."""
    db = TestingSessionLocal()
    metrics = compute_governance_metrics(db)
    assert metrics.total_evaluations == 0
    assert metrics.total_overrides == 0
    assert "initialized and operational" in metrics.trustworthiness_narrative
    assert len(metrics.use_cases) >= 3


def test_metrics_computation_with_traffic():
    """Verify metrics calculation correctly summarizes evaluations, latencies, and tier breakdown."""
    db = TestingSessionLocal()
    client = TestClient(app)

    # 1. Add some audit evaluations
    req1 = CheckRequest(
        id="req_m1",
        use_case_id="customer_support_bot",
        prompt="Hello support",
        ai_response="Hello customer",
    )
    sig1 = RiskSignal(
        detector_name="pii_entity_detector",
        risk_dimensions=["privacy"],
        confidence=0.1,
        evidence="Clean",
        latency_ms=45.0,
    )
    dec1 = Decision(
        request_id=req1.id,
        tier=DecisionTier.ALLOW,
        aggregate_confidence=0.1,
        contributing_signals=[sig1],
        rationale="Safe interaction",
    )
    record_audit_event(db, req1, dec1)

    req2 = CheckRequest(
        id="req_m2",
        use_case_id="customer_support_bot",
        prompt="Bad prompt",
        ai_response="Bad response",
    )
    sig2 = RiskSignal(
        detector_name="pii_entity_detector",
        risk_dimensions=["privacy"],
        confidence=0.9,
        evidence="SSN leak",
        latency_ms=60.0,
    )
    dec2 = Decision(
        request_id=req2.id,
        tier=DecisionTier.FLAG_FOR_REVIEW,
        aggregate_confidence=0.9,
        contributing_signals=[sig2],
        rationale="Flagged SSN",
    )
    record_audit_event(db, req2, dec2)

    # 2. Add an override
    record_human_override(
        db,
        "dec_req_m2",
        OverrideRequest(
            reviewer_id="auditor_lead",
            override_tier=DecisionTier.ALLOW,
            notes="Overturned to allow",
        ),
    )

    # 3. Query metrics summary via API
    res = client.get("/v1/metrics/summary?hours=24")
    assert res.status_code == 200
    data = res.json()

    assert data["total_evaluations"] == 2
    assert data["total_overrides"] == 1
    assert "Over 2 total evaluated interactions" in data["trustworthiness_narrative"]
    assert data["error_estimates"]["sample_size_human_reviews"] == 1
    assert data["error_estimates"]["estimated_false_positive_rate"] == 1.0
    assert len(data["detector_latencies"]) > 0
    assert len(data["time_series_history"]) > 0
