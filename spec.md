# Roche ATLAS ITSM Co-Pilot — Current Architecture Specification

## Objective

Provide an executive-grade ITSM co-pilot for ServiceNow-style operations. The
application combines a ticket dashboard, service-health analytics, interactive
ticket inspection, and grounded conversational assistance over a single
canonical enterprise data model.

The current delivery is a local, mock-backed reference implementation. It is
designed to connect to Gemini, ServiceNow, Veeva Vault, HP ALM, and Google
Drive when approved credentials and production connector adapters are supplied.
It is not yet a live integration or a production deployment.

## Requirements

### Product capabilities

1. Provide three persistent React views:
   - **Stats**: executive KPIs, interactive operational charts, team and
     assignee capacity metrics, and chart-to-ticket drill-down.
   - **Dashboard**: filtered ServiceNow work queue and a full ticket inspector.
   - **Chat**: vector-grounded ITSM co-pilot with citations, ticket context,
     CR generation, and RCA generation.
2. Support INC, RITM, PRB, and CHG records, with ServiceNow-style fields and
   type-specific content:
   - INC/RITM: SLA, requester/customer journals, sentiment, child incidents.
   - PRB: RCA state, linked incidents, PTasks, and linked changes.
   - CHG: CAB/change state, originating work, and CTasks.
3. Use one canonical ticket catalog for every product surface. Dashboard rows,
   Stats metrics, Chat ticket context, ticket topology, and RAG retrieval must
   never maintain independent copies of ticket information.
4. Derive all "Awaiting …" metrics strictly from `state == "On Hold"` and the
   ServiceNow-style `hold_reason` field. Supported reasons include Awaiting
   Caller, Change, Child, Vendor, Problem, and Parent.
5. Make Stats visuals interactive: clicking a KPI, chart segment, trend period,
   group row, or assignee row opens exactly the matching canonical tickets in
   Dashboard. Dashboard must offer return-to-Stats navigation.
6. Detect unusual incident patterns from the selected canonical reporting
   scope. The detector must compare recent incident volume with the preceding
   trend and identify explainable assignment-group, category, business-service,
   and P1/P2 concentration changes. Stats must render the findings as an
   interactive chart with ticket drill-down.
7. Show assignment-group anomaly briefings only when the backend reports an
   actual abnormal pattern. Healthy assignment-group selections must not
   interrupt the user with an empty modal.
8. When an assignee is selected, prioritize their queue in this order:
   breached or at-risk customer work, stale Problems/pending PTasks, Changes
   with pending CTasks, then regular backlog. Show the assignee briefing only
   when that person has an actionable risk signal.
9. Give every canonical ticket a stored, ticket-specific AI executive
   resolution plan. Plans must be grounded in the record description, current
   state, journal evidence, linked records/tasks, and enterprise knowledge;
   they must not apply a generic SAP-module checklist to unrelated records.

### Data and integration requirements

1. Maintain a canonical in-memory ServiceNow-style ticket repository with
   relational IDs rather than embedded competing ticket copies.
2. Maintain one centralized enterprise knowledge registry covering ServiceNow
   KBAs, Veeva Vault QMS material, HP ALM defects, and Google Drive KT/SUD
   documents.
3. Build vector chunks from both canonical tickets and knowledge records.
   Every vector chunk must retain `ticket_id`, `ticket_number`,
   `assignment_group`, and SAP `module` metadata.
4. Keep connector boundaries read-only by default. Connector status must state
   whether a source is mock-backed, which environment variables are required,
   and whether it is integration-ready.
5. Support Gemini generation and embeddings through environment configuration;
   local development must continue using deterministic fallback retrieval and
   grounded response synthesis when no key is configured.
6. Store `ai_resolution_summary` and source-tagged `ai_resolution_steps` on
   every canonical ticket. Each step contains an action, why it is relevant,
   and its evidence provenance (for example ServiceNow journal, linked PRB or
   CHG, KBA, Veeva SOP, or connector evidence). The existing RAG/chat guide
   must mirror this canonical resolution summary.

## Constraints

- The repository does not contain real ServiceNow, Veeva, HP ALM, Drive, or
  Gemini credentials. Secrets must remain outside Git.
- The local vector backend is Chroma when installed; deterministic in-process
  hash embeddings are an intentional offline fallback, not a production
  semantic-embedding replacement.
- Current external connectors expose production-compatible contracts but read
  canonical mock data. Live OAuth/token flows, source polling/webhooks,
  credential rotation, and write operations are out of scope until authorized.
- The application is static React assets served by FastAPI. It has no current
  SSO, RBAC, audit persistence, relational database, background job worker,
  rate limiting, or cloud deployment configuration.
- Preserve unrelated local/untracked files and do not commit generated vector
  databases, credentials, or development caches.
- The anomaly detector and per-ticket resolution plans are deterministic,
  explainable decision support in the reference implementation. They are not a
  trained predictive model, autonomous remediation system, or a substitute for
  approved operational change control.

## Architecture

```text
                                    React + Vite + Tailwind
                                App.jsx owns persistent tab state
                                                |
                                                | /api
                +-------------------------------+------------------------------+
                |                               |                              |
                v                               v                              v
          Stats.jsx                       Dashboard.jsx                    Chat.jsx
    KPIs, anomaly chart              Queue, warnings, drawer       Citations and actions
                |                               |                              |
                +--------------------- canonical ticket IDs ------------------+
                                                |
                                                v
                                  FastAPI (backend/app/main.py)
                              APIs, aggregation, chat, SPA static mount
                                      |                         |
                                      v                         v
                    Canonical ticket and knowledge stores     Hybrid RAG
                         models.py + central_db.py       rag_engine.py + vector_store.py
                                      |                         |
                                      v                         v
                          ServiceNow-style MOCK_DB       Chroma/local vector fallback
                              and knowledge registry      Gemini embeddings/generation
                                      |                         |
                                      +------------ connector contracts --------+
                                                    connectors.py
                               ServiceNow | Veeva Vault | HP ALM | Google Drive
```

### Frontend

- **`App.jsx`** owns tab state, selected theme, and the Stats-to-Dashboard
  drill-down payload. Dashboard and Chat remain mounted while hidden so Chat
  history persists.
- **`Stats.jsx`** retrieves backend-calculated metrics and renders KPI cards,
  donut charts, pipelines, team SLA health, workload/capacity tables, and a
  curved trend chart. It also renders the explainable incident-anomaly chart.
  It sends matching ticket IDs to App when the user clicks a chart element.
- **`Dashboard.jsx`** retrieves the canonical queue and assignment-group list,
  provides multi-select group/assignee filters, and renders a ticket drawer.
  It invokes the Stats API for assignment-group anomaly checks and shows an
  anomaly modal only when insights are present. Assignee selection applies the
  operational urgency ranking and shows an assignee briefing only for an
  actionable workload. When launched from Stats it applies the supplied
  canonical ticket IDs and provides a return control.
