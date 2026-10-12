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

# Importing models registers the canonical in-memory ServiceNow catalog with
# CentralTicketRepository.  This keeps RAG usable when this module is invoked
# directly (for example from a worker or a smoke test), rather than only after
# FastAPI has imported `main`.
from .models import MOCK_DB  # noqa: F401
from .central_db import central_ticket_by_reference, central_ticket_records
from .connectors import connector_documents, connector_statuses
from .local_llm import LOCAL_OPEN_SOURCE_GENERATOR
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


def warm_local_generation() -> None:
    """Warm cached local weights after startup without delaying API availability."""

    if gemini_client is None:
        LOCAL_OPEN_SOURCE_GENERATOR.warm_up()


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
    ticket_status = is_ticket_status_request(query_text)
    intent_instruction = (
        "The user explicitly requested a ticket update. Explain that ticket's current situation, impact, latest human update, and next best action in plain English. "
        if ticket_status else
        "This is a general question or SOP request. Answer only what the user asked in plain conversational English or simple numbered steps. "
        "Do not use Ticket overview, What is happening, Latest update, or Recommended actions headings. "
    )
    return (
        "You are ATLAS, an expert SAP Copilot. Answer only what the user specifically asks. "
        "Reply in the same language as the user whenever the configured model can do so. Speak naturally in plain text paragraphs or simple numbered lists. Do not use generic ticket headers or structural templates unless the user asked for a ticket status. "
        "Answer only from the internal evidence below, and do not sound like a field dump or API response. "
        f"{intent_instruction}"
        "Call out approval, GxP, rollback, or escalation gates only when the evidence requires them. "
        "Do not recite raw labels, every field, or JSON-style key/value data. Never use hyphen characters as list markers or separators. "
        "When a source is relevant, mention its title naturally in the sentence rather than outputting source IDs, URLs, or UI instructions. Do not invent source details.\n\n"
        f"Question: {query_text}\n\nLive ServiceNow ticket state from MOCK_DB:\n{live_context}\n\nEnterprise evidence:\n{excerpts}"
    )


def _fallback_prompt(query_text: str) -> str:
    return (
        "No relevant internal enterprise evidence was retrieved. You are ATLAS, an expert SAP Copilot. "
        "Answer only what the user specifically asks in plain conversational English or simple numbered steps. "
        "Do not use generic ticket headers or structural templates unless the user asked for a ticket status. "
        "Provide a safe diagnostic hypothesis, evidence collection steps, a rollback-aware investigation plan, and escalation criteria when relevant. "
        "Do not claim internal documents support the answer.\n\n"
        f"Question: {query_text}"
    )


def _local_generation_prompt(query_text: str, chunks: list[dict[str, object]]) -> str:
    """Keep local CPU generation focused enough to meet the Chat response budget."""

    # Keep CPU inference practical inside the protected interactive budget.
    # The complete vector evidence remains available to the deterministic
    # synthesizer; the optional local model receives only the two strongest
    # compact excerpts.
    evidence = "\n\n".join(
        f"{chunk['title']} ({chunk['system']}): {str(chunk['content'])[:360]}"
        for chunk in chunks[:2]
    )
    live_context = _live_ticket_context(chunks[:1])[:360]
    ticket_status = is_ticket_status_request(query_text)
    intent_instruction = (
        "The user asked for a ticket update; give only the relevant current status, latest update, and next action. "
        if ticket_status else
        "This is a general question; answer directly without Ticket overview, What is happening, Latest update, or Recommended actions headings. "
    )
    return (
        "You are ATLAS, an expert SAP Copilot. Answer only the user's question from this small set of ATLAS evidence. "
        "Reply in the same language as the user. Use a concise paragraph and, only when useful, simple numbered actions. "
        f"{intent_instruction}"
        "Do not display raw fields, journals, topology, source IDs, URLs, or debug metadata.\n\n"
        f"Question: {query_text}\n\nLive ticket context:\n{live_context}\n\nEvidence:\n{evidence}"
    ) if chunks else _fallback_prompt(query_text)


def _is_how_to_question(query_text: str) -> bool:
    return bool(re.search(r"\b(how|fix|resolve|recover|clear|troubleshoot|steps?|guide)\b", query_text.casefold()))


