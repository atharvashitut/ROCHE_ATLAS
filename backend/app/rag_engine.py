"""Hybrid Ollama/Gemini RAG over the canonical ATLAS enterprise corpus.

Retrieval uses a persistent local Chroma collection and Gemini embeddings when
credentials are configured. Ticket state, journal streams, work notes, task
evidence, and four connector sources are indexed as independent chunks.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

try:
    from google import genai
except ImportError:  # pragma: no cover - optional until requirements are installed
    genai = None

# Importing models registers the canonical in-memory ServiceNow catalog with
# CentralTicketRepository.  This keeps RAG usable when this module is invoked
# directly (for example from a worker or a smoke test), rather than only after
# FastAPI has imported `main`.
from .models import MOCK_DB, is_sla_at_risk, is_sla_breached  # noqa: F401
from .central_db import central_knowledge_records, central_ticket_by_reference, central_ticket_records
from .connectors import connector_documents, connector_statuses
from .ollama_client import OLLAMA_GENERATOR, OllamaStreamError
from .vector_store import RetrievedDocument, RetrievalDocument, VECTOR_STORE, serialize_retrieved


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GENERATION_MODEL = os.getenv("ATLAS_GEMINI_GENERATION_MODEL", "gemini-1.5-flash")
KNOWLEDGE_CHUNK_SIZE = 900
KNOWLEDGE_CHUNK_OVERLAP = 150
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY and genai else None
except Exception:  # pragma: no cover - preserve local availability on malformed credentials
    gemini_client = None


def _journal_text(entries: list[Any]) -> str:
    return " ".join(entry.value if hasattr(entry, "value") else str(entry.get("value", entry)) for entry in entries)


def _task_text(tasks: list[dict[str, object]]) -> str:
    return " ".join(" ".join(str(task.get(field, "")) for field in ("number", "short_description", "title", "state", "close_notes")) for task in tasks)


def _knowledge_chunks(text: str, *, size: int = KNOWLEDGE_CHUNK_SIZE, overlap: int = KNOWLEDGE_CHUNK_OVERLAP) -> list[str]:
    """Split knowledge sources into coherent, overlapping retrieval units."""

    normalized = " ".join(text.split())
    if len(normalized) <= size:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + size)
        if end < len(normalized):
            # Keep complete sentences together. Semicolons are frequently
            # used inside a single regulated step, so splitting on one creates
            # duplicated partial instructions across overlapping chunks.
            boundary = normalized.rfind(". ", start + size // 2, end)
            if boundary > start:
                end = boundary + 1
        chunks.append(normalized[start:end].strip())
        if end >= len(normalized):
            break
        overlap_start = max(end - overlap, start + 1)
        # Start the next chunk at a sentence boundary where possible. This
        # retains overlap without creating clipped sentence fragments that
        # would make a displayed procedure look incomplete.
        prior_boundary = normalized.rfind(". ", start, overlap_start)
        start = prior_boundary + 2 if prior_boundary >= start else overlap_start
    return chunks


def build_retrieval_documents() -> list[RetrievalDocument]:
    """Create stable, source-specific chunks from the canonical data stores."""

    documents: list[RetrievalDocument] = []
    for source in connector_documents():
        for index, chunk in enumerate(_knowledge_chunks(str(source["content"]))):
            documents.append(RetrievalDocument(
                id=f"source:{source['id']}:chunk:{index}", title=source["title"],
                content=f"{chunk}\nTags: {' '.join(source['tags'])}",
                source_type=source["source_type"], system=source["system"], connector=source["connector"],
                url=source["url"], record_type="knowledge", ticket_number=",".join(source["ticket_numbers"]),
                ticket_id=",".join(source["ticket_numbers"]), assignment_group="Enterprise Knowledge", module="Enterprise Knowledge", section=f"knowledge_chunk_{index}",
            ))
    for ticket in central_ticket_records().values():
        number = ticket.number
        ticket_url = f"/api/tickets/{number}"
        module = ", ".join(ticket.sap_modules)
        relationship_numbers = [
            *(ticket.child_ids or []),
            *[str(record.get("number", "")) for record in ticket.originating_tickets if record.get("number")],
            *[str(record.get("number", "")) for record in (ticket.parent_incident, ticket.linked_prb, ticket.linked_chg) if record and record.get("number")],
        ]
        resource_context = "; ".join(f"{key}: {value}" for key, value in ticket.resources.items())
        documents.append(RetrievalDocument(
            id=f"ticket:{number}:overview", title=f"{number} — {ticket.short_description}",
            content="\n".join(filter(None, [
                ticket.short_description,
                ticket.description,
                f"State: {ticket.state}. Priority: {ticket.priority}. Assignment group: {ticket.assignment_group}. Assigned to: {ticket.assigned_to}. Caller: {ticket.caller_id}. Requested for: {ticket.requested_for}.",
                f"Category: {ticket.category}. Business service: {ticket.business_service}. SAP modules: {module}. SLA status: {ticket.sla_status}. SLA remaining minutes: {ticket.sla_time_remaining}. Sentiment: {ticket.sentiment}. Hold reason: {ticket.hold_reason}.",
                f"Related ServiceNow records: {', '.join(related_number for related_number in relationship_numbers if related_number) or 'None recorded'}.",
                f"Configuration and service context: {resource_context}",
                ticket.ai_resolution_guide,
            ])),
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


def reindex_vector_db() -> None:
    """Clear derived embeddings and rebuild them from canonical live sources."""

    VECTOR_STORE.reset()
    initialize_vector_db()


async def diagnose_local_generation() -> None:
    """Probe the external Ollama service without loading model weights locally."""

    await OLLAMA_GENERATOR.diagnose()
    await OLLAMA_GENERATOR.warm()


def _query_terms(text: str) -> set[str]:
    ignored = {"a", "an", "and", "are", "can", "do", "for", "how", "i", "in", "is", "it", "me", "of", "on", "please", "show", "tell", "the", "this", "to", "what", "with", "status", "ticket"}
    return {term for term in re.findall(r"[a-z0-9_/-]+", text.casefold()) if len(term) > 1 and term not in ignored}


def _explicit_ticket_numbers(query_text: str) -> set[str]:
    """Find direct ServiceNow record references before semantic retrieval."""

    references = re.findall(r"\b(?:inc|ritm|prb|chg)\d{4,}\b", query_text.casefold())
    return {
        ticket.number
        for reference in references
        if (ticket := central_ticket_by_reference(reference)) is not None
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


def retrieve_vector_context(query_text: str, limit: int = 4) -> list[dict[str, object]]:
    """Execute hybrid semantic + lexical relevance filtering over vector results."""

    if not query_text.strip():
        return []
    # The index is hydrated once at application startup. Avoid rebuilding the
    # corpus and hashing every document on each chat turn; reindex_vector_db()
    # remains the explicit refresh point when a connector source changes.
    if not VECTOR_STORE.status()["document_count"]:
        initialize_vector_db()
    documents = VECTOR_STORE.documents()
    terms = _query_terms(query_text)
    explicit_tickets = _explicit_ticket_numbers(query_text)
    selected: list[dict[str, object]] = []
    selected_ids: set[str] = set()
    # SOP and SUD questions need enough adjacent source evidence to preserve
    # prerequisites, approvals, and the complete remediation sequence.
    selection_limit = min(limit, 5 if _is_knowledge_procedure_request(query_text) else 4)
    # A direct ServiceNow number is an authoritative context selection. Add
    # its overview/journal/task chunks before approximate vector results.
    for document in documents:
        if document.ticket_number in explicit_tickets:
            payload = serialize_retrieved(RetrievedDocument(document, 1.0))
            payload["lexical_hits"] = 1
            selected.append(payload)
            selected_ids.add(document.id)
    # A direct record reference is authoritative.  Do not pad a ticket deep
    # dive with adjacent tickets or SOPs simply because they share keywords;
    # the live canonical record is hydrated separately below.
    if explicit_tickets:
        return selected[:selection_limit]
    # Local hash embeddings preserve offline availability but are less precise
    # than Gemini embeddings for narrow SAP terminology. Rank every canonical
    # document lexically first so a procedure containing several exact terms
    # such as "Basis", "transport", and "STMS" is never crowded out by a
    # loosely related ticket overview.
    lexical_matches = []
    for document in documents:
        if document.id in selected_ids:
            continue
        searchable = f"{document.title} {document.content}".casefold()
        lexical_hits = sum(term in searchable for term in terms)
        if lexical_hits:
            lexical_matches.append((lexical_hits, document))
    for lexical_hits, document in sorted(
        lexical_matches,
        key=lambda item: (item[0], item[1].record_type == "knowledge"),
        reverse=True,
    ):
        if len(selected) >= selection_limit:
            break
        payload = serialize_retrieved(RetrievedDocument(document, min(1.0, lexical_hits / max(1, len(terms)))))
        payload["lexical_hits"] = lexical_hits
        selected.append(payload)
        selected_ids.add(document.id)
    for result in VECTOR_STORE.query(query_text, limit=limit):
        if len(selected) >= selection_limit:
            break
        document = result.document
        if document.id in selected_ids:
            continue
        searchable = f"{document.title} {document.content}".casefold()
        lexical_hits = sum(term in searchable for term in terms)
        # Keep top-k semantic results even when an embedding score is modest:
        # SAP transaction terminology is sparse and valid SUD chunks can be
        # missed by an arbitrary similarity cutoff.
        if lexical_hits or result.score > 0:
            payload = serialize_retrieved(result)
            payload["lexical_hits"] = lexical_hits
            selected.append(payload)
    return selected[:selection_limit]


def _live_ticket_context(chunks: list[dict[str, object]], *, limit: int = 3) -> str:
    """Hydrate retrieved ticket IDs from MOCK_DB immediately before generation."""

    ticket_ids = {
        str(chunk.get("ticket_id") or chunk.get("ticket_number") or "").upper()
        for chunk in chunks
    }
    live_records = [central_ticket_records().get(ticket_id) for ticket_id in ticket_ids]
    snapshots = []
    for ticket in live_records[:limit]:
        if ticket is None:
            continue
        latest_comment = ticket.comments[-1].value if ticket.comments else "No journal comment recorded"
        snapshots.append(
            f"{ticket.number}: state={ticket.state}; assignment_group={ticket.assignment_group}; "
            f"assignee={ticket.assigned_to}; sla={ticket.sla_health}; time_remaining={ticket.sla_time_remaining}; "
            f"modules={', '.join(ticket.sap_modules)}; latest_journal={latest_comment}"
        )
    return "\n".join(snapshots)


def _grounded_prompt(
    query_text: str,
    chunks: list[dict[str, object]],
    *,
    operational_context: str = "",
    history: list[dict[str, str]] | None = None,
    fds_standard_context: str = "",
) -> str:
    """Build evidence for generation without prescribing a response template."""

    # Stats answers already have exact values in the live aggregation, so
    # they need only a compact supporting excerpt. This keeps chart queries
    # especially responsive on CPU-only Ollama while preserving deep SOP text.
    evidence_budget = (
        900 if _is_fds_generation_request(query_text)
        else 1500 if _is_knowledge_procedure_request(query_text)
        else 400 if _is_metrics_intent(query_text)
        else 700
    )
    excerpts = _procedural_markdown_context(chunks, max_characters=evidence_budget)
    # Prior model answers can be several thousand characters each. Bound the
    # transcript before local CPU inference so a follow-up remains responsive
    # while retaining the most recent conversational intent.
    transcript_lines: list[str] = []
    for item in (history or [])[-2:]:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text", "")).split())
        if len(text) > 240:
            text = f"{text[:237].rstrip()}…"
        if text:
            transcript_lines.append(f"{str(item.get('role', 'user')).title()}: {text}")
    transcript = "\n".join(transcript_lines)
    return (
        f"User question:\n{query_text}\n\n"
        f"Recent conversation (optional context):\n{transcript or 'None'}\n\n"
        f"Live operational context:\n{operational_context or _live_ticket_context(chunks) or 'No directly matched live record.'}\n\n"
        f"Functional design standard:\n{fds_standard_context or 'Not requested.'}\n\n"
        f"Retrieved enterprise evidence:\n{excerpts or 'No internal document matched. Use general expertise and clearly distinguish assumptions.'}"
    )


def _procedural_markdown_context(chunks: list[dict[str, object]], *, max_characters: int = 1500) -> str:
    """Return a small, readable SOP payload instead of vector-store metadata.

    Ticket chunks are deliberately excluded: their human-facing fields are
    supplied by the dedicated canonical ticket formatter.  This avoids
    repeating journal text, IDs, and derived vector metadata in the prompt.
    """

    sections: list[str] = []
    remaining = max_characters
    for chunk in chunks:
        if chunk.get("record_type") != "knowledge" or remaining <= 0:
            continue
        title = str(chunk.get("title") or "Enterprise procedure").strip()
        content = re.sub(r"\s+", " ", str(chunk.get("content") or "")).strip()
        if not content:
            continue
        heading = f"### {title}\n"
        available = max(0, remaining - len(heading))
        if available <= 0:
            break
        truncated = len(content) > available
        excerpt = content[:available].rstrip()
        if truncated:
            # Reserve the final character for the truncation marker so the
            # complete Markdown evidence block never exceeds its budget.
            excerpt = f"{excerpt[:max(0, available - 1)].rstrip()}…"
        section = f"{heading}{excerpt}"
        sections.append(section)
        remaining -= len(section) + 2
    return "\n\n".join(sections)


def _fallback_prompt(query_text: str) -> str:
    return (
        f"User question:\n{query_text}\n\n"
        "No internal evidence was retrieved. Use general SAP and ITIL expertise, state uncertainty where relevant, and do not claim an internal source supports the answer."
    )


def _local_generation_prompt(
    query_text: str,
    chunks: list[dict[str, object]],
    *,
    operational_context: str = "",
    history: list[dict[str, str]] | None = None,
    fds_standard_context: str = "",
) -> str:
    """Return a complete grounded prompt for the process-external model."""

    return _grounded_prompt(
        query_text,
        chunks,
        operational_context=operational_context,
        history=history,
        fds_standard_context=fds_standard_context,
    ) if chunks or operational_context or fds_standard_context else _fallback_prompt(query_text)


def _synthesis_system_prompt(*, metric_mode: bool, concise: bool = False, fds_mode: bool = False) -> str:
    """Shared system envelope for Gemini and local Ollama synthesis."""

    metric_instruction = (
        " Metric mode: answer with exactly one short factual sentence in this order: scope, total records, breached, at risk, on track, and on hold. "
        "Copy only the exact counts from Live operational context; do not calculate or mention any percentage. "
        "Never say that more analysis is needed and never substitute one ticket's SLA for the team total."
        if metric_mode else ""
    )
    concise_instruction = (
        " For a normal operational question, answer directly in no more than six short bullets or three short paragraphs. "
        "Only provide a long procedure when the user explicitly requests a complete, detailed, or step-by-step answer."
        if concise else
        " For an explicitly complete procedural request, preserve all relevant prerequisites, approvals, transaction codes, and validation steps."
    )
    fds_instruction = (
        " Functional-design mode: create a complete Markdown Functional Design Specification with exactly these eight H2 headings, in this order: "
        "1. Document Header and Control; 2. Business Context and Scope; 3. Process Flow Diagram; 4. Functional Logic and Processing Algorithm; "
        "5. Technical Mapping and Data Dictionary; 6. Exception Handling and Error Codes; 7. Security and Authorization Requirements; "
        "8. Acceptance Criteria and HP ALM Test Cases. Do not rename, omit, merge, or add sections. "
        "Make the logic implementation-ready, use the retrieved process evidence, identify assumptions explicitly, and include traceability, data mappings, controlled errors, and security. "
        "Section 8 is mandatory and must contain exactly three distinct HP ALM-ready scripts named Positive Functional Path, Negative Boundary Gate, and Authorization Security Gate. "
        "For each script provide a test ID, objective, prerequisites, explicit action steps, expected results, screenshot evidence, and URS/FDS/ServiceNow Change/HP ALM Requirement traceability. "
        "Finish only after Section 8 with the literal marker END OF FDS. "
        "This applies to any requested SAP domain; do not limit the design to EWM unless the user's topic is EWM."
        if fds_mode else ""
    )
    return (
        "You are ATLAS, a senior SAP and GxP operations copilot. Use supplied live data and enterprise evidence as factual grounding. "
        "Start immediately with the requested facts, answer, or procedure. Do not use polite preambles, meta-introductions, or phrases such as 'here is', 'I can help', or 'based on the context'. "
        "Answer the user's actual request in the style, tone, language, length, and format they ask for; you may summarize, explain, write creatively, or use bullets when useful. "
        "Do not invent operational facts or numeric values not supported by the context. When context is incomplete, say what is uncertain. "
        "You may cite a relevant supplied document link naturally when it improves the answer, but do not force citations or a fixed response template."
        f"{metric_instruction}{concise_instruction}{fds_instruction}"
    )


def _is_how_to_question(query_text: str) -> bool:
    # "How many" is a reporting request, not a procedural question. Keep it
    # out of the SOP guard so quantified Dashboard queries retain their
    # canonical filter route.
    return bool(re.search(r"\b(?:how\s+(?:do|to|can|should)|fix|resolve|recover|clear|troubleshoot|steps?|guide)\b", query_text.casefold()))


def _is_analysis_or_resolution_request(query_text: str) -> bool:
    return _is_how_to_question(query_text) or bool(
        re.search(r"\b(analyse|analyze|analysis|resolution|root cause|recommend|what should|next steps?)\b", query_text.casefold())
    )


def _is_knowledge_procedure_request(query_text: str) -> bool:
    """Protect SOP/SUD questions from operational chart intent routing."""

    query = query_text.casefold()
    return _is_analysis_or_resolution_request(query_text) or bool(re.search(
        r"\b(?:explain|process|procedure|workflow|runbook|sop|sud|documentation|instructions?|guide|steps?|how does)\b",
        query,
    ))


def _is_fds_generation_request(query_text: str) -> bool:
    """Recognise a request to author a Functional Design Specification.

    This is intentionally domain-neutral: the governing template comes from
    the canonical Veeva document while the process content comes from the
    matching SUD/SOP documents retrieved for the requested SAP topic.
    """

    return bool(re.search(
        r"\b(?:fds|functional\s+design(?:\s+specification)?|functional\s+specification|ricefw)\b",
        query_text.casefold(),
    ))


def _fds_standard_context(*, max_characters: int = 1800) -> str:
    """Derive a compact eight-section authoring contract from canonical docs.

    The FDS requirements remain data owned by ``CENTRAL_KNOWLEDGE_DB``. This
    helper deliberately reads that source at runtime rather than duplicating
    an authoring template in the chat layer.
    """

    standards = [
        record for record in central_knowledge_records()
        if "fds" in {tag.casefold() for tag in record.get("tags", [])}
        or "functional design specification" in str(record.get("source_type", "")).casefold()
    ]
    sections: list[str] = []
    remaining = max_characters
    for standard in standards:
        content = str(standard.get("content", ""))
        matches = re.findall(r"(Section\s+[1-8][\s\S]*?)(?=\n\nSection\s+[1-8]|\Z)", content, flags=re.IGNORECASE)
        for match in matches:
            normalized = " ".join(match.split())
            if not normalized or remaining <= 0:
                break
            excerpt = normalized[:min(225, remaining)].rstrip()
            if len(normalized) > len(excerpt):
                excerpt = f"{excerpt.rstrip()}…"
            sections.append(excerpt)
            remaining -= len(excerpt) + 1
        if remaining <= 0:
            break
    return "\n".join(sections)


def is_ticket_status_request(query_text: str) -> bool:
    """Require an explicit record reference or update request before ticket wrapping."""

    query = query_text.casefold()
    if re.search(r"\b(?:inc|ritm|prb|chg)\d{4,}\b", query):
        return True
    asks_for_update = bool(re.search(r"\b(status|update|progress|what is happening|current state)\b", query))
    names_a_record = bool(re.search(r"\b(ticket|incident|change request|change|problem|service request|ritm)\b", query))
    return asks_for_update and names_a_record


def is_active_ticket_list_request(query_text: str) -> bool:
    """Identify requests for an operational queue rather than one ticket."""

    query = query_text.casefold()
    asks_for_tickets = bool(re.search(r"\b(tickets?|incidents?|queue|work items?)\b", query))
    asks_for_current_state = bool(re.search(r"\b(current|ongoing|open|active|today)\b", query))
    # A question such as "total number of open tickets and SLA breaches" is
    # an executive metric, not a request to enumerate every open ticket.
    asks_for_summary_metric = bool(re.search(
        r"\b(total|overall|sla|breach(?:ed|es)?|percentage|percent|metric|stats?|kpi|health)\b",
        query,
    ))
    return asks_for_tickets and asks_for_current_state and not asks_for_summary_metric


def _mentioned_assignees(query_text: str) -> list[str]:
    """Resolve people from the live repository, never from a duplicated list."""

    query = query_text.casefold()
    assignees = sorted({ticket.assigned_to for ticket in central_ticket_records().values() if ticket.assigned_to})
    return [assignee for assignee in assignees if assignee.casefold() in query]


def _mentioned_assignment_groups(query_text: str) -> list[str]:
    """Resolve assignment-group names from the same live ticket catalog."""

    query = query_text.casefold()
    groups = sorted({ticket.assignment_group for ticket in central_ticket_records().values() if ticket.assignment_group})
    return [group for group in groups if group.casefold() in query]


def _is_closed(ticket: Any) -> bool:
    return ticket.state in {"Closed", "Resolved", "Closed Complete", "Closed Incomplete", "Closed Skipped", "Canceled"}


def _related_ticket_numbers(ticket: Any) -> list[str]:
    """Read relationship references from the canonical ServiceNow record."""

    numbers = [*ticket.child_ids]
    if ticket.parent_incident and ticket.parent_incident.get("number"):
        numbers.append(str(ticket.parent_incident["number"]))
    for record in (*ticket.originating_tickets, ticket.linked_prb, ticket.linked_chg):
        if record and record.get("number"):
            numbers.append(str(record["number"]))
    return list(dict.fromkeys(number for number in numbers if number and number != ticket.number))


def _suggested_next_step(ticket: Any) -> str:
    """Use the first canonical resolution action instead of generic advice."""

    if ticket.ai_resolution_steps:
        action = str(ticket.ai_resolution_steps[0].get("action", "")).strip()
        if action:
            return action.rstrip(".") + "."
    return (ticket.ai_resolution_summary or ticket.ai_resolution_guide or "Review the ticket evidence with the owning support team.").split(". ", 1)[0].rstrip(".") + "."


def _ticket_detail_block(ticket: Any, index: int) -> list[str]:
    """Format one live queue item with the fields a support lead needs."""

    latest_comment = ticket.comments[-1].value if ticket.comments else "No customer-visible update is recorded."
    related = _related_ticket_numbers(ticket)
    status = f"{ticket.state} · {ticket.priority} · {ticket.assignment_group}"
    if ticket.type in {"INC", "RITM"} and ticket.sla_time_remaining is not None:
        status += f" · {'breached by ' + str(abs(ticket.sla_time_remaining)) + 'm' if ticket.is_breached or ticket.sla_time_remaining <= 0 else str(ticket.sla_time_remaining) + 'm remaining'}"
    if ticket.hold_reason:
        status += f" · {ticket.hold_reason}"
    return [
        f"{index}. {ticket.number} — {ticket.short_description}",
        f"   Status: {status}.",
        f"   Related records: {', '.join(related) if related else 'None recorded'}.",
        f"   Latest update: {latest_comment}",
        f"   Suggested next step: {_suggested_next_step(ticket)}",
    ]


def _workload_answer(scope_name: str, tickets: list[Any]) -> tuple[str, list[str]]:
    """Answer live people/team workload questions without requiring an LLM."""

    active = [ticket for ticket in tickets if not _is_closed(ticket)]
    breached = [ticket for ticket in active if is_sla_breached(ticket)]
    at_risk = [
        ticket for ticket in active
        if ticket not in breached and is_sla_at_risk(ticket)
    ]
    priority_rank = {"1 - Critical": 1, "2 - High": 2, "3 - Moderate": 3, "4 - Low": 4}
    ordered = sorted(active, key=lambda ticket: (
        0 if ticket in breached else 1 if ticket in at_risk else 2,
        priority_rank.get(ticket.priority, 9),
        ticket.number,
    ))
    if not ordered:
        return f"{scope_name} has no active records in the canonical ServiceNow queue.", []
    summary = (
        f"{scope_name} currently has {len(active)} active record{'s' if len(active) != 1 else ''} in the canonical ServiceNow queue. "
        f"{len(breached)} {'is' if len(breached) == 1 else 'are'} breached and {len(at_risk)} {'is' if len(at_risk) == 1 else 'are'} at risk."
    )
    lines = [f"{scope_name} — Current Queue", "", summary, "", "Tickets requiring attention"]
    for index, ticket in enumerate(ordered, start=1):
        lines.extend(_ticket_detail_block(ticket, index))
        lines.append("")
    return "\n".join(lines), [ticket.number for ticket in ordered]


def _is_metrics_intent(query_text: str) -> bool:
    """Recognise questions that require the live Stats calculation path."""

    # Users naturally alternate between "at risk" and "at-risk". Normalise
    # separators before evaluating the generic metric vocabulary so chart
    # eligibility follows the same SLA parser used for canonical filtering.
    query = re.sub(r"[-_]", " ", query_text.casefold())
    metric_terms = (
        "metric", "metrics", "stats", "statistic", "dashboard", "chart", "kpi", "total",
        "how many", "count", "percentage", "percent", "sla health", "sla breach", "breached",
        "at risk", "workload", "capacity", "open tickets", "open work", "anomaly", "unusual",
        "trend", "most breached", "team health", "team workload",
    )
    return any(term in query for term in metric_terms)


def _is_sla_health_question(query_text: str) -> bool:
    """Identify an SLA-health view without treating a queue request as one."""

    query = query_text.casefold()
    return bool(re.search(r"\b(?:sla\s+health|sla\s+status|sla\s+performance|health\s+of\s+sla)\b", query))


def _live_stats_snapshot(query_text: str, *, active_only: bool = True) -> dict[str, Any]:
    """Read the exact Stats-tab aggregation without importing it at module load.

    `main.py` imports this module, so the import is deliberately delayed until
    a live chat request. The call is read-only and uses explicit filter values
    instead of FastAPI's request-time Query defaults.
    """

    from .main import get_dashboard_stats

    groups = _mentioned_assignment_groups(query_text)
    assignees = _mentioned_assignees(query_text)
    modules = sorted(_requested_sap_modules(query_text))
    filters = _dashboard_query_filters(query_text)
    priority_names = {
        1: "1 - Critical",
        2: "2 - High",
        3: "3 - Moderate",
        4: "4 - Low",
    }
    priorities = [priority_names[rank] for rank in sorted(filters["priority_ranks"]) if rank in priority_names]
    exclude_on_hold = bool(re.search(r"\b(?:exclude|excluding|without|not)\s+on[ -]?hold\b", query_text.casefold()))
    return get_dashboard_stats(
        assignment_group=groups,
        group_filter_active=bool(groups),
        assignee=assignees,
        sap_module=modules,
        start_date=None,
        end_date=None,
        active_only=active_only,
        priority=priorities,
        exclude_on_hold=exclude_on_hold,
    )


def _stats_scope_label(stats: dict[str, Any]) -> str:
    """Describe the exact canonical scope used by a live stats response."""

    filters = stats.get("filters", {})
    groups = filters.get("assignment_groups", [])
    modules = filters.get("sap_modules", [])
    assignees = filters.get("assignees", [])
    if assignees:
        return f"{', '.join(assignees)}'s assigned queue"
    if len(groups) == 1:
        return f"{groups[0]} assignment-group scope"
    if modules:
        return f"{' and '.join(modules)} module scope"
    return "full canonical enterprise reporting scope"


def _stats_context_block(stats: dict[str, Any]) -> str:
    """Serialize live Stats values for the deterministic metrics synthesizer.

    This compact, read-only context is intentionally derived from the same
    canonical aggregation used by the Stats tab. It prevents a language model
    from guessing executive metrics while preserving the existing LLM paths
    for procedural and ticket-specific questions.
    """

    summary = stats["summary"]
    sla_segments = {
        str(segment["label"]): int(segment["value"])
        for segment in stats["sla_health_breakdown"]
    }
    return "\n".join([
        f"Scope: {_stats_scope_label(stats)}",
        f"Total records: {summary['total_tickets']}",
        f"In progress: {summary['in_progress']}",
        f"On hold: {summary['on_hold']}",
        f"SLA breached: {sla_segments.get('Breached', 0)}",
        f"SLA at risk: {sla_segments.get('At Risk', 0)}",
        f"SLA on track: {sla_segments.get('On Track', 0)}",
        f"Awaiting caller: {summary['awaiting_caller']}",
        f"Awaiting change: {summary['awaiting_change']}",
        f"Awaiting child: {summary['awaiting_child']}",
        f"Awaiting vendor: {summary['awaiting_vendor']}",
        f"Awaiting problem: {summary['awaiting_problem']}",
        f"Awaiting parent: {summary['awaiting_parent']}",
    ])


def _stats_chart_payload(stats: dict[str, Any]) -> dict[str, object]:
    """Build a UI-neutral chart payload solely from live Stats aggregation."""

    summary = stats["summary"]
    scope = _stats_scope_label(stats)
    sla_data = [
        dict(segment)
        for segment in stats["sla_health_breakdown"]
        if segment["label"] != "No SLA (PRB/CHG)"
    ]
    work_state_data = [dict(segment) for segment in stats["work_state_breakdown"]]
    on_track = int(next((item["value"] for item in sla_data if item["label"] == "On Track"), 0))
    return {
        "type": "dashboard_summary",
        "title": f"Live operational snapshot — {scope}",
        "categories": [item["label"] for item in sla_data],
        "series": [{"name": "SLA-tracked records", "data": [int(item["value"]) for item in sla_data]}],
        "metrics": [
            {"label": "Total scope", "value": int(summary["total_tickets"]), "color": "#38bdf8"},
            {"label": "SLA breached", "value": int(summary["breached"]), "color": "#ef4444"},
            {"label": "At risk", "value": int(next((item["value"] for item in sla_data if item["label"] == "At Risk"), 0)), "color": "#f59e0b"},
            {"label": "On track", "value": on_track, "color": "#10b981"},
            {"label": "On hold", "value": int(summary["on_hold"]), "color": "#a78bfa"},
        ],
        "charts": [
            {"type": "bar", "title": "SLA health", "data": sla_data},
            {"type": "bar", "title": "Active work state", "data": work_state_data},
        ],
    }


def _stats_answer(
    query_text: str,
    stats: dict[str, Any],
    stats_context: str | None = None,
) -> tuple[str, list[str]]:
    """Present calculated dashboard values in concise, natural language."""

    query = query_text.casefold()
    summary = stats["summary"]
    records = stats["record_type_pipeline"]
    active_total = sum(int(record["active"]) for record in records)
    sla_segments = {str(segment["label"]): int(segment["value"]) for segment in stats["sla_health_breakdown"]}
    eligible = sla_segments.get("Breached", 0) + sla_segments.get("At Risk", 0) + sla_segments.get("On Track", 0)
    breached = sla_segments.get("Breached", 0)
    breach_rate = round((breached / eligible) * 100) if eligible else 0
    on_track_count = sla_segments.get("On Track", 0)
    on_track_rate = round((on_track_count / eligible) * 100) if eligible else 0
    listed = [str(ticket["number"]) for ticket in stats.get("ticket_index", [])]
    # Read the scope from the exact serialized snapshot supplied to this
    # deterministic synthesizer. The numerical values below come from the
    # same immutable Stats payload rather than from model generation.
    context_lines = (stats_context or _stats_context_block(stats)).splitlines()
    scope_value = next((line.removeprefix("Scope: ") for line in context_lines if line.startswith("Scope: ")), _stats_scope_label(stats))
    scope = scope_value if scope_value.endswith("'s assigned queue") else f"the {scope_value}"

    if any(term in query for term in ("unusual", "anomaly", "abnormal")):
        insights = stats.get("anomaly_detection", {}).get("insights", [])
        if not insights:
            return f"I do not see an unusual incident pattern in {scope} for the current reporting window.", listed
        insight = insights[0]
        impacted = [str(ticket_id) for ticket_id in insight.get("ticket_ids", [])]
        impacted_assignees = sorted({
            ticket.assigned_to
            for ticket in central_ticket_records().values()
            if ticket.number in impacted
        })
        lines = [
            f"AI Operations Insight — {scope}",
            "",
            "Finding",
            insight["title"],
            "",
            "Evidence",
            f"• {insight['explanation']}",
            f"• Confidence: {insight['confidence_score']}%.",
            f"• Affected tickets: {', '.join(impacted) or 'none recorded'}.",
            f"• Assignment-group evidence: {'; '.join(str(item) for item in insight.get('supporting_evidence', [])[:3])}.",
            f"• Relevant assignees: {', '.join(impacted_assignees) or 'not recorded'}.",
            "",
            "Recommended Action",
            f"• {insight['recommended_action']}.",
        ]
        return "\n\n".join(lines), impacted

    if "assignee" in query and any(term in query for term in ("breach", "breached", "most")):
        workloads = stats.get("assignee_workload", [])
        if not workloads:
            return f"No assignee workload is available in {scope}.", listed
        top = max(workloads, key=lambda item: (int(item["breached"]), int(item["at_risk"]), int(item["active"])))
        return (
            f"{top['assignee']} has the most SLA-breached work in {scope}: {top['breached']} breached record"
            f"{'s' if top['breached'] != 1 else ''}, {top['at_risk']} at risk, and {top['active']} active. "
            f"Their coverage includes {', '.join(top['assignment_groups'])}.",
            [ticket["number"] for ticket in stats.get("ticket_index", []) if ticket["assignee"] == top["assignee"]],
        )

    if any(term in query for term in ("sla", "breach", "breached", "percentage", "percent", "at risk")):
        return (
            "\n".join([
                f"SLA Health — {scope}",
                "",
                "Current Position",
                f"• Total tracked records: {eligible}.",
                f"• On track: {on_track_count} ({on_track_rate}%).",
                f"• At risk: {sla_segments.get('At Risk', 0)}.",
                f"• Breached: {breached} ({breach_rate}%).",
                f"• Active work items in scope: {active_total}.",
                "",
                "SLA Breakdown",
                f"• Breached: {breached} · At risk: {sla_segments.get('At Risk', 0)} · On track: {on_track_count}.",
            ]),
            listed,
        )

    return (
        "\n".join([
            f"Operational Summary — {scope}",
            "",
            "Current Workload",
            f"• Active work items: {active_total} of {summary['total_tickets']} records in scope.",
            f"• In progress: {summary['in_progress']}.",
            f"• On hold: {summary['on_hold']}.",
            f"• SLA breached: {breached}.",
            "",
            "On-Hold Dependencies",
            f"• Awaiting caller: {summary['awaiting_caller']}.",
            f"• Awaiting change: {summary['awaiting_change']}.",
            f"• Awaiting child: {summary['awaiting_child']}.",
            f"• Awaiting vendor: {summary['awaiting_vendor']}.",
            f"• Awaiting problem: {summary['awaiting_problem']}.",
            f"• Awaiting parent: {summary['awaiting_parent']}.",
        ]),
        listed,
    )


def _ticket_answer(ticket: Any) -> str:
    """Return direct canonical detail for an explicit ServiceNow reference."""

    latest = ticket.comments[-1].value if ticket.comments else "No customer-visible update is recorded."
    details = [
        f"{ticket.number} is currently {ticket.state}: {ticket.short_description}.",
        f"It is owned by {ticket.assigned_to} in {ticket.assignment_group} with priority {ticket.priority}.",
    ]
    if ticket.type in {"INC", "RITM"} and ticket.sla_time_remaining is not None:
        details.append(
            f"The SLA is {'breached by ' + str(abs(ticket.sla_time_remaining)) + ' minutes' if ticket.is_breached or ticket.sla_time_remaining <= 0 else str(ticket.sla_time_remaining) + ' minutes remaining'}"
            + (f" and the current hold reason is {ticket.hold_reason}." if ticket.hold_reason else ".")
        )
    elif ticket.type == "PRB":
        details.append(f"The problem is in {ticket.prb_phase or ticket.rca_phase or 'its current'} analysis phase with risk {ticket.risk_level or 'not recorded'}.")
    elif ticket.type == "CHG":
        details.append(f"The change is in {ticket.chg_phase or ticket.cab_status or 'its current'} phase with risk {ticket.risk_level or 'not recorded'}.")
    details.extend([f"Latest update: {latest}", f"Recommended next step: {ticket.ai_resolution_summary or ticket.ai_resolution_guide}"])
    return "\n\n".join(details)


def _requested_sap_modules(query_text: str) -> set[str]:
    query = query_text.casefold()
    aliases = {
        "SAP EWM": ("ewm", "warehouse", "qrfc", "rf "),
        "SAP BASIS": ("basis", "sm37", "stms", "transport", "spool", "gateway"),
        "SAP PLM": ("plm", "recipe", "classification", "design bom"),
        "SAP MM": ("sap mm", " mm ", "purchase order", "supplier", "procurement", "release strategy"),
        "SAP SD": ("sap sd", " sd ", "billing", "sales order"),
        "SAP FICO": ("fico", "tax code", "finance posting"),
    }
    return {
        module
        for module, terms in aliases.items()
        if any(term in f" {query} " for term in terms)
    }


def _dashboard_query_filters(query_text: str) -> dict[str, object]:
    """Translate dashboard language into ServiceNow-field filters.

    The parser intentionally recognises field concepts and ordinary synonyms,
    not a finite set of canned questions. Every result is then evaluated over
    the canonical ticket repository, so Dashboard, Stats, and Chat retain one
    source of truth.
    """

    query = query_text.casefold()
    record_types: set[str] = set()
    if re.search(r"\b(?:incidents?|inc)\b", query):
        record_types.add("INC")
    if re.search(r"\b(?:service requests?|requests?|ritm)\b", query):
        record_types.add("RITM")
    if re.search(r"\b(?:problems?|prb)\b", query):
        record_types.add("PRB")
    if re.search(r"\b(?:changes?|change requests?|chg)\b", query):
        record_types.add("CHG")

    explicit_states: set[str] = set()
    state_patterns = {
        "New": r"\bnew\b",
        "In Progress": r"\bin[ -]?progress\b",
        "On Hold": r"\bon[ -]?hold\b|\bawaiting\b",
        "Resolved": r"\bresolved\b",
        "Closed": r"\bclosed\b|\bcomplete(?:d)?\b",
        "Root Cause Analysis": r"\b(?:root cause analysis|rca)\b",
        "Implement": r"\bimplement(?:ing|ation)?\b",
        "Assess": r"\basses(?:s|sing|ment)\b",
        "Authorize": r"\bauthori[sz](?:e|ed|ation)\b",
        "Scheduled": r"\bscheduled?\b",
        "Review": r"\breview\b",
    }
    for state, pattern in state_patterns.items():
        if re.search(pattern, query):
            explicit_states.add(state)

    hold_reasons: set[str] = set()
    hold_patterns = {
        "Awaiting Caller": r"\bawaiting\s+(?:caller|customer|user)\b",
        "Awaiting Change": r"\bawaiting\s+(?:change|cr)\b",
        "Awaiting Child": r"\bawaiting\s+child\b",
        "Awaiting Vendor": r"\bawaiting\s+vendor\b",
        "Awaiting Problem": r"\bawaiting\s+(?:problem|prb)\b",
        "Awaiting Parent": r"\bawaiting\s+parent\b",
    }
    for reason, pattern in hold_patterns.items():
        if re.search(pattern, query):
            hold_reasons.add(reason)

    priority_ranks = {
        int(match)
        for match in re.findall(r"\bp\s*([1-4])\b|\b([1-4])\s*[- ]\s*(?:critical|high|moderate|low)\b", query)
        for match in match
        if match
    }
    if re.search(r"\bcritical\b", query):
        priority_ranks.add(1)
    if re.search(r"\bhigh(?:[- ]priority)?\b", query):
        priority_ranks.add(2)
    if re.search(r"\bmoderate\b", query):
        priority_ranks.add(3)
    if re.search(r"\blow(?:[- ]priority)?\b", query):
        priority_ranks.add(4)

    # Negation must win over the generic breached token so "non-breached" is
    # always an SLA exclusion rather than a breach request.
    if re.search(r"\b(?:non|not|un)[ -]?breach(?:ed)?\b|\bwithin\s+sla\b|\bmet\s+sla\b", query):
        sla_mode = "non_breached"
    elif re.search(r"\bat[ -]?risk\b|\bnear[ -]?breach\b", query):
        sla_mode = "at_risk"
    elif re.search(r"\bon[ -]?track\b", query):
        sla_mode = "on_track"
    elif re.search(r"\bbreach(?:ed|es)?\b", query):
        sla_mode = "breached"
    else:
        sla_mode = None

    closed_requested = bool(re.search(r"\b(?:closed|resolved|completed|cancel(?:led|ed))\b", query))
    procedure_language = bool(re.search(r"\b(?:how do i|how to|recover|resolve|troubleshoot|configure|execute|activate)\b", query))
    # "Queue" can mean either a ServiceNow work queue or a SAP qRFC queue.
    # Treat it as an active-work signal only in the former, non-procedural
    # context; this prevents SMQ1/SMQ2 troubleshooting from becoming a ticket
    # list request.
    active_requested = bool(re.search(r"\b(?:active|open|ongoing|current|backlog)\b", query)) or ("queue" in query and not procedure_language)
    requires_active = bool(sla_mode or hold_reasons or active_requested) and not closed_requested
    return {
        "modules": _requested_sap_modules(query_text),
        "groups": _mentioned_assignment_groups(query_text),
        "assignees": _mentioned_assignees(query_text),
        "record_types": record_types,
        "states": explicit_states,
        "hold_reasons": hold_reasons,
        "priority_ranks": priority_ranks,
        "sla_mode": sla_mode,
        "requires_active": requires_active,
        "asks_for_count": bool(re.search(r"\b(?:how many|count|number of|total)\b", query)),
        "asks_for_details": bool(re.search(r"\b(?:show|list|which|details?|queue|records?)\b", query)),
    }


def _ticket_priority_rank(ticket: Any) -> int:
    match = re.search(r"\b([1-4])\b", str(ticket.priority))
    if match:
        return int(match.group(1))
    return {"P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(str(ticket.priority).upper(), 9)


def _is_at_risk(ticket: Any) -> bool:
    return is_sla_at_risk(ticket)


def _dashboard_filtered_tickets(query_text: str) -> tuple[list[Any], dict[str, object]]:
    """Apply reusable ServiceNow field filters directly to canonical records."""

    filters = _dashboard_query_filters(query_text)
    tickets = list(central_ticket_records().values())
    closed_states = {"Resolved", "Closed", "Closed Complete", "Closed Incomplete", "Closed Skipped", "Canceled"}
    modules = set(filters["modules"])
    groups = set(filters["groups"])
    assignees = set(filters["assignees"])
    record_types = set(filters["record_types"])
    states = set(filters["states"])
    hold_reasons = set(filters["hold_reasons"])
    priority_ranks = set(filters["priority_ranks"])
    sla_mode = filters["sla_mode"]

    if modules:
        tickets = [ticket for ticket in tickets if modules.intersection(ticket.sap_modules)]
    if groups:
        tickets = [ticket for ticket in tickets if ticket.assignment_group in groups]
    if assignees:
        tickets = [ticket for ticket in tickets if ticket.assigned_to in assignees]
    if record_types:
        tickets = [ticket for ticket in tickets if ticket.type in record_types]
    if states:
        tickets = [ticket for ticket in tickets if ticket.state in states]
    if hold_reasons:
        tickets = [ticket for ticket in tickets if ticket.hold_reason in hold_reasons]
    if priority_ranks:
        tickets = [ticket for ticket in tickets if _ticket_priority_rank(ticket) in priority_ranks]
    if filters["requires_active"]:
        tickets = [ticket for ticket in tickets if ticket.state not in closed_states]
    if sla_mode:
        # SLA status is defined only for incidents and requests. Problems and
        # changes are deliberately excluded instead of being mislabelled as
        # non-breached work.
        tickets = [ticket for ticket in tickets if ticket.type in {"INC", "RITM"}]
        if sla_mode == "breached":
            tickets = [ticket for ticket in tickets if ticket.is_breached or (ticket.sla_time_remaining is not None and ticket.sla_time_remaining <= 0)]
        elif sla_mode == "non_breached":
            tickets = [ticket for ticket in tickets if not ticket.is_breached and (ticket.sla_time_remaining is None or ticket.sla_time_remaining > 0)]
        elif sla_mode == "at_risk":
            tickets = [ticket for ticket in tickets if _is_at_risk(ticket)]
        elif sla_mode == "on_track":
            tickets = [ticket for ticket in tickets if not _is_at_risk(ticket) and not ticket.is_breached and str(ticket.sla_status).upper() == "ON_TRACK"]
    tickets.sort(key=lambda ticket: (_ticket_priority_rank(ticket), ticket.sla_time_remaining if ticket.sla_time_remaining is not None else 10**9, ticket.number))
    return tickets, filters


def _is_dashboard_filter_request(query_text: str) -> bool:
    """Decide whether a question asks for a filtered operational queue."""

    query = query_text.casefold()
    filters = _dashboard_query_filters(query_text)
    procedural = bool(re.search(r"\b(?:how do i|how to|create|configure|explain|steps?|guide|process|workflow|procedure|approval)\b", query))
    record_signal = bool(re.search(r"\b(?:tickets?|incidents?|requests?|problems?|changes?|queue|work items?|records?)\b", query))
    quantifier = bool(filters["asks_for_count"])
    applied_filter = any((
        filters["modules"], filters["groups"], filters["assignees"], filters["record_types"], filters["states"],
        filters["hold_reasons"], filters["priority_ranks"], filters["sla_mode"], filters["requires_active"],
    ))
    return applied_filter and (record_signal or quantifier) and not (procedural and not (quantifier or filters["asks_for_details"]))


def _dashboard_filter_label(filters: dict[str, object]) -> str:
    """Create a transparent human label from the active canonical filters."""

    parts: list[str] = []
    sla_label = {
        "breached": "SLA-breached",
        "non_breached": "non-breached SLA-tracked",
        "at_risk": "SLA at-risk",
        "on_track": "SLA on-track",
    }.get(str(filters["sla_mode"]), "")
    if sla_label:
        parts.append(sla_label)
    if filters["priority_ranks"]:
        parts.append(" / ".join(f"P{rank}" for rank in sorted(filters["priority_ranks"])))
    if filters["states"]:
        parts.append(" / ".join(sorted(filters["states"])))
    if filters["hold_reasons"]:
        parts.append(" / ".join(sorted(filters["hold_reasons"])))
    if filters["record_types"]:
        parts.append(" / ".join(sorted(filters["record_types"])))
    if filters["modules"]:
        parts.append(" / ".join(sorted(filters["modules"])))
    if filters["groups"]:
        parts.append(" / ".join(sorted(filters["groups"])))
    if filters["assignees"]:
        parts.append(" / ".join(sorted(filters["assignees"])))
    return " ".join(parts) or "Canonical ServiceNow"


def _dashboard_filtered_answer(query_text: str) -> tuple[str, list[str]]:
    """Answer any canonical dashboard filter combination without canned data."""

    tickets, filters = _dashboard_filtered_tickets(query_text)
    label = _dashboard_filter_label(filters)
    active_qualifier = " active" if filters["requires_active"] else ""
    if not tickets:
        return f"I found no{active_qualifier} {label} records in the canonical ServiceNow repository.", []
    noun = "record" if len(tickets) == 1 else "records"
    lines = [f"{label} {noun.title()} ({len(tickets)})", "", f"I found {len(tickets)}{active_qualifier} {label} {noun.lower()} using the live ServiceNow fields."]
    if filters["asks_for_count"] and not filters["asks_for_details"]:
        lines.extend(["", "Matching records", *[f"{ticket.number} — {ticket.short_description} ({ticket.state})" for ticket in tickets]])
    else:
        lines.extend(["", "Queue details"])
        for index, ticket in enumerate(tickets, start=1):
            lines.extend(_ticket_detail_block(ticket, index))
            lines.append("")
    return "\n".join(lines), [ticket.number for ticket in tickets]


def _active_ticket_list(query_text: str) -> list[Any]:
    tickets, _ = _dashboard_filtered_tickets(f"{query_text} active")
    priority_rank = {"1 - Critical": 1, "2 - High": 2, "3 - Moderate": 3, "4 - Low": 4}
    return sorted(tickets, key=lambda ticket: (priority_rank.get(ticket.priority, 9), ticket.number))


def _active_ticket_list_answer(query_text: str) -> tuple[str, list[str]]:
    tickets = _active_ticket_list(query_text)
    requested_modules = sorted(_requested_sap_modules(query_text))
    scope = " and ".join(requested_modules) if requested_modules else "selected"
    if not tickets:
        return (
            f"I do not see any current {scope} tickets in the canonical queue. "
            "Try another SAP module, assignment group, or a broader date scope.",
            [],
        )
    lines = [f"Current {scope} tickets", "", f"I found {len(tickets)} active record{'s' if len(tickets) != 1 else ''}.", "", "Queue details"]
    for index, ticket in enumerate(tickets, start=1):
        lines.extend(_ticket_detail_block(ticket, index))
        lines.append("")
    return "\n".join(lines), [ticket.number for ticket in tickets]


def _is_breached_ticket_list_request(query_text: str, history: list[dict[str, str]] | None = None) -> bool:
    """Recognise a direct or contextual request to enumerate SLA breaches."""

    query = query_text.casefold()
    # A quantified SLA question is an executive metric, not an enumeration.
    # Keep it on the canonical Stats + chart route even when it contains the
    # words "what", "tickets", and "breached".
    if re.search(r"\b(?:how\s+many|count|number\s+of|total)\b", query):
        return False
    mentions_breach = "breach" in query
    # Direct requests such as "Breached tickets in Basis" omit a leading
    # interrogative, but the plural record noun still unambiguously asks for a
    # list. Keep contextual pronouns for follow-up requests as well.
    asks_to_list = bool(re.search(r"\b(which|what|show|list|these|those|name)\b", query)) or bool(
        mentions_breach and re.search(r"\b(tickets?|incidents?|records?|work items?)\b", query)
    )
    history_text = " ".join(str(item.get("text", "")) for item in (history or [])[-6:]).casefold()
    return asks_to_list and (mentions_breach or ("breach" in history_text and bool(re.search(r"\b(these|those|them)\b", query))))


def _breached_ticket_list_answer(query_text: str) -> tuple[str, list[str]]:
    """Enumerate active SLA breaches within the canonical query scope."""

    requested_modules = sorted(_requested_sap_modules(query_text))
    breached = [
        ticket for ticket in central_ticket_records().values()
        if not _is_closed(ticket)
        and ticket.type in {"INC", "RITM"}
        and (ticket.is_breached or (ticket.sla_time_remaining is not None and ticket.sla_time_remaining <= 0))
    ]
    if requested_modules:
        breached = [
            ticket for ticket in breached
            if set(ticket.sap_modules).intersection(requested_modules)
        ]
    priority_rank = {"1 - Critical": 1, "2 - High": 2, "3 - Moderate": 3, "4 - Low": 4}
    breached.sort(key=lambda ticket: (priority_rank.get(ticket.priority, 9), ticket.sla_time_remaining or 0, ticket.number))
    scope = f"{', '.join(requested_modules)}" if requested_modules else "Enterprise"
    if not breached:
        return f"There are no active SLA-breached INC or RITM records in the {scope} module scope.", []
    lines = [
        f"{scope} SLA-Breached Tickets ({len(breached)})",
        "",
        "These results are filtered directly from canonical ticket SAP-module tags.",
        "",
    ]
    for index, ticket in enumerate(breached, start=1):
        lines.extend(_ticket_detail_block(ticket, index))
        lines.append("")
    return "\n".join(lines), [ticket.number for ticket in breached]


def _is_ewm_queue_lock_question(query_text: str) -> bool:
    query = query_text.casefold()
    return "ewm" in query and any(term in query for term in ("qrfc", "queue lock", "queue", "sm12", "smq1", "smq2"))


def _is_goods_receipt_question(query_text: str) -> bool:
    """Recognise the LEAP GR process without confusing it with inventory reconciliation."""

    query = query_text.casefold()
    return bool(
        re.search(r"\b(?:good(?:s)?\s+receipt|wareneingang|wareneingangsprozess|gr)\b", query)
        or any(term in query for term in ("/scwm/prdi", "inbound delivery", "hu creation", "handling unit packaging", "putaway by hu", "leap gr"))
    )


def _is_broad_goods_receipt_overview(query_text: str) -> bool:
    """Limit the curated LEAP overview to deliberately broad workflow asks.

    A mention of a Goods Receipt transaction is not, by itself, a reason to
    hide a concrete error runbook behind the generic five-step overview.
    """

    query = query_text.casefold()
    return _is_goods_receipt_question(query_text) and bool(
        re.search(r"\b(?:explain|overview|process|workflow|walk\s+me\s+through|describe)\b", query)
    ) and not _has_specific_troubleshooting_signal(query_text)


def _has_specific_troubleshooting_signal(query_text: str) -> bool:
    """Identify a request that must be answered from retrieved runbook evidence.

    These are field signatures and SAP transactions, not a list of canned
    questions.  They deliberately sit above broad process templates so the
    knowledge corpus remains the authority for an actual failure.
    """

    query = query_text.casefold()
    if re.search(
        r"(?:\bqa\s*0*07\b|\bm8\s*147\b|\bm7\s*0*42\b|/scwm/delivery\s*0*03\b|"
        r"\bcc0*32\b|\bqie_insp_doc\s*0*12\b|\bsysfail\b|\bmsc[23]n\b|\bobyc\b|"
        r"\bstms_import\b|\bcs02\b|\bcv0?[12]n\b|\bcc0?[12]\b)",
        query,
    ):
        return True
    return bool(re.search(r"\b(?:how\s+to\s+(?:resolve|fix)|how\s+(?:do|can|should)\s+.*(?:resolve|fix)|error|failed|blocked)\b", query))


def _is_integration_change_question(query_text: str) -> bool:
    query = query_text.casefold()
    return "change" in query and any(term in query for term in ("interface", "integration", "middleware", "api"))


def _is_servicenow_change_management_question(query_text: str) -> bool:
    """Recognise procedural Change Management questions, not CHG queue asks."""

    query = query_text.casefold()
    discusses_change = bool(re.search(r"\b(?:change management|change request|normal change|authorization change|ctask|c task)\b", query))
    procedure_signal = bool(re.search(r"\b(?:how|create|process|workflow|steps?|approval|assessment|testing|alm|close)\b", query))
    return discusses_change and procedure_signal


def _procedure_title(query_text: str, chunks: list[dict[str, object]]) -> str:
    """Choose a human-readable heading from the resolved knowledge context."""

    if _is_broad_goods_receipt_overview(query_text):
        return "LEAP SAP EWM Goods Receipt"
    if _is_integration_change_question(query_text):
        return "Production SAP Interface Change Control"
    if _is_servicenow_change_management_question(query_text):
        return "ServiceNow GxP Change Management"
    query = query_text.casefold()
    if any(term in query for term in ("smq1", "smq2", "sysfail", "stms", "transport", "basis")):
        return "SAP BASIS Queue and Transport Operations"
    if any(term in query for term in ("migo", "qa 007", "m7 042", "msc2n", "purchase order")):
        return "SAP MM Goods Movement and Batch Status Recovery"
    if any(term in query for term in ("cc032", "aennr", "change master", "cc01", "cc02", "bom", "document info")):
        return "SAP PLM Engineering Change Master Control"
    for chunk in chunks:
        if chunk.get("record_type") == "knowledge" and chunk.get("title"):
            return str(chunk["title"])
    return "ATLAS Operating Guidance"


def _format_procedure_answer(query_text: str, actions: list[str], chunks: list[dict[str, object]]) -> str:
    """Return consistent, scan-friendly SOP guidance from grounded actions."""

    title = _procedure_title(query_text, chunks)
    overview = (
        "This is the controlled sequence from the connected enterprise procedure. Complete each validation before moving to the next operational step."
    )
    controls = [
        "Preserve the relevant system evidence before changing production state.",
        "Use the approved escalation or change-control route when a production configuration change is required.",
    ]
    return "\n".join([
        title,
        "",
        "Overview",
        overview,
        "",
        "Procedure",
        *[f"{index}. {action}" for index, action in enumerate(actions, start=1)],
        "",
        "Key Controls",
        *[f"• {control}" for control in controls],
    ])


def _topic_action_items(query_text: str) -> list[str] | None:
    """Return concise local guidance for the high-value SAP support domains."""

    query = query_text.casefold()
    # Error signatures and explicit troubleshooting always use the vector
    # retrieved source.  Do not let a generic SOP template override the
    # evidence that explains the particular failure.
    if _has_specific_troubleshooting_signal(query_text):
        return None
    # Change compliance questions are grounded in the Veeva source rather
    # than a static summarisation.  This also prevents them from falling into
    # an operational CHG list route.
    if _is_servicenow_change_management_question(query_text):
        return None
    if _is_integration_change_question(query_text):
        return [
            "Confirm the affected interface, source and target systems, business impact, approved Change Request, implementation owner, and rollback owner.",
            "Capture the failing payload, correlation ID, current mapping version, endpoint response, and a known-good comparison before retrying or changing production configuration.",
            "Complete the required impact assessment, test evidence, approvals, implementation plan, and rollback plan under the approved change-control procedure.",
            "Implement only in the approved window. Monitor message processing, error queues, downstream record creation, and business validation during the change.",
            "Validate the end-to-end outcome with the business owner, record the evidence and residual risk in the Change Request, then close or roll back using the approved decision path.",
        ]
    if _is_broad_goods_receipt_overview(query_text):
        return [
            "Open and validate the inbound delivery in /SCWM/PRDI. Physically check the delivered quantity, review temperature requirements, and deconsolidate material by the required temperature zone.",
            "Create and label the Handling Units using the approved packaging specification. Keep only the permitted material type in each HU and retain the delivery evidence.",
            "Before putaway, verify that capacity checks are active for the storage type, product-master capacity consumption and destination-bin capacity are maintained, and the HU type is allowed for the proposed storage type and bin type.",
            "Create the putaway warehouse task. Where required, assign the HU to a transport HU and route it by conveyor or lift to primary level 0000 or 050.",
            "In the primary area, use Putaway by HU and confirm the final destination bin. Use CHPD only for an approved alternate bin. In LEAP, goods receipt posts when the destination putaway warehouse task is confirmed.",
        ]
    if any(term in query for term in ("lab2whs", "lab to warehouse", "return hu", "return handling unit", "return to primary", "return to secondary", "lab concierge", "ro id", "gi buffer")) or ("return" in query and any(term in query for term in ("lab", "warehouse", "hu", "handling unit", "primary", "secondary"))):
        return [
            "For a long term return to primary storage, use RF Option 4 Put away by HU, enter the RO ID, scan the handling unit, select Primary, and scan the secondary intermediate bin.",
            "Use the floor assigned Lab Concierge resource to run Picking by Q, select the applicable LEVEL XX to PSXX queue, scan the transport HU and source HU, and review any hazardous material warning before moving it to the conveyor bin.",
            "The logistics team completes Put away by HU in primary storage by scanning the transport HU, acknowledging the warning, and scanning the final destination bin.",
            "For overnight lab storage, select Secondary and scan the target bin; this confirms immediately and does not create a follow up task. For an administrative transfer, create a Process Type 10 warehouse task in Warehouse Management Monitor.",
            "Check the GI Buffer status before starting: once the consumption job has posted goods issue, the HU cannot be returned through LAB2WHS. Confirm temperature and storage class compatibility before confirmation.",
        ]
    if any(term in query for term in ("hazardous", "hazardous material", "storage class", "flash point", "ph value", "ph maintenance", "hsmr02", "hazardoussubstance", "we02", "eh&s", "ehs data")):
        return [
            "Identify which hazardous attribute is missing or incorrect: storage class, flash point in degrees Celsius, or pH value.",
            "For storage class or flash point changes, trigger the ERP transmission in HSMR02 with the material and logistical data. EWM receives the HAZARDOUSSUBSTANCE IDoc through ERP rather than directly from P08.",
            "Maintain pH manually after the IDoc in MAT1, Warehouse Data, under the custom Z fields. The pH field is a numeric free text value and is not populated automatically.",
            "Verify the combined values in Warehouse Management Monitor under Roche Enhancement and Product. If the IDoc is stuck, inspect WE02; if flash point is wrong, correct the ERP unit to Celsius before retransmitting.",
            "Use the hazardous mixing exception only for the approved scrapping process. It is not a normal putaway workaround.",
        ]
    if any(term in query for term in ("request hub", "request id", "order id", "muleleap", "datariver", "iwfwnd/traces", "def_release_who", "zl84_release_who", "zl84_req", "cube order")):
        return [
            "Confirm the individual Request ID as well as the basket Order ID, delivery level, and, for CUBE material, the required destination bin.",
            "If the request is absent from EWM, inspect /IWFWND/TRACES filtered by user MULELEAP and follow the payload through Request Hub, MuleSoft, DataRiver, and the EWM OData API.",
            "Check whether the picking warehouse task is deliberately locked or blocked for its future delivery date. DEF_RELEASE_WHO, program ZL84_RELEASE_WHO, releases eligible work at 02:00 and 13:00.",
            "Use ZL84_REQ_ORDE for the order header, ZL84_REQ_REQUEST for the request line, and ZL84_REQ_WHT to map the warehouse task back to the Request ID.",
            "Review the Request Monitor state: O, P, S, and C progress only forward. A secondary level item can stage or close automatically, and a closed request cannot be cancelled.",
        ]
    if any(term in query for term in ("qa 007", "m7 042", "restricted batch", "expired sled", "batch status", "msc2n", "movement type 101")):
        return [
            "Confirm that the purchase order is released in ME29N, then review the material, vendor batch, date of manufacture, and shelf-life expiration date entered in MIGO.",
            "For QA 007, obtain the Quality decision before changing the restricted batch. Update MSC2N to Unrestricted only when QA has approved release.",
            "For M7 042 or an expired SLED, verify the threshold and correct the Date of Manufacture on the MIGO Batch tab where it was entered incorrectly.",
            "Repost the goods receipt and retain the PO, QA decision, batch-status evidence, shelf-life values, and material-document outcome for auditability.",
        ]
    if any(term in query for term in ("disposal", "dispose", "scrap", "scrapping", "retained sample", "expired material", "prt0-scrap", "scrap-zone", "movement type 551", "scwm/prdo", "zz1_disposal_days")):
        return [
            "Confirm the disposal date from the batch expiration date plus ZZ1_DISPOSAL_DAYS in MAT1 Warehouse Data, then review the Disposal Overview in Warehouse Management Monitor.",
            "Initiate the financial goods issue in ERP with MIGO using movement type 551 and the correct material and quantity. This should create the scrapping outbound delivery in EWM.",
            "Verify that the picking warehouse task is assigned to PRT0-SCRAP before the RF operator starts Outbound Processes and Picking by Queue.",
            "After the source HU is confirmed into the transport HU, confirm that the follow up warehouse task moves it from staging to SCRAP-ZONE. Different storage classes may be mixed only in this approved scrap queue.",
            "Complete the final goods issue in /SCWM/PRDO and retain the delivery, warehouse task, and disposal evidence for auditability.",
        ]
    if any(term in query for term in ("goods receipt", "hu pulling", "capacity", "bin capacity", "hu type", "chpd", "inbound delivery", "label printing", "transport hu")):
        return [
            "Confirm whether the material is EWM managed or requires Signals or Limfinity HU pulling. For HU pulling, use the external barcode so EWM can build the HU tree and create the RF warehouse task.",
            "For a capacity or bin proposal issue, verify that capacity checks are active for the storage type, product master capacity consumption is maintained, bin capacity is available, and the HU type is permitted.",
            "For standard receipt, physically verify the delivery, deconsolidate by temperature zone, create and label the HU, then assign it to a transport HU for the conveyor or lift to the primary area.",
            "In primary storage, use Putaway by HU and use CHPD only where an approved alternate bin is required. Goods receipt posts only after the destination warehouse task is confirmed.",
            "If cancelling an incomplete receipt, cancel every open warehouse task before rejecting the inbound delivery. Confirm hazardous storage attributes and label requirements before resuming processing.",
        ]
    if any(term in query for term in ("hp alm", "quality center", "test plan", "test set", "test run", "test lab", "req coverage", "requirement coverage")):
        return [
            "Confirm the correct domain first: FIXE for LAL, FPSEWD for BAU10, or MMMCLC for LAURA, then select the right testing folder.",
            "Create and name the test plan using the applicable convention; BAU10 unit testing is restricted to authorization changes, while SAT plans use the Change number and description.",
            "Assign the required Designer, L2 IT assessor, Validation, and any LAL Quality or LAURA business-assessor roles before linking applicable URS, FS, and TDS requirements.",
            "Define each design step with distinct expected and actual results, set Evidence Required to Y, and collect screenshots at the location required by the landscape.",
            "Move the plan and run through the controlled review and approval states; create a test set early if needed, but do not create a test run until the test plan is approved.",
            "After approval, update the related Change Request and close its testing task with the completed evidence and approvals.",
        ]
    if any(term in query for term in ("cc032", "change master", "aennr", "release key", "cc01", "cc02")):
        return [
            "Capture the Change Number AENNR, current release key, Valid-From date, error CC032, and any active-user evidence before changing the Engineering Change Master.",
            "Confirm whether the maintenance is blocked because the Valid-From date has not been reached, the Release Key remains Draft, or another user owns an exclusive session.",
            "For a confirmed stale user lock, obtain the required approval and have the Basis owner remove it in SM12. Do not clear an active change-maintenance lock.",
            "Open CC02 and set the Release Key only when the controlled approval route permits changes; adjust Valid-From only through approved engineering change control.",
            "Validate the controlled object change in CS02 or CV02N using the AENNR and retain the error, approval, release state, and post-change evidence.",
        ]
    if "plm" in query or any(term in query for term in ("recipe", "classification", "design bom")):
        return [
            "Confirm the affected recipe, specification, design BOM, material, approval step, and business release impact.",
            "Capture workflow timestamps, scheduler queue depth, failed payload identifiers, and the current approval state before any retry.",
            "Compare approved and deployed classification mappings, object types, class assignments, and material master destinations.",
            "Use approved change control before restarting a regulated workflow or deploying a mapping correction.",
            "Validate the correction in QA, then confirm the approval trail, classification result, and downstream planning outcome.",
        ]
    if any(term in query for term in ("smq1", "smq2", "sysfail", "activate queue", "reset status")):
        return [
            "Capture the SMQ1 or SMQ2 queue name, LUW error, destination, retry history, and any ST22 short dump before changing the queue state.",
            "Determine whether the SYSFAIL is caused by destination or network availability, a locked database object, or an uncaught ABAP dump. Resolve the underlying cause before retrying.",
            "If a confirmed stale lock is the blocker, verify ownership and data-integrity risk before the approved Basis owner uses SM12. Do not remove an active business lock.",
            "Use Debug Queue only when diagnosis requires it; then Reset Status and Activate Queue in SMQ1 or SMQ2. Confirm that the queue returns to RUNNING.",
            "Validate the downstream business outcome and record queue evidence, approvals, retry result, and any residual risk in the linked ServiceNow record.",
        ]
    if any(term in query for term in ("stms", "transport management", "transport request", "transport import", "tms promotion")):
        return [
            "Create or review the Workbench or Customizing transport in SE09 or SE10 and confirm the GxP naming standard, impacted objects, code-inspector checks, and unit-test evidence.",
            "Release underlying tasks first and then the main Transport Request. Preserve the release status and quality-gate evidence before promotion.",
            "Use STMS_IMPORT to select the RBS010 quality or testing queue, choose the approved transport, and apply the documented import options.",
            "Promote to RBS020 production only in the scheduled maintenance window after the formal Quality Lead sign-off and approved change record are in place.",
            "Validate the imported object, business process, and relevant integration after the import; record the transport return code, approver decision, and validation result in ServiceNow.",
        ]
    if "basis" in query or any(term in query for term in ("sm37", "transport", "stms", "spool", "gateway", "certificate", "su53", "smq1", "smq2", "sysfail", "st22", "sm12")):
        return [
            "Capture the job log, dump, transport return code, gateway evidence, or authorization trace before changing the technical state.",
            "Confirm whether the impact is isolated to a user, device, node, client, or target system.",
            "Check active locks, queue ownership, technical user access, and the approved rollback point with the relevant Basis owner.",
            "Use change control for production restarts, transports, certificate changes, or configuration updates.",
            "Validate one representative business process and record the approvals, timestamps, and evidence in the work notes.",
        ]
    if "mm" in query or any(term in query for term in ("purchase order", "po ", "supplier", "release strategy", "procurement")):
        return [
            "Confirm the purchase order or supplier record, release strategy, purchasing group, approver, plant, and business deadline.",
            "Preserve workflow logs, authorization evidence, change history, and interface payloads before retriggering approval.",
            "Check release prerequisites, blocked predecessor steps, supplier master mandatory attributes, and integration status.",
            "Use approved change control before altering production release configuration or supplier attributes.",
            "Validate approver visibility, document release, supplier result, downstream message, and requester confirmation.",
        ]
    return None


def _retrieved_knowledge_answer(query_text: str, chunks: list[dict[str, object]]) -> str | None:
    """Give a direct factual answer from a matching SUD when no playbook fits.

    The local model is intentionally optional. This keeps newly added knowledge
    useful in offline demo environments instead of collapsing to generic advice.
    """

    terms = _query_terms(query_text)
    best: tuple[int, str, list[str], str] | None = None
    for chunk in chunks:
        if chunk.get("record_type") != "knowledge":
            continue
        # Knowledge chunks contain source body plus a trailing tag line. Keep
        # the full body: source chunking no longer prepends a summary line.
        content = str(chunk.get("content", "")).split("Tags:", 1)[0].strip()
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
        scored_sentences = [
            (sum(term in sentence.casefold() for term in terms), index, sentence)
            for index, sentence in enumerate(sentences)
        ]
        ranked = sorted(
            scored_sentences,
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] <= 0:
            continue
        _, first_index, _ = ranked[0]
        # Use the strongest source sentence only. Broad terms such as
        # “inbound” occur throughout a runbook and made a neighbouring-window
        # approach append unrelated QID or queue procedures to one error fix.
        matched = [sentences[first_index]]
        if matched and (best is None or ranked[0][0] > best[0]):
            best = (ranked[0][0], str(chunk.get("title", "internal procedure")), matched, str(chunk.get("id", "")))
    if not best:
        return None
    _, title, sentences, source_chunk_id = best

    broad_procedure = (
        _is_knowledge_procedure_request(query_text)
        and not _has_specific_troubleshooting_signal(query_text)
        and not _explicit_ticket_numbers(query_text)
    )
    if broad_procedure and ":chunk:" in source_chunk_id:
        # Parent-document expansion: vector search chooses the relevant
        # document chunk, then the canonical siblings restore its complete
        # controlled procedure in source order. This avoids relying on a
        # fragile top-k ordering for long regulated SOPs.
        source_prefix = source_chunk_id.rsplit(":chunk:", 1)[0]
        source_chunks = [
            document for document in build_retrieval_documents()
            if document.id.startswith(f"{source_prefix}:chunk:")
        ]
        source_chunks.sort(key=lambda document: int(document.id.rsplit(":chunk:", 1)[1]))
        seen_sentences: set[str] = set()
        expanded: list[str] = []
        for document in source_chunks:
            content = document.content.split("Tags:", 1)[0]
            for sentence in re.split(r"(?<=[.!?])\s+", content):
                normalized = sentence.strip()
                identity = normalized.casefold()
                if normalized and identity not in seen_sentences:
                    seen_sentences.add(identity)
                    expanded.append(normalized)
        if expanded:
            return "\n".join([
                title,
                "",
                "Complete procedure",
                *[f"{index}. {sentence.rstrip('.')}." for index, sentence in enumerate(expanded, start=1)],
            ])

    steps: list[str] = []
    for sentence in sentences:
        # Semicolons commonly separate the individual execution actions in
        # the curated SUDs. Retain full sentences otherwise, so the formatter
        # works for every connector without source-specific hardcoding.
        fragments = [fragment.strip(" ,") for fragment in re.split(r";\s+", sentence) if fragment.strip(" ,")]
        for fragment in fragments:
            steps.extend(
                piece.strip(" ,")
                for piece in re.split(
                    r",\s+(?=(?:verify|resynchronise|calculate|save|retry|record|inspect|confirm|validate|create|update|use|open|set|adjust|activate|resolve|capture|repost)\b)",
                    fragment,
                    flags=re.IGNORECASE,
                )
                if piece.strip(" ,")
            )
    normalised_steps = [step[:1].upper() + step[1:] if step else step for step in steps]
    return "\n".join([
        title,
        "",
        "Recommended steps",
        *[f"{index}. {step.rstrip('.')}." for index, step in enumerate(normalised_steps, start=1)],
    ])


def _has_authoritative_playbook(query_text: str) -> bool:
    """Keep high-confidence SOP routes deterministic when running without Gemini.

    A very small keyless model is useful for open-ended language, but it should
    never replace a precise, validated LEAP procedure with a weaker paraphrase.
    """

    return (
        _has_specific_troubleshooting_signal(query_text)
        or _is_ewm_queue_lock_question(query_text)
        or _topic_action_items(query_text) is not None
    )


def _local_answer(query_text: str, chunks: list[dict[str, object]]) -> str:
    if not chunks:
        return (
            "I could not find a matching live ticket, calculated metric, or approved enterprise document for that question. "
            "Try a ticket number, an assignee or assignment-group name, or a specific SAP process such as EWM goods receipt, Request Hub, or HP ALM testing."
        )

    # Error-code and troubleshooting requests are the highest priority. They
    # must be sourced from vector-retrieved SUD content, not from a generic
    # queue or goods-receipt template.
    if _has_specific_troubleshooting_signal(query_text):
        knowledge_answer = _retrieved_knowledge_answer(query_text, chunks)
        if knowledge_answer:
            return knowledge_answer

    if _is_how_to_question(query_text) and _is_ewm_queue_lock_question(query_text):
        return (
            "Here is a safe, controlled way to work through an EWM qRFC queue lock. "
            "\n\n"
            "1. Start by confirming the affected warehouse process, queue, business impact, and the approved incident or change record.\n"
            "2. In SM12, identify the lock owner, client, object, and lock age. Capture evidence first; do not delete a lock until active ownership is understood.\n"
            "3. Inspect SMQ1 for outbound queue status, destination, LUW error text, and retry history. Then inspect SMQ2 for inbound blocks or predecessor queues.\n"
            "4. Coordinate any approved unlock or controlled restart with EWM, Basis, and middleware. Keep a rollback and escalation route available.\n"
            "5. Validate queue drain, warehouse task creation, goods issue posting, and that the lock does not return. Document business confirmation and validation evidence."
        )

    topic_actions = _topic_action_items(query_text)
    if topic_actions:
        return _format_procedure_answer(query_text, topic_actions, chunks)

    knowledge_answer = _retrieved_knowledge_answer(query_text, chunks)
    if knowledge_answer:
        return knowledge_answer

    if _is_analysis_or_resolution_request(query_text):
        evidence_titles = [str(chunk.get("title", "")) for chunk in chunks[:3] if chunk.get("title")]
        return (
            "I found related operational evidence, but no approved source contains an exact resolution procedure for this wording. "
            f"The closest evidence is {', '.join(evidence_titles) or 'the current ATLAS repository'}. "
            "Ask for the named process, service, ticket, or error signature to receive a grounded next step."
        )
    return (
        "I found related ATLAS evidence, but it does not contain a direct answer to that wording. "
        "Ask for a specific ticket, team, assignment group, metric, document topic, or SAP process and I will use the matching live records."
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


def _add_natural_source_attribution(answer: str, chunks: list[dict[str, object]], query_text: str) -> str:
    """Keep source lineage visible in prose without adding UI cards or raw IDs."""

    knowledge_chunks = [chunk for chunk in chunks if chunk.get("record_type") == "knowledge"]
    for chunk in knowledge_chunks:
        title = str(chunk.get("title", "")).strip()
        if title and title.casefold() in answer.casefold():
            return answer
    if knowledge_chunks:
        # Deterministic procedure routes can be more precise than the first
        # vector hit. Select the matching canonical title for the citation.
        query = query_text.casefold()
        title_hint = (
            "goods receipt" if _is_goods_receipt_question(query_text)
            else "transport management" if any(term in query for term in ("stms", "transport", "tms"))
            else "engineering change" if any(term in query for term in ("cc032", "aennr", "change master", "cc01", "cc02"))
            else "procurement goods" if any(term in query for term in ("migo", "qa 007", "m7 042", "msc2n"))
            else "change management" if _is_servicenow_change_management_question(query_text)
            else ""
        )
        chunk = next(
            (candidate for candidate in knowledge_chunks if title_hint and title_hint in str(candidate.get("title", "")).casefold()),
            knowledge_chunks[0],
        )
        title = str(chunk.get("title", "")).strip()
        system = str(chunk.get("system", "enterprise knowledge base")).strip()
        if title:
            source_id = str(chunk.get("id", "")).removeprefix("source:")
            return f"{answer.rstrip()}\n\nSource: [{system}] {source_id} — {title} ↗"
    return answer


def _journal_value(entry: Any) -> tuple[str, str, str]:
    """Extract only display-safe journal data from Pydantic, dict, or string input."""

    if isinstance(entry, str):
        return "", "", entry.strip()
    if isinstance(entry, dict):
        return (
            str(entry.get("sys_created_on") or entry.get("timestamp") or "").strip(),
            str(entry.get("sys_created_by") or entry.get("author") or "").strip(),
            str(entry.get("value") or entry.get("text") or "").strip(),
        )
    return (
        str(getattr(entry, "sys_created_on", "") or getattr(entry, "timestamp", "")).strip(),
        str(getattr(entry, "sys_created_by", "") or getattr(entry, "author", "")).strip(),
        str(getattr(entry, "value", "") or getattr(entry, "text", "")).strip(),
    )


def _latest_journal_lines(entries: list[Any] | None, *, limit: int = 3, empty_label: str) -> list[str]:
    """Return the most recent human-readable journal entries, newest first."""

    normalized = [_journal_value(entry) for entry in (entries or [])]
    normalized = [entry for entry in normalized if entry[2]]
    normalized.sort(key=lambda entry: entry[0], reverse=True)
    if not normalized:
        return [empty_label]
    lines = []
    for created_on, author, value in normalized[:limit]:
        prefix = " · ".join(part for part in (created_on, author) if part)
        lines.append(f"- {prefix + ': ' if prefix else ''}{value}")
    return lines


def _sla_summary(ticket: Any) -> str:
    """Create a compact canonical SLA label without null fields or aliases."""

    remaining = getattr(ticket, "sla_time_remaining", None)
    if remaining is None:
        return "Not SLA-tracked"
    health = str(getattr(ticket, "sla_health", "") or getattr(ticket, "sla_status", "") or "Unknown")
    if bool(getattr(ticket, "is_breached", False)) or remaining <= 0:
        return f"Breached ({abs(remaining)}m overdue)"
    return f"{health} ({remaining}m remaining)"


def _single_ticket_deep_dive(
    ticket: Any,
    *,
    include_description: bool = False,
    include_journals: bool = False,
) -> str:
    """Return only the ticket fields needed for the user's stated lookup."""

    fields = (
        ("Number", getattr(ticket, "number", "")),
        ("Short description", getattr(ticket, "short_description", "")),
        ("Priority", getattr(ticket, "priority", "")),
        ("State", getattr(ticket, "state", "")),
        ("Assignee", getattr(ticket, "assigned_to", "") or getattr(ticket, "assignee", "")),
        ("Caller", getattr(ticket, "caller_id", "") or getattr(ticket, "requested_for", "")),
        ("SLA status", _sla_summary(ticket)),
    )
    lines = ["## Canonical ticket deep dive"]
    lines.extend(f"{label}: {value}" for label, value in fields if value not in (None, "", [], {}))
    if include_description and getattr(ticket, "description", ""):
        lines.append(f"Description: {ticket.description}")
    if include_journals:
        lines.append("### Three most recent work notes")
        lines.extend(_latest_journal_lines(getattr(ticket, "work_notes", None), empty_label="- No work notes recorded."))
        lines.append("### Three most recent comments")
        lines.extend(_latest_journal_lines(getattr(ticket, "comments", None), empty_label="- No comments recorded."))
    return "\n".join(lines)