- **`TicketCard.jsx`**, **`TopologyTree.jsx`**, and
  **`WorkItemActivities.jsx`** render ServiceNow journal, topology, task,
  attachment, SLA, similarity, and knowledge-reference details consistently in
  Dashboard and Chat. `TicketCard.jsx` renders the source-tagged, scrollable
  AI Executive Resolution Plan rather than a generic module checklist.
- **`Chat.jsx`** calls the chat API, shows vector-grounded/fallback state, and
  renders cited source cards and selected ticket context.

### Backend and canonical data

- **`models.py`** contains the Pydantic `Ticket` schema, journal entry schema,
  ServiceNow-like state fields, SLA calculations, `hold_reason`, relationship
  IDs, and the dense SAP enterprise `MOCK_DB` catalog. It also defines
  `TICKET_RESOLUTION_PLANS`: one source-tagged technical resolution plan for
  each canonical ticket.
- **`central_db.py`** owns the canonical ticket repository and canonical
  multi-source knowledge registry. It returns references to the same ticket
  objects rather than copying ticket data for separate consumers.
- **`main.py`** serializes canonical tickets, derives customer sentiment and
  breach classification, hydrates relationship topology, aggregates Stats, and
  handles API/static-SPA routing.
- Dashboard and Stats share a canonical reporting window and the same
  `is_sla_breached()` rule. This prevents the same record from being counted
  differently between views.
- **`main.detect_incident_anomalies(tickets, report_start, report_end)`**
  compares the recent 30-day period with the preceding reporting window and
  returns only evidence-backed anomaly insights. Each insight exposes affected
  ticket IDs, expected versus observed volume, explanation, confidence, and a
  recommended action.
- **`main.build_ticket_ai_insight(ticket)`** serializes the canonical stored
  resolution summary and steps into the ticket API response. Its generic SAP
  technical logic is a fallback only; all mock tickets use their explicit
  `ai_resolution_steps`.

### Vector RAG and Gemini

1. FastAPI startup runs `initialize_vector_db()`.
2. `rag_engine.build_retrieval_documents()` creates chunks for connector
   articles plus each ticket's overview, journal, and task evidence.
3. `vector_store.LocalVectorStore` fingerprints and synchronizes this corpus to
   a persistent Chroma collection when Chroma is installed.
4. `GeminiEmbeddingProvider` uses Gemini embeddings if `GEMINI_API_KEY` is
   available; otherwise it uses stable local hashed vectors.
5. Chat performs direct ticket-ID extraction plus vector/lexical retrieval.
   Retrieved ticket IDs are rehydrated from the canonical repository immediately
   before response generation, preventing stale RAG status or journal content.
6. Gemini is invoked only when configured. Otherwise, a deterministic grounded
   answer or explicit ITIL diagnostic fallback is returned. Sources are always
   returned as structured citation objects.
7. The ticket overview retrieval chunk includes the same canonical resolution
   summary used by the drawer. Retrieval therefore cannot cite an out-of-date
   generic resolution guide for a ticket whose drawer shows a different plan.

### External connector readiness

`backend/.env.example` defines the required placeholders:

| System | Required configuration |
| --- | --- |
| Gemini | `GEMINI_API_KEY`, optional generation/embedding model names |
| ServiceNow | instance URL, OAuth client ID, OAuth client secret |
| Veeva Vault | Vault URL, OAuth client ID, OAuth client secret |
| HP ALM | base URL, OAuth client ID, OAuth client secret |
| Google Drive | folder ID, service-account credentials path |

`GET /api/rag/status` exposes vector backend mode, embedding mode, Gemini
configuration state, and per-connector missing environment variables without
exposing secret values.

## API surface

| Endpoint | Purpose |
| --- | --- |
| `GET /api/dashboard/tickets` | Canonical ticket queue, optionally filtered by assignee/group |
| `GET /api/dashboard/assignment-groups` | Enterprise assignment-group catalog |
| `GET /api/dashboard/stats` and `GET /api/stats` | Live canonical analytics with group, assignee, and date filters |
| `GET /api/tickets/{id}` | Full ticket hydrated by number, ID, or `sys_id` |
| `POST /api/chat/query` and `POST /api/chat` | RAG-backed chat and CR/RCA actions |
| `GET /api/knowledge/sources` | Centralized knowledge-source registry |
| `GET /api/rag/status` | RAG/vector/Gemini/connector readiness diagnostics |

## Implemented feature inventory

### ServiceNow work management

- Native-style INC, RITM, PRB, and CHG schemas with number, `sys_id`, state,
  priority, assignment group, assignee, requester, SLA fields, hold reason,
  journals, closure rules, attachments, and SAP module/service classification.
- Relational topology with parent/child incidents, linked Problems and Changes,
  originating tickets, CTasks, PTasks, and SCTasks. Child views hydrate their
  full canonical record rather than displaying copied comment fixtures.
- Human-only customer/support journal rendering, customer sentiment scoring,
  reverse-chronological streams, pinned evidence, similarity/duplicate
  warnings, historical-context cards, and type-appropriate task activity.
- Warning-only assignee triage, breach reasons, SLA overdue display, and
  operational urgency ordering.

### Executive operations analytics

- Group/date filtered KPIs, SLA health, work-state and dependency distributions,
  record-type pipeline, team workload, team SLA ownership, capacity matrix,
  team-status call summary, and curved multi-group trend chart.
- Cursor-following chart tooltips and drill-down from visual metrics into the
  exact canonical Dashboard queue.
- Explainable anomaly detection for unusual incident patterns. Insights include
  observed versus expected count, confidence, evidence, correlated tickets,
  and a recommended intervention; modals open only when an anomaly exists.

### AI and RAG

- Persistent local Chroma vector store when available, with deterministic local
  vector fallback for offline development.
- Gemini embedding and generation adapters, activated only when
  `GEMINI_API_KEY` is supplied; deterministic grounded answer and ITIL fallback
  behavior otherwise.
- Hybrid ticket-ID, lexical, and semantic retrieval across ServiceNow-style
  tickets/journals/tasks plus ServiceNow KBA, Veeva Vault, HP ALM, and Google
  Drive source records.
- Structured source citations, source-specific citation cards, conversational
  ticket context, active-ticket listing by SAP domain, CR/RCA actions, and
  per-ticket source-tagged technical resolution plans.

### Experience and presentation

- Persistent Stats, Dashboard, and Chat tabs; Chat remains mounted while
  hidden, preserving chat history.
- Light and dark themes, responsive layout, executive dashboard presentation,
  interactive inspector drawer, and consistent topology/task rendering across
  Dashboard and Chat.

## AI capability assessment

ATLAS is accurately described as an **AI-enabled ITSM co-pilot prototype**,
not yet as a fully production-grade autonomous AI platform.

- It has real AI/RAG integration points: Gemini generation and embeddings,
  vector retrieval, grounding, citation objects, and contextual response
  synthesis are implemented in the codebase.
- Without a configured Gemini key, this environment uses deterministic local
  hash embeddings and rule/knowledge-grounded response logic. That remains
  useful decision support, but it is not live generative-model inference.
