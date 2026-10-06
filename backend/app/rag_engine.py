"""Hybrid Gemini RAG over the canonical ATLAS enterprise corpus.

Retrieval uses a persistent local Chroma collection and Gemini embeddings when
credentials are configured. Ticket state, journal streams, work notes, task
evidence, and four connector sources are indexed as independent chunks.
"""

from __future__ import annotations

import os
import re
from typing import Any

try:
    from google import genai
except ImportError:  # pragma: no cover - optional until requirements are installed
    genai = None

from .central_db import central_ticket_records
from .connectors import connector_documents, connector_statuses
from .vector_store import RetrievedDocument, RetrievalDocument, VECTOR_STORE, serialize_retrieved


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GENERATION_MODEL = os.getenv("ATLAS_GEMINI_GENERATION_MODEL", "gemini-1.5-flash")
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY and genai else None
except Exception:  # pragma: no cover - preserve local availability on malformed credentials
    gemini_client = None


def _journal_text(entries: list[Any]) -> str:
    return " ".join(entry.value if hasattr(entry, "value") else str(entry.get("value", entry)) for entry in entries)


def _task_text(tasks: list[dict[str, object]]) -> str:
    return " ".join(" ".join(str(task.get(field, "")) for field in ("number", "short_description", "title", "state", "close_notes")) for task in tasks)


def build_retrieval_documents() -> list[RetrievalDocument]:
    """Create stable, source-specific chunks from the canonical data stores."""

    documents: list[RetrievalDocument] = []
    for source in connector_documents():
        documents.append(RetrievalDocument(
            id=f"source:{source['id']}", title=source["title"],
            content=f"{source['summary']}\n{source['content']}\nTags: {' '.join(source['tags'])}",
            source_type=source["source_type"], system=source["system"], connector=source["connector"],
            url=source["url"], record_type="knowledge", ticket_number=",".join(source["ticket_numbers"]),
            ticket_id=",".join(source["ticket_numbers"]), assignment_group="Enterprise Knowledge", module="Enterprise Knowledge", section="knowledge_article",
        ))
    for ticket in central_ticket_records().values():
        number = ticket.number
        ticket_url = f"/api/tickets/{number}"
        module = ", ".join(ticket.sap_modules)
        documents.append(RetrievalDocument(
            id=f"ticket:{number}:overview", title=f"{number} — {ticket.short_description}",
            content="\n".join(filter(None, [ticket.short_description, ticket.description, f"State: {ticket.state}. Priority: {ticket.priority}. Assignment group: {ticket.assignment_group}. Assigned to: {ticket.assigned_to}.", ticket.ai_resolution_guide])),
            source_type="ServiceNow Ticket", system="ServiceNow", connector="ServiceNow", url=ticket_url,
            record_type=ticket.type, ticket_number=number, ticket_id=ticket.id, assignment_group=ticket.assignment_group, module=module, section="ticket_overview",
        ))
        journal = _journal_text(ticket.comments) + " " + _journal_text(ticket.work_notes)
        if journal.strip():
            documents.append(RetrievalDocument(
                id=f"ticket:{number}:journal", title=f"{number} — Journal and engineering notes", content=journal,
                source_type="ServiceNow Journal", system="ServiceNow", connector="ServiceNow", url=ticket_url,
                record_type=ticket.type, ticket_number=number, ticket_id=ticket.id, assignment_group=ticket.assignment_group, module=module, section="journal",
            ))
        tasks = _task_text(ticket.ctasks) + " " + _task_text(ticket.ptasks) + " " + _task_text(ticket.sctasks)
        if tasks.strip():
            documents.append(RetrievalDocument(
                id=f"ticket:{number}:tasks", title=f"{number} — Linked task evidence", content=tasks,
                source_type="ServiceNow Task", system="ServiceNow", connector="ServiceNow", url=ticket_url,
                record_type=ticket.type, ticket_number=number, ticket_id=ticket.id, assignment_group=ticket.assignment_group, module=module, section="tasks",
            ))
    return documents


