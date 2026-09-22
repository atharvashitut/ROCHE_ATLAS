"""Mock enterprise ITSM records and health classification for the ATLAS demo."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
]


class Ticket(BaseModel):
    """A common ticket shape with metrics applicable to its ServiceNow type."""

    id: str
    type: TicketType
    # Kept during the UI transition so existing ticket detail rendering remains compatible.
    record_type: TicketType
    title: str
    description: str
    state: str
    priority: str
    assignee: str
    assignment_group: str
    sla_status: SlaStatus | None = None
    sla_remaining_mins: int | None = None
    sentiment: Sentiment | None = None
    rca_phase: str | None = None
    cab_status: str | None = None
    risk_level: str | None = None
    parent_incident: str | None = None
    child_incidents: list[str] = Field(default_factory=list)
    linked_problem: str | None = None
    linked_change: str | None = None
    latest_work_notes: str
    closure_notes: str
    resources: dict[str, str]


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
        id="INC0048102", type="INC", record_type="INC", title="Atlas desktop client cannot authenticate",
        description="Several research users cannot sign in to the Atlas desktop client.", state="In Progress",
        priority="P1", assignee="Maya Chen", assignment_group="SAP EWM Support", sla_status="BREACHED", sla_remaining_mins=15, sentiment="Frustrated",
        child_incidents=["INC0048103"], linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="Identity team isolated a token refresh failure after the latest policy update.",
        closure_notes="Pending validated remediation and confirmation from the affected research group.",
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
        id="INC0048103", type="INC", record_type="INC", title="Token refresh failure for clinical operations users",
        description="Child incident tracking the token refresh symptom reported by clinical operations.", state="In Progress",
        priority="P2", assignee="Maya Chen", assignment_group="QMS Compliance Ops", sla_status="AT_RISK", sla_remaining_mins=85, sentiment="Impatient",
        parent_incident="INC0048102", linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="Reproduced with the affected policy group and attached traces to the problem record.",
        closure_notes="Close after the corrective change has been verified in production.",
        resources={"KBA": "KBA-ATLAS-1042 — Desktop client authentication recovery", "Veeva": "Veeva Vault / Quality / Token-Refresh-Validation", "GDrive": "ATLAS / Major Incidents / INC0048103"},
    ),
    "PRB0019201": Ticket(
        id="PRB0019201", type="PRB", record_type="PRB", title="Authentication policy refresh regression",
        description="Root-cause investigation for the policy refresh regression behind linked incidents.", state="Root Cause Analysis",
        priority="P1", assignee="Omar Rahman", assignment_group="Integration Middleware", rca_phase="RCA In Progress", risk_level="High Impact",
        parent_incident="INC0048102", child_incidents=["INC0048103"], linked_change="CHG0092100",
        latest_work_notes="RCA points to an expired claim mapping included in the policy baseline.",
        closure_notes="Problem remains open until the change review confirms corrective controls.",
        resources={"KBA": "KBA-ATLAS-1057 — Claim mapping diagnostics", "Veeva": "Veeva Vault / Quality / PRB0019201-RCA", "GDrive": "ATLAS / Problems / PRB0019201"},
    ),
    "CHG0092100": Ticket(
        id="CHG0092100", type="CHG", record_type="CHG", title="Correct expired claim mapping in production policy",
        description="Controlled change to correct the policy claim mapping and validate client sign-in.", state="Scheduled",
        priority="P2", assignee="Elena Rossi", assignment_group="Integration Middleware", cab_status="CAB Approved", risk_level="Emergency Change",
        parent_incident="INC0048102", child_incidents=["INC0048103"], linked_problem="PRB0019201",
        latest_work_notes="CAB approved the low-risk configuration correction for the next release window.",
        closure_notes="Post-implementation validation will confirm authentication and token refresh recovery.",
        resources={"KBA": "KBA-ATLAS-1061 — Policy change validation", "Veeva": "Veeva Vault / Change Control / CHG0092100", "GDrive": "ATLAS / Changes / CHG0092100"},
    ),
    "INC0048104": Ticket(
        id="INC0048104", type="INC", record_type="INC", title="SAP EWM batch job authorization failure",
        description="Nightly EWM reconciliation batch cannot access the production job client.", state="In Progress",
        priority="P2", assignee="Jonas Weber", assignment_group="SAP Basis Ops", sla_status="AT_RISK", sla_remaining_mins=70, sentiment="Impatient",
        latest_work_notes="Basis team is validating the affected technical user authorization profile.",
        closure_notes="Close after the scheduled batch completes successfully and finance validates output.",
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
        id="PRB0019202", type="PRB", record_type="PRB", title="Oracle database connection pool exhaustion",
        description="Problem investigation into intermittent connection exhaustion across reporting services.", state="Root Cause Analysis",
        priority="P1", assignee="Ravi Patel", assignment_group="Oracle DB Services", rca_phase="Evidence Collection", risk_level="High Impact",
        latest_work_notes="Database services is correlating pool exhaustion with the month-end reporting workload.",
        closure_notes="Problem remains open until pool sizing and connection-leak remediation are validated.",
        resources={"KBA": "KBA-ORACLE-315 — Connection pool triage", "Veeva": "Veeva Vault / Database / PRB0019202", "GDrive": "ATLAS / Problems / PRB0019202"},
    ),
}