def _ticket_queue_summary(tickets: list[Any], *, label: str) -> str:
    """Bound queue context to five dense, four-line ServiceNow summaries."""

    if not tickets:
        return f"{label}: no matching canonical ServiceNow records were found."
    lines = [f"{label}: {len(tickets)} matching canonical ServiceNow record(s); first {min(5, len(tickets))} shown for generation."]
    for index, ticket in enumerate(tickets[:5], start=1):
        work_note = _latest_journal_lines(
            getattr(ticket, "work_notes", None), limit=1, empty_label="No work note recorded."
        )[0].removeprefix("- ")
        lines.extend((
            f"{index}. {ticket.number} — {ticket.short_description}",
            f"   Priority: {ticket.priority} | State: {ticket.state} | Assignee: {ticket.assigned_to or ticket.assignee or 'Unassigned'}",
            f"   SLA: {_sla_summary(ticket)}",
            f"   Latest work note: {work_note}",
        ))
    if len(tickets) > 5:
        lines.append(f"{len(tickets) - 5} additional matching records are intentionally omitted from context to stay within the CPU generation budget.")
    return "\n".join(lines)


def _operational_ticket_context(
    tickets: list[Any],
    *,
    label: str,
    deep_dive: bool = False,
    include_description: bool = False,
    include_journals: bool = False,
) -> str:
    """Serialize canonical records as bounded grounding context, never as a response."""

    if deep_dive:
        return _single_ticket_deep_dive(
            tickets[0],
            include_description=include_description,
            include_journals=include_journals,
        ) if tickets else f"{label}: no matching canonical ServiceNow record was found."
    return _ticket_queue_summary(tickets, label=label)


