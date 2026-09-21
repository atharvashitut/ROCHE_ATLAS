from datetime import datetime, timezone

import pytest

from app.models import PlaybookRequest
from audit.gdrive_audit import AuditLogger, MockGoogleDriveDocsAdapter
from audit.playbook_gen import PlaybookGenerator


@pytest.mark.asyncio
async def test_audit_log_redacts_sensitive_details_and_is_immutable():
    adapter = MockGoogleDriveDocsAdapter()
    entry, location = await AuditLogger(adapter).record(
        action="change.approved",
        actor="change.manager",
        resource="CHG-2048",
        details={"token": "never-store-this", "patient_id": "patient-123", "nested": {"password": "also-hidden", "status": "approved"}},
        occurred_at=datetime(2026, 10, 1, 8, tzinfo=timezone.utc),
    )

    assert entry.payload["details"]["token"] == "***REDACTED***"
    assert entry.payload["details"]["patient_id"] == "***REDACTED***"
    assert entry.payload["details"]["nested"]["password"] == "***REDACTED***"
    assert "never-store-this" not in entry.canonical_payload
    assert location.endswith(entry.entry_id)
    assert adapter.entries == [entry]


def test_playbook_is_ordered_and_parameterized():
    payload = PlaybookRequest(
        change_id="CHG-2048",
        system="Veeva Vault",
        environment="production",
        owner="platform-ops",
        planned_start="2026-10-01T09:00:00+00:00",
        planned_end="2026-10-01T10:00:00+00:00",
        implementation_steps=["Deploy {system} update to {environment}"],
        validation_steps=["Verify health checks"],
        backout_steps=["Restore previous release"],
    )

    playbook = PlaybookGenerator().generate(payload)

    assert [item.order for item in playbook.items] == [1, 2, 3, 4, 5]
    assert playbook.items[1].instruction == "Deploy Veeva Vault update to production"
    assert playbook.items[-1].phase == "close"
