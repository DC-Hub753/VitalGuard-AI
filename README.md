# VitalGuard AI — Patient Deterioration Early-Warning Prototype

> **DEMO ONLY · SYNTHETIC DATA · NOT FOR CLINICAL USE**
>
> VitalGuard AI is a software prototype for exploring patient-observation monitoring, risk-signal visualisation and alert workflows. The included patients and observations are synthetic. The current risk model is trained on generated data and is not clinically validated.

## Requirements

- Node.js 20 or newer (Node.js 22 LTS recommended)
- npm 10 or newer
- Python 3.11+ recommended for the FastAPI backend

## Quick start

Frontend:
```bash
npm ci
cp .env.example .env
npm run dev
```

Backend (from the repository root):
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

The frontend normally runs at `http://localhost:5173`; the backend at `http://localhost:8000`. API docs are at `http://localhost:8000/docs`.

## Verification commands

Run from the project root:
```bash
npm run lint
npm test
npm run build
```

Run backend tests from `backend/`:
```bash
pytest -q
```

Only describe a command as passing after it has been run successfully against the current source.

## Environment configuration

Copy `.env.example` to `.env` for local development. Vite variables prefixed with `VITE_` are bundled into browser code, so never store secrets in them.

| Variable | Purpose |
| --- | --- |
| `VITE_DEMO_MODE` | Starts in synthetic demo mode unless explicitly set to `false`. |
| `VITE_API_BASE_URL` | Optional FastAPI base URL; local default is normally `http://localhost:8000`. |
| `VITE_APP_VERSION` | Frontend version label. |
| `DATABASE_URL` | Optional backend database URL; SQLite is used by default. |
| `VITALGUARD_DB_PATH` | Optional local SQLite file path for tests/development. |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins. |
| `VITALGUARD_AUTH_SECRET` | **Backend only.** Required signing secret, at least 32 characters; generate a unique random value and store only in Render's private environment. |
| `VITALGUARD_AUTH_USERNAME` | **Backend only.** Bootstrap operator username. |
| `VITALGUARD_AUTH_PASSWORD` | **Backend only.** Bootstrap operator password. |

## Current implementation

- React, TypeScript, Vite and Tailwind frontend with dashboard, patient directory/detail, alerts, analytics and settings.
- Existing synthetic patient records, demo simulation controls and local UI persistence.
- FastAPI synthetic risk endpoint, model metadata, deterministic holdout evaluation, coefficient-contribution explanation, bounded observation history and observation quality endpoint.
- SQLAlchemy storage adapter supports local SQLite and PostgreSQL when `DATABASE_URL` is configured. A hosted PostgreSQL instance is not yet confirmed in the live deployment.
- WebSocket event delivery for persisted observations and alerts, with a reconnecting frontend client.
- Persistent demo alert lifecycle (open, acknowledged, resolved) with audit trail.
- Dashboard includes backend alert operations, observation quality, and persisted prediction history. Patient detail includes backend observation/alert/audit timeline and descriptive trends. Patient cohort, vital charts and analytics still use local synthetic fixtures.
- Interactive model evaluation and coefficient-contribution workbench in Settings.
- Source-documented NEWS2 parameter scoring demo endpoint (`POST /api/v1/scores/news2`) and Settings calculator; this is not a clinically validated or approved implementation.
- Unified persisted patient timeline (`GET /api/v1/patients/{patient_id}/timeline`) and descriptive trend endpoint (`GET /api/v1/observations/trends?patient_id=...`).
- Deterministic simulator endpoint for stable, worsening, and recovering fictional observation scenarios.

### Phase 1 API: synthetic observation ingestion

Endpoint:
`POST /api/v1/demo/observations`

Example request:
```json
{
  "patient_id": "DEMO-LIVE-001",
  "scenario": "worsening",
  "step": 3
}
```

Supported scenarios: `stable`, `worsening`, `recovering`. Step must be between 0 and 1000. The endpoint generates one deterministic observation for the requested scenario and step, runs the current synthetic risk model, and persists the resulting observation/prediction using the configured storage adapter.

Example local request:
```bash
curl -X POST http://localhost:8000/api/v1/demo/observations \
  -H 'Content-Type: application/json' \
  -d '{"patient_id":"DEMO-LIVE-001","scenario":"worsening","step":3}'
```

History can be inspected at:
`GET /api/v1/observations?patient_id=DEMO-LIVE-001`

This is a one-observation-per-request simulator, not a continuous device feed. Each request creates a new observation; requests are not idempotent. The backend broadcasts saved observations and alerts over `/api/v1/live`, and the dashboard includes backend alert, history, timeline and trend views. Not all patient cards/charts are API-backed. Durable hosted PostgreSQL configuration remains outstanding.

