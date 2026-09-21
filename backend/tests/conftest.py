import pytest

from change_mgmt.risk_calendar import BlackoutWindow, ConfigurationItem
from triage.servicenow_relational import ServiceNowTicket
from triage.vision_search import VisionAnalysis


class StubVisionClient:
    async def analyse(self, image_base64: str) -> VisionAnalysis:
        return VisionAnalysis(summary="Veeva Vault login timeout displayed", embedding=[0.12, 0.34])


class StubVectorStore:
    def __init__(self, hits):
        self.hits = hits
        self.last_embedding = None

    async def search(self, embedding, limit=1):
        self.last_embedding = embedding
        return self.hits[:limit]


@pytest.fixture
def base64_image() -> str:
    return "aGVsbG8="


@pytest.fixture
def vector_hit() -> dict:
    return {
        "id": "445",
        "score": 0.91,
        "payload": {"document_id": "445", "title": "Resolve Veeva Vault Login Timeouts"},
    }


@pytest.fixture
def servicenow_tickets() -> list[ServiceNowTicket]:
    return [
        ServiceNowTicket("parent-1", "INC0010001", "Veeva Vault login timeout", "In Progress", problem_id="prb-7"),
        ServiceNowTicket("child-1", "INC0010002", "Veeva Vault login timeout for EU user", "New", parent="parent-1"),
        ServiceNowTicket("other-1", "INC0010003", "Salesforce browser issue", "Closed"),
    ]


@pytest.fixture
def veeva_mock_outputs() -> list[dict]:
    return [
        {"document_id": "Veeva Doc #501", "page": 4, "text": "LOW change requires a service owner."},
        {"document_id": "Veeva Doc #501", "page": 7, "text": "NORMAL change requires a change manager."},
        {"document_id": "Veeva Doc #501", "page": 11, "text": "EMERGENCY change requires emergency authorization."},
    ]


@pytest.fixture
def cmdb_cis() -> list[ConfigurationItem]:
    return [ConfigurationItem("CI-VAULT", "critical", "platform-ops")]


@pytest.fixture
def blackout_window() -> BlackoutWindow:
    from datetime import datetime, timezone

    return BlackoutWindow("Quarter close", datetime(2026, 10, 1, 8, tzinfo=timezone.utc), datetime(2026, 10, 1, 12, tzinfo=timezone.utc), ("CI-VAULT",))