- The anomaly detector and stored executive resolution plans are explainable
  data-driven/rule-based intelligence. They are deliberately deterministic so
  leaders can inspect their evidence. They are not model-trained forecasting
  or autonomous incident remediation.
- The connector interfaces and environment placeholders are ready for
  integration, but current source data is canonical mock data. No live
  ServiceNow, Veeva, HP ALM, Drive, SSO, RBAC, write-back, or production
  governance is active.

In short: the product has the architecture and interaction pattern of a modern
AI co-pilot, plus a functional local vector RAG path. It becomes a genuine
enterprise generative-AI system only after Gemini is configured and approved
live connector, identity, data-governance, and production-operational controls
are implemented.

## Key runtime contracts

| Component / function | Inputs | Output / responsibility |
| --- | --- | --- |
| `ticket_payload(ticket)` | Canonical `Ticket` | API-safe ticket plus SLA, sentiment, breach, topology, and AI resolution insight fields. |
| `get_dashboard_stats(groups, filter_active, assignees, start, end)` | Canonical filter criteria | All KPIs, chart datasets, ticket drill-down index, and anomaly detection results. |
| `detect_incident_anomalies(tickets, start, end)` | Filtered canonical tickets and reporting window | Evidence-backed abnormal incident trends with exact impacted ticket IDs. |
| `build_ticket_ai_insight(ticket)` | Canonical ticket | Stored summary and source-tagged resolution steps; generic fallback only if a plan is absent. |
| `build_retrieval_documents()` | Canonical ticket/knowledge stores | Metadata-preserving vector chunks for knowledge, overview, journals, and tasks. |
| `retrieve_vector_context(query, limit)` | User question and result limit | Hybrid exact-ticket, lexical, and semantic retrieval candidates with citations. |

Example operational flow: selecting **SAP PLM Support** in Dashboard calls
`GET /api/dashboard/stats` with that group, receives any anomaly insights, and
opens the anomaly warning only when `insights.length > 0`. Opening a PLM ticket
then uses `GET /api/tickets/{number}`; its drawer resolution plan comes from
the same canonical `Ticket.ai_resolution_steps` that feeds the RAG overview.

## Implementation steps for the next production phase

1. Replace canonical mock connector implementations with approved, read-only
   ServiceNow, Veeva Vault, HP ALM, and Drive adapters using the documented
   environment configuration.
2. Move all secrets to the approved secret manager and inject them at runtime;
   never load production credentials from committed `.env` files.
3. Replace local Chroma persistence with an approved managed vector store, or
   provision a persistent Chroma volume with encryption, backup, access
   controls, and index lifecycle management.
4. Replace `MOCK_DB` with a persistent system-of-record integration or database
   layer and add sync/refresh, retry, audit, and conflict-handling behavior.
5. Add application authentication, RBAC, tenancy/data-boundary enforcement,
   observability, request rate limits, tests, CI/CD, security review, and an
   approved deployment target.
6. Validate Gemini model choice, regional data controls, retention policy,
   prompt logging policy, and connector access with the relevant platform and
   security owners.

## Success criteria

### Current reference implementation

- Dashboard, Stats, and Chat retrieve the same canonical ticket state.
- All Stats KPIs and chart drill-downs map to exact canonical ticket IDs.
- On-hold dependency metrics are calculated only from valid On Hold records and
  `hold_reason`.
- RAG retrieves and cites ticket plus knowledge evidence with metadata back to
  its canonical ticket, assignment group, and module.
- Every canonical ticket has a source-tagged technical resolution plan and the
  drawer displays that plan without substituting unrelated module-wide steps.
- Anomaly and assignee pop-ups appear only for actionable backend-derived risk
  signals; a healthy filtered scope never produces an empty warning modal.
- The app starts and operates without external credentials, while honestly
  reporting fallback mode and connector readiness.
- `npm run lint`, `npm run build`, backend API smoke tests, and
  `GET /api/rag/status` pass.

### Production readiness gate

- Approved live connector implementations and secrets are configured.
- A persistent, access-controlled ticket and vector data store is deployed.
- Authentication, RBAC, audit, monitoring, backup, resiliency, test coverage,
  and CI/CD controls are approved.
- Gemini and all external integrations are validated under the enterprise's
  security, compliance, and data-governance requirements.

## Business architecture and commercial product narrative

### Product definition

**Roche ATLAS ITSM Co-Pilot** is an AI-enabled ITSM operations cockpit for
enterprise support leaders, assignment-group leads, and L2/L3 engineers. It
combines ServiceNow-style work management, explainable operational analytics,
ticket-level investigation, and grounded knowledge retrieval in one workspace.

The current application is a polished, locally runnable **reference PoC**. It
is credible for demonstrations, solution design, pilot discovery, and
integration planning. It is not yet a production SaaS product because the
canonical records are mock data and live connectors, identity, governance, and
operational controls have not been deployed.

### Business problem addressed

Enterprise support teams commonly need to move between ServiceNow queues,
spreadsheets, knowledge portals, problem/change records, monitoring alerts,
and engineer conversations before they can answer four basic questions:

1. What needs attention now?
2. Which team or engineer is carrying risk?
3. Are apparently separate tickets part of one underlying issue?
4. What is the safest, evidence-backed next resolution action?

ATLAS turns those questions into a common operational workflow. It does not
replace ServiceNow as the system of record. It acts as a read-only intelligence
and decision-support layer over ITSM records and connected enterprise knowledge.

### Personas and outcomes

| Persona | Primary need | ATLAS outcome |
| --- | --- | --- |
| Executive / service owner | Rapid visibility of operational risk | KPI ribbon, SLA health, workload, anomalies, trends, and ticket drill-down. |
| Tower or assignment-group lead | Manage a multi-team queue and intervene early | Group filters, anomaly findings, team call summary, breach distribution, and linked record context. |
| L2/L3 engineer | Diagnose and resolve the correct issue quickly | Ticket briefing, human journal, topology, tasks, historical similarity, knowledge citations, and ticket-specific resolution steps. |
| Incident manager | Coordinate escalation and identify recurring causes | Related incidents, linked Problems/Changes, duplicate signals, breach reasons, and suggested advisory actions. |
| Knowledge / quality owner | Make approved operating procedures discoverable | Grounded RAG citations across ServiceNow, Veeva Vault, HP ALM, and Google Drive knowledge. |

### Commercial capability map

| Capability domain | Current PoC capability | Customer value | Production expansion |
| --- | --- | --- | --- |
| ITSM operational cockpit | Dashboard, Stats, and Chat tabs backed by one canonical catalog | One view of operational health and work queues | Live ServiceNow read model, tenant separation, real-time refresh. |
| Executive analytics | KPIs, distributions, group workload, assignee capacity, trend charts, chart-to-ticket drill-down | Faster service reviews and accountable action | Historical warehouse, configurable reporting periods, export/scheduling. |
| AI operations analyst | Deterministic anomaly, group, assignee, and ticket analyses | Explainable risk and prioritisation without black-box claims | Governed model-assisted reasoning and validated predictive signals. |
| Ticket investigation | Drawers with SLA, sentiment, journal, topology, tasks, attachments, similarities, and resolution plans | Less context switching and faster triage | Live journal/task relationships, update timestamps, CI/service graph. |
| Knowledge intelligence | Hybrid RAG with vector and lexical retrieval plus citations | Grounded answers instead of untraceable chatbot text | Approved embeddings/LLM, source ingestion, permissions-aware retrieval. |
| Enterprise integrations | Connector contracts and environment placeholders | Clear path to ServiceNow, Veeva, HP ALM, Drive, and Gemini | OAuth/service accounts, secret manager, sync scheduler, observability. |