## Important limitations

- Patient directory, vital charts, cohort analytics and some local alert cards still use local synthetic fixtures; backend history and alert operations are separate views.
- The model is a StandardScaler + LogisticRegression classifier trained on generated synthetic observations and heuristic labels. Its output is a demo signal, not a validated probability of clinical deterioration.
- Model evaluation metrics describe agreement with synthetic heuristic labels only. Coefficient contributions are not SHAP explanations or causal attributions.
- WebSocket fan-out is in-process and designed for a single backend instance. Hosted PostgreSQL, identity/role controls, and production operational safeguards remain deployment work.
- The NEWS2 scoring endpoint follows parameter bands from the RCP chart for demonstration, but the implementation is not clinically validated or approved. The existing local NEWS2-like display also remains a separate synthetic fixture.
- No clinical performance, safety, regulatory or real-device integration is claimed.
- Do not use real patient data or use this prototype to diagnose, triage, or make treatment decisions.

## Project layout

```text
backend/app/
  main.py              FastAPI application
  model.py             Synthetic demo classifier
  schemas.py           Validated API request/response schemas
  simulator.py         Deterministic fictional observation scenarios
  simulator_routes.py  Demo observation ingestion endpoint
  timeline_routes.py   Persisted patient timeline
  trend_routes.py      Descriptive observation trends
  news2.py             NEWS2 parameter scoring demonstration
  storage.py           SQLite/PostgreSQL storage adapter
backend/tests/
  test_api.py
  test_simulator.py
src/
  data/                Synthetic frontend fixtures
  pages/               Dashboard and feature pages
  services/            API and demo data services
  store/               Frontend state
  test/                Frontend tests
docs/
  REALTIME_DEMO_ROADMAP.md
```

## Database configuration

- Local development defaults to SQLite.
- Hosted deployments can set `DATABASE_URL` to a PostgreSQL connection string. The adapter normalizes common `postgres://` and `postgresql://` URLs to psycopg 3. The live Render API currently defaults to SQLite unless a private `DATABASE_URL` is configured.
- Configure credentials only in the backend service's private environment settings; do not commit them.
- Provision the hosted database separately. Existing SQLite records are not automatically migrated.
- This storage adapter currently supports synthetic demonstration data only; it is not a production patient-record system.

## Live API smoke test

Run `npm run smoke:api` to check health, model metadata, frontend CORS preflight, synthetic prediction and persistence, model evaluation, coefficient contributions, NEWS2 scoring/Scale 2 guard, data quality, alert acknowledgement/resolution and audit trail. This writes fictional records to the configured demo database.

- Workflow: `.github/workflows/live-api-smoke.yml`
- Script: `scripts/smoke-test.mjs`
- Run via GitHub Actions → Live API smoke test → Run workflow.
- The workflow creates synthetic demo records; never send real patient data.

## Delivery plan and current project phase

The repository has two phase histories: the legacy feature roadmap below documents already-built demo capabilities, while the sequential production-readiness plan defines the work to do next. Do not confuse legacy feature phase numbers with the new delivery phases.

- [Master delivery plan](docs/MASTER_DELIVERY_PLAN.md) — full sequential phases 0–20 and release gates.
- [Phase 0 audit](docs/PHASE_0_AUDIT.md) — current repository, Render baseline and gaps.
- [Phase 1 requirements](docs/PHASE_1_REQUIREMENTS.md) — product, data, security, model and safety requirements.
- [Phase 2 architecture](docs/PHASE_2_ARCHITECTURE.md) — deployed topology, modules and trust boundaries.
- [Phase 2 API contracts](docs/PHASE_2_API_CONTRACTS.md) — current endpoint inventory and proposed API semantics.
- [Phase 2 data model](docs/PHASE_2_DATA_MODEL.md) — current storage and target observation lifecycle.
- [Legacy demo feature roadmap](docs/REALTIME_DEMO_ROADMAP.md) — delivered prototype capabilities and limitations.
- [Render release runbook](docs/RENDER_RELEASE_RUNBOOK.md) — service branches and deployment verification.

Current delivery phase: Phase 5 database migrations are in progress. Authentication/authorization code and schema migrations are present, but hosted database durability/backup-restore evidence and live end-to-end verification remain outstanding. The current Render demo URLs are [frontend](https://vitalguard-ai-dc.onrender.com) and [backend API](https://vitalguard-risk-api-dc.onrender.com/docs). The frontend production fallback and live API smoke workflow target these current URLs; override `VITE_API_BASE_URL` only when deliberately pointing the frontend at another API.
