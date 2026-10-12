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
        "id": "VEEVA-EWM-SOP-104",
        "title": "GxP Controlled Recovery for SAP EWM qRFC Queue Locks",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/EWM-SOP-104",
        "summary": "Approved procedure for diagnosing and recovering EWM qRFC queue locks while preserving audit evidence and warehouse continuity.",
        "content": "SAP EWM qRFC queue lock controlled recovery. First confirm business impact, queue names, affected warehouse number, and an approved incident/change record. In SM12, identify the lock owner, user, client, object, and age; do not delete a lock until ownership and active processing are verified. In SMQ1, inspect outbound qRFC queues for queue status, destination, LUW error text, and retry history. In SMQ2, inspect inbound qRFC queues and confirm whether the queue is stopped, executing, or blocked by a predecessor. Capture SM12, SMQ1, and SMQ2 evidence before any intervention. Coordinate an approved unlock or controlled queue restart with EWM, Basis, and middleware owners. Validate warehouse task creation, goods issue posting, queue drain, and absence of re-locks after recovery. Record business confirmation, validation timestamps, and rollback/escalation evidence in the ServiceNow journal.",
        "ticket_numbers": ["INC0048102", "PRB0031022", "CHG0092100", "INC0048144"],
        "tags": ["sap", "ewm", "gxp", "veeva", "qrfc", "queue", "queue lock", "sm12", "smq1", "smq2", "warehouse recovery"],
    },
    {
        "id": "VEEVA-EWM-SOP-117",
        "title": "GxP Warehouse Task and Staging Area Recovery Guidelines",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/EWM-SOP-117",
        "summary": "Controlled triage and validation guidance for blocked warehouse tasks, staging, and outbound wave processing.",
        "content": "SAP EWM warehouse task and staging recovery. Confirm the warehouse process type, activity area, staging area, wave, delivery, and handling-unit scope before changing task state. Review warehouse task status and exception codes, then check whether stock, staging bins, or delivery items are blocked by an open predecessor task. Preserve queue and task evidence before retrying any task. Use an approved business-continuity process when physical warehouse movement must continue. After remediation, validate warehouse task confirmation, staging-bin stock consistency, wave release, delivery status, and goods issue posting. Obtain warehouse-supervisor confirmation and document any manual fallback activity, reconciliation result, and residual risk.",
        "ticket_numbers": ["INC0048132", "INC0048133", "INC0048136"],
        "tags": ["sap", "ewm", "gxp", "veeva", "warehouse task", "staging", "wave", "outbound", "goods issue", "reconciliation"],
    },
    {
        "id": "VEEVA-EWM-SOP-128",
        "title": "GxP RF Handheld Scanner Connection Recovery and Validation",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/EWM-SOP-128",
        "summary": "Approved recovery sequence for RF handheld authentication, gateway connectivity, and post-recovery scanning validation.",
        "content": "SAP EWM RF handheld recovery. Confirm whether impact is isolated to one device, a wireless access point, a gateway node, or all users. Capture device ID, user, warehouse number, timestamp, RF transaction, network location, and gateway error before restarting sessions. Verify authorized role and token/session validity before changing access controls. Check RF gateway and connection-pool health with Basis/network owners, then use an approved controlled restart only when the impact and rollback are understood. Validate login, menu access, one representative scan, warehouse task confirmation, and follow-on queue processing. Record device-level evidence, business confirmation, and any temporary manual process used during the outage.",
        "ticket_numbers": ["INC0048109", "INC0048134"],
        "tags": ["sap", "ewm", "gxp", "veeva", "rf", "handheld", "scanner", "gateway", "connection", "authentication", "warehouse"],
    },
    {
        "id": "VEEVA-EWM-SOP-141",
        "title": "GxP Physical Inventory Difference Clearing in SAP EWM",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/EWM-SOP-141",
        "summary": "Controlled process for investigating and clearing EWM physical-inventory differences with segregation-of-duties and reconciliation evidence.",
        "content": "SAP EWM physical inventory difference clearing. Confirm the physical-inventory document, bin, stock type, material, batch, handling unit, and count history. Do not clear a difference until recount requirements, tolerance rules, approval authority, and potential quality impact have been assessed. Preserve the initial count, recount, and stock snapshot evidence. Investigate open warehouse tasks, staging movements, pending queues, and ERP/EWM replication before posting an adjustment. Use the approved difference-clearing transaction and dual-control approval path. Validate the resulting EWM stock, ERP reconciliation, inventory document status, and downstream financial or quality impact. Retain approver, reason code, reconciliation outcome, and closure evidence.",
        "ticket_numbers": ["INC0048136"],
        "tags": ["sap", "ewm", "gxp", "veeva", "physical inventory", "inventory difference", "stock", "reconciliation", "count", "difference clearing"],
    },
    {
        "id": "VEEVA-PLM-SOP-215",
        "title": "GxP SAP PLM Recipe Approval and Classification Recovery",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/PLM-SOP-215",
        "summary": "Controlled diagnosis for PLM recipe approval delays, design BOM classification routing, and regulated material master synchronization.",
        "content": "SAP PLM controlled recovery for recipe approval and classification integration. Confirm the recipe, specification, design BOM, material, approval step, and release impact. Capture scheduler queue depth, workflow timestamps, failed payload identifiers, and current approval state before retrying anything. For classification routing, compare approved and deployed field mappings, object types, class assignments, and material master destinations. For recipe workflow delay, confirm worker pool capacity, scheduled job health, approval ownership, and pending predecessor steps. Do not restart a regulated approval workflow or deploy a mapping correction without approved change control and rollback evidence. Validate the corrected payload in QA, confirm the recipe approval trail, material classification, and downstream manufacturing planning result. Retain validation screenshots, audit trail references, business confirmation, and any deviation assessment.",
        "ticket_numbers": ["INC0048125", "INC0048141", "INC0048142", "INC0048143", "PRB0031023", "PRB0031024", "CHG0092101", "CHG0092102"],
        "tags": ["sap", "plm", "gxp", "veeva", "recipe", "approval", "classification", "design bom", "material master", "scheduler", "workflow"],
    },
    {
        "id": "VEEVA-BASIS-SOP-233",
        "title": "GxP SAP Basis Job, Transport, and Gateway Recovery Controls",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/BASIS-SOP-233",
        "summary": "Controlled recovery guidance for Basis batch jobs, transports, RF gateway connectivity, and supporting infrastructure evidence.",
        "content": "SAP Basis controlled recovery. For a batch job, capture SM37 job log, spool, dump details, job variant, client, and technical user before restarting. For transport issues, record transport request, target system, import queue, lock owner, return code, and approved rollback point before clearing or reimporting. For RF or gateway disruption, establish whether the impact is device specific, node specific, or network wide, then preserve gateway, ICM, connection pool, and certificate evidence. Confirm authorization and SU53 evidence before altering roles. Use approved change control for production configuration, transport, restart, certificate, or capacity changes. Validate the scheduled job, import queue, representative RF transaction, and downstream business process after recovery. Record operator, timestamps, approvals, validation evidence, and escalation path.",
        "ticket_numbers": ["INC0048104", "INC0048109", "INC0048120", "INC0048137", "INC0048138", "INC0048139", "INC0048140"],
        "tags": ["sap", "basis", "gxp", "veeva", "sm37", "transport", "stms", "rf gateway", "icm", "su53", "certificate", "spool"],
    },
    {
        "id": "VEEVA-MM-SOP-247",
        "title": "GxP SAP MM Purchase Order Release and Supplier Master Recovery",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/MM-SOP-247",
        "summary": "Controlled investigation and remediation for purchase order release failures, supplier master validation, and procurement approval evidence.",
        "content": "SAP MM controlled recovery for purchase order release and supplier master validation. Confirm the purchase order, release strategy, purchasing group, approver, supplier, plant, and business deadline. Preserve release workflow logs, authorization evidence, change history, and any interface payload before retriggering approval. Check release strategy configuration, approval prerequisites, blocked predecessor steps, supplier master mandatory attributes, and integration status. Do not alter release configuration or supplier attributes in production without approved change control and an auditable rollback path. After remediation, validate the release sequence, approver visibility, supplier master result, purchasing document status, and downstream message. Record requester confirmation, approver evidence, validation output, and closure notes.",
        "ticket_numbers": ["INC0048110", "INC0048111", "INC0048131", "RITM0094101"],
        "tags": ["sap", "mm", "gxp", "veeva", "purchase order", "po", "release strategy", "supplier master", "approval", "procurement", "workflow"],
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
        "id": "VEEVA-ALM-SOP-319",
        "title": "GxP HP ALM Test Plan, Test Set, and Test Run Lifecycle",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/ALM-SOP-319",
        "summary": "Controlled procedure for HP ALM test planning, evidence capture, review, approval, execution, and change-request testing closure across BAU10, LAL, and LAURA.",
        "content": "HP ALM controlled test lifecycle for BAU10, LAL, and LAURA. Select the correct HP ALM domain before any work: FIXE for LAL, FPSEWD for BAU10, and MMMCLC for LAURA. In Testing > Test Plan, select the applicable Unit Testing or System Acceptance Testing folder and create a new test from the Tests tab or folder context menu. BAU10 unit testing is only for authorization changes. BAU10 naming is UT_3W_A_OPS_<Role name> for unit tests and SAT_CHGnumber_CHGdescription for system acceptance testing. LAL must follow CSV naming conventions and does not require a test version; LAURA follows the BAU10 pattern. Complete the test description and open the created test plan. Assign required resources: Designer, Review, Assessor IT from L2, and Validation. For LAL, Designer does not review and Quality approval by Michael Haug is required. For LAURA, assign Assessor Business to Jurij Novokrescenov or Jeton Fanaj. In Req Coverage, link the related URS, FS, and TDS from the Change Request Risk Impact Analysis; where no relevant document exists, leave coverage empty only with a CSV explanation. In Design Steps, enter a description and expected result, then use General to set Evidence Required to Y before saving. Submit the test plan by moving it from In Progress to Ready for Review. The IT assessor changes it from Ready for Review to Ready for Approval with credentials; notify the required second reviewer and then Validation, plus Quality for LAL. A Test Set may be created while approval is pending, but a Test Run must not be created until its Test Plan is approved. In Test Lab, create a Test Set in the appropriate folder, name it, use Select Tests in the execution grid to link the approved Test Plan, then set Ready for Testing and choose Run Test Set. In the run window, choose Begin Run. Capture execution evidence through Attachments. LAL attaches screenshots to each step; LAURA attaches screenshots to the test run/test rather than an individual step. Use Pass Selected only after recording an Actual Result that is materially different from the Expected Result; do not copy and paste expected wording. End the test run. In Test Runs, open the test-run ID, review Resources, and for BAU10 and LAURA assign yourself as a reviewer where required before saving. Move the run from In Progress to Ready for Review; the IT assessor performs Ready for Review to Ready for Approval with credentials where applicable. Notify remaining reviewers, obtain Validation approval and LAL Quality approval where required, then update the Change Request and close its testing task only after the associated test plan/run is approved.",
        "ticket_numbers": ["CHG0092100", "CHG0092101", "CHG0092102"],
        "tags": ["hp alm", "alm", "quality center", "veeva", "gxp", "test plan", "test set", "test run", "test lab", "unit testing", "system acceptance testing", "sat", "ut", "requirement coverage", "urs", "fs", "tds", "evidence required", "review", "approval", "validation", "quality", "bau10", "lal", "laura", "change request"],
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
    {
        "id": "GDRIVE-LEAP-SUD-201",
        "title": "LEAP SUD: EH&S Data Transmission and Hazardous Material Monitoring",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-LEAP-SUD-201",
        "summary": "System user documentation for EH&S data synchronisation from P08 through ERP into SAP EWM and safe hazardous-material monitoring.",
        "content": "LEAP EH&S hazardous-material SUD. Safe EWM putaway depends on storage class, flash point, and pH value. Storage class prevents chemically incompatible materials being co-stored. Flash point must be sent in degrees Celsius and determines flammable-safe storage. pH is not automated by IDoc; it must be entered manually in EWM. The technical flow is EH&S P08 to ERP to EWM using IDoc message type HAZARDOUSSUBSTANCE; EWM has no direct P08 interface. When ERP storage class or flash point changes, trigger transmission in HSMR02 with the material and logistical data. After the IDoc, maintain pH in MAT1, Warehouse Data, custom Z-fields as a numeric value. Verify the consolidated result in Warehouse Management Monitor, Roche Enhancement to Product. For normal-bin putaway with blank hazardous fields, rerun HSMR02. For missing pH, update MAT1. For flash-point unit errors, correct ERP to Celsius. For a stuck IDoc, inspect technical segments in WE02. The scrapping exception permits storage-class mixing in one handling unit only for documented disposal tasks because quantities are negligible.",
        "ticket_numbers": ["INC0048125", "INC0048136"],
        "tags": ["sap", "ewm", "ehs", "hazardous", "hazardous material", "storage class", "flash point", "ph", "p08", "erp", "idoc", "hazardoussubstance", "hsmr02", "mat1", "we02", "putaway", "scrapping", "google drive", "sud"],
    },
    {
        "id": "GDRIVE-LEAP-SUD-202",
        "title": "LEAP SUD: Request Hub Material Ordering and Order Monitoring",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-LEAP-SUD-202",
        "summary": "System user documentation for Request Hub ordering, middleware tracing, EWM request monitoring, release jobs, and status exceptions.",
        "content": "LEAP Request Hub SUD. Request Hub is the material-ordering front end for EWM and ERP managed stock, external Limfinity or Signals material, and minus-80 degree CUBE material. An Order ID represents the whole basket and a Request ID represents an individual line item; support should trace Request IDs for discrepancies. Standard material needs a delivery level, while CUBE material needs both a delivery level and destination bin or the request is blocked. The integration path is Request Hub to MuleSoft to DataRiver to EWM through the OData API. If an order does not appear in EWM, inspect /IWFWND/TRACES and filter user MULELEAP for rejected payload evidence. Valid requests create locked or blocked picking warehouse tasks until the delivery date. Job DEF_RELEASE_WHO, program ZL84_RELEASE_WHO, releases eligible tasks at 02:00 and 13:00. ZL84_REQ_ORDE stores order headers, ZL84_REQ_REQUEST stores request lines, and ZL84_REQ_WHT maps warehouse tasks to Request IDs. In Warehouse Monitor, Roche Enhancement to Request Order to Request, statuses move only forward: O Open awaiting picking, P Picked, S Staged, C Closed delivered, or Cancelled. Secondary-level stock can automatically stage or close without task creation. Manual cancellation is allowed before Closed; reverse status movement is forbidden.",
        "ticket_numbers": ["RITM0094101", "INC0048132", "INC0048133"],
        "tags": ["sap", "ewm", "request hub", "material ordering", "order id", "request id", "mulesoft", "datariver", "odata", "iwfwnd/traces", "muleleap", "warehouse task", "def_release_who", "zl84_release_who", "zl84_req_orde", "zl84_req_request", "zl84_req_wht", "cube", "google drive", "sud"],
    },
    {
        "id": "GDRIVE-LEAP-SUD-203",
        "title": "LEAP SUD: Disposal of EWM Materials and Retained Samples",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-LEAP-SUD-203",
        "summary": "System user documentation for expired-material disposal, scrapping warehouse tasks, SCRAP-ZONE movement, and final goods issue.",
        "content": "LEAP disposal SUD. The disposal date is the SAP batch expiration date plus Disposal Days, maintained as ZZ1_DISPOSAL_DAYS in MAT1 Warehouse Data. Warehouse leads monitor upcoming disposal in Warehouse Monitor, Roche Enhancements to Stock to Disposal Overview, which combines expiration, disposal date, and handling-unit data. Monthly report /SCWM/R_WME_MON_NODE_BTC_RUN sends the prior-month reached disposal list to the shared Google mailbox. Start disposal in ERP with MIGO movement type 551 and the material and quantity. EWM then creates a scrapping outbound delivery and picking warehouse task; L2 support must confirm queue PRT0-SCRAP. The RF operator selects Outbound Processes to Picking by Queue and PRT0-SCRAP, then confirms the source handling unit into a transport handling unit. In this SCRAP queue only, different storage classes may be mixed in the transport HU. Confirmation creates a follow-up warehouse task from staging to SCRAP-ZONE. Complete final goods issue in /SCWM/PRDO by selecting the delivery and posting GI.",
        "ticket_numbers": ["INC0048136"],
        "tags": ["sap", "ewm", "disposal", "scrap", "scrapping", "retained samples", "expiration", "zz1_disposal_days", "mat1", "scwm/r_wme_mon_node_btc_run", "migo", "551", "outbound delivery", "prt0-scrap", "scrap-zone", "rf", "scwm/prdo", "goods issue", "google drive", "sud"],
    },
    {
        "id": "GDRIVE-LEAP-SUD-204",
        "title": "LEAP SUD: SAP EWM Goods Receipt and Handling Unit Processing",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-LEAP-SUD-204",
        "summary": "System user documentation for the LEAP SAP EWM Goods Receipt process: inbound delivery handling, HU packaging, capacity validation, putaway, cancellations, and label printing.",
        "content": "LEAP SAP EWM Goods Receipt SUD. Start with the inbound delivery in /SCWM/PRDI: physically check the delivered quantity, review the delivery and temperature requirements, then deconsolidate material by required temperature zone. Create the handling units and apply the required labels; only the same material type may be packed in one handling unit. Validate capacity before putaway: capacity checks must be active for the storage type, product-master capacity consumption must be maintained under units of measure, destination-bin capacity must be maintained, and the selected HU type must be permitted for that storage type and bin type. Create the putaway warehouse task, pack the HU into a transport HU where needed, and use Assign HU to Transport HU to route it by conveyor or lift to primary level 0000 or 050. In primary storage, run Putaway by HU, scan the transport or source HU, and confirm the final destination bin. Use exception code CHPD only when an approved alternate bin is required. In LEAP, final goods receipt posting occurs when the destination putaway warehouse task is confirmed. EWM managed consumables, non-EWM Signals or Limfinity material, beads, rack packs, and retained samples have distinct handling. For Signals or Limfinity HU pulling, EWM uses the external handling-unit barcode through an API to build the HU tree; an open warehouse task is created in RF if none exists. Hazardous putaway uses storage class, flash point, pH, and temperature control indicators; minus-80 degree CUBE storage is not EWM managed. If putaway is not complete, cancel all open warehouse tasks before rejecting the inbound delivery. Labels can be printed in Work Center Pack, Warehouse Monitor Physical Stock, or the packing dialogue for HU reprint.",
        "ticket_numbers": ["INC0048132", "INC0048133", "INC0048136"],
        "tags": ["sap", "ewm", "goods receipt", "gr", "handling unit", "hu", "hu pulling", "signals", "limfinity", "capacity", "storage type", "bin capacity", "hu type", "putaway", "chpd", "conveyor", "hazardous", "inbound delivery", "label printing", "cube", "google drive", "sud"],
    },
    {
        "id": "GDRIVE-LEAP-SUD-205",
        "title": "LEAP SUD: LAB2WHS Return Process from Laboratory to Warehouse",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/GDRIVE-LEAP-SUD-205",
        "summary": "System user documentation for returning laboratory handling units to primary or secondary storage and managing LAB2WHS exceptions.",
        "content": "LEAP LAB2WHS SUD. LAB2WHS returns research material from laboratory storage to warehouse storage while validating temperature and hazardous requirements. For a long-term return to primary storage, the scientist or technician uses RF Option 4 Put away by HU, enters an RO ID, scans the handling unit, selects Primary, and scans a secondary intermediate bin. The system creates a follow-up warehouse task to the primary destination. A floor-assigned Lab Concierge logs in, uses Option 4 Picking by Q, selects the queue such as LEVEL 01 to PS04, scans a transport HU and source HU, reviews hazardous warnings and storage class, and puts the transport HU in the logistics intermediate conveyor bin. The logistics team completes Option 2 Put away by HU, scans the transport HU, confirms warnings, and scans the final primary bin. For temporary secondary storage, select Secondary and scan the destination bin; the warehouse task confirms immediately with no follow-up task. For administrative stock transfer, identify HUs in Warehouse Management Monitor, manually create a warehouse task with Process Type 10, and enter the primary destination bin. Returns must start before the Request Hub GI Buffer consumption job posts goods issue; consumed HUs cannot use LAB2WHS return. Temperature and storage class are checked using a custom Z-table. Queue determination follows activity areas: LEVEL XX to PSXX for lab-to-warehouse and PSXX to LEVEL XX for warehouse-to-lab. Resource groups map Lab Concierges to floors and queues.",
        "ticket_numbers": ["INC0048133", "INC0048136"],
        "tags": ["sap", "ewm", "lab2whs", "lab to warehouse", "return", "primary storage", "secondary storage", "lab concierge", "ro id", "picking by queue", "level", "ps04", "transport hu", "process type 10", "gi buffer", "temperature", "storage class", "queue determination", "resource group", "google drive", "sud"],
    },
    {
        "id": "VEEVA-CHG-SOP-041",
        "title": "GxP ServiceNow Change Management and ALM Evidence Lifecycle",
        "source_type": "Veeva Vault SOP",
        "system": "Veeva Vault",
        "connector": "Veeva Vault",
        "url": "https://roche.veevavault.com/documents/CHG-SOP-041",
        "summary": "Controlled normal and authorization change process covering ServiceNow assessment, GxP approval, HP ALM evidence, C task closure, and regulated implementation.",
        "content": "ServiceNow Change Management SOP for regulated SAP systems. Start from the analysed incident and create a normal Change Request linked to the originating incident; authorization changes follow the applicable standard-change flow. Keep the Change description high level: state the pre-change system behaviour, expected behaviour, and corrective action without copying raw error text. In Assess, assign L3 for code fixes or L1 for business-process assessment, create an L2 alignment meeting task with L1 and L3 stakeholders, and complete the system assessment questionnaire. Determine GxP impact from the URS identifier. GxP-impacting changes require Quality Assurance approval in Authorize; non-GxP changes require the Service Owner or deputy and Validation Lead. Before approval, update final testing details and the Final Impact Assessment. Do not alter an approved initial impact assessment; record any changed assumption under deviations to the initial impact assessment. In Schedule, ensure every C task has closure comments and complete build and testing-preparation tasks. Formal test evidence is produced in HP ALM: create an approved test plan with requirements coverage for URS, FS, and TDS, assign review and validation resources, set Evidence Required to Y for each step, create a test set, link the approved plan, execute the test run in QBS, collect timestamped screenshots or logs with instance identifiers, and record plan and run IDs in the Change Request. For BAU10, unit testing is only for authorization changes; SAT names use the Change number and description. After validation approval, the GPM integration team implements in the approved maintenance window, typically an alternate Wednesday in an even week. Capture post-implementation cut-over activities, business validation, residual risk, and approvals. If requirements remain, create a child Change Request and document the deviation; if build or test corrections are required, create a new build task or record the correction in the deviation section. Address validation-tracker feedback before final sign-off. Close the testing task and Change only after evidence, approvals, and C task closure comments are complete. The traceability matrix and validation registry remain the governed source for URS, FS, TDS, document versions, and required reviewer roles.",
        "ticket_numbers": ["CHG0092100", "CHG0092101", "CHG0092102", "INC0048110", "INC0048122"],
        "tags": ["servicenow", "change management", "change request", "normal change", "authorization change", "gxp", "assessment", "authorize", "schedule", "implement", "ctask", "closure comments", "final impact assessment", "deviation", "quality assurance", "validation", "service owner", "alm", "hp alm", "test plan", "test set", "test run", "evidence required", "urs", "fs", "tds", "traceability matrix", "validation registry", "qbs", "gpm", "cab", "maintenance window", "veeva", "sop"],
    },
    {
        "id": "GDRIVE-SUD-SAP-EWM-001",
        "title": "SUD SAP EWM: Inbound Delivery, Quality Inspection, and qRFC Queue Governance",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-SAP-EWM-001",
        "summary": "GxP runbook for EWM inbound delivery processing, QIE inspection documents, warehouse tasks, and controlled qRFC remediation.",
        "content": "SUD-SAP-EWM-001 applies to SAP EWM, S/4HANA Core, HP ALM, and Veeva Vault. For inbound delivery processing, ERP creates the delivery in VL31N and transmits it to EWM through qRFC. EWM creates an Inbound Delivery Notification and then an Inbound Delivery document. In /SCWM/PRDI, enter the ERP delivery or EWM document number, unload the header, physically count against the delivery note, and post Goods Receipt. ERP receives the material document and EWM stock moves to the received-on-dock GR area. Create warehouse tasks from /SCWM/PRDI in background or foreground through /SCWM/TAS_CREATE. Storage control chooses the storage type search sequence using hazard class, storage condition, and handling-unit type. Confirm warehouse tasks in /SCWM/TO_CONF or RFUI; stock moves from ROD to final storage. Where the material is QM-managed, QIE creates inspection type 1701 or 1704, posts stock to Quality Inspection Stock, creates samples linked to the HU, and moves stock after the QM/QIE usage decision to unrestricted or blocked status. For /SCWM/DELIVERY 003 zero gross or net weight errors, inspect delivery Goods Movement Data, verify UOM in /SCWM/MAT1, resynchronise conversions with /SCWM/R_ERP_MAT_CHECK, calculate weight and volume under the item data lock, save, and retry GR. For IDN QIE_INSP_DOC 012, confirm SAP Note 3145892 or equivalent, process the IDN in /SCWM/MON under Inbound Delivery Notification, force QID regeneration, and activate a stopped SMQ2 queue with F6 only after evidence is captured. For a qRFC queue lock, capture queue name, LUW error, destination, and ST22 evidence; confirm lock ownership in SM12, resolve the underlying cause, then reset and activate the approved SMQ1 or SMQ2 queue and validate the downstream warehouse document.",
        "ticket_numbers": ["INC0048102", "INC0048133", "INC0048136", "PRB0031022"],
        "tags": ["sap", "ewm", "inbound delivery", "goods receipt", "scwm/prdi", "vl31n", "qrfc", "warehouse task", "scwm/tas_create", "scwm/to_conf", "rfui", "quality inspection", "qie", "inspection 1701", "inspection 1704", "rod", "scwm/delivery 003", "weight volume", "scwm/mat1", "scwm/r_erp_mat_check", "qid", "qie_insp_doc 012", "smq2", "google drive", "sud"],
    },
    {
        "id": "GDRIVE-SUD-SAP-BASIS-002",
        "title": "SUD SAP BASIS: Transport Management, Queue Governance, and System Maintenance",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-SAP-BASIS-002",
        "summary": "GxP runbook for TMS promotion, transport quality gates, SMQ1/SMQ2 SYSFAIL diagnosis, and controlled queue recovery.",
        "content": "SUD-SAP-BASIS-002 governs SAP S/4HANA, Solution Manager, HP ALM, and ServiceNow technical operations. Create Workbench or Customizing transports in RBS005 using SE09 or SE10 and follow GxP naming standards. Complete SCI or ATC checks and unit tests, release underlying tasks first, then release the main transport. BAU10 transport validation must retain the relevant unit-test and authorization-change evidence before promotion. For quality lane RBS010, use STMS_IMPORT, select the target queue, choose the transport request, and apply approved import options. Import to RBS020 production only in a scheduled maintenance window after formal Quality Lead sign-off. A transport Return Code 8 requires review of the STMS import log and failed object before retry; correct the identified dependency or activation error through approved change control. For SMQ1 or SMQ2 queues in SYSFAIL, collect the queue and ST22 dump evidence first. Investigate network loss, destination availability, locked tables, or uncaught ABAP dumps. If a confirmed stale lock is the cause, use SM12 only after confirming data-integrity risk and ownership. Resolve RFC or network availability issues before retry. In SMQ1 or SMQ2 use Debug Queue only where needed for diagnosis, Reset Status, then Activate Queue and verify RUNNING status. Record queue evidence, approver decisions, restart outcome, and validation result in the linked ServiceNow record.",
        "ticket_numbers": ["INC0048120", "INC0048104", "INC0048109", "INC0048137", "INC0048140"],
        "tags": ["sap", "basis", "transport", "tms", "stms_import", "se09", "se10", "rbs005", "rbs010", "rbs020", "sci", "atc", "smq1", "smq2", "sysfail", "st22", "sm12", "rfc", "queue", "maintenance window", "google drive", "sud"],
    },
    {
        "id": "GDRIVE-SUD-SAP-PLM-003",
        "title": "SUD SAP PLM: Engineering Change Masters, DIRs, and BOM Control",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-SAP-PLM-003",
        "summary": "GxP runbook for Engineering Change Master lifecycle, controlled BOM/DIR changes, release keys, and AENNR lock remediation.",
        "content": "SUD-SAP-PLM-003 covers GxP-critical Engineering Change Masters, Document Info Records, and Bill of Material control. Create an Engineering Change Order in CC01 by entering AENNR and change type. Enable the required object flags for BOM, Document, or Material Master. Create a Document Info Record in CV01N and revise the controlled document in CV02N; when changing a BOM in CS02 or a document in CV02N, enter the AENNR so every modification follows the controlled version trail. Draft document versions such as 12.1 can progress through review, while the controlled whole version such as 13.0 is assigned only after full approval. Release the Change Master in CC02 by setting Release Key status 01 Fully Released. For CC032, where the AENNR is locked or its release key is not set, determine whether the Valid-From date has not been reached, the release key remains Draft, or another user owns an exclusive session. Remove a confirmed stale lock through SM12, set the Release Key in CC02 when approvals permit, and adjust Valid-From only under approved engineering change control. Retain evidence of the original error, lock ownership, approvals, version state, and post-release validation.",
        "ticket_numbers": ["INC0048125", "INC0048141", "INC0048142", "PRB0019202", "PRB0031023"],
        "tags": ["sap", "plm", "engineering change", "ecm", "change master", "aennr", "cc01", "cc02", "cs02", "cv02n", "bom", "document info record", "dir", "release key", "cc032", "valid from", "sm12", "google drive", "sud"],
    },
    {
        "id": "GDRIVE-SUD-SAP-MM-004",
        "title": "SUD SAP MM: Procurement Goods Movements and Invoice Matching",
        "source_type": "Google Drive KT/SUD Hub",
        "system": "Google Drive",
        "connector": "Google Drive",
        "url": "https://drive.google.com/file/d/SUD-SAP-MM-004",
        "summary": "GxP runbook for PO goods receipt, batch and shelf-life capture, MIGO movement 101, and restricted-batch/SLED failure recovery.",
        "content": "SUD-SAP-MM-004 covers SAP MM procurement execution, goods movements, and invoice matching. Before goods receipt, confirm that the purchase order is released in ME29N. In MIGO select Goods Receipt with Purchase Order as the reference document and use movement type 101 where applicable. Enter the vendor batch, date of manufacture, and shelf-life expiration date, then post to create the material document. MIRO three-way matching compares the purchase order, goods receipt, and supplier invoice before invoice posting. For QA 007 Restricted Batch Status, inspect the batch display in MSC3N and obtain the Quality decision; only then use MSC2N to change the batch to Unrestricted and repost MIGO. For M7 042 expired SLED, verify the threshold and correct the Date of Manufacture on the MIGO Batch tab where it was entered incorrectly. For M8 147 account determination missing, inspect the material valuation and account-assignment context in MM03, then validate the relevant valuation class and transaction-key configuration in OBYC before reposting MIGO. Preserve the PO, QA decision, batch status, SLED or account-determination evidence, and material-document outcome for auditability.",
        "ticket_numbers": ["INC0048110", "PRB0030991"],
        "tags": ["sap", "mm", "procurement", "goods receipt", "migo", "movement type 101", "purchase order", "me29n", "vendor batch", "manufacture date", "sled", "shelf life", "qa 007", "m7 042", "msc2n", "invoice matching", "google drive", "sud"],
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
