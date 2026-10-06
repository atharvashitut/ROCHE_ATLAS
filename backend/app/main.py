"""FastAPI entry point for the Roche ATLAS ITSM Co-Pilot demo."""

from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from .central_db import central_knowledge_documents, central_knowledge_summary, central_ticket_by_reference, central_ticket_records
from .models import ALL_ASSIGNMENT_GROUPS, Ticket, calculate_health_color, resolve_child_tickets
from .rag_engine import initialize_vector_db, query_hybrid_rag, rag_status


class ChatQuery(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    ticket_id: str | None = None
    action: Literal["chat", "generate_cr", "generate_rca"] = "chat"


def classify_breach_reason(ticket: Ticket) -> str:
    """Classify incident breach ownership using the standard ServiceNow rules."""

    if ticket.on_hold_reason == "Awaiting Vendor":
        return "BR_INC_Vendor Dependency"
    if ticket.on_hold_reason in {"Awaiting Caller", "Awaiting User", "Awaiting Customer"}:
        return "BR_INC_To's and Fro's b/w user and assignee"
    if ticket.on_hold_reason in {"Awaiting Change", "Awaiting Problem"}:
        return "BR_INC_Change/Problem Dependency"
    return "BR_INC_Delayed By Assignee"


def ticket_payload(ticket: Ticket) -> dict:
    payload = {
        **ticket.model_dump(),
        "health_color": calculate_health_color(ticket),
        "customer_sentiment": calculate_customer_sentiment(ticket),
        "breach_reason": classify_breach_reason(ticket) if ticket.is_breached else None,
        # Preserve the internal workflow stage while exposing the ServiceNow
        # executive RED/YELLOW/GREEN SLA contract to every client.
        "sla_workflow_status": ticket.sla_status,
        "sla_status": ticket.sla_health,
        "sla_time_remaining": ticket.sla_time_remaining,
        "module": ticket.sap_modules[0] if ticket.sap_modules else "Enterprise ITSM",
    }
    if ticket.type == "INC":
        children = resolve_child_tickets(ticket)
        # Keep the previous field as a compatibility alias while clients move
        # to child_tickets. Both are hydrated from the same canonical records.
        payload["child_tickets"] = children
        payload["child_incidents"] = children
    return payload


def calculate_customer_sentiment(ticket: Ticket) -> dict[str, object]:
    """Score only caller/requested-for comments, excluding support journal entries."""

    customer_comments = sorted(
        (entry for entry in ticket.comments if entry.is_customer),
        key=lambda entry: entry.sys_created_on,
    )
    if not customer_comments:
        return {"status": "Neutral", "score_pct": 0, "explanation": "No caller-authored additional comments are available for scoring."}

    latest = customer_comments[-1]
    latest_text = latest.value.lower()
    keywords = ("blocked", "immediately", "stuck", "vp", "urgent")
    matched = [keyword for keyword in keywords if keyword in latest_text]
    score = min(100, len(matched) * 20)
    low_sla = ticket.sla_remaining_percent is not None and ticket.sla_remaining_percent < 20
    if low_sla:
        score = min(100, round(score * 1.5))

    if any(term in latest_text for term in ("thank", "resolved", "appreciate")):
        status = "Satisfied"
    elif score >= 70:
        status = "Frustrated"
    elif score >= 20:
        status = "Impatient"
    else:
        status = "Neutral"

    trigger = f"urgent caller phrasing ({', '.join(repr(keyword) for keyword in matched)})" if matched else "no urgency keywords in the latest caller update"
    sla_clause = f" and low SLA time remaining ({ticket.sla_remaining_percent}%)" if low_sla else ""
    return {"status": status, "score_pct": score, "explanation": f"Triggered by {trigger}{sla_clause}."}


def find_ticket_by_reference(ticket_reference: str) -> Ticket | None:
    """Resolve a ServiceNow number, true sys_id, or topology snapshot sys_id."""

    ticket_db = central_ticket_records()
    ticket = central_ticket_by_reference(ticket_reference)
    if ticket is not None:
        return ticket

    needle = ticket_reference.casefold()

    relationship_records = (
        (ticket.parent_incident, *ticket.child_incidents, ticket.linked_prb, ticket.linked_chg, *ticket.originating_tickets)
        for ticket in ticket_db.values()
    )
    for records in relationship_records:
        for record in records:
            if not record:
                continue
            if needle in {str(record.get("number", "")).casefold(), str(record.get("sys_id", "")).casefold()}:
                return ticket_db.get(str(record.get("number", "")).upper())
    return None


def topology_payload(ticket: Ticket) -> dict[str, object]:
    """Return the ServiceNow relationship graph needed by chat and ticket inspectors."""

    return {
        "record_type": ticket.type,
        "current_ticket": {"number": ticket.number, "short_description": ticket.short_description, "state": ticket.state, "type": ticket.type},
        "parent_incident": ticket.parent_incident if ticket.type == "INC" else None,
        "child_incidents": resolve_child_tickets(ticket) if ticket.type == "INC" else [],
        "linked_prb": ticket.linked_prb if ticket.type == "INC" else None,
        "originating_tickets": ticket.originating_tickets if ticket.type in {"CHG", "PRB"} else [],
        "ctasks": ticket.ctasks if ticket.type == "CHG" else [],
        "ptasks": ticket.ptasks if ticket.type == "PRB" else [],
        "linked_chg": ticket.linked_chg if ticket.type in {"INC", "PRB"} else None,
    }


def find_ticket_from_natural_language(query_text: str) -> str | None:
    """Return the highest-scoring ticket from ServiceNow fields and knowledge sources."""

    stop_words = {
        "a", "an", "and", "are", "for", "how", "is", "of", "please", "show",
        "status", "the", "this", "ticket", "what", "with", "about", "can", "do",
        "i", "it", "me", "my", "need", "recover", "should", "to", "we", "you",
    }
    terms = {
        term.lower()
        for term in re.findall(r"[a-zA-Z0-9_]{3,}", query_text)
        if term.lower() not in stop_words and term.lower() != "sap"
    }
    if not terms:
        return None

    best_id: str | None = None
    best_score = 0
    for ticket_id, ticket in central_ticket_records().items():
        knowledge_text = " ".join(
            " ".join(reference.values()) for reference in ticket.knowledge_refs
        )
        title_text = f"{ticket.id} {ticket.title}".lower()
        detail_text = " ".join([
            ticket.description,
            ticket.ai_resolution_guide,
            " ".join(ticket.additional_comments),
            " ".join(ticket.resources.values()),
            knowledge_text,
        ]).lower()
        # A title match is intentionally worth more than incidental prose in
        # a journal entry.  That keeps queries such as “EWM qRFC queue lock”
        # anchored to the owning incident instead of a loosely related RITM.
        score = sum(term in title_text for term in terms) * 6
        score += sum(term in detail_text for term in terms) * 2
        if score > best_score:
            best_id, best_score = ticket_id, score
    return best_id if best_score >= 4 else None


def chat_response(query: ChatQuery) -> str:
    ticket = central_ticket_by_reference(query.ticket_id) if query.ticket_id else None
    context = f" for {ticket.id}" if ticket else ""
    if query.action == "generate_cr":
        title = ticket.title if ticket else "the selected service issue"
        return f"Change request draft{context}: Correct the configuration related to {title}. Validate in the approved release window, monitor authentication telemetry, and retain a rollback to the prior policy baseline."
    if query.action == "generate_rca":
        title = ticket.title if ticket else "the reported service issue"
        return f"RCA draft{context}: The observed impact is {title}. The mock evidence points to a policy claim mapping regression. Correct the mapping, validate token refresh, and add a pre-release claim validation control."
    if ticket:
        context = f"{ticket.id} ({ticket.type}) is {ticket.state}, assigned to {ticket.assignee} in {ticket.assignment_group}."
        if ticket.type in {"INC", "RITM"}:
            customer_sentiment = calculate_customer_sentiment(ticket)
            sla_summary = f"SLA is breached by {abs(ticket.sla_remaining_minutes or 0)} minutes" if ticket.is_breached or (ticket.sla_remaining_minutes is not None and ticket.sla_remaining_minutes <= 0) else f"SLA has {ticket.sla_remaining_minutes} minutes remaining"
            return f"{context} {sla_summary} and customer sentiment is {customer_sentiment['status']} ({customer_sentiment['score_pct']}%). Health is {calculate_health_color(ticket)}. Resolution guide: {ticket.ai_resolution_guide}"
        if ticket.type == "PRB":
            return f"{context} RCA phase is {ticket.prb_phase} and risk level is {ticket.risk_level}. Health is {calculate_health_color(ticket)}. Resolution guide: {ticket.ai_resolution_guide}"
        return f"{context} Change phase is {ticket.chg_phase} and risk level is {ticket.risk_level}. Health is {calculate_health_color(ticket)}. Resolution guide: {ticket.ai_resolution_guide}"
    return "ATLAS Co-Pilot is using deterministic mock ticket data. Ask about a ticket ID, or select a ticket to generate a focused CR or RCA draft."


app = FastAPI(title="Roche ATLAS ITSM Co-Pilot", version="1.0.0")


@app.on_event("startup")
def initialize_canonical_vector_db() -> None:
    """Index the current MOCK_DB and connector corpus before serving requests."""

    initialize_vector_db()


@app.get("/api/dashboard/tickets")
def list_dashboard_tickets(assignee: str | None = None, assignment_group: str | None = None) -> dict[str, list[dict]]:
    tickets = list(central_ticket_records().values())
    if assignee:
        tickets = [ticket for ticket in tickets if ticket.assignee == assignee]
    if assignment_group:
        tickets = [ticket for ticket in tickets if ticket.assignment_group == assignment_group]
    return {"tickets": [ticket_payload(ticket) for ticket in tickets]}


@app.get("/api/dashboard/assignment-groups")
def list_assignment_groups() -> dict[str, list[str]]:
    """Return the enterprise assignment-group catalog used by queue filters."""

    return {"assignment_groups": ALL_ASSIGNMENT_GROUPS}


def _month_starts(start: date, end: date) -> list[date]:
    """Return report buckets beginning on each month between the filter bounds."""

    cursor = start.replace(day=1)
    final = end.replace(day=1)
    months: list[date] = []
    while cursor <= final:
        months.append(cursor)
        cursor = date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1)
    return months


