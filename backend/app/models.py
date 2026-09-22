"""Mock enterprise ITSM records and health classification for the ATLAS demo."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    assignment_group: str
    sla_status: SlaStatus | None = None
    sla_remaining_mins: int | None = None
    sentiment: Sentiment | None = None
    rca_phase: str | None = None
    cab_status: str | None = None
    risk_level: str | None = None
    # Public topology fields follow the ServiceNow relationship direction for each
    # record type. The *_id fields below remain internal mock-data inputs only.
    parent_incident: dict[str, object] | None = None
    originating_tickets: list[dict[str, object]] = Field(default_factory=list)
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
    work_notes: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
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
        priority_map = {"P1": "1 - Critical", "P2": "2 - High", "P3": "3 - Moderate", "P4": "4 - Low"}
        self.priority = priority_map.get(self.priority, self.priority)
        state_map = {"Fulfillment": "In Progress", "Root Cause Analysis": "Root Cause Analysis"}
        self.state = state_map.get(self.state, self.state)
        self.work_notes = self.work_notes or [self.latest_work_notes]
        if self.type in {"INC", "RITM"}:
            self.comments = self.comments or self.additional_comments or self.work_notes.copy()
            self.additional_comments = self.comments
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
        self.knowledge_refs = self.knowledge_refs or _knowledge_references(self.number, self.title)
        self.ai_resolution_guide = self.ai_resolution_guide or (
            f"Confirm the reported impact, execute the approved remediation for {self.title}, "
            "validate service recovery with the requester, and document the evidence in work notes."
        )
        return self


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
            "source_type": "Google Drive KT/SUD Hub",
            "title": f"{number} KT Video Recording and SUD walkthrough PPT",
            "path_or_url": f"Google Drive / ATLAS / KT Hub / {number} / SUD-walkthrough.pptx | KT-video-recording",
            "summary": "Operational context, handover steps, and a recorded walkthrough for first-line resolution.",
        },
    ]


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


MOCK_DB: dict[str, Ticket] = {
    "INC0048102": Ticket(
        id="INC0048102", type="INC", record_type="INC", title="SAP EWM qRFC Queue Lock",
        description="A locked SAP EWM qRFC queue is blocking warehouse replication and delaying outbound processing.", state="In Progress",
        priority="P1", assignee="Maya Chen", assignment_group="SAP EWM Support", sla_status="BREACHED", sla_remaining_mins=15, sentiment="Frustrated",
        child_incidents=[{"sys_id": "sys_inc_2", "number": "INC0048103", "short_description": "Token refresh failure for operations users", "state": "In Progress"}], linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="SAP EWM support isolated a stuck qRFC queue owner after the replication job retry.",
        closure_notes="Pending validated queue unlock and confirmation from warehouse operations.",
        additional_comments=["Warehouse operations reports outbound queues are locked after the replication job retry.", "SAP EWM support is validating the qRFC queue owner and unlock procedure with the integration team."],
        resources={"KBA": "KBA-ATLAS-1042 — Desktop client authentication recovery", "Veeva": "Veeva Vault / Quality / ATLAS-Auth-Investigation", "GDrive": "ATLAS / Major Incidents / INC0048102"},
    ),
    "RITM0094101": Ticket(
        id="RITM0094101", type="RITM", record_type="RITM", title="Provision SAP EWM 1010 Sandbox Roles",
        description="Service request to provision approved SAP EWM 1010 sandbox roles for a project team.", state="Fulfillment",
        priority="P3", assignee="Priya Nair", assignment_group="SAP EWM Support", sla_status="ON_TRACK", sla_remaining_mins=360, sentiment="Calm",
        latest_work_notes="Role request validated against the approved sandbox access matrix and queued for provisioning.",
        closure_notes="Close after role assignment and requester confirmation.",
        resources={"KBA": "KBA-EWM-1010 — Sandbox role provisioning", "Veeva": "Veeva Vault / Access / EWM-1010-Roles", "GDrive": "ATLAS / Service Requests / RITM0094101"},
    ),
    "INC0048103": Ticket(
        id="INC0048103", type="INC", record_type="INC", title="Token refresh failure for operations users",
        description="Child incident tracking the token refresh symptom reported by warehouse operations.", state="In Progress",
        priority="P2", assignee="Maya Chen", assignment_group="QMS Compliance Ops", sla_status="AT_RISK", sla_remaining_mins=85, sentiment="Impatient",
        parent_incident={"sys_id": "sys_inc_1", "number": "INC0048102", "short_description": "SAP EWM qRFC Queue Lock", "state": "In Progress"}, linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="Reproduced with the affected policy group and attached traces to the problem record.",
        closure_notes="Close after the corrective change has been verified in production.",
        resources={"KBA": "KBA-ATLAS-1042 — Desktop client authentication recovery", "Veeva": "Veeva Vault / Quality / Token-Refresh-Validation", "GDrive": "ATLAS / Major Incidents / INC0048103"},
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
        resources={"KBA": "KBA-SAP-2024 — Batch authorization diagnostics", "Veeva": "Veeva Vault / SAP / Batch-Access", "GDrive": "ATLAS / Incidents / INC0048104"},
    ),
    "RITM0094102": Ticket(
        id="RITM0094102", type="RITM", record_type="RITM", title="Provision Veeva Vault quality reviewer role",
        description="Approved request to grant Quality Reviewer access to a Veeva Vault workspace.", state="Fulfillment",
        priority="P3", assignee="Sofia Moretti", assignment_group="Veeva Vault Admin", sla_status="ON_TRACK", sla_remaining_mins=540, sentiment="Calm",
        latest_work_notes="Requester approval and training evidence were verified; access is queued for the next fulfillment cycle.",
        closure_notes="Close after access confirmation and audit trail verification.",
        resources={"KBA": "KBA-VEEVA-081 — Quality reviewer fulfillment", "Veeva": "Veeva Vault / Access / RITM0094102", "GDrive": "ATLAS / Service Requests / RITM0094102"},
    ),
    "INC0048105": Ticket(
        id="INC0048105", type="INC", record_type="INC", title="AWS data ingestion worker capacity alarm",
        description="Data ingestion workers are saturated and delaying regulated reporting feeds.", state="In Progress",
        priority="P1", assignee="Avery Brooks", assignment_group="AWS Cloud Infrastructure", sla_status="BREACHED", sla_remaining_mins=25, sentiment="Frustrated",
        latest_work_notes="On-call engineers are increasing worker capacity while investigating the traffic anomaly.",
        closure_notes="Close after sustained queue recovery and reporting-feed validation.",
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
        description="Purchase orders in SAP MM remain stuck in the approval workflow and cannot be released to suppliers.", state="In Progress",
        priority="P2", assignee="Nina Keller", assignment_group="SAP MM Support", sla_status="AT_RISK", sla_remaining_mins=95, sentiment="Impatient",
        child_incident_ids=["INC0048111"], latest_work_notes="Workflow agent trace shows a missing substitution rule after the latest purchasing-org update.",
        closure_notes="Close after test POs complete approval and the buyer confirms release processing.",
        additional_comments=["Buyers report that high-priority PO approvals have been waiting longer than two hours.", "SAP MM support is comparing the affected purchasing organization to the working template."],
        similar_records=[{"id": "PRB0018992", "score": 95, "title": "Historical Root Cause: PO Release Strategy Config Corruption", "state": "Closed", "resolution_date": "Last Month"}],
        historical_tickets=[{"id": "INC0042911", "title": "PO Release Strategy sync failure", "resolution_date": "3 months ago", "close_notes_snippet": "Restarted the PO release workflow in SWPR. Users were able to approve immediately after.", "relevance_score": 82}],
        resources={"KBA": "KBA-SAP-MM-118 — PO workflow release diagnosis", "Veeva": "Veeva Vault / Procurement / MM-Workflow-SOP", "GDrive": "ATLAS / SAP KT Hub / MM / PO-workflow-SUD.pptx"},
    ),
    "INC0048111": Ticket(
        id="INC0048111", type="INC", record_type="INC", title="SAP MM PO Workflow Child Approval Exception",
        description="Child incident for a purchasing group whose PO approval substitution rule is not being applied.", state="In Progress",
        priority="P2", assignee="Nina Keller", assignment_group="SAP MM Support", sla_status="AT_RISK", sla_remaining_mins=90, sentiment="Impatient",
        parent_incident_id="INC0048110", latest_work_notes="Approval exception has been isolated to the purchasing-group substitution configuration.",
        closure_notes="Close after the substitution rule is restored and PO approval completes.",
        additional_comments=["Buyer supplied a failing PO example and approval timestamp.", "Customer-visible update: the purchasing group exception is under active correction."],
        resources={"KBA": "KBA-SAP-MM-119 — PO approval child exception", "Veeva": "Veeva Vault / Procurement / MM-Workflow-SOP", "GDrive": "ATLAS / SAP KT Hub / MM / PO-approval-child-SUD.pdf"},
    ),
    "INC0048112": Ticket(
        id="INC0048112", type="INC", record_type="INC", title="SAP SD Billing Document IDoc Failure",
        description="SAP SD billing IDocs failed during invoice document generation for completed deliveries.", state="Resolved",
        priority="1 - Critical", assignee="Marco Silva", assignment_group="SAP SD Support", sla_status="ON_TRACK", sla_remaining_mins=180, sentiment="Calm",
        latest_work_notes="Corrected the pricing condition mapping and completed a monitored billing IDoc reprocess.",
        closure_notes="Billing IDocs were reprocessed successfully and finance confirmed invoice postings.", close_code="Solved (Permanently)",
        additional_comments=["Finance was notified that the billing document reprocess completed successfully.", "Customer-visible update: delayed invoices are now available for posting."],
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
        description="SolMan Technical Monitoring detected job Z_EWM_RECON_NIGHTLY canceled in client 100 with dump ITAB_ERROR_IN_INITIAL_SIZE.", state="In Progress",
        priority="P1", assignee="Jonas Weber", assignment_group="SAP Basis Ops", sla_status="BREACHED", sla_remaining_mins=18, sentiment="Frustrated",
        latest_work_notes="Basis on-call is reviewing SM37 spool and ST22 dump evidence for the nightly EWM reconciliation run.",
        additional_comments=["SolMan monitoring raised a P1 alert after the nightly reconciliation job canceled.", "Warehouse reconciliation is delayed pending batch job recovery."],
        similar_records=[{"id": "INC0048121", "score": 98, "title": "Duplicate: Nightly EWM reconciliation job cancellation alert", "state": "New", "resolution_date": "Current Triage Queue"}],
        knowledge_refs=[{"source_type": "ServiceNow KBA", "title": "SolMan KBA — SM37 batch job dump recovery", "path_or_url": "https://servicenow.example.local/kb?id=solman-sm37-itab-error", "summary": "Guided SM37, ST22, and job-log triage for failed EWM batch runs."}, {"source_type": "Veeva Vault SOP", "title": "SAP Note 2491021 controlled implementation SOP", "path_or_url": "Veeva Vault / QMS / SAP Notes / 2491021.pdf", "summary": "Controlled review procedure for SAP Note 2491021 and related monitoring fixes."}, {"source_type": "Google Drive KT/SUD Hub", "title": "SolMan job monitoring KT video", "path_or_url": "Google Drive / ATLAS / KT Hub / SolMan / SM37-job-monitoring-video", "summary": "Recorded walkthrough for identifying redundant SolMan monitoring alerts."}],
        resources={"KBA": "KBA-SOLMAN-212 — SM37 job cancellation", "Veeva": "Veeva Vault / QMS / SAP Note 2491021", "GDrive": "ATLAS / SolMan KT / SM37-monitoring-video"},
    ),
    "INC0048121": Ticket(
        id="INC0048121", type="INC", record_type="INC", title="Duplicate SolMan Alert: Batch Job Z_EWM_RECON_NIGHTLY canceled",
        description="Automated alert trigger for failed job Z_EWM_RECON_NIGHTLY.", state="New",
        priority="P1", assignee="Triage Queue", assignment_group="Observability & Monitoring", sla_status="AT_RISK", sla_remaining_mins=45, sentiment="Impatient",
        latest_work_notes="Alert correlation engine flagged this event as a likely duplicate of the SAP Basis incident.",
        additional_comments=["Automated monitoring opened this alert from the same nightly EWM reconciliation job cancellation.", "Triage should link this duplicate to the active SAP Basis investigation."],
        similar_records=[{"id": "INC0048120", "score": 98, "title": "SolMan Alert: SM37 Batch Job Z_EWM_RECON_NIGHTLY failed with ABAP dump", "state": "In Progress", "resolution_date": "Active Work Item"}],
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
        resources={"KBA": "KBA-ALM-4091 — HP ALM to ServiceNow sync", "Veeva": "Veeva Vault / QMS / ALM-ServiceNow-Bridge-SOP", "GDrive": "ATLAS / ALM KT / Defect-sync-replay-SUD.pdf"},
    ),
}


def _relationship_snapshot(ticket_id: str, include_close_notes: bool = False) -> dict[str, object]:
    ticket = MOCK_DB[ticket_id]
    snapshot = {
        "sys_id": ticket.sys_id,
        "number": ticket.number,
        "title": ticket.title,
        "short_description": ticket.short_description,
        "state": ticket.state,
        "type": ticket.type,
        "latest_note": ticket.work_notes[-1],
        "comments": ticket.comments,
        "additional_comments": ticket.additional_comments,
        "ctasks": ticket.ctasks,
        "ptasks": ticket.ptasks,
        "sctasks": ticket.sctasks,
    }
    if include_close_notes and ticket.close_notes:
        snapshot["close_notes"] = ticket.close_notes
    if ticket.type == "PRB":
        snapshot["prb_phase"] = ticket.prb_phase or "New"
    if ticket.type == "CHG":
        snapshot["chg_phase"] = ticket.chg_phase or "New"
    return snapshot


def _enrich_relationship_topology() -> None:
    """Publish only valid, type-specific ServiceNow ITIL relationship graphs."""

    for ticket in MOCK_DB.values():
        # Reset display relationships so legacy links cannot leak into an invalid graph.
        explicit_parent = ticket.parent_incident
        explicit_originating = ticket.originating_tickets.copy()
        explicit_children = ticket.child_incidents.copy()
        ticket.parent_inc = None
        ticket.originating_tickets = []
        ticket.child_incs = []
        ticket.child_incidents = []
        ticket.linked_prb = None
        ticket.linked_chg = None

        if ticket.type == "INC":
            if explicit_parent:
                ticket.parent_incident = explicit_parent
                ticket.parent_inc = explicit_parent
            elif ticket.parent_incident_id in MOCK_DB:
                ticket.parent_incident = _relationship_snapshot(ticket.parent_incident_id)
                # parent_inc is retained as a transition alias for existing consumers.
                ticket.parent_inc = ticket.parent_incident
            else:
                ticket.parent_incident = None
            if explicit_children and ticket.parent_incident is None:
                ticket.child_incs = explicit_children
                ticket.child_incidents = explicit_children
            elif ticket.child_incident_ids and ticket.parent_incident is None:
                children = [
                    _relationship_snapshot(child_id, include_close_notes=True)
                    for child_id in ticket.child_incident_ids
                    if child_id in MOCK_DB and MOCK_DB[child_id].type == "INC"
                ]
                ticket.child_incs = children
                ticket.child_incidents = children
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
