"""Feedback loop & calibration engine for ControlPlane.ai.

Whenever a human reviewer overrides an automated decision in the review queue,
a labeled feedback record is persisted. Over time, this module analyzes human judgment
versus detector predictions to calculate per-detector accuracy, precision, and false-positive
rates, producing actionable policy threshold recommendations while keeping humans in the loop.
"""

from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db import FeedbackExampleRecord, AuditLogRecord
from backend.app.models import RiskSignal


class DetectorPerformanceStats(BaseModel):
    detector_name: string = Field(..., alias="detector_name")
    total_evaluated_overrides: int
    flagged_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    false_positive_rate: float
    accuracy_against_human_judgment: float
    status: str  # "calibrated" | "warning_high_fp" | "insufficient_data"
    suggested_threshold_adjustment: Optional[str] = None


class FeedbackPerformanceResponse(BaseModel):
    total_overrides_recorded: int
    analyzed_at: datetime
    detectors: List[DetectorPerformanceStats]
    global_insights: List[str]


def store_feedback_example(
    db: Session,
    decision_id: str,
    use_case_id: str,
    original_tier: str,
    corrected_tier: str,
    reviewer_id: str,
    justification: Optional[str],
    prompt: str,
    ai_response: str,
    contributing_signals: List[Dict[str, Any]],
) -> FeedbackExampleRecord:
    """Stores a labeled training example when an auditor overrides a decision."""
    example_id = f"fb_{uuid.uuid4().hex[:12]}"
    record = FeedbackExampleRecord(
        id=example_id,
        decision_id=decision_id,
        use_case_id=use_case_id,
        original_tier=original_tier,
        corrected_tier=corrected_tier,
        reviewer_id=reviewer_id,
        justification=justification or "",
        prompt=prompt,
        ai_response=ai_response,
        contributing_signals=contributing_signals,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


KNOWN_DETECTORS = [
    "pii_entity_detector",
    "retrieval_verification_detector",
    "ai_judge_detector",
    "bias_heuristic_detector",
    "statistical_anomaly_detector",
]


def compute_detector_performance(
    db: Session,
    use_case_id: Optional[str] = None,
) -> FeedbackPerformanceResponse:
    """Analyzes accumulated human overrides to evaluate per-detector accuracy against human judgment."""
    query = db.query(FeedbackExampleRecord)
    if use_case_id:
        query = query.filter(FeedbackExampleRecord.use_case_id == use_case_id)
    
    records = query.all()
    total_overrides = len(records)

    detector_stats: Dict[str, Dict[str, int]] = {
        name: {
            "total_evals": 0,
            "flagged": 0,
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "tn": 0,
        }
        for name in KNOWN_DETECTORS
    }

    FLAG_CONFIDENCE_THRESHOLD = 0.30

    for rec in records:
        signals_map: Dict[str, float] = {}
        if isinstance(rec.contributing_signals, list):
            for sig in rec.contributing_signals:
                if isinstance(sig, dict):
                    name = sig.get("detector_name")
                    conf = float(sig.get("confidence", 0.0))
                    if name:
                        signals_map[name] = conf

        # Human ground truth:
        # "allow" means human judged it safe
        # "block" means human judged it unsafe
        human_judged_unsafe = rec.corrected_tier == "block"
        human_judged_safe = rec.corrected_tier == "allow"

        for det_name in KNOWN_DETECTORS:
            conf = signals_map.get(det_name, 0.0)
            detector_stats[det_name]["total_evals"] += 1
            detector_flagged = conf >= FLAG_CONFIDENCE_THRESHOLD

            if detector_flagged:
                detector_stats[det_name]["flagged"] += 1
                if human_judged_safe:
                    # Detector flagged risk, but human allowed it -> False Positive
                    detector_stats[det_name]["fp"] += 1
                elif human_judged_unsafe:
                    # Detector flagged risk, and human blocked it -> True Positive
                    detector_stats[det_name]["tp"] += 1
            else:
                if human_judged_unsafe:
                    # Detector said safe, but human blocked -> False Negative
                    detector_stats[det_name]["fn"] += 1
                elif human_judged_safe:
                    detector_stats[det_name]["tn"] += 1

    detector_results: List[DetectorPerformanceStats] = []
    insights: List[str] = []

    for name in KNOWN_DETECTORS:
        s = detector_stats[name]
        flagged = s["flagged"]
        tp = s["tp"]
        fp = s["fp"]
        fn = s["fn"]
        total = s["total_evals"]

        fp_rate = round(fp / flagged, 3) if flagged > 0 else 0.0
        correct_predictions = tp + s["tn"]
        accuracy = round(correct_predictions / total, 3) if total > 0 else 1.0

        if total < 3:
            status = "insufficient_data"
            suggestion = "Insufficient override history to recommend threshold modifications."
        elif fp_rate >= 0.35:
            status = "warning_high_fp"
            suggestion = (
                f"{name} has been overridden as false-positive in {int(fp_rate * 100)}% of flags. "
                f"Consider raising its confidence threshold or decreasing detector weight in policy YAML."
            )
            insights.append(suggestion)
        else:
            status = "calibrated"
            suggestion = f"Well-calibrated with human auditor judgment (FP rate: {int(fp_rate * 100)}%)."

        detector_results.append(
            DetectorPerformanceStats(
                detector_name=name,
                total_evaluated_overrides=total,
                flagged_count=flagged,
                true_positive_count=tp,
                false_positive_count=fp,
                false_negative_count=fn,
                false_positive_rate=fp_rate,
                accuracy_against_human_judgment=accuracy,
                status=status,
                suggested_threshold_adjustment=suggestion,
            )
        )

    if not insights:
        insights.append(
            "All active detectors are currently operating within acceptable human-alignment tolerances."
        )

    return FeedbackPerformanceResponse(
        total_overrides_recorded=total_overrides,
        analyzed_at=datetime.now(timezone.utc),
        detectors=detector_results,
        global_insights=insights,
    )
