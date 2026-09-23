"""OpenAI-grounded retrieval across ATLAS knowledge connectors and ITSM records."""

from __future__ import annotations

import os
import re
from typing import Any

try:  # Keep local demo startup independent from optional hosted AI credentials.
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on the developer environment
    OpenAI = None  # type: ignore[assignment,misc]

from .models import MOCK_DB, Ticket


KNOWLEDGE_CORPUS: list[dict[str, str]] = [
    {
        "id": "KBA003192",
        "title": "SAP EWM qRFC Queue Lock Resolution & SM12 Unlock Procedure",
        "system": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA003192",
        "content": "SAP EWM qRFC queue lock recovery, SM12 unlock procedure, warehouse goods issue and replication validation.",
    },
    {
        "id": "VEEVA-SOP-0042",
        "title": "GxP Standard Operating Procedure for Batch Interface Access Controls",
        "system": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/SOP-0042",
        "content": "GxP compliant batch interface access controls, SAP authorization roles, approval evidence and controlled remediation.",
    },
    {
        "id": "ALM-DEF-8812",
        "title": "Known Defect: SolMan Redundant Alert Suppression in SAP EWM 1010",
        "system": "HP ALM",
        "url": "https://alm.roche.com/qcbin/defect/8812",
        "content": "SolMan monitoring defect, redundant SAP EWM 1010 alert suppression and job-monitoring triage guidance.",
    },
    {
        "id": "GDRIVE-SUD-109",
        "title": "System Understanding Document: SAP MM PO Release Workflow Integration Architecture",
        "system": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-109-ARCH",
        "content": "SAP MM purchase order release workflow, integration architecture, approval routing and diagnostic handover information.",
    },
]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
try:
    client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and OpenAI else None
except Exception:  # pragma: no cover - protects API startup from malformed local config
    client = None


def _tokens(text: str) -> set[str]:
    """Normalize terms and a small set of ITSM/SAP synonyms for broad retrieval."""

    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    expansions = {
        "po": {"purchase", "order", "workflow"},
        "qrfc": {"queue", "replication", "sm12"},
        "authorization": {"access", "role", "su53"},
        "solman": {"monitoring", "alert"},
    }
    for phrase, synonyms in expansions.items():
        if phrase in text.lower() or phrase in tokens:
            tokens.update(synonyms)
    return tokens


def _ticket_context(ticket: Ticket) -> str:
    """Collect searchable ServiceNow fields, including customer and internal journals."""

    comments = " ".join(entry.value for entry in ticket.comments)
    work_notes = " ".join(entry.value for entry in ticket.work_notes)
    return " ".join([
        ticket.number,
        ticket.short_description,
        ticket.description,
        ticket.ai_resolution_guide,
        comments,
        work_notes,
        " ".join(ticket.additional_comments),
    ])


def _searchable_chunks() -> list[dict[str, str]]:
    """Return citation-ready chunks from all enterprise connectors and active records."""

    ticket_chunks = [
        {
            "id": ticket.number,
            "title": ticket.short_description,
            "system": "ServiceNow Ticket",
            "url": f"/api/tickets/{ticket.number}",
            "content": _ticket_context(ticket),
        }
        for ticket in MOCK_DB.values()
    ]
    return [*KNOWLEDGE_CORPUS, *ticket_chunks]


def _score_chunk(query_terms: set[str], chunk: dict[str, str], index: int) -> tuple[int, int]:
    chunk_terms = _tokens(f"{chunk['title']} {chunk['content']}")
    exact_score = len(query_terms & chunk_terms)
    title_score = len(query_terms & _tokens(chunk["title"]))
    return (exact_score + title_score * 2, -index)


def _retrieve_context(query_text: str, limit: int = 4) -> list[dict[str, str]]:
    """Select the best matching cross-platform documents and ticket records."""

    chunks = _searchable_chunks()
    query_terms = _tokens(query_text)
    ranked = sorted(
        ((_score_chunk(query_terms, chunk, index), chunk) for index, chunk in enumerate(chunks)),
        key=lambda item: item[0],
        reverse=True,
    )
    return [chunk for _, chunk in ranked[:limit]]


def _source_payload(chunks: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{key: chunk[key] for key in ("id", "title", "system", "url")} for chunk in chunks]


def _context_prompt(query_text: str, chunks: list[dict[str, str]]) -> str:
    context = "\n\n".join(
        f"[{chunk['id']}] {chunk['title']} | {chunk['system']}\n{chunk['content']}"
        for chunk in chunks
    )
    return f"User question: {query_text}\n\nRetrieved enterprise context:\n{context}"


def _fallback_answer(query_text: str, chunks: list[dict[str, str]]) -> str:
    """Create a useful local synthesis from the same retrieved evidence as OpenAI."""

    ticket_chunks = [chunk for chunk in chunks if chunk["system"] == "ServiceNow Ticket"]
    document_chunks = [chunk for chunk in chunks if chunk["system"] != "ServiceNow Ticket"]
    parts = [f"ATLAS found relevant context for “{query_text.strip()}”."]
    if ticket_chunks:
        parts.append("Active record context: " + "; ".join(
            f"{chunk['id']} — {chunk['title']}" for chunk in ticket_chunks
        ) + ".")
    if document_chunks:
        parts.append("Enterprise guidance: " + "; ".join(
            f"{chunk['id']} — {chunk['title']}" for chunk in document_chunks
        ) + ".")
    parts.append("Validate the current record state and follow the approved remediation or escalation path before making production changes.")
    return " ".join(parts)


def query_chatgpt_rag(query_text: str) -> dict[str, Any]:
    """Retrieve ATLAS context and optionally ask ChatGPT for a grounded synthesis."""

    chunks = _retrieve_context(query_text)
    sources = _source_payload(chunks)
    answer = _fallback_answer(query_text, chunks)
    if client is not None:
        try:
            completion = client.chat.completions.create(
                model="gpt-4o",
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Roche ATLAS ITIL Co-Pilot. Answer the user question based strictly on the "
                            "provided enterprise knowledge docs (ServiceNow, Veeva Vault, HP ALM, Google Drive) "
                            "and active incident records. Always provide structured, grounded answers with citations."
                        ),
                    },
                    {"role": "user", "content": _context_prompt(query_text, chunks)},
                ],
            )
            generated_answer = completion.choices[0].message.content
            if generated_answer:
                answer = generated_answer
                sources.append({
                    "id": "CHATGPT-GROUNDED",
                    "title": "ChatGPT grounded synthesis",
                    "system": "ChatGPT Grounded",
                    "url": "https://platform.openai.com/",
                })
        except Exception:
            # Preserve an evidence-based local answer if the configured service is unavailable.
            pass

    return {"answer": answer, "sources": sources, "model_used": "gpt-4o"}
