"""Read-only, deterministic intelligence agents for the ATLAS PoC.

The agents deliberately do not own data, persist findings, call ServiceNow, or
perform actions. They investigate the existing canonical repository, anomaly
signals, relationships, and retrieval evidence, then return advisory payloads
for the UI surfaces that already exist.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Iterable

from .models import Ticket, effective_hold_reason, is_sla_breached


CLOSED_STATES = {"Closed", "Resolved", "Closed Complete", "Closed Incomplete", "Closed Skipped", "Canceled"}
CLOSED_TASK_STATES = {"Closed", "Closed Complete", "Closed Incomplete", "Closed Skipped", "Canceled"}


def _ticket_ids(tickets: Iterable[Ticket]) -> list[str]:
    return sorted({ticket.number for ticket in tickets})


def _pending_tasks(ticket: Ticket) -> list[dict[str, object]]:
    return [
        task
        for task in [*ticket.ctasks, *ticket.ptasks, *ticket.sctasks]
        if str(task.get("state", "")) not in CLOSED_TASK_STATES
    ]


def _near_breach(ticket: Ticket) -> bool:
    return (
        ticket.type in {"INC", "RITM"}
        and not is_sla_breached(ticket)
        and ticket.sla_remaining_minutes is not None
        and 0 < ticket.sla_remaining_minutes <= 90
    )


def _sentiment_risk(ticket: Ticket) -> bool:
    if ticket.sentiment in {"Frustrated", "Impatient"}:
        return True
    customer_text = " ".join(entry.value.casefold() for entry in ticket.comments if entry.is_customer)
    return any(term in customer_text for term in ("blocked", "urgent", "immediately", "stuck", "vp"))


def _related_ids(tickets: Iterable[Ticket]) -> tuple[list[str], list[str]]:
    changes: set[str] = set()
    problems: set[str] = set()
    for ticket in tickets:
        if ticket.linked_chg and ticket.linked_chg.get("number"):
            changes.add(str(ticket.linked_chg["number"]))
        if ticket.linked_prb and ticket.linked_prb.get("number"):
            problems.add(str(ticket.linked_prb["number"]))
        for record in ticket.originating_tickets:
            number = str(record.get("number", ""))
            if number.startswith("CHG"):
                changes.add(number)
            if number.startswith("PRB"):
                problems.add(number)
    return sorted(changes), sorted(problems)


def _finding(
    *,
    finding_id: str,
    title: str,
    severity: str,
    explanation: str,
    evidence: list[str],
    tickets: Iterable[Ticket],
    confidence: int,
    action: str,
    action_reason: str,
    contributing_factor: str,
    expected_count: float | None = None,
) -> dict[str, object]:
    ticket_list = list(tickets)
    change_ids, problem_ids = _related_ids(ticket_list)
    related_evidence = [
        *( [f"Related Changes: {', '.join(change_ids)}"] if change_ids else [] ),
        *( [f"Related Problems: {', '.join(problem_ids)}"] if problem_ids else [] ),
    ]
    return {
        "id": finding_id,
        "title": title,
        "finding": title,
        "severity": severity,
        "current_count": len(ticket_list),
        "expected_count": expected_count,
        "explanation": explanation,
        "evidence": [*evidence, *related_evidence],
        # Existing assignment-group popup keys. Keeping this normalized avoids
        # a new presentation component or a parallel UI data shape.
        "supporting_evidence": [*evidence, *related_evidence],
        "related_ticket_ids": _ticket_ids(ticket_list),
        "ticket_ids": _ticket_ids(ticket_list),
        "related_change_ids": change_ids,
        "related_problem_ids": problem_ids,
        "possible_contributing_factor": contributing_factor,
        "confidence": confidence,
        "confidence_score": confidence,
        "recommended_action": action,
        "recommendation_reason": action_reason,
    }


def analyze_assignment_group_workload(
    tickets: list[Ticket],
    anomaly_insights: list[dict[str, object]],
) -> dict[str, object]:
    """Investigate an already-selected group's canonical workload.

    Existing anomaly detection remains the entry signal. This agent enriches
    that signal with exact relationship, duplicate, business-service, and
    priority evidence. It returns no findings when the evidence is not strong
    enough for an advisory conclusion.
    """

    findings: list[dict[str, object]] = []
    by_number = {ticket.number: ticket for ticket in tickets}

    for index, anomaly in enumerate(anomaly_insights):
        impacted = [by_number[number] for number in anomaly.get("ticket_ids", []) if number in by_number]
        if not impacted:
            continue
        changes, problems = _related_ids(impacted)
        contributing = (
            f"Linked Change {', '.join(changes)} is associated with the affected incidents."
            if changes else (
                f"Linked Problem {', '.join(problems)} indicates a recurring underlying issue."
                if problems else "The pattern is concentrated in the same operational category or business service."
            )
        )
        findings.append(_finding(
            finding_id=f"anomaly-{index + 1}",
            title=str(anomaly.get("title", "Unusual incident pattern")),
            severity=str(anomaly.get("severity", "MEDIUM")),
            explanation=str(anomaly.get("explanation", "An abnormal incident pattern was detected.")),
            evidence=[str(item) for item in anomaly.get("supporting_evidence", [])],
            tickets=impacted,
            confidence=int(anomaly.get("confidence_score", 75)),
            action=str(anomaly.get("recommended_action", "Investigate the affected incident pattern")),
            action_reason=str(anomaly.get("recommendation_reason", "The reported increase is above the prior trend.")),
            contributing_factor=contributing,
            expected_count=float(anomaly["expected_count"]) if anomaly.get("expected_count") is not None else None,
        ))

    active_incidents = [ticket for ticket in tickets if ticket.type == "INC" and ticket.state not in CLOSED_STATES]
    similar_incidents = [ticket for ticket in active_incidents if ticket.similar_records or ticket.historical_tickets]
    if len(similar_incidents) >= 2:
        findings.append(_finding(
            finding_id="duplicate-cluster",
            title="Repeated or similar incidents require correlation review",
            severity="HIGH" if len(similar_incidents) >= 3 else "MEDIUM",
            explanation=f"{len(similar_incidents)} active incidents have an existing similarity or historical-match signal.",
            evidence=[
                f"Tickets: {', '.join(_ticket_ids(similar_incidents))}",
                "Each record carries an existing similarity or historical evidence reference.",
            ],
            tickets=similar_incidents,
            confidence=min(94, 72 + len(similar_incidents) * 6),
            action="Correlate the matched incidents before opening duplicate work",
            action_reason="A shared resolution or a Problem record may prevent parallel troubleshooting.",
            contributing_factor="Existing similarity records indicate potentially repeated symptoms or a shared underlying cause.",
        ))

    service_groups: dict[str, list[Ticket]] = {}
    for ticket in active_incidents:
        service_groups.setdefault(ticket.business_service, []).append(ticket)
    for service, clustered in service_groups.items():
        if len(clustered) < 3:
            continue
        changes, problems = _related_ids(clustered)
        if not changes and not problems and not any(ticket.similar_records for ticket in clustered):
            continue
        findings.append(_finding(
            finding_id=f"service-{service.casefold().replace(' ', '-')}",
            title=f"Recurring incidents affect {service}",
            severity="HIGH" if any(is_sla_breached(ticket) for ticket in clustered) else "MEDIUM",
            explanation=f"{len(clustered)} active incidents in the selected scope affect the same business service.",
            evidence=[
                f"Business service: {service}",
                f"Active incident IDs: {', '.join(_ticket_ids(clustered))}",
            ],
            tickets=clustered,
            confidence=min(92, 68 + len(clustered) * 6),
            action="Review the shared service pattern and linked records",
            action_reason="A common service impact with linked change/problem evidence may warrant a coordinated Problem investigation.",
            contributing_factor=(f"Related Change {', '.join(changes)}" if changes else f"Related Problem {', '.join(problems)}" if problems else "Existing similarity evidence"),
        ))

    findings.sort(key=lambda item: (item["severity"] == "HIGH", item["confidence_score"], item["current_count"]), reverse=True)
    findings = findings[:5]
    return {
        "agent": "assignment_group_investigator",
        "findings": findings,
        "summary": f"{len(findings)} evidence-backed assignment-group finding{'s' if len(findings) != 1 else ''}." if findings else "",
    }


def analyze_assignee_workload(tickets: list[Ticket], assignee: str, report_end: date) -> dict[str, object]:
    """Prioritize an assignee's workload using canonical risk signals only."""

    scoped = [ticket for ticket in tickets if ticket.assigned_to == assignee or ticket.assignee == assignee]
    breached = [ticket for ticket in scoped if is_sla_breached(ticket)]
    near_breach = [ticket for ticket in scoped if _near_breach(ticket)]
    urgent_sentiment = [ticket for ticket in scoped if _sentiment_risk(ticket)]
    high_priority = [ticket for ticket in scoped if ticket.priority.startswith(("1 -", "2 -")) and ticket.state not in CLOSED_STATES]
    stale_problems = [ticket for ticket in scoped if ticket.type == "PRB" and _pending_tasks(ticket)]
    pending_changes = [ticket for ticket in scoped if ticket.type == "CHG" and _pending_tasks(ticket)]
    findings: list[dict[str, object]] = []

    risk_tickets = list({ticket.number: ticket for ticket in [*breached, *near_breach, *urgent_sentiment, *high_priority]}.values())
    if risk_tickets:
        def priority_score(ticket: Ticket) -> tuple[int, int, int, int]:
            return (
                int(is_sla_breached(ticket)),
                int(_near_breach(ticket)),
                int(_sentiment_risk(ticket)),
                int(ticket.priority.startswith("1 -")),
            )
        top = max(risk_tickets, key=priority_score)
        findings.append(_finding(
            finding_id="assignee-risk-priority",
            title=f"Prioritize {top.number} as the highest current workload risk",
            severity="HIGH" if breached or urgent_sentiment else "MEDIUM",
            explanation=(
                f"{len(breached)} breached, {len(near_breach)} near-breach, "
                f"{len(urgent_sentiment)} customer-urgency, and {len(high_priority)} high-priority ticket signals are in scope."
            ),
            evidence=[
                f"Breached: {', '.join(_ticket_ids(breached)) or 'none'}",
                f"Near breach: {', '.join(_ticket_ids(near_breach)) or 'none'}",
                f"Customer urgency: {', '.join(_ticket_ids(urgent_sentiment)) or 'none'}",
            ],
            tickets=risk_tickets,
            confidence=min(96, 75 + min(20, len(risk_tickets) * 3)),
            action=f"Prioritize {top.number} and its linked work first",
            action_reason="It has the strongest combined SLA, customer-impact, and priority signal in the assignee's current workload.",
            contributing_factor="SLA exposure, customer urgency, and priority combine into an immediate service-risk concentration.",
        ))

    if stale_problems:
        findings.append(_finding(
            finding_id="assignee-stale-problems",
            title="Open Problem work is delaying durable resolution",
            severity="HIGH" if any(ticket.priority.startswith("1 -") for ticket in stale_problems) else "MEDIUM",
            explanation=f"{len(stale_problems)} Problem record{'s' if len(stale_problems) != 1 else ''} has active PTasks requiring follow-through.",
            evidence=[f"Problems: {', '.join(_ticket_ids(stale_problems))}", f"Pending PTasks: {sum(len(_pending_tasks(ticket)) for ticket in stale_problems)}"],
            tickets=stale_problems,
            confidence=84,
            action="Drive the active RCA tasks before opening more workaround activity",
            action_reason="Completing the Problem investigation is the clearest path to prevent recurring incidents.",
            contributing_factor="Unfinished PTasks leave the underlying cause unresolved.",
        ))

    if pending_changes:
        findings.append(_finding(
            finding_id="assignee-pending-changes",
            title="Pending Change tasks are the delivery constraint",
            severity="HIGH" if any(ticket.priority.startswith("1 -") for ticket in pending_changes) else "MEDIUM",
            explanation=f"{len(pending_changes)} Change record{'s' if len(pending_changes) != 1 else ''} has open implementation work.",
            evidence=[f"Changes: {', '.join(_ticket_ids(pending_changes))}", f"Pending CTasks: {sum(len(_pending_tasks(ticket)) for ticket in pending_changes)}"],
            tickets=pending_changes,
            confidence=82,
            action="Confirm ownership and evidence for the next open Change task",
            action_reason="The documented implementation task is the known blocker to service recovery.",
            contributing_factor="Open CTasks prevent the linked remediation from being completed.",
        ))

    similar = [ticket for ticket in scoped if ticket.similar_records or ticket.historical_tickets]
    if len(similar) >= 2:
        findings.append(_finding(
            finding_id="assignee-similar-work",
            title="Similar work items can be investigated as one pattern",
            severity="MEDIUM",
            explanation=f"{len(similar)} tickets assigned to {assignee} have similarity or historical-match evidence.",
            evidence=[f"Tickets: {', '.join(_ticket_ids(similar))}"],
            tickets=similar,
            confidence=80,
            action="Review the shared evidence before continuing parallel investigation",
            action_reason="A common diagnosis or a linked Problem may reduce duplicate effort.",
            contributing_factor="Existing similarity records show related symptoms or historical resolutions.",
        ))

    findings.sort(key=lambda item: (item["severity"] == "HIGH", item["confidence_score"]), reverse=True)
    findings = findings[:3]
    return {
        "agent": "assignee_workload_investigator",
        "findings": findings,
        "summary": findings[0]["explanation"] if findings else "",
        "priority_ticket_id": findings[0]["ticket_ids"][0] if findings and findings[0]["ticket_ids"] else None,
        "report_end": report_end.isoformat(),
    }


