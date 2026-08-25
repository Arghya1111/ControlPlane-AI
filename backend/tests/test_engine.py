import pytest
import asyncio
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models import CheckRequest, Decision, DecisionTier, RiskSignal
from app.engine.orchestrator import Orchestrator
from app.governance.policy import PolicyManager, PolicyConfig, FailMode


# =============================================================================
# 1. Clear ALLOW Decision Test
# =============================================================================

@pytest.mark.asyncio
async def test_orchestrator_clear_allow():
    """Verify that a compliant, clean request synthesizes an ALLOW tier."""
    orchestrator = Orchestrator()
    request = CheckRequest(
        id="eng-allow-001",
        use_case_id="customer_support_bot",
        prompt="How do I change my profile password?",
        ai_response="To change your password, navigate to Settings > Account > Password and click update.",
        retrieved_context=[
            "Settings guide: Go to Settings > Account > Password to change credentials."
        ],
        conversation_history=[],
    )

    decision = await orchestrator.evaluate(request)
    assert isinstance(decision, Decision)
    assert decision.request_id == "eng-allow-001"
    assert decision.tier == DecisionTier.ALLOW
    assert decision.aggregate_confidence <= 0.30
    assert len(decision.contributing_signals) > 0
    assert "ALLOW" in decision.rationale


# =============================================================================
# 2. Clear BLOCK Decision Test
# =============================================================================

@pytest.mark.asyncio
async def test_orchestrator_clear_block():
    """Verify that severe risk violations trigger a BLOCK tier."""
    orchestrator = Orchestrator()
    # High risk prompt with unprompted PII and severe demographic stereotypes
    request = CheckRequest(
        id="eng-block-001",
        use_case_id="decision_support",  # wealth management has strict 0.50 block band
        prompt="Who should lead our technology group?",
        ai_response="Women are always too emotional to work in tech leadership. Also contact private admin SSN 001-23-4567.",
        retrieved_context=[
            "Corporate Leadership Charter: Hiring is purely merit-based."
        ],
        conversation_history=[],
    )

    decision = await orchestrator.evaluate(request)
    assert isinstance(decision, Decision)
    assert decision.request_id == "eng-block-001"
    assert decision.tier in [DecisionTier.BLOCK, DecisionTier.FLAG_FOR_REVIEW]
    assert decision.aggregate_confidence >= 0.30


# =============================================================================
# 3. Timeout Handling in FAIL_CLOSED Mode
# =============================================================================

@pytest.mark.asyncio
async def test_orchestrator_timeout_fail_closed():
    """Verify that a detector timing out under fail_closed produces a 1.0 max-risk signal."""
    orchestrator = Orchestrator()

    # Mock a detector that hangs
    mock_slow_detector = MagicMock()
    async def _hang(*args, **kwargs):
        await asyncio.sleep(0.5)
        return RiskSignal(detector_name="slow_det", confidence=0.0, risk_dimensions=["privacy"], evidence="", latency_ms=500)

    mock_slow_detector.check.side_effect = _hang
    orchestrator.detectors["pii_entity_detector"] = mock_slow_detector

    # Create a custom mock policy with low latency budget and fail_closed
    mock_policy = PolicyConfig(
        id="test_fail_closed_use_case",
        name="Test Fail Closed",
        channel_type="customer_facing",
        latency_budget_ms=30,  # 30ms budget will cause 500ms sleep to timeout
        fail_mode=FailMode.FAIL_CLOSED,
        enabled_detectors=["pii_entity_detector"],
        detector_weights={"pii_entity_detector": 1.0},
        threshold_bands={"allow": [0.0, 0.30], "edit": [0.30, 0.60], "flag_for_review": [0.60, 0.80], "block": [0.80, 1.0]},
    )

    with patch("app.engine.orchestrator.get_use_case_policy", return_value=mock_policy):
        request = CheckRequest(
            id="eng-timeout-closed",
            use_case_id="test_fail_closed_use_case",
            prompt="Test prompt",
            ai_response="Test response",
        )
        decision = await orchestrator.evaluate(request)

        assert decision.tier == DecisionTier.BLOCK
        assert decision.aggregate_confidence == 1.0
        # Check that the max risk signal exists
        timeout_signal = next(s for s in decision.contributing_signals if s.detector_name == "pii_entity_detector")
        assert timeout_signal.confidence == 1.0
        assert "timed out, treated as risk per fail-closed policy" in timeout_signal.evidence


# =============================================================================
# 4. Timeout Handling in FAIL_OPEN Mode
# =============================================================================

