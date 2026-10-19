# Roche ATLAS ITSM Co-Pilot — End-to-End Project Specification

## 1. Purpose and scope

ATLAS is a read-only ITSM co-pilot proof of concept for support operations. It combines a ServiceNow-style ticket catalogue, enterprise knowledge, operational analytics, ticket topology, and a grounded chat assistant. It helps L2/L3 engineers and support leads understand workload, SLA exposure, a ticket's evidence and relationships, and safe resolution actions.

ATLAS is advisory: it does not create, update, close, approve, or remediate records in ServiceNow, SAP, HP ALM, Veeva Vault, Google Drive, or any other external system.

## 2. Requirements

### Functional

1. Use one canonical ticket source for Dashboard, Stats, topology, ticket detail, AI insight, and Chat.
2. Support `INC`, `RITM`, `PRB`, and `CHG` records, including ownership, SLA, journals, tasks, attachments, relationships, and resolution plans.
3. Calculate all workload/SLA metrics in the backend from canonical ticket fields.
4. Support grounded questions for ticket status, assignment groups, assignees, SAP modules, ServiceNow processes, and curated enterprise documents.
5. Treat `at risk <assignment group|assignee>` and `SLA breach <assignment group|assignee>` as scoped ticket-list queries, not global SLA-health summaries.
6. Include stored, ticket-specific resolution actions in direct ticket enquiries when backend data exists.
7. Provide SAP Basis, SAP Security, SAP PLM, SAP EWM, and ServiceNow operational/runbook knowledge.
8. Support long-form FDS, HP ALM test case, RCA, SOP, runbook, technical troubleshooting, and architecture answers.
9. Provide both JSON and SSE chat APIs, with provenance metadata and graceful fallbacks.

### Non-functional

1. Run on an 8-vCPU/32-GB instance with seven Ollama threads and one CPU left for FastAPI/system work.
2. Use an Ollama context window of 4,096 tokens.
3. Use two output tiers: 350 tokens only for explicit brief operational lookups; 2,048 tokens for every other request.
4. Remain usable without external AI credentials through local and deterministic fallbacks.
5. Keep all connector behavior read-only.
6. Do not create separate frontend fixtures, browser-computed metrics, or a second operational system of record.

## 3. As-is architecture

```text
React 19 + Vite browser
  ├─ Stats: KPIs, charts, drill-down
  ├─ Dashboard: ticket queue, drawer, activities, topology, sources
  └─ Chat: streamed operational answers
             │ REST + Server-Sent Events
             ▼
FastAPI / Uvicorn
  ├─ main.py              API, ticket payloads, stats and advisory analysis
  ├─ rag_engine.py        intent routing, exact filters, retrieval, prompting
  ├─ models.py            typed tickets, SLA and relationship normalization
  ├─ central_db.py        canonical knowledge and ticket access boundary
  ├─ agent_intelligence.py explainable ticket/team recommendations
  ├─ connectors.py        read-only source adapter contract
  ├─ vector_store.py      Chroma/local retrieval
  └─ ollama_client.py     async local model adapter
       │                 │                 │
       ▼                 ▼                 ▼
 Canonical ticket     Knowledge registry   Derived Chroma vector index
 repository           SAP + ServiceNow     (rebuildable, not authoritative)
       │                                      │
       └───────────── retrieval corpus ───────┘
                         │
                         ▼
                Ollama daemon (Llama 3.2 3B; 1B fallback)
                Optional Gemini generation/embeddings
```

### Component ownership

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Web UI | React 19, Vite | Presentation only: Stats, Dashboard, Chat, drawer, drill-down, stream display. |
| API | FastAPI, Uvicorn | REST/SSE endpoints, payload composition, backend analytics. |
| Domain | Pydantic | Ticket validation, normalisation, SLA state, task/journal rules, topology. |
| Operational data | In-memory repository | Canonical runtime ticket data. |
| Knowledge | Curated Python registry | Canonical enterprise document metadata and content. |
| Retrieval | Chroma/local fallback | Semantic evidence lookup from derived documents. |
| AI | Ollama, optional Gemini | Grounded natural-language synthesis. |

