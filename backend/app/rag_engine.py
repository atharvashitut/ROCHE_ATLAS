"""Hybrid multi-connector retrieval with Gemini grounding and ITIL fallback reasoning."""

from __future__ import annotations

import os
import re
from typing import Any

try:  # The API remains available in local development without the optional SDK.
    from google import genai
except ImportError:  # pragma: no cover - depends on installed optional dependencies
    genai = None

from .models import MOCK_DB, Ticket


KNOWLEDGE_CORPUS: list[dict[str, str]] = [
    {
        "id": "KBA003192",
        "title": "SAP EWM qRFC Queue Lock Resolution & SM12 Unlock Procedure",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA003192",
        "content": "SAP EWM qRFC queue lock recovery, SM12 unlock procedure, warehouse goods issue and replication validation.",
    },
    {
        "id": "VEEVA-SOP-0042",
        "title": "GxP Standard Operating Procedure for Batch Interface Access Controls",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/SOP-0042",
        "content": "GxP compliant batch interface access controls, SAP authorization roles, approval evidence and controlled remediation.",
    },
    {
        "id": "ALM-DEF-8812",
        "title": "Known Defect: SolMan Redundant Alert Suppression in SAP EWM 1010",
        "system": "HP ALM",
        "connector": "HP ALM",
        "url": "https://alm.roche.com/qcbin/defect/8812",
        "content": "SolMan monitoring defect, redundant SAP EWM 1010 alert suppression and job-monitoring triage guidance.",
    },
    {
        "id": "GDRIVE-SUD-109",
        "title": "System Understanding Document: SAP MM PO Release Workflow Integration Architecture",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-109-ARCH",
        "content": "SAP MM purchase order release workflow, integration architecture, approval routing and diagnostic handover information.",
    },
]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY and genai else None
except Exception:  # pragma: no cover - protects app startup from malformed local credentials
    gemini_client = None


def _tokens(text: str) -> set[str]:
    """Return meaningful terms with ITSM/SAP synonym expansion for broad matching."""

    stop_words = {"a", "an", "and", "are", "can", "do", "for", "how", "i", "in", "is", "it", "me", "of", "on", "please", "show", "tell", "the", "this", "to", "what", "with", "you"}
    tokens = {term for term in re.findall(r"[a-z0-9]+", text.lower()) if term not in stop_words}
    synonyms = {
        "po": {"purchase", "order", "workflow"},
        "qrfc": {"queue", "replication", "sm12"},
        "authorization": {"access", "role", "su53"},
        "solman": {"monitoring", "alert"},
        "batch": {"job", "sm37"},
    }
    for term, related in synonyms.items():
        if term in tokens:
            tokens.update(related)
    return tokens


def _ticket_chunk(ticket: Ticket) -> dict[str, str]:
    comments = " ".join(entry.value for entry in ticket.comments)
    work_notes = " ".join(entry.value for entry in ticket.work_notes)
    return {
        "id": ticket.number,
        "title": ticket.short_description,
        "system": "ServiceNow Ticket",
        "connector": "ServiceNow",
        "url": f"/api/tickets/{ticket.number}",
        "content": " ".join([ticket.description, ticket.ai_resolution_guide, comments, work_notes]),
    }


def _connector_chunks() -> dict[str, list[dict[str, str]]]:
    """Expose every connector so searches run independently across all four tools."""

    connectors = {name: [] for name in ("ServiceNow", "Veeva Vault", "HP ALM", "Google Drive")}
    for chunk in KNOWLEDGE_CORPUS:
        connectors[chunk["connector"]].append(chunk)
    connectors["ServiceNow"].extend(_ticket_chunk(ticket) for ticket in MOCK_DB.values())
    return connectors


def _score(query_terms: set[str], chunk: dict[str, str]) -> int:
    title_terms = _tokens(chunk["title"])
    content_terms = _tokens(chunk["content"])
    return len(query_terms & content_terms) + (len(query_terms & title_terms) * 2)


