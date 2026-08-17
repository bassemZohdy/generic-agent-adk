# Docker Image Publishing to GitHub Container Registry

## Overview

The CI/CD pipeline automatically builds and publishes Docker images to GitHub Container Registry (GHCR) for every push to `main` and for version tags.

## Configuration

### 1. GitHub Container Registry Access

The workflow uses the `GITHUB_TOKEN` provided by GitHub Actions, which has the necessary permissions to publish to GHCR.

**No additional secrets are required** - the token is automatically available in workflow context.

### 2. Image Naming Convention

Images are published to:
```
ghcr.io/<owner>/<repository>:<tag>
```

Example:
```
ghcr.io/bassemzohdy/generic-agent-adk:main
ghcr.io/bassemzohdy/generic-agent-adk:latest
ghcr.io/bassemzohdy/generic-agent-adk:v1.0.0
ghcr.io/bassemzohdy/generic-agent-adk:main-abc123def456
```

### 3. Tagging Strategy

The workflow automatically generates multiple tags:

| Type | Condition | Examples |
|------|-----------|----------|
| Branch | Push to branch | `main`, `develop` |
| Semantic Version | Push version tag | `v1.0.0`, `v1.2.0` |
| Major.Minor | Version tag | `v1.0`, `v1.2` |
| Commit SHA | All pushes | `main-abc123def456` |
| Latest | Push to default branch | `latest` |

## Workflow Steps

### 1. Lint Job
- `git diff --check`, Keycloak JSON fixture validation, `docker compose config`
- Secret scan via `gitleaks/gitleaks-action`

### 2. Test Job
- Runs pytest across Python 3.10, 3.11, 3.12, 3.13
- `pip-audit --strict` against locked dependencies
- Enforces the coverage gate (`COVERAGE_THRESHOLD`, currently 85%)

### 3. Build Job
- Sets up Docker Buildx
- Builds the image tagged only as an **unverified staging tag**
  (`ghcr.io/<owner>/<repo>:ci-<sha>`) — never a floating release tag directly
- Non-PR events: pushes the staging tag to GHCR (`push: true`)
- PR events: loads the image into the local Docker daemon only (`load: true`,
  never pushed — forked-PR runs have no registry credentials) and runs the
  dependency-lock check, Trivy scan, and startup smoke test right there,
  against the local image

### 4. Verify Staged Image Job (non-PR only)
- Pulls the staging tag from GHCR
- Runs `scripts/verify-image-dependencies.sh` (confirms installed packages
  match `uv.lock` exactly)
- Scans the staging tag with Trivy (`HIGH,CRITICAL`, fails the build on any
  unfixed match — this is a hard gate, not informational)
- Runs a startup smoke test for two use cases

### 5. Promote Verified Image Job (non-PR only)
- Runs only after Verify Staged Image succeeds
- Uses `docker buildx imagetools create` to attach the real release tags
  (`latest`, branch name, semver, `<branch>-<sha>`) to the **already-verified
  digest** — so a vulnerable or broken image is never reachable under a
  release tag, even transiently

## Usage

### Pulling Images

```bash
# Latest build from main
docker pull ghcr.io/bassemzohdy/generic-agent-adk:latest

# Specific version
docker pull ghcr.io/bassemzohdy/generic-agent-adk:v1.0.0

# Branch-specific build
docker pull ghcr.io/bassemzohdy/generic-agent-adk:main
docker pull ghcr.io/bassemzohdy/generic-agent-adk:develop

# Commit-specific build
docker pull ghcr.io/bassemzohdy/generic-agent-adk:main-abc123def456
```

### Running Published Image

```bash
docker run -it \
  -v ./examples/assistant.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-api-key \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

## Authentication

### For Private Repositories

If your repository is private, you need to authenticate:

```bash
# Authenticate with GitHub
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull image
docker pull ghcr.io/bassemzohdy/generic-agent-adk:latest

