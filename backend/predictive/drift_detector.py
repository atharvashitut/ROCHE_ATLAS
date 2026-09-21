"""Compare CMDB configuration snapshots against Veeva validation baselines."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DriftFinding:
    field: str
    expected: Any
    observed: Any
    severity: str


@dataclass(frozen=True)
class DriftReport:
    ci_id: str
    compliant: bool
    drift_score: int
    findings: tuple[DriftFinding, ...]

    def as_dict(self) -> dict:
        return {"ci_id": self.ci_id, "compliant": self.compliant, "drift_score": self.drift_score, "findings": [asdict(finding) for finding in self.findings]}


class DriftDetector:
    def detect(self, ci_id: str, snapshot: dict[str, Any], baseline: dict[str, Any]) -> DriftReport:
        findings: list[DriftFinding] = []
        for field, expected in baseline.items():
            observed = snapshot.get(field)
            if observed != expected:
                severity = "high" if field in {"validation_state", "encryption", "audit_logging"} else "medium"
                findings.append(DriftFinding(field, expected, observed, severity))
        for field in snapshot.keys() - baseline.keys():
            findings.append(DriftFinding(field, "<not permitted by baseline>", snapshot[field], "low"))
        weighted = sum({"high": 40, "medium": 20, "low": 8}[finding.severity] for finding in findings)
        return DriftReport(ci_id, not findings, min(100, weighted), tuple(findings))
