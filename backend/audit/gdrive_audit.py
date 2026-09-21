"""Immutable, redacted audit payloads routed through a Google Drive/Docs adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from core.redaction import redact_payload


@dataclass(frozen=True)
class ImmutableAuditEntry:
    entry_id: str
    recorded_at: str
    payload: dict[str, Any]
    canonical_payload: str


class GoogleDriveDocsAdapter(Protocol):
    async def append_immutable(self, entry: ImmutableAuditEntry) -> str: ...


class MockGoogleDriveDocsAdapter:
    def __init__(self):
        self.entries: list[ImmutableAuditEntry] = []

    async def append_immutable(self, entry: ImmutableAuditEntry) -> str:
        self.entries.append(entry)
        return f"mock-gdrive://itsm-copilot-audit/{entry.entry_id}"


class AuditLogger:
    def __init__(self, adapter: GoogleDriveDocsAdapter):
        self.adapter = adapter

    async def record(self, action: str, actor: str, resource: str, details: dict[str, Any], occurred_at: datetime | None = None) -> tuple[ImmutableAuditEntry, str]:
        timestamp = (occurred_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        payload = {"action": action, "actor": actor, "resource": resource, "details": redact_payload(details)}
        canonical = json.dumps({"recorded_at": timestamp, **payload}, sort_keys=True, separators=(",", ":"), default=str)
        entry = ImmutableAuditEntry(
            entry_id=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            recorded_at=timestamp,
            payload=payload,
            canonical_payload=canonical,
        )
        return entry, await self.adapter.append_immutable(entry)
