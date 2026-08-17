# CI/CD Integration Guide

This document describes the CI/CD pipeline in `.github/workflows/ci.yml` for
the Generic Agent Runtime (ADK). The pipeline tests, lints, builds a Docker
image, verifies it, and — only once verified — publishes it to GitHub
Container Registry (GHCR).

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Push / PR / Tag                    │
└──────────────────────┬───────────────────────────────────────┘
                        │
             ┌──────────┴──────────┐
             │                     │
        ┌────▼────┐          ┌────▼────┐
        │  LINT   │          │  TEST   │
        │ (5 min) │          │ (15 min)│
        └────┬────┘          └────┬────┘
             │                    │
             └──────────┬─────────┘
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

**Steps**: `git diff --check`, Keycloak JSON fixture validation,
`docker compose config` validation, secret scanning via
`gitleaks/gitleaks-action`.

**Triggers**: every push, PR, tag. **Duration**: ~5 minutes.

### 2. Test Job (Python 3.10–3.13)

**Steps**:
1. `uv sync --frozen`
2. `pip-audit --strict` against the locked dependency set
3. `pytest tests/ -v --tb=short --cov=basic_agent --cov-report=term-missing --cov-report=xml --cov-report=html`
4. Upload coverage artifacts (Python 3.13 run only)
5. Re-run with `--cov-fail-under=${{ env.COVERAGE_THRESHOLD }}` (currently
   **85%**) as a hard gate
6. Optional, non-blocking Codecov upload

**Triggers**: every push, PR, tag. **Duration**: ~15 minutes per Python
version, matrix runs in parallel with `fail-fast: false`.

### 3. Build Docker Image Job

**Dependencies**: `needs: [test, lint]`.

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

### 4. Verify Staged Image Job (non-PR only)

**Dependencies**: `needs: build`. **Condition**:
`github.event_name != 'pull_request'`.

**Steps**:
1. Pull the `ci-<sha>` staging tag from GHCR
2. `scripts/verify-image-dependencies.sh` — installed distributions inside
   the image must match `uv.lock` exactly (via `uv lock --check` plus a
   `uv pip freeze` diff)
3. Trivy scan (`HIGH,CRITICAL`, `ignore-unfixed: true`, `exit-code: '1'`) —
   this **fails the workflow** on any match; it is a hard gate, not
   informational
4. Startup smoke test: imports `root_agent` for the `assistant` use case and
   for `examples/approval-gate.yaml`, asserting the expected agent type

**Duration**: ~10 minutes.

### 5. Promote Verified Image Job (non-PR only)

**Dependencies**: `needs: [build, verify-image]`. **Condition**:
`github.event_name != 'pull_request'`.

**Steps**: `docker buildx imagetools create -t <release-tag> <digest-ref>`
for each tag computed in the Build job's metadata step (branch, semver,
`<branch>-<sha>`, and `latest` on the default branch) — pointed at the exact
digest that passed Verify Staged Image, never rebuilt.

**Duration**: ~5 minutes.

### 6. Notify Success Job

Runs `if: always()`. Fails if `build` didn't succeed, or — for non-PR
events — if `verify-image` or `promote-image` didn't succeed.

## Environment Variables

```yaml
COVERAGE_THRESHOLD: 85               # Minimum coverage percentage required
REGISTRY: ghcr.io                    # Container registry
IMAGE_NAME: ${{ github.repository }} # image owner/repo-name
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

| Trigger        | Lint | Test | Build | Verify | Promote |
|-----------------|------|------|-------|--------|---------|
| Push to main    | ✅   | ✅   | ✅ (push staging tag) | ✅ | ✅ |
| Push with `v*` tag | ✅ | ✅  | ✅ (push staging tag) | ✅ | ✅ |
| Pull request    | ✅   | ✅   | ✅ (local only, verified in-job) | — | — |

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
`uv run pytest --cov=basic_agent --cov-report=term-missing --cov-fail-under=85`,
then add tests for the reported missing lines.

**Docker build fails** — check `Dockerfile` and dependency changes; reproduce
with `docker build --progress=plain .`.

**Trivy scan fails in Verify Staged Image** — a HIGH/CRITICAL vulnerability
with a known fix was found; update the affected package (see
`docs/SECURITY-HARDENING-2026-08-15.md` for the pattern used to patch prior
findings) and re-push.

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
Verified Image attaches `v1.0.0`, `1.0`, and `latest` to the verified digest.
Confirm with `docker pull ghcr.io/<owner>/adk:v1.0.0`.
