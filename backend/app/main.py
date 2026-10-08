"""FastAPI entry point for the Roche ATLAS ITSM Co-Pilot demo."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from .agent_intelligence import analyze_assignment_group_workload, analyze_assignee_workload, analyze_ticket
from .central_db import central_knowledge_documents, central_knowledge_summary, central_ticket_by_reference, central_ticket_records
from .models import (
    ALL_ASSIGNMENT_GROUPS,
    CANONICAL_REPORT_END,
    CANONICAL_REPORT_START,
    Ticket,
    calculate_health_color,
    effective_hold_reason,
    is_sla_breached,
    resolve_child_tickets,
)
from .rag_engine import compose_conversational_ticket_response, initialize_vector_db, query_hybrid_rag, rag_status, retrieve_vector_context


class ChatQuery(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)
    ticket_id: str | None = None
    action: Literal["chat", "generate_cr", "generate_rca"] = "chat"


def classify_breach_reason(ticket: Ticket) -> str:
    """Classify incident breach ownership using the standard ServiceNow rules."""

    hold_reason = effective_hold_reason(ticket)
    if hold_reason == "Awaiting Vendor":
        return "BR_INC_Vendor Dependency"
    if hold_reason in {"Awaiting Caller", "Awaiting User", "Awaiting Customer"}:
        return "BR_INC_To's and Fro's b/w user and assignee"
    if hold_reason in {"Awaiting Change", "Awaiting Problem"}:
        return "BR_INC_Change/Problem Dependency"
    if hold_reason == "Awaiting Parent":
        return "BR_INC_Parent Dependency"
    return "BR_INC_Delayed By Assignee"


def ticket_payload(ticket: Ticket, include_agent_analysis: bool = False) -> dict:
    payload = {
        **ticket.model_dump(),
        "health_color": calculate_health_color(ticket),
        "customer_sentiment": calculate_customer_sentiment(ticket),
        "is_breached": is_sla_breached(ticket),
        "breach_reason": classify_breach_reason(ticket) if is_sla_breached(ticket) else None,
        "hold_reason": effective_hold_reason(ticket),
        # Compatibility alias; all first-party UI now reads hold_reason.
        "on_hold_reason": effective_hold_reason(ticket),
        # Preserve the internal workflow stage while exposing the ServiceNow
        # executive RED/YELLOW/GREEN SLA contract to every client.
        "sla_workflow_status": ticket.sla_status,
        "sla_status": ticket.sla_health,
        "sla_time_remaining": ticket.sla_time_remaining,
        "module": ticket.sap_modules[0] if ticket.sap_modules else "Enterprise ITSM",
        "ai_insight": build_ticket_ai_insight(ticket),
    }
    if ticket.type == "INC":
        children = resolve_child_tickets(ticket)
        # Keep the previous field as a compatibility alias while clients move
        # to child_tickets. Both are hydrated from the same canonical records.
        payload["child_tickets"] = children
        payload["child_incidents"] = children
    if include_agent_analysis:
        try:
            relationship_numbers = {
                str(record.get("number", ""))
                for record in (ticket.parent_incident, ticket.linked_prb, ticket.linked_chg, *ticket.originating_tickets)
                if record and record.get("number")
            }
            relationship_numbers.update(ticket.child_ids)
            related_records = [
                related for number in relationship_numbers
                if number and (related := central_ticket_by_reference(number)) is not None
            ]
            agent_analysis = analyze_ticket(ticket, related_records, retrieve_vector_context(ticket.number, limit=4))
            payload["agent_analysis"] = agent_analysis
            payload["ai_insight"] = {
                **payload["ai_insight"],
                "resolution_summary": f"{agent_analysis['current_impact']} {agent_analysis['likely_contributing_factor']}",
                "resolution_actions": agent_analysis["recommended_next_steps"],
                "recommended_actions": agent_analysis["recommended_next_steps"],
                "confidence_score": agent_analysis["confidence_score"],
            }
        except Exception:
            # Agent analysis is optional advisory intelligence. A retrieval or
            # analysis failure must never break the canonical ticket response.
            payload["agent_analysis"] = None
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


def technical_resolution_actions(ticket: Ticket) -> list[dict[str, str]]:
    """Return concise, module-aware L2/L3 diagnostic and resolution steps.

    The steps are generated from the canonical ServiceNow record's SAP module
    tags and description.  Conditional routing is deliberately explicit so a
    drawer briefing can be followed safely without treating it as permission
    to make an unapproved production change.
    """

    text = " ".join([
        ticket.short_description,
        ticket.description,
        " ".join(entry.value for entry in ticket.comments),
        " ".join(entry.value for entry in ticket.work_notes),
    ]).casefold()
    actions: list[dict[str, str]] = []

    def add(action: str, why: str) -> None:
        if not any(existing["action"] == action for existing in actions):
            actions.append({"action": action, "why": why})

    if "SAP BASIS" in ticket.sap_modules and any(term in text for term in ("sm37", "abap dump", "batch job", "background job")):
        add(
            "Review SM37, ST22, and the job spool before restart",
            "Capture job log, ABAP dump, variant, technical user, and client so SAP Basis can distinguish a data issue from a platform failure.",
        )
    if "SAP EWM" in ticket.sap_modules:
        add(
            "Capture lock ownership in SM12 before intervention",
            "Record the lock owner, client, object, and age; do not remove an active lock until ownership is confirmed.",
        )
        add(
            "Inspect qRFC queues in SMQ1 and SMQ2",
            "Check outbound and inbound queue status, destination, LUW error text, retries, and predecessor blocks before a controlled restart.",
        )
        add(
            "Validate warehouse recovery in /SCWM/MON",
            "After the approved queue action, confirm warehouse task processing and a representative goods issue without a re-lock.",
        )
    if "SAP Security" in ticket.sap_modules or any(term in text for term in ("authorization", "token", "su53", "m_mseg")):
        add(
            "Run SU53 for the affected user or technical batch user",
            "If the trace shows a missing authorization object, route the evidence to Identity & Access Management for the approved role correction; do not grant broad access as a workaround.",
        )
    if "SAP BASIS" in ticket.sap_modules:
        if any(term in text for term in ("rf", "gateway", "timeout", "connection")):
            add(
                "Check SMICM and SMGW for node-specific gateway errors",
                "Confirm whether the RF timeout is isolated to one node, connection pool, or certificate path before a controlled restart.",
            )
        add(
            "Verify the SAP client context before changing technical settings",
            "If the evidence names client 000, raise the controlled investigation with SAP Basis; client 000 changes require Basis ownership and approved change control.",
        )
    if "SAP PLM" in ticket.sap_modules:
        add(
            "Review the PLM specification or recipe in CG03/CG02",
            "Confirm the affected specification or recipe version, status, and classification values before attempting a resynchronization.",
        )
        add(
            "Trace the PLM integration payload and queue",
            "Compare the failed payload mapping with the Material Master classification target, then capture queue or middleware errors for the integration owner.",
        )
        add(
            "Reprocess only after mapping and approval checks pass",
            "Use the controlled PLM procedure to validate the synchronization result and preserve GxP evidence.",
        )
    if "SAP MM" in ticket.sap_modules:
        add(
            "Inspect the purchasing document in ME23N and workflow history in SWI1",
            "Confirm the release strategy, approver step, and any workflow error before restarting or re-routing approval.",
        )
        add(
            "Validate Material Master and authorization prerequisites",
            "If the workflow or classification data is valid but access fails, attach the SU53 trace and route the correction to the authorization owner.",
        )
    if "SAP SD" in ticket.sap_modules or "SAP FICO" in ticket.sap_modules:
        add(
            "Inspect the billing error in VFX3 and the billing document in VF03",
            "Capture the blocked billing reason, tax determination message, and account assignment context before any reposting.",
        )
        add(
            "Validate tax and posting configuration with the SD/FICO owner",
            "Correct mapping through approved transport control, then retest one representative billing document and reconcile the FI posting.",
        )
    if "SAP Middleware" in ticket.sap_modules:
        add(
            "Review the interface message and retry history in the middleware monitor",
            "Identify the failing payload, endpoint, and retry pattern; preserve evidence before replaying or clearing a message.",
        )
    if ticket.type == "PRB":
        add(
            "Attach diagnostic evidence to the RCA task before proposing the permanent fix",
            "The problem record should distinguish the observed symptom, technical cause, and validated corrective action.",
        )
    if ticket.type == "CHG":
        add(
            "Complete open change tasks and record validation evidence",
            "Close implementation tasks only after the agreed technical and business checks pass, with rollback evidence retained.",
        )
    return actions


def build_ticket_ai_insight(ticket: Ticket) -> dict[str, object]:
    """Build a concise, deterministic explanation for the drawer AI insight.

    This intentionally uses the same native ServiceNow fields that drive the
    queue and Stats tab.  It is an explainable operational aid, not an opaque
    model score.
    """

    sentiment = calculate_customer_sentiment(ticket)
    related = [
        record["number"]
        for record in (ticket.parent_incident, ticket.linked_prb, ticket.linked_chg, *ticket.originating_tickets)
        if record and record.get("number")
    ]
    evidence: list[str] = [f"State: {ticket.state}", f"Assignment group: {ticket.assignment_group}"]
    reasoning: list[str] = []
    recommendations: list[dict[str, str]] = []
    resolution_actions: list[dict[str, str]] = []
    has_canonical_plan = bool(ticket.ai_resolution_steps)
    confidence = 72

    resolution_actions.extend(ticket.ai_resolution_steps or technical_resolution_actions(ticket))
    if not resolution_actions:
        resolution_actions.append({
            "action": "Execute the approved remediation and validate recovery",
            "why": ticket.ai_resolution_guide,
        })

    def recommend(action: str, why: str) -> None:
        """Add generic operational advice only when a canonical plan is absent."""

        if not has_canonical_plan:
            recommendations.append({"action": action, "why": why})

    if ticket.type in {"INC", "RITM"}:
        if is_sla_breached(ticket):
            overdue = abs(ticket.sla_remaining_minutes or 0)
            reasoning.append("The SLA is already breached, so customer impact needs immediate ownership.")
            evidence.append(f"SLA: breached by {overdue} minutes")
            recommend("Escalate remediation ownership", "The agreed response target has already been missed.")
            confidence += 16
        elif ticket.sla_remaining_minutes is not None and ticket.sla_remaining_minutes <= 90:
            reasoning.append("The remaining SLA window is below the operational at risk threshold.")
            evidence.append(f"SLA: {ticket.sla_remaining_minutes} minutes remaining")
            recommend("Prioritize the next remediation step", "Early intervention reduces the chance of a breach.")
            confidence += 10
        if sentiment["status"] in {"Frustrated", "Impatient"}:
            reasoning.append("Recent caller language signals elevated business urgency.")
            evidence.append(f"Customer sentiment: {sentiment['status']} ({sentiment['score_pct']}%)")
            recommend("Confirm the recovery plan with the requester", "The caller journal indicates active business impact.")
            confidence += 8
    if ticket.state == "On Hold":
        hold_reason = effective_hold_reason(ticket) or "a dependency"
        reasoning.append(f"Progress is constrained by {hold_reason.lower()}.")
        evidence.append(f"On hold reason: {hold_reason}")
        recommend("Clear or formally hand off the blocking dependency", f"The record cannot advance while {hold_reason.lower()} remains open.")
        confidence += 5
    if ticket.type == "PRB" and any(task.get("state") not in {"Closed", "Canceled"} for task in ticket.ptasks):
        reasoning.append("Open problem tasks show that root cause investigation is incomplete.")
        evidence.append(f"Open PTasks: {sum(task.get('state') not in {'Closed', 'Canceled'} for task in ticket.ptasks)}")
        recommend("Complete the active root cause analysis task", "The related problem has active investigation work remaining.")
        confidence += 6
    if ticket.type == "CHG" and any(not str(task.get("state", "")).startswith("Closed") for task in ticket.ctasks):
        reasoning.append("Implementation work remains open on the linked change.")
        evidence.append(f"Open CTasks: {sum(not str(task.get('state', '')).startswith('Closed') for task in ticket.ctasks)}")
        recommend("Complete and evidence the open change tasks", "Open implementation tasks are the active delivery constraint.")
        confidence += 6
    if ticket.similar_records or ticket.historical_tickets:
        reasoning.append("A historical or ongoing similarity match provides a reusable resolution path.")
        evidence.append(f"Similarity matches: {len(ticket.similar_records) + len(ticket.historical_tickets)}")
        recommend("Reuse the matched resolution evidence", "A related record may shorten diagnosis and avoid duplicate effort.")
        confidence += 4
    if not reasoning:
        reasoning.append("The record has no detected breach, blocked dependency, or unfinished delivery task.")
        recommend("Validate recovery and close with evidence", "No elevated operational signal is present in the current record.")
    if related:
        evidence.append(f"Related records: {', '.join(related[:3])}")

    deduplicated_actions: list[dict[str, str]] = []
    seen_actions: set[str] = set()
    for recommendation in [*resolution_actions, *recommendations]:
        if recommendation["action"] not in seen_actions:
            deduplicated_actions.append(recommendation)
            seen_actions.add(recommendation["action"])
    return {
        "reasoning": reasoning[:3],
        "supporting_evidence": evidence[:5],
        "related_events": related[:4] or ["No linked ServiceNow work item is recorded."],
        "confidence_score": min(confidence, 98),
        "recommended_actions": deduplicated_actions[:5],
        "resolution_summary": ticket.ai_resolution_summary or ticket.ai_resolution_guide,
        "resolution_actions": deduplicated_actions[:5],
    }


def detect_incident_anomalies(tickets: list[Ticket], report_start: date, report_end: date) -> dict[str, object]:
    """Detect transparent incident-pattern anomalies from canonical records.

    The detector compares the most recent 30-day period with the preceding
    reporting window.  It evaluates volume, P1/P2 concentration, category,
    and business-service patterns, returning the underlying record IDs so the
    UI can drill into the exact evidence rather than displaying a black-box
    score.
    """

    incidents = [ticket for ticket in tickets if ticket.type == "INC"]
    if not incidents:
        return {"summary": {"total": 0, "high": 0, "medium": 0, "impacted_tickets": 0}, "insights": []}

    range_days = max(1, (report_end - report_start).days + 1)
    recent_days = min(30, max(7, range_days // 3))
    recent_start = report_end - timedelta(days=recent_days - 1)
    recent = [ticket for ticket in incidents if date.fromisoformat(ticket.opened_on) >= recent_start]
    baseline = [ticket for ticket in incidents if date.fromisoformat(ticket.opened_on) < recent_start]
    baseline_days = max(1, (recent_start - report_start).days)
    insights: list[dict[str, object]] = []

    def is_high_priority(ticket: Ticket) -> bool:
        return ticket.priority.startswith("1 -") or ticket.priority.startswith("2 -")

    def add_insight(
        *,
        kind: str,
        severity: str,
        title: str,
        current: int,
        expected: float,
        impacted: list[Ticket],
        explanation: str,
        recommendation: str,
        recommendation_reason: str,
    ) -> None:
        if not impacted:
            return
        impacted_ids = {ticket.number for ticket in impacted}
        # A single cluster can appear through multiple dimensions (for
        # example, a PLM assignment group and its owning business service).
        # Keep one executive insight per identical evidence set instead of
        # flooding leaders with differently named copies of the same signal.
        if any(set(existing["ticket_ids"]) == impacted_ids for existing in insights):
            return
        ratio = current / max(expected, 0.5)
        confidence = min(97, max(72, round(68 + min(ratio, 3) * 9 + min(current, 5) * 2)))
        insights.append({
            "id": f"{kind}-{len(insights) + 1}",
            "kind": kind,
            "severity": severity,
            "title": title,
            "current_count": current,
            "expected_count": round(expected, 1),
            "delta_pct": round(max(0, ((current - expected) / max(expected, 0.5)) * 100)),
            "explanation": explanation,
            "supporting_evidence": [
                f"{current} incident{'s' if current != 1 else ''} in the most recent {recent_days} days",
                f"Expected baseline: {expected:.1f} over an equivalent period",
                f"Impacted assignment groups: {', '.join(sorted({ticket.assignment_group for ticket in impacted}))}",
            ],
            "related_events": sorted({ticket.linked_chg.get('number') for ticket in impacted if ticket.linked_chg} | {ticket.linked_prb.get('number') for ticket in impacted if ticket.linked_prb}),
            "confidence_score": confidence,
            "recommended_action": recommendation,
            "recommendation_reason": recommendation_reason,
            "ticket_ids": sorted(impacted_ids),
        })

    dimensions = (
        ("assignment_group", lambda ticket: ticket.assignment_group, "assignment group"),
        ("category", lambda ticket: ticket.category, "category"),
        ("business_service", lambda ticket: ticket.business_service, "business service"),
    )
    for kind, selector, label in dimensions:
        recent_by_value: dict[str, list[Ticket]] = {}
        baseline_by_value: Counter[str] = Counter()
        for ticket in recent:
            recent_by_value.setdefault(selector(ticket), []).append(ticket)
        for ticket in baseline:
            baseline_by_value[selector(ticket)] += 1
        for value, impacted in recent_by_value.items():
            current = len(impacted)
            expected = baseline_by_value[value] * recent_days / baseline_days
            if current >= 2 and (expected < 1 or current >= max(2, expected * 1.6)):
                severity = "HIGH" if current >= 3 or current >= expected * 2.5 else "MEDIUM"
                add_insight(
                    kind=f"{kind}_spike",
                    severity=severity,
                    title=f"Unusual {value} incident pattern",
                    current=current,
                    expected=expected,
                    impacted=impacted,
                    explanation=f"{value} generated {current} incidents in the latest {recent_days}-day window, above its expected baseline of {expected:.1f}.",
                    recommendation="Investigate a recent Change" if any(ticket.linked_chg for ticket in impacted) else "Create a Problem record",
                    recommendation_reason="The clustered pattern is stronger than the prior reporting trend and should be investigated as a common cause.",
                )

    recent_high_priority = [ticket for ticket in recent if is_high_priority(ticket)]
    baseline_high_priority = [ticket for ticket in baseline if is_high_priority(ticket)]
    expected_high_priority = len(baseline_high_priority) * recent_days / baseline_days
    if len(recent_high_priority) >= 2 and (expected_high_priority < 1 or len(recent_high_priority) >= max(2, expected_high_priority * 1.5)):
        add_insight(
            kind="p1_p2_spike",
            severity="HIGH",
            title="Elevated P1/P2 incident concentration",
            current=len(recent_high_priority),
            expected=expected_high_priority,
            impacted=recent_high_priority,
            explanation=f"{len(recent_high_priority)} P1/P2 incidents were opened in the latest {recent_days} days, compared with an expected {expected_high_priority:.1f}.",
            recommendation="Escalate the incident cluster",
            recommendation_reason="The concentration of high-priority incidents creates a material service-risk pattern.",
        )

    insights.sort(key=lambda item: (item["severity"] == "HIGH", item["delta_pct"], item["current_count"]), reverse=True)
    insights = insights[:6]
    impacted_ticket_ids = {ticket_id for insight in insights for ticket_id in insight["ticket_ids"]}
    return {
        "summary": {
            "total": len(insights),
            "high": sum(insight["severity"] == "HIGH" for insight in insights),
            "medium": sum(insight["severity"] == "MEDIUM" for insight in insights),
            "impacted_tickets": len(impacted_ticket_ids),
            "analysis_window": {"start_date": recent_start.isoformat(), "end_date": report_end.isoformat(), "days": recent_days},
        },
        "insights": insights,
    }


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
        hold_context = f" (hold reason: {effective_hold_reason(ticket)})" if effective_hold_reason(ticket) else ""
        context = f"{ticket.id} ({ticket.type}) is {ticket.state}{hold_context}, assigned to {ticket.assignee} in {ticket.assignment_group}."
        if ticket.type in {"INC", "RITM"}:
            customer_sentiment = calculate_customer_sentiment(ticket)
            sla_summary = f"SLA is breached by {abs(ticket.sla_remaining_minutes or 0)} minutes" if is_sla_breached(ticket) else f"SLA has {ticket.sla_remaining_minutes} minutes remaining"
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

    report_end = end_date or CANONICAL_REPORT_END
    report_start = start_date or CANONICAL_REPORT_START
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
    awaiting_counts = Counter(effective_hold_reason(ticket) or "Not classified" for ticket in on_hold)
    state_counts = Counter("On Hold" if ticket.state == "On Hold" else "In Progress" for ticket in tickets if ticket.state == "On Hold" or ticket.state in active_states)
    type_pipeline = [
        {
            "label": record_type,
            "total": sum(ticket.type == record_type for ticket in tickets),
            "active": sum(ticket.type == record_type and ticket.state not in closed_states for ticket in tickets),
            "closed": sum(ticket.type == record_type and ticket.state in closed_states for ticket in tickets),
            "breached": sum(ticket.type == record_type and is_sla_breached(ticket) for ticket in tickets),
            "color": type_colors[record_type],
        }
        for record_type in record_types
    ]
    sla_eligible = [ticket for ticket in tickets if ticket.type in {"INC", "RITM"}]
    sla_breached = sum(is_sla_breached(ticket) for ticket in sla_eligible)
    sla_at_risk = sum(
        not is_sla_breached(ticket)
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
            and not is_sla_breached(ticket)
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
        breached = sum(is_sla_breached(ticket) for ticket in group_sla)
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
            "breached": sum(is_sla_breached(ticket) for ticket in assignee_tickets),
            "at_risk": sum(is_at_risk(ticket) for ticket in assignee_tickets),
            "assignment_groups": sorted({ticket.assignment_group for ticket in assignee_tickets}),
        }
        for assignee, assignee_tickets in assignee_map.items()
    ]
    team_sla_health.sort(key=lambda item: (item["breached"], item["at_risk"], item["sla_eligible"]), reverse=True)
    team_status_call.sort(key=lambda item: (item["breached"], item["at_risk"], item["average_backlog_age_days"]), reverse=True)
    assignee_workload.sort(key=lambda item: (item["breached"], item["at_risk"], item["active"]), reverse=True)
    anomaly_detection = detect_incident_anomalies(tickets, report_start, report_end)
    try:
        assignment_group_agent = analyze_assignment_group_workload(tickets, anomaly_detection["insights"])
    except Exception:
        # Preserve Stats and the existing anomaly detector if advisory analysis
        # encounters an unexpected malformed mock record.
        assignment_group_agent = {"agent": "assignment_group_investigator", "findings": [], "summary": ""}
    try:
        assignee_agent = analyze_assignee_workload(tickets, assignee[0], report_end) if len(set(assignee)) == 1 else None
    except Exception:
        assignee_agent = None
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
            "awaiting_problem": awaiting_counts["Awaiting Problem"],
            "awaiting_parent": awaiting_counts["Awaiting Parent"],
        },
        "awaiting_breakdown": [
            {"label": "Awaiting Caller", "value": awaiting_counts["Awaiting Caller"], "color": "#f59e0b"},
            {"label": "Awaiting Change", "value": awaiting_counts["Awaiting Change"], "color": "#2563eb"},
            {"label": "Awaiting Child", "value": awaiting_counts["Awaiting Child"], "color": "#8b5cf6"},
            {"label": "Awaiting Vendor", "value": awaiting_counts["Awaiting Vendor"], "color": "#ec4899"},
            {"label": "Awaiting Problem", "value": awaiting_counts["Awaiting Problem"], "color": "#14b8a6"},
            {"label": "Awaiting Parent", "value": awaiting_counts["Awaiting Parent"], "color": "#64748b"},
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
                "breached": sum(ticket.assignment_group == group and is_sla_breached(ticket) for ticket in tickets),
            }
            for group in visible_groups
            if any(ticket.assignment_group == group for ticket in tickets)
        ],
        "team_sla_health": team_sla_health,
        "assignee_workload": assignee_workload,
        "team_status_call": team_status_call,
        "work_item_trend": {"groups": visible_groups, "series": trend},
        "anomaly_detection": anomaly_detection,
        "assignment_group_agent": assignment_group_agent,
        "assignee_agent": assignee_agent,
        # Kept for compatibility with older clients; the executive cockpit
        # uses work_item_trend so Changes, Problems, and Requests are included.
        "incident_trend": {"groups": visible_groups, "series": trend},
        "available_groups": ALL_ASSIGNMENT_GROUPS,
        "available_assignees": sorted({ticket.assigned_to for ticket in central_ticket_records().values()}),
        # The executive UI uses this compact canonical index for chart
        # drill-downs. Full details are still fetched only through /api/tickets.
        "ticket_index": [
            {
                "number": ticket.number,
                "type": ticket.type,
                "state": ticket.state,
                "assignment_group": ticket.assignment_group,
                "assignee": ticket.assigned_to,
                "opened_on": ticket.opened_on,
                "is_breached": is_sla_breached(ticket),
                "sla_health": ticket.sla_health,
                "hold_reason": effective_hold_reason(ticket),
            }
            for ticket in tickets
        ],
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
    return {"ticket": ticket_payload(ticket, include_agent_analysis=True)}


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
    rag_result = query_hybrid_rag(query.message)
    ticket_list_intent = rag_result.get("intent") == "active_ticket_list" and not query.ticket_id
    if not ticket_list_intent:
        found_id = found_id or find_ticket_from_natural_language(query_text)
    # Semantic retrieval resolves conversational references that are not a
    # literal ServiceNow number. The selected record is still hydrated from
    # the canonical MOCK_DB-backed repository below.
    if not ticket_list_intent:
        found_id = found_id or next((ticket_id for ticket_id in rag_result["ticket_ids"] if ticket_id in ticket_db), None)
    else:
        found_id = None
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
            response = compose_conversational_ticket_response(ticket, query.message, response)
    if ticket and ticket.similar_records:
        response = "⚠️ **AI Similarity Detection Triggered:** I found historical patterns matching this issue.\n\n" + response
    return {
        "response": response,
        "action": action,
        "ticket_id": normalized_id,
        "generated_content": response if action != "chat" else None,
        "ticket": ticket_payload(ticket, include_agent_analysis=True) if ticket else None,
        "ai_resolution_guide": ticket.ai_resolution_guide if ticket else None,
        "knowledge_refs": ticket.knowledge_refs if ticket else [],
        "topology": topology_payload(ticket) if ticket else None,
        "sources": rag_result["sources"],
        "model_used": rag_result["model_used"],
        "embedding_model": rag_result["embedding_model"],
        "fallback_reasoning": rag_result["fallback_reasoning"],
        "retrieval_route": rag_result["retrieval_route"],
        "retrieval": rag_result["retrieval"],
        "intent": rag_result["intent"],
        "listed_ticket_ids": rag_result["listed_ticket_ids"],
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