def initialize_vector_db() -> None:
    """Build the vector DB from the live canonical ticket catalog at startup."""

    VECTOR_STORE.sync(build_retrieval_documents())


def _query_terms(text: str) -> set[str]:
    ignored = {"a", "an", "and", "are", "can", "do", "for", "how", "i", "in", "is", "it", "me", "of", "on", "please", "show", "tell", "the", "this", "to", "what", "with", "status", "ticket"}
    return {term for term in re.findall(r"[a-z0-9_/-]+", text.casefold()) if len(term) > 1 and term not in ignored}


def _explicit_ticket_numbers(query_text: str) -> set[str]:
    """Find direct ServiceNow record references before semantic retrieval."""

    query = query_text.casefold()
    return {
        ticket.number
        for ticket in central_ticket_records().values()
        if ticket.number.casefold() in query or ticket.id.casefold() in query
    }


def _has_unmapped_signature(query_text: str) -> bool:
    """Prevent an explicit zero-day signature from receiving unrelated citations."""

    signatures = re.findall(r"[a-z]+[_-]\d+[a-z0-9_-]*|\b\d{4,}\b", query_text.casefold())
    for ticket in central_ticket_records().values():
        if not ticket.is_known_issue:
            haystack = f"{ticket.number} {ticket.short_description} {ticket.description}".casefold()
            if any(signature in haystack for signature in signatures):
                return True
    return False


def retrieve_vector_context(query_text: str, limit: int = 8) -> list[dict[str, object]]:
    """Execute hybrid semantic + lexical relevance filtering over vector results."""

    if not query_text.strip() or _has_unmapped_signature(query_text):
        return []
    documents = build_retrieval_documents()
    VECTOR_STORE.sync(documents)
    terms = _query_terms(query_text)
    explicit_tickets = _explicit_ticket_numbers(query_text)
    selected: list[dict[str, object]] = []
    selected_ids: set[str] = set()
    # A direct ServiceNow number is an authoritative context selection. Add
    # its overview/journal/task chunks before approximate vector results.
    for document in documents:
        if document.ticket_number in explicit_tickets:
            payload = serialize_retrieved(RetrievedDocument(document, 1.0))
            payload["lexical_hits"] = 1
            selected.append(payload)
            selected_ids.add(document.id)
    for result in VECTOR_STORE.query(query_text, limit=limit):
        document = result.document
        if document.id in selected_ids:
            continue
        searchable = f"{document.title} {document.content}".casefold()
        lexical_hits = sum(term in searchable for term in terms)
        semantic_enough = result.score >= 0.62 and VECTOR_STORE.embedder.mode == "gemini"
        if lexical_hits or semantic_enough:
            payload = serialize_retrieved(result)
            payload["lexical_hits"] = lexical_hits
            selected.append(payload)
    return selected[:6]


def _live_ticket_context(chunks: list[dict[str, object]]) -> str:
    """Hydrate retrieved ticket IDs from MOCK_DB immediately before generation."""

    ticket_ids = {
        str(chunk.get("ticket_id") or chunk.get("ticket_number") or "").upper()
        for chunk in chunks
    }
    live_records = [central_ticket_records().get(ticket_id) for ticket_id in ticket_ids]
    snapshots = []
    for ticket in live_records:
        if ticket is None:
            continue
        latest_comment = ticket.comments[-1].value if ticket.comments else "No journal comment recorded"
        snapshots.append(
            f"{ticket.number}: state={ticket.state}; assignment_group={ticket.assignment_group}; "
            f"assignee={ticket.assigned_to}; sla={ticket.sla_health}; time_remaining={ticket.sla_time_remaining}; "
            f"modules={', '.join(ticket.sap_modules)}; latest_journal={latest_comment}"
        )
    return "\n".join(snapshots)


def _grounded_prompt(query_text: str, chunks: list[dict[str, object]]) -> str:
    excerpts = "\n\n".join(f"[{chunk['id']}] {chunk['title']} ({chunk['system']})\n{str(chunk['content'])[:1800]}\nCitation: {chunk['url']}" for chunk in chunks)
    live_context = _live_ticket_context(chunks)
    return (
        "You are the Roche ATLAS ITIL Co-Pilot. Answer only from the internal evidence below. "
        "Provide an assessment, safe next actions, validation/closure evidence, and source citations using [id]. "
        "Do not invent source details.\n\n"
        f"Question: {query_text}\n\nLive ServiceNow ticket state from MOCK_DB:\n{live_context}\n\nEnterprise evidence:\n{excerpts}"
    )


