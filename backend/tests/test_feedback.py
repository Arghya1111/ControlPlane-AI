import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import Base, get_db, FeedbackExampleRecord
from app.models import CheckRequest, Decision, DecisionTier, RiskSignal
from app.governance.audit import record_audit_event, record_human_override, OverrideRequest
from app.feedback.loop import store_feedback_example, compute_detector_performance

from sqlalchemy.pool import StaticPool

# In-memory SQLite for testing
TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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


def test_feedback_example_storage_on_override():
    """Verify that human override automatically persists a labeled feedback example."""
    db = TestingSessionLocal()
    client = TestClient(app)

    # 1. Record an initial audit event with a flag
    req = CheckRequest(
        id="req_feedback_01",
        use_case_id="customer_support_bot",
        prompt="Tell me about the CEO",
        ai_response="The CEO is John Doe at john@acme.com",
    )
    sig = RiskSignal(
        detector_name="bias_heuristic_detector",
        risk_dimensions=["bias"],
        confidence=0.75,
        evidence="Flagged bias pattern",
        latency_ms=10,
    )
    dec = Decision(
        request_id=req.id,
        tier=DecisionTier.FLAG_FOR_REVIEW,
        aggregate_confidence=0.75,
        contributing_signals=[sig],
        rationale="Elevated risk score",
    )
    record_audit_event(db, req, dec)

    # 2. Perform human override via API
    res = client.post(
        "/v1/audit/dec_req_feedback_01/override",
        json={
            "reviewer_id": "auditor_alice",
            "override_tier": "allow",
            "notes": "Verified context, this was a false positive bias flag.",
        },
    )
    assert res.status_code == 200

    # 3. Verify FeedbackExampleRecord was created
    fb_records = db.query(FeedbackExampleRecord).all()
    assert len(fb_records) == 1
    assert fb_records[0].decision_id == "dec_req_feedback_01"
    assert fb_records[0].original_tier == "flag_for_review"
    assert fb_records[0].corrected_tier == "allow"
    assert fb_records[0].reviewer_id == "auditor_alice"
    assert "false positive" in fb_records[0].justification


def test_detector_performance_computation():
    """Verify FP rate, accuracy, and suggested threshold warnings derived from overrides."""
    db = TestingSessionLocal()

    # Simulate 4 overrides where bias_heuristic_detector flagged (conf=0.8)
    bias_signal = [{"detector_name": "bias_heuristic_detector", "confidence": 0.8}]
    
    for i in range(3):
        store_feedback_example(
            db=db,
            decision_id=f"dec_fp_{i}",
            use_case_id="customer_support_bot",
            original_tier="flag_for_review",
            corrected_tier="allow",
            reviewer_id="reviewer_1",
            justification="False positive flag",
            prompt="Hello",
            ai_response="World",
            contributing_signals=bias_signal,
        )

    store_feedback_example(
        db=db,
        decision_id="dec_tp_1",
        use_case_id="customer_support_bot",
        original_tier="flag_for_review",
        corrected_tier="block",
        reviewer_id="reviewer_1",
        justification="Legitimate violation",
        prompt="Unsafe prompt",
        ai_response="Unsafe response",
        contributing_signals=bias_signal,
    )

    report = compute_detector_performance(db)
    assert report.total_overrides_recorded == 4

    bias_stats = next(d for d in report.detectors if d.detector_name == "bias_heuristic_detector")
    assert bias_stats.flagged_count == 4
    assert bias_stats.true_positive_count == 1
    assert bias_stats.false_positive_count == 3
    assert bias_stats.false_positive_rate == 0.75
    assert bias_stats.status == "warning_high_fp"
    assert "Consider raising its confidence threshold" in bias_stats.suggested_threshold_adjustment


def test_feedback_performance_api_endpoint():
    """Verify GET /v1/feedback/detector-performance endpoint."""
    client = TestClient(app)
    res = client.get("/v1/feedback/detector-performance")
    assert res.status_code == 200
    data = res.json()
    assert "detectors" in data
    assert "total_overrides_recorded" in data
    assert len(data["detectors"]) == 5
