# Roche ATLAS ITSM Co-Pilot — Implementation Specification

## Objective

Deliver a single-repository IT service-management co-pilot with a React/Vite
frontend and FastAPI backend. It presents mocked ITSM ticket health, ticket
relationships and notes, and a conversational interface for ticket queries and
CR/RCA drafting. The frontend is compiled into static assets which FastAPI
serves from `frontend/dist`.

The requested deployment target was left unselected. Therefore, for this
implementation, **delivery** means a successful production build and push to
`origin/main`. A hosting platform, public URL, credentials, and CI/CD deployment
configuration are explicitly out of scope and must be supplied before a remote
runtime deployment can be performed.

## Requirements

### Frontend build and styling

1. In `frontend`, replace the existing Tailwind v4 dependency with the required
   Tailwind CSS v3 toolchain by running:

   ```bash
   npm install -D tailwindcss@3 postcss autoprefixer
   ```

2. Ensure `frontend/tailwind.config.js` is an ESM configuration with exactly the
   requested scan paths:

   ```js
   /** @type {import('tailwindcss').Config} */
   export default {
     content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
     theme: { extend: {} },
     plugins: [],
   }
   ```

3. `frontend/src/index.css` must begin with the three Tailwind v3 directives:
   `@tailwind base`, `@tailwind components`, and `@tailwind utilities`.
   Add `frontend/postcss.config.js` if it is absent so Vite processes those
   directives with `tailwindcss` and `autoprefixer`.

4. Replace the Vite starter screen with a responsive, accessible two-tab React
   application: **Dashboard** and **Chat**.

### Backend

1. Create an importable `backend/app` package and provide dependency metadata
   sufficient to run FastAPI locally (at minimum FastAPI and Uvicorn).
2. In `backend/app/models.py`, define a typed `Ticket` Pydantic schema,
   in-memory `MOCK_DB`, and `calculate_health_color()`.
3. Seed `MOCK_DB` with these IDs and relationship coverage:

   | ID | Type | Relationship role |
   | --- | --- | --- |
   | `INC0048102` | Incident | Parent incident |
   | `INC0048103` | Incident | Child incident |
   | `PRB0019201` | Problem | Linked problem |
   | `CHG0092100` | Change | Linked change |

4. Every ticket must include enough mock information to render its ID, title,
   state, assignee, SLA state, sentiment, work notes, closure notes, related
   records, and KBA/Veeva/Google Drive reference values.
5. `calculate_health_color(ticket)` returns one of `RED`, `YELLOW`, or `GREEN`.
   The deterministic rule is: a breached SLA or `Frustrated` sentiment is RED;
   an at-risk SLA or `Impatient` sentiment is YELLOW; all other combinations
   are GREEN. The most severe applicable result wins.

### API contract

`backend/app/main.py` exposes JSON APIs under `/api` and serves the compiled
single-page app:

| Method and path | Behavior |
| --- | --- |
| `GET /api/dashboard/tickets` | Returns ticket summaries, each including the calculated health color. Optional `assignee` filtering may be supported server-side; the client must still work from the unfiltered response. |
| `GET /api/tickets/{id}` | Returns the complete ticket and normalized relationship data. Return JSON `404` for an unknown ID. |
| `POST /api/chat/query` | Accepts a JSON query with `message`, optional `ticket_id`, and optional action (`chat`, `generate_cr`, or `generate_rca`). Returns a deterministic mock co-pilot response with any generated CR/RCA content. Validate malformed payloads with FastAPI's normal 422 response. |

Static routing must only occur after API routes are registered. Existing files
under `frontend/dist` are served directly; non-API paths fall back to
`frontend/dist/index.html` so browser refreshes work for the SPA. If no build
exists, API routes must remain usable and root handling must fail clearly rather
than masking an API error.

### User interface

1. `frontend/src/api.js` contains the central `fetch` helpers for all three API
   endpoints. Helpers must reject non-success responses with a useful error.
2. `frontend/src/components/Dashboard.jsx` displays active tickets in a
   color-coded table. Health indicators use RED/YELLOW/GREEN, and visible
   sentiment labels include Frustrated, Impatient, and Calm. It provides
   assignee filtering, loading/empty/error states, and a side drawer that loads
   and displays selected-ticket details. The drawer can be dismissed by its
   explicit control and Escape key.
