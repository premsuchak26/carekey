"""Core domain models for CareKey platform."""

import datetime as dt
from enum import StrEnum
from typing import Literal
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