def _deterministic_failure_response(query_text: str, chunks: list[dict[str, object]], operational_context: str) -> str:
    """Last-resort response; callers use this only after generation fails."""

    base = _local_answer(query_text, chunks)
    if operational_context:
        return f"The generation service is temporarily unavailable. Retrieved operational context:\n\n{operational_context}\n\n{base}"
    return base



def _is_brief_operational_lookup(query_text: str) -> bool:
    """Identify only the short operational lookups eligible for the small tier."""

    query = query_text.casefold()
    # Any request for reasoning, an authored deliverable, or implementation
    # guidance is full-budget by default, even when it mentions a ticket/SLA.
    if re.search(
        r"\b(?:fds|functional\s+design|ricefw|hp\s*alm|test\s*case|rca|root\s*cause|sop|runbook|"
        r"procedure|troubleshoot(?:ing)?|technical|architect(?:ure|ural)?|explain|why|how\s+(?:does|do|to)|"
        r"design|implement|steps?|recommend|analysis)\b",
        query,
    ):
        return False

    status_field = r"(?:status|state|update|priority|sla(?:\s+(?:status|health))?)"
    ticket_lookup = bool(_explicit_ticket_numbers(query_text)) and bool(re.search(rf"\b{status_field}\b", query))
    assignee_lookup = bool(re.search(r"\b(?:assignee|assigned\s+to)\b", query)) and bool(re.search(rf"\b{status_field}\b", query))
    basic_metric_lookup = bool(re.search(r"\b(?:metric|metrics|kpi|stats?|count|total|how\s+many|number\s+of)\b", query))
    return ticket_lookup or assignee_lookup or basic_metric_lookup


