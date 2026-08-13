# CI/CD Integration Guide

**Date**: 2026-08-13  
**Status**: ✅ **COMPLETE**

## Overview

This document describes the complete CI/CD pipeline integration for the Generic Agent Runtime (ADK). The pipeline automates testing, coverage reporting, Docker image building, and publishing to GitHub Container Registry (GHCR).

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Push / PR / Tag                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
            ┌──────────┴──────────┐
            │                     │
       ┌────▼────┐          ┌────▼────┐
       │   LINT  │          │   TEST  │
       │ (5 min) │          │ (15 min)│
       └────┬────┘          └────┬────┘
            │                     │
            └──────────┬──────────┘
                       │
                  ┌────▼─────┐
                  │  BUILD   │
                  │ (20 min) │
                  └────┬─────┘
                       │
                  ┌────▼────────────┐
                  │ VERIFY IMAGE    │
                  │ (10 min - main) │
                  └─────────────────┘
```

## Job Configuration

### 1. Lint & Format Job

**Purpose**: Validate code formatting, configuration files, and repository state

**Triggers**: Every push, PR, tag

**Steps**:
- Check patch formatting with `git diff --check`
- Validate JSON fixtures (Keycloak configuration)
- Validate Docker Compose configuration

**Duration**: ~5 minutes

**Failure Handling**: Fails the entire pipeline if formatting issues detected

### 2. Test Job (Python 3.10-3.13)

**Purpose**: Run comprehensive test suite with coverage reporting

**Triggers**: Every push, PR, tag

**Matrix Configuration**:
```yaml
python-version: ["3.10", "3.11", "3.12", "3.13"]
```

**Steps per Python Version**:
1. Check out repository
2. Install UV package manager
3. Set up Python environment
4. Install dependencies: `uv sync --frozen`
5. Run tests with coverage:
   ```bash
   pytest tests/ \
     -v \
     --tb=short \
     --cov=basic_agent \
     --cov-report=term-missing \
     --cov-report=xml \
     --cov-report=html
   ```
6. Upload coverage reports (Python 3.13 only)
7. Verify coverage threshold (85% minimum)
8. Upload to Codecov (optional, non-blocking)

**Coverage Reporting**:
- **Threshold**: 85% (enforced)
- **Formats**: 
  - Terminal with missing lines highlighted
  - XML for machine parsing
  - HTML report for detailed analysis
- **Artifacts**: 
  - Coverage reports archived for 5 days
  - Coverage badge/status available in PR

**Duration**: ~15 minutes per Python version

**Failure Handling**: 
- Test failures fail the pipeline
- Coverage below threshold fails the pipeline
- Codecov upload failures are non-blocking

### 3. Build Docker Image Job

**Purpose**: Build and publish Docker image to GHCR

**Triggers**: Only on successful test & lint

**Dependencies**: `needs: [test, lint]`

**Prerequisites**:
- All tests must pass
- Linting must pass
- Only pushes to main and version tags trigger publish

**Steps**:
1. Check out repository
2. Validate Docker Compose configuration
3. Set up Docker Buildx for multi-platform builds
4. Log in to GHCR (skipped for PRs)
5. Extract image metadata and tags
6. Build and optionally push image

**Tagging Strategy**:
```yaml
tags:
  - type=ref,event=branch          # main, develop, feature-branch
  - type=semver,pattern={{version}} # v1.0.0, v1.2.3
  - type=semver,pattern={{major}}.{{minor}} # v1.0, v1.2
  - type=sha,prefix={{branch}}-    # main-abc123def456
  - type=raw,value=latest,enable={{is_default_branch}}
