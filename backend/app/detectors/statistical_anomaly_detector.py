import math
import time
import hashlib
import json
import uuid
from typing import List, Optional
import re
from sqlalchemy.orm import Session

from app.models import CheckRequest, RiskSignal
from app.detectors.base import BaseDetector
from app.db import SessionLocal, BaselineResponseRecord, init_db

# Default baseline prototypes for the 3 use cases (seeding 10 samples each to meet minimum threshold)
INITIAL_BASELINES = {
    "customer_support_bot": [
        "I understand your issue with the order and I'm happy to help you with the refund process.",
        "Thank you for contacting customer support. Let me check your account details.",
        "Your shipment has been updated and is on track for delivery by Friday.",
        "To reset your credentials, please follow the password recovery link sent to your email.",
        "I have escalated your ticket to our technical support tier for immediate resolution.",
        "Your subscription has been renewed successfully for the upcoming billing cycle.",
        "Please provide your order number so I can check our fulfillment database.",
        "A confirmation receipt has been sent to your primary email address on file.",
        "We appreciate your patience while we verify your warranty coverage details.",
        "I have applied a promotional credit of ten dollars to your customer account balance.",
    ],
    "wealth_advisor_copilot": [
        "Based on your moderate risk profile, a balanced 60/40 equity and fixed income portfolio is recommended.",
        "Market volatility in technology assets suggests trimming high-beta exposure within fiduciary limits.",
        "Tax-loss harvesting opportunities are available in your non-qualified brokerage account.",
        "Your required minimum distribution (RMD) has been calculated in accordance with IRS guidelines.",
        "Municipal bonds remain attractive for high-net-worth investors seeking tax-exempt yield.",
        "Dollar-cost averaging into index funds is an appropriate strategy given current market fluctuations.",
        "Rebalancing your 401k allocations annually maintains target risk tolerance parameters.",
        "Diversifying across international developed markets mitigates single-country concentration risk.",
        "Estate planning strategies including revocable living trusts can optimize wealth transfer.",
        "Treasury inflation-protected securities (TIPS) provide a hedge against purchasing power erosion.",
    ],
    "internal_hr_assistant": [
        "Full-time employees receive 12 weeks of paid parental leave after completing 6 months of service.",
        "Open enrollment for health and dental insurance begins November 1st and ends November 30th.",
        "To submit an expense reimbursement, please navigate to the intranet portal under Finance Tools.",
        "Standard paid time off accrues at a rate of 1.5 days per month worked.",
        "The corporate wellness program provides up to $500 annual reimbursement for gym memberships.",
        "Performance evaluation cycles occur bi-annually in June and December across all departments.",
        "Remote work policy allows up to two days of telecommuting per week with manager approval.",
        "Employees can contribute up to the statutory maximum in the corporate 401k matching plan.",
        "Bereavement leave grants up to 5 consecutive paid business days for immediate family members.",
        "Tuition reimbursement is available for accredited degree programs aligned with your role.",
    ],
}

VECTOR_DIM = 64
DEFAULT_MIN_BASELINE_SAMPLES = 10
DEFAULT_MAX_BASELINE_SAMPLES = 500


def _compute_fallback_vector(text: str, dim: int = VECTOR_DIM) -> List[float]:
    """Compute a deterministic normalized n-gram hashed feature vector for text."""
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return [0.0] * dim

    vec = [0.0] * dim
    for word in words:
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign

    # L2 normalize
    norm = math.sqrt(sum(x ** 2 for x in vec))
    if norm > 0:
        vec = [round(x / norm, 5) for x in vec]
    return vec


def _cosine_sim(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))