def _is_analysis_or_resolution_request(query_text: str) -> bool:
    return _is_how_to_question(query_text) or bool(
        re.search(r"\b(analyse|analyze|analysis|resolution|root cause|recommend|what should|next steps?)\b", query_text.casefold())
    )


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
    breached = [ticket for ticket in active if ticket.is_breached or (ticket.sla_time_remaining is not None and ticket.sla_time_remaining <= 0)]
    at_risk = [
        ticket for ticket in active
        if ticket not in breached and ticket.type in {"INC", "RITM"}
        and (ticket.sla_status == "AT_RISK" or (ticket.sla_time_remaining is not None and 0 < ticket.sla_time_remaining <= 90))
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

    query = query_text.casefold()
    metric_terms = (
        "metric", "metrics", "stats", "statistic", "dashboard", "chart", "kpi", "total",
        "how many", "count", "percentage", "percent", "sla health", "sla breach", "breached",
        "at risk", "workload", "capacity", "open tickets", "open work", "anomaly", "unusual",
        "trend", "most breached", "team health", "team workload",
    )
    return any(term in query for term in metric_terms)


def _live_stats_snapshot(query_text: str) -> dict[str, Any]:
    """Read the exact Stats-tab aggregation without importing it at module load.

    `main.py` imports this module, so the import is deliberately delayed until
    a live chat request. The call is read-only and uses explicit filter values
    instead of FastAPI's request-time Query defaults.
    """

    from .main import get_dashboard_stats

    groups = _mentioned_assignment_groups(query_text)
    assignees = _mentioned_assignees(query_text)
    modules = sorted(_requested_sap_modules(query_text))
    return get_dashboard_stats(
        assignment_group=groups,
        group_filter_active=bool(groups),
        assignee=assignees,
        sap_module=modules,
        start_date=None,
        end_date=None,
    )


def _stats_scope_label(stats: dict[str, Any]) -> str:
    """Describe the exact canonical scope used by a live stats response."""

    filters = stats.get("filters", {})
    groups = filters.get("assignment_groups", [])
    modules = filters.get("sap_modules", [])
    assignees = filters.get("assignees", [])
    if modules:
        return f"{' and '.join(modules)} module scope"
    if assignees:
        return f"{', '.join(assignees)}'s assigned queue"
    if len(groups) == 1:
        return f"{groups[0]} assignment-group scope"
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
    return {
        "type": "dashboard_summary",
        "title": f"Live operational snapshot — {scope}",
        "metrics": [
            {"label": "Total scope", "value": int(summary["total_tickets"]), "color": "#38bdf8"},
            {"label": "SLA breached", "value": int(summary["breached"]), "color": "#ef4444"},
            {"label": "At risk", "value": int(next((item["value"] for item in sla_data if item["label"] == "At Risk"), 0)), "color": "#f59e0b"},
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
    listed = [str(ticket["number"]) for ticket in stats.get("ticket_index", [])]
    # Read the scope from the exact serialized snapshot supplied to this
    # deterministic synthesizer. The numerical values below come from the
    # same immutable Stats payload rather than from model generation.
    context_lines = (stats_context or _stats_context_block(stats)).splitlines()
    scope_value = next((line.removeprefix("Scope: ") for line in context_lines if line.startswith("Scope: ")), _stats_scope_label(stats))
    scope = f"the {scope_value}"

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
            f"The strongest current anomaly is {insight['title']}.",
            f"{insight['explanation']} Confidence is {insight['confidence_score']}%.",
            f"Affected tickets: {', '.join(impacted) or 'none recorded'}.",
            f"Assignment-group evidence: {'; '.join(str(item) for item in insight.get('supporting_evidence', [])[:3])}.",
            f"Relevant assignees: {', '.join(impacted_assignees) or 'not recorded'}.",
            f"Recommended action: {insight['recommended_action']}.",
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

    if any(term in query for term in ("sla", "breach", "breached", "percentage", "percent")):
        return (
            f"In {scope}, there are {active_total} active work items across {summary['total_tickets']} records in the reporting window. "
            f"SLA applies to {eligible} INC/RITM records: {breached} breached, {sla_segments.get('At Risk', 0)} at risk, and {sla_segments.get('On Track', 0)} on track. "
            f"The current breach rate is {breach_rate}%.",
            listed,
        )

    return (
        f"In {scope}, there are {active_total} active work items out of {summary['total_tickets']} total records. "
        f"{summary['in_progress']} are in progress, {summary['on_hold']} are on hold, and {breached} SLA-tracked records are breached. "
        f"On-hold dependencies include {summary['awaiting_caller']} awaiting caller, {summary['awaiting_change']} awaiting change, "
        f"{summary['awaiting_child']} awaiting child, {summary['awaiting_vendor']} awaiting vendor, "
        f"{summary['awaiting_problem']} awaiting problem, and {summary['awaiting_parent']} awaiting parent.",
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
    lines = [f"Current {scope} tickets", "", f"I found {len(tickets)} active record{'s' if len(tickets) != 1 else ''}.", "", "Queue details"]
    for index, ticket in enumerate(tickets, start=1):
        lines.extend(_ticket_detail_block(ticket, index))
        lines.append("")
    return "\n".join(lines), [ticket.number for ticket in tickets]


def _is_breached_ticket_list_request(query_text: str, history: list[dict[str, str]] | None = None) -> bool:
    """Recognise a direct or contextual request to enumerate SLA breaches."""

    query = query_text.casefold()
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


def _is_integration_change_question(query_text: str) -> bool:
    query = query_text.casefold()
    return "change" in query and any(term in query for term in ("interface", "integration", "middleware", "api"))


def _procedure_title(query_text: str, chunks: list[dict[str, object]]) -> str:
    """Choose a human-readable heading from the resolved knowledge context."""

    if _is_goods_receipt_question(query_text):
        return "LEAP SAP EWM Goods Receipt"
    if _is_integration_change_question(query_text):
        return "Production SAP Interface Change Control"
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
    if _is_integration_change_question(query_text):
        return [
            "Confirm the affected interface, source and target systems, business impact, approved Change Request, implementation owner, and rollback owner.",
            "Capture the failing payload, correlation ID, current mapping version, endpoint response, and a known-good comparison before retrying or changing production configuration.",
            "Complete the required impact assessment, test evidence, approvals, implementation plan, and rollback plan under the approved change-control procedure.",
            "Implement only in the approved window. Monitor message processing, error queues, downstream record creation, and business validation during the change.",
            "Validate the end-to-end outcome with the business owner, record the evidence and residual risk in the Change Request, then close or roll back using the approved decision path.",
        ]
    if _is_goods_receipt_question(query_text):
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
    if any(term in query for term in ("disposal", "dispose", "scrap", "scrapping", "retained sample", "expired material", "prt0-scrap", "scrap-zone", "movement type 551", "migo", "scwm/prdo", "zz1_disposal_days")):
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


def _retrieved_knowledge_answer(query_text: str, chunks: list[dict[str, object]]) -> str | None:
    """Give a direct factual answer from a matching SUD when no playbook fits.

    The local model is intentionally optional. This keeps newly added knowledge
    useful in offline demo environments instead of collapsing to generic advice.
    """

    terms = _query_terms(query_text)
    best: tuple[int, str, list[str]] | None = None
    for chunk in chunks:
        if chunk.get("record_type") != "knowledge":
            continue
        # Retrieval chunks begin with the document summary. Prefer the source
        # body so a procedural answer does not merely repeat the article title.
        content = str(chunk.get("content", "")).split("Tags:", 1)[0]
        if "\n" in content:
            content = content.split("\n", 1)[1]
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
        ranked = sorted(
            ((sum(term in sentence.casefold() for term in terms), index, sentence) for index, sentence in enumerate(sentences)),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] <= 0:
            continue
        _, first_index, _ = ranked[0]
        # Preserve the source's procedural sequence after the best-matching
        # sentence instead of assembling unrelated high-scoring fragments.
        matched = sentences[first_index:first_index + 3]
        if matched and (best is None or ranked[0][0] > best[0]):
            best = (ranked[0][0], str(chunk.get("title", "internal procedure")), matched)
    if not best:
        return None
    _, title, sentences = best
    return f"According to {title}, {' '.join(sentences)}"


def _has_authoritative_playbook(query_text: str) -> bool:
    """Keep high-confidence SOP routes deterministic when running without Gemini.

    A very small keyless model is useful for open-ended language, but it should
    never replace a precise, validated LEAP procedure with a weaker paraphrase.
    """

    return _is_ewm_queue_lock_question(query_text) or _topic_action_items(query_text) is not None


def _local_answer(query_text: str, chunks: list[dict[str, object]]) -> str:
    if not chunks:
        return (
            "I could not find a matching live ticket, calculated metric, or approved enterprise document for that question. "
            "Try a ticket number, an assignee or assignment-group name, or a specific SAP process such as EWM goods receipt, Request Hub, or HP ALM testing."
        )

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
    attribution = next((line for line in grounded_answer.splitlines() if line.startswith("This guidance is grounded in ")), "")
    return (
        f"{ticket.number} is currently {ticket.state}. {situation}\n\n"
        f"Latest update: {latest_comment}\n\n"
        "Next steps\n"
        f"1. {next_move}.\n"
        "2. Confirm the current business impact and any dependency with the owning team.\n"
        "3. Validate the outcome with the requester and record the evidence before closure."
        + (f"\n\n{attribution}" if attribution else "")
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


def _add_natural_source_attribution(answer: str, chunks: list[dict[str, object]]) -> str:
    """Keep source lineage visible in prose without adding UI cards or raw IDs."""

    knowledge_chunks = [chunk for chunk in chunks if chunk.get("record_type") == "knowledge"]
    for chunk in knowledge_chunks:
        title = str(chunk.get("title", "")).strip()
        if title and title.casefold() in answer.casefold():
            return answer
    if knowledge_chunks:
        # Deterministic procedure routes can be more precise than the first
        # vector hit. Select the matching canonical title for the citation.
        chunk = next(
            (
                candidate for candidate in knowledge_chunks
                if _is_goods_receipt_question(answer)
                and "goods receipt" in str(candidate.get("title", "")).casefold()
            ),
            next(
                (
                    candidate for candidate in knowledge_chunks
                    if _is_integration_change_question(answer)
                    and "change control for sap interface" in str(candidate.get("title", "")).casefold()
                ),
                knowledge_chunks[0],
            ),
        )
        title = str(chunk.get("title", "")).strip()
        system = str(chunk.get("system", "enterprise knowledge base")).strip()
        if title:
            source_id = str(chunk.get("id", "")).removeprefix("source:")
            return f"{answer.rstrip()}\n\nSource: [{system}] {source_id} — {title} ↗"
    return answer


def query_hybrid_rag(query_text: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Retrieve evidence, then prefer Gemini or local open-source synthesis."""

    chunks = retrieve_vector_context(query_text)
    has_internal_match = bool(chunks)
    prompt = _grounded_prompt(query_text, chunks) if has_internal_match else _fallback_prompt(query_text)
    ticket_list_intent = is_active_ticket_list_request(query_text)
    listed_ticket_ids: list[str] = []
    assignees = _mentioned_assignees(query_text)
    groups = _mentioned_assignment_groups(query_text)
    operational_scope_intent = False
    chart_data: dict[str, object] | None = None
    stats_context: str | None = None
    direct_ticket_ids = _explicit_ticket_numbers(query_text)
    direct_ticket = next((central_ticket_records().get(ticket_id) for ticket_id in direct_ticket_ids if ticket_id in central_ticket_records()), None)
    # A module-specific queue question is a scoped operational lookup.  Keep
    # it on the list path even when phrased as "how many", so the response
    # provides both the truthful count and the records behind that count.
    module_queue_intent = bool(_requested_sap_modules(query_text)) and bool(
        re.search(r"\b(tickets?|incidents?|queue|work items?)\b", query_text.casefold())
    )
    # A module queue request (for example, "how many PLM tickets are in the
    # queue") is handled by the ticket-list path so it returns the actual
    # matching work items rather than unrelated global metrics.
    breach_list_intent = _is_breached_ticket_list_request(query_text, history)
    stats_intent = (
        _is_metrics_intent(query_text)
        and direct_ticket is None
        and not ticket_list_intent
        and not module_queue_intent
        and not breach_list_intent
        and not assignees
        and not groups
    )
    if direct_ticket is not None:
        answer = _ticket_answer(direct_ticket)
        listed_ticket_ids = [direct_ticket.number]
        operational_scope_intent = True
        intent = "direct_ticket"
    elif breach_list_intent:
        answer, listed_ticket_ids = _breached_ticket_list_answer(query_text)
        operational_scope_intent = True
        intent = "breached_ticket_list"
    elif assignees:
        assignee = assignees[0]
        scoped_tickets = [ticket for ticket in central_ticket_records().values() if ticket.assigned_to == assignee]
        answer, listed_ticket_ids = _workload_answer(assignee, scoped_tickets)
        if _is_metrics_intent(query_text):
            live_stats = _live_stats_snapshot(query_text)
            stats_context = _stats_context_block(live_stats)
            chart_data = _stats_chart_payload(live_stats)
        operational_scope_intent = True
        intent = "assignee_workload"
    elif groups:
        group = groups[0]
        scoped_tickets = [ticket for ticket in central_ticket_records().values() if ticket.assignment_group == group]
        answer, listed_ticket_ids = _workload_answer(group, scoped_tickets)
        if _is_metrics_intent(query_text):
            live_stats = _live_stats_snapshot(query_text)
            stats_context = _stats_context_block(live_stats)
            chart_data = _stats_chart_payload(live_stats)
        operational_scope_intent = True
        intent = "assignment_group_workload"
    elif stats_intent:
        live_stats = _live_stats_snapshot(query_text)
        stats_context = _stats_context_block(live_stats)
        answer, listed_ticket_ids = _stats_answer(query_text, live_stats, stats_context)
        chart_data = _stats_chart_payload(live_stats)
        operational_scope_intent = True
        intent = "live_stats"
    elif ticket_list_intent or module_queue_intent:
        answer, listed_ticket_ids = _active_ticket_list_answer(query_text)
        intent = "active_ticket_list"
    else:
        answer = _local_answer(query_text, chunks)
        intent = "conversational_guidance"
    model_used = "live-stats-deterministic" if stats_intent else "canonical-ticket-deterministic" if direct_ticket is not None else "local-grounded-fallback"
    if gemini_client is not None and not ticket_list_intent and not operational_scope_intent:
        try:
            generated = gemini_client.models.generate_content(model=GENERATION_MODEL, contents=prompt)
            if generated.text:
                answer, model_used = generated.text, GENERATION_MODEL
        except Exception:
            pass
    elif not ticket_list_intent and not operational_scope_intent and not _has_authoritative_playbook(query_text):
        local_answer = LOCAL_OPEN_SOURCE_GENERATOR.generate(_local_generation_prompt(query_text, chunks))
        if local_answer:
            answer = local_answer
            model_used = f"local:{LOCAL_OPEN_SOURCE_GENERATOR.model_id}"
    if has_internal_match and not ticket_list_intent and not operational_scope_intent:
        answer = _add_natural_source_attribution(answer, chunks)
    ticket_ids = []
    for chunk in chunks:
        ticket_id = str(chunk.get("ticket_id") or chunk.get("ticket_number") or "").upper()
        if ticket_id in central_ticket_records() and ticket_id not in ticket_ids:
            ticket_ids.append(ticket_id)
    for ticket_id in listed_ticket_ids:
        if ticket_id in central_ticket_records() and ticket_id not in ticket_ids:
            ticket_ids.append(ticket_id)
    return {
        "answer": answer, "sources": _sources(chunks), "model_used": model_used,
        "embedding_model": VECTOR_STORE.status()["embedding_model"],
        "fallback_reasoning": not has_internal_match and not operational_scope_intent,
        "retrieval_route": "live_stats" if stats_intent else "canonical_ticket" if direct_ticket is not None else "vector_grounded_rag" if has_internal_match else "gemini_itil_reasoning",
        "retrieval": [{key: value for key, value in chunk.items() if key != "content"} for chunk in chunks],
        "ticket_ids": ticket_ids,
        "intent": intent,
        "listed_ticket_ids": listed_ticket_ids,
        # Included for the API contract and diagnostics; it is derived solely
        # from the central Stats calculation and is not persisted anywhere.
        "stats_context": stats_context,
        "chart_data": chart_data,
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
        "local_generation": LOCAL_OPEN_SOURCE_GENERATOR.status(),
    }


# Compatibility aliases for older endpoints and integrations.
query_chatgpt_rag = query_hybrid_rag
retrieve_multi_tool_context = retrieve_vector_context
