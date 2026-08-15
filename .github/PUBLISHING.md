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
ghcr.io/your-org/adk:main
ghcr.io/your-org/adk:latest
ghcr.io/your-org/adk:v1.0.0
ghcr.io/your-org/adk:main-abc123def456
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

### 1. Test Job
- Runs pytest across Python 3.10, 3.11, 3.12, 3.13
- Validates configuration files
- Checks patch formatting
- Only builds if tests pass

### 2. Build Job
- Sets up Docker Buildx for multi-architecture builds
- Logs into GitHub Container Registry (on non-PR pushes)
- Extracts metadata and generates tags
- Builds and pushes image to GHCR
- Uses GitHub Actions cache for layer caching

### 3. Verify Job
- Runs only after successful build on `main` branch
- Pulls published image from GHCR
- Verifies image metadata
- Confirms image is accessible

## Usage

### Pulling Images

```bash
# Latest build from main
docker pull ghcr.io/your-org/adk:latest

# Specific version
docker pull ghcr.io/your-org/adk:v1.0.0

# Branch-specific build
docker pull ghcr.io/your-org/adk:main
docker pull ghcr.io/your-org/adk:develop

# Commit-specific build
docker pull ghcr.io/your-org/adk:main-abc123def456
```

### Running Published Image

```bash
docker run -it \
  -v ./examples/assistant.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-api-key \
  ghcr.io/your-org/adk:latest
```

## Authentication

### For Private Repositories

If your repository is private, you need to authenticate:

```bash
# Authenticate with GitHub
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull image
docker pull ghcr.io/your-org/adk:latest

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
2. Build job to create image
3. Image published as:
   - `ghcr.io/your-org/adk:v1.0.0`
   - `ghcr.io/your-org/adk:1.0`
   - `ghcr.io/your-org/adk:latest`

## Monitoring

### View Published Images

In GitHub, go to:
- **Settings** → **Packages and registries** → **Container registry**

Or via CLI:
```bash
# List available tags
docker search ghcr.io/your-org/adk --no-trunc
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

GitHub automatically scans published images in your repository (enterprise feature).

To manually scan locally:

```bash
# Using trivy
trivy image ghcr.io/your-org/adk:latest

# Using grype
grype ghcr.io/your-org/adk:latest
```

## Examples

### Deploy Latest Main Build

```bash
docker pull ghcr.io/your-org/adk:latest
docker run -d \
  -p 8002:8002 \
  -v ./examples/assistant.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-api-key \
  ghcr.io/your-org/adk:latest
```

### Deploy Specific Version

```bash
docker pull ghcr.io/your-org/adk:v1.0.0
docker tag ghcr.io/your-org/adk:v1.0.0 my-adk:production
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
    image: ghcr.io/your-org/adk:latest
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

- **test**: Python tests across 4 versions
- **build**: Docker build and push
- **verify-image**: Verify published image

See `.github/workflows/ci.yml` for complete configuration.