@app.get("/api/dashboard/stats")
def get_dashboard_stats(
    assignment_group: list[str] = Query(default=[]),
    group_filter_active: bool = False,
    assignee: list[str] = Query(default=[]),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Return canonical ServiceNow-style operational analytics for the Stats tab."""

    report_end = end_date or date(2026, 10, 6)
    four_month_window_start = (report_end.year * 12 + report_end.month - 1) - 3
    report_start = start_date or date(four_month_window_start // 12, four_month_window_start % 12 + 1, 1)
    if report_start > report_end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")

    selected_groups = set(assignment_group) if group_filter_active else set(ALL_ASSIGNMENT_GROUPS)
    tickets = [
        ticket for ticket in central_ticket_records().values()
        if ticket.assignment_group in selected_groups
        and (not assignee or ticket.assigned_to in set(assignee))
        and report_start <= date.fromisoformat(ticket.opened_on) <= report_end
    ]

    closed_states = {"Closed", "Resolved", "Closed Complete", "Closed Incomplete", "Closed Skipped", "Canceled"}
    active_states = {"In Progress", "Implement", "Root Cause Analysis", "Assess", "Authorize", "Scheduled", "Review", "Fix in Progress", "Work in Progress"}
    record_types = ("INC", "RITM", "PRB", "CHG")
    type_colors = {"INC": "#38bdf8", "RITM": "#8b5cf6", "PRB": "#f59e0b", "CHG": "#10b981"}
    on_hold = [ticket for ticket in tickets if ticket.state == "On Hold"]
    awaiting_counts = Counter(ticket.on_hold_reason or "Not classified" for ticket in on_hold)
    state_counts = Counter("On Hold" if ticket.state == "On Hold" else "In Progress" for ticket in tickets if ticket.state == "On Hold" or ticket.state in active_states)
    type_pipeline = [
        {
            "label": record_type,
            "total": sum(ticket.type == record_type for ticket in tickets),
            "active": sum(ticket.type == record_type and ticket.state not in closed_states for ticket in tickets),
            "closed": sum(ticket.type == record_type and ticket.state in closed_states for ticket in tickets),
            "breached": sum(ticket.type == record_type and ticket.is_breached for ticket in tickets),
            "color": type_colors[record_type],
        }
        for record_type in record_types
    ]
    sla_eligible = [ticket for ticket in tickets if ticket.type in {"INC", "RITM"}]
    sla_breached = sum(ticket.is_breached or (ticket.sla_remaining_minutes is not None and ticket.sla_remaining_minutes <= 0) for ticket in sla_eligible)
    sla_at_risk = sum(
        not ticket.is_breached
        and (ticket.sla_status == "AT_RISK" or (ticket.sla_remaining_minutes is not None and 0 < ticket.sla_remaining_minutes <= 90))
        for ticket in sla_eligible
    )
    sla_on_track = max(0, len(sla_eligible) - sla_breached - sla_at_risk)
    pipeline_states = [
        {"label": "New", "value": sum(ticket.state == "New" for ticket in tickets), "color": "#94a3b8"},
        {"label": "In Progress", "value": state_counts["In Progress"], "color": "#10b981"},
        {"label": "On Hold", "value": state_counts["On Hold"], "color": "#f59e0b"},
        {"label": "Resolved / Closed", "value": sum(ticket.state in closed_states for ticket in tickets), "color": "#64748b"},
    ]

    months = _month_starts(report_start, report_end)
    visible_groups = sorted(
        selected_groups,
        key=lambda group: sum(ticket.assignment_group == group for ticket in tickets),
        reverse=True,
    )
    trend_by_month: dict[str, dict[str, int]] = {
        month.isoformat(): {group: 0 for group in visible_groups} for month in months
    }
    for ticket in tickets:
        if ticket.assignment_group not in visible_groups:
            continue
        bucket = date.fromisoformat(ticket.opened_on).replace(day=1).isoformat()
        if bucket in trend_by_month:
            trend_by_month[bucket][ticket.assignment_group] += 1

    trend = [
        {
            "month": month.isoformat(),
            "label": month.strftime("%b %Y"),
            "groups": trend_by_month[month.isoformat()],
            "total": sum(trend_by_month[month.isoformat()].values()),
        }
        for month in months
    ]
    def is_at_risk(ticket: Ticket) -> bool:
        return (
            ticket.type in {"INC", "RITM"}
            and not ticket.is_breached
            and (ticket.sla_status == "AT_RISK" or (ticket.sla_remaining_minutes is not None and 0 < ticket.sla_remaining_minutes <= 90))
        )

    team_sla_health = []
    team_status_call = []
    assignee_map: dict[str, list[Ticket]] = {}
    for ticket in tickets:
        assignee_map.setdefault(ticket.assigned_to or ticket.assignee, []).append(ticket)
    for group in visible_groups:
        group_tickets = [ticket for ticket in tickets if ticket.assignment_group == group]
        if not group_tickets:
            continue
        group_sla = [ticket for ticket in group_tickets if ticket.type in {"INC", "RITM"}]
        breached = sum(ticket.is_breached or (ticket.sla_remaining_minutes is not None and ticket.sla_remaining_minutes <= 0) for ticket in group_sla)
        at_risk = sum(is_at_risk(ticket) for ticket in group_sla)
        active_tickets = [ticket for ticket in group_tickets if ticket.state not in closed_states]
        resolved = sum(ticket.state in closed_states for ticket in group_tickets)
        average_backlog_age = round(sum((report_end - date.fromisoformat(ticket.opened_on)).days for ticket in active_tickets) / len(active_tickets)) if active_tickets else 0
        breach_rate = round((breached / len(group_sla)) * 100) if group_sla else 0
        team_sla_health.append({
            "group": group,
            "breached": breached,
            "at_risk": at_risk,
            "on_track": max(0, len(group_sla) - breached - at_risk),
            "sla_eligible": len(group_sla),
        })
        team_status_call.append({
            "group": group,
            "open_backlog": len(active_tickets),
            "average_backlog_age_days": average_backlog_age,
            "resolved": resolved,
            "resolution_velocity_pct": round((resolved / len(group_tickets)) * 100),
            "breach_rate_pct": breach_rate,
            "breached": breached,
            "at_risk": at_risk,
        })
    assignee_workload = [
        {
            "assignee": assignee,
            "active": sum(ticket.state not in closed_states for ticket in assignee_tickets),
            "total": len(assignee_tickets),
            "breached": sum(ticket.is_breached or (ticket.sla_remaining_minutes is not None and ticket.sla_remaining_minutes <= 0) for ticket in assignee_tickets if ticket.type in {"INC", "RITM"}),
            "at_risk": sum(is_at_risk(ticket) for ticket in assignee_tickets),
            "assignment_groups": sorted({ticket.assignment_group for ticket in assignee_tickets}),
        }
        for assignee, assignee_tickets in assignee_map.items()
    ]
    team_sla_health.sort(key=lambda item: (item["breached"], item["at_risk"], item["sla_eligible"]), reverse=True)
    team_status_call.sort(key=lambda item: (item["breached"], item["at_risk"], item["average_backlog_age_days"]), reverse=True)
    assignee_workload.sort(key=lambda item: (item["breached"], item["at_risk"], item["active"]), reverse=True)
    return {
        "filters": {
            "assignment_groups": sorted(selected_groups),
            "assignees": sorted(assignee),
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
        },
        "summary": {
            "total_tickets": len(tickets),
            "incidents": sum(ticket.type == "INC" for ticket in tickets),
            "service_requests": sum(ticket.type == "RITM" for ticket in tickets),
            "problems": sum(ticket.type == "PRB" for ticket in tickets),
            "changes": sum(ticket.type == "CHG" for ticket in tickets),
            "breached": sla_breached,
            "in_progress": state_counts["In Progress"],
            "on_hold": state_counts["On Hold"],
            "awaiting_caller": awaiting_counts["Awaiting Caller"],
            "awaiting_change": awaiting_counts["Awaiting Change"],
            "awaiting_child": awaiting_counts["Awaiting Child"],
            "awaiting_vendor": awaiting_counts["Awaiting Vendor"],
        },
        "awaiting_breakdown": [
            {"label": "Awaiting Caller", "value": awaiting_counts["Awaiting Caller"], "color": "#f59e0b"},
            {"label": "Awaiting Change", "value": awaiting_counts["Awaiting Change"], "color": "#2563eb"},
            {"label": "Awaiting Child", "value": awaiting_counts["Awaiting Child"], "color": "#8b5cf6"},
            {"label": "Awaiting Vendor", "value": awaiting_counts["Awaiting Vendor"], "color": "#ec4899"},
        ],
        "work_state_breakdown": [
            {"label": "In Progress", "value": state_counts["In Progress"], "color": "#10b981"},
            {"label": "On Hold", "value": state_counts["On Hold"], "color": "#f59e0b"},
        ],
        "record_type_pipeline": type_pipeline,
        "sla_health_breakdown": [
            {"label": "Breached", "value": sla_breached, "color": "#ef4444"},
            {"label": "At Risk", "value": sla_at_risk, "color": "#f59e0b"},
            {"label": "On Track", "value": sla_on_track, "color": "#10b981"},
            {"label": "No SLA (PRB/CHG)", "value": sum(ticket.type in {"PRB", "CHG"} for ticket in tickets), "color": "#64748b"},
        ],
        "pipeline_state_breakdown": pipeline_states,
        "breach_by_type": [{"label": item["label"], "value": item["breached"], "color": item["color"]} for item in type_pipeline],
        "team_workload": [
            {
                "group": group,
                "total": sum(ticket.assignment_group == group for ticket in tickets),
                "active": sum(ticket.assignment_group == group and ticket.state not in closed_states for ticket in tickets),
                "breached": sum(ticket.assignment_group == group and ticket.is_breached for ticket in tickets),
            }
            for group in visible_groups
            if any(ticket.assignment_group == group for ticket in tickets)
        ],
        "team_sla_health": team_sla_health,
        "assignee_workload": assignee_workload,
        "team_status_call": team_status_call,
        "work_item_trend": {"groups": visible_groups, "series": trend},
        # Kept for compatibility with older clients; the executive cockpit
        # uses work_item_trend so Changes, Problems, and Requests are included.
        "incident_trend": {"groups": visible_groups, "series": trend},
        "available_groups": ALL_ASSIGNMENT_GROUPS,
        "available_assignees": sorted({ticket.assigned_to for ticket in central_ticket_records().values()}),
    }


@app.get("/api/stats")
def get_live_stats(
    assignment_group: list[str] = Query(default=[]),
    group_filter_active: bool = False,
    assignee: list[str] = Query(default=[]),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Canonical stats alias for integrations outside the dashboard route."""

    return get_dashboard_stats(assignment_group, group_filter_active, assignee, start_date, end_date)


@app.get("/api/knowledge/sources")
def list_central_knowledge_sources() -> dict[str, object]:
    """Expose the canonical multi-platform registry used by tickets and RAG."""

    return {**central_knowledge_summary(), "sources": central_knowledge_documents()}


@app.get("/api/rag/status")
def get_rag_status() -> dict[str, object]:
    """Expose vector-store and connector readiness for operational checks."""

    return rag_status()


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict[str, dict]:
    ticket = find_ticket_by_reference(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} was not found")
    return {"ticket": ticket_payload(ticket)}


@app.post("/api/chat/query")
def query_chat(query: ChatQuery) -> dict[str, object]:
    ticket_db = central_ticket_records()
    if query.ticket_id and query.ticket_id.upper() not in ticket_db:
        raise HTTPException(status_code=404, detail=f"Ticket {query.ticket_id} was not found")

    query_text = query.message.upper()
    found_id = query.ticket_id.upper() if query.ticket_id else next(
        (ticket_id for ticket_id in ticket_db if ticket_id in query_text),
        None,
    )
    found_id = found_id or find_ticket_from_natural_language(query_text)
    rag_result = query_hybrid_rag(query.message)
    # Semantic retrieval resolves conversational references that are not a
    # literal ServiceNow number. The selected record is still hydrated from
    # the canonical MOCK_DB-backed repository below.
    found_id = found_id or next((ticket_id for ticket_id in rag_result["ticket_ids"] if ticket_id in ticket_db), None)
    rca_intent = "RCA" in query_text or "ROOT CAUSE" in query_text
    cr_intent = bool(re.search(r"\bCR\b", query_text)) or "CHANGE" in query_text

    if query.action == "generate_rca" or rca_intent:
        action = "generate_rca"
        normalized_id = found_id if found_id and ticket_db[found_id].type == "PRB" else "PRB0031022"
    elif query.action == "generate_cr" or cr_intent:
        action = "generate_cr"
        normalized_id = found_id if found_id and ticket_db[found_id].type == "CHG" else "CHG0092100"
    else:
        action = "chat"
        normalized_id = found_id

    normalized_query = query.model_copy(update={"ticket_id": normalized_id, "action": action})
    response = chat_response(normalized_query)
    ticket = ticket_db.get(normalized_id) if normalized_id else None
    if action == "chat":
        response = rag_result["answer"]
        if ticket:
            ticket_context = chat_response(normalized_query)
            response = f"Here is the information for {ticket.id}: {ticket_context}\n\n{response}"
    if ticket and ticket.similar_records:
        response = "⚠️ **AI Similarity Detection Triggered:** I found historical patterns matching this issue.\n\n" + response
    return {
        "response": response,
        "action": action,
        "ticket_id": normalized_id,
        "generated_content": response if action != "chat" else None,
        "ticket": ticket_payload(ticket) if ticket else None,
        "ai_resolution_guide": ticket.ai_resolution_guide if ticket else None,
        "knowledge_refs": ticket.knowledge_refs if ticket else [],
        "topology": topology_payload(ticket) if ticket else None,
        "sources": rag_result["sources"],
        "model_used": rag_result["model_used"],
        "embedding_model": rag_result["embedding_model"],
        "fallback_reasoning": rag_result["fallback_reasoning"],
        "retrieval_route": rag_result["retrieval_route"],
        "retrieval": rag_result["retrieval"],
    }


@app.post("/api/chat")
def query_chat_compat(query: ChatQuery) -> dict[str, object]:
    """Compatibility route for clients using the concise chat endpoint."""

    return query_chat(query)


class SPAStaticFiles(StaticFiles):
    """Serve build assets and fall back to the SPA entrypoint for browser routes."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api/"):
                return await super().get_response("index.html", scope)
            raise


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = PROJECT_ROOT / "frontend" / "dist"

# API routes are registered above this root mount, so /api always returns JSON.
app.mount("/", SPAStaticFiles(directory=DIST_DIR, html=True, check_dir=False), name="frontend")