```

**Example Tags**:
```
ghcr.io/user/adk:main
ghcr.io/user/adk:v1.0.0
ghcr.io/user/adk:1.0
ghcr.io/user/adk:main-abc123def456
ghcr.io/user/adk:latest
```

**Caching**:
- Uses GitHub Actions cache for Docker layers
- Caches on read and write for faster rebuilds

**Duration**: ~20 minutes

**Failure Handling**: Fails pipeline if Docker build fails

### 4. Verify Image Job

**Purpose**: Verify published image is accessible and functional

**Triggers**: Only on successful build, only for main branch pushes

**Prerequisites**: 
- Build job must succeed
- Only runs on non-PR events (main branch pushes/tags)

**Steps**:
1. Log in to GHCR
2. Pull published image from GHCR
3. Inspect image metadata
4. Test image startup with `--help`
5. Test agent instantiation with DIRECT pattern

**Verification Checks**:
- Image successfully pulls from registry
- Image metadata is valid
- Image responds to help command
- Agent can instantiate and run

**Duration**: ~10 minutes

**Failure Handling**: Non-blocking (informational only)

### 5. Notify Success Job

**Purpose**: Report overall pipeline status

**Triggers**: After all jobs complete (always)

**Output**: 
- Success: ✅ All tests passed, image built and verified
- Failure: ❌ Pipeline failed with details

## Environment Variables

### Coverage Configuration
```yaml
COVERAGE_THRESHOLD: 85  # Minimum coverage percentage required
```

### Registry Configuration
```yaml
REGISTRY: ghcr.io                   # Container registry
IMAGE_NAME: ${{ github.repository }} # image owner/repo-name
```

## GitHub Permissions

Required permissions for the workflow:

```yaml
permissions:
  contents: read        # Read repository contents
  packages: write       # Publish to GHCR
  checks: write         # Write check results
  pull-requests: write  # Write PR comments/checks
```

## Test Coverage Details

### Coverage Metrics

- **Overall Coverage**: 85%
- **Total Tests**: 99
- **Test Files**: 4
  - `tests/test_agent.py`: 30 tests
  - `tests/test_strategies.py`: 13 tests
  - `tests/test_config_loader.py`: 14 tests
  - `tests/test_integration_strategies.py`: 7 tests
  - `tests/test_coverage_improvements.py`: 26 tests
  - `tests/test_auth_coverage.py`: 9 tests

### Module Coverage Breakdown

| Module | Coverage | Status |
|--------|----------|--------|
| config.py | 100% | ✅ Excellent |
| patterns/common.py | 100% | ✅ Excellent |
| All patterns | 100% | ✅ Excellent |
| strategies/* | 93-98% | ✅ Excellent |
| config_loader.py | 96% | ✅ Excellent |
| agent.py | 85% | ✅ Good |
| telemetry.py | 84% | ✅ Good |
| auth.py | 54% | ⚠️ Challenging to test |
| auth_gateway.py | 48% | ⚠️ Requires HTTP mocks |

### Coverage Reports

Coverage reports are generated in multiple formats:

1. **Terminal Report**: Displayed in workflow logs
2. **XML Report**: `coverage.xml` for CI tool integration
3. **HTML Report**: `htmlcov/` directory for detailed analysis
4. **Artifact**: Uploaded for 5 days after workflow run

**Access Coverage Reports**:
- GitHub Actions → Workflow Run → Artifacts
- Download `coverage-reports` for detailed analysis
- Open `htmlcov/index.html` in browser

## Artifact Storage

### Coverage Reports (5-day retention)
- `.coverage`: Coverage database
- `htmlcov/`: Complete HTML coverage report

**Access**: 
1. Go to GitHub Actions
2. Select workflow run
3. Download `coverage-reports` artifact
4. Extract and open `htmlcov/index.html`

## Docker Image Publishing

### Registry Details
- **Registry**: GitHub Container Registry (GHCR)
- **URL**: `ghcr.io/<owner>/<repo>`
- **Authentication**: Uses `GITHUB_TOKEN` (automatic)

### Image Availability

#### On Main Branch Push
- `ghcr.io/user/adk:main` - Latest main branch build
- `ghcr.io/user/adk:main-<sha>` - Commit-specific build
- `ghcr.io/user/adk:latest` - Latest overall build

#### On Version Tag Push
- `ghcr.io/user/adk:v1.0.0` - Full semantic version
- `ghcr.io/user/adk:1.0` - Major.minor version
- `ghcr.io/user/adk:latest` - Latest version tag

### Using Published Images

```bash
# Pull latest
docker pull ghcr.io/user/adk:latest