class StatisticalAnomalyDetector(BaseDetector):
    """Detects semantic drift and statistical output anomalies against use-case baselines

    Embeds ai_response and evaluates cosine proximity against rolling distribution
    baselines stored in the database. Flags statistical outliers that deviate
    from standard domain responses.
    """

    detector_name: str = "statistical_anomaly_detector"

    def __init__(
        self,
        anomaly_threshold: float = 0.25,
        min_baseline_samples: int = DEFAULT_MIN_BASELINE_SAMPLES,
        max_baseline_samples: int = DEFAULT_MAX_BASELINE_SAMPLES,
        auto_seed: bool = True,
    ):
        self.anomaly_threshold = anomaly_threshold
        self.min_baseline_samples = min_baseline_samples
        self.max_baseline_samples = max_baseline_samples
        if auto_seed:
            self._ensure_baseline_seeded()

    def _ensure_baseline_seeded(self) -> None:
        """Seed baseline prototypes in SQLite if missing."""
        init_db()
        db: Session = SessionLocal()
        try:
            for use_case_id, samples in INITIAL_BASELINES.items():
                existing = db.query(BaselineResponseRecord).filter(
                    BaselineResponseRecord.use_case_id == use_case_id
                ).count()
                if existing == 0:
                    for i, sample in enumerate(samples):
                        vec = _compute_fallback_vector(sample)
                        record = BaselineResponseRecord(
                            id=f"base_{use_case_id}_{i}_{uuid.uuid4().hex[:6]}",
                            use_case_id=use_case_id,
                            sample_text=sample,
                            embedding_vector=vec,
                        )
                        db.add(record)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _get_baseline_vectors(self, use_case_id: str) -> List[List[float]]:
        """Fetch baseline vectors for a use case from the database."""
        db: Session = SessionLocal()
        try:
            records = (
                db.query(BaselineResponseRecord)
                .filter(BaselineResponseRecord.use_case_id == use_case_id)
                .order_by(BaselineResponseRecord.created_at.desc())
                .limit(self.max_baseline_samples)
                .all()
            )
            if records:
                return [r.embedding_vector for r in records if r.embedding_vector]
        except Exception:
            pass
        finally:
            db.close()
        return []

    def record_response_embedding(self, use_case_id: str, text: str, embedding: List[float]) -> None:
        """Add a processed response embedding to the rolling baseline pool (capped at max_baseline_samples)."""
        db: Session = SessionLocal()
        try:
            record = BaselineResponseRecord(
                id=f"rec_{use_case_id}_{uuid.uuid4().hex[:8]}",
                use_case_id=use_case_id,
                sample_text=text[:500],
                embedding_vector=embedding,
            )
            db.add(record)

            # Cap the rolling window: trim records older than max_baseline_samples
            count = (
                db.query(BaselineResponseRecord)
                .filter(BaselineResponseRecord.use_case_id == use_case_id)
                .count()
            )
            if count > self.max_baseline_samples:
                excess = count - self.max_baseline_samples
                oldest_records = (
                    db.query(BaselineResponseRecord.id)
                    .filter(BaselineResponseRecord.use_case_id == use_case_id)
                    .order_by(BaselineResponseRecord.created_at.asc())
                    .limit(excess)
                    .all()
                )
                oldest_ids = [r[0] for r in oldest_records]
                db.query(BaselineResponseRecord).filter(
                    BaselineResponseRecord.id.in_(oldest_ids)
                ).delete(synchronize_session=False)

            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    async def check(self, request: CheckRequest) -> RiskSignal:
        start_time = time.perf_counter()

        resp_vec = _compute_fallback_vector(request.ai_response)
        baseline_vecs = self._get_baseline_vectors(request.use_case_id)

        # Cold-Start Handling: If fewer than minimum baseline samples exist
        if len(baseline_vecs) < self.min_baseline_samples:
            # Asynchronously add the current embedding to build the history
            self.record_response_embedding(request.use_case_id, request.ai_response, resp_vec)
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["bias", "hallucination", "privacy"],
                confidence=0.0,
                evidence="insufficient baseline history for this use case, anomaly check skipped",
                latency_ms=self.calculate_latency_ms(start_time),
            )

        similarities = [_cosine_sim(resp_vec, b_vec) for b_vec in baseline_vecs]
        max_similarity = max(similarities) if similarities else 0.0
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0

        is_outlier = max_similarity < self.anomaly_threshold

        # Add processed response into the rolling baseline pool
        self.record_response_embedding(request.use_case_id, request.ai_response, resp_vec)

        if is_outlier:
            # =========================================================================
            # RISK DIMENSIONS & CONFIDENCE RATIONALE:
            # A statistical distribution outlier detects uncharacteristic vocabulary or
            # semantic drift, but cannot isolate whether the anomaly stems from a novel
            # demographic bias pattern, an ungrounded hallucination, or an unexpected
            # data exposure.
            # Thus, we tag ALL THREE dimensions ("bias", "hallucination", "privacy")
            # at a deliberately capped low confidence (capped at 0.40). This serves as
            # a coarse catch-all safety net for manual review without over-weighting
            # the automated decision tier.
            # =========================================================================
            deviation = max(0.0, 1.0 - max_similarity)
            confidence = min(0.40, 0.20 + (0.20 * deviation))
            evidence = (
                f"statistical outlier detected; exact risk category unknown, "
                f"treating as a broad low-confidence signal for review. "
                f"(max baseline similarity: {max_similarity:.2f} < threshold {self.anomaly_threshold:.2f}, "
                f"sample size: {len(baseline_vecs)})."
            )
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["bias", "hallucination", "privacy"],
                confidence=round(confidence, 2),
                evidence=evidence,
                latency_ms=self.calculate_latency_ms(start_time),
            )
        else:
            confidence = 0.05
            evidence = (
                f"Statistical in-distribution match: Response conforms to '{request.use_case_id}' "
                f"typical output patterns (max similarity: {max_similarity:.2f})."
            )
            return RiskSignal(
                detector_name=self.detector_name,
                risk_dimensions=["hallucination"],
                confidence=round(confidence, 2),
                evidence=evidence,
                latency_ms=self.calculate_latency_ms(start_time),
            )
