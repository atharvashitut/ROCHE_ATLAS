"""Screenshot-driven knowledge retrieval using Terra Vision and Qdrant.

The HTTP clients are deliberately small and injectable.  This keeps provider credentials
at the boundary and allows the triage logic to be exercised with deterministic fixtures.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class VisionAnalysis:
    summary: str
    embedding: list[float]


@dataclass(frozen=True)
class KnowledgeMatch:
    document_id: str
    document_title: str
    document_reference: str
    confidence: float
    analysis: str


class VisionClient(Protocol):
    async def analyse(self, image_base64: str) -> VisionAnalysis: ...


class VectorStore(Protocol):
    async def search(self, embedding: list[float], limit: int = 1) -> list[dict[str, Any]]: ...


class TerraVisionClient:
    """Adapter for an OpenAI-compatible GPT-Terra Vision deployment."""

    def __init__(self, base_url: str, api_key: str, model: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = client

    async def analyse(self, image_base64: str) -> VisionAnalysis:
        _validate_base64_image(image_base64)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Summarize the error, product, and useful troubleshooting terms in this screenshot."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
            ]}],
        }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=30)
        try:
            response = await client.post(f"{self.base_url}/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            summary = response.json()["choices"][0]["message"]["content"]
            embedding_response = await client.post(
                f"{self.base_url}/v1/embeddings",
                headers=headers,
                json={"model": self.model, "input": summary},
            )
            embedding_response.raise_for_status()
            embedding = embedding_response.json()["data"][0]["embedding"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Terra Vision API could not analyse the screenshot") from exc
        finally:
            if owns_client:
                await client.aclose()
        return VisionAnalysis(summary=str(summary), embedding=[float(value) for value in embedding])


class QdrantVectorStore:
    """Minimal Qdrant REST adapter for the knowledge-base collection."""

    def __init__(self, base_url: str, collection: str, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.client = client

    async def search(self, embedding: list[float], limit: int = 1) -> list[dict[str, Any]]:
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.post(
                f"{self.base_url}/collections/{self.collection}/points/search",
                json={"vector": embedding, "limit": limit, "with_payload": True},
            )
            response.raise_for_status()
            return response.json().get("result", [])
        except httpx.HTTPError as exc:
            raise RuntimeError("Knowledge vector database search failed") from exc
        finally:
            if owns_client:
                await client.aclose()


class VisionSearchService:
    def __init__(self, vision_client: VisionClient, vector_store: VectorStore):
        self.vision_client = vision_client
        self.vector_store = vector_store

    async def search(self, image_base64: str) -> KnowledgeMatch:
        _validate_base64_image(image_base64)
        analysis = await self.vision_client.analyse(image_base64)
        hits = await self.vector_store.search(analysis.embedding)
        if not hits:
            return KnowledgeMatch(
                document_id="UNMATCHED",
                document_title="No matching knowledge document",
                document_reference="Knowledge base: no match",
                confidence=0.0,
                analysis=analysis.summary,
            )
        hit = hits[0]
        payload = hit.get("payload", {})
        document_id = str(payload.get("document_id", hit.get("id", "UNKNOWN")))
        title = str(payload.get("title", "Untitled knowledge document"))
        reference = str(payload.get("reference", f"Veeva Doc #{document_id}"))
        return KnowledgeMatch(
            document_id=document_id,
            document_title=title,
            document_reference=reference,
            confidence=float(hit.get("score", 0.0)),
            analysis=analysis.summary,
        )


def _validate_base64_image(image_base64: str) -> None:
    try:
        if not base64.b64decode(image_base64, validate=True):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError("image_base64 must be a non-empty, valid base64 image") from exc
