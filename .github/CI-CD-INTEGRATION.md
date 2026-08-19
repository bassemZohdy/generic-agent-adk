# CI/CD Integration Guide

This document describes the CI/CD pipeline in `.github/workflows/ci.yml` for
the Generic Agent Runtime (ADK). The pipeline tests, lints, builds a Docker
image, verifies it, and — only once verified — publishes it to GitHub
Container Registry (GHCR).

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 GitHub Push / PR / Tag / Manual             │
└──────────────────────┬──────────────────────────────────────┘
                        │
         ┌──────────────┼─────────────────────────┐
         │              │                         │
    ┌────▼────┐   ┌─────▼─────┐   ┌────▼────────┐  ┌────▼─────┐
    │  LINT   │   │   TEST    │   │ TEST-EXTRAS │  │  AUDIT   │
    │ (5 min) │   │ (15 min)  │   │   (docker,  │  │ (10 min) │
    └────┬────┘   └─────┬─────┘   │    gke)     │  └────┬─────┘
         │              │         └────┬────────┘       │
         └──────────────┼─────────────┼─────────────────┘
                        │
                   ┌────▼─────┐
                   │  BUILD   │   pushes an unverified staging tag only
                   │ (20 min) │   (non-PR); PR runs verify locally instead
                   └────┬─────┘
                        │  (non-PR only)
              ┌─────────▼──────────┐
              │  VERIFY STAGED     │   dependency-lock check, Trivy scan,
              │  IMAGE (10 min)    │   startup smoke test
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │  PROMOTE VERIFIED  │   attaches latest/branch/semver tags
              │  IMAGE (5 min)     │   to the already-verified digest
              └────────────────────┘
```

A vulnerable or broken image is never reachable under a release tag
(`latest`, a branch name, a semver tag): `build` only ever pushes the
throwaway `ci-<sha>` staging tag, and `promote-image` attaches the real tags
only after `verify-image` succeeds.

## Job Configuration

### 1. Lint & Format Job

**Steps**: `git diff --check`, Ruff lint/format checks, package compilation and
build, Keycloak JSON fixture validation, YAML/link validation,
`docker compose config` validation, and secret scanning via
`gitleaks/gitleaks-action`.

**Triggers**: pushes to `main` or version tags, and pull requests.
**Duration**: ~5 minutes.

### 2. Sandbox Image Verification Job (optional)

Runs when the repository variable `SANDBOX_IMAGE_DIGEST` is configured. It
verifies the pinned image reference, scans it for vulnerabilities, and
generates an SBOM using Trivy and Syft.

**Duration**: ~10 minutes.

### 3. Test Job (Python 3.10–3.13)

**Steps**:
1. `uv sync --frozen`
2. `pytest tests/ -v --tb=short --cov=basic_agent --cov-report=term-missing --cov-report=xml --cov-report=html --cov-fail-under=${{ env.COVERAGE_THRESHOLD }}`
3. Upload coverage artifacts (Python 3.13 run only)
4. Optional, non-blocking Codecov upload

**Triggers**: pushes to `main` or version tags, and pull requests.
**Duration**: ~15 minutes per Python version, matrix runs in parallel with
`fail-fast: false`.

### 4. Dependency Audit Job

**Steps**: install the locked environment and run `pip-audit --strict`.

**Triggers**: pushes to `main` or version tags, pull requests, and manual
workflow dispatches.
**Duration**: ~10 minutes.

### 5. Test Extras Job (docker, gke)

**Steps**:
1. `uv sync --frozen --extra ${{ matrix.extra }}` for `docker` and `gke` extras
2. `pytest tests/ -v --tb=short --cov=basic_agent --cov-report=term --cov-fail-under=${{ env.COVERAGE_THRESHOLD }}`

**Triggers**: pushes to `main` or version tags, and pull requests.
**Duration**: ~15 minutes, matrix runs `docker` and `gke` legs in parallel.

### 6. Build Docker Image Job

**Dependencies**: `needs: [test, test-extras, lint, audit]`.

**Steps**:
1. `docker compose config` validation
2. Set up Buildx
3. Non-PR: log in to GHCR, extract release metadata (the tags that will
   eventually be promoted) via `docker/metadata-action`
4. Build the image tagged as `ghcr.io/<owner>/<repo>:ci-<sha>` —
   - non-PR: `push: true` (staging tag only, no release tags applied here)
   - PR: `load: true`, `push: false` (kept local to the runner; PRs — including
     forked ones — have no registry credentials)
5. **PR only**: with the image now loaded locally, run the dependency-lock
   check, a Trivy scan, and the startup smoke test directly against it. This
   is what gives PRs real image-verification coverage without needing a
   registry push.

**Duration**: ~20 minutes.

### 7. Verify Staged Image Job (non-PR only)

**Dependencies**: `needs: build`. **Condition**:
`github.event_name != 'pull_request'`.

**Steps**:
1. Pull the `ci-<sha>` staging tag from GHCR
2. `scripts/verify-image-dependencies.sh` — installed distributions inside
   the image must match `uv.lock` exactly (via `uv lock --check` plus a
   `uv pip freeze` diff)
3. Trivy scan (`HIGH,CRITICAL`, `ignore-unfixed: true`, `exit-code: '1'`) —
   this **fails the workflow** on any fixed HIGH/CRITICAL finding; unfixed
   findings are ignored. It is a hard gate, not informational.
4. Startup smoke test: imports `root_agent` for the `assistant` use case and
   for `examples/approval-gate.yaml`, asserting the expected agent type

**Duration**: ~10 minutes.

### 8. Promote Verified Image Job (non-PR only)

**Dependencies**: `needs: [build, verify-image]`. **Condition**:
`github.event_name != 'pull_request'`.

**Steps**: `docker buildx imagetools create -t <release-tag> <digest-ref>`
for each tag computed in the Build job's metadata step (branch, semver,
`<branch>-<sha>`, and `latest` on the default branch) — pointed at the exact
digest that passed Verify Staged Image, never rebuilt.

**Duration**: ~5 minutes.

### 9. Notify Success Job

Runs `if: always()`. Fails if `build` didn't succeed, or — for non-PR
events — if `verify-image` or `promote-image` didn't succeed.

## Environment Variables

```yaml
COVERAGE_THRESHOLD: 90               # Minimum coverage percentage required
REGISTRY: ghcr.io                    # Container registry
IMAGE_NAME: bassemzohdy/generic-agent-adk # lower-case owner/repo for GHCR
```

## GitHub Permissions

```yaml
permissions:
  contents: read        # Read repository contents
  packages: write       # Publish to GHCR
  checks: write         # Write check results
  pull-requests: write  # Write PR comments/checks
