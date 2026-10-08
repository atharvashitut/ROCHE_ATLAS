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
        if len(selected) >= 6:
            break
        payload = serialize_retrieved(RetrievedDocument(document, min(1.0, lexical_hits / max(1, len(terms)))))
        payload["lexical_hits"] = lexical_hits
        selected.append(payload)
        selected_ids.add(document.id)
    for result in VECTOR_STORE.query(query_text, limit=limit):
        if len(selected) >= 6:
            break
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
        "You are Roche ATLAS, a thoughtful ITIL L2/L3 co-pilot speaking with an engineer. "
        "Answer only from the internal evidence below, but sound natural and collaborative rather than like a field dump or API response. "
        "For a general troubleshooting or how-to question, begin with a short direct answer, then give a safe, numbered, step by step path. "
        "For an analysis or resolution request, organise the answer as Situation, Key risks or blockers, and Recommended actions with numbered steps. "
        "Call out approval, GxP, rollback, or escalation gates when the evidence requires them. "
        "For a specific ticket, explain in plain English what is happening, why it matters, what is currently blocking progress, and the best next move. "
        "Do not recite raw labels, every field, or JSON-style key/value data. Use short headings and numbered action items. Never use hyphen characters as list markers or separators. Use citations inline as [id], and mention that the linked source cards contain the documents. "
        "Do not invent source details.\n\n"
        f"Question: {query_text}\n\nLive ServiceNow ticket state from MOCK_DB:\n{live_context}\n\nEnterprise evidence:\n{excerpts}"
    )


def _fallback_prompt(query_text: str) -> str:
    return (
        "No relevant internal enterprise evidence was retrieved. You are the Roche ATLAS ITIL L2/L3 Co-Pilot. "
        "Respond conversationally: acknowledge the question, provide a labelled diagnostic hypothesis, safe evidence collection steps, a rollback-aware investigation plan, and escalation criteria. "
        "Do not claim internal documents support the answer.\n\n"
        f"Question: {query_text}"
    )


def _is_how_to_question(query_text: str) -> bool:
    return bool(re.search(r"\b(how|fix|resolve|recover|clear|troubleshoot|steps?|guide)\b", query_text.casefold()))


def _is_analysis_or_resolution_request(query_text: str) -> bool:
    return _is_how_to_question(query_text) or bool(
        re.search(r"\b(analyse|analyze|analysis|resolution|root cause|recommend|what should|next steps?)\b", query_text.casefold())
    )


def is_active_ticket_list_request(query_text: str) -> bool:
    """Identify requests for an operational queue rather than one ticket."""

    query = query_text.casefold()
    asks_for_tickets = bool(re.search(r"\b(tickets?|incidents?|queue|work items?)\b", query))
    asks_for_current_state = bool(re.search(r"\b(current|ongoing|open|active|today)\b", query))
    return asks_for_tickets and asks_for_current_state


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


def _active_ticket_list(query_text: str) -> list[Any]:
    closed_states = {"Resolved", "Closed", "Closed Complete", "Closed Incomplete", "Closed Skipped", "Canceled"}
    requested_modules = _requested_sap_modules(query_text)
    tickets = [ticket for ticket in central_ticket_records().values() if ticket.state not in closed_states]
    if requested_modules:
        tickets = [ticket for ticket in tickets if requested_modules.intersection(ticket.sap_modules)]
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
    lines = [f"Current {scope} tickets", f"I found {len(tickets)} active record{'s' if len(tickets) != 1 else ''}.", ""]
    for index, ticket in enumerate(tickets, start=1):
        hold_reason = getattr(ticket, "hold_reason", None) if ticket.state == "On Hold" else None
        status = f"State: {ticket.state}. Team: {ticket.assignment_group}."
        if hold_reason:
            status += f" Waiting on {hold_reason}."
        lines.extend([
            f"{index}. {ticket.number}  {ticket.short_description}",
            f"   {status}",
        ])
    lines.extend(["", "Tell me a ticket number if you want a focused explanation or resolution plan for one of these records."])
    return "\n".join(lines), [ticket.number for ticket in tickets]


def _is_ewm_queue_lock_question(query_text: str) -> bool:
    query = query_text.casefold()
    return "ewm" in query and any(term in query for term in ("qrfc", "queue lock", "queue", "sm12", "smq1", "smq2"))


def _citation_ids(chunks: list[dict[str, object]], limit: int = 4) -> str:
    return " ".join(f"[{chunk['id']}]" for chunk in chunks[:limit])


def _topic_action_items(query_text: str) -> list[str] | None:
    """Return concise local guidance for the high-value SAP support domains."""

    query = query_text.casefold()
    if "plm" in query or any(term in query for term in ("recipe", "classification", "design bom")):
        return [
            "Confirm the affected recipe, specification, design BOM, material, approval step, and business release impact.",
            "Capture workflow timestamps, scheduler queue depth, failed payload identifiers, and the current approval state before any retry.",
            "Compare approved and deployed classification mappings, object types, class assignments, and material master destinations.",
            "Use approved change control before restarting a regulated workflow or deploying a mapping correction.",
            "Validate the correction in QA, then confirm the approval trail, classification result, and downstream planning outcome.",
        ]
    if "basis" in query or any(term in query for term in ("sm37", "transport", "stms", "spool", "gateway", "certificate", "su53")):
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