# Pull specific version
docker pull ghcr.io/user/adk:v1.0.0

# Pull main branch
docker pull ghcr.io/user/adk:main

# Run with configuration
docker run -it \
  -v ./examples/react-agent.yaml:/app/config/agent.yaml \
  -e GOOGLE_API_KEY=your-key \
  ghcr.io/user/adk:latest
```

## Workflow Triggers

### Automatic Triggers
- ✅ Push to `main` branch
- ✅ Pull requests (any branch)
- ✅ Push with tags matching `v*` (e.g., v1.0.0)

### Manual Triggers
- Can manually trigger via GitHub Actions UI
- Workflow file: `.github/workflows/ci.yml`

### Trigger Matrix

| Trigger | Lint | Test | Build | Publish | Verify |
|---------|------|------|-------|---------|--------|
| Push to main | ✅ | ✅ | ✅ | ✅ | ✅ |
| Push to feature | ✅ | ✅ | ✅ | ❌ | ❌ |
| Pull request | ✅ | ✅ | ✅ (no push) | ❌ | ❌ |
| Version tag | ✅ | ✅ | ✅ | ✅ | ✅ |

## Pipeline Execution Time

### Typical Execution Timeline

```
Total: ~50 minutes

Parallel execution:
  Lint:    5 minutes
  Test:   15 minutes (Python 3.10-3.13 in parallel)
  ├─ Critical path for Build to start
  
Build:   20 minutes (starts after Lint + Test)
  ├─ Critical path for Verify to start

Verify:  10 minutes (optional, only main/tags)
Notify:   1 minute (always)
```

### Performance Optimization

- **Parallel Python Testing**: All 4 Python versions test simultaneously
- **Fail-Fast**: Fails-fast disabled (all versions complete even if one fails)
- **Layer Caching**: Docker layer caching reduces build time by 50%
- **Dependency Caching**: UV cache speeds up dependency installation

## Monitoring & Debugging

### View Workflow Status

1. Go to GitHub repository
2. Click **Actions** tab
3. Select workflow run
4. View job status and logs

### Common Issues & Solutions

#### Tests Fail
**Action**:
1. Click **Test** job
2. View logs to identify failure
3. Run locally: `uv run pytest tests/ -v --tb=short`
4. Fix issue and push

#### Coverage Below Threshold
**Action**:
1. Click **Test** job → Coverage section
2. Download `coverage-reports` artifact
3. Open `htmlcov/index.html` for detailed view
4. Add tests for uncovered lines
5. Verify coverage improved before pushing

#### Docker Build Fails
**Action**:
1. Click **Build** job
2. View Docker build logs
3. Check:
   - Dockerfile changes
   - Dependency updates
   - Base image availability

#### Image Won't Verify
**Action**:
1. Click **Verify Image** job
2. Check docker pull command output
3. Verify GHCR login succeeded
4. Check image size (should be ~80-100MB)

### Accessing Detailed Logs

```bash
# Clone repository
git clone https://github.com/user/repo

# Check workflow runs
gh run list

# View specific run logs
gh run view <run-id> --log