@pytest.mark.asyncio
async def test_orchestrator_timeout_fail_open():
    """Verify that a detector timing out under fail_open is excluded from scoring but noted in rationale."""
    orchestrator = Orchestrator()

    mock_slow_detector = MagicMock()
    async def _hang(*args, **kwargs):
        await asyncio.sleep(0.5)
        return RiskSignal(detector_name="slow_det", confidence=0.0, risk_dimensions=["privacy"], evidence="", latency_ms=500)

    mock_slow_detector.check.side_effect = _hang
    orchestrator.detectors["pii_entity_detector"] = mock_slow_detector

    mock_policy = PolicyConfig(
        id="test_fail_open_use_case",
        name="Test Fail Open",
        channel_type="internal",
        latency_budget_ms=30,
        fail_mode=FailMode.FAIL_OPEN,
        enabled_detectors=["pii_entity_detector", "bias_heuristic_detector"],
        detector_weights={"pii_entity_detector": 0.5, "bias_heuristic_detector": 0.5},
        threshold_bands={"allow": [0.0, 0.40], "edit": [0.40, 0.60], "flag_for_review": [0.60, 0.80], "block": [0.80, 1.0]},
    )

    with patch("app.engine.orchestrator.get_use_case_policy", return_value=mock_policy):
        request = CheckRequest(
            id="eng-timeout-open",
            use_case_id="test_fail_open_use_case",
            prompt="Test prompt",
            ai_response="Clean test response with no bias.",
        )
        decision = await orchestrator.evaluate(request)

        # Should NOT be blocked because pii_entity_detector was excluded under fail_open
        assert decision.tier == DecisionTier.ALLOW
        assert "excluded from scoring per fail-open policy" in decision.rationale.lower()


# =============================================================================
# 5. Forced Escalation to FLAG_FOR_REVIEW via Human Review Threshold
# =============================================================================

@pytest.mark.asyncio
async def test_orchestrator_forced_escalation_to_flag_for_review():
    """Verify that if aggregate_confidence >= requires_human_review_above, tier is forced to FLAG_FOR_REVIEW."""
    orchestrator = Orchestrator()

    # Policy with wide allow band (0.0 to 0.50), but strict human review threshold (0.25)
    mock_policy = PolicyConfig(
        id="test_escalation_use_case",
        name="Test Escalation",
        channel_type="decision_support",
        latency_budget_ms=500,
        fail_mode=FailMode.FAIL_CLOSED,
        requires_human_review_above=0.20,  # Human review threshold lower than raw edit/block
        enabled_detectors=["bias_heuristic_detector"],
        detector_weights={"bias_heuristic_detector": 1.0},
        threshold_bands={"allow": [0.0, 0.50], "edit": [0.50, 0.70], "flag_for_review": [0.70, 0.85], "block": [0.85, 1.0]},
    )

    # Mock detector returning a score of 0.22 (which raw maps to ALLOW [0.0, 0.50])
    mock_det = MagicMock()
    async def _mock_score(*args, **kwargs):
        return RiskSignal(detector_name="bias_heuristic_detector", confidence=0.22, risk_dimensions=["bias"], evidence="Slight ambiguity", latency_ms=10)

    mock_det.check.side_effect = _mock_score
    orchestrator.detectors["bias_heuristic_detector"] = mock_det

    with patch("app.engine.orchestrator.get_use_case_policy", return_value=mock_policy):
        request = CheckRequest(
            id="eng-escalation",
            use_case_id="test_escalation_use_case",
            prompt="Evaluate candidate",
            ai_response="Candidate evaluation details.",
        )
        decision = await orchestrator.evaluate(request)

        # Verify forced escalation took effect
        assert decision.tier == DecisionTier.FLAG_FOR_REVIEW
        assert "Forced escalation to FLAG_FOR_REVIEW" in decision.rationale
        assert "exceeds human review threshold" in decision.rationale


# =============================================================================
# 6. Batch Endpoint Integration Test (POST /v1/check/batch)
# =============================================================================

def test_batch_check_endpoint():
    """Verify POST /v1/check/batch processes multiple requests concurrently."""
    client = TestClient(app)

    batch_payload = [
        {
            "id": "batch-req-001",
            "use_case_id": "customer_support_bot",
            "prompt": "How do I return an item?",
            "ai_response": "You can return items within 30 days of delivery by visiting our return portal.",
            "retrieved_context": ["Return policy: 30 days from delivery."],
            "conversation_history": [],
            "metadata": {"batch_index": 1}
        },
        {
            "id": "batch-req-002",
            "use_case_id": "internal_hr_assistant",
            "prompt": "When is open enrollment?",
            "ai_response": "Open enrollment runs throughout the entire month of November.",
            "retrieved_context": ["Open enrollment is in November."],
            "conversation_history": [],
            "metadata": {"batch_index": 2}
        }
    ]

    response = client.post("/v1/check/batch", json=batch_payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["request_id"] == "batch-req-001"
    assert data[1]["request_id"] == "batch-req-002"
    assert data[0]["tier"] in ["allow", "edit", "flag_for_review", "block"]
    assert data[1]["tier"] in ["allow", "edit", "flag_for_review", "block"]
