import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from triage.drafter import DraftType, draft_response
from triage.vision_search import QdrantVectorStore, TerraVisionClient, VisionSearchService

app = FastAPI(title="ITSM Copilot API", version="0.1.0")


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
