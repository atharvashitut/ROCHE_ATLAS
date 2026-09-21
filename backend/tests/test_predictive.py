import pytest

from predictive.drift_detector import DriftDetector
from predictive.problem_builder import ProblemRecordBuilder
from predictive.rca_engine import LogTrace, MockLLMContextAdapter, RootCauseEngine, TicketHistory


@pytest.mark.asyncio
async def test_rca_links_logs_and_incident_history():
    result = await RootCauseEngine(MockLLMContextAdapter()).analyse(
        [LogTrace("trace-42", "Gateway timeout while authenticating Vault user")],
        [TicketHistory("INC0010042", "Vault login timeout seen in production", "high")],
    )

    assert result.probable_causes[0].confidence == pytest.approx(0.84)
    assert result.probable_causes[0].cause.startswith("Upstream service timeout")
    assert [link.href for link in result.evidence_links] == ["log://traces/trace-42", "servicenow://incidents/INC0010042"]


def test_problem_builder_creates_prb_for_recurrence():
    decision = ProblemRecordBuilder(recurrence_threshold=3).build(
        "Veeva Vault", "Recurring authentication timeouts", ["INC0010042", "INC0010043", "INC0010044"], 3, False
    )

    assert decision.should_create is True
    assert decision.record is not None
    assert decision.record.number.startswith("PRB")
    assert decision.record.priority == "P2"


def test_problem_builder_skips_isolated_low_impact_incident():
    decision = ProblemRecordBuilder().build("Veeva Vault", "Single timeout", ["INC0010042"], 1, False)

    assert decision.should_create is False
    assert decision.record is None


def test_drift_detector_flags_baseline_differences():
    report = DriftDetector().detect(
        "CI-VAULT",
        {"validation_state": "draft", "timeout_seconds": 60, "debug_mode": True},
        {"validation_state": "approved", "timeout_seconds": 30},
    )

    assert report.compliant is False
    assert report.drift_score == 68
    assert {finding.field for finding in report.findings} == {"validation_state", "timeout_seconds", "debug_mode"}
