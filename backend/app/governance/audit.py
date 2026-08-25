from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import CheckRequest, Decision, DecisionTier, RiskSignal
from app.db import AuditLogRecord, DecisionRecord
from app.feedback.loop import store_feedback_example


class OverrideRequest(BaseModel):
    reviewer_id: str = Field(..., description="Operator/reviewer ID recording the override")
    override_tier: DecisionTier = Field(..., description="Target decision tier after review (e.g. allow, block, edit)")
    notes: str = Field(..., description="Justification note explaining why the automated decision was modified")


class AuditLogEntry(BaseModel):
    id: str
    request_id: str
    use_case_id: str
    prompt: str
    ai_response: str
    retrieved_context: Optional[List[str]] = None
    conversation_history: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tier: DecisionTier
    aggregate_confidence: float
    contributing_signals: List[RiskSignal] = Field(default_factory=list)
    rationale: str
    reviewed_by: Optional[str] = None
    override: bool = False
    override_tier: Optional[DecisionTier] = None
    override_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(cls, record: AuditLogRecord) -> "AuditLogEntry":
        """Convert SQLAlchemy AuditLogRecord to Pydantic AuditLogEntry."""
        signals = [RiskSignal.model_validate(s) for s in (record.contributing_signals or [])]
        return cls(
            id=record.id,
            request_id=record.request_id,
            use_case_id=record.use_case_id,
            prompt=record.prompt,
            ai_response=record.ai_response,
            retrieved_context=record.retrieved_context,
            conversation_history=record.conversation_history,
            metadata=record.metadata_payload or {},
            tier=DecisionTier(record.tier),
            aggregate_confidence=record.aggregate_confidence,
            contributing_signals=signals,
            rationale=record.rationale,
            reviewed_by=record.reviewed_by,
            override=record.override,
            override_tier=DecisionTier(record.override_tier) if record.override_tier else None,
            override_notes=record.override_notes,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class AuditLogQueryResponse(BaseModel):
    total: int
    items: List[AuditLogEntry]


def record_audit_event(db: Session, request: CheckRequest, decision: Decision) -> AuditLogRecord:
    """Record an interaction check and synthesized decision into the immutable audit trail."""
    decision_id = f"dec_{request.id}"
    signals_json = [s.model_dump() for s in decision.contributing_signals]

    record = AuditLogRecord(
        id=decision_id,
        request_id=request.id,
        use_case_id=request.use_case_id,
        prompt=request.prompt,
        ai_response=request.ai_response,
        retrieved_context=request.retrieved_context,
        conversation_history=request.conversation_history,
        metadata_payload=request.metadata,
        tier=decision.tier.value if isinstance(decision.tier, DecisionTier) else str(decision.tier),
        aggregate_confidence=decision.aggregate_confidence,
        contributing_signals=signals_json,
        rationale=decision.rationale,
        reviewed_by=decision.reviewed_by,
        override=decision.override or False,
        override_tier=None,
        override_notes=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    record = db.merge(record)
    db.commit()
    db.refresh(record)
    return record


def query_audit_logs(
    db: Session,
    use_case_id: Optional[str] = None,
    tier: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[int, List[AuditLogRecord]]:
    """Query audit logs with dynamic filtering, sorting by most recent first."""
    query = db.query(AuditLogRecord)

    if use_case_id:
        query = query.filter(AuditLogRecord.use_case_id == use_case_id)
    if tier:
        query = query.filter(AuditLogRecord.tier == tier.lower())
    if from_date:
        query = query.filter(AuditLogRecord.created_at >= from_date)
    if to_date:
        query = query.filter(AuditLogRecord.created_at <= to_date)

    total = query.count()
    records = query.order_by(desc(AuditLogRecord.created_at)).offset(offset).limit(limit).all()
    return total, records


def count_audit_logs(
    db: Session,
    use_case_id: Optional[str] = None,
    tier: Optional[str] = None,
) -> int:
    """Return fast total count of audit logs matching filters."""
    query = db.query(AuditLogRecord)
    if use_case_id:
        query = query.filter(AuditLogRecord.use_case_id == use_case_id)
    if tier:
        query = query.filter(AuditLogRecord.tier == tier.lower())
    return query.count()


def record_human_override(
    db: Session,
    decision_id: str,
    override_req: OverrideRequest,
) -> Optional[AuditLogRecord]:
    """Record a human reviewer override for an audited decision.

    Updates the record's tier, override flag, reviewer, and justification note,
    and stores a labeled feedback training example for detector calibration.
    """
    record = db.query(AuditLogRecord).filter(AuditLogRecord.id == decision_id).first()
    if not record:
        # Check by request_id if decision_id was formatted as req-...
        record = db.query(AuditLogRecord).filter(AuditLogRecord.request_id == decision_id).first()

    if not record:
        return None

    old_tier = record.tier

    # Update audit record
    record.tier = override_req.override_tier.value
    record.override = True
    record.override_tier = override_req.override_tier.value
    record.override_notes = override_req.notes
    record.reviewed_by = override_req.reviewer_id
    record.updated_at = datetime.now(timezone.utc)
    record.rationale = (
        f"{record.rationale} [OVERRIDE by {override_req.reviewer_id}: "
        f"Tier changed to {override_req.override_tier.value.upper()}. Notes: {override_req.notes}]"
    )

    db.commit()
    db.refresh(record)

    # Store labeled training example for feedback loop and calibration analytics
    store_feedback_example(
        db=db,
        decision_id=record.id,
        use_case_id=record.use_case_id,
        original_tier=old_tier,
        corrected_tier=override_req.override_tier.value,
        reviewer_id=override_req.reviewer_id,
        justification=override_req.notes,
        prompt=record.prompt,
        ai_response=record.ai_response,
        contributing_signals=record.contributing_signals or [],
    )

    return record
