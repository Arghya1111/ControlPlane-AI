"""Governance Metrics & System Trustworthiness Engine for ControlPlane.ai.

Aggregates operational decision telemetry, detector latencies, time-series volume,
estimated empirical error rates bounded by human override history, and synthesizes
an executive trustworthiness narrative for stakeholders.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import AuditLogRecord, FeedbackExampleRecord
from app.governance.policy import PolicyManager


class TierBreakdown(BaseModel):
    allow: int = 0
    edit: int = 0
    flag_for_review: int = 0
    block: int = 0
    total: int = 0


class UseCaseMetricSummary(BaseModel):
    use_case_id: str
    use_case_name: str
    channel_type: str
    latency_budget_ms: int
    avg_latency_ms: float
    latency_budget_compliance_pct: float
    tier_counts: TierBreakdown
    total_evaluations: int
    overrides_count: int


class DetectorLatencyMetric(BaseModel):
    detector_name: str
    avg_latency_ms: float
    p95_latency_ms: float
    sample_count: int


class EstimatedErrorRates(BaseModel):
    sample_size_human_reviews: int
    estimated_false_positive_rate: float
    estimated_false_negative_rate: float
    disclaimer: str


class TimeSeriesPoint(BaseModel):
    timestamp: str
    formatted_time: str
    use_case_id: str
    allow: int = 0
    edit: int = 0
    flag_for_review: int = 0
    block: int = 0
    total: int = 0


class GovernanceMetricsResponse(BaseModel):
    generated_at: datetime
    total_evaluations: int
    total_overrides: int
    use_cases: List[UseCaseMetricSummary]
    overall_tier_breakdown: TierBreakdown
    detector_latencies: List[DetectorLatencyMetric]
    error_estimates: EstimatedErrorRates
    trustworthiness_narrative: str
    time_series_history: List[TimeSeriesPoint]


def generate_trustworthiness_narrative(
    total_evals: int,
    total_overrides: int,
    override_rate: float,
    fp_rate: float,
    fn_rate: float,
    budget_compliant_pct: float,
    block_count: int,
    flag_count: int,
) -> str:
    """Synthesizes a rolling executive narrative summarizing system safety and reliability."""
    if total_evals == 0:
        return (
            "ControlPlane.ai is initialized and operational across all enterprise deployment channels. "
            "No live traffic has been evaluated yet; baseline guardrails and declarative policy configs are ready."
        )

    fp_pct = int(fp_rate * 100)
    fn_pct = int(fn_rate * 100)
    compliance_pct = int(budget_compliant_pct)

    narrative = (
        f"Over {total_evals:,} total evaluated interactions across enterprise deployment channels, "
        f"the ControlPlane.ai middleware has successfully enforced declarative safety policies with "
        f"{compliance_pct}% latency budget compliance. The system intervened on {block_count + flag_count:,} "
        f"interactions ({block_count:,} blocked for policy violations, {flag_count:,} escalated for human auditor review). "
        f"Based on {total_overrides:,} human review actions recorded to date, the estimated false-positive rate is {fp_pct}% "
        f"and the estimated false-negative rate is {fn_pct}%. All decisions remain immutably audited with full request context "
        f"and multi-signal attribution, ensuring verifiable governance without black-box opacity."
    )
    return narrative


def compute_governance_metrics(db: Session, hours: int = 24) -> GovernanceMetricsResponse:
    """Computes operational governance metrics, error rates, latencies, and executive narrative."""
    # Query all audit records
    audit_records = db.query(AuditLogRecord).all()
    feedback_records = db.query(FeedbackExampleRecord).all()

    total_evals = len(audit_records)
    total_overrides = len(feedback_records)

    policies = PolicyManager.list_policies()
    policy_map = {p.id: p for p in policies}

    # Aggregate per-use-case metrics
    uc_metrics: Dict[str, Dict[str, Any]] = {}
    for p in policies:
        uc_metrics[p.id] = {
            "use_case_id": p.id,
            "use_case_name": p.name,
            "channel_type": p.channel_type.value,
            "latency_budget_ms": p.latency_budget_ms,
            "latencies": [],
            "tiers": {"allow": 0, "edit": 0, "flag_for_review": 0, "block": 0},
            "overrides_count": 0,
        }

    overall_tiers = {"allow": 0, "edit": 0, "flag_for_review": 0, "block": 0}
    detector_latencies_map: Dict[str, List[float]] = {}

    for rec in audit_records:
        uc_id = rec.use_case_id
        if uc_id not in uc_metrics:
            uc_metrics[uc_id] = {
                "use_case_id": uc_id,
                "use_case_name": uc_id.replace("_", " ").title(),
                "channel_type": "customer_facing",
                "latency_budget_ms": 500,
                "latencies": [],
                "tiers": {"allow": 0, "edit": 0, "flag_for_review": 0, "block": 0},
                "overrides_count": 0,
            }

        tier = rec.tier.lower() if rec.tier else "allow"
        if tier in overall_tiers:
            overall_tiers[tier] += 1
        if tier in uc_metrics[uc_id]["tiers"]:
            uc_metrics[uc_id]["tiers"][tier] += 1

        if rec.override:
            uc_metrics[uc_id]["overrides_count"] += 1

        # Extract detector latencies from contributing signals
        if isinstance(rec.contributing_signals, list):
            req_latency = 0.0
            for sig in rec.contributing_signals:
                if isinstance(sig, dict):
                    name = sig.get("detector_name")
                    lat = float(sig.get("latency_ms", 0.0))
                    if name:
                        detector_latencies_map.setdefault(name, []).append(lat)
                    req_latency = max(req_latency, lat)
            if req_latency > 0:
                uc_metrics[uc_id]["latencies"].append(req_latency)

    # Calculate use-case summaries
    use_case_summaries: List[UseCaseMetricSummary] = []
    total_budget_compliant = 0
    total_latency_evaluated = 0

    for uc_id, data in uc_metrics.items():
        lats = data["latencies"]
        avg_lat = round(sum(lats) / len(lats), 1) if lats else 0.0
        budget = data["latency_budget_ms"]
        compliant_count = sum(1 for l in lats if l <= budget)
        comp_pct = round((compliant_count / len(lats)) * 100, 1) if lats else 100.0

        total_budget_compliant += compliant_count
        total_latency_evaluated += len(lats)

        t_counts = data["tiers"]
        uc_total = sum(t_counts.values())

        use_case_summaries.append(
            UseCaseMetricSummary(
                use_case_id=uc_id,
                use_case_name=data["use_case_name"],
                channel_type=data["channel_type"],
                latency_budget_ms=budget,
                avg_latency_ms=avg_lat,
                latency_budget_compliance_pct=comp_pct,
                tier_counts=TierBreakdown(
                    allow=t_counts["allow"],
                    edit=t_counts["edit"],
                    flag_for_review=t_counts["flag_for_review"],
                    block=t_counts["block"],
                    total=uc_total,
                ),
                total_evaluations=uc_total,
                overrides_count=data["overrides_count"],
            )
        )

    overall_compliance = (
        (total_budget_compliant / total_latency_evaluated) * 100 if total_latency_evaluated > 0 else 100.0
    )

    # Compute Detector Latencies
    detector_latencies: List[DetectorLatencyMetric] = []
    for det_name, lats in detector_latencies_map.items():
        if lats:
            avg_l = round(sum(lats) / len(lats), 1)
            sorted_l = sorted(lats)
            p95_idx = int(len(sorted_l) * 0.95)
            p95_l = sorted_l[min(p95_idx, len(sorted_l) - 1)]
            detector_latencies.append(
                DetectorLatencyMetric(
                    detector_name=det_name,
                    avg_latency_ms=avg_l,
                    p95_latency_ms=p95_l,
                    sample_count=len(lats),
                )
            )

    # Compute Estimated FP / FN Rates bounded by human review data
    fp_count = 0
    fn_count = 0
    for fb in feedback_records:
        orig = fb.original_tier.lower()
        corr = fb.corrected_tier.lower()
        if orig in ("block", "flag_for_review") and corr == "allow":
            fp_count += 1
        elif orig == "allow" and corr == "block":
            fn_count += 1

    fp_rate = round(fp_count / total_overrides, 3) if total_overrides > 0 else 0.0
    fn_rate = round(fn_count / total_overrides, 3) if total_overrides > 0 else 0.0

    error_estimates = EstimatedErrorRates(
        sample_size_human_reviews=total_overrides,
        estimated_false_positive_rate=fp_rate,
        estimated_false_negative_rate=fn_rate,
        disclaimer=(
            "Note: These error rates are empirical estimates derived strictly from the sample of human "
            "reviews recorded in the audit queue (N=" + str(total_overrides) + "). They do not represent universal "
            "ground truth across all unreviewed interactions."
        ),
    )

    # Build Time-Series History
    time_series_history: List[TimeSeriesPoint] = []
    now = datetime.now(timezone.utc)
    
    for h in range(5, -1, -1):
        window_start = now - timedelta(hours=h + 1)
        window_end = now - timedelta(hours=h)
        formatted = (now - timedelta(hours=h)).strftime("%H:%M")

        for uc_id in ["customer_support_bot", "wealth_advisor_copilot", "internal_hr_assistant"]:
            bucket_records = [
                r for r in audit_records
                if r.use_case_id == uc_id and (window_start <= r.created_at.replace(tzinfo=timezone.utc) <= window_end if r.created_at.tzinfo is None else window_start <= r.created_at <= window_end)
            ]
            
            b_allow = sum(1 for r in bucket_records if r.tier == "allow")
            b_edit = sum(1 for r in bucket_records if r.tier == "edit")
            b_flag = sum(1 for r in bucket_records if r.tier == "flag_for_review")
            b_block = sum(1 for r in bucket_records if r.tier == "block")

            time_series_history.append(
                TimeSeriesPoint(
                    timestamp=window_end.isoformat(),
                    formatted_time=formatted,
                    use_case_id=uc_id,
                    allow=b_allow,
                    edit=b_edit,
                    flag_for_review=b_flag,
                    block=b_block,
                    total=len(bucket_records),
                )
            )

    # Narrative synthesis
    narrative = generate_trustworthiness_narrative(
        total_evals=total_evals,
        total_overrides=total_overrides,
        override_rate=round(total_overrides / total_evals, 3) if total_evals > 0 else 0.0,
        fp_rate=fp_rate,
        fn_rate=fn_rate,
        budget_compliant_pct=overall_compliance,
        block_count=overall_tiers["block"],
        flag_count=overall_tiers["flag_for_review"],
    )

    return GovernanceMetricsResponse(
        generated_at=now,
        total_evaluations=total_evals,
        total_overrides=total_overrides,
        use_cases=use_case_summaries,
        overall_tier_breakdown=TierBreakdown(
            allow=overall_tiers["allow"],
            edit=overall_tiers["edit"],
            flag_for_review=overall_tiers["flag_for_review"],
            block=overall_tiers["block"],
            total=total_evals,
        ),
        detector_latencies=detector_latencies,
        error_estimates=error_estimates,
        trustworthiness_narrative=narrative,
        time_series_history=time_series_history,
    )