## 4. Frontend design and features

`frontend/src/App.jsx` provides the three product views:

| View | Main components | Function |
| --- | --- | --- |
| Stats | `Stats.jsx` | API-calculated KPIs, SLA/state/type/team charts and drill-down. |
| Dashboard | `Dashboard.jsx`, `TicketCard.jsx`, `WorkItemActivities.jsx`, `TopologyTree.jsx`, `KnowledgeReferences.jsx` | Queue, detailed record, journal/activity, relationships, evidence, AI insight. |
| Chat | `Chat.jsx` | Prompt shortcuts, streamed responses, source metadata, inline SLA chart display. |

`frontend/src/api.js` is the sole browser API boundary. It parses REST responses and SSE events from `/api/chat/stream`. The browser does not calculate alternative KPI values. Theme selection in `localStorage` is presentation-only; chat history is sent as a bounded, non-persistent context window.

## 5. Backend technical analysis

### API and analytics — `backend/app/main.py`

Main responsibilities:

- Starts vector indexing and non-blocking Ollama diagnostics.
- Serves `/api/dashboard/tickets`, `/api/dashboard/assignment-groups`, `/api/dashboard/stats`, `/api/tickets/{ticket_id}`, `/api/knowledge/sources`, `/api/rag/status`, `/api/chat/query`, and `/api/chat/stream`.
- Creates canonical ticket payloads, including topology, SLA/breach reason, sentiment, knowledge, and AI insight.
- Calculates dashboard statistics from filtered ticket records, not browser state.
- Adds deterministic module-aware diagnostic actions (for example, SM12/SMQ1/SMQ2 for EWM; SU53 for Security; SM37/ST22 for Basis).

### Domain and ticket model — `backend/app/models.py`

`Ticket` is the shared Pydantic shape for incidents, requests, problems, and changes. It contains identity, descriptions, state, priority, assignee/group, caller, SAP modules, SLA values, hold reason, journals, attachments, task lists, relations, knowledge references, and `ai_resolution_steps`.

The model validator normalizes legacy aliases, priority/state formats, journal/task shapes, close-note rules, SLA state, and relationship topology. The shared SLA predicates define:

- **Breached:** SLA-tracked INC/RITM with explicit breach or zero/negative remaining time.
- **At risk:** non-breached SLA-tracked INC/RITM with positive remaining time inside the configured 90-minute warning buffer.
- **On track:** SLA-tracked work outside the warning buffer.

### Canonical data boundary — `backend/app/central_db.py`

`CENTRAL_TICKET_REPOSITORY` exposes a read-only `MappingProxyType` over the typed ticket catalogue registered from `MOCK_DB` in `models.py`. `CENTRAL_KNOWLEDGE_DB` holds curated documents with ID, title, source type, system, connector, URL, content, linked tickets, and tags.

This means the current runtime has no PostgreSQL, MySQL, or cloud transactional database. Tickets and documents are source-controlled Python data, loaded in memory at application start. It is correct for a demonstrator but not a multi-user production persistence design.

### Query orchestration — `backend/app/rag_engine.py`

The RAG engine:

1. Parses ticket IDs, groups, assignees, SAP modules, priorities, states, hold reasons, record types, and SLA wording.
2. Hydrates current tickets from the canonical repository.
3. Calculates KPI answers through the same stats aggregation as the Stats tab.
4. Returns deterministic responses for exact data: metrics, scoped at-risk/breach ticket lists, and direct ticket resolution plans.
5. Retrieves procedural/knowledge evidence when a generative answer is appropriate.
6. Builds a bounded grounded prompt and invokes Ollama.
7. Falls back to retrieved or deterministic guidance when inference is unavailable.

The direct-ticket path includes resolution actions from `Ticket.ai_resolution_steps`; it only gives generic guidance when no ticket-specific plan is present. Scoped SLA queue entries contain number, summary, priority/state, owner, SLA condition, latest update, related records, and suggested next action.

### Explainable intelligence — `agent_intelligence.py`

