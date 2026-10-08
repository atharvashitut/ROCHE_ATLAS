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
