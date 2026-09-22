"""Mock ITSM records and health classification for the ATLAS demo."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HealthColor = Literal["RED", "YELLOW", "GREEN"]
SlaStatus = Literal["BREACHED", "AT_RISK", "ON_TRACK"]
Sentiment = Literal["Frustrated", "Impatient", "Calm"]


class Ticket(BaseModel):
    """The information required by the dashboard and ticket detail view."""

    id: str
    record_type: Literal["INC", "PRB", "CHG"]
    title: str
    description: str
    state: str
    priority: str
    assignee: str
    sla_status: SlaStatus
    sentiment: Sentiment
    parent_incident: str | None = None
    child_incidents: list[str] = Field(default_factory=list)
    linked_problem: str | None = None
    linked_change: str | None = None
    latest_work_notes: str
    closure_notes: str
    resources: dict[str, str]


def calculate_health_color(ticket: Ticket) -> HealthColor:
    """Return the most severe health state from SLA and user sentiment."""

    if ticket.sla_status == "BREACHED" or ticket.sentiment == "Frustrated":
        return "RED"
    if ticket.sla_status == "AT_RISK" or ticket.sentiment == "Impatient":
        return "YELLOW"
    return "GREEN"


MOCK_DB: dict[str, Ticket] = {
    "INC0048102": Ticket(
        id="INC0048102", record_type="INC", title="Atlas desktop client cannot authenticate",
        description="Several research users cannot sign in to the Atlas desktop client.", state="In Progress",
        priority="P1", assignee="Maya Chen", sla_status="BREACHED", sentiment="Frustrated",
        child_incidents=["INC0048103"], linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="Identity team isolated a token refresh failure after the latest policy update.",
        closure_notes="Pending validated remediation and confirmation from the affected research group.",
        resources={"KBA": "KBA-ATLAS-1042 — Desktop client authentication recovery", "Veeva": "Veeva Vault / Quality / ATLAS-Auth-Investigation", "GDrive": "ATLAS / Major Incidents / INC0048102"},
    ),
    "INC0048103": Ticket(
        id="INC0048103", record_type="INC", title="Token refresh failure for clinical operations users",
        description="Child incident tracking the token refresh symptom reported by clinical operations.", state="In Progress",
        priority="P2", assignee="Maya Chen", sla_status="AT_RISK", sentiment="Impatient",
        parent_incident="INC0048102", linked_problem="PRB0019201", linked_change="CHG0092100",
        latest_work_notes="Reproduced with the affected policy group and attached traces to the problem record.",
        closure_notes="Close after the corrective change has been verified in production.",
        resources={"KBA": "KBA-ATLAS-1042 — Desktop client authentication recovery", "Veeva": "Veeva Vault / Quality / Token-Refresh-Validation", "GDrive": "ATLAS / Major Incidents / INC0048103"},
    ),
    "PRB0019201": Ticket(
        id="PRB0019201", record_type="PRB", title="Authentication policy refresh regression",
        description="Root-cause investigation for the policy refresh regression behind linked incidents.", state="Root Cause Analysis",
        priority="P1", assignee="Omar Rahman", sla_status="AT_RISK", sentiment="Calm",
        parent_incident="INC0048102", child_incidents=["INC0048103"], linked_change="CHG0092100",
        latest_work_notes="RCA points to an expired claim mapping included in the policy baseline.",
        closure_notes="Problem remains open until the change review confirms corrective controls.",
        resources={"KBA": "KBA-ATLAS-1057 — Claim mapping diagnostics", "Veeva": "Veeva Vault / Quality / PRB0019201-RCA", "GDrive": "ATLAS / Problems / PRB0019201"},
    ),
    "CHG0092100": Ticket(
        id="CHG0092100", record_type="CHG", title="Correct expired claim mapping in production policy",
        description="Controlled change to correct the policy claim mapping and validate client sign-in.", state="Scheduled",
        priority="P2", assignee="Elena Rossi", sla_status="ON_TRACK", sentiment="Calm",
        parent_incident="INC0048102", child_incidents=["INC0048103"], linked_problem="PRB0019201",
        latest_work_notes="CAB approved the low-risk configuration correction for the next release window.",
        closure_notes="Post-implementation validation will confirm authentication and token refresh recovery.",
        resources={"KBA": "KBA-ATLAS-1061 — Policy change validation", "Veeva": "Veeva Vault / Change Control / CHG0092100", "GDrive": "ATLAS / Changes / CHG0092100"},
    ),
}