## Detailed logical architecture

### Architectural principles

1. **One canonical ticket catalog.** All application views derive ticket state
   from `MOCK_DB` through the central repository abstraction. The Dashboard,
   Stats service, API details, and RAG chunks do not maintain separate ticket
   copies.
2. **Read-only intelligence.** Analytics, retrieval, and AI agent functions
   observe records and make recommendations; they do not create, update, close,
   reassign, or write back ServiceNow records.
3. **Evidence before recommendation.** AI outputs include concrete ticket IDs,
   source references, state/SLA/task signals, and a confidence level where a
   meaningful pattern exists. The system is designed to return no finding rather
   than invent a correlation.
4. **Graceful offline operation.** The local PoC uses deterministic analysis
   and retrieval when external model credentials are not present. Gemini is an
   optional enhancement, not a dependency for core application availability.
5. **Separation of concerns.** The presentation layer is React, orchestration
   is FastAPI, business objects are canonical models, retrieval is isolated in
   the vector/RAG modules, and integrations are expressed as future connector
   boundaries.

### Layered component model

```text
┌───────────────────────────────────────────────────────────────────────────┐
│ Experience layer: React + Vite + Tailwind                                 │
│                                                                           │
│  Stats ─ executive analytics, filters, charts, drill-down                │
│  Dashboard ─ queue, group/assignee controls, drawer, warnings            │
│  Chat ─ conversational investigation, citations, ticket cards            │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │ HTTPS / JSON
┌───────────────────────────────▼───────────────────────────────────────────┐
│ API and orchestration layer: FastAPI (`backend/app/main.py`)              │
│                                                                           │
│  dashboard listing │ ticket hydration │ stats aggregation │ chat routing  │
│  filter parsing    │ SLA/sentiment     │ anomaly delivery   │ static SPA   │
└───────┬─────────────────────┬─────────────────────┬────────────────────────┘
        │                     │                     │
┌───────▼─────────────┐ ┌─────▼────────────────┐ ┌─▼────────────────────────┐
│ Canonical data      │ │ Intelligence layer   │ │ Retrieval / RAG layer     │
│ `models.py`         │ │ `agent_intelligence` │ │ `rag_engine.py`           │
│ `central_db.py`     │ │ existing anomaly     │ │ `vector_store.py`         │
│                     │ │ detector + agents    │ │ hybrid vector + keyword   │
│ Tickets, topology,  │ │                      │ │ retrieval, citations      │
│ journals, tasks,    │ │ Group/assignee/      │ │                           │
│ knowledge refs,     │ │ ticket investigation │ │ Chroma or hash fallback   │
│ plans and metadata  │ │ (runtime only)       │ │                           │
└───────┬─────────────┘ └────────────────────────┘ └───────────┬─────────────┘
        │                                                       │
┌───────▼───────────────────────────────────────────────────────▼─────────────┐
│ Integration boundary (contract-ready; mock-backed in this PoC)              │
│ ServiceNow ITSM │ Veeva Vault QMS │ HP ALM / Quality Center │ Google Drive  │
│ Gemini / approved generative model                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Canonical data model and lineage

The current canonical repository represents ServiceNow-native work records and
their operational context. The data model deliberately uses identifiers and
relationships that map to future live ServiceNow responses.

| Data class | Examples of core fields | Used by |
| --- | --- | --- |
| Ticket identity | `sys_id`, `number`, `type`, `short_description`, `description`, `state`, `priority` | Every API, UI view, vector metadata, and agent. |
| Accountability | `assignment_group`, `assigned_to` / assignee, caller/requested-for context | Dashboard filtering, group/assignee workload, sentiment analysis. |
| SLA / operational state | `sla_status`, `sla_remaining_minutes`, `is_breached`, `hold_reason`, risk indicators | KPI aggregation, urgency sorting, breach classifier, executive views. |
| Human journals | ServiceNow-style comment objects with author, timestamp, message, customer flag/role | Drawer journal, customer sentiment, Chat context, evidence. |
| Relationships | `parent_id`, `child_ids`, linked Problem/Change, originating records | Topology tree, full-record hydration, correlation analysis. |
| Work tasks | `ctasks`, `ptasks`, `sctasks`, state and latest comment/closure data | Change/Problem execution tracking and AI recommendations. |
| Business context | SAP module tags, service, CI, category, assignment group | Group analytics, RAG metadata, anomaly/correlation reasoning. |
| Knowledge & resolution | `knowledge_refs`, historical/similar records, source-tagged resolution plans | Ticket summary, cited chat responses, recommended next actions. |

The parent-child display is dynamically resolved from canonical IDs rather than
from independently edited embedded copies. That principle prevents the earlier
class of inconsistency where a child ticket displayed one journal in a parent
drawer and a different journal when opened independently.

### Data lifecycle in the current PoC

1. `models.py` defines canonical tickets, cross-record relationships, knowledge
   metadata, and resolution-plan source material.
2. `central_db.py` exposes that catalog to all backend consumers.
3. `main.py` calculates filtered dashboard and stats views directly from the
   canonical source at request time.
4. `vector_store.py` creates searchable chunks from canonical tickets and the
   enterprise knowledge corpus; each chunk retains ticket/group/module
   metadata.
5. `rag_engine.py` retrieves relevant chunks and asks a configured model to
   synthesise an answer, or returns a deterministic grounded response locally.
6. `agent_intelligence.py` reads the same ticket set, existing anomaly signals,
   relationships, and retrieval evidence to form runtime-only findings.
7. The frontend displays the resulting state in existing UI components. It does
   not manufacture an independent analytics dataset.

## Functional feature inventory

### 1. Dashboard and work-queue management

- ServiceNow-style multi-record queue covering INC, RITM, PRB, and CHG records.
- Ticket-type tabs with context-aware fields: SLA and sentiment for customer
  work, versus Problem/Change phase and task status for operational records.
- Searchable assignment-group multi-select with Select All, Deselect All, and
  My Teams behaviour.
- Multi-select assignee filter with Select All and Deselect All behaviour.
- Filtered queue ordering that promotes breached/near-breach, high-sentiment,
  stale Problems, and Changes with open CTasks ahead of regular backlog.
- Accurate on-hold dependency categories based on ServiceNow-style
  `hold_reason`: Awaiting Caller, Child, Change, Problem, Parent, and Vendor.
- SLA badge treatment for overdue tickets with negative remaining minutes,
  breach reason classification, and visible urgency.
- Ticket attachments pinned above journal content when available.

### 2. Ticket drawer and investigation workspace

- A consistent drawer hierarchy for every ticket, with a concise AI executive
  resolution plan, relational topology, evidence/attachments, human journal,
  child ticket context where appropriate, and knowledge grounding.
- Record-type-specific topology:
  - Incident: parent/current/child incidents plus linked Problem and Change.
  - Problem: originating incidents, PTasks, and linked fix Change.
  - Change: originating tickets and CTasks only.
- Deep-node navigation: clicking a topology item hydrates the full canonical
  record through the ticket API rather than rendering a shallow cached object.
- Child ticket journals are pulled from the actual child ticket record, filtered
  to human messages, and constrained by an internal scroll container.
- Human customer/support journal with newest-first ordering, author/role,
  timestamp, and customer sentiment where relevant.
- Similarity/duplicate and historical-context panels when canonical evidence
  identifies a related active or resolved record.
- Change/Problem task cards that show the correct task state and only disclose
  closure notes for closed tasks.

### 3. Stats and executive cockpit

- KPI ribbon for total scoped records, SLA breaches, in-progress, on-hold, and
  ServiceNow hold-reason dependencies.
- Interactive distributions for record type, SLA health, workload, status,
  module, and assignment group.
- Four-month incident trend per selected assignment group, using backend data.
- SLA breach/at-risk breakdown by assignment group for tower-lead
  accountability.
- Assignee workload/capacity matrix including active tickets and individual
  breach count.
- Team status call summary exposing backlog age, resolution velocity, and breach
  rate by group.
- Hover tooltips and chart-to-ticket drill-down so a business metric remains
  traceable to the underlying records.
- A Stats-to-Dashboard path with a back action, rather than a dead-end chart.

### 4. Anomaly and workload intelligence

- Existing deterministic anomaly detection evaluates filtered incident volume,
  priority concentration, service/category concentration, and abnormal trends.
- Assignment-group analysis enriches actual anomaly results with repeated
  services, duplicate/similarity signals, related Problems/Changes, evidence,
  confidence, and advisory action.
- Assignment-group warning content appears only when the backend finds a
  material signal; a healthy scope does not show a generic warning dialog.
- Assignee analysis ranks operational workload by breach, near breach, customer
  urgency, priority, stale Problems, pending tasks, and related patterns.
- Assignee briefing appears only when the selected person has an actionable risk
  signal. It never takes automatic remediation action.

### 5. Conversational co-pilot and grounded retrieval

- Natural-language ticket-ID detection, ticket title/description matching, and
  SAP-domain query matching for EWM, MM, PLM, Basis, Security, SD, FICO, and
  related areas.
- Queries such as “show ongoing PLM tickets”, “what is the status of
  INC0048102”, or “how do I investigate an EWM queue lock?” can return matched
  tickets, readable action-oriented content, and relevant citations.
- Hybrid retrieval combines exact ticket matching, keyword/lexical ranking, and
  local vector similarity to reduce dependence on one retrieval method.
- Citations identify the source platform and offer links for ServiceNow KBA,
  Veeva Vault, HP ALM, Google Drive, and model-grounded responses where
  applicable.
- When a model credential is absent, deterministic grounded synthesis still
  uses the retrieved knowledge/ticket context and does not prevent local use.

### 6. AI agent intelligence layer

The latest intelligence layer is deliberately small, isolated, advisory, and
reversible. It does not alter the canonical repository.

| Runtime agent | Trigger | Reused inputs | Output | UI destination |
| --- | --- | --- | --- | --- |
| Assignment-group investigator | A filtered group produces an existing warning condition | Filtered tickets, existing anomaly results, topology, similarity signals | Meaningful findings with evidence, related IDs, confidence, and recommendation | Existing assignment-group briefing/popup. |
| Assignee workload investigator | One assignee has an operational warning condition | Assigned tickets, SLA, sentiment, priority, task and Problem state | Prioritised risk summary, affected tickets/patterns, recommended focus | Existing assignee briefing modal. |
| Ticket investigator | Full ticket is opened or returned from Chat | Canonical ticket, relationships, stored resolution plan, retrieval evidence | What is happening, impact, evidence, related records, likely factor, next steps, confidence | Existing AI Summary / Executive Resolution Plan in drawer and ticket cards. |

Each agent is wrapped in error isolation. If its logic or retrieval fails, the
regular Stats, Dashboard, Chat, ticket hydration, anomaly detector, and RAG
paths continue to work and the agent field returns empty/null.

## Runtime sequence flows

### Executive filtering and drill-down

```text
User selects groups/date/assignees
  → React sends filter parameters to FastAPI
  → FastAPI filters canonical tickets once
  → stats aggregation calculates KPIs, charts, workload, and anomalies
  → optional group/assignee agent reads the same filtered records
  → UI renders metric + hover tooltip + exact ticket drill-down
  → user opens a drill-down ticket
  → ticket API hydrates canonical record and runtime ticket analysis