def _generation_token_budget(query_text: str) -> int:
    """Use 350 tokens only for explicit brief lookups; default everything else to 2,048."""

    full_budget = max(350, int(os.getenv("ATLAS_OLLAMA_MAX_TOKENS", "2048")))
    brief_budget = min(full_budget, max(1, int(os.getenv("ATLAS_OLLAMA_STANDARD_MAX_TOKENS", "350"))))
    return brief_budget if _is_brief_operational_lookup(query_text) else full_budget


def prepare_hybrid_rag(query_text: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Prepare one read-only RAG execution plan for JSON or SSE delivery."""

    dashboard_filters = _dashboard_query_filters(query_text)
    metrics_requested = _is_metrics_intent(query_text)
    fds_requested = _is_fds_generation_request(query_text)
    # Metrics are already fully grounded in the canonical Stats aggregation;
    # three retrieval chunks are enough for an optional natural-language
    # explanation, while procedural requests retain deeper evidence.
    retrieval_limit = 3 if metrics_requested else 8 if fds_requested else 5 if _is_knowledge_procedure_request(query_text) else 4
    chunks = retrieve_vector_context(query_text, limit=retrieval_limit)
    direct_ticket_ids = _explicit_ticket_numbers(query_text)
    direct_tickets = [
        ticket for ticket_id in direct_ticket_ids
        if (ticket := central_ticket_records().get(ticket_id)) is not None
    ]
    assignees = _mentioned_assignees(query_text)
    groups = _mentioned_assignment_groups(query_text)
    modules = _requested_sap_modules(query_text)
    queue_language = bool(re.search(r"\b(?:tickets?|incidents?|requests?|problems?|changes?|queue|work items?|records?|workload)\b", query_text.casefold()))
    filter_present = any((
        dashboard_filters["modules"], dashboard_filters["groups"], dashboard_filters["assignees"],
        dashboard_filters["record_types"], dashboard_filters["states"], dashboard_filters["hold_reasons"],
        dashboard_filters["priority_ranks"], dashboard_filters["sla_mode"],
    ))

    scoped_tickets: list[Any] = list(direct_tickets)
    if not scoped_tickets and (queue_language or filter_present) and (filter_present or assignees or groups or modules):
        scoped_tickets, _ = _dashboard_filtered_tickets(query_text)

    sla_visual_requested = _is_sla_health_question(query_text) or str(dashboard_filters["sla_mode"]) in {"at_risk", "breached", "on_track", "non_breached"}
    stats_context: str | None = None
    chart_data: dict[str, object] | None = None
    metric_answer: str | None = None
    if metrics_requested:
        live_stats = _live_stats_snapshot(query_text, active_only=True)
        stats_context = _stats_context_block(live_stats)
        # Numerical analytics are a calculation, not a generative task. Use
        # the exact canonical aggregation for their concise chat copy so the
        # text and chart can never disagree and KPI questions return without
        # waiting on local CPU inference.
        metric_answer, _ = _stats_answer(query_text, live_stats, stats_context)
        if sla_visual_requested:
            chart_data = _stats_chart_payload(live_stats)

    # A KPI question is grounded by the canonical Stats snapshot. Adding five
    # queue cards to that same prompt costs CPU tokens and can distract a
    # compact local model from the exact totals. Preserve ticket context for
    # explicit ticket references and for requests that actually ask to list
    # or inspect the matching records.
    include_ticket_context = bool(direct_tickets) or not metrics_requested or bool(dashboard_filters.get("asks_for_details"))
    query = query_text.casefold()
    ticket_context = _operational_ticket_context(
        scoped_tickets,
        label="Exact ticket match" if direct_tickets else "Live canonical queue filter",
        deep_dive=bool(direct_tickets),
        include_description=bool(re.search(r"\b(?:description|details?|what(?:'s| is) happening|explain)\b", query)),
        include_journals=bool(re.search(r"\b(?:journal|comment|work notes?|history|latest update)\b", query)),
    ) if scoped_tickets and include_ticket_context else ""
    operational_context = "\n\n".join(part for part in (stats_context, ticket_context) if part)
    fds_context = _fds_standard_context() if fds_requested else ""
    prompt = _local_generation_prompt(
        query_text,
        chunks,
        operational_context=operational_context,
        history=history,
        fds_standard_context=fds_context,
    )

    ticket_ids: list[str] = []
    for chunk in chunks:
        ticket_id = str(chunk.get("ticket_id") or chunk.get("ticket_number") or "").upper()
        if ticket_id in central_ticket_records() and ticket_id not in ticket_ids:
            ticket_ids.append(ticket_id)
    for ticket in scoped_tickets:
        if ticket.number not in ticket_ids:
            ticket_ids.append(ticket.number)

    intent = "functional_design_generation" if fds_requested else "direct_ticket" if direct_tickets else "live_ticket_context" if scoped_tickets else "live_stats_context" if metrics_requested else "vector_grounded_rag"
    generation_max_tokens = _generation_token_budget(query_text)
    return {
        "query_text": query_text,
        "chunks": chunks,
        "prompt": prompt,
        "system_prompt": _synthesis_system_prompt(
            metric_mode=metrics_requested,
            concise=generation_max_tokens <= 350,
            fds_mode=fds_requested,
        ),
        "max_tokens": generation_max_tokens,
        "operational_context": operational_context,
        "ticket_ids": ticket_ids,
        "intent": intent,
        "listed_ticket_ids": [ticket.number for ticket in scoped_tickets],
        "stats_context": stats_context,
        "metric_answer": metric_answer,
        "chart_data": chart_data,
        "fds_standard_context": fds_context,
        "sources": _sources(chunks),
        "retrieval": [{key: value for key, value in chunk.items() if key != "content"} for chunk in chunks],
        "retrieval_route": "vector_plus_live_context" if operational_context else "vector_grounded_rag" if chunks else "general_reasoning",
    }


def hybrid_rag_metadata(plan: dict[str, Any]) -> dict[str, Any]:
    """Return response metadata before a streaming generation begins."""

    return {
        "max_tokens": plan["max_tokens"],
        "sources": plan["sources"],
        "embedding_model": VECTOR_STORE.status()["embedding_model"],
        "retrieval_route": plan["retrieval_route"],
        "retrieval": plan["retrieval"],
        "ticket_ids": plan["ticket_ids"],
        "intent": plan["intent"],
        "listed_ticket_ids": plan["listed_ticket_ids"],
        "stats_context": plan["stats_context"],
        "chart_data": plan["chart_data"],
    }


async def stream_hybrid_rag(plan: dict[str, Any]):
    """Yield model deltas; leave transport framing to the FastAPI route."""

    if plan.get("metric_answer"):
        yield {
            "type": "token",
            "content": str(plan["metric_answer"]),
            "model_used": "canonical-live-analytics",
        }
        return

    try:
        async for content, model in OLLAMA_GENERATOR.stream_generate(
            system_prompt=str(plan["system_prompt"]),
            user_prompt=str(plan["prompt"]),
            max_tokens=int(plan["max_tokens"]),
        ):
            yield {"type": "token", "content": content, "model_used": f"ollama:{model}"}
    except OllamaStreamError as error:
        # A generated fallback remains read-only and is intentionally sent as
        # a token after an error event, keeping the SSE connection usable.
        yield {"type": "error", "message": "Local generation is temporarily unavailable.", "detail": str(error)}
        yield {
            "type": "token",
            "content": _deterministic_failure_response(
                str(plan["query_text"]), list(plan["chunks"]), str(plan["operational_context"])
            ),
            "model_used": "ollama-unavailable",
        }


async def query_hybrid_rag(query_text: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Ground every query, then send every healthy request to Ollama."""

    plan = prepare_hybrid_rag(query_text, history)
    if plan.get("metric_answer"):
        return {
            "answer": str(plan["metric_answer"]),
            **hybrid_rag_metadata(plan),
            "model_used": "canonical-live-analytics",
            "fallback_reasoning": False,
        }
    generated, model = await OLLAMA_GENERATOR.generate(
        system_prompt=str(plan["system_prompt"]),
        user_prompt=str(plan["prompt"]),
        max_tokens=int(plan["max_tokens"]),
    )
    engine_failed = not bool(generated)
    if generated:
        answer = generated
        model_used = f"ollama:{model}"
    elif gemini_client is not None:
        # Optional secondary engine, preserved for configured deployments. It
        # is attempted only after the local Ollama execution path fails.
        try:
            fallback = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model=GENERATION_MODEL,
                contents=f"{plan['system_prompt']}\n\n{plan['prompt']}",
            )
            if fallback.text:
                answer = fallback.text
                model_used = GENERATION_MODEL
                engine_failed = False
            else:
                answer = _deterministic_failure_response(query_text, list(plan["chunks"]), str(plan["operational_context"]))
                model_used = "ollama-unavailable"
        except Exception:
            answer = _deterministic_failure_response(query_text, list(plan["chunks"]), str(plan["operational_context"]))
            model_used = "ollama-unavailable"
    else:
        answer = _deterministic_failure_response(query_text, list(plan["chunks"]), str(plan["operational_context"]))
        model_used = "ollama-unavailable"

    return {
        "answer": answer,
        **hybrid_rag_metadata(plan),
        "model_used": model_used,
        "fallback_reasoning": engine_failed,
    }


def rag_status() -> dict[str, object]:
    """Operational status for local vector retrieval and connector readiness."""

    initialize_vector_db()
    return {
        "vector_store": VECTOR_STORE.status(),
        "connectors": connector_statuses(),
        "generation": {
            "primary_provider": "Ollama local daemon",
            "ollama": OLLAMA_GENERATOR.status(),
            "gemini_configured": gemini_client is not None,
            "gemini_api_key_environment": "GEMINI_API_KEY",
            "gemini_model": GENERATION_MODEL,
            "fallback": "deterministic-grounded-synthesis",
        },
    }


# Compatibility aliases for older endpoints and integrations.
query_chatgpt_rag = query_hybrid_rag
retrieve_multi_tool_context = retrieve_vector_context