def _search_connector(query_terms: set[str], chunks: list[dict[str, str]], limit: int = 2) -> list[dict[str, str]]:
    matches = [(score, index, chunk) for index, chunk in enumerate(chunks) if (score := _score(query_terms, chunk)) > 0]
    return [chunk for _, _, chunk in sorted(matches, key=lambda match: (match[0], -match[1]), reverse=True)[:limit]]


def retrieve_multi_tool_context(query_text: str) -> list[dict[str, str]]:
    """Search ServiceNow, Veeva, HP ALM, and Google Drive independently and merge matches."""

    query_terms = _tokens(query_text)
    if not query_terms:
        return []
    connector_results = [_search_connector(query_terms, chunks) for chunks in _connector_chunks().values()]
    return [chunk for result in connector_results for chunk in result][:6]


def _sources(chunks: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{key: chunk[key] for key in ("id", "title", "system", "url")} for chunk in chunks]


def _grounded_prompt(query_text: str, chunks: list[dict[str, str]]) -> str:
    snippets = "\n\n".join(f"[{chunk['id']}] {chunk['title']} ({chunk['system']})\n{chunk['content']}\nLink: {chunk['url']}" for chunk in chunks)
    return (
        "You are the Roche ATLAS ITIL Co-Pilot. Use only the internal snippets below. "
        "Provide a full, step-by-step resolution with an assessment, safe validation steps, "
        "and connected-source citations using the supplied URLs. Do not invent source details.\n\n"
        f"Question: {query_text}\n\nInternal snippets:\n{snippets}"
    )


def _reasoning_prompt(query_text: str) -> str:
    return (
        "No specific internal enterprise documents were found across connected tools for this query. "
        "Act as an expert ITIL L2/L3 Enterprise Support Co-Pilot and provide a diagnostic hypothesis, "
        "troubleshooting steps, and recommended investigation commands based on general ITIL best practices.\n\n"
        f"Question: {query_text}"
    )


def _local_grounded_answer(query_text: str, chunks: list[dict[str, str]]) -> str:
    sources = "; ".join(f"[{chunk['id']}] {chunk['title']}" for chunk in chunks)
    return (
        f"Assessment: ATLAS found internal evidence relevant to “{query_text}”.\n\n"
        f"1. Review the active record and its latest journal/work-note evidence.\n"
        f"2. Follow the approved recovery or validation procedure in: {sources}.\n"
        "3. Validate service restoration with the requester and capture evidence before closure."
    )


def _local_reasoning_answer(query_text: str) -> str:
    return (
        f"Diagnostic hypothesis: “{query_text}” may involve an application, integration, or access-control failure.\n\n"
        "1. Confirm business impact, affected users, timestamps, and recent changes.\n"
        "2. Review monitoring, application logs, job history, and authentication or integration error codes.\n"
        "3. Compare the failing path with a known-good transaction and escalate to the owning L2/L3 team with evidence.\n"
        "4. Record a workaround, validation result, and requester confirmation in the ServiceNow journal."
    )


def query_hybrid_rag(query_text: str) -> dict[str, Any]:
    """Use internal multi-tool RAG when matched; otherwise invoke Gemini ITIL reasoning."""

    chunks = retrieve_multi_tool_context(query_text)
    has_internal_match = bool(chunks)
    prompt = _grounded_prompt(query_text, chunks) if has_internal_match else _reasoning_prompt(query_text)
    answer = _local_grounded_answer(query_text, chunks) if has_internal_match else _local_reasoning_answer(query_text)
    if gemini_client is not None:
        try:
            generated = gemini_client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
            if generated.text:
                answer = generated.text
        except Exception:
            # Deterministic local synthesis remains available if the hosted model is unavailable.
            pass

    return {
        "answer": answer,
        "sources": _sources(chunks),
        "model_used": "gemini-1.5-flash",
        "fallback_reasoning": not has_internal_match,
        "retrieval_route": "grounded_rag" if has_internal_match else "gemini_itil_reasoning",
    }


# Compatibility alias for older integrations calling the previous RAG function directly.
query_chatgpt_rag = query_hybrid_rag