```

## Trigger Matrix

| Trigger        | Lint | Sandbox* | Test | Audit | Test-Extras | Build | Verify | Promote |
|-----------------|------|----------|------|-------|-------------|-------|--------|---------|
| Push to main    | ✅   | ✅       | ✅   | ✅    | ✅          | ✅ (push staging tag) | ✅ | ✅ |
| Push with `v*` tag | ✅ | ✅     | ✅   | ✅    | ✅          | ✅ (push staging tag) | ✅ | ✅ |
| Pull request    | ✅   | ✅       | ✅   | ✅    | ✅          | ✅ (local only, verified in-job) | — | — |
| Manual dispatch | ✅   | ✅       | ✅   | ✅    | ✅          | ✅ (push staging tag) | ✅ | ✅ |

`*` The Sandbox job is skipped when `SANDBOX_IMAGE_DIGEST` is unset.

### Scheduled verification (separate workflow)

[`verify-published-image.yml`](workflows/verify-published-image.yml) runs weekly
(and on manual `workflow_dispatch`) against the **published** `:latest` tag —
outside the push pipeline, so it catches drift push-time CI can't: a new
base-image CVE surfacing after the last green build, or a `:latest` that no
longer boots with its default `CMD`. It logs in, pulls `:latest`, Trivy-scans
it (HIGH/CRITICAL gate), and boots it with its real entrypoint, polling
`/docs` to 200. It lives in its own workflow so the `schedule` trigger never
re-runs `build`/`promote-image`.

## Common Issues & Solutions

**Tests fail** — reproduce locally: `uv run pytest tests/ -v --tb=short`.

**Coverage below threshold** — reproduce locally:
`uv run pytest --cov=basic_agent --cov-report=term-missing --cov-fail-under=90`,
then add tests for the reported missing lines.

**Docker build fails** — check `Dockerfile` and dependency changes; reproduce
with `docker build --progress=plain .`.

**Trivy scan fails in Verify Staged Image** — a HIGH/CRITICAL vulnerability
with a known fix was found; review the current security-hardening entries in
`TODO.md` and the relevant ADR before updating a dependency, then re-push.

**Image won't verify / dependency-lock check fails** — the installed set
inside the image has drifted from `uv.lock`; run
`sh scripts/verify-image-dependencies.sh <local-image-tag>` locally against a
freshly built image to reproduce.

## Manual Verification Before Pushing

```bash
uv run pytest tests/ -v --cov=basic_agent
git diff --check
python -m json.tool keycloak/realm-basic-agent.json
GRAFANA_ADMIN_PASSWORD=x KEYCLOAK_ADMIN_PASSWORD=x docker compose config
```

## Creating a Release

```bash
git tag v1.0.0
git push origin v1.0.0
```

This runs the full pipeline; once Verify Staged Image passes, Promote
Verified Image attaches `v1.0.0` and `1.0` to the verified digest. The
`latest` tag remains on the most recent verified `main` build.
Confirm with `docker pull ghcr.io/bassemzohdy/generic-agent-adk:v1.0.0`.
