import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.models import (
    CheckRequest,
    Decision,
    DecisionTier,
    RiskSignal,
    FailMode,
)
from app.detectors import (
    BaseDetector,
    PIIEntityDetector,
    RetrievalVerificationDetector,
    AIJudgeDetector,
    BiasHeuristicDetector,
    StatisticalAnomalyDetector,
)
from app.governance.policy import PolicyConfig, get_use_case_policy, PolicyManager


class Orchestrator:
    """Core Responsible AI Decision & Orchestration Engine.

    Coordinates concurrent detector evaluation, enforces latency budgets,
    manages fail-open / fail-closed fault tolerance, computes weighted multi-signal
    aggregation, and synthesizes policy decisions with escalation rules.
    """

    def __init__(self):
        # Instantiate detector registry
        self.detectors: Dict[str, BaseDetector] = {
            "pii_entity_detector": PIIEntityDetector(),
            "retrieval_verification_detector": RetrievalVerificationDetector(),
            "ai_judge_detector": AIJudgeDetector(),
            "bias_heuristic_detector": BiasHeuristicDetector(),
            "statistical_anomaly_detector": StatisticalAnomalyDetector(),
        }

    def _get_active_policy(self, use_case_id: str) -> PolicyConfig:
        """Lookup policy for use case or construct safe fallback."""
        policy = get_use_case_policy(use_case_id)
        if policy:
            return policy

        # Safe fallback default policy
        return PolicyConfig(
            id=use_case_id,
            name=f"Default Policy ({use_case_id})",
            channel_type="customer_facing",
            latency_budget_ms=500,
            fail_mode=FailMode.FAIL_CLOSED,
            requires_human_review_above=0.65,
        )

    async def _run_single_detector(
        self,
        detector_name: str,
        detector: BaseDetector,
        request: CheckRequest,
        timeout_sec: float,
    ) -> RiskSignal:
        """Execute a single detector wrapped in an asyncio timeout."""
        start_time = time.perf_counter()
        try:
            # Special check for detectors supporting latency budget parameter
            if isinstance(detector, AIJudgeDetector):
                return await asyncio.wait_for(
                    detector.check(request, latency_budget_ms=int(timeout_sec * 1000)),
                    timeout=timeout_sec,
                )
            else:
                return await asyncio.wait_for(
                    detector.check(request),
                    timeout=timeout_sec,
                )
        except (asyncio.TimeoutError, TimeoutError):
            raise TimeoutError(f"Detector '{detector_name}' exceeded latency budget of {timeout_sec*1000:.0f}ms")

    async def evaluate(self, request: CheckRequest) -> Decision:
        """Orchestrate concurrent detector execution and synthesize final Decision."""
        start_overall = time.perf_counter()
        policy = self._get_active_policy(request.use_case_id)
        timeout_sec = policy.latency_budget_ms / 1000.0

        # Filter enabled detectors
        active_detectors: List[Tuple[str, BaseDetector]] = [
            (name, self.detectors[name])
            for name in policy.enabled_detectors
            if name in self.detectors
        ]

        if not active_detectors:
            return Decision(
                request_id=request.id,
                tier=DecisionTier.ALLOW,
                aggregate_confidence=0.0,
                contributing_signals=[],
                rationale="No risk detectors configured for this use case policy.",
                timestamp=datetime.now(timezone.utc),
            )

        # Run all enabled detectors concurrently with asyncio.gather
        tasks = [
            self._run_single_detector(name, det, request, timeout_sec)
            for name, det in active_detectors
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        contributing_signals: List[RiskSignal] = []
        scoring_signals: List[Tuple[RiskSignal, float]] = []
        omitted_fail_open_detectors: List[str] = []
        timed_out_fail_closed_detectors: List[str] = []

        for (name, _), result in zip(active_detectors, results):
            weight = policy.detector_weights.get(name, 1.0)

            if isinstance(result, Exception):
                # =====================================================================
                # FAULT TOLERANCE & TIMEOUT HANDLING:
                # 1. fail_closed: In high-assurance environments, an uncompleted check
                #    poses an unverified risk. We synthesize a maximum-risk signal (1.0)
                #    to protect the downstream user or system.
                # 2. fail_open: In internal/low-friction tools, we exclude the timed-out
                #    detector from numerical scoring to avoid false blocking, but
                #    explicitly document the omission in the audit trail.
                # =====================================================================
                if policy.fail_mode == FailMode.FAIL_CLOSED:
                    timed_out_fail_closed_detectors.append(name)
                    max_risk_sig = RiskSignal(
                        detector_name=name,
                        risk_dimensions=["bias", "hallucination", "privacy"],
                        confidence=1.0,
                        evidence="timed out, treated as risk per fail-closed policy",
                        latency_ms=policy.latency_budget_ms,
                    )
                    contributing_signals.append(max_risk_sig)
                    scoring_signals.append((max_risk_sig, weight))
                else:
                    omitted_fail_open_detectors.append(name)
            elif isinstance(result, RiskSignal):
                contributing_signals.append(result)
                scoring_signals.append((result, weight))

        # =========================================================================
        # WEIGHTED AGGREGATION DESIGN:
        # We compute a normalized weighted average of detector confidences:
        # aggregate_confidence = sum(confidence_i * weight_i) / sum(weight_i)
        #
        # Design rationale:
        # 1. High-assurance domain detectors (e.g. retrieval verification in wealth
        #    management) are assigned higher weights than coarse heuristic filters.
        # 2. Normalization ensures that missing/disabled detectors or fail-open
        #    omissions do not artificially deflate aggregate risk scores.
        # =========================================================================
        if scoring_signals:
            total_weight = sum(w for _, w in scoring_signals)
            if total_weight > 0:
                weighted_sum = sum(sig.confidence * w for sig, w in scoring_signals)
                aggregate_confidence = round(weighted_sum / total_weight, 3)
            else:
                aggregate_confidence = 0.0
        else:
            aggregate_confidence = 0.0

        # Map aggregate_confidence to raw DecisionTier based on policy threshold bands
        raw_tier = self._map_score_to_tier(aggregate_confidence, policy.threshold_bands)

        # =========================================================================
        # ESCALATION UNDER UNCERTAINTY:
        # If aggregate_confidence >= requires_human_review_above and the raw tier
        # would have allowed or edited the response, we force tier to 'flag_for_review'.
        # This embodies the Responsible AI principle of "escalate under uncertainty".
        # =========================================================================
        final_tier = raw_tier
        was_escalated = False
        if aggregate_confidence >= policy.requires_human_review_above:
            if raw_tier in [DecisionTier.ALLOW, DecisionTier.EDIT]:
                final_tier = DecisionTier.FLAG_FOR_REVIEW
                was_escalated = True

        # Synthesize clear, audit-ready rationale
        rationale = self._synthesize_rationale(
            final_tier=final_tier,
            raw_tier=raw_tier,
            was_escalated=was_escalated,
            aggregate_confidence=aggregate_confidence,
            policy=policy,
            scoring_signals=scoring_signals,
            omitted_fail_open=omitted_fail_open_detectors,
            timed_out_fail_closed=timed_out_fail_closed_detectors,
        )

        return Decision(
            request_id=request.id,
            tier=final_tier,
            aggregate_confidence=aggregate_confidence,
            contributing_signals=contributing_signals,
            rationale=rationale,
            timestamp=datetime.now(timezone.utc),
            reviewed_by=None,
            override=False,
        )

    def _map_score_to_tier(
        self, score: float, bands: Dict[str, List[float]]
    ) -> DecisionTier:
        """Map confidence score to tier using policy threshold bands."""
        # Check block band first
        if "block" in bands and score >= bands["block"][0]:
            return DecisionTier.BLOCK
        if "flag_for_review" in bands and score >= bands["flag_for_review"][0]:
            return DecisionTier.FLAG_FOR_REVIEW
        if "edit" in bands and score >= bands["edit"][0]:
            return DecisionTier.EDIT
        return DecisionTier.ALLOW

    def _synthesize_rationale(
        self,
        final_tier: DecisionTier,
        raw_tier: DecisionTier,
        was_escalated: bool,
        aggregate_confidence: float,
        policy: PolicyConfig,
        scoring_signals: List[Tuple[RiskSignal, float]],
        omitted_fail_open: List[str],
        timed_out_fail_closed: List[str],
    ) -> str:
        """Synthesize human-readable audit rationale for the decision."""
        reasons = []

        if was_escalated:
            reasons.append(
                f"Forced escalation to FLAG_FOR_REVIEW: Aggregate risk score ({aggregate_confidence:.2f}) "
                f"exceeds human review threshold ({policy.requires_human_review_above:.2f}) "
                f"despite raw tier mapping ({raw_tier.value.upper()})."
            )
        else:
            reasons.append(
                f"Decision {final_tier.value.upper()} synthesized from aggregate risk confidence "
                f"of {aggregate_confidence:.2f} under policy '{policy.name}'."
            )

        # High risk contributors
        flagged_signals = [sig for sig, _ in scoring_signals if sig.confidence >= 0.40]
        if flagged_signals:
            summary = "; ".join(f"{s.detector_name} (conf: {s.confidence:.2f})" for s in flagged_signals)
            reasons.append(f"Elevated risk signals detected from: [{summary}].")

        # Fail-closed timeouts
        if timed_out_fail_closed:
            reasons.append(
                f"Detector(s) [{', '.join(timed_out_fail_closed)}] timed out and were assigned maximum risk "
                f"per fail-closed policy."
            )

        # Fail-open omissions
        if omitted_fail_open:
            reasons.append(
                f"Detector(s) [{', '.join(omitted_fail_open)}] timed out and were excluded from scoring "
                f"per fail-open policy."
            )

        return " ".join(reasons)
