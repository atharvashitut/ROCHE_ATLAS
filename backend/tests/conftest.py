import pytest

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
