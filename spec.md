# Roche ATLAS ITSM Co-Pilot — Data and Backend Architecture Specification

## Purpose

This specification describes how ATLAS stores, relates, serves, and retrieves operational data today. ATLAS is a read-only ITSM co-pilot PoC: it models ServiceNow work items, enterprise knowledge, operational analytics, topology, and RAG chat without writing back to ServiceNow or any connected system.

## Requirements

1. Maintain one canonical ticket dataset for Dashboard, Stats, topology, ticket drawer, AI analysis, and Chat.
2. Maintain one canonical enterprise-knowledge dataset for ServiceNow KBAs, Veeva Vault SOPs, HP ALM defects, and Google Drive KT/SUDs.
3. Resolve relationship views from current canonical records, not independently maintained embedded copies.
4. Calculate metrics dynamically from canonical ticket fields and active filters.
5. Build the vector index only from canonical ticket and knowledge data.
6. Keep retrieval and generation available without API keys through deterministic fallbacks.
7. Keep all integrations read-only in the PoC.

## Current Storage Model

### Canonical ticket repository

The PoC does not currently use PostgreSQL, ServiceNow, or another external transactional database at runtime. Ticket data is authored in `backend/app/models.py` as `MOCK_DB`, a dictionary of typed Pydantic `Ticket` objects.

At model initialization, `register_ticket_records(MOCK_DB)` stores references to those same objects in `CENTRAL_TICKET_REPOSITORY` from `backend/app/central_db.py`.

| Component | Role |
| --- | --- |
| `MOCK_DB` | Current authoring source for typed tickets |
| `CENTRAL_TICKET_REPOSITORY` | Canonical runtime access boundary |
| `central_ticket_records()` | Read-only `MappingProxyType` view used by APIs, RAG, stats, and agents |
| `central_ticket_by_reference()` | Lookup by ATLAS ID, ServiceNow number, or `sys_id` |

The repository uses an `RLock` for safe access and holds object references rather than a second ticket copy. Therefore `MOCK_DB` is the current source definition and the repository is the mandatory consumer path.

### Canonical knowledge repository

Enterprise documents are defined once in `backend/app/central_db.py` as `CENTRAL_KNOWLEDGE_DB`. Each `CentralKnowledgeRecord` contains:

| Field | Meaning |
| --- | --- |
| `id` | Stable source ID, such as `KBA003192` or `GDRIVE-LEAP-SUD-204` |
| `title` | Human-readable document name |
| `source_type` | ServiceNow KBA, Veeva Vault SOP, HP ALM Defect, or Google Drive KT/SUD Hub |
| `system` / `connector` | Source platform and connector route |
| `url` | Current source link or future live integration link |
| `summary` / `content` | Retrieval-ready source content |
| `ticket_numbers` | Explicit record references |
| `tags` | Deterministic relationship and retrieval keywords |

`central_knowledge_records()` returns deep copies for connector ingestion, preventing adapters from mutating the canonical registry.

### Derived stores

These are derived views, never independent systems of record:

| Derived artifact | Source |
| --- | --- |
| Ticket API payload | Canonical ticket repository plus calculated health, sentiment, SLA, and topology |
| Stats response | Filtered canonical ticket records |
| Topology snapshots | Canonical relationship IDs resolved at request time |
| Vector corpus | Canonical tickets, journals, tasks, and knowledge documents |
| Chroma collection | Rebuildable vector index of the canonical corpus |

No Dashboard, Stats, or Chat component should own an operational ticket, assignee, assignment-group, or metric fixture.

## Ticket Schema

`Ticket` in `backend/app/models.py` represents the shared ServiceNow work-item shape for `INC`, `RITM`, `PRB`, and `CHG`.

### Core fields

| Area | Fields |
| --- | --- |
| Identity | `id`, `sys_id`, `number`, `type`, `record_type` |
| Content | `short_description`, `title`, `description` |
| Workflow | `state`, `priority`, `rca_phase`, `prb_phase`, `cab_status`, `chg_phase`, `risk_level` |
| Ownership | `assignment_group`, `assigned_to` / `assignee`, `caller_id`, `requested_for` |
| Classification | `category`, `business_service`, `sap_modules`, `resources`, `opened_on` |
| SLA | `sla_status`, `sla_time_remaining`, `sla_remaining_minutes`, `sla_health`, `is_breached`, `hold_reason` |
| Intelligence | `sentiment`, `similar_records`, `historical_tickets`, `ai_resolution_guide`, `ai_resolution_steps` |

