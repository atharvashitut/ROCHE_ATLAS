# ITSM-Copilot architecture

## Topology

ITSM-Copilot is a three-service deployment with adapter boundaries around each enterprise integration.

```text
Operator browser
       │ HTTPS
       ▼
React/Tailwind UI ───────────────► FastAPI API
                                      │
          ┌───────────────────────────┼─────────────────────────────┐
          ▼                           ▼                             ▼
   Terra Vision adapter          Qdrant adapter              Enterprise adapters
  (screenshot analysis)       (knowledge retrieval)   ServiceNow · Veeva · CMDB · Drive
```

The React UI is a static build served by unprivileged Nginx. The FastAPI service owns request validation, privacy controls, triage, change management, audit, and predictive workflows. Qdrant has a named persistent volume in Compose; production deployments should use a managed or separately operated internal Qdrant cluster.

## Service boundaries

| Area | API responsibility | Adapter boundary |
| --- | --- | --- |
| Triage | Vision search, document match, customer/L3 draft | GPT-Terra Vision and Qdrant |
| Service management | Incident relationships, CRs, Problems | ServiceNow REST |
| Change control | Veeva policy parsing, calendar/CMDB risk | Veeva Vault and CMDB/calendar |
| Audit | Immutable, redacted events and playbooks | Google Drive/Docs |
| Predictive | RCA context, recurrence decisions, drift | LLM, ServiceNow, CMDB |

Each module depends on a small protocol or adapter rather than a live SDK. `Mock*Adapter` implementations make the same endpoint contracts executable without enterprise credentials. The adapter mode is selected with `COPILOT_ADAPTER_MODE`: `mock` is the local default and `live` is enabled only after approved endpoints and secrets have been supplied.

## Security and data privacy

- The `RedactionMiddleware` records a redacted JSON request copy, removes sensitive-key values, and sanitizes JSON before an API response leaves the service.
- Sensitive keys include credentials plus common PII/PHI markers (patient, MRN, date of birth, SSN, email, and phone). Embedded email and SSN patterns are also replaced.
- `core.errors` returns a standard error envelope with a correlation ID and avoids exposing internal exception text.
- OAuth client-credentials lifecycle helpers cache tokens only in process and refresh them before expiration. Credentials belong in a secret manager, never source control or a committed `.env` file.
- Runtime API and UI containers run as non-root, have dropped Linux capabilities, `no-new-privileges`, and read-only roots with narrowly scoped temporary filesystems.
- Audit records are canonicalized and hashed before the Drive/Docs adapter receives them. They must not be treated as a substitute for a regulated WORM retention store where one is required.

## Vector search pipeline

1. The client supplies a base64 incident screenshot to the visual-triage endpoint.
2. The vision adapter produces a concise error/product analysis and an embedding.
3. The Qdrant adapter queries the configured knowledge collection and returns the top payload with document ID, title, reference, and score.
4. The drafter chooses a customer resolution or L3 escalation based on retrieval confidence.

In production, create collections and ingest only approved, access-controlled Veeva knowledge documents. Enforce document-level authorization before returning results, retain source-document/page provenance, and protect embedding endpoints using the same outbound credential controls as other adapters.

## Live migration guide

1. Keep `COPILOT_ADAPTER_MODE=mock` while API and frontend contracts are exercised by `scripts/smoke_test.py`.
2. Implement a concrete adapter behind the relevant protocol (`VisionClient`, `VectorStore`, `TicketStore`, `CMDBCalendarAdapter`, `GoogleDriveDocsAdapter`, or `LLMContextAdapter`). Preserve the existing response contract.
3. Configure endpoint URLs, OAuth audience/scope, and client credentials through the approved secret manager. Populate the runtime only through its deployment platform.
4. Run contract tests against a non-production tenant with synthetic data. Confirm privacy middleware redacts both accepted and error payloads.
5. Switch one adapter at a time in a canary deployment. Monitor `/livez`, `/healthz`, API error envelopes, adapter latency, and audit delivery.
6. Promote only after security, validation, and service owners approve the integration.
