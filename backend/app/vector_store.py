"""Persistent local vector retrieval for the ATLAS RAG prototype.

Chroma provides a durable local vector database for development.  Gemini
embeddings are used when an API key is available.  A deterministic hashed
embedding remains available for offline demos so API availability never blocks
the ServiceNow workflow; deployment environments should always configure
``GEMINI_API_KEY``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any, Iterable

try:  # Optional at import time so local API smoke tests remain possible.
    import chromadb
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    chromadb = None

try:
    from google import genai
except ImportError:  # pragma: no cover - exercised only before dependencies are installed
    genai = None


VECTOR_DIMENSIONS = 256
DEFAULT_COLLECTION = "atlas_enterprise_knowledge"
DEFAULT_VECTOR_PATH = Path(__file__).resolve().parents[1] / ".atlas-vector-db"


@dataclass(frozen=True)
class RetrievalDocument:
    """A normalized, independently citeable unit of enterprise context."""

    id: str
    title: str
    content: str
    source_type: str
    system: str
    connector: str
    url: str
    record_type: str
    ticket_number: str = ""
    ticket_id: str = ""
    assignment_group: str = ""
    module: str = ""
    section: str = "overview"

    def metadata(self) -> dict[str, str]:
        return {
            "dataset": "atlas",
            "title": self.title,
            "source_type": self.source_type,
            "system": self.system,
            "connector": self.connector,
            "url": self.url,
            "record_type": self.record_type,
            "ticket_number": self.ticket_number,
            "ticket_id": self.ticket_id,
            "assignment_group": self.assignment_group,
            "module": self.module,
            "section": self.section,
        }


@dataclass(frozen=True)
class RetrievedDocument:
    """A vector-search result and its cosine-style relevance score."""

    document: RetrievalDocument
    score: float


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_/-]+", text.casefold())


def _normalise(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    return [value / magnitude for value in vector] if magnitude else vector


def _local_embedding(text: str) -> list[float]:
    """Stable offline lexical vector; not a substitute for Gemini embeddings."""

    vector = [0.0] * VECTOR_DIMENSIONS
    terms = _tokens(text)
    for term in terms + [f"{left}:{right}" for left, right in zip(terms, terms[1:])]:
        digest = hashlib.sha256(term.encode()).digest()
        index = int.from_bytes(digest[:2], "big") % VECTOR_DIMENSIONS
        direction = 1.0 if digest[2] % 2 else -1.0
        vector[index] += direction
    return _normalise(vector)


class GeminiEmbeddingProvider:
    """Gemini embedding provider with an offline-compatible local fallback."""

    def __init__(self) -> None:
        self.model = os.getenv("ATLAS_GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self._api_key = os.getenv("GEMINI_API_KEY")
        try:
            self._client = genai.Client(api_key=self._api_key) if genai and self._api_key else None
        except Exception:  # pragma: no cover - malformed local credentials
            self._client = None

    @property
    def mode(self) -> str:
        return "gemini" if self._client is not None else "local_hash_fallback"

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._client is not None:
            try:
                response = self._client.models.embed_content(model=self.model, contents=texts)
                embeddings = getattr(response, "embeddings", None) or []
                vectors = [list(getattr(embedding, "values", embedding)) for embedding in embeddings]
                if len(vectors) == len(texts) and all(vectors):
                    return [_normalise([float(value) for value in vector]) for vector in vectors]
            except Exception:
                # Retrieval retains deterministic availability; status reports the fallback mode.
                pass
        return [_local_embedding(text) for text in texts]


class LocalVectorStore:
    """Chroma-backed persistent store with a deterministic in-process fallback."""

    def __init__(self, path: Path | None = None, collection_name: str = DEFAULT_COLLECTION) -> None:
        self.path = Path(os.getenv("ATLAS_VECTOR_STORE_PATH", str(path or DEFAULT_VECTOR_PATH)))
        self.collection_name = collection_name
        self.embedder = GeminiEmbeddingProvider()
        self._lock = RLock()
        self._fingerprint = ""
        self._documents: dict[str, RetrievalDocument] = {}
        self._vectors: dict[str, list[float]] = {}
        self._client: Any | None = None
        self._collection: Any | None = None
        self._using_chroma = False

    def _collection_handle(self) -> Any | None:
        if chromadb is None:
            return None
        if self._collection is None:
            self.path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.path))
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @staticmethod
    def _fingerprint_for(documents: Iterable[RetrievalDocument]) -> str:
        material = "\n".join(
            f"{document.id}|{document.content}|{document.url}"
            for document in sorted(documents, key=lambda item: item.id)
        )
        return hashlib.sha256(material.encode()).hexdigest()

    def sync(self, documents: list[RetrievalDocument]) -> None:
        """Upsert the full canonical corpus when its content changes."""

        fingerprint = self._fingerprint_for(documents)
        with self._lock:
            if fingerprint == self._fingerprint:
                return
            vectors = self.embedder.embed([document.content for document in documents])
            self._documents = {document.id: document for document in documents}
            self._vectors = dict(zip(self._documents, vectors, strict=True))
            collection = self._collection_handle()
            if collection is not None:
                try:
                    # Canonical re-sync prevents stale connector documents after a source update.
                    collection.delete(where={"dataset": "atlas"})
                    collection.upsert(
                        ids=[document.id for document in documents],
                        documents=[document.content for document in documents],
                        metadatas=[document.metadata() for document in documents],
                        embeddings=vectors,
                    )
                    self._using_chroma = True
                except Exception:
                    # A local collection may have been created previously
                    # with a different embedding dimension. The corpus is
                    # canonical and fully re-indexable, so recreate safely.
                    try:
                        if self._client is None:
                            raise RuntimeError("Chroma client is unavailable")
                        self._client.delete_collection(self.collection_name)
                        self._collection = self._client.get_or_create_collection(
                            name=self.collection_name,
                            metadata={"hnsw:space": "cosine"},
                        )
                        self._collection.upsert(
                            ids=[document.id for document in documents],
                            documents=[document.content for document in documents],
                            metadatas=[document.metadata() for document in documents],
                            embeddings=vectors,
                        )
                        self._using_chroma = True
                    except Exception:
                        self._using_chroma = False
            self._fingerprint = fingerprint

    def query(self, query_text: str, limit: int = 8) -> list[RetrievedDocument]:
        """Return the highest-relevance canonical chunks for a user query."""

        with self._lock:
            if not self._documents:
                return []
            query_vector = self.embedder.embed([query_text])[0]
            if self._using_chroma and self._collection is not None:
                try:
                    result = self._collection.query(
                        query_embeddings=[query_vector],
                        n_results=min(limit, len(self._documents)),
                        include=["metadatas", "distances"],
                    )
                    ids = result.get("ids", [[]])[0]
                    distances = result.get("distances", [[]])[0]
                    return [
                        RetrievedDocument(self._documents[document_id], max(0.0, 1.0 - float(distance)))
                        for document_id, distance in zip(ids, distances, strict=True)
                        if document_id in self._documents
                    ]
                except Exception:
                    self._using_chroma = False
            scored = [
                RetrievedDocument(document, sum(left * right for left, right in zip(query_vector, self._vectors[document_id], strict=True)))
                for document_id, document in self._documents.items()
            ]
            return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "backend": "chromadb" if self._using_chroma else "in_process_vector_fallback",
                "path": str(self.path),
                "collection": self.collection_name,
                "document_count": len(self._documents),
                "embedding_provider": self.embedder.mode,
                "embedding_model": self.embedder.model if self.embedder.mode == "gemini" else "deterministic-local-hash",
            }


VECTOR_STORE = LocalVectorStore()


def serialize_retrieved(result: RetrievedDocument) -> dict[str, object]:
    """Return API-safe retrieval metadata without exposing embedding values."""

    return {**asdict(result.document), "score": round(result.score, 4)}
