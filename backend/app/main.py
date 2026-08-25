import os
import sys
from pathlib import Path

# Ensure the backend directory is in sys.path when invoked directly or via uvicorn backend.app.main:app
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Configure structured logging for Render and local environments
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("controlplane.api")

from app.models import (
    CheckRequest,
    Decision,
    DecisionTier,
    RiskSignal,
    UseCaseProfile,
)
from app.db import init_db, get_db
from app.governance import (
    PolicyManager,
    PolicyConfig,
    AuditLogEntry,
    AuditLogQueryResponse,
    OverrideRequest,
    record_audit_event,
    query_audit_logs,
    record_human_override,
    GovernanceMetricsResponse,
    compute_governance_metrics,
)
from app.feedback import (
    compute_detector_performance,
    FeedbackPerformanceResponse,
)
from app.engine.orchestrator import Orchestrator

app = FastAPI(
    title="ControlPlane.ai",
    description="Responsible AI checking middleware for enterprise LLM deployments",
    version="0.1.0",
)

# Parse allowed CORS origins from environment variable (comma-separated), defaulting to local frontend
raw_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in raw_allowed_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()


@app.on_event("startup")
def on_startup():
    logger.info("Starting ControlPlane.ai Responsible AI Middleware...")
    logger.info(f"CORS enabled for origins: {allowed_origins}")
    init_db()
    loaded = PolicyManager.load_policies()
    logger.info(f"Loaded {len(loaded)} governance policy configurations: {list(loaded.keys())}")


@app.get("/health", tags=["System"])
def health_check():
    """Health-check endpoint to verify service availability."""
    return {
        "status": "ok",
        "service": "ControlPlane.ai",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/v1/use-cases", response_model=List[UseCaseProfile], tags=["Policies"])
def list_use_cases():
    """List all configured enterprise use case profiles and risk thresholds."""
    policies = PolicyManager.list_policies()
    return [p.to_use_case_profile() for p in policies]


@app.get("/v1/use-cases/{use_case_id}", response_model=UseCaseProfile, tags=["Policies"])
def get_use_case(use_case_id: str):
    """Get a specific use case profile by ID or alias."""
    policy = PolicyManager.get_policy(use_case_id)
    if not policy:
        logger.warning(f"Requested use case policy '{use_case_id}' was not found.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Use case policy '{use_case_id}' not found",
        )
    return policy.to_use_case_profile()


@app.post("/v1/check", response_model=Decision, tags=["Responsible AI Pipeline"])
async def check_interaction(request: CheckRequest, db: Session = Depends(get_db)):
    """Evaluate an LLM prompt and response pair against active Responsible AI risk policies.

    Executes all configured detectors concurrently, aggregates risk signals,
    persists full immutable audit log, and returns a policy-governed tier decision.
    """
    logger.info(f"Processing check request '{request.id}' for use case '{request.use_case_id}'")
    decision = await orchestrator.evaluate(request)
    # Immutable audit recording: nothing is checked without leaving a trace
    record_audit_event(db, request, decision)
    logger.info(f"Decision for '{request.id}': tier={decision.tier.value} conf={decision.aggregate_confidence:.3f}")
    return decision


@app.post("/v1/check/batch", response_model=List[Decision], tags=["Responsible AI Pipeline"])
async def check_interaction_batch(requests: List[CheckRequest], db: Session = Depends(get_db)):
    """Evaluate a batch of LLM interactions concurrently and record audit logs."""
    if not requests:
        return []

    logger.info(f"Processing batch of {len(requests)} check requests")
    decisions = await asyncio.gather(*(orchestrator.evaluate(req) for req in requests))

    for req, dec in zip(requests, decisions):
        record_audit_event(db, req, dec)

    return list(decisions)


@app.get("/v1/audit", response_model=AuditLogQueryResponse, tags=["Governance & Audit"])
def get_audit_trail(
    use_case_id: Optional[str] = Query(None, description="Filter by use case ID"),
    tier: Optional[str] = Query(None, description="Filter by decision tier (allow, edit, flag_for_review, block)"),
    from_date: Optional[datetime] = Query(None, alias="from", description="Filter records starting from ISO timestamp"),
    to_date: Optional[datetime] = Query(None, alias="to", description="Filter records up to ISO timestamp"),
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """Query the Responsible AI audit log with multi-dimensional filters."""
    total, records = query_audit_logs(
        db=db,
        use_case_id=use_case_id,
        tier=tier,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return AuditLogQueryResponse(
        total=total,
        items=[AuditLogEntry.from_record(r) for r in records],
    )


@app.post("/v1/audit/{decision_id}/override", response_model=AuditLogEntry, tags=["Governance & Audit"])
def override_audit_decision(
    decision_id: str,
    override_req: OverrideRequest,
    db: Session = Depends(get_db),
):
    """Record a human operator override on a policy decision with reviewer ID and justification note."""
    logger.info(f"Recording human override on decision '{decision_id}' by reviewer '{override_req.reviewer_id}' -> tier={override_req.override_tier.value}")
    record = record_human_override(db=db, decision_id=decision_id, override_req=override_req)
    if not record:
        logger.warning(f"Override attempted for non-existent decision '{decision_id}'")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit decision record '{decision_id}' not found",
        )
    return AuditLogEntry.from_record(record)


@app.get(
    "/v1/feedback/detector-performance",
    response_model=FeedbackPerformanceResponse,
    tags=["Feedback & Calibration"],
)
def get_detector_performance_metrics(
    use_case_id: Optional[str] = Query(None, description="Optional use case ID to filter calibration analysis"),
    db: Session = Depends(get_db),
):
    """Return per-detector calibration statistics and suggested threshold adjustments derived from human overrides."""
    return compute_detector_performance(db=db, use_case_id=use_case_id)


@app.get(
    "/v1/metrics/summary",
    response_model=GovernanceMetricsResponse,
    tags=["Governance & Metrics"],
)
def get_governance_metrics_summary(
    hours: int = Query(24, ge=1, le=168, description="Time window in hours for metrics aggregation"),
    db: Session = Depends(get_db),
):
    """Compute and expose system trustworthiness narrative, decision volume mix over time, error estimates, and latencies."""
    return compute_governance_metrics(db=db, hours=hours)
