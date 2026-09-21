"""Validated API contracts for change and audit workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from change_mgmt.veeva_rules import ChangeType


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChangeRequestPayload(_StrictModel):
    change_id: str = Field(pattern=r"^CHG[A-Z0-9-]{3,40}$")
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=4000)
    requested_by: str = Field(min_length=3, max_length=120)
    ci_ids: list[str] = Field(min_length=1, max_length=20)
    planned_start: datetime
    planned_end: datetime
    requested_type: ChangeType = ChangeType.NORMAL
    implementation_steps: list[str] = Field(min_length=1, max_length=30)
    test_steps: list[str] = Field(min_length=1, max_length=30)
    backout_steps: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("ci_ids", "implementation_steps", "test_steps", "backout_steps")
    @classmethod
    def nonempty_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("list entries must not be blank")
        return values

    @field_validator("planned_start", "planned_end")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone offset")
        return value

    @model_validator(mode="after")
    def valid_window(self) -> "ChangeRequestPayload":
        if self.planned_end <= self.planned_start:
            raise ValueError("planned_end must be after planned_start")
        if len(set(self.ci_ids)) != len(self.ci_ids):
            raise ValueError("ci_ids must be unique")
        return self


class AuditLogRequest(_StrictModel):
    action: str = Field(min_length=3, max_length=120)
    actor: str = Field(min_length=3, max_length=120)
    resource: str = Field(min_length=3, max_length=180)
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def audit_time_has_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone offset")
        return value


class AuditLogResponse(_StrictModel):
    entry_id: str
    recorded_at: str
    location: str
    payload: dict[str, Any]


class PlaybookRequest(_StrictModel):
    change_id: str = Field(pattern=r"^CHG[A-Z0-9-]{3,40}$")
    system: str = Field(min_length=2, max_length=80)
    environment: str = Field(min_length=2, max_length=40)
    owner: str = Field(min_length=3, max_length=120)
    planned_start: datetime
    planned_end: datetime
    implementation_steps: list[str] = Field(min_length=1, max_length=30)
    validation_steps: list[str] = Field(min_length=1, max_length=30)
    backout_steps: list[str] = Field(min_length=1, max_length=30)

    @field_validator("planned_start", "planned_end")
    @classmethod
    def playbook_time_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone offset")
        return value

    @model_validator(mode="after")
    def playbook_window_is_valid(self) -> "PlaybookRequest":
        if self.planned_end <= self.planned_start:
            raise ValueError("planned_end must be after planned_start")
        return self


class RCAEvidenceLog(_StrictModel):
    trace_id: str = Field(min_length=2, max_length=80)
    content: str = Field(min_length=3, max_length=8000)


class RCATicketHistory(_StrictModel):
    number: str = Field(pattern=r"^INC[A-Z0-9-]{3,40}$")
    summary: str = Field(min_length=3, max_length=1000)
    impact: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")


class RCARequest(_StrictModel):
    logs: list[RCAEvidenceLog] = Field(default_factory=list, max_length=30)
    tickets: list[RCATicketHistory] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def has_evidence(self) -> "RCARequest":
        if not self.logs and not self.tickets:
            raise ValueError("at least one log or ticket is required")
        return self


class ProblemRequest(_StrictModel):
    service: str = Field(min_length=2, max_length=120)
    summary: str = Field(min_length=8, max_length=500)
    incident_numbers: list[str] = Field(min_length=1, max_length=50)
    recurrence_count: int = Field(ge=0, le=10000)
    high_impact_outage: bool = False

    @field_validator("incident_numbers")
    @classmethod
    def valid_incident_numbers(cls, values: list[str]) -> list[str]:
        if any(not value.startswith("INC") or len(value) < 6 for value in values):
            raise ValueError("incident_numbers must contain ServiceNow INC references")
        return values


class DriftRequest(_StrictModel):
    ci_id: str = Field(min_length=2, max_length=120)
    snapshot: dict[str, Any] = Field(min_length=1, max_length=100)
    baseline: dict[str, Any] = Field(min_length=1, max_length=100)
