"""FastAPI entry point for the Roche ATLAS ITSM Co-Pilot demo."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from .models import ALL_ASSIGNMENT_GROUPS, MOCK_DB, Ticket, calculate_health_color


class ChatQuery(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    ticket_id: str | None = None
    action: Literal["chat", "generate_cr", "generate_rca"] = "chat"


def ticket_payload(ticket: Ticket) -> dict:
    return {**ticket.model_dump(), "health_color": calculate_health_color(ticket)}


def topology_payload(ticket: Ticket) -> dict[str, object]:
    """Return the ServiceNow relationship graph needed by chat and ticket inspectors."""

    return {
        "parent_inc": ticket.parent_inc,
        "current_ticket": {"number": ticket.number, "title": ticket.title, "type": ticket.type},
        "child_incs": ticket.child_incs,
        "linked_prb": ticket.linked_prb,
        "linked_chg": ticket.linked_chg,
    }


def find_ticket_from_natural_language(query_text: str) -> str | None:
    """Return the highest-scoring ticket from ServiceNow fields and knowledge sources."""

    stop_words = {"a", "an", "and", "are", "for", "how", "is", "of", "please", "show", "status", "the", "this", "ticket", "what", "with"}
    terms = [term for term in re.findall(r"[A-Z0-9]{2,}", query_text.upper()) if term.lower() not in stop_words and term != "SAP"]
    best_id: str | None = None
    best_score = 0
    for ticket_id, ticket in MOCK_DB.items():
        knowledge_text = " ".join(
            " ".join(reference.values()) for reference in ticket.knowledge_refs
        )
        searchable_text = " ".join([
            ticket.title,
            ticket.description,
            ticket.ai_resolution_guide,
            " ".join(ticket.additional_comments),
            " ".join(ticket.resources.values()),
            knowledge_text,
        ]).upper()
        score = sum(term in searchable_text for term in terms)
        if score > best_score:
            best_id, best_score = ticket_id, score
    return best_id if best_score else None


def chat_response(query: ChatQuery) -> str:
    ticket = MOCK_DB.get(query.ticket_id) if query.ticket_id else None
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
            return f"{context} SLA has {ticket.sla_remaining_mins} minutes remaining and customer sentiment is {ticket.sentiment}. Health is {calculate_health_color(ticket)}. Resolution guide: {ticket.ai_resolution_guide}"
        if ticket.type == "PRB":
            return f"{context} RCA phase is {ticket.prb_phase} and risk level is {ticket.risk_level}. Health is {calculate_health_color(ticket)}. Resolution guide: {ticket.ai_resolution_guide}"
        return f"{context} Change phase is {ticket.chg_phase} and risk level is {ticket.risk_level}. Health is {calculate_health_color(ticket)}. Resolution guide: {ticket.ai_resolution_guide}"
    return "ATLAS Co-Pilot is using deterministic mock ticket data. Ask about a ticket ID, or select a ticket to generate a focused CR or RCA draft."


app = FastAPI(title="Roche ATLAS ITSM Co-Pilot", version="1.0.0")


@app.get("/api/dashboard/tickets")
def list_dashboard_tickets(assignee: str | None = None, assignment_group: str | None = None) -> dict[str, list[dict]]:
    tickets = list(MOCK_DB.values())
    if assignee:
        tickets = [ticket for ticket in tickets if ticket.assignee == assignee]
    if assignment_group:
        tickets = [ticket for ticket in tickets if ticket.assignment_group == assignment_group]
    return {"tickets": [ticket_payload(ticket) for ticket in tickets]}


@app.get("/api/dashboard/assignment-groups")
def list_assignment_groups() -> dict[str, list[str]]:
    """Return the enterprise assignment-group catalog used by queue filters."""

    return {"assignment_groups": ALL_ASSIGNMENT_GROUPS}


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str) -> dict[str, dict]:
    ticket = MOCK_DB.get(ticket_id.upper())
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} was not found")
    return {"ticket": ticket_payload(ticket)}


@app.post("/api/chat/query")
def query_chat(query: ChatQuery) -> dict[str, object]:
    if query.ticket_id and query.ticket_id.upper() not in MOCK_DB:
        raise HTTPException(status_code=404, detail=f"Ticket {query.ticket_id} was not found")

    query_text = query.message.upper()
    found_id = query.ticket_id.upper() if query.ticket_id else next(
        (ticket_id for ticket_id in MOCK_DB if ticket_id in query_text),
        None,
    )
    found_id = found_id or find_ticket_from_natural_language(query_text)
    rca_intent = "RCA" in query_text or "ROOT CAUSE" in query_text
    cr_intent = bool(re.search(r"\bCR\b", query_text)) or "CHANGE" in query_text

    if query.action == "generate_rca" or rca_intent:
        action = "generate_rca"
        normalized_id = found_id if found_id and MOCK_DB[found_id].type == "PRB" else "PRB0019201"
    elif query.action == "generate_cr" or cr_intent:
        action = "generate_cr"
        normalized_id = found_id if found_id and MOCK_DB[found_id].type == "CHG" else "CHG0092100"
    else:
        action = "chat"
        normalized_id = found_id

    normalized_query = query.model_copy(update={"ticket_id": normalized_id, "action": action})
    response = chat_response(normalized_query)
    ticket = MOCK_DB.get(normalized_id) if normalized_id else None
    if action == "chat" and ticket:
        response = f"Here is the information for {ticket.id}: {response}"
    return {
        "response": response,
        "action": action,
        "ticket_id": normalized_id,
        "generated_content": response if action != "chat" else None,
        "ticket": ticket_payload(ticket) if ticket else None,
        "ai_resolution_guide": ticket.ai_resolution_guide if ticket else None,
        "knowledge_refs": ticket.knowledge_refs if ticket else [],
        "topology": topology_payload(ticket) if ticket else None,
    }


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