```

### Assignment-group anomaly flow

```text
Group selected
  → existing anomaly detector searches for material abnormal patterns
  → no material evidence: no warning popup
  → material evidence: group investigator correlates services, duplicates,
    related Changes/Problems, and record IDs
  → existing popup presents finding, evidence, confidence, and recommendation
```

### Assignee prioritisation flow

```text
Assignee selected
  → queue ordering ranks breach/near breach + customer urgency first
  → stale Problems and Changes with pending tasks follow
  → if actual operational risk exists, existing briefing receives agent summary
  → user closes briefing and sees the same prioritised queue underneath
```

### Ticket and Chat investigation flow

```text
Ticket opened or question submitted
  → API resolves ticket number/sys_id against canonical repository
  → RAG retrieves ticket, journal, task, and knowledge chunks with metadata
  → ticket agent joins canonical relationships and retrieved evidence
  → response displays action-oriented explanation plus source citations
  → no model key: deterministic grounded response; model key: Gemini synthesis
```

## API and function reference

### HTTP API

| Endpoint | Primary parameters | Main response content | Typical usage |
| --- | --- | --- | --- |
| `GET /api/dashboard/tickets` | assignment-group, assignee, type/search filters as supported | Filtered canonical ticket summaries | Populate the Dashboard table and quick filtering. |
| `GET /api/tickets/{ticket_id}` | `ticket_id` may be ServiceNow number or `sys_id`, case-insensitive | Fully hydrated canonical ticket, relationships, SLA/sentiment, resolution data, and isolated `agent_analysis` | Open a drawer or topology node. |
| `GET /api/dashboard/stats` | selected groups, assignees, start/end dates, active filters | KPI totals, chart series, drill-down IDs, existing anomalies, optional group/assignee analysis | Render Stats and existing operational popups. |
| `GET /api/dashboard/assignment-groups` | none | Master group list | Populate group selectors. |
| `POST /api/chat` (and compatibility chat route where present) | user message/query | Answer, matched ticket context, source citations, model/fallback metadata | Answer conversational investigations. |
| `GET /api/rag/status` | none | Vector-store, source, and model availability state | Health check / demonstration readiness. |

### Important backend functions

| Function | Inputs | Returns | Notes |
| --- | --- | --- | --- |
| `ticket_payload(ticket, include_agent_analysis=False)` | Canonical ticket and analysis flag | API-safe ticket payload | Full analysis is opt-in for details; agent failure must not fail hydration. |
| `get_dashboard_stats(groups, filter_active, assignees, start, end)` | Normalised filter criteria | Unified executive metrics/data series | Applies filters before every calculation to keep Dashboard and Stats aligned. |
| `detect_incident_anomalies(tickets, start, end)` | Filtered tickets and reporting period | Evidence-backed abnormal incident findings | Existing detector; it is not replaced by the new agent layer. |
| `analyze_assignment_group_workload(tickets, anomaly_insights)` | Canonical filtered records plus existing detector output | Meaningful group findings only | Read-only enrichment of detector evidence. |
| `analyze_assignee_workload(tickets, assignee, report_end)` | Filtered scope, selected assignee, date | Risk-focused prioritisation | Uses breaches, near breaches, tasks, stale Problems, similarities, and common services. |
| `analyze_ticket(ticket, related_records, retrieval)` | Canonical ticket, relationships, retrieval snippets | Ticket-specific explanation and recommendations | Uses evidence rather than a generic module checklist. |
| `build_retrieval_documents()` | Canonical ticket and knowledge repositories | Vector-indexable chunks with metadata | Preserves `ticket_id`, group, module, source, and URL/path lineage. |
| `retrieve_vector_context(query, limit)` | Query text and result limit | Ranked hybrid evidence and citations | Supports deterministic local retrieval when an external embedding/model is unavailable. |

### Example customer demonstration prompts

| Prompt | Expected ATLAS behaviour |
| --- | --- |
| “What is happening with INC0048102?” | Hydrate the ticket, explain plain-English impact, show current journal/topology, evidence, next actions, and citations. |
| “Show ongoing Basis tickets.” | Find active Basis-tagged records, return a readable list and relevant grouped context. |
| “How do I fix an EWM qRFC queue lock?” | Retrieve EWM procedures and provide stepwise guidance with KBA/SOP citations. |
| “Which SAP PLM tickets are at risk?” | Retrieve or filter PLM records with SLA/priority/sentiment context; do not invent risk where data is absent. |
| “What should Nina Keller work on first?” | Use assignee workload rules to rank actual risk and explain the rationale. |

## Explainability, guardrails, and trust model

### What every AI-derived finding should expose

- **Finding:** the operational pattern or ticket assessment.
- **Evidence:** the exact operational signals used, such as SLA state, journal
  urgency, age, task state, volume trend, or repeated service/category.
- **Traceability:** related ticket, Change, and Problem IDs plus cited knowledge
  sources where they exist.
- **Confidence:** a bounded evidence-based confidence, not a claim of certainty.
- **Recommended action:** advisory next step only; never an automatic update.

### Explicit non-goals and safeguards

- No agent writes to ServiceNow, Veeva, HP ALM, Google Drive, or `MOCK_DB`.
- No incident is automatically escalated, reassigned, linked, closed, or used to
  create a Change/Problem.
- A similarity indicator is decision support, not a declaration that records
  are duplicates.
- A RAG answer is grounded in retrieved content but should be reviewed by a
  qualified engineer before production action.
- A local deterministic fallback is designed for continuity and demos; it is
  not a substitute for an approved enterprise model, eval framework, or human
  operating procedure.

## Security, compliance, and enterprise readiness

### Current PoC posture

The PoC runs locally with mock enterprise content and optional environment
variables. It contains no required real API keys, no live source integration,
no customer production data, and no write-back action. This makes it suitable
for safe architecture reviews and controlled demos when mock content remains
in use.

### Required controls before customer production use

| Area | Required production control |
| --- | --- |
| Identity and access | Enterprise SSO, RBAC/ABAC, group-aware data entitlements, least-privilege service identities. |
| Secrets | Approved secret manager, rotation, no committed credentials, connector-specific scopes. |
| Data protection | Classification, regional processing approval, encryption in transit/at rest, retention/deletion rules, and PII review. |
| Connector governance | Read-only scopes initially, audit logs, rate limits, retry/backoff, schema contracts, and reconciliation controls. |
| Model governance | Approved Gemini/model endpoint, prompt/data handling approval, safety policy, evaluation set, model/version tracking. |
| RAG governance | Permission-aware document ingestion, source freshness/versioning, citation verification, vector index backup and lifecycle. |
| Operations | Health checks, logs/metrics/traces, alerting, SLOs, DR, vulnerability management, CI/CD gates, and change management. |
| Assurance | Threat model, privacy/security review, accessibility checks, performance/load tests, and human-in-the-loop operating procedures. |

## Target production deployment reference architecture

The following is a target design, not a claim about the current local PoC.

```text
Corporate browser
  → enterprise SSO / access proxy
  → ATLAS web application (static React deployment)
  → ATLAS API service (FastAPI, horizontally scalable)
      ├─ ServiceNow read adapter / webhook or scheduled sync
      ├─ Veeva Vault, HP ALM, Drive read adapters
      ├─ operational ticket/read-model store
      ├─ managed vector database with metadata/security filters
      ├─ approved Gemini endpoint through enterprise AI controls
      ├─ secret manager + central logging/metrics/tracing
      └─ audit/event store and monitoring
