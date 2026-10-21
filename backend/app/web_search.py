"""No-key DuckDuckGo web snippets for the ATLAS PoC.

Web results are supplementary evidence only. Ticket-specific questions and
credential-like text remain internal and are never submitted to a search
provider.
"""

from __future__ import annotations

import asyncio
import os
import re
import warnings
from typing import Any
from urllib.parse import urlparse

try:
    from duckduckgo_search import DDGS
except ImportError:  # pragma: no cover - handled as a safe unavailable state
    DDGS = None


_TICKET_REFERENCE = re.compile(r"\b(?:inc|ritm|prb|chg)\d{4,}\b", re.IGNORECASE)
_SENSITIVE_TERMS = re.compile(
    r"\b(?:password|passcode|secret|api[ _-]?key|access[ _-]?token|bearer|client[ _-]?secret|private[ _-]?key)\b",
    re.IGNORECASE,
)
_EMAIL_ADDRESS = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SAP_TOPIC = re.compile(
    r"\b(?:sap|s/4hana|s4hana|ewm|basis|abap|fiori|idoc|q[ -]?rfc|rfc|sm\d+|st\d+|su\d+|/scwm/)\b",
    re.IGNORECASE,
)


def _enabled() -> bool:
    return os.getenv("ATLAS_WEB_SEARCH_ENABLED", "true").strip().casefold() in {"1", "true", "yes", "on"}


def sanitize_web_query(query_text: str) -> tuple[str | None, str | None]:
    """Permit only de-identified, non-ticket web research queries."""

    if _SENSITIVE_TERMS.search(query_text):
        return None, "Web research is skipped because the question appears to contain a credential or secret."
    if _TICKET_REFERENCE.search(query_text):
        return None, "Web research is skipped for ticket-specific questions; canonical ticket data remains internal."
    if not _SAP_TOPIC.search(query_text):
        return None, "Web research is limited to SAP topics and SAP-owned sources."
    query = _EMAIL_ADDRESS.sub("[redacted-email]", query_text)
    query = re.sub(r"\b\d{7,}\b", "[redacted-id]", query)
    query = " ".join(query.split())[:800]
    return (query or None), None


def _is_sap_source(url: str) -> bool:
    """Accept SAP-owned links or a URL explicitly labelled with SAP."""

    host = (urlparse(url).hostname or "").casefold().rstrip(".")
    return host == "sap.com" or host.endswith(".sap.com") or "sap" in url.casefold()


class DuckDuckGoWebSearch:
    """Bounded, backend-only search adapter with source URLs for citation."""

    def __init__(self) -> None:
        self.max_results = min(8, max(1, int(os.getenv("ATLAS_WEB_SEARCH_MAX_RESULTS", "5"))))

    def status(self) -> dict[str, object]:
        return {
            "enabled": _enabled(),
            "provider": "DuckDuckGo Search",
            "library_available": DDGS is not None,
            "max_results": self.max_results,
            "source_scope": "SAP-owned domains (*.sap.com) or URLs containing 'sap'",
            "data_policy": "sanitized_query_only; ticket IDs, credential-like text, emails, and long identifiers are excluded",
        }

    async def search(self, query_text: str) -> dict[str, object]:
        if not _enabled():
            return {"chunks": [], "status": "disabled", "warning": None}
        if DDGS is None:
            return {"chunks": [], "status": "unavailable", "warning": "duckduckgo-search is not installed."}
        query, warning = sanitize_web_query(query_text)
        if not query:
            return {"chunks": [], "status": "skipped", "warning": warning}
        try:
            results = await asyncio.to_thread(self._search_sync, query)
        except Exception as error:  # Search must never break internal RAG.
            return {"chunks": [], "status": "unavailable", "warning": f"Web research unavailable: {type(error).__name__}."}

        chunks: list[dict[str, object]] = []
        seen_urls: set[str] = set()
        for index, result in enumerate(results, start=1):
            url = str(result.get("href") or result.get("url") or "").strip()
            if not url or not _is_sap_source(url) or url in seen_urls:
                continue
            seen_urls.add(url)
            title = str(result.get("title") or "DuckDuckGo web result").strip()
            snippet = str(result.get("body") or result.get("snippet") or "").strip()
            if not snippet:
                continue
            chunks.append({
                "id": f"web:{index}:{url}",
                "title": title,
                "content": snippet,
                "source_type": "DuckDuckGo Web",
                "system": "DuckDuckGo Search",
                "connector": "DuckDuckGo Search",
                "url": url,
                "record_type": "web_knowledge",
                "ticket_number": "",
                "ticket_id": "",
                "assignment_group": "Web research",
                "module": "Web research",
                "section": "web_search",
                "score": 1.0,
            })
            if len(chunks) >= self.max_results:
                break
        return {
            "chunks": chunks,
            "status": "ready" if chunks else "unavailable",
            "warning": None if chunks else "DuckDuckGo returned no usable cited results.",
        }

    def _search_sync(self, query: str) -> list[dict[str, Any]]:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r"This package \(`duckduckgo_search`\) has been renamed.*")
            with DDGS() as search:
                return list(search.text(query, max_results=self.max_results))


WEB_SEARCH = DuckDuckGoWebSearch()
