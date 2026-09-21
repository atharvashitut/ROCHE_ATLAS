# ROCHE_ATLAS

## ITSM-Copilot

ITSM-Copilot provides a FastAPI decisioning API, a React/Tailwind operations UI, and a local Qdrant vector database. Phases 1–4 include triage, change control, audit/playbooks, predictive intelligence, privacy hardening, and a mock-mode smoke suite.

## Start locally

1. Copy `.env.example` to `.env` and supply the GPT-Terra Vision credentials.
2. Run `docker compose up --build`.
3. Open the UI at `http://localhost:5173`, API docs at `http://localhost:8000/docs`, and Qdrant at `http://localhost:6333/dashboard`.

## Test

Run `docker compose run --rm -v "$PWD/backend:/app:ro" api pytest -p no:cacheprovider`.

Generate deterministic fixtures and verify the complete API journey with `python scripts/seed_data.py` and `python scripts/smoke_test.py`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the topology and live-adapter migration model, and [DEPLOYMENT.md](DEPLOYMENT.md) for Docker Compose, Kubernetes, and Ona deployment guidance.

## Triage engine

- `backend/triage/vision_search.py` converts a base64 screenshot into a Terra Vision analysis and retrieves the strongest Qdrant knowledge hit.
- `backend/triage/servicenow_relational.py` provides live REST and in-memory mock adapters for incident search plus parent/child/problem traversal.
- `backend/triage/drafter.py` creates a customer resolution at confidence `>= 0.75`, otherwise an L3 escalation summary.
