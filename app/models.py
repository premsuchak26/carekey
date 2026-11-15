"""Core domain models for CareKey platform."""

import datetime as dt
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class MemberRole(StrEnum):
    """Member roles with hierarchical permissions."""

    VIEWER = "VIEWER"
    HELPER = "HELPER"
    MANAGER = "MANAGER"
    ELDER = "ELDER"

    @property
    def level(self) -> int:
        """Numeric permission level for hierarchy comparison."""
        match self:
            case MemberRole.VIEWER:
                return 1
            case MemberRole.HELPER:
                return 2
            case MemberRole.MANAGER:
                return 3
            case MemberRole.ELDER:
                return 4


class Elder(BaseModel):
    """Elder profile owning a CareCircle."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    phone: str | None = None
    notes: str | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now())


class CareCircle(BaseModel):
    """CareCircle coordinating elder support with a unique circle code."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    circle_code: str
    elder_id: str
    name: str
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now())


class Member(BaseModel):
    """Circle member with role-based permissions and scrypt-hashed access key."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    circle_id: str
    name: str
    role: MemberRole
    key_hash: str
    salt: str
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now())
    expires_at: dt.datetime | None = None
    revoked_at: dt.datetime | None = None
    failed_attempts: int = 0
    locked_until: dt.datetime | None = None


class DoseSchedule(BaseModel):
    """Medication dosing schedule."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    medication_id: str
    times_of_day: list[str] = Field(default_factory=lambda: ["08:00"])  # HH:MM format
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 0=Mon, 6=Sun
    start_date: dt.date = Field(default_factory=lambda: dt.datetime.now().date())
    end_date: dt.date | None = None
    max_doses_per_day: int = 1
    dose_amount: str = "1 tablet"


class Medication(BaseModel):
    """Medication record associated with a CareCircle."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    circle_id: str
    name: str
    dosage: str
    instructions: str = ""
    prescribing_doctor: str = ""
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now())
    schedule: DoseSchedule | None = None


class DoseEvent(BaseModel):
    """Recorded dose administration event."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    circle_id: str
    medication_id: str
    scheduled_time: dt.datetime
    status: Literal["taken", "skipped"]
    dose_status: Literal["on_time", "late", "missed", "skipped"]
    timestamp: dt.datetime = Field(default_factory=lambda: dt.datetime.now())
    logged_by: str = ""
    notes: str = ""


class Appointment(BaseModel):
    """Scheduled healthcare appointment."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    circle_id: str
    doctor: str
    place: str
    datetime: dt.datetime
    notes: str = ""
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now())


class AdherenceSummary(BaseModel):
    """Medication adherence metrics."""

    medication_id: str
    medication_name: str
    total_doses: int
    taken_doses: int
    on_time_doses: int
    late_doses: int
    missed_doses: int
    skipped_doses: int
    adherence_percentage: float
    streak_days: int


class RiskLevel(StrEnum):
    """Risk tiers for medication change proposals."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ProposalStatus(StrEnum):
    """Lifecycle statuses for two-key change proposals."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EMERGENCY_APPLIED = "EMERGENCY_APPLIED"


class ChangeProposal(BaseModel):
    """Two-key rule change proposal submitted by non-elder manager."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    circle_id: str
    elder_id: str
    author_id: str
    author_name: str
    author_role: str = "MANAGER"
    target_type: Literal["medication", "schedule"] = "medication"
    action: Literal["add", "edit", "delete"]
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str
    status: ProposalStatus = ProposalStatus.PENDING
    risk_level: RiskLevel = RiskLevel.LOW
    risk_reasons: list[str] = Field(default_factory=list)
    is_emergency: bool = False
    emergency_reason: str | None = None
    rejection_reason: str | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now())
    resolved_at: dt.datetime | None = None
    resolved_by_id: str | None = None
    resolved_by_name: str | None = None


class AuditEntry(BaseModel):
    """Append-only, cryptographically linked audit log entry."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    elder_id: str
    actor: str
    action: str
    target: str
    timestamp: dt.datetime = Field(default_factory=lambda: dt.datetime.now())
    details: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    hash: str
    circle_id: str = ""
