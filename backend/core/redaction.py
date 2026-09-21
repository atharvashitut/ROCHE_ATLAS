"""Global PII/PHI redaction for API ingress, egress, and structured logging."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

_SENSITIVE_KEY_MARKERS = (
    "password", "token", "secret", "api_key", "authorization", "cookie",
    "patient", "phi", "mrn", "medical_record", "date_of_birth", "dob", "ssn", "email", "phone",
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_MAX_JSON_BYTES = 1_000_000


def redact_payload(value: Any) -> Any:
    """Copy a value while replacing sensitive fields and embedded PII patterns."""
    if isinstance(value, dict):
        return {key: "***REDACTED***" if _is_sensitive_key(str(key)) else redact_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(item) for item in value)
    if isinstance(value, str):
        return _SSN.sub("***REDACTED:SSN***", _EMAIL.sub("***REDACTED:EMAIL***", value))
    return value


def _is_sensitive_key(key: str) -> bool:
    normalised = key.lower().replace("-", "_")
    return any(marker in normalised for marker in _SENSITIVE_KEY_MARKERS)


class RedactionMiddleware(BaseHTTPMiddleware):
    """Retains only a redacted request copy and sanitizes JSON before response egress."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.redacted_payload = await self._redacted_request_payload(request)
        response = await call_next(request)
        sanitized_response = await self._sanitize_json_response(response)
        sanitized_response.headers["X-Request-ID"] = request.state.request_id
        return sanitized_response

    async def _redacted_request_payload(self, request: Request) -> Any | None:
        if "application/json" not in request.headers.get("content-type", ""):
            return None
        body = await request.body()
        if not body or len(body) > _MAX_JSON_BYTES:
            return None
        try:
            return redact_payload(json.loads(body))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    async def _sanitize_json_response(self, response: Response) -> Response:
        if "application/json" not in response.headers.get("content-type", ""):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        if not body or len(body) > _MAX_JSON_BYTES:
            return self._replacement_response(response, body)
        try:
            body = json.dumps(redact_payload(json.loads(body)), separators=(",", ":")).encode("utf-8")
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        return self._replacement_response(response, body)

    @staticmethod
    def _replacement_response(response: Response, body: bytes) -> Response:
        headers = {key: value for key, value in response.headers.items() if key.lower() not in {"content-length", "content-type"}}
        return Response(content=body, status_code=response.status_code, headers=headers, media_type="application/json", background=response.background)
