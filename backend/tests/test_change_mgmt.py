from datetime import datetime, timezone

import pytest

from app.models import ChangeRequestPayload
from change_mgmt.cr_builder import ChangeRequestBuilder
from change_mgmt.risk_calendar import MockCMDBCalendarAdapter, RiskCalendarService
from change_mgmt.veeva_rules import ChangeType, VeevaRulesParser


def _payload() -> ChangeRequestPayload:
    return ChangeRequestPayload(
        change_id="CHG-2048",
        title="Update Vault integration timeout",
        description="Increase the Vault integration timeout to prevent login failures.",
        requested_by="platform-ops",
        ci_ids=["CI-VAULT"],
        planned_start="2026-10-01T09:00:00+00:00",
        planned_end="2026-10-01T12:30:00+00:00",
        requested_type="normal",
        implementation_steps=["Update timeout on {system}"],
        test_steps=["Verify login health"],
        backout_steps=["Restore prior timeout"],
    )


def test_veeva_rules_are_traceable(veeva_mock_outputs):
    policy = VeevaRulesParser().policy_for(ChangeType.NORMAL, veeva_mock_outputs)

    assert policy.source_document == "Veeva Doc #501"
    assert policy.source_page == 7
    assert "change_manager" in policy.approver_roles


@pytest.mark.asyncio
async def test_risk_calendar_detects_blackout_and_explains_score(cmdb_cis, blackout_window):
    service = RiskCalendarService(MockCMDBCalendarAdapter(cmdb_cis, [blackout_window]))

    result = await service.assess(
        ["CI-VAULT"],
        datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
        datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc),
        ChangeType.NORMAL,
    )

    assert result.score == 100
    assert result.blackout_conflicts == ("Quarter close",)
    assert any("criticality" in factor for factor in result.factors)


@pytest.mark.asyncio
async def test_cr_builder_populates_required_fields(veeva_mock_outputs, cmdb_cis):
    payload = _payload()
    assessment = await RiskCalendarService(MockCMDBCalendarAdapter(cmdb_cis)).assess(
        payload.ci_ids, payload.planned_start, payload.planned_end, payload.requested_type, True
    )
    policy = VeevaRulesParser().policy_for(ChangeType.NORMAL, veeva_mock_outputs)
    record = ChangeRequestBuilder().build(payload, assessment, policy)

    assert record.classification == ChangeType.NORMAL
    assert record.backout_plan == ["Restore prior timeout"]
    assert record.approver_routing == ["service_owner", "change_manager"]
    assert record.policy_trace["page"] == 7
