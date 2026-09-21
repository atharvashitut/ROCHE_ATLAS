# ITSM-Copilot

Phase 1 establishes a FastAPI triage API, a React/Tailwind operator UI, and a local Qdrant vector database.

## Start locally

1. Copy `.env.example` to `.env` and supply the GPT-Terra Vision credentials.
2. Run `docker compose up --build`.
3. Open the UI at `http://localhost:5173`, API docs at `http://localhost:8000/docs`, and Qdrant at `http://localhost:6333/dashboard`.

## Test

Run `docker compose run --rm api pytest`.

## Triage engine

- `backend/triage/vision_search.py` converts a base64 screenshot into a Terra Vision analysis and retrieves the strongest Qdrant knowledge hit.
- `backend/triage/servicenow_relational.py` provides live REST and in-memory mock adapters for incident search plus parent/child/problem traversal.
- `backend/triage/drafter.py` creates a customer resolution at confidence `>= 0.75`, otherwise an L3 escalation summary.
