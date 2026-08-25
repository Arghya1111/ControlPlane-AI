from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ChannelType(str, Enum):
    CUSTOMER_FACING = "customer_facing"
    INTERNAL = "internal"
    DECISION_SUPPORT = "decision_support"


class RiskTolerance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FailMode(str, Enum):
    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


class DecisionTier(str, Enum):
    ALLOW = "allow"
    EDIT = "edit"
    FLAG_FOR_REVIEW = "flag_for_review"
    BLOCK = "block"


RiskDimension = Literal["bias", "hallucination", "privacy"]


class UseCaseProfile(BaseModel):
    id: str = Field(..., description="Unique use case identifier (e.g. customer_support_chatbot)")
    name: str = Field(..., description="Human readable name of the deployment use case")
    channel_type: ChannelType = Field(..., description="Channel type: customer_facing, internal, decision_support")
    latency_budget_ms: int = Field(default=500, description="Allowed latency budget in milliseconds", ge=1)
    risk_tolerance: RiskTolerance = Field(default=RiskTolerance.MEDIUM, description="Risk tolerance tier: low, medium, high")
    fail_mode: FailMode = Field(default=FailMode.FAIL_OPEN, description="Behavior on pipeline timeout/error: fail_open, fail_closed")
    requires_human_review_above: float = Field(
        default=0.75,
        description="Confidence threshold above which human review is mandated",
        ge=0.0,
        le=1.0,
    )


class CheckRequest(BaseModel):
    id: str = Field(..., description="Unique interaction / request identifier")
    use_case_id: str = Field(..., description="Referenced UseCaseProfile id")
    prompt: str = Field(..., description="User prompt or input message sent to the LLM")
    ai_response: str = Field(..., description="Model-generated response to be checked")
    retrieved_context: Optional[List[str]] = Field(
        default=None,
        description="Optional list of retrieved RAG documents/context passages",
    )
    conversation_history: Optional[List[str]] = Field(
        default=None,
        description="Optional list of previous conversation turns",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata such as user_id, tenant_id, session_id, model_name",
    )


class RiskSignal(BaseModel):
    detector_name: str = Field(..., description="Identifier of the detector producing this signal")
    risk_dimensions: List[RiskDimension] = Field(
        ...,
        description="List of risk dimensions evaluated (bias, hallucination, privacy)",
    )
    confidence: float = Field(
        ...,
        description="Confidence score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    evidence: str = Field(..., description="Human-readable explanation / snippet justifying the signal")
    latency_ms: float = Field(..., description="Time taken by detector to evaluate in milliseconds", ge=0.0)


class Decision(BaseModel):
    request_id: str = Field(..., description="Corresponding CheckRequest ID")
    tier: DecisionTier = Field(..., description="Policy decision: allow, edit, flag_for_review, block")
    aggregate_confidence: float = Field(
        ...,
        description="Aggregated risk confidence score between 0.0 and 1.0",
        ge=0.0,
        le=1.0,
    )
    contributing_signals: List[RiskSignal] = Field(
        default_factory=list,
        description="List of individual detector risk signals that drove the decision",
    )
    rationale: str = Field(..., description="Human-readable synthesis explaining the final decision")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the decision was synthesized",
    )
    reviewed_by: Optional[str] = Field(
        default=None,
        description="User/operator ID if reviewed or overwritten by a human",
    )
    override: Optional[bool] = Field(
        default=None,
        description="Flag indicating whether an operator overrode the automated decision",
    )


class CheckResult(BaseModel):
    request_id: str = Field(..., description="CheckRequest identifier")
    decision: Decision = Field(..., description="Final Responsible AI decision")
    latency_ms: float = Field(..., description="Total middleware processing latency in ms", ge=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Passthrough metadata and runtime telemetry")
