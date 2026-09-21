import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.models import AuditLogRequest, AuditLogResponse, ChangeRequestPayload, PlaybookRequest
from audit.gdrive_audit import AuditLogger, MockGoogleDriveDocsAdapter
from audit.playbook_gen import PlaybookGenerator
from change_mgmt.cr_builder import ChangeRequestBuilder
from change_mgmt.risk_calendar import MockCMDBCalendarAdapter, RiskCalendarService
from change_mgmt.veeva_rules import VeevaRulesParser
from triage.drafter import DraftType, draft_response
from triage.vision_search import QdrantVectorStore, TerraVisionClient, VisionSearchService

app = FastAPI(title="ITSM Copilot API", version="0.1.0")

_VEEVA_MOCK_OUTPUTS = (
    {"document_id": "Veeva Doc #501", "page": 4, "text": "Low change: service owner approval and documented validation are required."},
    {"document_id": "Veeva Doc #501", "page": 7, "text": "Normal change: change manager approval, test plan, and backout plan are required."},
    {"document_id": "Veeva Doc #501", "page": 11, "text": "Emergency change: emergency change manager authorization must be recorded."},
)
_AUDIT_LOGGER = AuditLogger(MockGoogleDriveDocsAdapter())


class VisionTriageRequest(BaseModel):
    image_base64: str = Field(min_length=1, description="Screenshot encoded in base64")


class VisionTriageResponse(BaseModel):
    document_title: str
    document_reference: str
    confidence: float
    analysis: str
    draft_type: DraftType
    draft: str


def get_vision_service() -> VisionSearchService:
    return VisionSearchService(
        vision_client=TerraVisionClient(
            base_url=os.getenv("TERRA_VISION_BASE_URL", "https://api.terra.example"),
            api_key=os.getenv("TERRA_VISION_API_KEY", ""),
            model=os.getenv("TERRA_VISION_MODEL", "gpt-terra-vision"),
        ),
        vector_store=QdrantVectorStore(
            base_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
            collection=os.getenv("QDRANT_COLLECTION", "knowledge_base"),
        ),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/triage/vision", response_model=VisionTriageResponse)
async def triage_vision(payload: VisionTriageRequest) -> VisionTriageResponse:
    try:
        match = await get_vision_service().search(payload.image_base64)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    draft = draft_response(match)
    return VisionTriageResponse(
        document_title=match.document_title,
        document_reference=match.document_reference,
        confidence=match.confidence,
        analysis=match.analysis,
        draft_type=draft.kind,
        draft=draft.content,
    )


@app.post("/api/v1/changes")
async def create_change(payload: ChangeRequestPayload) -> dict:
    assessment = await RiskCalendarService(MockCMDBCalendarAdapter()).assess(
        ci_ids=payload.ci_ids,
        starts_at=payload.planned_start,
        ends_at=payload.planned_end,
        requested_type=payload.requested_type,
        has_backout_plan=bool(payload.backout_steps),
    )
    builder = ChangeRequestBuilder()
    classification = builder.classify(assessment, payload.requested_type)
    policy = VeevaRulesParser().policy_for(classification, _VEEVA_MOCK_OUTPUTS)
    return builder.build(payload, assessment, policy).as_dict()


@app.post("/api/v1/audit", response_model=AuditLogResponse)
async def create_audit_log(payload: AuditLogRequest) -> AuditLogResponse:
    entry, location = await _AUDIT_LOGGER.record(
        action=payload.action,
        actor=payload.actor,
        resource=payload.resource,
        details=payload.details,
        occurred_at=payload.occurred_at,
    )
    return AuditLogResponse(entry_id=entry.entry_id, recorded_at=entry.recorded_at, location=location, payload=entry.payload)


@app.post("/api/v1/audit/playbook")
async def generate_playbook(payload: PlaybookRequest) -> dict:
    return PlaybookGenerator().generate(payload).as_dict()