# Log out
docker logout ghcr.io
```

### For Public Repositories

Public images can be pulled without authentication.

## Version Release Process

### Creating a Release Tag

```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0
```

This triggers:
1. Tests to run
2. Build job to create the staging-tagged image
3. Verify Staged Image to scan and smoke-test it
4. Promote Verified Image to attach the release tags, only once verified:
   - `ghcr.io/bassemzohdy/generic-agent-adk:v1.0.0`
   - `ghcr.io/bassemzohdy/generic-agent-adk:1.0`
   - `ghcr.io/bassemzohdy/generic-agent-adk:latest`

## Monitoring

### View Published Images

In GitHub, go to:
- **Settings** → **Packages and registries** → **Container registry**

Or via CLI:
```bash
# List available tags
docker search ghcr.io/bassemzohdy/generic-agent-adk --no-trunc
```

### GitHub Actions Logs

View build and publish logs:
- Go to **Actions** tab in your repository
- Click the latest CI/CD workflow run
- View logs for each job step

## Troubleshooting

### Build Fails

Check the CI/CD logs:
1. Go to **Actions** → Latest run
2. Check **Test** job for test failures
3. Check **Build** job for Docker build errors

### Image Not Pushed

Ensure:
- Workflow ran on `main` branch or version tag
- **Build** job succeeded
- GitHub token has package write permissions (should be automatic)

### Can't Pull Image

For public repos:
- Ensure repository is public
- Verify image tag is correct

For private repos:
- Authenticate with GitHub token
- Ensure you have repository access

## Security

### Token Scope

The `GITHUB_TOKEN` used in workflows:
- Is automatically created and has limited scope
- Cannot access other repositories
- Cannot modify repository settings
- Only has permissions for the current workflow context

### Best Practices

1. **Never commit credentials** - Use secrets management
2. **Use version tags** for production deployments
3. **Verify image signatures** when available
4. **Scan images** for vulnerabilities (see below)

## Image Scanning

Every image is scanned with Trivy (`HIGH,CRITICAL`, unfixed findings ignored)
as a hard CI gate before it can carry a release tag — see Verify Staged Image
above. This is enforced, not merely informational.

To manually scan locally:

```bash
# Using trivy
trivy image ghcr.io/bassemzohdy/generic-agent-adk:latest

# Using grype
grype ghcr.io/bassemzohdy/generic-agent-adk:latest
```

## Examples

### Deploy Latest Main Build

```bash
docker pull ghcr.io/bassemzohdy/generic-agent-adk:latest
docker run -d \
  -p 8002:8002 \
  -v ./examples/assistant.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-api-key \
  ghcr.io/bassemzohdy/generic-agent-adk:latest
```

### Deploy Specific Version

```bash
docker pull ghcr.io/bassemzohdy/generic-agent-adk:v1.0.0
docker tag ghcr.io/bassemzohdy/generic-agent-adk:v1.0.0 my-adk:production
docker run -d \
  -p 8002:8002 \
  -v ./examples/assistant.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-api-key \
  my-adk:production
```

### Use in Docker Compose

```yaml
version: '3.8'
services:
  adk-runtime:
    image: ghcr.io/bassemzohdy/generic-agent-adk:latest
    ports:
      - "8002:8002"
    environment:
      GOOGLE_API_KEY: ${GOOGLE_API_KEY}
      AGENT_USE_CASE: assistant
      ADK_MODEL: gemini-2.0-flash
    volumes:
      - ./examples/assistant.yaml:/app/config/agent.yaml
```

## CI/CD Workflow File

The workflow is defined in `.github/workflows/ci.yml`:

- **lint**: formatting, config validation, secret scan
- **test**: Python tests across 4 versions, `pip-audit`, coverage gate
- **build**: Docker build; pushes only an unverified staging tag (non-PR), or
  builds + verifies locally with no push (PR)
- **verify-image**: dependency-lock check, Trivy scan, smoke test of the
  staging tag (non-PR only)
- **promote-image**: attaches release tags to the verified digest (non-PR
  only)

See `.github/workflows/ci.yml` for complete configuration.
