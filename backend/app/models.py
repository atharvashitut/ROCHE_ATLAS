"""Mock enterprise ITSM records and health classification for the ATLAS demo."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .central_db import central_knowledge_references, register_ticket_records

HealthColor = Literal["RED", "YELLOW", "GREEN"]
TicketType = Literal["INC", "RITM", "PRB", "CHG"]
SlaStatus = Literal["BREACHED", "AT_RISK", "ON_TRACK"]
Sentiment = Literal["Frustrated", "Impatient", "Calm"]


ALL_ASSIGNMENT_GROUPS = [
    "SAP EWM Support",
    "Integration Middleware",
    "QMS Compliance Ops",
    "SAP Basis Ops",
    "Veeva Vault Admin",
    "AWS Cloud Infrastructure",
    "Oracle DB Services",
    "Workplace Technology",
    "Network Operations Center",
    "Cybersecurity Operations",
    "Identity & Access Management",
    "Service Desk L2",
    "Data Platform Engineering",
    "Salesforce Platform Support",
    "Microsoft 365 Collaboration",
    "Linux Server Operations",
    "Windows Server Operations",
    "Observability & Monitoring",
    "End User Compute",
    "Enterprise Integration Services",
    "SAP MM Support",
    "SAP SD Support",
    "SAP PLM Support",
]

# The demo uses one authoritative operational reporting period. Records that
# omit an explicit opened date are deterministically placed within this window
# so the default queue and executive statistics describe the same population.
CANONICAL_REPORT_START = date(2026, 7, 1)
CANONICAL_REPORT_END = date(2026, 10, 6)


class ServiceNowJournalEntry(BaseModel):
    """ServiceNow sys_journal_field entry used for comments and work notes."""

    sys_id: str
    element: Literal["comments", "work_notes"]
    sys_created_by: str
    sys_created_on: str
    value: str
    is_customer: bool


class TicketAttachment(BaseModel):
    """An openable evidence file linked to a ServiceNow record."""

    filename: str
    content_type: str
    size: str
    url: str


class Ticket(BaseModel):
    """A common ticket shape with metrics applicable to its ServiceNow type."""

    id: str
    sys_id: str = ""
    number: str = ""
    type: TicketType
    # Kept during the UI transition so existing ticket detail rendering remains compatible.
    record_type: TicketType
    title: str
    short_description: str = ""
    description: str
    state: str
    priority: str
    assignee: str
    assigned_to: str = ""
    caller_id: str = ""
    requested_for: str = ""
    assignment_group: str
    # ServiceNow classification fields used by operations analytics.  They are
    # derived once from the canonical ticket content when a record does not
    # explicitly provide them, so every API, chart, and RAG result uses the
    # same terminology.
    category: str = ""
    business_service: str = ""
    opened_on: str = ""
    sap_modules: list[str] = Field(default_factory=list)
    is_breached: bool = False
    # ServiceNow's hold reason is meaningful only while the record itself is
    # in the On Hold state. `on_hold_reason` remains only as a compatibility
    # alias for older mock-data callers.
    hold_reason: str | None = None
    on_hold_reason: str | None = None
    sla_status: SlaStatus | None = None
    sla_health: HealthColor | None = None
    sla_time_remaining: int | None = None
    sla_remaining_minutes: int | None = None
    sla_remaining_mins: int | None = None
    sla_remaining_percent: int | None = None
    sentiment: Sentiment | None = None
    rca_phase: str | None = None
    cab_status: str | None = None
    risk_level: str | None = None
    # Public topology fields follow the ServiceNow relationship direction for each
    # record type. The *_id fields below remain internal mock-data inputs only.
    parent_incident: dict[str, object] | None = None
    originating_tickets: list[dict[str, object]] = Field(default_factory=list)
    # Canonical relational IDs are the source of truth. Display snapshots are
    # rebuilt from these IDs so a parent view cannot drift from the child record.
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    child_tickets: list[dict[str, object]] = Field(default_factory=list)
    is_known_issue: bool = True
    parent_incident_id: str | None = Field(default=None, exclude=True)
    originating_ticket_ids: list[str] = Field(default_factory=list, exclude=True)
    child_incident_ids: list[str] = Field(default_factory=list, exclude=True)
    child_incidents: list[dict[str, object]] = Field(default_factory=list)
    linked_problem: str | None = Field(default=None, exclude=True)
    linked_change: str | None = Field(default=None, exclude=True)
    latest_work_notes: str
    closure_notes: str = ""
    resources: dict[str, str]
    chg_phase: str | None = None
    prb_phase: str | None = None
    work_notes: list[ServiceNowJournalEntry] = Field(default_factory=list)
    comments: list[ServiceNowJournalEntry] = Field(default_factory=list)
    attachments: list[TicketAttachment] = Field(default_factory=list)
    additional_comments: list[str] = Field(default_factory=list)
    ctasks: list[dict[str, object]] = Field(default_factory=list)
    ptasks: list[dict[str, object]] = Field(default_factory=list)
    sctasks: list[dict[str, object]] = Field(default_factory=list)
    close_code: str | None = None
    close_notes: str | None = None
    parent_inc: dict[str, object] | None = Field(default=None, exclude=True)
    child_incs: list[dict[str, object]] = Field(default_factory=list, exclude=True)
    linked_prb: dict[str, object] | None = None
    linked_chg: dict[str, object] | None = None
    knowledge_refs: list[dict[str, str]] = Field(default_factory=list)
    ai_resolution_guide: str = ""
    # Canonical, ticket-specific L2/L3 runbook material. These plans emulate
    # a consolidated AI result grounded in the ServiceNow record, linked work,
    # journal evidence, and connected knowledge sources.
    ai_resolution_summary: str = ""
    ai_resolution_steps: list[dict[str, str]] = Field(default_factory=list)
    similar_records: list[dict[str, object]] = Field(default_factory=list)
    historical_tickets: list[dict[str, object]] = Field(default_factory=list)

    @model_validator(mode="after")
    def enrich_servicenow_fields(self) -> "Ticket":
        """Populate consistent ServiceNow-native demo data from legacy-compatible fields."""

        self.sys_id = self.sys_id or hashlib.md5(self.id.encode()).hexdigest()
        if len(self.sys_id) != 32:
            raise ValueError("sys_id must be a 32-character GUID string")
        self.number = self.number or self.id
        self.short_description = self.short_description or self.title
        self.title = self.short_description
        self.assigned_to = self.assigned_to or self.assignee
        self.assignee = self.assigned_to
        # The canonical mock database carries a stable opened date for
        # reporting. Existing records are deterministically backfilled across
        # the previous four months so dashboard analytics behave like a real
        # ServiceNow reporting table rather than frontend fixture data.
        if not self.opened_on:
            # Keep every generated mock record within the same canonical
            # window used by the default Dashboard and Stats views.
            window_days = (CANONICAL_REPORT_END - CANONICAL_REPORT_START).days + 1
            offset = int(hashlib.sha256(self.number.encode()).hexdigest()[:8], 16) % window_days
            self.opened_on = (CANONICAL_REPORT_END - timedelta(days=offset)).isoformat()
        self.caller_id = self.caller_id or f"{self.assignment_group} Requester"
        self.requested_for = self.requested_for or self.caller_id
        priority_map = {"P1": "1 - Critical", "P2": "2 - High", "P3": "3 - Moderate", "P4": "4 - Low"}
        self.priority = priority_map.get(self.priority, self.priority)
        state_map = {"Fulfillment": "In Progress", "Root Cause Analysis": "Root Cause Analysis"}
        self.state = state_map.get(self.state, self.state)
        self.hold_reason = self.hold_reason or self.on_hold_reason
        if self.state != "On Hold":
            self.hold_reason = None
        self.on_hold_reason = self.hold_reason
        self.sla_remaining_minutes = self.sla_remaining_minutes if self.sla_remaining_minutes is not None else self.sla_remaining_mins
        # Retain the original field while API consumers migrate to the canonical name.
        self.sla_remaining_mins = self.sla_remaining_minutes
        self.sla_time_remaining = self.sla_remaining_minutes
        if self.sla_time_remaining is not None:
            self.sla_health = "RED" if self.sla_time_remaining <= 0 else "YELLOW" if self.sla_time_remaining <= 90 else "GREEN"
        self.parent_incident_id = self.parent_id or self.parent_incident_id
        self.parent_id = self.parent_incident_id
        self.child_incident_ids = self.child_ids or self.child_incident_ids
        self.child_ids = self.child_incident_ids
        self.sla_remaining_percent = self.sla_remaining_percent if self.sla_remaining_percent is not None else {
            "BREACHED": 15,
            "AT_RISK": 35,
            "ON_TRACK": 65,
        }.get(self.sla_status or "", None)
        self.work_notes = _normalise_journal_entries(
            self.work_notes or [self.latest_work_notes],
            element="work_notes",
            ticket=self,
        )
        source_comments = self.comments or self.additional_comments or [self.latest_work_notes]
        self.comments = _normalise_journal_entries(source_comments, element="comments", ticket=self)
        if self.type in {"INC", "RITM"}:
            self.additional_comments = [entry.value for entry in self.comments]
        self.ctasks = [_normalise_task(task, "ctask", self) for task in self.ctasks]
        self.ptasks = [_normalise_task(task, "ptask", self) for task in self.ptasks]
        self.sctasks = [_normalise_task(task, "sctask", self) for task in self.sctasks]
        closed_states = {"Closed", "Resolved", "Closed Complete", "Closed Incomplete", "Closed Skipped"}
        if self.state in closed_states:
            self.close_notes = self.close_notes or self.closure_notes
        else:
            self.close_notes = None
            self.close_code = None
        if self.type == "PRB":
            self.prb_phase = self.prb_phase or ("RCA" if self.rca_phase else "Assess")
        if self.type == "CHG":
            self.chg_phase = self.chg_phase or {"Scheduled": "Schedule", "Implement": "Implement", "Authorize": "Authorize", "Review": "Review", "Closed": "Closed"}.get(self.state, "Assess")
        self.knowledge_refs = central_knowledge_references(self.number, self.title) or self.knowledge_refs or _knowledge_references(self.number, self.title)
        self.ai_resolution_guide = self.ai_resolution_guide or (
            f"Confirm the reported impact, execute the approved remediation for {self.title}, "
            "validate service recovery with the requester, and document the evidence in work notes."
        )
        self.ai_resolution_summary = self.ai_resolution_summary or self.ai_resolution_guide
        self.sap_modules = self.sap_modules or _infer_sap_modules(self)
        self.category = self.category or self.sap_modules[0]
        self.business_service = self.business_service or _infer_business_service(self)
        return self


def _normalise_journal_entries(
    entries: list[ServiceNowJournalEntry] | list[str],
    *,
    element: Literal["comments", "work_notes"],
    ticket: Ticket,
) -> list[ServiceNowJournalEntry]:
    """Convert legacy mock strings to role-aware ServiceNow journal entries."""

    normalized: list[ServiceNowJournalEntry] = []
    for index, entry in enumerate(entries):
        if isinstance(entry, ServiceNowJournalEntry):
            normalized.append(entry)
            continue
        is_customer = element == "comments" and index % 2 == 0
        normalized.append(ServiceNowJournalEntry(
            sys_id=hashlib.md5(f"{ticket.id}-{element}-{index}".encode()).hexdigest(),
            element=element,
            sys_created_by=ticket.caller_id if is_customer else ticket.assigned_to,
            sys_created_on=f"2026-09-23 11:{10 + index * 5:02d}:00",
            value=entry,
            is_customer=is_customer,
        ))
    if element == "comments" and not any(not entry.is_customer for entry in normalized):
        normalized.append(ServiceNowJournalEntry(
            sys_id=hashlib.md5(f"{ticket.id}-comments-support".encode()).hexdigest(),
            element="comments",
            sys_created_by=ticket.assigned_to,
            sys_created_on="2026-09-23 11:30:00",
            value=ticket.latest_work_notes,
            is_customer=False,
        ))
    return normalized


def _infer_sap_modules(ticket: Ticket) -> list[str]:
    """Derive stable module tags from the canonical ticket content."""

    text = f"{ticket.short_description} {ticket.description} {ticket.assignment_group}".casefold()
    module_keywords = (
        ("SAP EWM", ("ewm", "warehouse", "qrf", "rf handheld")),
        ("SAP BASIS", ("basis", "netweaver", "sm37", "hana", "transport", "spool")),
        ("SAP MM", ("sap mm", "purchase order", "supplier master", "material master")),
        ("SAP SD", ("sap sd", "billing", "tax code", "sales")),
        ("SAP FICO", ("fico", "finance", "posting")),
        ("SAP PLM", ("plm", "ehs", "recipe")),
        ("SAP Security", ("authorization", "grc", "token", "su53")),
        ("SAP Middleware", ("middleware", "integration", "pi/po", "gateway")),
    )
    modules = [module for module, keywords in module_keywords if any(keyword in text for keyword in keywords)]
    return modules or ["Enterprise ITSM"]


def _infer_business_service(ticket: Ticket) -> str:
    """Map canonical SAP module tags to a stable ServiceNow service name."""

    module_to_service = {
        "SAP EWM": "SAP Warehouse Execution",
        "SAP BASIS": "SAP Technical Platform",
        "SAP MM": "SAP Materials Management",
        "SAP SD": "SAP Sales and Distribution",
        "SAP FICO": "SAP Finance and Controlling",
        "SAP PLM": "SAP Product Lifecycle Management",
        "SAP Security": "SAP Identity and Access",
        "SAP Middleware": "SAP Integration Platform",
    }
    return module_to_service.get(ticket.sap_modules[0] if ticket.sap_modules else "", "Enterprise ITSM Services")


def _normalise_task(task: dict[str, str], task_kind: str, ticket: Ticket) -> dict[str, str | list[str] | None]:
    """Map legacy task keys to native ServiceNow task REST fields and closure rules."""

    state_maps = {
        "ctask": {"Closed": "Closed Complete", "Open": "Open", "Pending": "Pending", "Closed Skipped": "Closed Skipped"},
        "ptask": {"Closed": "Closed", "Open": "Work in Progress", "Pending": "New", "Closed Skipped": "Canceled"},
        "sctask": {"Closed": "Closed Complete", "Open": "Open", "Pending": "Pending", "Closed Skipped": "Closed Skipped"},
    }
    state = state_maps[task_kind].get(task.get("state", ""), task.get("state", "New"))
    number = task.get("number") or task.get("id", "")
    is_closed = state.startswith("Closed") if task_kind != "ptask" else state == "Closed"
    close_notes = task.get("close_notes") if is_closed else None
    if is_closed and not close_notes:
        close_notes = "Task closure validated and documented."
    normalized: dict[str, str | list[str] | None] = {
        "sys_id": task.get("sys_id") or hashlib.md5(f"{ticket.number}-{number}".encode()).hexdigest(),
        "number": number,
        "short_description": task.get("short_description") or task.get("title", ""),
        "state": state,
        "assigned_to": task.get("assigned_to") or ticket.assigned_to,
        "comments": task.get("comments") or [],
        "close_notes": close_notes,
    }
    if task_kind == "ctask":
        normalized["change_task_type"] = task.get("change_task_type") or "Implementation"
        normalized["assignment_group"] = task.get("assignment_group") or ticket.assignment_group
    elif task_kind == "ptask":
        normalized["problem_task_type"] = task.get("problem_task_type") or "Investigation"
        normalized["assignment_group"] = task.get("assignment_group") or ticket.assignment_group
    return normalized


def _knowledge_references(number: str, title: str) -> list[dict[str, str]]:
    """Return three traceable knowledge sources for a mock enterprise record."""

    return [
        {
            "source_type": "ServiceNow KBA",
            "title": f"KBA — {title} recovery procedure",
            "path_or_url": f"https://servicenow.example.local/kb?id={number.lower()}-recovery",
            "summary": "Step-by-step validation and recovery checks for the reported service impact.",
        },
        {
            "source_type": "Veeva Vault SOP",
            "title": f"SOP — Controlled remediation for {number}",
            "path_or_url": f"Veeva Vault / QMS / SOPs / {number}-controlled-remediation.pdf",
            "summary": "Approved quality and compliance controls to apply while resolving this work item.",
        },
        {
            "source_type": "HP ALM Defect",
            "title": f"HP ALM Quality Center — Related defect analysis for {number}",
            "path_or_url": f"https://alm.roche.com/qcbin/defects?related_record={number}",
            "summary": "Related defect evidence, test execution history, and release-quality impact for this work item.",
        },
        {
            "source_type": "Google Drive KT/SUD Hub",
            "title": f"{number} KT Video Recording and SUD walkthrough PPT",
            "path_or_url": f"Google Drive / ATLAS / KT Hub / {number} / SUD-walkthrough.pptx | KT-video-recording",
            "summary": "Operational context, handover steps, and a recorded walkthrough for first-line resolution.",
        },
    ]


def is_sla_breached(ticket: Ticket) -> bool:
    """Return the single SLA-breach decision used by all ATLAS views.

    Problems and changes do not carry an SLA countdown in this demo; their
    operational risk is represented separately through phase and risk fields.
    """

    return ticket.type in {"INC", "RITM"} and (
        ticket.is_breached
        or (ticket.sla_remaining_minutes is not None and ticket.sla_remaining_minutes <= 0)
    )


def effective_hold_reason(ticket: Ticket) -> str | None:
    """Return a valid ServiceNow hold reason only for an On Hold record."""

    return ticket.hold_reason if ticket.state == "On Hold" else None


def calculate_health_color(ticket: Ticket) -> HealthColor:
    """Classify operational health from the metrics applicable to a ticket type."""

    if ticket.type in {"INC", "RITM"}:
        if ticket.sentiment == "Frustrated" or (ticket.sla_remaining_mins is not None and ticket.sla_remaining_mins <= 30):
            return "RED"
        if ticket.sentiment == "Impatient" or (ticket.sla_remaining_mins is not None and ticket.sla_remaining_mins <= 90):
            return "YELLOW"
        return "GREEN"
    if ticket.risk_level in {"High Impact", "Emergency Change"}:
        return "RED"
    return "GREEN"


def _journal_thread(
    ticket_id: str,
    *,
    requester: str,
    l1_support: str,
    l2_support: str,
    initial_report: str,
    monitoring_check: str,
    business_impact: str,
    diagnostic_update: str,
) -> list[dict[str, str | bool]]:
    """Create a sequential customer/L1/L2 ServiceNow additional-comments stream."""

    entries = [
        ("08:30:00", requester, True, initial_report),
        ("08:50:00", l1_support, False, f"Initial triage is complete. {monitoring_check}"),
        ("09:25:00", requester, True, f"Business impact update: {business_impact} Please confirm the expected next step and timing."),
        ("10:10:00", l2_support, False, f"L2 diagnostic update: {diagnostic_update} We will post the next update after validation."),
    ]
    return [
        {
            "sys_id": hashlib.md5(f"{ticket_id}-comments-{index}".encode()).hexdigest(),
            "element": "comments",
            "sys_created_by": author,
            "sys_created_on": f"2026-09-23 {created_at}",
            "value": value,
            "is_customer": is_customer,
        }
        for index, (created_at, author, is_customer, value) in enumerate(entries, start=1)
    ]


MOCK_DB: dict[str, Ticket] = {
    "INC0048102": Ticket(
        id="INC0048102", type="INC", record_type="INC", title="SAP EWM qRFC Queue Lock",
        description="A locked SAP EWM qRFC queue is blocking warehouse replication and delaying outbound processing.", state="In Progress",
        priority="P1", assignee="Maya Chen", caller_id="Elena Martins", assignment_group="SAP EWM Support", is_breached=True, on_hold_reason=None, sla_status="BREACHED", sla_remaining_minutes=-18, sla_remaining_percent=15, sentiment="Frustrated",
        child_incidents=[{"sys_id": "sys_inc_2", "number": "INC0048103", "short_description": "Token refresh failure for operations users", "state": "In Progress"}, {"sys_id": "sys_inc_x", "number": "INC0048109", "short_description": "Warehouse scanners unable to post goods issue", "state": "New"}], linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="SAP EWM support isolated a stuck qRFC queue owner after the replication job retry.",
        closure_notes="Pending validated queue unlock and confirmation from warehouse operations.",
        comments=[
            {"sys_id": "f3f59c2a7f574d148483000000000001", "element": "comments", "sys_created_by": "Elena Martins", "sys_created_on": "2026-09-23 08:30:00", "value": "Batch processing for warehouse goods issue failed in SAP EWM. Scanners are displaying authorization error SM12/qRFC queue lock.", "is_customer": True},
            {"sys_id": "f3f59c2a7f574d148483000000000002", "element": "comments", "sys_created_by": "Alex Rivera", "sys_created_on": "2026-09-23 08:45:00", "value": "Initial triage complete. Attempted manual qRFC queue flush in SolMan, but queue remained locked. Escalating to SAP EWM L2 Support.", "is_customer": False},
            {"sys_id": "f3f59c2a7f574d148483000000000003", "element": "comments", "sys_created_by": "Elena Martins", "sys_created_on": "2026-09-23 09:30:00", "value": "Our goods issue processing is blocked and the VP is asking for status immediately. The queue is still stuck!", "is_customer": True},
            {"sys_id": "f3f59c2a7f574d148483000000000004", "element": "comments", "sys_created_by": "Maya Chen", "sys_created_on": "2026-09-23 10:15:00", "value": "SAP EWM support is validating the qRFC queue owner and unlock procedure with the integration middleware team.", "is_customer": False},
            {"sys_id": "f3f59c2a7f574d148483000000000005", "element": "comments", "sys_created_by": "Elena Martins", "sys_created_on": "2026-09-23 11:10:00", "value": "Warehouse shift is ending in 1 hour. Can we get an ETA on the emergency patch deployment?", "is_customer": True},
            {"sys_id": "f3f59c2a7f574d148483000000000006", "element": "comments", "sys_created_by": "Maya Chen", "sys_created_on": "2026-09-23 11:15:00", "value": "Emergency patch CHG0092100 is approved and CTASK001 pre-patch backup is complete. Proceeding with qRFC queue unlock.", "is_customer": False},
        ],
        attachments=[
            {"filename": "qRFC_remediation_checklist.pdf", "content_type": "application/pdf", "size": "248 KB", "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"},
            {"filename": "sap_sm12_queue_lock_error.png", "content_type": "image/svg+xml", "size": "1.4 MB", "url": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='675'%3E%3Crect width='100%25' height='100%25' fill='%230f172a'/%3E%3Ctext x='70' y='130' fill='%2367e8f9' font-size='42' font-family='Arial'%3ESAP SM12 Queue Lock Evidence%3C/text%3E%3Ctext x='70' y='220' fill='%23e2e8f0' font-size='28' font-family='Arial'%3ELock owner: EWM_QRFC_REPL%3C/text%3E%3Ctext x='70' y='275' fill='%23fda4af' font-size='28' font-family='Arial'%3EStatus: Queue lock detected%3C/text%3E%3C/svg%3E"},
        ],
        resources={"KBA": "KBA-ATLAS-1042 — Desktop client authentication recovery", "Veeva": "Veeva Vault / Quality / ATLAS-Auth-Investigation", "GDrive": "ATLAS / Major Incidents / INC0048102"},
    ),
    "RITM0094101": Ticket(
        id="RITM0094101", type="RITM", record_type="RITM", title="Provision SAP EWM 1010 Sandbox Roles",
        description="Service request to provision approved SAP EWM 1010 sandbox roles for a project team.", state="Fulfillment",
        priority="P3", assignee="Priya Nair", assignment_group="SAP EWM Support", sla_status="ON_TRACK", sla_remaining_mins=360, sentiment="Calm",
        latest_work_notes="Role request validated against the approved sandbox access matrix and queued for provisioning.",
        closure_notes="Close after role assignment and requester confirmation.",
        comments=_journal_thread("RITM0094101", requester="Daniel Ruiz", l1_support="Alex Rivera", l2_support="Priya Nair", initial_report="I need SAP EWM 1010 sandbox roles for the warehouse test cycle beginning tomorrow.", monitoring_check="L1 verified the request approval, training evidence, and sandbox access matrix in ServiceNow.", business_impact="The project team cannot complete integration testing until the role assignment is available.", diagnostic_update="The approved roles are queued in the SAP access provisioning batch and the role matrix is being rechecked."),
        resources={"KBA": "KBA-EWM-1010 — Sandbox role provisioning", "Veeva": "Veeva Vault / Access / EWM-1010-Roles", "GDrive": "ATLAS / Service Requests / RITM0094101"},
    ),
    "INC0048103": Ticket(
        id="INC0048103", type="INC", record_type="INC", title="Token refresh failure for operations users",
        description="Child incident tracking the token refresh symptom reported by warehouse operations.", state="In Progress",
        priority="P2", assignee="Maya Chen", assignment_group="QMS Compliance Ops", sla_status="AT_RISK", sla_remaining_mins=85, sentiment="Impatient",
        parent_incident={"sys_id": "sys_inc_1", "number": "INC0048102", "short_description": "SAP EWM qRFC Queue Lock", "state": "In Progress"}, linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="Reproduced with the affected policy group and attached traces to the problem record.",
        closure_notes="Close after the corrective change has been verified in production.",
        comments=_journal_thread("INC0048103", requester="Elena Martins", l1_support="Alex Rivera", l2_support="Maya Chen", initial_report="Operations users cannot refresh their token after the warehouse sign-in screen times out.", monitoring_check="SolMan and identity monitoring show repeated refresh failures for the affected operations policy group.", business_impact="The morning shift is using manual workarounds and cannot complete normal scanner transactions.", diagnostic_update="The issue was reproduced with the affected policy group and traces were attached to the linked problem record."),
        resources={"KBA": "KBA-ATLAS-1042 — Desktop client authentication recovery", "Veeva": "Veeva Vault / Quality / Token-Refresh-Validation", "GDrive": "ATLAS / Major Incidents / INC0048103"},
    ),
    "INC0048109": Ticket(
        id="INC0048109", type="INC", record_type="INC", title="Warehouse scanners unable to post goods issue",
        description="Warehouse handheld scanners cannot post goods issue while the SAP EWM qRFC queue remains locked and memory pressure delays replication.", state="New",
        priority="P1", assignee="Maya Chen", assignment_group="SAP EWM Support", sla_status="AT_RISK", sla_remaining_mins=55, sentiment="Impatient",
        parent_incident={"sys_id": "sys_inc_1", "number": "INC0048102", "short_description": "SAP EWM qRFC Queue Lock", "state": "In Progress"},
        latest_work_notes="Warehouse operations supplied failed goods-issue timestamps for correlation with the qRFC queue backlog.",
        additional_comments=["Operators cannot confirm goods issue from affected scanner queues.", "Customer-visible update: SAP EWM support is correlating the scanner failures with the active qRFC recovery."],
        historical_tickets=[{"id": "INC0038810", "title": "Warehouse scanner posting delay", "resolution_date": "8 months ago", "close_notes_snippet": "Cleared the blocked qRFC queue after validating the warehouse replication worker.", "relevance_score": 76}],
        comments=_journal_thread("INC0048109", requester="Luca Bianchi", l1_support="Alex Rivera", l2_support="Maya Chen", initial_report="Warehouse scanners cannot post goods issue for the outbound queues.", monitoring_check="L1 correlated the scanner failures with the open SAP EWM qRFC backlog in SolMan.", business_impact="Outbound loading is accumulating and the shift supervisor needs a recovery estimate before the next carrier window.", diagnostic_update="SAP EWM L2 is correlating failed posting timestamps with the locked qRFC owner and memory-pressure alerts."),
        resources={"KBA": "KBA-SAP-EWM-1062 — Scanner goods issue queue recovery", "Veeva": "Veeva Vault / Warehouse / EWM-Scanner-Recovery-SOP", "GDrive": "ATLAS / SAP KT Hub / EWM / Scanner-goods-issue-recovery-video"},
    ),
    "PRB0019201": Ticket(
        id="PRB0019201", type="PRB", record_type="PRB", title="SAP EWM qRFC Queue Lock & Memory Exhaustion",
        description="Root-cause investigation into SAP EWM qRFC queue locks and memory exhaustion that stall warehouse replication.", state="Root Cause Analysis",
        priority="P1", assignee="Omar Rahman", assignment_group="Integration Middleware", rca_phase="RCA In Progress", risk_level="High Impact",
        originating_tickets=[{"sys_id": "sys_inc_1", "number": "INC0048102", "short_description": "SAP EWM qRFC Queue Lock", "state": "In Progress"}, {"sys_id": "sys_inc_x", "number": "INC0048109", "short_description": "Warehouse scanners unable to post goods issue", "state": "New"}], linked_change="CHG0092100",
        latest_work_notes="RCA isolated qRFC payload pressure and memory exhaustion during queue recovery.",
        closure_notes="Problem remains open until the queue tuning and emergency patch are validated in production.",
        ptasks=[{"id": "PTASK001", "title": "Collect qRFC queue lock traces", "state": "Closed"}, {"id": "PTASK002", "title": "Validate middleware retry policy", "state": "Work in Progress"}, {"id": "PTASK003", "title": "Review preventive monitoring threshold", "state": "New"}],
        resources={"KBA": "KBA-SAP-EWM-1057 — qRFC queue and memory recovery", "Veeva": "Veeva Vault / Quality / PRB0019201-RCA", "GDrive": "ATLAS / Problems / PRB0019201"},
    ),
    "CHG0092100": Ticket(
        id="CHG0092100", type="CHG", record_type="CHG", title="Emergency Patch for SAP EWM qRFC Queue Recovery",
        description="Emergency change to deploy the approved SAP EWM qRFC queue recovery patch.", state="Implement",
        priority="P2", assignee="Elena Rossi", assignment_group="Integration Middleware", cab_status="CAB Approved", risk_level="Emergency Change",
        originating_tickets=[{"sys_id": "sys_prb_1", "number": "PRB0019201", "short_description": "SAP EWM qRFC Queue Lock & Memory Exhaustion", "state": "Root Cause Analysis"}],
        latest_work_notes="Emergency CAB approved the controlled qRFC recovery patch and implementation is underway.",
        closure_notes="Post-implementation validation will confirm authentication and token refresh recovery.",
        ctasks=[{"id": "CTASK001", "title": "Pre-patch backup", "state": "Closed Complete", "close_notes": "Validated backup checksum and recovery point."}, {"id": "CTASK002", "title": "Deploy patch", "state": "Open"}],
        resources={"KBA": "KBA-ATLAS-1061 — Policy change validation", "Veeva": "Veeva Vault / Change Control / CHG0092100", "GDrive": "ATLAS / Changes / CHG0092100"},
    ),
    "INC0048104": Ticket(
        id="INC0048104", type="INC", record_type="INC", title="SAP EWM batch job authorization failure",
        description="Nightly EWM reconciliation batch cannot access the production job client.", state="In Progress",
        priority="P2", assignee="Jonas Weber", assignment_group="SAP Basis Ops", sla_status="AT_RISK", sla_remaining_mins=70, sentiment="Impatient",
        latest_work_notes="Basis team is validating the affected technical user authorization profile.",
        closure_notes="Close after the scheduled batch completes successfully and finance validates output.",
        historical_tickets=[{"id": "INC0031099", "title": "Batch user background auth failure", "resolution_date": "6 months ago", "close_notes_snippet": "Assigned SAP_ALL temporarily to batch user ALEREMOTE; permanently fixed via SU53 role adjustment.", "relevance_score": 85}, {"id": "RITM0088102", "title": "Missing background execution role", "resolution_date": "1 year ago", "close_notes_snippet": "Granted Z_BATCH_EXECUTION role to technical user.", "relevance_score": 78}],
        comments=_journal_thread("INC0048104", requester="Helen Foster", l1_support="Service Desk L1", l2_support="Jonas Weber", initial_report="The nightly EWM reconciliation batch fails with an authorization error in the production job client.", monitoring_check="L1 reviewed SM37 and the job-monitoring alert, then attached the available SU53 evidence.", business_impact="Finance reconciliation is delayed and the warehouse cannot complete the planned morning variance review.", diagnostic_update="SAP Basis is validating the technical-user authorization profile and segregation-of-duties controls."),
        resources={"KBA": "KBA-SAP-2024 — Batch authorization diagnostics", "Veeva": "Veeva Vault / SAP / Batch-Access", "GDrive": "ATLAS / Incidents / INC0048104"},
    ),
    "RITM0094102": Ticket(
        id="RITM0094102", type="RITM", record_type="RITM", title="Provision Veeva Vault quality reviewer role",
        description="Approved request to grant Quality Reviewer access to a Veeva Vault workspace.", state="Fulfillment",
        priority="P3", assignee="Sofia Moretti", assignment_group="Veeva Vault Admin", sla_status="ON_TRACK", sla_remaining_mins=540, sentiment="Calm",
        latest_work_notes="Requester approval and training evidence were verified; access is queued for the next fulfillment cycle.",
        closure_notes="Close after access confirmation and audit trail verification.",
        comments=_journal_thread("RITM0094102", requester="Amira Khan", l1_support="Service Desk L1", l2_support="Sofia Moretti", initial_report="Please provision the approved Quality Reviewer role in Veeva Vault for the upcoming document review cycle.", monitoring_check="L1 confirmed manager approval, required training, and the requester's active Vault account.", business_impact="The reviewer cannot complete the controlled SOP review before the scheduled quality gate.", diagnostic_update="Veeva administration verified the role mapping and queued it for the next controlled fulfillment cycle."),
        resources={"KBA": "KBA-VEEVA-081 — Quality reviewer fulfillment", "Veeva": "Veeva Vault / Access / RITM0094102", "GDrive": "ATLAS / Service Requests / RITM0094102"},
    ),
    "INC0048105": Ticket(
        id="INC0048105", type="INC", record_type="INC", title="AWS data ingestion worker capacity alarm",
        description="Data ingestion workers are saturated and delaying regulated reporting feeds.", state="In Progress",
        priority="P1", assignee="Avery Brooks", assignment_group="AWS Cloud Infrastructure", sla_status="BREACHED", sla_remaining_mins=25, sentiment="Frustrated",
        latest_work_notes="On-call engineers are increasing worker capacity while investigating the traffic anomaly.",
        closure_notes="Close after sustained queue recovery and reporting-feed validation.",
        comments=_journal_thread("INC0048105", requester="Regulatory Reporting Team", l1_support="Cloud Operations L1", l2_support="Avery Brooks", initial_report="The regulated reporting feed is delayed because AWS ingestion workers are saturated.", monitoring_check="Cloud monitoring confirmed queue depth growth and worker-capacity alarms across the ingestion tier.", business_impact="The reporting team may miss the regulated submission preparation window if the backlog is not reduced.", diagnostic_update="Cloud infrastructure is scaling the worker pool while isolating the traffic anomaly and validating downstream throughput."),
        resources={"KBA": "KBA-AWS-211 — Worker capacity response", "Veeva": "Veeva Vault / Cloud / Ingestion-Capacity", "GDrive": "ATLAS / Incidents / INC0048105"},
    ),
    "PRB0019202": Ticket(
        id="PRB0019202", type="PRB", record_type="PRB", title="SAP PLM Recipe Sync API Exhaustion",
        description="SAP PLM recipe synchronization exhausts the API retry pool and leaves formulation updates unprocessed.", state="Root Cause Analysis",
        priority="P1", assignee="Lea Fischer", assignment_group="SAP PLM Support", rca_phase="RCA In Progress", risk_level="High Impact",
        latest_work_notes="API trace shows recipe synchronization retries exhausting the downstream connection pool.",
        closure_notes="Problem remains open until the retry policy and API pool fix are validated.",
        ptasks=[{"id": "PTASK001", "title": "Capture Recipe Sync API retry trace", "state": "Open"}, {"id": "PTASK002", "title": "Validate API pool remediation", "state": "Closed", "close_notes": "Validated corrected API pool sizing in the controlled test tenant."}],
        resources={"KBA": "KBA-SAP-PLM-060 — Recipe Sync API exhaustion", "Veeva": "Veeva Vault / QMS / PLM-Recipe-API-SOP", "GDrive": "ATLAS / Problems / PRB0019202"},
    ),
    "INC0048110": Ticket(
        id="INC0048110", type="INC", record_type="INC", title="SAP MM PO Workflow Release Failure",
        description="Purchase orders in SAP MM remain stuck in the approval workflow and cannot be released to suppliers.", state="On Hold",
        priority="P2", assignee="Nina Keller", assignment_group="SAP MM Support", is_breached=True, on_hold_reason="Awaiting Change", sla_status="AT_RISK", sla_remaining_minutes=-45, sentiment="Impatient",
        child_incident_ids=["INC0048111"], latest_work_notes="Workflow agent trace shows a missing substitution rule after the latest purchasing-org update.",
        closure_notes="Close after test POs complete approval and the buyer confirms release processing.",
        additional_comments=["Buyers report that high-priority PO approvals have been waiting longer than two hours.", "SAP MM support is comparing the affected purchasing organization to the working template."],
        similar_records=[{"id": "PRB0018992", "score": 95, "title": "Historical Root Cause: PO Release Strategy Config Corruption", "state": "Closed", "resolution_date": "Last Month"}],
        historical_tickets=[{"id": "INC0042911", "title": "PO Release Strategy sync failure", "resolution_date": "3 months ago", "close_notes_snippet": "Restarted the PO release workflow in SWPR. Users were able to approve immediately after.", "relevance_score": 82}],
        comments=_journal_thread("INC0048110", requester="Mark Vance", l1_support="Procurement Service Desk", l2_support="Nina Keller", initial_report="Purchase orders are stuck in the SAP MM approval workflow and cannot be released to suppliers.", monitoring_check="L1 reviewed workflow logs and found the affected purchasing organization differs from the working template.", business_impact="Urgent purchase orders are waiting for approval and buyers are escalating before the supplier cut-off.", diagnostic_update="SAP MM L2 isolated a missing substitution rule and is awaiting the controlled change needed for the purchasing-organization configuration."),
        attachments=[
            {"filename": "po_release_authorization_failure.png", "content_type": "image/svg+xml", "size": "876 KB", "url": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='675'%3E%3Crect width='100%25' height='100%25' fill='%230f172a'/%3E%3Ctext x='70' y='130' fill='%2367e8f9' font-size='42' font-family='Arial'%3ESAP MM PO Release Authorization Failure%3C/text%3E%3Ctext x='70' y='220' fill='%23e2e8f0' font-size='28' font-family='Arial'%3EPurchasing org: 1010%3C/text%3E%3Ctext x='70' y='275' fill='%23fda4af' font-size='28' font-family='Arial'%3EMissing substitution rule%3C/text%3E%3C/svg%3E"},
        ],
        resources={"KBA": "KBA-SAP-MM-118 — PO workflow release diagnosis", "Veeva": "Veeva Vault / Procurement / MM-Workflow-SOP", "GDrive": "ATLAS / SAP KT Hub / MM / PO-workflow-SUD.pptx"},
    ),
    "INC0048111": Ticket(
        id="INC0048111", type="INC", record_type="INC", title="SAP MM PO Workflow Child Approval Exception",
        description="Child incident for a purchasing group whose PO approval substitution rule is not being applied.", state="In Progress",
        priority="P2", assignee="Nina Keller", assignment_group="SAP MM Support", sla_status="AT_RISK", sla_remaining_mins=90, sentiment="Impatient",
        parent_incident_id="INC0048110", latest_work_notes="Approval exception has been isolated to the purchasing-group substitution configuration.",
        closure_notes="Close after the substitution rule is restored and PO approval completes.",
        additional_comments=["Buyer supplied a failing PO example and approval timestamp.", "Customer-visible update: the purchasing group exception is under active correction."],
        comments=_journal_thread("INC0048111", requester="Mark Vance", l1_support="Procurement Service Desk", l2_support="Nina Keller", initial_report="A purchasing-group approval substitution is not being applied to the submitted PO.", monitoring_check="L1 verified the failing PO and timestamp against the parent SAP MM workflow incident.", business_impact="The buyer cannot approve the order and needs the exception corrected before today's purchasing run.", diagnostic_update="SAP MM L2 confirmed the child exception is tied to the missing purchasing-group substitution configuration."),
        resources={"KBA": "KBA-SAP-MM-119 — PO approval child exception", "Veeva": "Veeva Vault / Procurement / MM-Workflow-SOP", "GDrive": "ATLAS / SAP KT Hub / MM / PO-approval-child-SUD.pdf"},
    ),
    "INC0048112": Ticket(
        id="INC0048112", type="INC", record_type="INC", title="SAP SD Billing Document IDoc Failure",
        description="SAP SD billing IDocs failed during invoice document generation for completed deliveries.", state="Resolved",
        priority="1 - Critical", assignee="Marco Silva", assignment_group="SAP SD Support", sla_status="ON_TRACK", sla_remaining_mins=180, sentiment="Calm",
        latest_work_notes="Corrected the pricing condition mapping and completed a monitored billing IDoc reprocess.",
        closure_notes="Billing IDocs were reprocessed successfully and finance confirmed invoice postings.", close_code="Solved (Permanently)",
        additional_comments=["Finance was notified that the billing document reprocess completed successfully.", "Customer-visible update: delayed invoices are now available for posting."],
        comments=_journal_thread("INC0048112", requester="Finance Operations", l1_support="Finance Service Desk", l2_support="Marco Silva", initial_report="Billing document IDocs failed and completed deliveries are not generating invoices.", monitoring_check="L1 checked the IDoc monitor and confirmed the failure is limited to the affected pricing-condition mapping.", business_impact="Finance cannot post the delayed invoices until the failed IDocs are recovered.", diagnostic_update="SAP SD corrected the mapping and completed a monitored IDoc reprocess; finance validation is in progress."),
        resources={"KBA": "KBA-SAP-SD-207 — Billing IDoc recovery", "Veeva": "Veeva Vault / Finance / SD-Billing-Control", "GDrive": "ATLAS / SAP KT Hub / SD / Billing-IDoc-recovery-video"},
    ),
    "PRB0019203": Ticket(
        id="PRB0019203", type="PRB", record_type="PRB", title="SAP PLM Recipe Sync Integration Failure",
        description="Recipe master data updates from SAP PLM are not synchronizing to the downstream formulation service.", state="Root Cause Analysis",
        priority="P1", assignee="Lea Fischer", assignment_group="SAP PLM Support", rca_phase="RCA In Progress", risk_level="High Impact",
        latest_work_notes="Integration logs show a schema mismatch after the latest recipe attribute extension.",
        closure_notes="Problem remains open until the corrected mapping passes recipe sync and audit checks.",
        ptasks=[{"id": "PTASK101", "title": "Compare PLM recipe payload schemas", "state": "Closed"}, {"id": "PTASK102", "title": "Correct downstream attribute mapping", "state": "Open"}, {"id": "PTASK103", "title": "Execute regulated recipe sync validation", "state": "Pending"}],
        resources={"KBA": "KBA-SAP-PLM-054 — Recipe synchronization triage", "Veeva": "Veeva Vault / QMS / PLM-Recipe-Integration-SOP", "GDrive": "ATLAS / SAP KT Hub / PLM / Recipe-sync-SUD.pdf"},
    ),
    "RITM0094103": Ticket(
        id="RITM0094103", type="RITM", record_type="RITM", title="SAP Basis SU53 Authorization Role Grant",
        description="Request to correct missing SU53 authorization for a controlled SAP Basis batch job.", state="Closed Complete",
        priority="P2", assignee="Jonas Weber", assignment_group="SAP Basis Ops", sla_status="ON_TRACK", sla_remaining_mins=300, sentiment="Calm",
        latest_work_notes="Requested authorization object was verified against the batch job role design and segregation-of-duties control.",
        closure_notes="Role transport was validated and the batch job completed without SU53 errors.", close_code="Successful",
        additional_comments=["Job owner attached the SU53 trace from the failed overnight run.", "Basis and authorization teams confirmed the requested change requires controlled role approval."],
        comments=_journal_thread("RITM0094103", requester="Nora Patel", l1_support="Service Desk L1", l2_support="Jonas Weber", initial_report="Please grant the approved SAP Basis role required to resolve the SU53 error on the overnight batch job.", monitoring_check="L1 reviewed the submitted SU53 trace, approval evidence, and affected job details.", business_impact="The batch owner cannot complete the next controlled processing run without the authorization correction.", diagnostic_update="Basis and authorization teams validated the role transport and requested a final batch-job confirmation from the requester."),
        sctasks=[{"id": "SCTASK001", "title": "Validate SU53 authorization trace", "state": "Closed Complete", "close_notes": "Role assignment validated against the approved trace."}],
        resources={"KBA": "KBA-SAP-BASIS-310 — SU53 batch-job authorization", "Veeva": "Veeva Vault / Access / SAP-Basis-Authorization-SOP", "GDrive": "ATLAS / SAP KT Hub / Basis / SU53-authorization-video"},
    ),
    "PRB0018992": Ticket(
        id="PRB0018992", type="PRB", record_type="PRB", title="Historical Root Cause: PO Release Strategy Config Corruption",
        description="Historical SAP MM problem in which a corrupted release strategy configuration blocked purchase order workflow approvals.", state="Closed",
        priority="P1", assignee="Nina Keller", assignment_group="SAP MM Support", rca_phase="RCA", risk_level="High Impact",
        latest_work_notes="Historical review confirmed release strategy configuration corruption in the purchasing organization.",
        closure_notes="Applied SAP Note 2839211 to fix release workflow config.", close_code="Solved (Permanently)",
        ptasks=[{"id": "PTASK8992", "title": "Validate SAP Note 2839211 implementation", "state": "Closed", "close_notes": "Release strategy validation completed successfully."}],
        resources={"KBA": "KBA-SAP-MM-094 — Release strategy configuration recovery", "Veeva": "Veeva Vault / Procurement / MM-Release-Strategy-SOP", "GDrive": "ATLAS / SAP KT Hub / MM / Release-strategy-RCA.pptx"},
    ),
    "INC0048120": Ticket(
        id="INC0048120", type="INC", record_type="INC", title="SolMan Alert: SM37 Batch Job Z_EWM_RECON_NIGHTLY failed with ABAP dump",
        description="SolMan Technical Monitoring detected job Z_EWM_RECON_NIGHTLY canceled in client 100 with dump ITAB_ERROR_IN_INITIAL_SIZE.", state="On Hold",
        priority="P1", assignee="Jonas Weber", assignment_group="SAP Basis Ops", is_breached=True, on_hold_reason="Awaiting Vendor", sla_status="BREACHED", sla_remaining_minutes=-120, sentiment="Frustrated",
        latest_work_notes="Basis on-call is reviewing SM37 spool and ST22 dump evidence for the nightly EWM reconciliation run.",
        additional_comments=["SolMan monitoring raised a P1 alert after the nightly reconciliation job canceled.", "Warehouse reconciliation is delayed pending batch job recovery."],
        similar_records=[{"id": "INC0048121", "score": 98, "title": "Duplicate: Nightly EWM reconciliation job cancellation alert", "state": "New", "resolution_date": "Current Triage Queue"}],
        knowledge_refs=[{"source_type": "ServiceNow KBA", "title": "SolMan KBA — SM37 batch job dump recovery", "path_or_url": "https://servicenow.example.local/kb?id=solman-sm37-itab-error", "summary": "Guided SM37, ST22, and job-log triage for failed EWM batch runs."}, {"source_type": "Veeva Vault SOP", "title": "SAP Note 2491021 controlled implementation SOP", "path_or_url": "Veeva Vault / QMS / SAP Notes / 2491021.pdf", "summary": "Controlled review procedure for SAP Note 2491021 and related monitoring fixes."}, {"source_type": "Google Drive KT/SUD Hub", "title": "SolMan job monitoring KT video", "path_or_url": "Google Drive / ATLAS / KT Hub / SolMan / SM37-job-monitoring-video", "summary": "Recorded walkthrough for identifying redundant SolMan monitoring alerts."}],
        comments=_journal_thread("INC0048120", requester="Warehouse Operations", l1_support="Monitoring Service Desk", l2_support="Jonas Weber", initial_report="SolMan alerted that Z_EWM_RECON_NIGHTLY failed with an ABAP dump in client 100.", monitoring_check="L1 reviewed the SM37 status, ST22 notification, and the correlated SolMan monitoring event.", business_impact="Warehouse reconciliation is delayed and operations need to know whether the nightly result can be recovered before shift handover.", diagnostic_update="SAP Basis is reviewing spool and dump evidence while the external support vendor confirms the recommended remediation path."),
        resources={"KBA": "KBA-SOLMAN-212 — SM37 job cancellation", "Veeva": "Veeva Vault / QMS / SAP Note 2491021", "GDrive": "ATLAS / SolMan KT / SM37-monitoring-video"},
    ),
    "INC0048121": Ticket(
        id="INC0048121", type="INC", record_type="INC", title="Duplicate SolMan Alert: Batch Job Z_EWM_RECON_NIGHTLY canceled",
        description="Automated alert trigger for failed job Z_EWM_RECON_NIGHTLY.", state="New",
        priority="P1", assignee="Triage Queue", assignment_group="Observability & Monitoring", sla_status="AT_RISK", sla_remaining_mins=45, sentiment="Impatient",
        latest_work_notes="Alert correlation engine flagged this event as a likely duplicate of the SAP Basis incident.",
        additional_comments=["Automated monitoring opened this alert from the same nightly EWM reconciliation job cancellation.", "Triage should link this duplicate to the active SAP Basis investigation."],
        similar_records=[{"id": "INC0048120", "score": 98, "title": "SolMan Alert: SM37 Batch Job Z_EWM_RECON_NIGHTLY failed with ABAP dump", "state": "In Progress", "resolution_date": "Active Work Item"}],
        comments=_journal_thread("INC0048121", requester="Monitoring Automation", l1_support="Monitoring Service Desk", l2_support="Triage Queue", initial_report="Automated monitoring created a second alert for the canceled Z_EWM_RECON_NIGHTLY batch job.", monitoring_check="L1 compared the event key, timestamps, and job name with the open SAP Basis incident.", business_impact="Duplicate paging is distracting the on-call team while the primary batch-job recovery is underway.", diagnostic_update="The triage queue confirmed a high-confidence duplicate match and is preparing the incident linkage to the primary investigation."),
        resources={"KBA": "KBA-SOLMAN-212 — SM37 job cancellation", "Veeva": "Veeva Vault / QMS / SAP Note 2491021", "GDrive": "ATLAS / SolMan KT / Alert-correlation-SUD.pptx"},
    ),
    "PRB0019205": Ticket(
        id="PRB0019205", type="PRB", record_type="PRB", title="SolMan ChaRM Transport Synchronization Failure during Cutover",
        description="SolMan ChaRM release transport failed to sync with SAP PLM QA environment.", state="Root Cause Analysis",
        priority="P2", assignee="Mira Desai", assignment_group="Workplace Technology", rca_phase="RCA In Progress", risk_level="High Impact",
        latest_work_notes="ALM engineering is correlating ChaRM and STMS logs from the QA cutover window.",
        ptasks=[{"id": "PTASK00101", "title": "Analyze SolMan transport log STMS", "state": "Closed", "close_notes": "Log confirmed target buffer deadlock in QA instance."}, {"id": "PTASK00102", "title": "Re-align ChaRM project landscape buffer", "state": "Work in Progress", "close_notes": None}],
        resources={"KBA": "KBA-SOLMAN-310 — ChaRM transport synchronization", "Veeva": "Veeva Vault / QMS / ChaRM-Cutover-SOP", "GDrive": "ATLAS / SolMan KT / ChaRM-STMS-analysis-video"},
    ),
    "INC0048122": Ticket(
        id="INC0048122", type="INC", record_type="INC", title="HP ALM to ServiceNow defect sync error for SAP SD release",
        description="Automated API bridge failed to sync ALM Defect #4091 into ServiceNow Change CHG0092100.", state="In Progress",
        priority="P3", assignee="Avery Brooks", assignment_group="Enterprise Integration Services", sla_status="AT_RISK", sla_remaining_mins=110, sentiment="Impatient",
        latest_work_notes="Integration support is replaying the failed defect payload and validating the CHG0092100 mapping.",
        additional_comments=["Release manager reported that ALM Defect #4091 is missing from the ServiceNow change record.", "Customer-visible update: API bridge replay is in progress."],
        similar_records=[{"id": "PRB0019205", "score": 85, "title": "SolMan ChaRM Transport Synchronization Failure", "state": "Root Cause Analysis", "resolution_date": "Active PRB"}],
        comments=_journal_thread("INC0048122", requester="Release Management", l1_support="Integration Service Desk", l2_support="Avery Brooks", initial_report="HP ALM Defect 4091 did not synchronize into ServiceNow change CHG0092100 for the SAP SD release.", monitoring_check="L1 verified the API bridge failure and captured the failed payload correlation identifier.", business_impact="The release manager cannot complete change evidence and needs the defect record visible before the deployment review.", diagnostic_update="Enterprise integration support is replaying the payload and validating the HP ALM-to-ServiceNow field mapping."),
        resources={"KBA": "KBA-ALM-4091 — HP ALM to ServiceNow sync", "Veeva": "Veeva Vault / QMS / ALM-ServiceNow-Bridge-SOP", "GDrive": "ATLAS / ALM KT / Defect-sync-replay-SUD.pdf"},
    ),
    "INC0048125": Ticket(
        id="INC0048125", type="INC", record_type="INC", title="SAP SD Customer Tax Code Clarification Required",
        description="Billing processing is paused while the caller confirms the required customer tax-code treatment for the release.", state="On Hold",
        priority="P2", assignee="Marco Silva", assignment_group="SAP SD Support", is_breached=True, on_hold_reason="Awaiting Caller", sla_status="BREACHED", sla_remaining_minutes=-15, sentiment="Impatient",
        latest_work_notes="SAP SD support requested the caller's confirmation of the tax-code scenario before the approved correction can proceed.",
        closure_notes="Close after the caller confirms the tax-code treatment and billing completes successfully.",
        additional_comments=["Finance needs clarification on the customer tax-code scenario before the billing correction is applied.", "Customer-visible update: SAP SD support is awaiting the requested tax-code confirmation."],
        comments=_journal_thread("INC0048125", requester="Finance Operations", l1_support="Finance Service Desk", l2_support="Marco Silva", initial_report="Billing is paused because the customer tax-code treatment requires clarification for this SAP SD release.", monitoring_check="L1 reviewed the billing log and confirmed the exception is limited to the unresolved customer tax-code scenario.", business_impact="The billing team cannot process the affected customer invoices until the tax-code decision is confirmed.", diagnostic_update="SAP SD support documented the required tax-code options and is awaiting caller confirmation before applying the controlled correction."),
        resources={"KBA": "KBA-SAP-SD-221 — Customer tax-code billing validation", "Veeva": "Veeva Vault / Finance / SD-Tax-Code-Control", "GDrive": "ATLAS / SAP KT Hub / SD / Customer-tax-code-billing-SUD.pdf"},
    ),
}


# The active demo catalog is deliberately small but fully relational.  Keep
# relationship identifiers here (rather than duplicate child snapshots) and
# resolve snapshots at API time to guarantee journal/status synchronisation.
MOCK_DB.update({
    "INC0048102": Ticket(
        id="INC0048102", type="INC", record_type="INC", title="SAP EWM qRFC Queue Lock & Batch Auth Failure",
        description="SAP EWM qRFC queue locking and batch authorization failures are blocking goods issue processing across the warehouse estate.",
        state="In Progress", priority="P1", assignee="Maya Chen", caller_id="Elena Martins", assignment_group="SAP EWM Support",
        is_breached=True, sla_status="BREACHED", sla_remaining_minutes=-18, sla_remaining_percent=15, sentiment="Frustrated",
        child_ids=["INC0048103", "INC0048109", "INC0048144"], linked_problem="PRB0031022", linked_change="CHG0092100",
        latest_work_notes="L2 isolated the locked qRFC owner and is coordinating the emergency recovery with Basis and Security.",
        comments=[
            {"sys_id": "8102c001000000000000000000000001", "element": "comments", "sys_created_by": "Elena Martins", "sys_created_on": "2026-09-23 08:30:00", "value": "Batch processing for warehouse goods issue failed in SAP EWM. Scanners show an authorization error and an SM12/qRFC queue lock.", "is_customer": True},
            {"sys_id": "8102c002000000000000000000000002", "element": "comments", "sys_created_by": "Alex Rivera", "sys_created_on": "2026-09-23 08:45:00", "value": "Initial L1 triage is complete. A SolMan queue flush was attempted, but the queue remains locked; escalating to SAP EWM L2.", "is_customer": False},
            {"sys_id": "8102c003000000000000000000000003", "element": "comments", "sys_created_by": "Elena Martins", "sys_created_on": "2026-09-23 09:30:00", "value": "Goods issue processing is blocked and the VP is asking for status immediately. The queue is still stuck.", "is_customer": True},
            {"sys_id": "8102c004000000000000000000000004", "element": "comments", "sys_created_by": "Maya Chen", "sys_created_on": "2026-09-23 10:15:00", "value": "SAP EWM L2 is validating qRFC ownership and the batch authorization path with Basis and the integration middleware team.", "is_customer": False},
            {"sys_id": "8102c005000000000000000000000005", "element": "comments", "sys_created_by": "Elena Martins", "sys_created_on": "2026-09-23 11:10:00", "value": "Warehouse shift ends in one hour. Please confirm the ETA for the emergency recovery.", "is_customer": True},
            {"sys_id": "8102c006000000000000000000000006", "element": "comments", "sys_created_by": "Maya Chen", "sys_created_on": "2026-09-23 11:15:00", "value": "CHG0092100 is approved, the pre-patch backup is complete, and the team is proceeding with controlled qRFC queue unlock.", "is_customer": False},
        ],
        attachments=[
            {"filename": "qRFC_remediation_checklist.pdf", "content_type": "application/pdf", "size": "248 KB", "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"},
            {"filename": "sap_sm12_queue_lock_error.png", "content_type": "image/svg+xml", "size": "1.4 MB", "url": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='675'%3E%3Crect width='100%25' height='100%25' fill='%230f172a'/%3E%3Ctext x='70' y='130' fill='%2367e8f9' font-size='42' font-family='Arial'%3ESAP SM12 Queue Lock Evidence%3C/text%3E%3C/svg%3E"},
        ],
        resources={"KBA": "KBA003192 — SAP EWM qRFC Queue Lock Resolution", "Veeva": "Veeva Vault / QMS / Batch access controls", "GDrive": "ATLAS / EWM / qRFC recovery KT"},
    ),
    "INC0048103": Ticket(
        id="INC0048103", type="INC", record_type="INC", title="Token Refresh & Authorization Failure (Object M_MSEG_LGO)",
        description="SAP Security/GRC authorization checks fail while refreshing warehouse operations tokens for object M_MSEG_LGO.",
        state="In Progress", priority="P2", assignee="Nina Keller", caller_id="Elena Martins", assignment_group="Identity & Access Management",
        sla_status="AT_RISK", sla_remaining_minutes=65, sentiment="Impatient", parent_id="INC0048102",
        latest_work_notes="Security L2 reproduced the missing M_MSEG_LGO object authorization and is validating the controlled role correction.",
        comments=_journal_thread("INC0048103", requester="Elena Martins", l1_support="Alex Rivera", l2_support="Nina Keller", initial_report="Warehouse operators cannot refresh the mobile token and receive an M_MSEG_LGO authorization error.", monitoring_check="L1 checked GRC request history and gateway authentication traces.", business_impact="The affected users are unable to confirm goods movement during the current shift.", diagnostic_update="Security L2 reproduced the failed object check and is validating the approved role delta."),
        resources={"KBA": "KB0062011 — GRC authorization remediation", "Veeva": "Veeva Vault / QMS / GRC role validation", "GDrive": "ATLAS / Security / M_MSEG_LGO KT"},
    ),
    "INC0048109": Ticket(
        id="INC0048109", type="INC", record_type="INC", title="RF Handheld Gateway Connection Timeout on Node 02",
        description="SAP BASIS/NetWeaver RF handheld gateway connections time out on node 02 while EWM queues are under recovery.",
        state="In Progress", priority="P2", assignee="Jonas Weber", caller_id="Luca Bianchi", assignment_group="SAP Basis Ops",
        sla_status="AT_RISK", sla_remaining_minutes=55, sentiment="Impatient", parent_id="INC0048102",
        latest_work_notes="Basis L2 is comparing Node 02 ICM and gateway traces with the healthy node before a controlled restart.",
        comments=_journal_thread("INC0048109", requester="Luca Bianchi", l1_support="Alex Rivera", l2_support="Jonas Weber", initial_report="RF handhelds are timing out when connecting through gateway node 02.", monitoring_check="L1 confirmed node 01 remains healthy and collected NetWeaver gateway timeout samples.", business_impact="Outbound loading is accumulating because handheld operators cannot post the required goods issues.", diagnostic_update="Basis L2 is reviewing ICM, gateway, and connection-pool traces before deciding on a controlled node restart."),
        resources={"KBA": "KBA-BASIS-210 — RF gateway timeout recovery", "Veeva": "Veeva Vault / Operations / NetWeaver validation", "GDrive": "ATLAS / Basis / RF gateway KT"},
    ),
    "INC0048110": Ticket(
        id="INC0048110", type="INC", record_type="INC", title="Billing Document SD-FI Posting Block & Tax Code Determination Failure",
        description="SAP SD billing documents cannot post to FICO because tax code determination fails during SD-FI account assignment.",
        state="On Hold", priority="P1", assignee="Marco Silva", caller_id="Finance Operations", assignment_group="SAP SD Support",
        is_breached=True, on_hold_reason="Awaiting Change", sla_status="BREACHED", sla_remaining_minutes=-45, sentiment="Frustrated",
        latest_work_notes="SD/FICO L2 validated the tax configuration mismatch and is awaiting the controlled transport referenced in the recovery plan.",
        similar_records=[{"id": "PRB0030991", "score": 92, "title": "Historical Root Cause: SD-FI Tax Code Determination Mapping", "state": "Closed", "resolution_date": "2026-08-17"}],
        comments=_journal_thread("INC0048110", requester="Finance Operations", l1_support="Finance Service Desk", l2_support="Marco Silva", initial_report="Billing documents are blocked because SD-FI posting fails during tax code determination.", monitoring_check="L1 correlated failed billing document logs with the affected tax determination configuration.", business_impact="Finance cannot close the current billing batch until postings reach FICO.", diagnostic_update="SD/FICO L2 isolated the configuration mismatch and is preparing controlled transport validation."),
        attachments=[
            {"filename": "po_release_authorization_failure.png", "content_type": "image/svg+xml", "size": "824 KB", "url": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1200' height='675'%3E%3Crect width='100%25' height='100%25' fill='%230f172a'/%3E%3Ctext x='70' y='130' fill='%2367e8f9' font-size='42' font-family='Arial'%3ESAP authorization evidence%3C/text%3E%3C/svg%3E"},
            {"filename": "sd_fi_posting_tax_error.pdf", "content_type": "application/pdf", "size": "412 KB", "url": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"},
        ],
        resources={"KBA": "KB-SD-FICO-350 — Billing tax determination recovery", "Veeva": "Veeva Vault / Finance / SD-FI posting control", "GDrive": "ATLAS / SD-FICO / billing KT"},
    ),
    "INC0048125": Ticket(
        id="INC0048125", type="INC", record_type="INC", title="EHS Specification Sync Failure between SAP PLM and Material Master Classification",
        description="SAP PLM EHS specifications fail to synchronize to Material Master classification through the controlled integration flow.",
        state="In Progress", priority="P2", assignee="Priya Nair", caller_id="Product Compliance", assignment_group="SAP PLM Support",
        sla_status="AT_RISK", sla_remaining_minutes=95, sentiment="Impatient", latest_work_notes="PLM L2 is comparing classification payload mappings against the approved EHS specification schema.",
        comments=_journal_thread("INC0048125", requester="Product Compliance", l1_support="PLM Service Desk", l2_support="Priya Nair", initial_report="EHS specifications are not synchronizing from SAP PLM to Material Master classification.", monitoring_check="L1 confirmed the integration failure in the PLM monitoring dashboard and collected the failed payload ID.", business_impact="Product compliance cannot release the affected materials until classification data is current.", diagnostic_update="PLM L2 is validating the field mapping, controlled specification schema, and the related known defect."),
        resources={"KBA": "KB0062011 — SAP PLM EHS classification recovery", "Veeva": "VEEVA-SPEC-0099", "ALM": "ALM-DEF-8812", "GDrive": "GDRIVE-SUD-311"},
    ),
    "INC0048130": Ticket(
        id="INC0048130", type="INC", record_type="INC", title="Unmapped ERR_9921_SYNC_FAIL Memory Corruption on SAP PO Gateway",
        description="A previously unmapped ERR_9921_SYNC_FAIL memory corruption signature is causing SAP PO Gateway message processing instability.",
        state="In Progress", priority="P1", assignee="Avery Brooks", caller_id="Integration Operations", assignment_group="Enterprise Integration Services",
        sla_status="AT_RISK", sla_remaining_minutes=40, sentiment="Impatient", is_known_issue=False,
        latest_work_notes="Integration L2 preserved heap and gateway diagnostics; no matching internal KBA, defect, or SUD has been identified.",
        comments=_journal_thread("INC0048130", requester="Integration Operations", l1_support="Integration Service Desk", l2_support="Avery Brooks", initial_report="SAP PO Gateway is failing with ERR_9921_SYNC_FAIL and suspected memory corruption.", monitoring_check="L1 captured the error signature, gateway timestamp, and affected interface identifiers.", business_impact="Several asynchronous integration messages are accumulating and downstream business processes are delayed.", diagnostic_update="Integration L2 is preserving diagnostics and isolating the heap corruption pattern as a potential zero-day."),
        resources={"KBA": "No matching internal KBA", "Veeva": "No controlled procedure identified", "GDrive": "Pending new KT/SUD"},
    ),
    "PRB0030991": Ticket(
        id="PRB0030991", type="PRB", record_type="PRB", title="Historical Root Cause: SD-FI Tax Code Determination Mapping",
        description="Closed problem record for an SD-FI billing posting block caused by an obsolete tax determination mapping.",
        state="Closed", priority="P1", assignee="Marco Silva", assignment_group="SAP SD Support", rca_phase="Closed", risk_level="High Impact",
        latest_work_notes="Validated billing posting recovery after transporting the corrected tax-code determination mapping.",
        closure_notes="Corrected the tax-code determination mapping and validated successful SD billing postings into FICO.",
        close_code="Solved (Permanently)",
        resources={"KBA": "KB-SD-FICO-350 — Billing tax determination recovery", "Veeva": "Veeva Vault / Finance / SD-FI posting control", "GDrive": "ATLAS / SD-FICO / billing KT"},
    ),
    "PRB0031022": Ticket(
        id="PRB0031022", type="PRB", record_type="PRB", title="SAP EWM qRFC Queue Lock & Batch Authorization Root Cause Analysis",
        description="Problem investigation into the coupled SAP EWM qRFC lock, Basis queue ownership, and batch authorization failure.",
        state="Root Cause Analysis", priority="P1", assignee="Omar Rahman", assignment_group="Integration Middleware", rca_phase="RCA In Progress", risk_level="High Impact",
        originating_ticket_ids=["INC0048102"], linked_change="CHG0092100", latest_work_notes="RCA identified a qRFC ownership lock compounded by a missing controlled batch authorization role.",
        ptasks=[
            {"id": "PTASK001", "title": "Collect qRFC and SM12 lock traces", "state": "Closed", "close_notes": "Trace collection confirmed the blocked queue owner and authorization failure sequence."},
            {"id": "PTASK002", "title": "Validate batch authorization role correction", "state": "Work in Progress", "comments": [{"sys_created_on": "2026-09-23 11:38:00", "value": "Basis validation confirms the corrected role is available in the controlled production client; business retest is pending."}]},
            {"id": "PTASK003", "title": "Define preventive queue monitoring", "state": "New", "comments": [{"sys_created_on": "2026-09-23 11:42:00", "value": "Monitoring threshold review is queued after the qRFC recovery controls are validated."}]},
        ],
        resources={"KBA": "KBA003192 — qRFC queue recovery", "Veeva": "Veeva Vault / RCA / EWM batch authorization", "GDrive": "ATLAS / EWM / RCA KT"},
    ),
    "CHG0092100": Ticket(
        id="CHG0092100", type="CHG", record_type="CHG", title="Emergency SAP EWM qRFC and Batch Authorization Recovery",
        description="Emergency change to unlock the SAP EWM qRFC queue and deploy the approved batch authorization correction.",
        state="Implement", priority="P1", assignee="Elena Rossi", assignment_group="Integration Middleware", cab_status="CAB Approved", risk_level="Emergency Change",
        originating_ticket_ids=["PRB0031022"], latest_work_notes="Emergency CAB approval is recorded; implementation is proceeding through the controlled recovery runbook.",
        ctasks=[
            {"id": "CTASK001", "title": "Pre-patch backup and recovery point", "state": "Closed Complete", "close_notes": "Backup checksum and recovery point validated."},
            {"id": "CTASK002", "title": "Deploy qRFC and authorization correction", "state": "Open", "comments": [{"sys_created_on": "2026-09-23 11:45:00", "value": "Implementation window is active. The team is applying the approved qRFC recovery and authorization correction under CAB control."}]},
        ],
        resources={"KBA": "KBA003192 — qRFC emergency recovery", "Veeva": "Veeva Vault / Change Control / CHG0092100", "GDrive": "ATLAS / EWM / emergency change KT"},
    ),
    "INC0048131": Ticket(
        id="INC0048131", type="INC", record_type="INC", title="SAP MM Supplier Master Validation Exception",
        description="Supplier master validation is failing for a controlled purchasing-data update and requires requester confirmation of the source values.",
        state="On Hold", priority="P2", assignee="Nina Keller", caller_id="Procurement Operations", assignment_group="SAP MM Support",
        on_hold_reason="Awaiting Caller", sla_status="AT_RISK", sla_remaining_minutes=110, sentiment="Impatient",
        latest_work_notes="SAP MM L2 validated the interface payload and is awaiting the requester’s confirmation of the controlled supplier attributes.",
        comments=_journal_thread("INC0048131", requester="Procurement Operations", l1_support="Procurement Service Desk", l2_support="Nina Keller", initial_report="Supplier master changes are failing validation before the purchasing update can be released.", monitoring_check="L1 confirmed the error occurs only for the controlled supplier record and attached the validation result.", business_impact="Procurement cannot release the supplier amendment before the next purchasing cycle.", diagnostic_update="SAP MM L2 isolated the mandatory source attribute mismatch and requested confirmation from the business owner."),
        resources={"KBA": "KBA-MM-388 — Supplier master validation recovery", "Veeva": "Veeva Vault / Procurement / supplier-master-control", "GDrive": "ATLAS / SAP MM / supplier master KT"},
    ),
    "INC0048132": Ticket(
        id="INC0048132", type="INC", record_type="INC", title="SAP EWM Outbound Wave Confirmation Dependency",
        description="Outbound wave confirmation is paused until the linked warehouse device recovery activity completes its validation.",
        state="On Hold", priority="P3", assignee="Maya Chen", caller_id="Warehouse Operations", assignment_group="SAP EWM Support",
        on_hold_reason="Awaiting Child", sla_status="AT_RISK", sla_remaining_minutes=145, sentiment="Calm",
        latest_work_notes="EWM L2 is awaiting validation from the dependent warehouse recovery work before releasing outbound wave confirmation.",
        comments=_journal_thread("INC0048132", requester="Warehouse Operations", l1_support="Warehouse Service Desk", l2_support="Maya Chen", initial_report="Outbound wave confirmation is paused after the device-recovery validation dependency was raised.", monitoring_check="L1 confirmed the queue is stable and documented the downstream validation dependency.", business_impact="The next outbound wave cannot be released until warehouse device validation completes.", diagnostic_update="SAP EWM L2 confirmed no additional queue remediation is required and is waiting for the dependent recovery evidence."),
        resources={"KBA": "KBA-EWM-274 — Outbound wave dependency handling", "Veeva": "Veeva Vault / Warehouse / outbound-wave-control", "GDrive": "ATLAS / SAP EWM / outbound wave KT"},
    ),
    "INC0048133": Ticket(
        id="INC0048133", type="INC", record_type="INC", title="SAP EWM Wave Release Queue Throughput Degradation",
        description="Outbound wave releases are delayed as EWM queue throughput drops during the warehouse peak window.", state="In Progress",
        priority="P2", assignee="Maya Chen", caller_id="Warehouse Operations", assignment_group="SAP EWM Support", opened_on="2026-07-09",
        sla_status="AT_RISK", sla_remaining_minutes=88, sentiment="Impatient", latest_work_notes="EWM L2 is balancing queue workers and validating throughput against the planned wave-release volume.",
        comments=_journal_thread("INC0048133", requester="Warehouse Operations", l1_support="Warehouse Service Desk", l2_support="Maya Chen", initial_report="Outbound wave releases are taking longer than the warehouse operating threshold.", monitoring_check="L1 confirmed worker saturation during the peak wave-release window.", business_impact="Picking teams are waiting for wave assignments before the afternoon carrier cut-off.", diagnostic_update="EWM L2 is validating queue-worker capacity and the release scheduler profile."),
        resources={"KBA": "KBA-EWM-311 — Wave release throughput recovery", "Veeva": "Veeva Vault / Warehouse / wave-release-control", "GDrive": "ATLAS / SAP EWM / wave release KT"},
    ),
    "INC0048134": Ticket(
        id="INC0048134", type="INC", record_type="INC", title="SAP EWM RF Device Session Re-authentication Failure",
        description="Warehouse RF devices intermittently fail session re-authentication after a controlled EWM mobility policy refresh.", state="In Progress",
        priority="P2", assignee="Maya Chen", caller_id="Warehouse Mobility Team", assignment_group="SAP EWM Support", opened_on="2026-08-11",
        sla_status="AT_RISK", sla_remaining_minutes=76, sentiment="Impatient", latest_work_notes="EWM L2 is comparing RF session policy claims with the approved mobility role baseline.",
        comments=_journal_thread("INC0048134", requester="Warehouse Mobility Team", l1_support="Mobility Service Desk", l2_support="Maya Chen", initial_report="Several RF devices require repeated sign-in after the mobility policy refresh.", monitoring_check="L1 correlated the failed sessions with the policy deployment timestamp.", business_impact="Warehouse users lose scanning time while device sessions are re-established.", diagnostic_update="EWM L2 is comparing the token claims and approved RF mobility role baseline."),
        resources={"KBA": "KBA-EWM-326 — RF session authentication recovery", "Veeva": "Veeva Vault / Warehouse / RF-access-control", "GDrive": "ATLAS / SAP EWM / RF mobility KT"},
    ),
    "INC0048135": Ticket(
        id="INC0048135", type="INC", record_type="INC", title="SAP EWM Inbound Delivery Replication Delay",
        description="Inbound delivery replication from ERP to EWM was delayed after a transient queue communication interruption.", state="Resolved",
        priority="P3", assignee="Maya Chen", caller_id="Inbound Logistics", assignment_group="SAP EWM Support", opened_on="2026-09-08",
        sla_status="ON_TRACK", sla_remaining_minutes=310, sentiment="Calm", latest_work_notes="EWM L2 replayed the validated queue entries and confirmed inbound delivery consistency.",
        close_code="Solved (Permanently)", closure_notes="Replayed the validated delivery queue entries and confirmed that inbound replication remained stable through the next receiving cycle.",
        comments=_journal_thread("INC0048135", requester="Inbound Logistics", l1_support="Warehouse Service Desk", l2_support="Maya Chen", initial_report="Inbound deliveries are not appearing in EWM after ERP confirmation.", monitoring_check="L1 identified a short communication interruption and preserved the queue IDs.", business_impact="Receiving teams cannot complete inbound putaway for the affected deliveries.", diagnostic_update="EWM L2 replayed the validated entries and requested a receiving-cycle confirmation."),
        resources={"KBA": "KBA-EWM-335 — Inbound replication recovery", "Veeva": "Veeva Vault / Warehouse / inbound-delivery-control", "GDrive": "ATLAS / SAP EWM / inbound replication KT"},
    ),
    "INC0048136": Ticket(
        id="INC0048136", type="INC", record_type="INC", title="SAP EWM Stock Type Synchronization Mismatch",
        description="A stock-type synchronization mismatch is preventing selected warehouse bins from receiving the approved status update.", state="In Progress",
        priority="P2", assignee="Maya Chen", caller_id="Inventory Control", assignment_group="SAP EWM Support", opened_on="2026-10-02",
        sla_status="AT_RISK", sla_remaining_minutes=104, sentiment="Calm", latest_work_notes="EWM L2 is validating stock-type mapping and the outbound replication acknowledgement.",
        comments=_journal_thread("INC0048136", requester="Inventory Control", l1_support="Warehouse Service Desk", l2_support="Maya Chen", initial_report="Warehouse bins retain the prior stock type after the approved inventory adjustment.", monitoring_check="L1 confirmed the mismatch is limited to the affected synchronization queue.", business_impact="Inventory control cannot release the affected bins for the next allocation run.", diagnostic_update="EWM L2 is checking the stock-type mapping and replication acknowledgement."),
        resources={"KBA": "KBA-EWM-342 — Stock type synchronization validation", "Veeva": "Veeva Vault / Warehouse / inventory-control", "GDrive": "ATLAS / SAP EWM / stock type KT"},
    ),
    "INC0048137": Ticket(
        id="INC0048137", type="INC", record_type="INC", title="SAP BASIS Spool Work Process Saturation",
        description="Spool work processes are approaching saturation during scheduled warehouse-label generation.", state="In Progress",
        priority="P2", assignee="Jonas Weber", caller_id="Warehouse Print Services", assignment_group="SAP Basis Ops", opened_on="2026-07-16",
        sla_status="AT_RISK", sla_remaining_minutes=92, sentiment="Impatient", latest_work_notes="Basis L2 is reviewing spool-server queue depth and work-process allocation before the next print cycle.",
        comments=_journal_thread("INC0048137", requester="Warehouse Print Services", l1_support="Basis Service Desk", l2_support="Jonas Weber", initial_report="Warehouse label jobs are delayed because spool processing is reaching capacity.", monitoring_check="L1 captured spool queue depth and work-process saturation evidence.", business_impact="Outbound labels may not be ready for the next dispatch wave.", diagnostic_update="Basis L2 is reviewing work-process allocation and spool-server queue controls."),
        resources={"KBA": "KBA-BASIS-451 — Spool saturation response", "Veeva": "Veeva Vault / Infrastructure / print-control", "GDrive": "ATLAS / SAP Basis / spool operations KT"},
    ),
    "INC0048138": Ticket(
        id="INC0048138", type="INC", record_type="INC", title="SAP BASIS HANA Backup Chain Alert",
        description="The HANA backup monitoring chain reported a delayed log-backup handoff requiring Basis validation.", state="Resolved",
        priority="P3", assignee="Jonas Weber", caller_id="Database Operations", assignment_group="SAP Basis Ops", opened_on="2026-08-19",
        sla_status="ON_TRACK", sla_remaining_minutes=420, sentiment="Calm", latest_work_notes="Basis L2 confirmed the backup chain resumed and the retention checkpoint was validated.",
        close_code="Solved (Permanently)", closure_notes="Validated the log-backup handoff, confirmed the next full backup checkpoint, and recorded the successful retention verification.",
        comments=_journal_thread("INC0048138", requester="Database Operations", l1_support="Basis Service Desk", l2_support="Jonas Weber", initial_report="HANA monitoring reports a delayed log-backup handoff for the production system.", monitoring_check="L1 confirmed no data loss indicators and attached the backup-monitoring timeline.", business_impact="Operations needs confirmation that the protected backup chain remains compliant.", diagnostic_update="Basis L2 validated the handoff and monitored the subsequent checkpoint."),
        resources={"KBA": "KBA-BASIS-463 — HANA backup chain validation", "Veeva": "Veeva Vault / Infrastructure / backup-control", "GDrive": "ATLAS / SAP Basis / HANA backup KT"},
    ),
    "INC0048139": Ticket(
        id="INC0048139", type="INC", record_type="INC", title="SAP BASIS RFC Destination TLS Certificate Warning",
        description="A production RFC destination is approaching its TLS certificate renewal threshold and needs controlled validation.", state="In Progress",
        priority="P3", assignee="Jonas Weber", caller_id="Integration Operations", assignment_group="SAP Basis Ops", opened_on="2026-09-14",
        sla_status="ON_TRACK", sla_remaining_minutes=360, sentiment="Calm", latest_work_notes="Basis L2 is validating the replacement certificate chain in the controlled connectivity path.",
        comments=_journal_thread("INC0048139", requester="Integration Operations", l1_support="Basis Service Desk", l2_support="Jonas Weber", initial_report="An RFC destination certificate warning was raised ahead of the production renewal window.", monitoring_check="L1 verified the expiry threshold and captured the active certificate chain.", business_impact="Integration teams need assurance that the renewal will not interrupt scheduled interfaces.", diagnostic_update="Basis L2 is validating the replacement certificate chain and controlled cutover plan."),
        resources={"KBA": "KBA-BASIS-474 — RFC TLS renewal validation", "Veeva": "Veeva Vault / Infrastructure / certificate-control", "GDrive": "ATLAS / SAP Basis / RFC TLS KT"},
    ),
    "INC0048140": Ticket(
        id="INC0048140", type="INC", record_type="INC", title="SAP BASIS Transport Import Lock in QA",
        description="A QA transport import remains locked after a controlled deployment and requires Basis recovery validation.", state="In Progress",
        priority="P2", assignee="Jonas Weber", caller_id="Release Management", assignment_group="SAP Basis Ops", opened_on="2026-10-04",
        sla_status="AT_RISK", sla_remaining_minutes=72, sentiment="Impatient", latest_work_notes="Basis L2 is validating the import queue lock owner and the approved rollback point before releasing the transport.",
        comments=_journal_thread("INC0048140", requester="Release Management", l1_support="Basis Service Desk", l2_support="Jonas Weber", initial_report="The QA transport import did not complete and the import queue remains locked.", monitoring_check="L1 preserved the transport log and confirmed the lock is isolated to the current QA queue.", business_impact="Release validation cannot proceed until the controlled import is available in QA.", diagnostic_update="Basis L2 is checking the lock owner and approved rollback point before recovery."),
        resources={"KBA": "KBA-BASIS-486 — Transport lock recovery", "Veeva": "Veeva Vault / Release / transport-control", "GDrive": "ATLAS / SAP Basis / transport KT"},
    ),
    "INC0048141": Ticket(
        id="INC0048141", type="INC", record_type="INC", title="SAP PLM Design BOM Classification Routing Failure",
        description="Engineering design BOM updates are failing to route to the approved material classification queue after a controlled PLM mapping release.", state="In Progress",
        priority="P2", assignee="Priya Nair", caller_id="Product Engineering", assignment_group="SAP PLM Support", opened_on="2026-08-05",
        sla_status="AT_RISK", sla_remaining_minutes=68, sentiment="Impatient", linked_problem="PRB0031023", linked_change="CHG0092101",
        latest_work_notes="PLM L2 isolated a classification-route mismatch and is collecting payload evidence for the linked RCA.",
        comments=_journal_thread("INC0048141", requester="Product Engineering", l1_support="PLM Service Desk", l2_support="Priya Nair", initial_report="Design BOM classification updates are not reaching the approved downstream material queue.", monitoring_check="L1 confirmed the failure began after the controlled PLM mapping release and captured the payload identifiers.", business_impact="Engineering cannot release the affected BOM revision to manufacturing planning.", diagnostic_update="PLM L2 isolated the classification-route mismatch and opened a linked problem investigation."),
        resources={"KBA": "KBA-PLM-522 — Design BOM classification routing recovery", "Veeva": "Veeva Vault / PLM / BOM-classification-control", "GDrive": "ATLAS / SAP PLM / BOM classification KT"},
    ),
    "INC0048142": Ticket(
        id="INC0048142", type="INC", record_type="INC", title="SAP PLM Recipe Approval Workflow Scheduler Timeout",
        description="Recipe approvals are timing out when the PLM background scheduler reaches the configured approval-workflow concurrency limit.", state="On Hold",
        priority="P2", assignee="Priya Nair", caller_id="Quality Operations", assignment_group="SAP PLM Support", opened_on="2026-09-17",
        on_hold_reason="Awaiting Change", sla_status="AT_RISK", sla_remaining_minutes=82, sentiment="Impatient", linked_problem="PRB0031024", linked_change="CHG0092102",
        latest_work_notes="PLM L2 confirmed scheduler contention and is awaiting the controlled capacity change for the workflow worker pool.",
        comments=_journal_thread("INC0048142", requester="Quality Operations", l1_support="PLM Service Desk", l2_support="Priya Nair", initial_report="Recipe approval tasks are timing out before the quality review can be completed.", monitoring_check="L1 confirmed the scheduler queue rises above the configured approval-workflow threshold during peak review activity.", business_impact="Quality Operations cannot complete the controlled recipe approval cycle for the pending manufacturing release.", diagnostic_update="PLM L2 confirmed scheduler contention and linked the required capacity change."),
        resources={"KBA": "KBA-PLM-534 — Recipe approval scheduler recovery", "Veeva": "Veeva Vault / PLM / recipe-approval-control", "GDrive": "ATLAS / SAP PLM / recipe workflow KT"},
    ),
    "INC0048143": Ticket(
        id="INC0048143", type="INC", record_type="INC", title="SAP PLM Recipe Approval Reconciliation Waiting for RCA",
        description="Controlled recipe-approval reconciliation is paused until the linked Problem record confirms the scheduler contention root cause and approved recovery path.", state="On Hold",
        priority="P2", assignee="Priya Nair", caller_id="Quality Operations", assignment_group="SAP PLM Support",
        hold_reason="Awaiting Problem", sla_status="AT_RISK", sla_remaining_minutes=74, sentiment="Impatient", linked_problem="PRB0031024",
        latest_work_notes="PLM L2 completed evidence collection and is awaiting the linked problem RCA before applying a controlled workaround to the affected recipe approvals.",
        comments=_journal_thread("INC0048143", requester="Quality Operations", l1_support="PLM Service Desk", l2_support="Priya Nair", initial_report="Recipe approvals need reconciliation, but Quality Operations requires the confirmed root cause before the controlled correction can proceed.", monitoring_check="L1 linked the affected approval tasks to the scheduler timeout pattern and attached the audit evidence.", business_impact="The manufacturing release cannot proceed until the recipe approvals are reconciled under the approved quality procedure.", diagnostic_update="PLM L2 placed the incident on hold pending PRB0031024 root-cause confirmation and controlled workaround guidance."),
        resources={"KBA": "KBA-PLM-534 — Recipe approval scheduler recovery", "Veeva": "Veeva Vault / PLM / recipe-approval-control", "GDrive": "ATLAS / SAP PLM / recipe workflow KT"},
    ),
    "INC0048144": Ticket(
        id="INC0048144", type="INC", record_type="INC", title="SAP EWM Warehouse Recovery Validation Waiting for Parent Incident",
        description="A dependent warehouse recovery validation remains paused until the primary EWM qRFC incident confirms its controlled queue-unlock recovery state.", state="On Hold",
        priority="P3", assignee="Maya Chen", caller_id="Warehouse Operations", assignment_group="SAP EWM Support",
        hold_reason="Awaiting Parent", sla_status="AT_RISK", sla_remaining_minutes=128, sentiment="Calm", parent_id="INC0048102",
        latest_work_notes="EWM L2 completed local validation preparation and is waiting for the parent qRFC recovery confirmation before releasing the dependent warehouse test.",
        comments=_journal_thread("INC0048144", requester="Warehouse Operations", l1_support="Warehouse Service Desk", l2_support="Maya Chen", initial_report="Warehouse recovery validation cannot begin until the parent qRFC incident confirms the queue-unlock recovery status.", monitoring_check="L1 confirmed the local validation evidence is ready and no standalone device fault is present.", business_impact="The dependent warehouse regression test remains paused until the primary incident recovery is confirmed.", diagnostic_update="EWM L2 linked this child incident to INC0048102 and placed it on hold pending the parent recovery confirmation."),
        resources={"KBA": "KBA003192 — qRFC queue recovery", "Veeva": "Veeva Vault / Warehouse / recovery-validation-control", "GDrive": "ATLAS / SAP EWM / parent-recovery validation KT"},
    ),
    "PRB0031023": Ticket(
        id="PRB0031023", type="PRB", record_type="PRB", title="SAP PLM Classification Route Mapping Regression",
        description="Problem investigation into a PLM classification-route mapping regression affecting design BOM updates after the controlled mapping release.", state="Root Cause Analysis",
        priority="P2", assignee="Priya Nair", assignment_group="SAP PLM Support", opened_on="2026-08-06",
        rca_phase="RCA In Progress", risk_level="High Impact", originating_ticket_ids=["INC0048141", "INC0048125"], linked_change="CHG0092101",
        latest_work_notes="RCA confirms the release profile omitted an approved classification-route mapping for the engineering BOM object type.",
        ptasks=[
            {"id": "PTASK003101", "title": "Compare approved and deployed PLM route mappings", "state": "Closed", "close_notes": "Confirmed the engineering BOM route mapping was omitted from the deployed release profile."},
            {"id": "PTASK003102", "title": "Validate corrected classification route in QA", "state": "Work in Progress", "comments": [{"sys_created_on": "2026-10-07 09:20:00", "value": "QA validation is running against representative engineering BOM payloads and approved material classes."}]},
        ],
        resources={"KBA": "KBA-PLM-522 — Design BOM classification routing recovery", "Veeva": "Veeva Vault / PLM / mapping-RCA", "GDrive": "ATLAS / SAP PLM / classification route analysis"},
    ),
    "CHG0092101": Ticket(
        id="CHG0092101", type="CHG", record_type="CHG", title="SAP PLM Classification Route Mapping Correction",
        description="Controlled change to restore the approved PLM design BOM classification-route mapping and validate downstream material classification processing.", state="Authorize",
        priority="P2", assignee="Priya Nair", assignment_group="SAP PLM Support", opened_on="2026-10-01",
        cab_status="CAB Review Scheduled", risk_level="High Impact", originating_ticket_ids=["PRB0031023"],
        latest_work_notes="Change evidence, rollback mapping profile, and QA validation plan are prepared for CAB authorization.",
        ctasks=[
            {"id": "CTASK003101", "title": "Export current PLM mapping profile", "state": "Closed Complete", "close_notes": "Current mapping profile exported and checksum retained as the approved rollback point."},
            {"id": "CTASK003102", "title": "Deploy corrected classification route", "state": "Pending", "comments": [{"sys_created_on": "2026-10-07 10:05:00", "value": "Deployment is pending CAB authorization and final QA evidence review."}]},
        ],
        resources={"KBA": "KBA-PLM-522 — Design BOM classification routing recovery", "Veeva": "Veeva Vault / Change Control / CHG0092101", "GDrive": "ATLAS / SAP PLM / classification route deployment KT"},
    ),
    "PRB0031024": Ticket(
        id="PRB0031024", type="PRB", record_type="PRB", title="SAP PLM Recipe Workflow Scheduler Contention",
        description="Root-cause analysis of PLM recipe approval scheduler contention during concurrent quality-review windows.", state="Root Cause Analysis",
        priority="P2", assignee="Priya Nair", assignment_group="SAP PLM Support", opened_on="2026-09-18",
        rca_phase="RCA In Progress", risk_level="High Impact", originating_ticket_ids=["INC0048142"], linked_change="CHG0092102",
        latest_work_notes="RCA identified workflow worker-pool saturation during the quality-review batch window and a missing alert threshold.",
        ptasks=[
            {"id": "PTASK003201", "title": "Capture PLM workflow scheduler concurrency profile", "state": "Closed", "close_notes": "Profile confirms worker-pool saturation during concurrent quality-review requests."},
            {"id": "PTASK003202", "title": "Define scheduler capacity and alert threshold", "state": "Work in Progress", "comments": [{"sys_created_on": "2026-10-07 10:18:00", "value": "Capacity model and alert threshold are being validated against the regulated approval workload."}]},
        ],
        resources={"KBA": "KBA-PLM-534 — Recipe approval scheduler recovery", "Veeva": "Veeva Vault / PLM / scheduler-RCA", "GDrive": "ATLAS / SAP PLM / scheduler analysis KT"},
    ),
    "CHG0092102": Ticket(
        id="CHG0092102", type="CHG", record_type="CHG", title="SAP PLM Recipe Workflow Capacity and Alerting Update",
        description="Controlled change to increase the PLM recipe-approval scheduler capacity and introduce proactive concurrency alerting.", state="Assess",
        priority="P3", assignee="Priya Nair", assignment_group="SAP PLM Support", opened_on="2026-10-03",
        cab_status="Assessment In Progress", risk_level="Medium Impact", originating_ticket_ids=["PRB0031024"],
        latest_work_notes="PLM Support is validating the capacity proposal, alert thresholds, and rollback plan with Quality Operations.",
        ctasks=[
            {"id": "CTASK003201", "title": "Validate current recipe approval scheduler baseline", "state": "Closed Complete", "close_notes": "Baseline captured for concurrent review volume, queue wait time, and worker utilization."},
            {"id": "CTASK003202", "title": "Configure capacity and concurrency alert threshold", "state": "Open", "comments": [{"sys_created_on": "2026-10-07 10:30:00", "value": "Configuration is awaiting the final approved capacity target from the change assessment."}]},
        ],
        resources={"KBA": "KBA-PLM-534 — Recipe approval scheduler recovery", "Veeva": "Veeva Vault / Change Control / CHG0092102", "GDrive": "ATLAS / SAP PLM / scheduler capacity KT"},
    ),
})


def _resolution_plan(summary: str, *steps: tuple[str, str, str]) -> dict[str, object]:
    """Build a canonical, traceable multi-source AI resolution plan."""

    return {
        "summary": summary,
        "steps": [
            {"action": action, "why": why, "sources": sources}
            for action, why, sources in steps
        ],
    }


# These are the authoritative executive-resolution plans for the demo queue.
# Each plan is deliberately specific to the record, its relationships, open
# tasks, journal evidence, and connected knowledge sources.  The drawer and
# chat APIs consume these values directly; no presentation layer duplicates
# or reinterprets the runbook.
TICKET_RESOLUTION_PLANS: dict[str, dict[str, object]] = {
    "INC0048102": _resolution_plan(
        "Restore warehouse goods issue by separating the qRFC lock from the batch-user authorization failure, then validate the approved emergency change.",
        ("Capture the lock owner in SM12", "Record client, object, owner, and lock age before any unlock so active warehouse processing is not interrupted.", "INC0048102 journal + KBA003192"),
        ("Inspect the blocked LUWs in SMQ1 and SMQ2", "Identify the queue status, predecessor dependency, destination, and retry error; retain the evidence for the linked root-cause investigation.", "KBA003192 + PRB0031022"),
        ("Run SU53 for the batch user after queue ownership is confirmed", "If M_MSEG_LGO or a related authorization is missing, send the trace to Identity & Access Management for the approved role correction.", "VEEVA-SOP-0042 + INC0048103"),
        ("Validate the approved CHG0092100 correction", "After the controlled unlock and role correction, confirm queue drain and one representative goods issue in /SCWM/MON.", "CHG0092100 + ServiceNow KBA"),
    ),
    "RITM0094101": _resolution_plan(
        "Fulfil the approved SAP EWM 1010 sandbox access request without extending the role scope beyond the project approval.",
        ("Verify the requested role set against the approved access record", "Confirm requester, sandbox client, validity period, and segregation-of-duties approval before provisioning.", "RITM approval + Veeva access-control SOP"),
        ("Provision the approved roles through the controlled identity process", "Assign only the approved sandbox roles and retain the role-change evidence for audit.", "ServiceNow RITM + IAM connector"),
        ("Validate login and a non-production EWM transaction", "Ask the requester to confirm access to the intended sandbox scope; remove any temporary access that is not required.", "Requester confirmation + SAP EWM access guide"),
    ),
    "INC0048103": _resolution_plan(
        "Restore warehouse token refresh by proving the missing M_MSEG_LGO authorization and applying the approved role correction.",
        ("Capture SU53 immediately after the token refresh failure", "The trace identifies the denied object and field values needed for a controlled role correction.", "INC0048103 journal + KBA-SEC-118"),
        ("Compare the user role in PFCG with the approved warehouse role design", "Confirm whether the missing authorization is a role-content gap or an expired assignment before changing access.", "KBA-SEC-118 + VEEVA-SOP-0042"),
        ("Route the evidence to Identity & Access Management", "IAM owns the approved role adjustment; do not use SAP_ALL or a broad temporary role as a workaround.", "ServiceNow assignment rules + GRC controls"),
        ("Retest token refresh and goods movement access", "Validate the corrected token path against the parent EWM incident and document the result in the journal.", "INC0048102 relationship + requester validation"),
    ),
    "INC0048109": _resolution_plan(
        "Recover RF connectivity on node 02 by isolating the gateway, network, or queue-recovery dependency before a controlled restart.",
        ("Compare node 02 with a healthy RF node using SMICM and SMGW", "Confirm whether the timeout is node-specific and capture gateway or ICM connection errors.", "INC0048109 journal + KBA-BASIS-210"),
        ("Validate the RFC destination and gateway endpoint in SM59", "Separate certificate or destination failures from an RF-device or connection-pool fault.", "SAP Basis runbook + middleware evidence"),
        ("Coordinate queue-recovery timing with the parent EWM incident", "Do not restart the RF path while the parent qRFC recovery is actively changing queue ownership.", "INC0048102 topology + PRB0031022"),
        ("Test one representative handheld transaction after recovery", "Confirm login, scan, and goods-issue posting from node 02 before closing the incident.", "Warehouse validation record"),
    ),
    "PRB0019201": _resolution_plan(
        "Establish the technical cause of the EWM replication stall by correlating lock ownership, queue retries, and middleware memory pressure.",
        ("Use the closed PTASK001 trace to anchor the timeline", "Compare SM12 lock timestamps with SMQ1/SMQ2 retry history to identify whether the lock precedes the memory symptom.", "PTASK001 closure + KBA003192"),
        ("Complete PTASK002 against the middleware retry policy", "Validate retry concurrency and backoff settings before changing queue handling; attach the result to the RCA.", "PTASK002 + middleware runbook"),
        ("Define the preventive threshold in PTASK003", "Use measured queue depth and heap pressure to create an actionable alert threshold rather than a generic monitoring rule.", "PTASK003 + observability evidence"),
        ("Feed the verified fix into CHG0092100", "Only promote the queue and authorization correction after the RCA evidence supports the implementation path.", "CHG0092100 + problem workflow"),
    ),
    "CHG0092100": _resolution_plan(
        "Implement the approved emergency qRFC and authorization correction with rollback protection and warehouse validation.",
        ("Confirm CTASK001 recovery point and backup evidence", "The pre-patch backup is complete; verify its timestamp and rollback availability before touching production queue or role configuration.", "CTASK001 closure + VEEVA-SOP-0185"),
        ("Execute CTASK002 under the approved emergency window", "Apply the qRFC recovery and the narrow batch-role correction, with EWM, Basis, and IAM owners present for the controlled hand-off.", "CTASK002 + PRB0031022"),
        ("Validate SMQ1/SMQ2 drain and SU53 clearance", "Confirm both the replication path and authorization path are healthy before declaring the change effective.", "KBA003192 + KBA-SEC-244"),
        ("Obtain warehouse business confirmation", "Validate a representative goods issue and record the outcome, timestamps, and rollback decision in the change journal.", "Warehouse Operations + ServiceNow change record"),
    ),
    "INC0048104": _resolution_plan(
        "Restore the nightly EWM reconciliation job by proving the technical-user authorization gap and applying the approved role change.",
        ("Capture the failing run in SM37 and the immediate SU53 trace", "Record job variant, client, technical user, and denied authorization before any retry.", "INC0048104 journal + KBA-BASIS-428"),
        ("Verify the client context and role ownership", "If the evidence names client 000, route the controlled investigation to SAP Basis; otherwise route a missing object to IAM.", "SAP client-control policy + IAM process"),
        ("Retry only after the approved role transport is confirmed", "Run the job in the approved window and confirm reconciliation output rather than treating a job start as recovery.", "Veeva access-control SOP + business validation"),
    ),
    "RITM0094102": _resolution_plan(
        "Fulfil the Veeva Quality Reviewer request through the approved Vault entitlement workflow and verify the minimum required access.",
        ("Validate requester, vault, role, and approval evidence", "Ensure the request maps to the correct quality workspace and approved reviewer role.", "ServiceNow RITM + Veeva Vault access workflow"),
        ("Assign the Quality Reviewer role with the approved expiry", "Avoid administrative or owner permissions; retain the entitlement change record.", "Veeva Vault audit trail"),
        ("Ask the requester to validate a review-only action", "Confirm the user can complete the intended review without gaining authoring or administration rights.", "Requester confirmation"),
    ),
    "INC0048105": _resolution_plan(
        "Reduce regulated-feed delay by confirming worker saturation, scaling within the approved capacity boundary, and validating backlog drain.",
        ("Inspect worker saturation, queue depth, and error rate", "Determine whether CPU, memory, concurrency, or a downstream dependency is limiting ingestion.", "Cloud monitoring evidence + incident journal"),
        ("Apply the approved capacity or concurrency adjustment", "Use the documented autoscaling and rollback parameters; do not bypass change control for regulated feeds.", "Cloud runbook + change-control evidence"),
        ("Validate feed latency and record reconciliation", "Confirm that the delayed reporting feed drains and that no regulated records were skipped or duplicated.", "Business-owner validation"),
    ),
    "PRB0019202": _resolution_plan(
        "Remove PLM recipe-sync API exhaustion by measuring retry-pool behavior and validating a controlled pool remediation.",
        ("Complete PTASK001 with a retry and error trace", "Capture concurrency, response codes, retry count, and the affected recipe payloads to distinguish API throttling from malformed data.", "PTASK001 + PLM integration journal"),
        ("Use the PTASK002 remediation evidence to set the safe pool limit", "Confirm the corrected pool configuration handles representative recipe volume without exhausting retries.", "PTASK002 closure + PLM API runbook"),
        ("Reprocess a controlled sample and reconcile formulation updates", "Validate that downstream formulation receives the expected version and preserve GxP evidence.", "Veeva PLM SOP + requester validation"),
    ),
    "INC0048110": _resolution_plan(
        "Resolve the SD-FI posting block by isolating the failed tax determination and applying the approved mapping correction through the linked dependency.",
        ("Review the blocked billing item in VFX3 and document in VF03", "Capture the tax-code message, pricing context, and account-assignment details before any reposting.", "INC0048110 journal + KBA-SD-FICO-350"),
        ("Compare tax determination and account-assignment mapping with the approved configuration", "Identify the precise condition record or mapping discrepancy with the SD/FICO owner.", "KBA-SD-519 + finance configuration evidence"),
        ("Wait for the approved change, then retest one representative billing document", "The incident is on hold for a change; validate FI posting and tax result after implementation before releasing backlog.", "On-hold reason + change-control process"),
    ),
    "INC0048111": _resolution_plan(
        "Restore the purchasing-group approval path by validating substitution and agent determination before restarting workflow.",
        ("Inspect the purchase order in ME23N and workflow log in SWI1", "Confirm the release strategy, current agent, and point at which the substitution rule was not applied.", "INC0048111 journal + MM workflow guide"),
        ("Verify the approved substitution rule and validity dates", "Correct the assigned substitute only through the governed workflow configuration or approved master data path.", "Purchasing policy + ServiceNow evidence"),
        ("Restart or re-route only the affected approval after validation", "Confirm the approver receives the task and that the parent billing issue is not blocked by an unrelated workflow fault.", "Parent topology + requester confirmation"),
    ),
    "INC0048112": _resolution_plan(
        "Confirm the resolved SD billing IDoc failure remains corrected and preserve the successful recovery evidence.",
        ("Review the processed IDoc in WE02 or WE05", "Verify the status sequence, application document, and absence of repeated errors for the affected delivery.", "INC0048112 closure + SD IDoc runbook"),
        ("Reconcile invoice generation with the delivery and billing document", "Confirm the regenerated invoice is complete and no duplicate billing document was created.", "Business validation + finance evidence"),
        ("Retain the closure evidence and monitor the next scheduled run", "The record is resolved; reopen only if the same error signature recurs.", "ServiceNow closure policy"),
    ),
    "PRB0019203": _resolution_plan(
        "Correct the PLM-to-formulation integration failure by proving the payload-schema and downstream attribute-mapping gap.",
        ("Use PTASK101 schema comparison as the baseline", "Compare the approved recipe payload with the rejected downstream message to isolate the changed or missing field.", "PTASK101 closure + PLM integration evidence"),
        ("Complete PTASK102 mapping correction in a controlled environment", "Validate the downstream attribute mapping against representative regulated recipe data before production promotion.", "PTASK102 + Veeva controlled-remediation SOP"),
        ("Execute PTASK103 regulated synchronization validation", "Reconcile recipe version, formulation update, and audit evidence before closing the problem.", "PTASK103 + quality validation"),
    ),
    "RITM0094103": _resolution_plan(
        "Retain the successful SU53 role-grant evidence and confirm the corrected batch job remains stable.",
        ("Review the closed SCTASK001 trace and approved role record", "Ensure the granted role maps only to the documented SU53 authorization requirement.", "SCTASK001 closure + access approval"),
        ("Confirm the next controlled batch run completes without SU53", "The request is closed complete; a successful repeat run is the final operational validation.", "Batch-job evidence + requester confirmation"),
    ),
    "PRB0018992": _resolution_plan(
        "Use this closed historical problem as reference evidence for PO release strategy corruption; do not treat it as an active remediation plan.",
        ("Review the SAP Note 2839211 implementation evidence", "Confirm the historical release-strategy configuration fix and its documented test result.", "PTASK8992 closure + historical PRB"),
        ("Compare the active PO workflow configuration before reuse", "Reuse the prior corrective pattern only if the active release strategy and symptom match the historical record.", "Historical RCA + active MM incident"),
    ),
    "INC0048120": _resolution_plan(
        "Recover the EWM reconciliation batch by diagnosing the ITAB_ERROR_IN_INITIAL_SIZE dump in client 100 and validating the job after a controlled fix.",
        ("Inspect SM37 job log, spool, and variant", "Capture the failing step, selection volume, technical user, and client 100 before a restart.", "INC0048120 journal + KBA-BASIS-428"),
        ("Analyze the dump in ST22 and application log context", "Determine whether the internal-table allocation is driven by data volume, program logic, or a memory parameter before changing capacity.", "ST22 evidence + SolMan monitoring"),
        ("Route the remediation to the owning team", "Send program or data-volume evidence to the application owner; send platform-memory evidence to SAP Basis; keep vendor dependency evidence attached while on hold.", "On-hold reason + vendor connector"),
        ("Run a controlled reconciliation test", "Validate that the job completes for a representative scope and that the next scheduled run has no duplicate alert.", "Warehouse Operations confirmation"),
    ),
    "INC0048121": _resolution_plan(
        "Treat this record as a duplicate monitoring alert and correlate it to INC0048120 before any independent remediation.",
        ("Compare job name, client, timestamp, and dump signature with INC0048120", "The alerts refer to the same Z_EWM_RECON_NIGHTLY failure pattern; avoid parallel investigation.", "Similarity score 98% + INC0048120"),
        ("Link or suppress the redundant monitoring event", "Retain the alert evidence while routing all technical action to the active owner of INC0048120.", "Observability process + ServiceNow duplicate handling"),
        ("Confirm alert closure after the primary job validation", "Close the duplicate only when the primary incident has a successful monitored run.", "Primary incident journal"),
    ),
    "PRB0019205": _resolution_plan(
        "Resolve ChaRM transport synchronization by confirming the QA buffer deadlock and realigning the controlled landscape buffer.",
        ("Use the closed STMS log analysis to confirm the deadlock signature", "Validate target queue, return code, and buffer state against the recorded PTASK00101 evidence.", "PTASK00101 closure + SolMan ChaRM log"),
        ("Complete PTASK00102 with an approved buffer realignment", "Re-align the QA landscape only under release control and preserve the before-and-after buffer evidence.", "PTASK00102 + change-management controls"),
        ("Retest one controlled transport synchronization", "Confirm the transport appears in the intended QA target without creating a duplicate import or bypassing ChaRM governance.", "QA validation + release management"),
    ),
    "INC0048122": _resolution_plan(
        "Restore HP ALM to ServiceNow defect synchronization by isolating the failed API bridge mapping for Defect 4091 and CHG0092100.",
        ("Inspect the bridge payload, response, and correlation ID", "Confirm whether the failure is authentication, schema, required-field, or Change-reference mapping.", "INC0048122 journal + ALM connector logs"),
        ("Compare Defect 4091 fields with the ServiceNow Change contract", "Correct the field transformation only through the approved integration configuration path.", "HP ALM defect + CHG0092100"),
        ("Replay one controlled message and reconcile both records", "Verify the ALM defect links to the intended Change without creating a duplicate record.", "Integration test evidence"),
    ),
    "INC0048125": _resolution_plan(
        "Restore EHS specification synchronization by validating the PLM specification, Material Master classification, and integration payload as one controlled flow.",
        ("Review the affected specification in CG03/CG02", "Capture specification version, status, and classification characteristics before resubmitting data.", "KB0062011 + VEEVA-SPEC-0099"),
        ("Compare target classification and payload mapping", "Use the PLM-to-Material Master integration mapping to identify the missing or incompatible characteristic.", "GDRIVE-SUD-311 + ALM-DEF-8812"),
        ("Correct the mapping through controlled change and resynchronize a sample", "Validate the Material Master classification result and retain GxP evidence before processing the remaining backlog.", "Veeva SOP + ServiceNow KBA"),
    ),
    "INC0048130": _resolution_plan(
        "Contain the unknown SAP PO Gateway memory-corruption signature, collect diagnostics, and route a safe recovery through middleware engineering.",
        ("Capture gateway error context, message IDs, and memory diagnostics", "Preserve the ERR_9921_SYNC_FAIL evidence before retrying messages so the unknown signature can be analysed.", "INC0048130 journal + KBA-MW-772"),
        ("Pause unsafe replay and isolate the affected interface", "Prevent repeated corruption while confirming whether the fault is payload-specific, node-specific, or heap-related.", "Middleware runbook + zero-day handling"),
        ("Escalate the diagnostic bundle to the middleware platform owner", "No known internal resolution exists; the owner should evaluate heap, patch, and vendor support options under change control.", "RAG fallback policy + connector evidence"),
    ),
    "PRB0030991": _resolution_plan(
        "Use this closed SD-FI mapping problem as reference evidence for the active billing-posting investigation.",
        ("Review the obsolete tax-mapping corrective record", "Confirm the historical condition, mapping change, and validation evidence before applying any similar correction.", "PRB0030991 closure + KBA-SD-519"),
        ("Compare current tax determination with the historical signature", "Only reuse the resolution if the account-assignment and tax-code error match the closed root cause.", "Historical RCA + INC0048110"),
    ),
    "PRB0031022": _resolution_plan(
        "Complete the coupled EWM/Basis/Security RCA before finalizing the emergency change, using the recorded qRFC and authorization evidence.",
        ("Use the closed qRFC and SM12 trace to establish lock sequence", "Determine whether lock ownership is a cause or consequence of the queue and authorization failure.", "PTASK001 closure + KBA003192"),
        ("Complete PTASK002 with a least-privilege batch-role validation", "Prove the approved authorization correction resolves the batch path without broad access.", "PTASK002 + KBA-SEC-244"),
        ("Define PTASK003 queue-depth and retry alerts", "Create a preventive threshold from observed queue behaviour and tie it to the linked change validation.", "PTASK003 + CHG0092100"),
    ),
    "INC0048131": _resolution_plan(
        "Resolve the supplier-master validation exception after the requester confirms the authoritative source values.",
        ("Review the supplier record and change evidence in BP", "Identify the failing field and compare it with the controlled purchasing-data source.", "INC0048131 journal + supplier-master process"),
        ("Obtain requester confirmation for the disputed source values", "The incident is on hold awaiting caller input; do not overwrite master data based on an unverified value.", "On-hold reason + requester journal"),
        ("Apply the approved correction and rerun validation", "Confirm the supplier update passes the controlled validation and retains the change audit trail.", "Master-data governance evidence"),
    ),
    "INC0048132": _resolution_plan(
        "Release outbound-wave confirmation only after the linked device-recovery validation proves warehouse execution is stable.",
        ("Review the wave status and dependent warehouse activity in /SCWM/MON", "Confirm which outbound waves are paused and that no standalone wave-processing error is present.", "INC0048132 journal + EWM monitor"),
        ("Wait for the linked device-recovery validation result", "The hold is a real dependency; avoid forcing confirmation while RF recovery is still under test.", "On-hold reason + related recovery activity"),
        ("Release and validate one representative wave", "After dependency clearance, confirm confirmation and downstream goods issue complete normally.", "Warehouse Operations validation"),
    ),
    "INC0048133": _resolution_plan(
        "Improve outbound-wave throughput by identifying whether queue backlog, worker capacity, or warehouse peak demand is constraining release.",
        ("Measure queue depth and retries in SMQ1/SMQ2", "Capture the backlog pattern and failed LUWs before changing queue settings.", "INC0048133 journal + EWM queue procedure"),
        ("Compare wave-release volume with configured processing capacity", "Determine whether the degradation aligns with a peak window or a technical bottleneck.", "Warehouse operations data + performance evidence"),
        ("Apply the approved tuning path and validate a peak-window sample", "Confirm throughput improves without creating duplicate warehouse tasks or starving other queues.", "Controlled performance-change process"),
    ),
    "INC0048134": _resolution_plan(
        "Restore RF session re-authentication by isolating the mobility-policy refresh from user authorization and gateway connectivity.",
        ("Capture a failed device session and run SU53 for the affected identity", "Distinguish a missing warehouse authorization from a token or mobility-policy issue.", "INC0048134 journal + security evidence"),
        ("Compare the refreshed mobility policy with the prior approved version", "Identify whether a policy claim, certificate, or session setting changed during the controlled refresh.", "Change evidence + IAM controls"),
        ("Validate re-authentication on a representative RF device", "Confirm repeated login and scan activity works before releasing the correction broadly.", "Warehouse tester confirmation"),
    ),
    "INC0048135": _resolution_plan(
        "Confirm the resolved inbound-delivery delay remains stable and that the transient communication interruption has not left a queue backlog.",
        ("Review the recovered delivery replication in SMQ1/SMQ2", "Confirm the relevant ERP-to-EWM queue has drained without failed or duplicate LUWs.", "INC0048135 closure + EWM queue evidence"),
        ("Validate one inbound delivery in /SCWM/MON", "Ensure the delivery is visible and processable in EWM after the communication recovery.", "Warehouse validation"),
    ),
    "INC0048136": _resolution_plan(
        "Correct the EWM stock-type mismatch by comparing source stock attributes, target mapping, and the blocked bin update.",
        ("Inspect the affected stock and bin status in /SCWM/MON", "Capture the expected and actual stock type before attempting a resynchronization.", "INC0048136 journal + EWM monitor"),
        ("Compare the ERP-to-EWM stock-type mapping and queue payload", "Identify whether the mismatch originates in master data, mapping logic, or a failed replication message.", "Integration evidence + EWM configuration"),
        ("Reprocess a controlled sample and validate bin status", "Confirm the approved status update reaches the selected bin without changing unrelated stock.", "Warehouse validation + change control"),
    ),
    "INC0048137": _resolution_plan(
        "Protect warehouse-label processing by relieving spool saturation and proving capacity before the next label-generation window.",
        ("Review spool utilization in SPAD and active work processes in SM50", "Identify whether spool servers, work processes, or output volume is saturating the label path.", "INC0048137 journal + Basis capacity evidence"),
        ("Inspect the label jobs in SM37", "Correlate job runtime, spool size, and peak schedule before adjusting capacity or release timing.", "SM37 evidence + warehouse label schedule"),
        ("Apply the approved capacity or scheduling adjustment", "Validate a representative label run and retain rollback evidence before the next warehouse peak.", "Basis change-control process"),
    ),
    "INC0048138": _resolution_plan(
        "Maintain the resolved HANA backup chain by confirming the next checkpoint and retaining compliance evidence.",
        ("Review backup status and handoff history in DBACOCKPIT", "Confirm the delayed log-backup handoff completed and the retention chain is intact.", "INC0048138 closure + Basis backup procedure"),
        ("Monitor the next scheduled checkpoint", "A successful subsequent checkpoint confirms the recovery is durable rather than a one-off delay.", "Backup-monitoring evidence"),
    ),
    "INC0048139": _resolution_plan(
        "Renew the RFC TLS certificate before expiry through controlled connectivity validation.",
        ("Inspect the destination in SM59 and certificate chain in STRUST", "Confirm expiry date, host, trust chain, and the exact destination affected before replacement.", "INC0048139 journal + RFC TLS runbook"),
        ("Validate the replacement certificate in the approved path", "Test trust and connection in non-production or the approved cutover window before production activation.", "Certificate-control procedure"),
        ("Run a representative RFC connectivity test after renewal", "Confirm scheduled interfaces use the renewed chain without handshake or authorization failure.", "Integration Operations confirmation"),
    ),
    "INC0048140": _resolution_plan(
        "Recover the QA transport import lock by confirming ownership, preserving the rollback point, and re-running the controlled import.",
        ("Inspect the import queue and logs in STMS", "Capture transport request, return code, queue position, and lock owner before clearing or reimporting.", "INC0048140 journal + transport recovery KBA"),
        ("Verify the lock with SM12 and the approved rollback point", "Do not release a lock or reimport until Basis confirms no active deployment process owns it.", "Basis recovery controls + release evidence"),
        ("Re-run the QA import and complete release validation", "Confirm the transport imports once, QA validation proceeds, and no stale queue entry remains.", "Release Management confirmation"),
    ),
    "INC0048141": _resolution_plan(
        "Restore Design BOM classification routing by using the linked RCA and controlled mapping change rather than manually bypassing the queue.",
        ("Inspect the Design BOM and failed classification payload", "Confirm the object type, route, and target material-class queue that failed after the mapping release.", "INC0048141 journal + KBA-PLM-522"),
        ("Use PRB0031023 to validate the omitted route mapping", "The linked RCA contains the approved-versus-deployed mapping comparison needed to avoid a speculative fix.", "PRB0031023 + linked topology"),
        ("Validate CHG0092101 in QA before production release", "Reprocess a representative BOM only after the corrected route passes controlled downstream classification validation.", "CHG0092101 + Veeva PLM SOP"),
    ),
    "INC0048142": _resolution_plan(
        "Restore recipe approvals by proving scheduler contention and validating the approved capacity change before releasing the backlog.",
        ("Capture scheduler queue depth, worker utilization, and timeout timing", "Confirm the contention profile during the quality-review window rather than treating a single timeout as a data issue.", "INC0048142 journal + KBA-PLM-534"),
        ("Use PRB0031024 to verify the capacity threshold", "The linked problem holds the measured root-cause evidence and preventive alert design.", "PRB0031024 + scheduler RCA"),
        ("Wait for CHG0092102 and validate a controlled approval sample", "The incident is on hold for the capacity change; test representative approvals after implementation before releasing all queued work.", "CHG0092102 + Veeva recipe-approval control"),
    ),
    "INC0048143": _resolution_plan(
        "Keep recipe-approval reconciliation controlled until PRB0031024 confirms the scheduler root cause and approved recovery path.",
        ("Review the reconciliation evidence against the linked scheduler pattern", "Confirm every paused approval is part of the known contention pattern and not a separate quality-data fault.", "INC0048143 journal + PRB0031024"),
        ("Obtain the RCA-approved workaround before changing approvals", "The record is correctly on hold awaiting the Problem; do not manually reconcile regulated approvals without the confirmed path.", "On-hold reason + Veeva quality procedure"),
        ("Validate the reconciliation sample after capacity recovery", "Confirm the approval audit trail, status, and quality review outcome before closing the incident.", "Quality Operations validation"),
    ),
    "INC0048144": _resolution_plan(
        "Perform dependent warehouse recovery validation only after the parent qRFC incident reports a controlled recovery state.",
        ("Confirm INC0048102 has completed its queue and authorization validation", "This child record must not independently change queue settings while the parent recovery is active.", "Parent topology + INC0048102 journal"),
        ("Run the prepared warehouse regression test in /SCWM/MON", "After parent clearance, validate the dependent flow, goods issue, and queue status with the prepared evidence set.", "EWM recovery-validation SOP"),
        ("Document the child validation against the parent closure evidence", "Link the result so the parent and child records retain one consistent recovery narrative.", "ServiceNow relational record policy"),
    ),
    "PRB0031023": _resolution_plan(
        "Eliminate the PLM classification-route regression by proving the deployed profile differs from the approved mapping and validating the correction in QA.",
        ("Use PTASK003101 evidence to identify the omitted route", "The closed comparison confirms which engineering BOM object type is absent from the deployed mapping profile.", "PTASK003101 closure + PRB0031023"),
        ("Complete PTASK003102 with representative QA payloads", "Validate corrected routing to approved material classes before allowing the linked change to proceed.", "PTASK003102 + QA evidence"),
        ("Feed the verified mapping into CHG0092101", "The change should deploy only the approved correction with the exported profile available as rollback.", "CHG0092101 + Veeva mapping-RCA"),
    ),
    "CHG0092101": _resolution_plan(
        "Deploy the approved PLM classification-route correction after CAB authorization and QA evidence review.",
        ("Verify CTASK003101 rollback export and checksum", "The current mapping profile is the controlled rollback point if downstream classification validation fails.", "CTASK003101 closure + change evidence"),
        ("Obtain CAB authorization before CTASK003102 deployment", "The change is in Authorize; do not deploy the corrected route while authorization or QA evidence is incomplete.", "CHG0092101 CAB status + Veeva change control"),
        ("Validate Design BOM routing and material classification after deployment", "Use representative payloads to confirm downstream processing and attach the result before closing the change.", "PRB0031023 + business validation"),
    ),
    "PRB0031024": _resolution_plan(
        "Resolve PLM scheduler contention by turning the measured concurrency profile into an approved capacity and alerting design.",
        ("Use PTASK003201 to establish the saturation threshold", "The closed profile defines queue wait time, worker utilization, and concurrent-review conditions that reproduce the failure.", "PTASK003201 closure + scheduler RCA"),
        ("Complete PTASK003202 with capacity and alert values", "Validate the target against regulated approval load and document the threshold that will trigger intervention before timeouts.", "PTASK003202 + KBA-PLM-534"),
        ("Provide the approved design to CHG0092102", "The linked change should implement only the capacity and alert values validated by the RCA.", "CHG0092102 + Veeva scheduler-RCA"),
    ),
    "CHG0092102": _resolution_plan(
        "Implement the validated PLM scheduler capacity and concurrency alerting change with rollback and approval-workflow verification.",
        ("Use CTASK003201 baseline as the implementation reference", "Compare post-change queue wait time and worker utilization with the captured baseline.", "CTASK003201 closure + capacity evidence"),
        ("Complete CTASK003202 after the approved capacity target is confirmed", "Configure only the approved worker and alert values; retain the prior values for rollback.", "CTASK003202 + change assessment"),
        ("Run a controlled recipe-approval load test", "Validate that concurrent quality approvals complete within target and that the alert fires before saturation.", "PRB0031024 + Quality Operations validation"),
    ),
}

for _ticket_id, _plan in TICKET_RESOLUTION_PLANS.items():
    _ticket = MOCK_DB[_ticket_id]
    _ticket.ai_resolution_summary = str(_plan["summary"])
    # Keep the existing RAG/chat guide aligned with the canonical executive
    # summary instead of allowing an older generic sentence to leak into a
    # different channel.
    _ticket.ai_resolution_guide = _ticket.ai_resolution_summary
    _ticket.ai_resolution_steps = list(_plan["steps"])


def _relationship_snapshot(
    ticket_id: str,
    include_close_notes: bool = False,
    include_journal: bool = False,
) -> dict[str, object]:
    """Create relationship metadata, never a competing ticket record copy."""

    ticket = MOCK_DB[ticket_id]
    snapshot = {
        "sys_id": ticket.sys_id,
        "number": ticket.number,
        "title": ticket.title,
        "short_description": ticket.short_description,
        "state": ticket.state,
        "type": ticket.type,
        "latest_note": ticket.work_notes[-1].value,
    }
    if include_journal:
        snapshot["comments"] = [entry.model_dump() for entry in ticket.comments]
        snapshot["additional_comments"] = ticket.additional_comments
    if ticket.type == "CHG":
        snapshot["ctasks"] = ticket.ctasks
    if ticket.type == "PRB":
        snapshot["ptasks"] = ticket.ptasks
    if ticket.type == "RITM":
        snapshot["sctasks"] = ticket.sctasks
    if include_close_notes and ticket.close_notes:
        snapshot["close_notes"] = ticket.close_notes
    if ticket.type == "PRB":
        snapshot["prb_phase"] = ticket.prb_phase or "New"
    if ticket.type == "CHG":
        snapshot["chg_phase"] = ticket.chg_phase or "New"
    return snapshot


def resolve_child_tickets(ticket: Ticket) -> list[dict[str, object]]:
    """Resolve an incident's child cards directly from canonical child IDs.

    The response intentionally uses the current full child record every time;
    parent topology can therefore never retain stale child comments or state.
    """

    if ticket.type != "INC":
        return []
    return [
        _relationship_snapshot(child_id, include_close_notes=True)
        for child_id in ticket.child_ids
        if child_id in MOCK_DB and MOCK_DB[child_id].type == "INC"
    ]


def _enrich_relationship_topology() -> None:
    """Publish only valid, type-specific ServiceNow ITIL relationship graphs."""

    for ticket in MOCK_DB.values():
        # Reset display relationships so legacy links cannot leak into an invalid graph.
        explicit_parent = ticket.parent_incident
        explicit_originating = ticket.originating_tickets.copy()
        explicit_children = [
            _relationship_snapshot(str(child["number"]), include_close_notes=True)
            if str(child.get("number", "")).upper() in MOCK_DB and MOCK_DB[str(child["number"]).upper()].type == "INC"
            else child
            for child in ticket.child_incidents
        ]
        ticket.parent_inc = None
        ticket.originating_tickets = []
        ticket.child_incs = []
        ticket.child_incidents = []
        ticket.child_tickets = []
        ticket.linked_prb = None
        ticket.linked_chg = None

        if ticket.type == "INC":
            if explicit_parent:
                ticket.parent_incident = explicit_parent
                ticket.parent_inc = explicit_parent
            elif ticket.parent_id in MOCK_DB:
                ticket.parent_incident = _relationship_snapshot(ticket.parent_id)
                ticket.parent_inc = ticket.parent_incident
            elif ticket.parent_incident_id in MOCK_DB:
                ticket.parent_incident = _relationship_snapshot(ticket.parent_incident_id)
                # parent_inc is retained as a transition alias for existing consumers.
                ticket.parent_inc = ticket.parent_incident
            else:
                ticket.parent_incident = None
            if explicit_children and ticket.parent_incident is None:
                ticket.child_incs = explicit_children
                ticket.child_incidents = explicit_children
            elif ticket.child_ids and ticket.parent_incident is None:
                children = resolve_child_tickets(ticket)
                ticket.child_incs = children
                ticket.child_incidents = children
                ticket.child_tickets = children
            elif ticket.child_incident_ids and ticket.parent_incident is None:
                children = resolve_child_tickets(ticket)
                ticket.child_incs = children
                ticket.child_incidents = children
                ticket.child_tickets = children
            if ticket.linked_problem in MOCK_DB:
                ticket.linked_prb = _relationship_snapshot(ticket.linked_problem)
            if ticket.linked_change in MOCK_DB:
                ticket.linked_chg = _relationship_snapshot(ticket.linked_change)

        elif ticket.type == "PRB":
            ticket.parent_incident = None
            ticket.originating_tickets = explicit_originating or [
                _relationship_snapshot(ticket_id)
                for ticket_id in ticket.originating_ticket_ids
                if ticket_id in MOCK_DB
            ]
            if ticket.linked_change in MOCK_DB:
                ticket.linked_chg = _relationship_snapshot(ticket.linked_change)

        elif ticket.type == "CHG":
            ticket.parent_incident = None
            ticket.originating_tickets = explicit_originating or [
                _relationship_snapshot(ticket_id)
                for ticket_id in ticket.originating_ticket_ids
                if ticket_id in MOCK_DB
            ]
            # CHGs intentionally expose only their originating ticket and CTasks.
            ticket.child_incident_ids = []


_enrich_relationship_topology()
register_ticket_records(MOCK_DB)