The Pydantic validator normalizes legacy aliases, fills PoC defaults, maps priority/state aliases, normalizes journals/tasks, derives SLA health, and enforces close-note rules.

### Journals, tasks, and evidence

| Entity | Storage field | Notes |
| --- | --- | --- |
| Customer-visible journal | `comments: list[ServiceNowJournalEntry]` | `sys_journal_field` style author, timestamp, element, value, and `is_customer` |
| Internal journal | `work_notes: list[ServiceNowJournalEntry]` | Internal support activity |
| Attachments | `attachments` | Filename, media type, size, URL |
| Change tasks | `ctasks` | CHG execution work |
| Problem tasks | `ptasks` | PRB investigation work |
| Catalog tasks | `sctasks` | RITM fulfillment work |

Active records and active tasks do not expose closure notes. Closed/resolved records expose them only when valid for their state.

## Relational Schema

Relationships are ID-driven. Snapshot objects are generated only for display.

```text
                        parent_id
            ┌─────────────────────────────────┐
            │                                 ▼
        Parent INC ── child_ids ──> Child INC (full canonical Ticket)
            │
            ├── linked_problem ──> PRB
            │                        ├── originating_ticket_ids ──> INC/RITM records
            │                        ├── ptasks
            │                        └── linked_change ──> CHG
            │                                                  ├── originating_ticket_ids
            └── linked_change ─────────────────────────────────└── ctasks

        RITM ── sctasks
```

### Incident

- `parent_id` identifies a parent incident.
- `child_ids` identifies canonical child incidents.
- `linked_problem` and `linked_change` identify linked PRB/CHG records.
- `resolve_child_tickets()` retrieves each child from its full canonical record. Parent and standalone child views therefore share the same comments and state.

### Problem

- `originating_ticket_ids` identifies one or more contributing INC/RITM records.
- `ptasks` represent downstream investigation/remediation work.
- `linked_change` identifies an implementation change when present.

### Change

- `originating_ticket_ids` identifies the requesting INC/PRB work.
- `ctasks` are the only downstream execution tasks.
- A CHG never treats child incidents as downstream tasks.

`_enrich_relationship_topology()` validates these type-specific relationship rules at model initialization. `_relationship_snapshot()` creates compact topology nodes, not independently stored ticket copies.

## Backend Data Flow

```text
Canonical Ticket Repository ─────┬──> /api/dashboard/tickets ──> Dashboard
                                 ├──> /api/dashboard/stats ────> Stats
                                 ├──> /api/tickets/{reference} ─> Drawer / topology
                                 └──> RAG hydration + agents ───> /api/chat/query ─> Chat

Canonical Knowledge Registry ────> Connector adapters ─────────> Vector corpus ──> RAG retrieval
```

### Dashboard

The Dashboard fetches `/api/dashboard/tickets` and `/api/dashboard/assignment-groups`.

- Groups, review-team defaults, and assignees come from backend repository data.
- Ticket filters, ordering, drawer hydration, anomaly popups, and assignee briefings consume API data.
- Full drawer records are retrieved via `/api/tickets/{ticket_id}` when required.

### Stats

`/api/dashboard/stats` applies assignment-group, assignee, and date filters before calculating all KPIs and chart datasets:

- State, type, SLA, on-hold-reason, team, and assignee counts
- Work-item trends and SLA ownership
- Team status-call summaries
- Anomaly detection and advisory analyses
- A compact API-generated `ticket_index` for chart drill-down

The browser does not calculate alternative KPI totals. Chart clicks hand API-provided IDs to Dashboard drill-down.

### Chat

`POST /api/chat/query` calls `query_hybrid_rag()`.

1. Intent routing recognizes ticket IDs, assignees, assignment groups, operational ticket lists, and known SOP topics.
2. Hybrid retrieval selects canonical vector and lexical evidence.
3. Ticket references are hydrated from the canonical repository immediately before response generation.
4. Gemini is used when configured; otherwise bounded local generation and deterministic grounded synthesis preserve availability.
5. Chat returns clean text only; it does not embed the ticket drawer, journals, topology, or source-card UI.

Assignee and assignment-group questions are answered directly from the live canonical ticket fields, so a small local model cannot omit or invent workload details.

