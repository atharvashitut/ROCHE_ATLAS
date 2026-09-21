#!/usr/bin/env python3
"""Write deterministic local mock data for ITSM-Copilot adapters and demos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_seed_data() -> dict:
    """Return a stable seed package; no random or live-system data is used."""
    return {
        "metadata": {"dataset_version": "1.0", "generated_at": "2026-10-01T08:00:00Z", "classification": "synthetic"},
        "servicenow": {
            "tickets": [
                {"sys_id": "parent-1", "number": "INC0010001", "short_description": "Veeva Vault login timeout", "state": "In Progress", "problem_id": "prb-7"},
                {"sys_id": "child-1", "number": "INC0010002", "short_description": "Veeva Vault login timeout for EU user", "state": "New", "parent": "parent-1"},
                {"sys_id": "recurrence-1", "number": "INC0010042", "short_description": "Gateway authentication timeout", "state": "Resolved"},
                {"sys_id": "recurrence-2", "number": "INC0010043", "short_description": "Gateway authentication timeout", "state": "Resolved"},
                {"sys_id": "recurrence-3", "number": "INC0010044", "short_description": "Gateway authentication timeout", "state": "Resolved"},
            ],
            "problems": [{"sys_id": "prb-7", "number": "PRB0000007", "short_description": "Vault authentication latency"}],
        },
        "veeva_vault": {
            "sops": [
                {"document_id": "Veeva Doc #501", "page": 4, "change_type": "low", "text": "Low change requires service owner approval and documented validation."},
                {"document_id": "Veeva Doc #501", "page": 7, "change_type": "normal", "text": "Normal change requires change manager approval, a test plan, and a backout plan."},
                {"document_id": "Veeva Doc #501", "page": 11, "change_type": "emergency", "text": "Emergency change requires emergency change manager authorization."},
            ]
        },
        "cmdb": {
            "baseline": {"ci_id": "CI-VAULT", "validation_state": "approved", "timeout_seconds": 30, "audit_logging": True},
            "snapshot": {"ci_id": "CI-VAULT", "validation_state": "draft", "timeout_seconds": 60, "audit_logging": True, "debug_mode": True},
        },
        "qdrant": {
            "collection": "knowledge_base",
            "vector_size": 2,
            "points": [
                {"id": "445", "vector": [0.12, 0.34], "payload": {"document_id": "445", "title": "Resolve Veeva Vault Login Timeouts", "reference": "Veeva Doc #445", "approved": True}},
                {"id": "446", "vector": [0.88, 0.05], "payload": {"document_id": "446", "title": "Validate Vault Certificate Rotation", "reference": "Veeva Doc #446", "approved": True}},
            ],
        },
        "audit_stream": [
            {
                "action": "change.approved",
                "actor": "change.manager",
                "resource": "CHG-3048",
                "details": {
                    "patient_name": "Synthetic Patient",
                    "patient_email": "synthetic.patient@example.invalid",
                    "mrn": "SYN-000042",
                    "date_of_birth": "1970-01-01",
                    "decision": "approved",
                },
                "occurred_at": "2026-10-01T08:30:00Z",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/mock_seed.json"), help="JSON destination")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_seed_data(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote deterministic synthetic data to {args.output}")


if __name__ == "__main__":
    main()