This is rules-based operational analysis, not an opaque ML model. It evaluates SLA urgency, customer comments, pending tasks, dependencies, historical/similar records, and workload to create explainable findings and recommendations for tickets, assignees, and groups.

## 6. Database and data utilisation

| Store | Implementation | Authority | Consumers |
| --- | --- | --- | --- |
| Ticket catalogue | Typed `MOCK_DB` registered in an in-memory repository | Current source of truth for operations | Dashboard, Stats, ticket detail, topology, agents, Chat. |
| Knowledge catalogue | `CENTRAL_KNOWLEDGE_DB` | Current source of truth for curated documentation | Retrieval, sources API, ticket knowledge references. |
| Vector index | Chroma under `backend/.atlas-vector-db` by default | Derived and rebuildable only | RAG retrieval. |
| Browser storage | `localStorage` | Theme preference only | UI. |
| Chat transcript | Request payload, max 12 messages | Ephemeral follow-up context only | Chat. |

### Relationship model

```text
Parent INC ── child_ids ──> Child INC
    ├── linked_problem ──> PRB ── ptasks
    │                         └── linked_change ──> CHG ── ctasks
    └── linked_change ────────────────────────────────┘

RITM ── sctasks
```

Relationships are IDs resolved from canonical records at request time. This prevents parent views, child views, and Chat from holding conflicting copies of a record's state or journals.

### Retrieval index

`vector_store.py` indexes knowledge documents plus ticket overviews, journal streams, and task streams. Metadata includes ticket ID/number, assignment group, module, record type, source system, source URL, and document section. A content fingerprint resynchronizes the index when the canonical corpus changes.

| Condition | Embedding/retrieval behavior |
| --- | --- |
| Gemini configured and available | Gemini `gemini-embedding-001` embeddings. |
| Gemini unavailable | Deterministic local 256-dimension hash embeddings. |
| Chroma unavailable | In-process vector-map similarity fallback. |

The vector index is never the authority for ticket state, SLA, assignee, or KPI counts; those always come from the canonical ticket repository.

## 7. AI, RAG, and output policy

| Capability | Implementation | Purpose |
| --- | --- | --- |
| Primary generation | Ollama `llama3.2:3b` | Local grounded responses. |
| Local fallback | Ollama `llama3.2:1b` | Secondary local generation model. |
| Optional remote fallback | Gemini client | Used only after local generation fails when configured. |
| Embeddings | Gemini or local hash | Retrieval vector creation. |
| Exact operational answers | Python calculations/formatters | Prevents fabricated counts, ticket details, and plans. |
| Advisory intelligence | Explainable Python rules | Ticket/team recommendations. |

The models are not fine-tuned on ATLAS data. They are grounded at runtime. Deterministic paths deliberately take precedence whenever backend data already answers the question exactly.

```text
Question → intent/filter parser → canonical ticket/stat lookup + vector retrieval
         → deterministic answer OR grounded prompt → Ollama stream
         → optional Gemini fallback → JSON/SSE with sources and retrieval metadata
```

| Query class | Maximum output | Examples |
| --- | --- | --- |
| Explicit brief operational lookup | 350 tokens | Ticket status, priority, assignee status, SLA status, basic count. |
| All other requests | 2,048 tokens | FDS, test case, RCA, SOP, runbook, troubleshooting, architecture, explanation. |

Complex work receives 2,048 tokens by default; it is not required to prove it needs a larger budget.

## 8. Runtime and configuration

`start.sh` starts or reuses Ollama, creates/uses `.venv`, installs missing backend/frontend dependencies, starts FastAPI on port 8000, and starts Vite on port 5173. It stores runtime PID/log files in a temporary per-user directory, outside the Git worktree.