def analyze_ticket(ticket: Ticket, related_records: list[Ticket], retrieval: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Build an evidence-backed ticket analysis without mutating canonical data."""

    related_changes, related_problems = _related_ids([ticket, *related_records])
    open_tasks = _pending_tasks(ticket)
    similar_ids = [str(record.get("id", "")) for record in [*ticket.similar_records, *ticket.historical_tickets] if record.get("id")]
    customer_updates = [entry for entry in ticket.comments if entry.is_customer]
    evidence = [
        f"State: {ticket.state}",
        f"Priority: {ticket.priority}",
        f"Assignment group: {ticket.assignment_group}",
        *( [f"SLA: breached"] if is_sla_breached(ticket) else [f"SLA: {ticket.sla_remaining_minutes} minutes remaining"] if ticket.sla_remaining_minutes is not None else [] ),
        *( [f"Customer updates: {len(customer_updates)}"] if customer_updates else [] ),
        *( [f"Open tasks: {len(open_tasks)}"] if open_tasks else [] ),
        *( [f"Similar/history: {', '.join(similar_ids[:3])}"] if similar_ids else [] ),
    ]
    related = [
        *( [f"Problems: {', '.join(related_problems)}"] if related_problems else [] ),
        *( [f"Changes: {', '.join(related_changes)}"] if related_changes else [] ),
        *( [f"Related incidents: {', '.join(_ticket_ids(related_records))}"] if related_records else [] ),
    ]
    if related_problems:
        likely_factor = f"The linked Problem record ({', '.join(related_problems)}) is the strongest current contributing-factor evidence."
    elif related_changes:
        likely_factor = f"The linked Change record ({', '.join(related_changes)}) should be investigated as a potential contributor."
    elif similar_ids:
        likely_factor = "Historical or similar-ticket evidence suggests a recurring pattern, but no single root cause is confirmed."
    elif effective_hold_reason(ticket):
        likely_factor = f"Progress is constrained by {effective_hold_reason(ticket).lower()}, rather than a confirmed technical root cause."
    else:
        likely_factor = "The current record contains no confirmed common-cause relationship; follow the ticket-specific resolution plan."
    retrieval_sources = [str(item.get("title", "")) for item in (retrieval or []) if item.get("title")][:3]
    confidence = 70 + min(12, len(ticket.ai_resolution_steps) * 3) + min(8, len(related)) + min(6, len(retrieval_sources) * 2)
    return {
        "agent": "ticket_investigator",
        "what_is_happening": f"{ticket.short_description}: {ticket.description}",
        "current_impact": f"The record is {ticket.state}" + (f" and SLA-breached" if is_sla_breached(ticket) else "") + ".",
        "evidence": evidence,
        "related_records": related or ["No related Incident, Problem, or Change is currently recorded."],
        "likely_contributing_factor": likely_factor,
        "recommended_next_steps": ticket.ai_resolution_steps,
        "retrieval_sources": retrieval_sources,
        "confidence_score": min(96, confidence),
    }
