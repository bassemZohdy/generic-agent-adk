# Managed Persistence Operations & Multi-Instance Architecture

This document describes session and artifact persistence operations for the Generic Agent ADK runtime, supporting multi-instance production deployments (Cloud Run, Kubernetes, or multi-container Docker Compose).

## Persistence Architecture

The runtime separates session metadata/events from artifact storage:

1. **Session Service (`ADK_SESSION_SERVICE_URI` / `DATABASE_URL`)**:
   - Manages user sessions, conversational event history, and agent state deltas.
   - **Supported Backends**: PostgreSQL (`postgresql://...`), MySQL (`mysql://...`), Cloud SQL, and SQLite (`sqlite:///...` for single-instance development).
   - **Production Requirement**: In `DEPLOYMENT_ENV=production`, missing `ADK_SESSION_SERVICE_URI` or `DATABASE_URL` will cause the application to fail closed at startup.

2. **Artifact Service (`ADK_ARTIFACT_SERVICE_URI` / `STORAGE_BUCKET`)**:
   - Stores generated files, blobs, tool outputs, and execution artifacts.
   - **Supported Backends**: Google Cloud Storage (`gs://<bucket>/<prefix>`) and local directory URIs (`file:///...`).
   - **S3 (`s3://...`) is not supported**: the pinned google-adk service registry has no `s3` scheme, and an unknown URI silently falls back to in-memory storage rather than failing closed. Use `gs://` or `file://` instead.
   - If `STORAGE_BUCKET` is specified, the runtime automatically configures `gs://<STORAGE_BUCKET>/adk-artifacts`.

3. **Memory Service (`ADK_MEMORY_SERVICE_URI`)**:
   - Ambient conversational memory and vector retrieval indexing (`memory://` for in-process or managed external service).

## Multi-Instance Configuration

When scaling horizontally across multiple container instances, all instances must point to the same shared database and artifact storage:

```yaml
env:
  - name: DEPLOYMENT_ENV
    value: "production"
  - name: ADK_SESSION_SERVICE_URI
    valueFrom:
      secretKeyRef:
        name: adk-session-db-uri
        key: uri
  - name: STORAGE_BUCKET
    value: "my-project-adk-artifacts"
```

### Session Isolation & Ownership
* Session IDs are strictly scoped to the authenticated token subject (`sub`).
* An instance will reject requests attempting to read or mutate a session belonging to another user (`403 Forbidden`).
* Under `AUTH_DISABLED=true` in development, sessions are isolated per client using a random, unauthenticated `adk_anonymous_id` cookie (a plain `secrets.token_urlsafe(24)` value — not encrypted). Any client can mint one; it only namespaces sessions and is not a credential.

## Operational Procedures

### 1. Database Migrations
ADK manages its internal session and event tables automatically on connection. When deploying schema upgrades:
1. Run pre-deployment verification in staging with `scripts/check-adk-assumptions.py`.
2. Connect to the staging database with the target ADK version before promoting application containers.
3. Keep database credentials in Google Secret Manager or Kubernetes Secrets.

### 2. Backup & Restore
* **Database Backup**: Schedule automated daily snapshots of the Cloud SQL / PostgreSQL instance. Point-in-time recovery (PITR) should be enabled with a 7-day minimum retention window.
* **Artifact Backup**: Enable Object Versioning and Lifecycle Management on the Google Cloud Storage bucket (`STORAGE_BUCKET`).
* **Restore Procedure**:
  1. Restore database snapshot to a new instance or restore point.
  2. Update `ADK_SESSION_SERVICE_URI` in Secret Manager.
  3. Restart application containers to trigger connection pool re-initialization.

### 3. Artifact Retention & Cleanup
Configure lifecycle rules on the artifact storage bucket:
* Delete temporary execution artifacts older than 30 days.
* Transition long-term knowledge attachments to Nearline / Coldline storage after 90 days.