3. `frontend/src/components/TicketCard.jsx` renders selected-ticket details:
   an inline chat card, latest work notes, closure notes, resource-copy buttons,
   and a clear relational topology tree:

   ```text
   Parent INC -> Child INC(s) -> Linked PRB -> Linked CHG
   ```

   KBA, Veeva, and GDrive buttons copy their corresponding configured reference
   to the browser clipboard and give temporary success/error feedback. They must
   not claim to write to those external systems.
4. `frontend/src/components/Chat.jsx` is a full-width conversation view with
   message input, send control, loading/error feedback, and quick actions that
   invoke CR and RCA generation through `POST /api/chat/query`.
5. `frontend/src/App.jsx` owns the Dashboard/Chat navigation state and mounts
   both views without adding a router dependency. The default tab is Dashboard.
6. Use Tailwind utility classes for application styling. Avoid reliance on
   generated assets, proprietary service APIs, or unsupported browser-only APIs
   without graceful error feedback.

## Architecture

```text
React/Vite UI
  ├─ Dashboard ───── GET /api/dashboard/tickets
  │   └─ TicketCard / drawer ─ GET /api/tickets/{id}
  └─ Chat / quick actions ──── POST /api/chat/query
                                  │
                                  ▼
                         FastAPI + MOCK_DB
                                  │
                                  ▼
                  frontend/dist static files + SPA fallback
```

The system is intentionally mock-backed: no ServiceNow, KBA, Veeva, Google
Drive, LLM provider, database, authentication, or authorization integration is
introduced. The API shape is deliberately separated from UI components so those
systems can replace `MOCK_DB` later without restructuring the screen.

## Constraints and safeguards

- Plan mode prohibits implementation during this phase; this document is the
  only intended workspace change.
- Keep the scope to the requested frontend, backend, build metadata, and this
  specification. Preserve pre-existing uncommitted files that are unrelated to
  the feature, including the root-level untracked `tailwind.config.js`, unless
  the user explicitly authorizes its modification or inclusion.
- Do not invent a cloud deployment target. Do not expose a public service or
  make external system writes.
- The requested `git add .` is superseded by a status review before committing:
  stage only the completed feature and specification files so unrelated user
  work is not included. Use the requested commit message for the scoped commit:
  `feat: complete ATLAS ITSM Co-Pilot codebase`.
- Push only after build and backend smoke checks pass and the configured remote
  and current branch are verified. Do not force-push.

## Implementation steps

1. Inspect repository status and existing Vite configuration; retain relevant
   starter project setup while removing obsolete starter UI code.
2. Install the requested Tailwind v3 development dependencies in `frontend`;
   update the lockfile, Tailwind config, PostCSS config, and global CSS.
3. Create the backend package, ticket schema, four-ticket mock dataset, health
   calculation, API routes, static mount, SPA fallback, and local dependency
   metadata.
4. Build `api.js`, `TicketCard`, `Dashboard`, `Chat`, and the two-tab `App`,
   wiring each state transition to the documented API contract.
5. Run frontend linting when compatible with the existing project and run
   `npm run build` in `frontend`. Run backend import/API smoke checks using an
   in-process FastAPI client or equivalent, including 200/404/422 cases and all
   health color branches.
6. Build production frontend assets with `npm run build`; verify FastAPI serves
   an asset and SPA fallback while all `/api` routes continue to return JSON.
7. Review the diff and Git status; commit only the scoped files with the
   requested message and push the resulting commit to `origin/main`.

## Success criteria

- `frontend/package.json` and lockfile resolve Tailwind 3.x, PostCSS, and
  Autoprefixer; `npm run build` exits successfully and creates `frontend/dist`.
- The finished application has working Dashboard and Chat tabs, assignee
  filters, color-coded health, a usable keyboard-dismissible details drawer,
  topology tree, notes, clipboard feedback, and CR/RCA quick actions.
- `/api/dashboard/tickets` returns all four required records with correct
  colors; ticket detail returns a full record; unknown IDs return 404; chat,
  CR, and RCA requests return deterministic mock responses.
- Direct access to a compiled static asset and a non-API SPA path succeeds when
  `frontend/dist` exists, without intercepting `/api/*` routes.
- The requested commit exists on `main` and `git push origin main` succeeds.
- A remote deployment is not represented as complete unless a hosting target
  and deployment configuration are later provided.
