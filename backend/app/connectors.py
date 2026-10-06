"""Connector contracts for ATLAS enterprise retrieval sources.

The demo runs with canonical mock records.  Each connector has the same shape
as its future live equivalent so a ServiceNow, Veeva, ALM, or Drive adapter can
be introduced without changing retrieval, citation, or chat code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from .central_db import central_knowledge_records


class EnterpriseConnector(Protocol):
    """A read-only source connector that emits normalized retrieval records."""

    name: str
    system: str

    def read_documents(self) -> Iterable[dict[str, Any]]: ...

    def status(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class CanonicalMockConnector:
    """Read canonical mock data through a production-compatible connector API."""

    name: str
    system: str

    def read_documents(self) -> Iterable[dict[str, Any]]:
        return [
            document
            for document in central_knowledge_records()
            if document["connector"] == self.name
        ]

    def status(self) -> dict[str, object]:
        documents = list(self.read_documents())
        return {
            "connector": self.name,
            "system": self.system,
            "mode": "canonical_mock",
            "configured": True,
            "document_count": len(documents),
            "write_enabled": False,
        }


CONNECTORS: tuple[EnterpriseConnector, ...] = (
    CanonicalMockConnector("ServiceNow", "ServiceNow ITSM"),
    CanonicalMockConnector("Veeva Vault", "Veeva Vault QMS"),
    CanonicalMockConnector("HP ALM", "HP ALM Quality Center"),
    CanonicalMockConnector("Google Drive", "Google Drive KT Hub"),
)


def connector_documents() -> list[dict[str, Any]]:
    """Return each connector document once, in a stable source order."""

    return [document for connector in CONNECTORS for document in connector.read_documents()]


def connector_statuses() -> list[dict[str, object]]:
    """Expose source-readiness without exposing credentials or source secrets."""

    return [connector.status() for connector in CONNECTORS]
