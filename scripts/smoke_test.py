#!/usr/bin/env python3
"""Run schema-checked smoke tests for every ITSM-Copilot `/api/v1/` endpoint."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SmokeCase:
    name: str
    method: str
    path: str
    payload: dict[str, Any] | None
    validate: Callable[[Any], None]


def request(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(f"{base_url.rstrip('/')}{path}", data=body, method=method, headers=headers)
    with urlopen(req, timeout=15) as response:  # noqa: S310 - base URL is an explicit operator argument
        return response.status, json.loads(response.read().decode("utf-8"))


def object_schema(**fields: type | tuple[type, ...]) -> Callable[[Any], None]:
    def validate(value: Any) -> None:
        if not isinstance(value, dict):
            raise AssertionError(f"expected object, got {type(value).__name__}")
        for key, expected_type in fields.items():
            if key not in value:
                raise AssertionError(f"missing required field: {key}")
            if not isinstance(value[key], expected_type):
                raise AssertionError(f"field {key} must be {expected_type}, got {type(value[key]).__name__}")
    return validate


def audit_list_schema(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise AssertionError("expected a non-empty audit array")
    object_schema(entry_id=str, recorded_at=str, location=str, payload=dict)(value[0])


def build_cases() -> list[SmokeCase]:
    image = base64.b64encode(b"synthetic-screenshot").decode("ascii")
    change = {
        "change_id": "CHG-3048", "title": "Vault authentication timeout update", "description": "Increase the Vault integration timeout to reduce authentication failures.", "requested_by": "platform-ops", "ci_ids": ["CI-VAULT"], "planned_start": "2026-10-01T09:00:00+00:00", "planned_end": "2026-10-01T11:30:00+00:00", "requested_type": "normal", "implementation_steps": ["Update timeout configuration"], "test_steps": ["Verify authentication health"], "backout_steps": ["Restore previous configuration"],
    }
    playbook = {
        "change_id": "CHG-3048", "system": "Veeva Vault", "environment": "production", "owner": "platform-ops", "planned_start": "2026-10-01T09:00:00+00:00", "planned_end": "2026-10-01T11:30:00+00:00", "implementation_steps": ["Deploy {system} update"], "validation_steps": ["Validate authentication"], "backout_steps": ["Restore prior release"],
    }
    return [
        SmokeCase("triage vision", "POST", "/api/v1/triage/vision", {"image_base64": image}, object_schema(document_title=str, document_reference=str, confidence=(int, float), draft_type=str, draft=str)),
        SmokeCase("incident relationship traversal", "GET", "/api/v1/triage/incidents/parent-1/relationships", None, object_schema(ticket=dict, children=list, problem=(dict, type(None)))),
        SmokeCase("change risk and Veeva policy", "POST", "/api/v1/changes", change, object_schema(change_id=str, classification=str, risk_assessment=dict, policy_trace=dict)),
        SmokeCase("audit event creation", "POST", "/api/v1/audit", {"action": "smoke.executed", "actor": "smoke.runner", "resource": "CHG-3048", "details": {"patient_id": "synthetic", "result": "pass"}, "occurred_at": "2026-10-01T08:30:00+00:00"}, object_schema(entry_id=str, recorded_at=str, location=str, payload=dict)),
        SmokeCase("audit stream", "GET", "/api/v1/audit", None, audit_list_schema),
        SmokeCase("implementation playbook", "POST", "/api/v1/audit/playbook", playbook, object_schema(change_id=str, target=str, items=list)),
        SmokeCase("predictive root cause analysis", "POST", "/api/v1/predictive/rca", {"logs": [{"trace_id": "trace-42", "content": "Gateway timeout during Vault authentication"}], "tickets": [{"number": "INC0010042", "summary": "Repeated Vault timeout", "impact": "high"}]}, object_schema(probable_causes=list, evidence_links=list)),
        SmokeCase("problem record generation", "POST", "/api/v1/predictive/problem", {"service": "Veeva Vault", "summary": "Recurring authentication timeouts", "incident_numbers": ["INC0010042", "INC0010043", "INC0010044"], "recurrence_count": 3, "high_impact_outage": False}, object_schema(should_create=bool, reason=str, record=(dict, type(None)))),
        SmokeCase("CMDB drift detection", "POST", "/api/v1/predictive/drift", {"ci_id": "CI-VAULT", "snapshot": {"validation_state": "draft", "timeout_seconds": 60}, "baseline": {"validation_state": "approved", "timeout_seconds": 30}}, object_schema(ci_id=str, compliant=bool, drift_score=int, findings=list)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000", help="running API root URL")
    args = parser.parse_args()
    passed: list[str] = []
    cases = build_cases()
    for case in cases:
        try:
            status, payload = request(args.base_url, case.method, case.path, case.payload)
            if status not in {200, 201}:
                raise AssertionError(f"expected HTTP 200/201, received {status}")
            case.validate(payload)
        except (HTTPError, URLError, AssertionError, json.JSONDecodeError) as exc:
            print(f"FAIL {case.name}: {exc}", file=sys.stderr)
            print(f"RESULT {len(passed)}/{len(cases)} endpoint checks passed", file=sys.stderr)
            return 1
        passed.append(case.name)
        print(f"PASS {case.name}")
    print(f"RESULT PASS {len(passed)}/{len(cases)} `/api/v1/` endpoint checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