```

The recommended rollout sequence is: controlled mock-data demo, read-only
ServiceNow pilot, permission-aware knowledge pilot, approved model deployment,
then broader connectors and governed production operation. Write-back should be
considered only after a separate safety, ownership, and approval design.

## Delivery scope statement

### Implemented in the repository today

- React/Vite/Tailwind single-page experience with persistent Stats, Dashboard,
  and Chat views plus light/dark theming.
- FastAPI routes for tickets, dashboard data, stats, assignment groups, chat,
  and RAG status.
- ServiceNow-inspired canonical mock catalog, topology/task/journal rendering,
  filters, visual analytics, anomaly detection, vector retrieval, citations,
  and deterministic fallback.
- Read-only assignment-group, assignee, and ticket intelligence agents embedded
  in existing UI surfaces.
- Connector and model configuration placeholders for a future enterprise
  integration.

### Deliberately outside the current implementation

- Live ServiceNow, Veeva Vault, HP ALM, Drive, or Gemini credentials/adapters.
- Multi-tenant persistence, SSO/RBAC, audit logging, compliance certification,
  automated data synchronization, background workers, and production hosting.
- Predictive ML training, automated remediation, or write-back actions.

## Expanded success criteria for a sellable pilot

### Demonstration acceptance

- A leader can filter one or more assignment groups and see KPIs, charts, and
  drill-down ticket counts that reconcile with the Dashboard.
- A chart click identifies the exact in-scope canonical ticket set and opens a
  ticket without losing the selected analytical context.
- An anomaly/group/assignee warning is shown only when the record evidence
  satisfies its backend rule; it includes ticket IDs and a reason.
- Opening any topology node shows the same canonical journal, SLA state, and
  relationship information as opening that record directly.
- Chat returns readable, action-oriented, cited answers for ticket-specific and
  knowledge/how-to questions with no external model key required.
- The ticket executive plan is specific to the selected ticket and explains
  evidence, likely contributing factor, recommended actions, and confidence.

### Production pilot acceptance

- Reconciliation tests show the connected read model matches approved
  ServiceNow source records for identity, state, assignment, journal, SLA, and
  relationship fields.
- Security review approves identity, permissions, data boundaries, secrets,
  logging, and model/provider handling.
- Retrieval evaluation demonstrates source-grounding, citation accuracy,
  permission enforcement, freshness, and acceptable failure behaviour.
- Operational tests meet agreed availability, latency, scalability, accessibility,
  and supportability targets.
- Business owners approve agent recommendation quality with a documented human
  review process before any future action automation is considered.

## LEAP SAP EWM knowledge-corpus expansion (approved design)

### Purpose and source-governance decision

The supplied LEAP SAP EWM material will expand the central enterprise knowledge
corpus used by the existing vector RAG pipeline. It will not be copied into
individual tickets, embedded in frontend components, or used to create a second
knowledge repository.

The agreed governance model is **split by document**:

- Controlled operating procedures and compliance-sensitive warehouse processes
  are sourced from **Veeva Vault QMS**.
- Foundational KT material and system-user documentation are sourced from the
  **Google Drive KT Hub**.

This division allows ATLAS to distinguish controlled SOP guidance from useful
operational reference material while presenting both through the existing
grounded-citation experience.

### Canonical knowledge catalog additions

The following records will be added to the existing central knowledge registry.
The IDs, source type, document title, and source path are the only canonical
identity for each document. `path_or_url` values remain integration-safe
placeholders until approved live document URLs are supplied.

| Canonical ID | Source system | Proposed title | Document class | Retrieval role |
| --- | --- | --- | --- | --- |
| `GDRIVE-LEAP-KT-001` | Google Drive KT Hub | LEAP Project: SAP EWM General Overview | KT / solution overview | Explains the overall LEAP landscape, warehouse tiers, roles, HUs, storage, and operating model. |
| `VEEVA-LEAP-EWM-010` | Veeva Vault QMS | EH&S Data Transmission and Monitoring for Hazardous Materials | Controlled SOP | Safety/compliance guidance for EH&S master data, IDoc, hazardous putaway, and monitoring. |
| `VEEVA-LEAP-EWM-011` | Veeva Vault QMS | Material Ordering (Request Hub) and Order Monitoring | Controlled operational procedure | Request Hub ordering, middleware tracing, request lifecycle, and release-job troubleshooting. |
| `VEEVA-LEAP-EWM-012` | Veeva Vault QMS | Disposal of EWM Materials and Retained Samples | Controlled disposal SOP | Expiry/disposal monitoring, scrapping execution, hazardous exception controls, and final GI. |
| `GDRIVE-LEAP-SUD-001` | Google Drive KT Hub | LEAP System User Documentation: Goods Receipt | System user documentation | EWM/non-EWM goods receipt, HU pulling, capacity, hazardous routing, cancellation, and labels. |

### Required canonical metadata

Each record above must use the existing knowledge-document schema and include,
at minimum:

| Field | Requirement |
| --- | --- |
| `id` | The stable canonical ID listed above. |
| `title` | Exact document title from the catalog. |
| `source_type` / `system` | `Veeva Vault QMS` or `Google Drive KT Hub`; never an ambiguous generic source label. |
| `path_or_url` / `url` | Approved source link at implementation time. Until then, a clearly marked non-production placeholder that cannot be mistaken for a live controlled document. |
| `summary` | A concise, factual description of scope and intended support use. |
| `document_class` | `controlled_sop`, `kt_overview`, or `system_user_documentation`. |
| `sap_modules` | At least `SAP EWM`; add connected domains such as EH&S, ERP, MuleSoft, Request Hub, RF, and warehouse operations where relevant. |
| `topics` | Searchable functional and technical terms, including transactions, jobs, monitor paths, storage concepts, and exception names. |
| `version`, `effective_date`, `owner`, `approval_status` | Required future live-integration metadata. Use mock-safe values only until the document owners provide authoritative values. |
| `access_scope` | Required for a production permission-aware retrieval filter; default to mock/demo scope in the PoC. |

### Content coverage to preserve during ingestion

The documents must be represented as section-aware knowledge chunks, not a
single undifferentiated paragraph. The following content is in scope.

#### `GDRIVE-LEAP-KT-001` — LEAP EWM general overview

- LEAP’s laboratory-consolidation objective: logistics is centralised so
  scientists can focus on research, with SAP EWM as the warehouse control
  system.
- System landscape: SAP EWM, Request Hub, MuleSoft, SAP EIP, and the Arrron
  system for the minus-80°C deep-freeze cube.
- Primary, secondary, and tertiary storage model, including EWM ownership,
  temperature zones, hazardous areas, transfer/arrival areas, and the fact that
  tertiary laboratory storage is outside EWM management.
- Handling Unit concept, permitted packaging, barcode/number-range behaviour,
  and automated-conveyor implications.
- External-material HU pulling concept for Signals/Infinity-managed material.
- Hazardous storage/transport restrictions, storage class, flash point,
  compatibility, and the special handling of human samples.
- Roles, resource groups, RF scanner/MOP device context, and the Scullery
  glassware operating process.

#### `VEEVA-LEAP-EWM-010` — EH&S hazardous-data SOP

- The three safety-critical properties: storage class, flash point in Celsius,
  and pH value; include the rule that pH is maintained manually in EWM rather
  than transmitted by IDoc.
- Architecture and lineage: EH&S P08 → ERP → EWM using IDoc message type
  `HAZARDOUSSUBSTANCE`; avoid claiming a direct P08-to-EWM integration.
- Operator procedure: trigger/update via `HSMR02`, maintain pH in `MAT1`
  Warehouse Data Z-fields, and review integrated data in the Warehouse Monitor
  path `Roche Enhancement → Product`.
- Exception and safety content: scrapping compatibility bypass, normal-bin
  safety risk, unit-of-measure checks for flash point, and IDoc diagnostics with
  `WE02`.

#### `VEEVA-LEAP-EWM-011` — Request Hub ordering and monitoring SOP

- Order ID versus Request ID hierarchy, material categories, and the mandatory
  destination-bin rule for CUBE material.
- Integration chain: Request Hub → MuleSoft → DataRiver → EWM OData API.
- Troubleshooting through `/IWFWND/TRACES`, filtered by user `MULELEAP`, when
  an accepted Request Hub order is not visible in EWM.
- Warehouse task creation as initially locked/blocked, and release timing for
  job `DEF_RELEASE_WHO` / program `ZL84_RELEASE_WHO` at 02:00 and 13:00.
- Supporting Z tables `ZL84_REQ_ORDE`, `ZL84_REQ_REQUEST`, and
  `ZL84_REQ_WHT`; monitor path `Roche Enhancement → Request Order → Request`.
- Status lifecycle `O → P → S → C`, forward-only transition rule, cancellation
  restriction after closure, and secondary-level no-task exception.

#### `VEEVA-LEAP-EWM-012` — disposal and retained-sample SOP

- Disposal-date formula based on expiration plus `ZZ1_DISPOSAL_DAYS` in `MAT1`.
- Monitoring path `Roche Enhancements → Stock → Disposal Overview`, monthly
  report `/SCWM/R_WME_MON_NODE_BTC_RUN`, and expected notification behaviour.
- Execution sequence: ERP `MIGO` movement type `551` → EWM scrapping outbound
  delivery → picking WT in queue `PRT0-SCRAP` → follow-up WT to `SCRAP-ZONE` →
  final GI in `/SCWM/PRDO`.
- Special SCRAP queue rule permitting compatible handling of different storage
  classes in one transport HU only within the documented disposal scenario.

#### `GDRIVE-LEAP-SUD-001` — goods-receipt SUD

- EWM-managed, non-EWM, rack-pack, retained-sample, and Signals/Limfinity HU
  pulling behaviours, including open-WT creation in RF when needed.
- Capacity management prerequisites: product master consumption, bin capacity,
  permitted HU types, and their relationship to common GR errors.
- EWM goods-receipt sequence: physical check, deconsolidation, HU/label
  creation, transport HU, conveyor routing, putaway by HU, exception `CHPD`,
  and WT confirmation as the final GR posting point.
- Hazardous destination logic using storage class, flash point, pH, and
  temperature control indicators; include the statement that the minus-80°C
  Cube is not EWM managed.
- Inbound cancellation preconditions, rejection workflow, and product/HU label
  printing locations.

### Retrieval and answer behaviour

The existing hybrid retrieval pipeline must index the documents alongside the
current ServiceNow, HP ALM, Veeva, and Drive knowledge records. Search must
operate across title, summary, topics, section headings, procedure steps,
transaction codes, job/program names, monitor paths, exception names, SAP
module tags, and document body chunks.

The chat response behaviour must remain conversational and action-oriented:

1. Match the user’s question to relevant LEAP sections and, where applicable,
   live/canonical ticket evidence.
2. Answer in concise numbered action steps rather than a raw record dump.
3. State applicability and safety constraints, especially for hazardous
   handling, disposal, and production transactions.
4. Present existing clickable, platform-labelled citations for every document
   used in the response.
5. Never fabricate a transaction, configuration, document version, or live
   Veeva/Drive URL. If retrieval confidence is low, say so and return the
   existing grounded/fallback response behaviour.

Examples of expected retrieval coverage:

| User question | Expected sources and answer focus |
| --- | --- |
| “How do I fix missing hazardous material pH data?” | EH&S SOP: distinguish IDoc data from manual pH entry; guide `MAT1`, monitor verification, and cite Veeva. |
| “Why is a Request Hub order not appearing in EWM?” | Ordering SOP: validate Request ID, trace `/IWFWND/TRACES` for `MULELEAP`, inspect integration/release status, and cite Veeva. |
| “What is the process to scrap an expired EWM material?” | Disposal SOP: explain monitored disposal date, `MIGO` 551, `PRT0-SCRAP`, follow-up WT, and `/SCWM/PRDO`; cite Veeva. |
| “How does LEAP secondary storage work?” | General overview: explain the three-tier model, temperature/hazardous zones, roles, and EWM boundary; cite Google Drive KT. |
| “What do I check for a goods receipt capacity error?” | GR SUD: capacity consumption, bin setup, HU type restrictions, and label/putaway checks; cite Google Drive. |

### RAG integration contracts

No new database or UI is required. The implementation must reuse the existing
central knowledge registry, `build_retrieval_documents()`, vector-store
initialisation, `retrieve_vector_context(query, limit)`, and existing Chat
citation cards.

| Existing function / component | New responsibility for this corpus | Inputs | Expected return / effect |
| --- | --- | --- | --- |
| Knowledge registry in `vector_store.py` | Register the five canonical documents and their source metadata once | Structured document definitions | One source-of-truth catalog available to retrieval and citations. |
| `build_retrieval_documents()` | Produce section-aware LEAP chunks and retain document/source metadata | Central catalog records | Search chunks with canonical ID, source system, topics, module, and `path_or_url`. |
| `retrieve_vector_context(query, limit)` | Rank LEAP sections with existing exact/lexical/vector methods | User query and limit | Relevant chunks/citations without bypassing existing ticket retrieval. |
| RAG context builder | Add retrieved LEAP snippets to model/fallback grounding | Retrieved chunks plus ticket context | Readable answer with traceable citations. |
| Existing `Chat.jsx` citation card | Render Veeva/Google source label and View Document link | Returned `sources` array | No new UI surface or layout change. |

### Constraints and safety requirements

- Do not add, edit, or duplicate ticket records in `MOCK_DB` for this corpus
  update. The documents are knowledge artifacts, not tickets.
- Do not hard-code SOP content into ticket summaries, Dashboard cards, or
  frontend components. Retrieval must originate from the canonical knowledge
  registry.
- Treat all contained SAP transactions and operational steps as controlled
  reference material. Responses must advise verification against the approved
  document and local authorisation/process requirements before action.
- Preserve the current no-key deterministic retrieval/fallback path. Gemini
  integration remains optional and must not become mandatory.
- Preserve existing source records and citation styling; this addition is
  additive and must not displace current KBA, Veeva, HP ALM, or Drive content.
- Do not represent placeholder URLs, proposed document IDs, or inferred
  ownership/effective dates as approved production document metadata.

### Implementation steps

1. Register the five catalog entries in the existing central knowledge source
   definition with the classifications and metadata specified above.
2. Convert each document into clean section-aware chunks, preserving procedure
   order and transaction/job/path tokens while avoiding repeated boilerplate.
3. Extend vector-store initialisation so the chunks are indexed from that single
   central registry with document, source, module, topic, and URL metadata.
4. Validate hybrid retrieval for the example questions and ensure citations
   resolve to the correct Veeva Vault or Google Drive label/link.
5. Adjust RAG answer formatting only as needed to keep stepwise, conversational
   responses and preserve the no-Gemini fallback path.
6. Run backend retrieval/API checks and the frontend build; confirm that no new
   UI, `MOCK_DB`, or duplicated knowledge data was introduced.

### Success criteria

- Each supplied LEAP document has one canonical knowledge-record identity and
  the agreed Veeva/Google ownership classification.
- A user can retrieve each major process by natural-language intent, transaction
  code, job name, monitor path, or exception name and receives the correct
  source citation.
- Hazardous-material, disposal, Request Hub, and goods-receipt responses retain
  the stated safety and process constraints rather than offering unsafe generic
  instructions.
- Existing ticket-specific answers, citations, Stats, Dashboard, and local
  deterministic fallback continue to work unchanged.
- `MOCK_DB` remains unchanged, and no raw SOP content is duplicated in ticket
  records or frontend components.
