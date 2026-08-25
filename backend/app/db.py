import os
from datetime import datetime, timezone
from typing import Generator
from sqlalchemy import Column, String, Float, DateTime, Text, JSON, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./controlplane.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class CheckRequestRecord(Base):
    __tablename__ = "check_requests"

    id = Column(String(64), primary_key=True, index=True)
    use_case_id = Column(String(64), index=True, nullable=False)
    prompt = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    retrieved_context = Column(JSON, nullable=True)
    conversation_history = Column(JSON, nullable=True)
    metadata_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DecisionRecord(Base):
    __tablename__ = "decisions"

    id = Column(String(64), primary_key=True, index=True)
    request_id = Column(String(64), index=True, nullable=False)
    tier = Column(String(32), nullable=False, index=True)
    aggregate_confidence = Column(Float, nullable=False)
    contributing_signals = Column(JSON, nullable=False)
    rationale = Column(Text, nullable=False)
    reviewed_by = Column(String(64), nullable=True)
    override = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class AuditLogRecord(Base):
    """Complete, immutable audit trail record for every checked interaction and policy decision."""
    __tablename__ = "audit_log"

    id = Column(String(64), primary_key=True, index=True)  # decision_id (e.g. dec_req-123)
    request_id = Column(String(64), index=True, nullable=False)
    use_case_id = Column(String(64), index=True, nullable=False)
    prompt = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    retrieved_context = Column(JSON, nullable=True)
    conversation_history = Column(JSON, nullable=True)
    metadata_payload = Column(JSON, nullable=True)
    tier = Column(String(32), index=True, nullable=False)
    aggregate_confidence = Column(Float, nullable=False)
    contributing_signals = Column(JSON, nullable=False)
    rationale = Column(Text, nullable=False)
    reviewed_by = Column(String(64), nullable=True)
    override = Column(Boolean, default=False, nullable=False)
    override_tier = Column(String(32), nullable=True)
    override_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class FeedbackExampleRecord(Base):
    """Stores labeled feedback training examples derived from human overrides."""
    __tablename__ = "feedback_examples"

    id = Column(String(64), primary_key=True, index=True)
    decision_id = Column(String(64), index=True, nullable=False)
    use_case_id = Column(String(64), index=True, nullable=False)
    original_tier = Column(String(32), nullable=False)
    corrected_tier = Column(String(32), nullable=False)
    reviewer_id = Column(String(64), nullable=False)
    justification = Column(Text, nullable=True)
    prompt = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    contributing_signals = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True, nullable=False)


class BaselineResponseRecord(Base):
    __tablename__ = "baseline_responses"

    id = Column(String(64), primary_key=True, index=True)
    use_case_id = Column(String(64), index=True, nullable=False)
    sample_text = Column(Text, nullable=False)
    embedding_vector = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency for database session management."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
