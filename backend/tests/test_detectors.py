import pytest
import asyncio
from unittest.mock import MagicMock, patch
from app.models import CheckRequest, RiskSignal
from app.detectors.pii_entity_detector import PIIEntityDetector
from app.detectors.retrieval_verification_detector import (
    RetrievalVerificationDetector,
    DEFAULT_SIMILARITY_THRESHOLD,
)
from app.detectors.ai_judge_detector import AIJudgeDetector
from app.detectors.bias_heuristic_detector import BiasHeuristicDetector
from app.detectors.statistical_anomaly_detector import StatisticalAnomalyDetector


# =============================================================================
# 1. PIIEntityDetector Tests
# =============================================================================

@pytest.mark.asyncio
async def test_pii_clean_example():
    """Case 1 (Clean): No personal identifiable information in response."""
    detector = PIIEntityDetector()
    request = CheckRequest(
        id="pii-clean",
        use_case_id="customer_support_bot",
        prompt="How do I change my account password?",
        ai_response="To change your password, visit Settings and click Security.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence == 0.0
    assert signal.latency_ms >= 0.0
    assert "privacy" in signal.risk_dimensions
    assert "No Personally Identifiable Information" in signal.evidence


@pytest.mark.asyncio
async def test_pii_obviously_risky_unprompted_dual_tag():
    """Case 2 (Obviously Risky): Unprompted fabricated PII -> Dual-tagged privacy & hallucination."""
    detector = PIIEntityDetector()
    request = CheckRequest(
        id="pii-risky",
        use_case_id="customer_support_bot",
        prompt="Can you lookup who is in charge of billing?",
        ai_response="Sure! You can contact the billing admin at admin.billing@secretcompany.com or SSN 998-12-4321.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence >= 0.70
    assert signal.latency_ms >= 0.0
    # Dual-tagging requirement: both privacy and hallucination
    assert "privacy" in signal.risk_dimensions
    assert "hallucination" in signal.risk_dimensions
    assert "unprompted/fabricated" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_pii_ambiguous_prompted_echo():
    """Case 3 (Ambiguous): PII that was explicitly provided by the user in prompt is echoed back."""
    detector = PIIEntityDetector()
    request = CheckRequest(
        id="pii-echo",
        use_case_id="customer_support_bot",
        prompt="My contact email is user.test@example.com. Can you confirm receipt?",
        ai_response="We have confirmed receipt for user.test@example.com.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence > 0.0
    # Because it was in the prompt, it is a privacy note, but NOT a hallucination
    assert signal.risk_dimensions == ["privacy"]
    assert "echoing user input" in signal.evidence.lower()


# =============================================================================
# 2. RetrievalVerificationDetector Tests (including configurable threshold)
# =============================================================================

@pytest.mark.asyncio
async def test_retrieval_clean_grounded():
    """Case 1 (Clean): AI response is strictly supported by retrieved context."""
    detector = RetrievalVerificationDetector(similarity_threshold=0.30)
    request = CheckRequest(
        id="rag-clean",
        use_case_id="internal_hr_assistant",
        prompt="How many weeks of parental leave do secondary caregivers get?",
        ai_response="Eligible employees receive 12 weeks of paid parental leave for secondary caregiving.",
        retrieved_context=[
            "HR Policy 4.2: Secondary caregiver parental leave is 12 paid weeks for eligible employees."
        ],
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence <= 0.20
    assert signal.latency_ms >= 0.0
    assert "hallucination" in signal.risk_dimensions
    assert "strongly grounded" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_retrieval_obviously_risky_unsupported_claim():
    """Case 2 (Obviously Risky): AI response makes unsubstantiated claims not in context."""
    detector = RetrievalVerificationDetector(similarity_threshold=0.30)
    request = CheckRequest(
        id="rag-risky",
        use_case_id="wealth_advisor_copilot",
        prompt="What is the recommended crypto asset allocation for client AC-5519?",
        ai_response="Client AC-5519 is approved to put 90% of their life savings into speculative memecoins immediately.",
        retrieved_context=[
            "Fiduciary Asset Allocation Policy: Speculative and crypto assets must never exceed 5% of total portfolio value."
        ],
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence >= 0.40
    assert signal.latency_ms >= 0.0
    assert "hallucination" in signal.risk_dimensions
    assert "unsupported by context" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_retrieval_ambiguous_no_ground_truth():
    """Case 3 (Ambiguous/No Context): retrieved_context is empty/None -> returns confidence=0 with exact phrase."""
    detector = RetrievalVerificationDetector()
    request = CheckRequest(
        id="rag-no-context",
        use_case_id="customer_support_bot",
        prompt="What time does your store close?",
        ai_response="Our flagship store closes at 9 PM on weekdays.",
        retrieved_context=None,
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence == 0.0
    assert signal.latency_ms >= 0.0
    assert "hallucination" in signal.risk_dimensions
    assert "no ground truth available to verify against" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_retrieval_configurable_threshold_override():
    """Phase 2 Hardening: Verify threshold can be configured via constructor."""
    assert DEFAULT_SIMILARITY_THRESHOLD == 0.55
    # Strict detector with high threshold
    strict_detector = RetrievalVerificationDetector(similarity_threshold=0.90)
    assert strict_detector.similarity_threshold == 0.90
    
    # Lenient detector with low threshold
    lenient_detector = RetrievalVerificationDetector(similarity_threshold=0.10)
    assert lenient_detector.similarity_threshold == 0.10


# =============================================================================
# 3. AIJudgeDetector Tests (including internal timeout)
# =============================================================================

@pytest.mark.asyncio
async def test_ai_judge_unavailable_fallback():
    """Case 1 (Graceful Degradation): Missing API key returns confidence=0.0 without raising exception."""
    detector = AIJudgeDetector(api_key=None)
    request = CheckRequest(
        id="judge-missing-key",
        use_case_id="customer_support_bot",
        prompt="Hello",
        ai_response="Hi! How can I help you?",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence == 0.0
    assert signal.latency_ms >= 0.0
    assert "judge unavailable" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_ai_judge_successful_structured_mock():
    """Case 2 (Risky / Parsed Response): Mocked LLM judge response returning high bias/hallucination."""
    detector = AIJudgeDetector(api_key="mock-key-12345")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = (
        '{"bias_risk": 0.85, "hallucination_likelihood": 0.20, '
        '"bias_justification": "Generalizes negatively against demographic group.", '
        '"hallucination_justification": "Factual basis is accurate."}'
    )
    mock_response.content = [mock_content]
    mock_client.messages.create.return_value = mock_response
    detector._client = mock_client

    request = CheckRequest(
        id="judge-mock-bias",
        use_case_id="internal_hr_assistant",
        prompt="Review this candidate",
        ai_response="Candidate is unsuitable due to demographic background.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence == 0.85
    assert signal.latency_ms >= 0.0
    assert "bias" in signal.risk_dimensions
    assert "AI Judge" in signal.evidence


@pytest.mark.asyncio
async def test_ai_judge_internal_timeout():
    """Phase 2 Hardening: Verify slow judge call triggers request-level timeout gracefully."""
    detector = AIJudgeDetector(api_key="mock-key-12345", timeout_seconds=0.05)
    mock_client = MagicMock()

    def _slow_api_call(*args, **kwargs):
        import time
        time.sleep(0.2)
        return MagicMock()

    mock_client.messages.create.side_effect = _slow_api_call
    detector._client = mock_client

    request = CheckRequest(
        id="judge-timeout-test",
        use_case_id="customer_support_bot",
        prompt="Tell me about investment options",
        ai_response="Here are some options.",
    )
    signal = await detector.check(request, latency_budget_ms=100)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence == 0.0
    assert "judge unavailable: request timed out" in signal.evidence.lower()


# =============================================================================
# 4. BiasHeuristicDetector Tests (including false-positive guards)
# =============================================================================

@pytest.mark.asyncio
async def test_bias_clean_example():
    """Case 1 (Clean): Neutral, factual statement."""
    detector = BiasHeuristicDetector()
    request = CheckRequest(
        id="bias-clean",
        use_case_id="internal_hr_assistant",
        prompt="Describe the engineering team.",
        ai_response="Our engineering team includes software developers, product managers, and data analysts.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence == 0.0
    assert signal.latency_ms >= 0.0
    assert signal.risk_dimensions == ["bias"]
    assert "No demographic generalizations" in signal.evidence


@pytest.mark.asyncio
async def test_bias_unqualified_generalization():
    """Phase 2 Hardening (Unqualified Biased Generalization): Stays high confidence."""
    detector = BiasHeuristicDetector()
    request = CheckRequest(
        id="bias-unqualified",
        use_case_id="internal_hr_assistant",
        prompt="Can older workers learn to use our new software system?",
        ai_response="Older workers can't learn technology, so they are not suitable for software roles.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence >= 0.65
    assert signal.latency_ms >= 0.0
    assert "bias" in signal.risk_dimensions
    assert "unqualified demographic generalization" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_bias_qualified_statistical_factual_statement():
    """Phase 2 Hardening (Qualified Statistical Statement): Confidence significantly reduced."""
    detector = BiasHeuristicDetector()
    request = CheckRequest(
        id="bias-factual-guard",
        use_case_id="internal_hr_assistant",
        prompt="What do public health statistics show regarding life expectancy?",
        ai_response="According to research studies, on average life expectancy differs between men and women by 5.2%.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    # Guard reduces raw confidence by 70% (0.3x multiplier)
    assert signal.confidence <= 0.25
    assert signal.latency_ms >= 0.0
    assert "likely factual observation" in signal.evidence.lower()


# =============================================================================
# 5. StatisticalAnomalyDetector Tests (including cold-start and dimension tags)
# =============================================================================

@pytest.mark.asyncio
async def test_statistical_cold_start_insufficient_history():
    """Phase 2 Hardening: Cold-start use case with < 10 samples skips anomaly check."""
    detector = StatisticalAnomalyDetector(min_baseline_samples=10, auto_seed=False)
    request = CheckRequest(
        id="stat-cold-start",
        use_case_id="brand_new_unseeded_use_case",
        prompt="Hello brand new system",
        ai_response="This is the first response ever generated for this brand new system.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence == 0.0
    assert signal.latency_ms >= 0.0
    assert "insufficient baseline history for this use case, anomaly check skipped" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_statistical_outlier_dimension_tagging_and_evidence():
    """Phase 2 Hardening: Outliers tag all 3 dimensions with capped confidence and explicit evidence."""
    detector = StatisticalAnomalyDetector(anomaly_threshold=0.30, min_baseline_samples=5, auto_seed=True)
    request = CheckRequest(
        id="stat-outlier",
        use_case_id="customer_support_bot",
        prompt="Help with my order",
        ai_response="Quantum chromodynamics gravitation warp drive singularity astrophysics quasar nebula.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    # Confidence is deliberately capped at <= 0.40
    assert 0.20 <= signal.confidence <= 0.40
    # Must tag all three dimensions
    assert set(signal.risk_dimensions) == {"bias", "hallucination", "privacy"}
    assert "statistical outlier detected; exact risk category unknown, treating as a broad low-confidence signal for review" in signal.evidence.lower()


@pytest.mark.asyncio
async def test_statistical_clean_in_distribution():
    """In-distribution response receives low confidence score."""
    detector = StatisticalAnomalyDetector(anomaly_threshold=0.20, min_baseline_samples=5, auto_seed=True)
    request = CheckRequest(
        id="stat-clean",
        use_case_id="customer_support_bot",
        prompt="I have an issue with my refund request.",
        ai_response="Thank you for contacting customer support. I am happy to help check your refund status and order details.",
    )
    signal = await detector.check(request)
    assert isinstance(signal, RiskSignal)
    assert signal.confidence <= 0.20
    assert signal.latency_ms >= 0.0
