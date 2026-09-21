"""Consistent, privacy-safe API error envelopes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.redaction import redact_payload

logger = logging.getLogger(__name__)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return _response(request, exc.status_code, "request_error", "The request could not be completed.", redact_payload(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _response(request, 422, "validation_error", "The request payload is invalid.", redact_payload(exc.errors()))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error request_id=%s", getattr(request.state, "request_id", "unknown"), exc_info=exc)
        return _response(request, 500, "internal_error", "An unexpected server error occurred.")


def _response(request: Request, status_code: int, code: str, message: str, details: Any | None = None) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", "unknown")}}
    if details is not None:
        payload["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=payload)
