import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.models import (
    AuditLogRequest,
    AuditLogResponse,
    ChangeRequestPayload,
    DriftRequest,
    PlaybookRequest,
    ProblemRequest,
    RCARequest,
)
from audit.gdrive_audit import AuditLogger, MockGoogleDriveDocsAdapter
from audit.playbook_gen import PlaybookGenerator
from change_mgmt.cr_builder import ChangeRequestBuilder
from change_mgmt.risk_calendar import BlackoutWindow, ConfigurationItem, MockCMDBCalendarAdapter, RiskCalendarService
from change_mgmt.veeva_rules import VeevaRulesParser
from triage.drafter import DraftType, draft_response
from triage.servicenow_relational import InMemoryServiceNowAdapter, ServiceNowRelationshipService, ServiceNowTicket
from triage.vision_search import MockQdrantVectorStore, MockTerraVisionClient, QdrantVectorStore, TerraVisionClient, VisionSearchService
from predictive.drift_detector import DriftDetector
from predictive.problem_builder import ProblemRecordBuilder
from predictive.rca_engine import LogTrace, MockLLMContextAdapter, RootCauseEngine, TicketHistory
from core.errors import install_exception_handlers
from core.health import router as health_router
from core.redaction import RedactionMiddleware

app = FastAPI(title="ITSM Copilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RedactionMiddleware)
install_exception_handlers(app)
app.include_router(health_router)

_VEEVA_MOCK_OUTPUTS = (
    {"document_id": "Veeva Doc #501", "page": 4, "text": "Low change: service owner approval and documented validation are required."},
    {"document_id": "Veeva Doc #501", "page": 7, "text": "Normal change: change manager approval, test plan, and backout plan are required."},
    {"document_id": "Veeva Doc #501", "page": 11, "text": "Emergency change: emergency change manager authorization must be recorded."},
)
_AUDIT_ADAPTER = MockGoogleDriveDocsAdapter()
_AUDIT_LOGGER = AuditLogger(_AUDIT_ADAPTER)
_CHANGE_RISK_ADAPTER = MockCMDBCalendarAdapter(
    cis=[ConfigurationItem("CI-VAULT", "critical", "platform-ops")],
    blackouts=[BlackoutWindow("Quarter close", datetime(2026, 10, 1, 8, tzinfo=timezone.utc), datetime(2026, 10, 1, 12, tzinfo=timezone.utc), ("CI-VAULT",))],
)
_INCIDENT_STORE = InMemoryServiceNowAdapter(
    [
        ServiceNowTicket("parent-1", "INC0010001", "Veeva Vault login timeout", "In Progress", problem_id="prb-7"),
        ServiceNowTicket("child-1", "INC0010002", "Veeva Vault login timeout for EU user", "New", parent="parent-1"),
    ],
    problems={"prb-7": {"number": "PRB0000007", "short_description": "Vault authentication latency"}},
)


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
    if os.getenv("COPILOT_ADAPTER_MODE", "mock").lower() == "mock":
        return VisionSearchService(vision_client=MockTerraVisionClient(), vector_store=MockQdrantVectorStore())
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


@app.get("/api/v1/triage/incidents/{ticket_id}/relationships")
async def incident_relationships(ticket_id: str) -> dict:
    try:
        result = await ServiceNowRelationshipService(_INCIDENT_STORE).traverse_relationships(ticket_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ticket = result["ticket"]
    parent = result["parent"]
    return {
        "ticket": {"sys_id": ticket.sys_id, "number": ticket.number, "short_description": ticket.short_description, "state": ticket.state},
        "parent": {"sys_id": parent.sys_id, "number": parent.number, "short_description": parent.short_description} if parent else None,
        "children": [{"sys_id": child.sys_id, "number": child.number, "short_description": child.short_description, "state": child.state} for child in result["children"]],
        "problem": result["problem"],
    }


@app.post("/api/v1/changes")
async def create_change(payload: ChangeRequestPayload) -> dict:
    assessment = await RiskCalendarService(_CHANGE_RISK_ADAPTER).assess(
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


@app.get("/api/v1/audit", response_model=list[AuditLogResponse])
async def list_audit_logs() -> list[AuditLogResponse]:
    return [
        AuditLogResponse(entry_id=entry.entry_id, recorded_at=entry.recorded_at, location=f"mock-gdrive://itsm-copilot-audit/{entry.entry_id}", payload=entry.payload)
        for entry in reversed(_AUDIT_ADAPTER.entries)
    ]


@app.post("/api/v1/audit/playbook")
async def generate_playbook(payload: PlaybookRequest) -> dict:
    return PlaybookGenerator().generate(payload).as_dict()


@app.post("/api/v1/predictive/rca")
async def predictive_rca(payload: RCARequest) -> dict:
    try:
        analysis = await RootCauseEngine(MockLLMContextAdapter()).analyse(
            [LogTrace(trace.trace_id, trace.content) for trace in payload.logs],
            [TicketHistory(ticket.number, ticket.summary, ticket.impact) for ticket in payload.tickets],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return analysis.as_dict()


@app.post("/api/v1/predictive/problem")
async def predictive_problem(payload: ProblemRequest) -> dict:
    return ProblemRecordBuilder().build(
        service=payload.service,
        summary=payload.summary,
        incident_numbers=payload.incident_numbers,
        recurrence_count=payload.recurrence_count,
        high_impact_outage=payload.high_impact_outage,
    ).as_dict()


@app.post("/api/v1/predictive/drift")
async def predictive_drift(payload: DriftRequest) -> dict:
    return DriftDetector().detect(payload.ci_id, payload.snapshot, payload.baseline).as_dict()
