"""Canonical enterprise knowledge registry for the ATLAS demo.

Every ServiceNow KBA, Veeva Vault document, HP ALM defect, and Google Drive
KT/SUD asset is declared once here. Ticket cards, API responses, and RAG
retrieval read from this registry instead of maintaining separate copies of
the same source metadata.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, TypedDict


class CentralKnowledgeRecord(TypedDict):
    id: str
    title: str
    source_type: str
    system: str
    connector: str
    url: str
    summary: str
    content: str
    ticket_numbers: list[str]
    tags: list[str]


CENTRAL_KNOWLEDGE_DB: tuple[CentralKnowledgeRecord, ...] = (
    {
        "id": "KBA003192",
        "title": "SAP EWM qRFC Queue Lock Resolution & SM12 Unlock Procedure",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA003192",
        "summary": "Approved qRFC queue unlock, SM12 validation, and warehouse recovery steps.",
        "content": "SAP EWM qRFC queue lock recovery, SM12 unlock procedure, warehouse goods issue, batch authorization, and replication validation.",
        "ticket_numbers": ["INC0048102", "PRB0031022", "CHG0092100"],
        "tags": ["sap", "ewm", "qrfc", "queue", "sm12", "basis", "authorization"],
    },
    {
        "id": "VEEVA-SOP-0042",
        "title": "GxP Standard Operating Procedure for Batch Interface Access Controls",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/SOP-0042",
        "summary": "Controlled remediation requirements for SAP batch interface access changes.",
        "content": "GxP batch interface access controls, SAP authorization roles, approval evidence, and controlled remediation.",
        "ticket_numbers": ["INC0048102", "INC0048103", "PRB0031022", "CHG0092100"],
        "tags": ["sap", "batch", "access", "authorization", "grc", "security"],
    },
    {
        "id": "KBA-SEC-118",
        "title": "SAP GRC M_MSEG_LGO Authorization and Token Refresh Recovery",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA-SEC-118",
        "summary": "Role validation and controlled remediation for M_MSEG_LGO token refresh failures.",
        "content": "SAP Security GRC M_MSEG_LGO authorization, mobile token refresh, role delta validation, and goods movement access.",
        "ticket_numbers": ["INC0048103"],
        "tags": ["sap", "security", "grc", "token", "authorization", "m_mseg_lgo"],
    },
    {
        "id": "KBA-BASIS-210",
        "title": "NetWeaver RF Gateway Node Timeout Recovery",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA-BASIS-210",
        "summary": "Diagnostic and controlled restart guidance for SAP RF gateway node timeouts.",
        "content": "SAP BASIS NetWeaver RF handheld gateway, ICM connection pool, node timeout diagnostics, and controlled restart validation.",
        "ticket_numbers": ["INC0048109"],
        "tags": ["sap", "basis", "netweaver", "rf", "gateway", "timeout"],
    },
    {
        "id": "KBA-SD-FICO-350",
        "title": "SD-FI Billing Tax Code Determination Recovery",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA-SD-FICO-350",
        "summary": "Controlled diagnosis for SD billing blocks and FICO tax code determination failures.",
        "content": "SAP SD FICO billing document posting block, tax code determination, account assignment, and transport validation.",
        "ticket_numbers": ["INC0048110"],
        "tags": ["sap", "sd", "fico", "billing", "tax", "posting"],
    },
    {
        "id": "KB0062011",
        "title": "SAP PLM EHS Classification Synchronization Recovery",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KB0062011",
        "summary": "Recovery checks for failed PLM EHS specification synchronization.",
        "content": "SAP PLM EHS specification, Material Master classification, mapping validation, and controlled recovery checks.",
        "ticket_numbers": ["INC0048125"],
        "tags": ["sap", "plm", "mm", "ehs", "specification", "classification"],
    },
    {
        "id": "VEEVA-SPEC-0099",
        "title": "Controlled EHS Specification Synchronization Procedure",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/VEEVA-SPEC-0099",
        "summary": "GxP-controlled reconciliation procedure for SAP PLM EHS specifications.",
        "content": "GxP controlled SAP PLM EHS specification and Material Master classification reconciliation procedure.",
        "ticket_numbers": ["INC0048125"],
        "tags": ["sap", "plm", "mm", "ehs", "veeva", "classification"],
    },
    {
        "id": "ALM-DEF-8812",
        "title": "Known Defect: SAP PLM Classification and SolMan Alert Synchronization",
        "source_type": "HP ALM Defect",
        "system": "HP ALM",
        "connector": "HP ALM",
        "url": "https://alm.roche.com/qcbin/defect/8812",
        "summary": "Known PLM classification synchronization defect and related release-quality evidence.",
        "content": "SAP PLM classification synchronization defect, SolMan alert suppression, SAP EWM monitoring, and job-monitoring triage guidance.",
        "ticket_numbers": ["INC0048125"],
        "tags": ["sap", "plm", "classification", "alm", "defect", "solman"],
    },
    {
        "id": "GDRIVE-SUD-109",
        "title": "SAP MM PO Release Workflow Integration Architecture",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-109-ARCH",
        "summary": "Architecture and handover guidance for SAP MM workflow integration.",
        "content": "SAP MM purchase order release workflow, integration architecture, approval routing, and diagnostic handover information.",
        "ticket_numbers": [],
        "tags": ["sap", "mm", "purchase", "order", "workflow"],
    },
    {
        "id": "GDRIVE-SUD-311",
        "title": "SAP PLM to Material Master Classification Integration Architecture",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-SUD-311",
        "summary": "Architecture and L2 handover for PLM-to-Material Master synchronization.",
        "content": "System understanding document for SAP PLM, MM classification mappings, payload flow, and L2 support handover.",
        "ticket_numbers": ["INC0048125"],
        "tags": ["sap", "plm", "mm", "classification", "integration"],
    },
)

# Dense, source-balanced corpus used by the local vector prototype.  Records
# remain canonical here: the dashboard, ticket cards, and retrieval engine do
# not maintain their own copies of citation metadata.
CENTRAL_KNOWLEDGE_DB += (
    {
        "id": "KBA-MW-772",
        "title": "SAP PI/PO Queue Retry and Heap-Dump Triage Runbook",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA-MW-772",
        "summary": "Evidence-preserving triage for SAP PI/PO queue backlogs, heap pressure, and retry control.",
        "content": "SAP PI PO gateway message queue retry, Java heap dump collection, ERR_9921_SYNC_FAIL investigation, interface replay safety, and middleware escalation evidence.",
        "ticket_numbers": ["INC0048130"],
        "tags": ["sap", "po", "gateway", "memory", "heap", "queue", "retry", "middleware"],
    },
    {
        "id": "KBA-BASIS-428",
        "title": "SAP SM37 Batch Failure and SU53 Authorization Evidence Collection",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA-BASIS-428",
        "summary": "Runbook for technical-user job failures, authorization traces, and approved recovery validation.",
        "content": "SAP SM37 batch job cancellation, SU53 authorization trace, technical user role validation, background job restart safeguards, SolMan monitoring, and audit evidence.",
        "ticket_numbers": ["INC0048104", "INC0048120"],
        "tags": ["sap", "basis", "sm37", "su53", "batch", "authorization", "solman"],
    },
    {
        "id": "KBA-SD-519",
        "title": "SAP SD-FI Billing Posting and Tax Determination Validation",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA-SD-519",
        "summary": "Controlled validation sequence for SD billing release, tax-code mapping, and FI posting recovery.",
        "content": "SAP SD billing document block, FICO posting, tax code determination, account assignment mapping, transport validation, and finance reconciliation evidence.",
        "ticket_numbers": ["INC0048110", "PRB0030991"],
        "tags": ["sap", "sd", "fico", "billing", "tax", "posting", "finance"],
    },
    {
        "id": "KBA-SEC-244",
        "title": "GRC Emergency Role Assignment and Token Refresh Validation",
        "source_type": "ServiceNow KBA",
        "system": "ServiceNow",
        "connector": "ServiceNow",
        "url": "https://roche.service-now.com/kb_view.do?sysparm_article=KBA-SEC-244",
        "summary": "Segregation-of-duties checks and validation for emergency SAP authorization corrections.",
        "content": "SAP GRC emergency access, M_MSEG_LGO authorization, token refresh validation, role delta approval, audit logging, and warehouse mobility access control.",
        "ticket_numbers": ["INC0048103", "PRB0031022", "CHG0092100"],
        "tags": ["sap", "grc", "authorization", "token", "security", "m_mseg_lgo"],
    },
    {
        "id": "VEEVA-SOP-0185",
        "title": "GxP Change Control for SAP Interface and Master Data Remediation",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/SOP-0185",
        "summary": "Quality controls for approved interface changes, evidence capture, and rollback decisions.",
        "content": "GxP change control for SAP integration remediation, controlled transport, approval matrix, rollback plan, test evidence, deviation assessment, and closure requirements.",
        "ticket_numbers": ["CHG0092100", "INC0048110", "INC0048125"],
        "tags": ["gxp", "change", "transport", "sap", "integration", "rollback", "validation"],
    },
    {
        "id": "VEEVA-SOP-0261",
        "title": "Warehouse Business Continuity for EWM Queue and RF Device Outages",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/SOP-0261",
        "summary": "Approved manual-contingency and recovery validation steps for EWM disruption scenarios.",
        "content": "SAP EWM business continuity, qRFC queue lock, RF scanner outage, manual goods issue contingency, warehouse reconciliation, and recovery sign-off.",
        "ticket_numbers": ["INC0048102", "INC0048109"],
        "tags": ["sap", "ewm", "warehouse", "rf", "scanner", "qrfc", "continuity"],
    },
    {
        "id": "VEEVA-SOP-0307",
        "title": "Controlled Veeva Vault Access Fulfillment and Audit Verification",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/SOP-0307",
        "summary": "Controlled fulfilment procedure for regulated Vault role assignments and requester confirmation.",
        "content": "Veeva Vault reviewer access, training verification, manager approval, role fulfilment, audit trail validation, and requester confirmation.",
        "ticket_numbers": ["RITM0094102"],
        "tags": ["veeva", "access", "role", "audit", "training", "fulfillment"],
    },
    {
        "id": "ALM-DEF-9021",
        "title": "Known Defect: SD-FI Tax Mapping Regression After Release Transport",
        "source_type": "HP ALM Defect",
        "system": "HP ALM",
        "connector": "HP ALM",
        "url": "https://alm.roche.com/qcbin/defect/9021",
        "summary": "Release-quality evidence for a tax mapping regression affecting SD billing and FI posting.",
        "content": "HP ALM defect for SAP SD FICO tax mapping regression, release transport impact, billing document posting block, regression test evidence, and corrective transport.",
        "ticket_numbers": ["INC0048110", "PRB0030991"],
        "tags": ["sap", "sd", "fico", "tax", "billing", "alm", "defect"],
    },
    {
        "id": "ALM-DEF-9176",
        "title": "Known Defect: NetWeaver RF Gateway Node 02 Connection Pool Leak",
        "source_type": "HP ALM Defect",
        "system": "HP ALM",
        "connector": "HP ALM",
        "url": "https://alm.roche.com/qcbin/defect/9176",
        "summary": "Defect analysis and test evidence for intermittent RF gateway node connection failures.",
        "content": "SAP NetWeaver RF gateway node 02, connection pool leak, ICM timeout, controlled restart, handheld connectivity test, and release defect evidence.",
        "ticket_numbers": ["INC0048109"],
        "tags": ["sap", "basis", "netweaver", "rf", "gateway", "timeout", "alm"],
    },
    {
        "id": "ALM-DEF-9234",
        "title": "Known Defect: SAP PO Heap Fragmentation During High-Volume Replay",
        "source_type": "HP ALM Defect",
        "system": "HP ALM",
        "connector": "HP ALM",
        "url": "https://alm.roche.com/qcbin/defect/9234",
        "summary": "Known diagnostic pattern for SAP PO heap fragmentation during replay operations.",
        "content": "SAP PO memory fragmentation, high-volume message replay, Java heap dump, gateway instability, error signature comparison, and safe replay throttling.",
        "ticket_numbers": ["INC0048130"],
        "tags": ["sap", "po", "memory", "heap", "gateway", "replay", "alm"],
    },
    {
        "id": "GDRIVE-KT-442",
        "title": "SAP EWM Major Incident: qRFC Recovery and Warehouse Validation Walkthrough",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-KT-442",
        "summary": "L2/L3 knowledge-transfer walkthrough for qRFC, RF gateway, and post-recovery business validation.",
        "content": "SAP EWM qRFC recovery KT video, SM12 lock owner, RF handheld validation, warehouse goods issue testing, batch authorization verification, and major incident handover.",
        "ticket_numbers": ["INC0048102", "INC0048103", "INC0048109", "PRB0031022"],
        "tags": ["sap", "ewm", "qrfc", "warehouse", "rf", "sm12", "kt"],
    },
    {
        "id": "GDRIVE-SUD-508",
        "title": "SAP PI/PO Integration Landscape, Interface Ownership, and Replay Guardrails",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-SUD-508",
        "summary": "System-understanding document for PI/PO failure triage and message replay safety.",
        "content": "SAP PI PO architecture, gateway interface ownership, retry queues, message replay guardrails, heap diagnostics, downstream dependency mapping, and support handover.",
        "ticket_numbers": ["INC0048130"],
        "tags": ["sap", "pi", "po", "gateway", "integration", "replay", "sud"],
    },
)

class CentralTicketRepository:
    """The sole runtime record store for API, topology, and RAG reads.

    A future ServiceNow/PostgreSQL adapter only needs to replace `replace_all`;
    consumers retain the same lookup API and cannot build divergent embedded
    copies of a ticket's journal.
    """

    def __init__(self) -> None:
        self._records: dict[str, Any] = {}
        self._lock = RLock()

    def replace_all(self, records: Mapping[str, Any]) -> None:
        with self._lock:
            self._records.clear()
            self._records.update({str(key).upper(): record for key, record in records.items()})

    def records(self) -> Mapping[str, Any]:
        with self._lock:
            return MappingProxyType(self._records)

    def get(self, reference: str) -> Any | None:
        needle = reference.casefold()
        with self._lock:
            for ticket in self._records.values():
                if needle in {ticket.id.casefold(), ticket.number.casefold(), ticket.sys_id.casefold()}:
                    return ticket
        return None


# The ticket catalog is registered once during model initialization. API and
# RAG consumers access records through this repository rather than importing a
# separate mock dictionary, which keeps every ticket view on one data path.
CENTRAL_TICKET_REPOSITORY = CentralTicketRepository()


def register_ticket_records(records: Mapping[str, Any]) -> None:
    """Register the canonical typed ServiceNow records without copying them."""

    CENTRAL_TICKET_REPOSITORY.replace_all(records)


def central_ticket_records() -> Mapping[str, Any]:
    """Return the single authoritative in-memory ticket catalog."""

    return CENTRAL_TICKET_REPOSITORY.records()


def central_ticket_by_reference(reference: str) -> Any | None:
    """Look up a record by ticket number, mock id, or ServiceNow sys_id."""

    return CENTRAL_TICKET_REPOSITORY.get(reference)


def central_knowledge_documents() -> list[dict[str, str]]:
    """Return RAG-ready copies without exposing internal ticket/tag indexes."""

    return [
        {key: record[key] for key in ("id", "title", "system", "connector", "url", "content")}
        for record in CENTRAL_KNOWLEDGE_DB
    ]


def central_knowledge_records() -> list[CentralKnowledgeRecord]:
    """Return deep copies of canonical source records for connector ingestion."""

    return deepcopy(list(CENTRAL_KNOWLEDGE_DB))


def central_knowledge_references(ticket_number: str, title: str) -> list[dict[str, str]]:
    """Return canonical citation cards for an incident or work item."""

    words = {word.lower() for word in title.replace("/", " ").replace("-", " ").split() if len(word) > 2}
    exact = [record for record in CENTRAL_KNOWLEDGE_DB if ticket_number in record["ticket_numbers"]]
    related = [
        record for record in CENTRAL_KNOWLEDGE_DB
        if record not in exact and words.intersection(record["tags"])
    ]
    selected = (exact + related)[:4]
    return [
        {
            "source_type": record["source_type"],
            "title": f"{record['id']} — {record['title']}",
            "path_or_url": record["url"],
            "summary": record["summary"],
        }
        for record in deepcopy(selected)
    ]


def central_knowledge_summary() -> dict[str, object]:
    """Expose connector coverage without duplicating central record payloads."""

    connectors = sorted({record["connector"] for record in CENTRAL_KNOWLEDGE_DB})
    return {"connectors": connectors, "record_count": len(CENTRAL_KNOWLEDGE_DB)}
