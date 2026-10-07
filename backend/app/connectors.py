"""Connector contracts for ATLAS enterprise retrieval sources.

The demo runs with canonical mock records.  Each connector has the same shape
as its future live equivalent so a ServiceNow, Veeva, ALM, or Drive adapter can
be introduced without changing retrieval, citation, or chat code.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
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
    required_environment: tuple[str, ...] = ()

    def read_documents(self) -> Iterable[dict[str, Any]]:
        return [
            document
            for document in central_knowledge_records()
            if document["connector"] == self.name
        ]

    def status(self) -> dict[str, object]:
        documents = list(self.read_documents())
        missing_environment = [name for name in self.required_environment if not os.getenv(name)]
        return {
            "connector": self.name,
            "system": self.system,
            "mode": "canonical_mock",
            "configured": not missing_environment,
            "integration_ready": not missing_environment,
            "required_environment": list(self.required_environment),
            "missing_environment": missing_environment,
            "document_count": len(documents),
            "write_enabled": False,
        }


CONNECTORS: tuple[EnterpriseConnector, ...] = (
    CanonicalMockConnector("ServiceNow", "ServiceNow ITSM", ("SERVICENOW_INSTANCE_URL", "SERVICENOW_CLIENT_ID", "SERVICENOW_CLIENT_SECRET")),
    CanonicalMockConnector("Veeva Vault", "Veeva Vault QMS", ("VEEVA_VAULT_URL", "VEEVA_CLIENT_ID", "VEEVA_CLIENT_SECRET")),
    CanonicalMockConnector("HP ALM", "HP ALM Quality Center", ("HP_ALM_BASE_URL", "HP_ALM_CLIENT_ID", "HP_ALM_CLIENT_SECRET")),
    CanonicalMockConnector("Google Drive", "Google Drive KT Hub", ("GOOGLE_DRIVE_FOLDER_ID", "GOOGLE_APPLICATION_CREDENTIALS")),
)


def connector_documents() -> list[dict[str, Any]]:
    """Return each connector document once, in a stable source order."""

    return [document for connector in CONNECTORS for document in connector.read_documents()]


def connector_statuses() -> list[dict[str, object]]:
    """Expose source-readiness without exposing credentials or source secrets."""

    return [connector.status() for connector in CONNECTORS]