## Vector RAG Architecture

`backend/app/vector_store.py` produces a `RetrievalDocument` for each:

- Knowledge document
- Ticket overview, including assignment, caller, service, SLA, relationships, and configuration context
- Ticket journal stream
- Ticket task stream

Each chunk carries source system/connector metadata plus `ticket_id`, `ticket_number`, `assignment_group`, `module`, `record_type`, and `section` where relevant.

`LocalVectorStore` persists a Chroma collection at `backend/.atlas-vector-db` by default. Its corpus fingerprint uses document ID, content, and URL. On canonical content change, ATLAS re-syncs the collection, preventing stale chunks.

| Condition | Embedding / retrieval behavior |
| --- | --- |
| `GEMINI_API_KEY` configured | Gemini embeddings |
| No Gemini key | Deterministic 256-dimension local hash embeddings |
| Chroma unavailable | In-process vector-map fallback |

The vector store is derived and rebuildable. It is never the authority for ticket state or source documents.

## Connector Architecture

`backend/app/connectors.py` defines a read-only connector contract. Current adapters read canonical mock records for:

- ServiceNow ITSM
- Veeva Vault QMS
- HP ALM Quality Center
- Google Drive KT Hub

Future integrations are prepared through environment-variable placeholders:

- `SERVICENOW_INSTANCE_URL`, `SERVICENOW_CLIENT_ID`, `SERVICENOW_CLIENT_SECRET`
- `VEEVA_VAULT_URL`, `VEEVA_CLIENT_ID`, `VEEVA_CLIENT_SECRET`
- `HP_ALM_BASE_URL`, `HP_ALM_CLIENT_ID`, `HP_ALM_CLIENT_SECRET`
- `GOOGLE_DRIVE_FOLDER_ID`, `GOOGLE_APPLICATION_CREDENTIALS`
- `GEMINI_API_KEY`

No connector writes tickets, documents, approvals, tasks, or changes.

## Constraints

1. Canonical ticket data is currently in process memory and is reloaded from Python definitions on restart.
2. Canonical knowledge is currently source-controlled Python data, not a live document-management integration.
3. Chroma contains only derived vectors and metadata.
4. Gemini and the local model are optional; deterministic responses must remain operational without either.
5. API and connector behavior is read-only for this PoC.
6. Compatibility aliases may remain during migration, but new work must use the canonical ServiceNow-style fields.
7. New UI code must not introduce independent operational fixtures or embedded child-journal copies.

## Production Transition Plan

1. Replace `MOCK_DB` registration with a read-only ServiceNow repository adapter or a replicated relational store.
2. Persist normalized tickets, journals, tasks, relationships, attachments, and knowledge sources in a managed database.
3. Add connector sync jobs with source timestamps, source IDs, idempotency keys, and audit history.
4. Preserve `CentralTicketRepository` as the consumer interface so APIs, stats, topology, and RAG do not require broad rewrites.
5. Keep vector chunks derived from normalized data; version and refresh them by source revision.
6. Store connector credentials in an approved secret manager, enforce least privilege, and apply user/team authorization at repository-query time.
7. Monitor connector freshness, vector-index freshness, retrieval quality, latency, and fallback usage.

## Implementation Steps for Future Data Changes

1. Modify tickets only in the canonical ticket authoring source, then register/rebuild the repository.
2. Modify documents only in the canonical knowledge source or its future sync adapter.
3. Express relationships through `parent_id`, `child_ids`, `originating_ticket_ids`, `linked_problem`, and `linked_change`.
4. Verify Dashboard and Stats through backend API outputs before adjusting presentation code.
5. Rebuild the vector corpus and test ticket, assignee, group, SOP, and no-match chat queries.
6. Do not add browser fixtures or duplicate relationship data.

## Success Criteria

- The same ticket state, journals, assignee, SLA, and relationships appear in Dashboard, Stats drill-down, drawer, and Chat.
- Parent incident child views show the same journal as the standalone child record.
- Stats counts equal their corresponding filtered canonical ticket set.
- Assignee and assignment-group Chat questions resolve from canonical ticket data.
- SOP/KBA queries retrieve the correct central knowledge source.
- The vector store can be rebuilt entirely from canonical ticket and knowledge records.
- No consumer component or AI layer becomes a second system of record.
