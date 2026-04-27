from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SAEnum
import uuid

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class EmailStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class EmailAction(str, Enum):
    accepted = "accepted"
    rejected = "rejected"


class EmailEvent(SQLModel, table=True):
    __tablename__ = "email_events"

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)

    source_filename: str
    raw_path: str

    status: EmailStatus = Field(
        default=EmailStatus.queued,
        sa_column=Column(SAEnum(EmailStatus, name="email_status"), nullable=False, index=True),
    )
    error: Optional[str] = None

    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
            index=True,
        )
    )

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
            index=True,
        )
    )
    processed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class EmailParsed(SQLModel, table=True):
    __tablename__ = "email_parsed"

    # 1:1 with event
    event_id: uuid.UUID = Field(primary_key=True, foreign_key="email_events.event_id")

    fingerprint: str = Field(index=True)
    canonical_fingerprint: Optional[str] = Field(default=None, index=True)
    duplicate_of: Optional[uuid.UUID] = Field(default=None, foreign_key="email_parsed.event_id", index=True)

    # hot fields for UI/ML
    from_address: Optional[str] = Field(default=None, index=True)
    to_address: Optional[str] = Field(default=None, index=True)
    subject: Optional[str] = Field(default=None, index=True)
    date: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )

    spf: Optional[str] = Field(default=None, index=True)
    dkim: Optional[str] = Field(default=None, index=True)
    dmarc: Optional[str] = Field(default=None, index=True)

    display_name_mismatch: bool = Field(default=False, index=True)
    sender_domain_mismatch: bool = Field(default=False, index=True)
    lookalike_domain_detected: bool = Field(default=False, index=True)
    internal_impersonation: bool = Field(default=False, index=True)
    unicode_trick_detected: bool = Field(default=False, index=True)

    urgency: Optional[int] = None
    credentials: Optional[int] = None
    payment: Optional[int] = None
    threat: Optional[int] = None

    # 1) full JSON payload
    parsed_payload: Dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))

    # Triage model output
    prob_phishing: Optional[float] = Field(default = None)
    prob_benign: Optional[float] = Field(default = None)


class EmailResolutionBase(SQLModel):
    action: EmailAction = Field(
        sa_column=Column(SAEnum(EmailAction, name="email_action"), nullable=False, index=True),
    )

    reason: str = Field(nullable=False)

class EmailResolution(EmailResolutionBase, table=True):
    __tablename__ = "email_resolutions"

    event_id: uuid.UUID = Field(primary_key=True, foreign_key="email_events.event_id")
    acting_user_id: uuid.UUID = Field(foreign_key="user.id")

    date: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
