# Cloud Run deployment notes

`service.yaml` intentionally keeps the service private to authenticated callers:
it uses `internal-and-cloud-load-balancing` ingress and leaves the Cloud Run
invoker IAM check enabled. Replace the `KEYCLOAK_HOST` and image placeholders,
then deploy with a service account that can read the referenced Secret Manager
secret.

```bash
gcloud run services replace deploy/cloudrun/service.yaml \
  --region=REGION \
  --project=PROJECT_ID

gcloud run services add-iam-policy-binding basic-adk-agent \
  --region=REGION \
  --project=PROJECT_ID \
  --member="serviceAccount:CALLER_SERVICE_ACCOUNT" \
  --role=roles/run.invoker
```

Grant `roles/run.invoker` only to the load balancer, gateway, or caller
identities that should reach the service. Keep `AUTH_DISABLED=false`; a
production deployment without `KEYCLOAK_ISSUER` fails during settings load.