def _local_answer(query_text: str, chunks: list[dict[str, object]]) -> str:
    if not chunks:
        return (
            "I do not see an internal procedure that directly covers this yet, but we can still approach it safely.\n\n"
            "Recommended actions\n"
            "1. Confirm the impact, scope, timestamps, recent changes, and a known good comparison path.\n"
            "2. Preserve logs, monitoring signals, and correlation IDs before any retry or restart.\n"
            "3. Check the owning service, dependencies, rollback route, and change control requirements.\n"
            "4. Escalate with the collected evidence and keep the requester updated in the ServiceNow journal."
        )

    citations = _citation_ids(chunks)
    if _is_how_to_question(query_text) and _is_ewm_queue_lock_question(query_text):
        return (
            "Yes. Here is a safe, controlled way to work through an EWM qRFC queue lock. "
            f"The linked source cards contain the approved detail. {citations}\n\n"
            "Recommended actions\n"
            "1. Start by confirming the affected warehouse process, queue, business impact, and the approved incident or change record.\n"
            "2. In SM12, identify the lock owner, client, object, and lock age. Capture evidence first; do not delete a lock until active ownership is understood.\n"
            "3. Inspect SMQ1 for outbound queue status, destination, LUW error text, and retry history. Then inspect SMQ2 for inbound blocks or predecessor queues.\n"
            "4. Coordinate any approved unlock or controlled restart with EWM, Basis, and middleware. Keep a rollback and escalation route available.\n"
            "5. Validate queue drain, warehouse task creation, goods issue posting, and that the lock does not return. Document business confirmation and validation evidence."
        )

    source_titles = "; ".join(str(chunk["title"]) for chunk in chunks[:3])
    if _is_analysis_or_resolution_request(query_text):
        topic_actions = _topic_action_items(query_text)
        actions = topic_actions or [
            "Confirm the exact scope and preserve the current error evidence.",
            "Follow the source specific diagnostic or recovery procedure with the owning team before changing production state.",
            "Validate the business outcome, record the evidence, and update the ServiceNow journal with the result.",
        ]
        return (
            "I found internal guidance that is relevant to this. Let’s take the controlled path rather than making a blind retry.\n\n"
            f"Useful references\n{source_titles}\n{citations}\n\n"
            "Recommended actions\n"
            + "\n".join(f"{index}. {action}" for index, action in enumerate(actions, start=1))
        )
    return (
        "I found relevant internal context for that question.\n\n"
        "Recommended actions\n"
        "1. Review the current service evidence and latest human update.\n"
        "2. Follow the controlled procedure before changing production state.\n"
        "3. Capture confirmation before closure.\n\n"
        f"Supporting sources\n{citations}\n\n"
        "Tell me whether you are diagnosing, planning a change, or validating recovery and I can narrow this to the exact next checks."
    )


def compose_conversational_ticket_response(ticket: Any, query_text: str, grounded_answer: str) -> str:
    """Turn a live ServiceNow record into a readable co-pilot update.

    The ticket is already hydrated from the canonical repository. This keeps
    specific-ticket chat answers current without turning the response into a
    raw schema dump.
    """

    latest_comment = ticket.comments[-1].value if ticket.comments else "there is no recent customer-visible journal update"
    hold_reason = getattr(ticket, "hold_reason", None) if ticket.state == "On Hold" else None
    situation = f"{ticket.short_description} is the main issue."
    if hold_reason:
        situation += f" Progress is currently paused because the record is waiting on {hold_reason.lower()}."
    elif ticket.state in {"Resolved", "Closed", "Closed Complete"}:
        situation += " The record is in a closure-oriented state, so the focus is on confirming the business outcome and evidence."
    else:
        situation += " The support team is actively working the recovery path."
    next_move = (ticket.ai_resolution_guide or "Validate the current evidence, coordinate the owning team, and confirm the outcome with the requester.").split(". ")[0].rstrip(".")
    return (
        f"Ticket overview\n{ticket.number}\n\n"
        f"What is happening\n{situation}\n\n"
        f"Latest update\n{latest_comment}\n\n"
        "Recommended actions\n"
        f"1. {next_move}.\n"
        "2. Confirm the current business impact and any dependency with the owning team.\n"
        "3. Validate the outcome with the requester and record the evidence before closure.\n\n"
        "Grounded guidance\n"
        f"{grounded_answer}\n\n"
        "Open the source cards below for the supporting procedures and evidence."
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
    ticket_list_intent = is_active_ticket_list_request(query_text)
    listed_ticket_ids: list[str] = []
    if ticket_list_intent:
        answer, listed_ticket_ids = _active_ticket_list_answer(query_text)
    else:
        answer = _local_answer(query_text, chunks)
    model_used = "local-grounded-fallback"
    if gemini_client is not None and not ticket_list_intent:
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
        "intent": "active_ticket_list" if ticket_list_intent else "conversational_guidance",
        "listed_ticket_ids": listed_ticket_ids,
    }


def rag_status() -> dict[str, object]:
    """Operational status for local vector retrieval and connector readiness."""

    initialize_vector_db()
    return {
        "vector_store": VECTOR_STORE.status(),
        "connectors": connector_statuses(),
        "generation": {
            "provider": "Google Gemini",
            "configured": gemini_client is not None,
            "api_key_environment": "GEMINI_API_KEY",
            "model": GENERATION_MODEL,
            "fallback": "local-grounded-fallback",
        },
    }


# Compatibility aliases for older endpoints and integrations.
query_chatgpt_rag = query_hybrid_rag
retrieve_multi_tool_context = retrieve_vector_context
