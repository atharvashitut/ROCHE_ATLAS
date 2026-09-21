"""Classify change risk and produce complete, policy-traceable change requests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from change_mgmt.risk_calendar import RiskAssessment
from change_mgmt.veeva_rules import ChangePolicy, ChangeType


@dataclass(frozen=True)
class ChangeRequestRecord:
    change_id: str
    classification: ChangeType
    risk_assessment: dict[str, Any]
    implementation_plan: list[str]
    test_plan: list[str]
    backout_plan: list[str]
    approver_routing: list[str]
    required_fields: list[str]
    policy_trace: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChangeRequestBuilder:
    def classify(self, assessment: RiskAssessment, requested_type: ChangeType | None = None) -> ChangeType:
        if requested_type == ChangeType.EMERGENCY or assessment.score >= 85:
            return ChangeType.EMERGENCY
        if assessment.score <= 30:
            return ChangeType.LOW
        return ChangeType.NORMAL

    def build(self, payload: Any, assessment: RiskAssessment, policy: ChangePolicy) -> ChangeRequestRecord:
        return ChangeRequestRecord(
            change_id=payload.change_id,
            classification=policy.change_type,
            risk_assessment={"score": assessment.score, "factors": list(assessment.factors), "blackout_conflicts": list(assessment.blackout_conflicts)},
            implementation_plan=list(payload.implementation_steps),
            test_plan=list(payload.test_steps),
            backout_plan=list(payload.backout_steps) or ["Restore the last verified configuration and validate service health."],
            approver_routing=list(policy.approver_roles),
            required_fields=list(policy.required_fields),
            policy_trace={"document_id": policy.source_document, "page": policy.source_page, "excerpt": policy.source_excerpt},
        )
