# VitalGuard AI — Phase 0 Repository and Deployment Audit

**Audit date:** 2026-10-11  
**Scope:** GitHub repository, frontend/backend branch alignment, Render service configuration, API/security posture, data persistence, tests and release evidence.  
**Status:** Audit completed; implementation changes begin in Phase 1. This document records repository evidence, not clinical approval.

## 1. Repository and deployment baseline

- Repository: https://github.com/DC-Hub753/VitalGuard-AI
- Frontend: https://vitalguard-ai-dc.onrender.com
  - Render service ID: `srv-db6cit7lk1mc73copa10`
  - Branch: `main`
  - Build: `npm ci && npm run build`
  - Publish directory: `dist`
- Backend: https://vitalguard-risk-api-dc.onrender.com
  - Render service ID: `srv-db6c105ckfvc73ctrelg`
  - Branch: `main`
  - Root directory: `backend/`
  - Build: `pip install -r requirements.txt`
  - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Both Render services have auto-deploy enabled.
- Render event history confirms the latest recorded frontend deployment succeeded on 2026-10-10 at 18:52:16 UTC and the latest recorded backend deployment succeeded on 2026-10-10 at 18:51:14 UTC.
- Latest recorded frontend commit: `a5ce38a8741a0dee1f0d12c33766e0ffc909d697`.
- Latest recorded backend commit: `9cb83bde68148586adb6edcad8e5cd4b811a2353`.
- The workspace service inventory did not show a VitalGuard-managed PostgreSQL service. Render's service metadata does not establish whether a private `DATABASE_URL` is configured, so hosted PostgreSQL remains **unverified**, not confirmed absent.
- The API status endpoint and frontend could not be independently loaded through the web inspection viewer during this audit. That limitation does not establish that either service is down.

## 2. Existing functionality confirmed in repository files

The repository documents and contains implementation for:
- React + TypeScript + Vite frontend.
- FastAPI backend and versioned REST endpoints.
- Synthetic observation ingestion and prediction.
- WebSocket event delivery, reconnect behavior, alert lifecycle and audit history.
- Observation quality, patient timeline and descriptive trend endpoints.
- A synthetic-data LogisticRegression model and coefficient-contribution explanations.
- A NEWS2 demonstration calculator and UI.
- Frontend tests, Python tests, a live API smoke script, and a manually triggered GitHub Actions workflow.
- Dependency automation via Dependabot.

These features are prototype capabilities. Their presence in source or successful deployment does not prove clinical validity or complete end-to-end runtime behavior.

## 3. High-priority gaps

### P0 — Security and data governance
1. No authentication or server-enforced role/resource authorization was found in the inspected deployed backend entry point. Observation, prediction and alert routes must be treated as public until every route is audited and protected.
2. Patient/ward-level access isolation is not established.
3. A manual acknowledgement checkbox for a NEWS2 Scale 2 demo is not authentication or proof of authorization.
4. No approval exists in the repository evidence to use identifiable patient data. Keep real patient data out of this prototype until access controls, governance, and applicable approvals are completed.

### P0 — Persistence and reliability
1. Storage uses `DATABASE_URL` when configured and otherwise falls back to SQLite.
2. Render service metadata does not prove `DATABASE_URL` is configured, and the service inventory did not show a managed VitalGuard database. Verify private environment configuration without exposing secret values.
3. Storage currently creates tables at runtime; a formal migration, backup/restore, retention, and recovery process is still needed.
4. The WebSocket event hub is in-process and intended for a single backend instance; durable replay and cross-instance fan-out are not established.

### P1 — Model validity and real data
1. The current model reports generated synthetic observations as its training data.
2. Model metrics are agreement with synthetic heuristic labels, not evidence of clinical prediction performance.
3. No reproducible, authorized real-clinical-data training and evaluation pipeline has been established in the inspected README/roadmap.
4. SHAP is not currently the implemented explanation method; the backend describes standardized logistic-regression coefficient contributions.
5. Define target outcome, prediction horizon, data leakage controls, calibration, sensitivity, specificity, subgroup evaluation and prospective validation before any clinical claim.

### P1 — Data flow and UI
1. Frontend demo mode defaults to enabled unless explicitly disabled.
2. README/roadmap acknowledge that some patient cohort, vital charts and analytics still use local synthetic fixtures while other views use persisted backend records.
3. Frontend API client exposes patient endpoints; validate every endpoint against the deployed backend contract and verify error/loading/empty/stale-data states.
4. Real incoming data requires a defined authorized source (staff entry, approved import, FHIR/HL7 integration or device gateway), provenance, units, timestamp handling, idempotency and validation.

### P1 — Verification and operations
1. Render deploy/build events succeeded, but the available GitHub combined-status lookup returned no status entries for the sampled commits. Treat CI results as unverified rather than passing.
2. The live API smoke workflow is manually triggered; the release process should explicitly record the deployed commit and smoke result.
3. Add verified health/readiness checks, structured logs, request IDs, security tests, deployment rollback and end-to-end failure/recovery tests.
4. Dependency versions have recently been updated; run the full frontend and backend test suites against the current branches and resolve any failures before relying on them.

## 4. Phase 0 acceptance results

| Check | Result |
|---|---|
| Repository identified | Confirmed |
| Frontend Render service and branch | Confirmed |
| Backend Render service and branch | Confirmed |
| Latest recorded Render deployments | Both succeeded |
| Source-level architecture and features | Reviewed |
| Hosted PostgreSQL configured and durable | Unverified |
| Authentication and authorization | Missing in inspected backend entry point; full route audit required |
| Real clinical data/model validation | Not established |
| GitHub CI passing | Unverified |
| Live runtime smoke test | Not completed in this audit |
| Clinical readiness | Not established; not approved for patient-care use |

## 5. Execution order after Phase 0

1. Phase 1: requirements, clinical safety boundaries and acceptance criteria.
2. Phase 2: architecture, API contracts and data model.
3. Phase 3–4: authentication, authorization and audit controls before any real patient data.
4. Phase 5–6: durable database and validated data ingestion.
5. Phase 7–10: authorized datasets, temporal features, model validation and explainability.
6. Phase 11–14: alert reliability, real-time delivery, integrated dashboard and notification workflows.
7. Phase 15–19: security hardening, CI, observability, staging/production release and resilience testing.
8. Phase 20: independent clinical/safety/privacy review and a formal controlled-pilot go/no-go decision.

## Safety boundary

VitalGuard AI remains a synthetic-data software prototype. Do not enter real patient information, use the current model for diagnosis/triage/treatment, or represent a demo score as a clinically validated probability. Production engineering and successful deployment are necessary but not sufficient for clinical use.


## Follow-up correction — own Render deployment (2026-10-13)

The original audit above captured a previous repository/deployment snapshot. The active deployment for this repository is now:
- Repository: https://github.com/DC-Hub753/VitalGuard-AI
- Frontend: https://vitalguard-ai-dc.onrender.com (service `srv-db6cit7lk1mc73copa10`, branch `main`, auto-deploy enabled).
- Backend: https://vitalguard-risk-api-dc.onrender.com (service `srv-db6c105ckfvc73ctrelg`, root directory `backend/`, branch `main`, auto-deploy enabled).
- Latest observed live commit at the start of Chunk 01: `87c1fc636f639aded1c3a304d1e35a1b48bfc4d7` (Render reported both services live for this commit).

The audit's earlier security and deployment statements should be read as historical observations, not current-state confirmation. This follow-up adds a fail-closed signing-secret check and the current frontend origin to the backend's default CORS allowlist. Deployment and live browser-to-API verification are still required before calling these fixes complete.
