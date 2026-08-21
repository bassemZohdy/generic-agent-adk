# Staging & Cloud Run Deployment Verification Runbook

This runbook details the verification procedures for staging deployments on Google Cloud Run with Keycloak / External OIDC Identity Providers, satisfying requirement T16.

## Pre-Deployment Verification Checklist

1. **Service Account & IAM Permissions**:
   The runtime service account (`basic-adk-runtime@PROJECT_ID.iam.gserviceaccount.com`) must possess:
   - `roles/secretmanager.secretAccessor` (to access database URI and model API keys)
   - `roles/storage.objectAdmin` on `gs://PROJECT_ID-adk-artifacts`
   - `roles/aiplatform.user` (if Vertex AI Code Interpreter or Gemini endpoints are used)

2. **Secrets Configuration in Secret Manager**:
   - `adk-session-database-uri`: Managed PostgreSQL / Cloud SQL URI (`postgresql://user:pass@host:5432/dbname`)
   - `google-api-key` (or `openai-api-key` / `anthropic-api-key` depending on `ADK_MODEL`)

3. **Keycloak / OIDC Realm Configuration**:
   - Ensure the OIDC discovery endpoint (`KEYCLOAK_ISSUER`) and JWKS endpoint (`KEYCLOAK_JWKS_URL`) are publicly reachable from Cloud Run.
   - For local development with Docker Compose, Keycloak realm definitions are provided in `keycloak/realm-basic-agent-dev.json`.

## Cloud Run Deployment

Deploy using the Knative manifest in `deploy/cloudrun/service.yaml`:

```bash
gcloud run services replace deploy/cloudrun/service.yaml \
  --project=PROJECT_ID \
  --region=us-central1
```

## Post-Deployment Smoke Verification Steps

### 1. Readiness & Startup Probes
Confirm the service starts and reports healthy:
```bash
SERVICE_URL=$(gcloud run services describe basic-adk-agent --region=us-central1 --format='value(status.url)')
curl -fsS "${SERVICE_URL}/health"
# Expected response: {"status":"ok"}
```

### 2. OIDC Authentication Verification
Test authenticated access using a valid OIDC Bearer token:
```bash
TOKEN=$(curl -s -X POST "https://KEYCLOAK_HOST/realms/basic-agent/protocol/openid-connect/token" \
  -d "client_id=basic-agent-client" \
  -d "username=testuser" \
  -d "password=testpass" \
  -d "grant_type=password" | jq -r .access_token)

# Execute an authenticated agent turn
curl -X POST "${SERVICE_URL}/run" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, verify runtime connection."}'
```

### 3. IDOR Protection Verification
Verify that attempting to query another user's session returns `403 Forbidden`:
```bash
curl -i -X GET "${SERVICE_URL}/users/another-user/sessions" \
  -H "Authorization: Bearer ${TOKEN}"
# Expected HTTP status: 403 Forbidden
```

### 4. Horizontal Scaling & Session Persistence Smoke Test
* Send a request on Session A.
* Trigger multiple parallel requests to spin up additional Cloud Run instances (`minScale: 1` to `maxScale: 10`).
* Confirm that subsequent requests on Session A retrieve prior state across instances without session loss.