def _fallback_prompt(query_text: str) -> str:
    return (
        "No relevant internal enterprise evidence was retrieved. You are the Roche ATLAS ITIL L2/L3 Co-Pilot. "
        "Provide a labelled diagnostic hypothesis, safe evidence collection steps, a rollback-aware investigation plan, and escalation criteria. "
        "Do not claim internal documents support the answer.\n\n"
        f"Question: {query_text}"
    )


def _local_answer(query_text: str, chunks: list[dict[str, object]]) -> str:
    if not chunks:
        return (
            f"Diagnostic hypothesis: {query_text} requires evidence-led investigation before a remediation decision.\n\n"
            "1. Confirm impact, scope, timestamps, recent changes, and a known-good comparison path.\n"
            "2. Preserve logs, monitoring signals, and correlation IDs before any retry or restart.\n"
            "3. Validate the owning service, dependencies, rollback route, and change-control requirements.\n"
            "4. Escalate with the collected evidence and record requester-facing updates in the ServiceNow journal."
        )
    citations = ", ".join(f"[{chunk['id']}]" for chunk in chunks[:4])
    return (
        f"Assessment: ATLAS retrieved relevant enterprise evidence for “{query_text}” {citations}.\n\n"
        "1. Validate the current ticket state, business impact, and latest human journal update.\n"
        "2. Follow the source-specific controlled recovery or diagnostic procedure before changing production state.\n"
        "3. Capture validation evidence, confirm recovery with the requester, and link the resulting work note to the cited record."
    )


def _sources(chunks: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    sources: list[dict[str, object]] = []
    for chunk in chunks:
        source_id = str(chunk["id"])
        if source_id not in seen:
            seen.add(source_id)
            sources.append({key: chunk[key] for key in ("id", "title", "system", "source_type", "url", "score")})
    return sources


def query_hybrid_rag(query_text: str) -> dict[str, Any]:
    """Retrieve vector evidence, then synthesize a Gemini-grounded response."""

    chunks = retrieve_vector_context(query_text)
    has_internal_match = bool(chunks)
    prompt = _grounded_prompt(query_text, chunks) if has_internal_match else _fallback_prompt(query_text)
    answer = _local_answer(query_text, chunks)
    model_used = "local-grounded-fallback"
    if gemini_client is not None:
        try:
            generated = gemini_client.models.generate_content(model=GENERATION_MODEL, contents=prompt)
            if generated.text:
                answer, model_used = generated.text, GENERATION_MODEL
        except Exception:
            pass
    ticket_ids = []
    for chunk in chunks:
        ticket_id = str(chunk.get("ticket_id") or chunk.get("ticket_number") or "").upper()
        if ticket_id in central_ticket_records() and ticket_id not in ticket_ids:
            ticket_ids.append(ticket_id)
    return {
        "answer": answer, "sources": _sources(chunks), "model_used": model_used,
        "embedding_model": VECTOR_STORE.status()["embedding_model"],
        "fallback_reasoning": not has_internal_match,
        "retrieval_route": "vector_grounded_rag" if has_internal_match else "gemini_itil_reasoning",
        "retrieval": [{key: value for key, value in chunk.items() if key != "content"} for chunk in chunks],
        "ticket_ids": ticket_ids,
    }


def rag_status() -> dict[str, object]:
    """Operational status for local vector retrieval and connector readiness."""

    initialize_vector_db()
    return {"vector_store": VECTOR_STORE.status(), "connectors": connector_statuses(), "generation_model": GENERATION_MODEL if gemini_client is not None else "local-grounded-fallback"}


# Compatibility aliases for older endpoints and integrations.
query_chatgpt_rag = query_hybrid_rag
retrieve_multi_tool_context = retrieve_vector_context
