"""Asynchronous, process-external Ollama generation adapter for ATLAS.

The web process never loads model weights. Ollama owns model lifecycle and
memory; ATLAS sends bounded, grounded chat requests over local HTTP and keeps
the deterministic RAG synthesizer available when the daemon is unavailable.
"""

from __future__ import annotations

import logging
import os
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


logger = logging.getLogger("uvicorn.error")


class OllamaStreamError(RuntimeError):
    """Raised only after every configured Ollama model stream has failed."""


class OllamaGenerator:
    """Thin async client with model fallback and non-fatal diagnostics."""

    def __init__(self) -> None:
        self.base_url = os.getenv("ATLAS_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.getenv("ATLAS_OLLAMA_MODEL", "llama3.2:3b")
        self.fallback_model = os.getenv("ATLAS_OLLAMA_FALLBACK_MODEL", "llama3:8b")
        # Keep local CPU generation deliberately bounded.  RAG provides a
        # compact context payload, while Ollama receives enough room for a
        # complete but responsive answer.
        self.temperature = float(os.getenv("ATLAS_OLLAMA_TEMPERATURE", "0.2"))
        # Most dashboard and ticket questions need a focused answer. RAG can
        # opt into a larger per-request budget for explicitly complete SOPs.
        self.max_tokens = max(1, int(os.getenv("ATLAS_OLLAMA_MAX_TOKENS", "220")))
        self.context_window = max(256, int(os.getenv("ATLAS_OLLAMA_NUM_CTX", "2048")))
        self.num_threads = max(1, int(os.getenv("ATLAS_OLLAMA_NUM_THREAD", "4")))
        # llama3.2:3b can take longer than a short HTTP window to generate a
        # grounded multi-document answer on a CPU-only development container.
        self.timeout_seconds = float(os.getenv("ATLAS_OLLAMA_TIMEOUT_SECONDS", "90"))
        self.diagnostic_timeout_seconds = float(os.getenv("ATLAS_OLLAMA_DIAGNOSTIC_TIMEOUT_SECONDS", "2"))
        self._state = "unknown"
        self._available_models: list[str] = []
        self._error: str | None = None

    @property
    def model_candidates(self) -> list[str]:
        return list(dict.fromkeys(model for model in (self.model, self.fallback_model) if model))

    async def diagnose(self) -> None:
        """Probe Ollama without delaying startup or crashing ATLAS."""

        try:
            timeout = httpx.Timeout(self.diagnostic_timeout_seconds)
            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                response = await client.get("/api/tags")
                response.raise_for_status()
            payload = response.json()
            self._available_models = [str(item.get("name", "")) for item in payload.get("models", [])]
            configured = next((model for model in self.model_candidates if model in self._available_models), None)
            if configured:
                self._state = "ready"
                self._error = None
                logger.info("ATLAS Ollama reachable: model=%s base_url=%s", configured, self.base_url)
            else:
                self._state = "model_missing"
                self._error = (
                    f"Neither configured Ollama model ({', '.join(self.model_candidates)}) is installed. "
                    f"Available models: {', '.join(self._available_models) or 'none'}"
                )
                logger.warning("ATLAS Ollama diagnostic: %s", self._error)
        except (httpx.HTTPError, ValueError) as error:
            self._state = "unreachable"
            self._error = f"Cannot reach Ollama at {self.base_url}: {type(error).__name__}: {error}"
            logger.warning("ATLAS Ollama diagnostic: %s", self._error)

    async def warm(self) -> None:
        """Load one configured model in the daemon without blocking web startup."""

        if self._state != "ready":
            return
        request_payload_base: dict[str, Any] = {
            "stream": False,
            "keep_alive": "60m",
            "messages": [
                {"role": "system", "content": "You are ready."},
                {"role": "user", "content": "ready"},
            ],
            "options": {
                "temperature": 0,
                "num_predict": 1,
                "num_ctx": self.context_window,
                "num_thread": self.num_threads,
            },
        }
        timeout = httpx.Timeout(connect=10.0, read=self.timeout_seconds, write=30.0, pool=10.0)
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                for model in self.model_candidates:
                    response = await client.post("/api/chat", json={**request_payload_base, "model": model})
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    logger.info("ATLAS Ollama warm-up complete: model=%s", model)
                    return
        except httpx.HTTPError as error:
            # A warm-up is an optimisation only; diagnostics and request
            # fallback behavior remain available if the daemon changes state.
            logger.warning("ATLAS Ollama warm-up skipped: %s", error)

    async def generate(self, *, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> tuple[str | None, str | None]:
        """Return generated text and selected model, or a clean unavailable state."""

        # Startup diagnostics run in the background, but a request can safely
        # try the daemon even before that probe completes.
        request_payload_base: dict[str, Any] = {
            "stream": False,
            "keep_alive": "60m",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens or self.max_tokens,
                "num_ctx": self.context_window,
                "num_thread": self.num_threads,
            },
        }
        errors: list[str] = []
        try:
            timeout = httpx.Timeout(self.timeout_seconds)
            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                for model in self.model_candidates:
                    response = await client.post("/api/chat", json={**request_payload_base, "model": model})
                    if response.status_code == 404:
                        errors.append(f"{model} is not installed")
                        continue
                    response.raise_for_status()
                    content = str(response.json().get("message", {}).get("content", "")).strip()
                    if content:
                        self._state = "ready"
                        self._error = None
                        return content, model
                    errors.append(f"{model} returned an empty response")
        except httpx.HTTPError as error:
            errors.append(f"{type(error).__name__}: {error}")

        self._state = "unreachable" if errors and "Connect" in " ".join(errors) else "unavailable"
        self._error = "; ".join(errors) or "Ollama did not return a response"
        logger.warning("ATLAS Ollama generation unavailable: %s", self._error)
        return None, None

    async def stream_generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield Ollama chat deltas while keeping the selected model resident.

        The HTTP client has a generous *read-gap* timeout rather than waiting
        for a complete response body. Once generation begins, each delta keeps
        both this connection and upstream SSE consumers active.
        """

        request_payload_base: dict[str, Any] = {
            "stream": True,
            "keep_alive": "60m",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens or self.max_tokens,
                "num_ctx": self.context_window,
                "num_thread": self.num_threads,
            },
        }
        errors: list[str] = []
        timeout = httpx.Timeout(connect=10.0, read=self.timeout_seconds, write=30.0, pool=10.0)
        for model in self.model_candidates:
            emitted = False
            try:
                async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                    async with client.stream("POST", "/api/chat", json={**request_payload_base, "model": model}) as response:
                        if response.status_code == 404:
                            errors.append(f"{model} is not installed")
                            continue
                        response.raise_for_status()
                        async for raw_line in response.aiter_lines():
                            if not raw_line.strip():
                                continue
                            try:
                                payload = json.loads(raw_line)
                            except json.JSONDecodeError:
                                continue
                            content = str(payload.get("message", {}).get("content", ""))
                            if content:
                                emitted = True
                                self._state = "ready"
                                self._error = None
                                yield content, model
                            if payload.get("done"):
                                return
                if not emitted:
                    errors.append(f"{model} returned an empty stream")
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{model}: {type(error).__name__}: {error}")

        self._state = "unreachable" if any("Connect" in error for error in errors) else "unavailable"
        self._error = "; ".join(errors) or "Ollama did not return a stream"
        logger.warning("ATLAS Ollama stream unavailable: %s", self._error)
        raise OllamaStreamError(self._error)

    def status(self) -> dict[str, object]:
        return {
            "provider": "Ollama local daemon",
            "base_url": self.base_url,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "num_ctx": self.context_window,
            "num_thread": self.num_threads,
            "state": self._state,
            "available_models": self._available_models,
            "error": self._error,
        }


OLLAMA_GENERATOR = OllamaGenerator()