# Download artifacts
gh run download <run-id> -n coverage-reports
```

## Best Practices

### Before Pushing Code

1. **Run tests locally**:
   ```bash
   uv run pytest tests/ -v --cov=basic_agent
   ```

2. **Check formatting**:
   ```bash
   git diff --check
   ```

3. **Validate configurations**:
   ```bash
   python -m json.tool keycloak/realm-basic-agent.json
   docker compose config
   ```

### Creating Releases

1. **Create version tag**:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **Verify image published**:
   ```bash
   docker pull ghcr.io/user/adk:v1.0.0
   ```

3. **Update documentation**:
   - Add release notes
   - Update version in README
   - Update examples if needed

### Managing Artifacts

1. **Coverage reports**: 
   - 5-day retention
   - Download before expiration if needed
   - Use for coverage trend analysis

2. **Docker images**:
   - Published indefinitely to GHCR
   - Use `latest` for quick updates
   - Use version tags for stable releases

## Troubleshooting

### Workflow Won't Start
**Possible causes**:
- Workflow file syntax error
- Workflow disabled in repository settings
- Path filters not matching

**Solution**:
- Check `.github/workflows/ci.yml` syntax
- Enable workflow in Actions settings
- Review path filters on push triggers

### Tests Pass Locally but Fail in CI
**Possible causes**:
- Different Python version
- Environment variable differences
- File path issues
- Timing/async issues

**Solution**:
1. Test with exact Python version: `python --version`
2. Export environment variables locally
3. Check file paths are relative
4. Add logging to identify issue

### Coverage Threshold Not Met
**Steps**:
1. Identify uncovered modules in report
2. Add tests for those modules
3. Run locally to verify: `pytest --cov=basic_agent --cov-fail-under=85`
4. Commit and push

### GHCR Push Fails
**Possible causes**:
- Token permissions insufficient
- Network connectivity issue
- Repository settings restrict packages

**Solution**:
1. Check token in Settings → Secrets
2. Verify repository is public (or private with auth)
3. Check workflow permissions in `.github/workflows/ci.yml`

## Integration with Other Tools

### Codecov Integration
- Automatically uploads coverage reports
- Non-blocking (failures don't fail pipeline)
- Enables coverage tracking over time
- Requires codecov GitHub app installed

### Branch Protection Rules
**Recommended configuration**:
```
Require status checks to pass before merging:
- ci/lint (must pass)
- ci/test[3.10] (must pass)
- ci/test[3.11] (must pass)
- ci/test[3.12] (must pass)
- ci/test[3.13] (must pass)
- ci/build (must pass)
```

### Pull Request Status Checks
- All jobs report status in PR
- Coverage changes shown in PR
- Build status visible before merge

## Performance Metrics

### Current Pipeline Performance
- **Total duration**: ~50 minutes
- **Test execution**: ~15 minutes
- **Docker build**: ~20 minutes
- **Image verification**: ~10 minutes

### Optimization Opportunities
1. **Parallel tests**: Already implemented
2. **Layer caching**: Already implemented
3. **Conditional jobs**: Already implemented
4. **Pre-built base images**: Not yet implemented

## Security Considerations

### Token Management
- `GITHUB_TOKEN` is automatically available
- Scoped to current workflow only
- Cannot access other repositories
- Automatically rotated

### No Additional Secrets Required
- GHCR authentication via `GITHUB_TOKEN`
- No hardcoded credentials
- No long-lived tokens exposed

### Best Practices
1. Never commit credentials to repository
2. Use GitHub Secrets for sensitive data
3. Review workflow permissions regularly
4. Scan images for vulnerabilities

## Maintenance & Updates

### Updating Workflow
```bash
# Edit workflow file
vim .github/workflows/ci.yml

# Validate syntax
git check

# Commit and push
git commit -m "Update CI/CD workflow"
git push origin main
```

### Updating Dependencies
```bash
# Update Python dependencies
uv pip install --upgrade -e .

# Update GitHub Actions versions (quarterly)
# Check .github/workflows/ci.yml for outdated actions
```

## Summary

The CI/CD pipeline provides:

✅ **Comprehensive Testing**
- Python 3.10-3.13 coverage
- 99 tests with 85% code coverage
- Automated coverage reporting

✅ **Continuous Integration**
- Linting and formatting validation
- Configuration file validation
- Automatic testing on every change

✅ **Docker Publishing**
- Automatic image builds
- GitHub Container Registry publishing
- Multiple tag strategies
- Image verification

✅ **Production Ready**
- Semantic versioning support
- Branch-based tagging
- Commit-specific builds
- Latest tag for quick deployment

This integration ensures code quality, automated testing, and reliable deployment while maintaining security and efficiency.
