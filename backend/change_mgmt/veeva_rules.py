"""Parse extracted Veeva evidence into traceable change-control policies."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class ChangeType(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    EMERGENCY = "emergency"


@dataclass(frozen=True)
class VeevaEvidence:
    document_id: str
    page: int
    extracted_text: str
    source_kind: str = "pdf"


@dataclass(frozen=True)
class ChangePolicy:
    change_type: ChangeType
    required_fields: tuple[str, ...]
    approver_roles: tuple[str, ...]
    minimum_lead_hours: int
    source_document: str
    source_page: int
    source_excerpt: str


_POLICY_DEFINITIONS = {
    ChangeType.LOW: {
        "required_fields": ("risk_assessment", "implementation_plan", "test_plan", "backout_plan"),
        "approver_roles": ("service_owner",),
        "minimum_lead_hours": 24,
    },
    ChangeType.NORMAL: {
        "required_fields": ("risk_assessment", "implementation_plan", "test_plan", "backout_plan", "business_impact"),
        "approver_roles": ("service_owner", "change_manager"),
        "minimum_lead_hours": 72,
    },
    ChangeType.EMERGENCY: {
        "required_fields": ("risk_assessment", "implementation_plan", "test_plan", "backout_plan", "emergency_justification"),
        "approver_roles": ("emergency_change_manager", "service_owner"),
        "minimum_lead_hours": 0,
    },
}


class VeevaRulesParser:
    """Maps OCR/PDF mock results to policy records with page-level provenance."""

    def parse(self, mock_outputs: Iterable[Mapping[str, object]]) -> dict[ChangeType, ChangePolicy]:
        evidence = [self._to_evidence(output) for output in mock_outputs]
        policies: dict[ChangeType, ChangePolicy] = {}
        for change_type in ChangeType:
            source = self._find_source(change_type, evidence)
            if source:
                policies[change_type] = self._build_policy(change_type, source)
        return policies

    def policy_for(self, change_type: ChangeType, mock_outputs: Iterable[Mapping[str, object]]) -> ChangePolicy:
        policies = self.parse(mock_outputs)
        if change_type not in policies:
            raise ValueError(f"No Veeva policy evidence found for {change_type.value} changes")
        return policies[change_type]

    @staticmethod
    def _to_evidence(output: Mapping[str, object]) -> VeevaEvidence:
        try:
            return VeevaEvidence(
                document_id=str(output["document_id"]),
                page=int(output["page"]),
                extracted_text=str(output["text"]),
                source_kind=str(output.get("source_kind", "pdf")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Veeva mock output requires document_id, page, and text") from exc

    @staticmethod
    def _find_source(change_type: ChangeType, evidence: list[VeevaEvidence]) -> VeevaEvidence | None:
        marker = change_type.value
        return next((item for item in evidence if marker in item.extracted_text.lower()), None)

    @staticmethod
    def _build_policy(change_type: ChangeType, source: VeevaEvidence) -> ChangePolicy:
        definition = _POLICY_DEFINITIONS[change_type]
        return ChangePolicy(
            change_type=change_type,
            required_fields=definition["required_fields"],
            approver_roles=definition["approver_roles"],
            minimum_lead_hours=definition["minimum_lead_hours"],
            source_document=source.document_id,
            source_page=source.page,
            source_excerpt=source.extracted_text[:240],
        )