| Variable | Default/target | Meaning |
| --- | --- | --- |
| `ATLAS_OLLAMA_NUM_THREAD` | `7` | Seven of eight vCPUs for inference. |
| `ATLAS_OLLAMA_NUM_CTX` | `4096` | Model context window. |
| `ATLAS_OLLAMA_MAX_TOKENS` | `2048` | Full/default budget. |
| `ATLAS_OLLAMA_STANDARD_MAX_TOKENS` | `350` | Brief lookup budget. |
| `ATLAS_OLLAMA_NUM_BATCH` | `512` | CPU inference batch size. |
| `ATLAS_OLLAMA_TIMEOUT_SECONDS` | `600` | Generation read-gap timeout. |
| `ATLAS_SLA_WARNING_BUFFER_MINUTES` | `90` | Shared SLA at-risk threshold. |

Ollama owns model memory in a separate process; FastAPI only sends bounded HTTP requests. This avoids loading model weights into the web process.

## 9. Security, compliance, and limitations

1. The current records are curated/mock PoC data, not live production data.
2. Connectors are read-only and currently act as an integration-ready contract rather than live synchronized clients.
3. AI output is advisory. SAP ownership, approved change control, CAB/GxP controls, and validation evidence remain mandatory.
4. Production requires SSO/RBAC, audit logging, secret-manager integration, encryption, retention controls, data classification, and approved hosting.
5. Chroma can contain locally indexed operational text and must receive equivalent controls in production.
6. There is currently no persistent relational database, connector scheduler, tenant model, durable audit trail, or automated write-back/remediation.
7. Cache/vector data, `.venv`, Python caches, and temporary logs must not be committed.

## 10. Current feature inventory

- Dashboard queue with filters and detailed ticket drawer.
- Stats/KPI analytics with drill-down.
- SLA health, on-track, at-risk, and breached classification.
- Scoped at-risk and breach lists by assignment group or assignee.
- Direct ticket status, journals, topology, related work, knowledge references, and stored remediation actions.
- Customer sentiment and explainable workload/ticket insights.
- ServiceNow and SAP Basis/Security/PLM/EWM procedural retrieval.
- FDS/procedure/test-case long-form generation context.
- Chroma-backed retrieval with offline local fallback.
- Streaming chat and non-streaming compatibility endpoint.

## 11. Implementation plan

### Maintain the current PoC

1. Add/modify tickets only in the canonical ticket authoring source, then register/rebuild the repository.
2. Add/modify documents only in `CENTRAL_KNOWLEDGE_DB`, with stable ID, source metadata, tags, links, and safe steps.
3. Add dashboard/chat filters in the shared backend filter functions so Stats, Dashboard, and Chat stay consistent.
4. Classify each new question path as exact canonical, calculated analytics, or generative RAG before implementing it.
5. Rebuild/retest retrieval after canonical data changes.
6. Keep frontend changes presentation-only.

### Move toward production

1. Replace in-code fixtures with authenticated, read-only ServiceNow/knowledge source synchronization or a replicated normalized database.
2. Persist tickets, journals, tasks, relationships, attachments, source revisions, and document metadata.
3. Add idempotent sync jobs, freshness telemetry, source timestamps, and audit history.
4. Keep the central repository interface so API, analytics, topology, and RAG consumers need minimal rewrites.
5. Version vector documents by source revision and implement incremental reindexing.
6. Add enterprise security, encryption, retention, RBAC, monitoring, automated tests, and operational dashboards.

## 12. Success criteria

### PoC

- Every view shows the same canonical ticket state, ownership, SLA, journals, and relationships.
- Stats totals equal the filtered ticket set used to calculate them.
- `SLA health <scope>` gives the scoped aggregate; `at risk <scope>` and `SLA breach <scope>` list only matching active INC/RITM tickets.
- Direct ticket queries return current canonical status plus ticket-specific resolution actions when stored.
- Procedures retrieve relevant central knowledge and expose source metadata.
- FDS/procedural questions use the 2,048-token profile and 4,096-token context; basic status lookups use 350 tokens.
- The application has documented local fallbacks when Gemini, Chroma, or Ollama is unavailable.

### Production readiness

- Source synchronization is authenticated, read-only, auditable, and measurably fresh.
- Security, data lifecycle, and GxP/operational advisory controls are approved.
- Automated regression tests cover SLA routing, ticket relationships, data provenance, retrieval relevance, and connector contracts.
