# GitHub Setup & CI/CD Configuration Guide

**Date**: 2026-08-14  
**Purpose**: Complete guide to configure GitHub repository and enable CI/CD

---

## Step 1: Create GitHub Repository

### Option A: Create on GitHub Web (Recommended)

1. Go to https://github.com/new
2. Enter repository name: `adk` or `generic-agent-runtime`
3. Choose visibility: **Public** (for GHCR image sharing) or **Private**
4. **DO NOT** initialize with README (you already have one)
5. Click "Create repository"
6. Copy the repository URL (e.g., `https://github.com/your-username/adk.git`)

### Option B: Using GitHub CLI

```bash
gh repo create adk --public --source=. --remote=origin --push
```

---

## Step 2: Add Remote & Configure

### Add Remote to Local Repository

Replace `YOUR_USERNAME` and `REPO_NAME` with your values:

```bash
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
git branch -M main  # Ensure main branch
git push -u origin main
```

### Verify Remote

```bash
git remote -v
# Should show:
# origin  https://github.com/YOUR_USERNAME/REPO_NAME.git (fetch)
# origin  https://github.com/YOUR_USERNAME/REPO_NAME.git (push)
```

---

## Step 3: Configure GitHub Secrets (For Private Repos)

If your repository is **private**, GitHub Actions needs authentication to push to GHCR.

### For Public Repositories
- No additional secrets needed
- `GITHUB_TOKEN` is provided automatically
- Images will be public on GHCR

### For Private Repositories

1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `GHCR_TOKEN`
4. Value: Create a GitHub Personal Access Token:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `write:packages`, `read:packages`
   - Copy the token
   - Paste into `GHCR_TOKEN` secret

**Note**: The included CI workflow uses `GITHUB_TOKEN`, so this is only if you want to override it.

---

## Step 4: Configure GitHub Actions Permissions

The CI/CD workflow needs permissions to:
- Read repository contents
- Write to packages (GHCR)
- Write checks (test results)
- Write to pull requests (coverage comments)

### Default Permissions (Recommended)

These are already set in `.github/workflows/ci.yml`:

```yaml
permissions:
  contents: read
  packages: write
  checks: write
  pull-requests: write
```

### Verify Workflow Permissions

1. Go to **Settings → Actions → General**
2. Find "Workflow permissions"
3. Select: **Read and write permissions**
4. Check: **Allow GitHub Actions to create and approve pull requests**
5. Click **Save**

---

## Step 5: Enable GitHub Container Registry (GHCR)

### Prerequisites

Your GitHub account must be linked to GHCR. This is automatic for all users.

### Verify GHCR Access

```bash
# Authenticate locally
docker login ghcr.io
# Username: your-github-username
# Password: Personal Access Token with read:packages, write:packages
```

---

## Step 6: Configure Branch Protection (Optional but Recommended)

Add branch protection to enforce quality gates:

1. Go to **Settings → Branches**
2. Click **Add rule** under "Branch protection rules"
3. Pattern: `main`
4. Enable:
   - ✅ Require a pull request before merging
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging

5. **Status checks to require**:
   - `ci / lint` - Code formatting
   - `ci / test (3.10)` - Test Python 3.10
   - `ci / test (3.11)` - Test Python 3.11
   - `ci / test (3.12)` - Test Python 3.12
   - `ci / test (3.13)` - Test Python 3.13
   - `ci / build` - Docker build
   - `ci / verify-image` - Image verification

6. Click **Create**

---

## Step 7: Enable Codecov (Optional)

For automatic coverage reports in pull requests:

1. Go to https://codecov.io
2. Sign in with GitHub
3. Authorize Codecov
4. Select repository: `your-username/adk`
5. **Installation note**: The workflow already sends coverage to Codecov
   - Codecov app will automatically add comments to PRs

---

## Step 8: Push to GitHub

### Initial Push (All Commits)

```bash
git push -u origin main
```

### Verify Push

```bash
git log origin/main --oneline -5
# Should show your commits on GitHub
```

### Monitor CI/CD

1. Go to your repository on GitHub
2. Click **Actions** tab
3. Watch the workflow run
4. Verify all jobs pass

---

## Step 9: Verify CI/CD is Working

### Check Workflow Status

1. Navigate to **Actions** tab in GitHub
2. You should see a workflow run for your push
3. Jobs should run in order:
   - ✅ Lint
   - ✅ Test (4 Python versions in parallel)
   - ✅ Build
   - ✅ Verify Image
   - ✅ Notify

### Check Test Results

1. Click the latest workflow run
2. Click **Test** job
3. Expand the test output
4. Should see: **99 passed, 23 warnings**

### Check Docker Publishing

After successful build:

1. Go to https://ghcr.io/your-username/repo-name
2. Should see image tags:
   - `main` - Latest main branch build
   - `main-<sha>` - Commit-specific
   - `latest` - Latest overall
   - Date/version tags if you create version releases

---

## Step 10: Create First Release (Optional)

### Semantic Versioning Tag

```bash
git tag v1.0.0
git push origin v1.0.0
```

This triggers:
- Tests to run
- Docker image to build and publish
- Images tagged as:
  - `v1.0.0` - Full version
  - `1.0` - Major.minor
  - `latest` - Latest version

---

## Troubleshooting

### Workflow Doesn't Run

**Problem**: Pushed to GitHub but no workflow started

**Solutions**:
1. Check `.github/workflows/ci.yml` exists in repository
2. Verify file is on `main` branch: `git ls-remote origin main`
3. Go to **Actions** → **Workflows** → **CI/CD**
4. Click **Enable workflow** if disabled

### Tests Fail in CI But Pass Locally

**Possible causes**:
- Different Python version (use matrix version)
- Environment variables not set
- File path differences

**Solution**:
```bash
# Test locally with same environment
python3.10 -m venv venv
source venv/bin/activate
uv sync
uv run pytest tests/ -v
```

### Can't Push to GHCR

**Problem**: Authentication failed when publishing image

**Solutions**:
1. For **public repos**: No auth needed (uses GITHUB_TOKEN automatically)
2. For **private repos**: Create GHCR_TOKEN secret (see Step 3)
3. Verify token has `write:packages` scope
4. Check repository visibility hasn't changed

### GitHub Actions Rate Limited

**Problem**: Actions job times out or fails

**Solution**:
- GitHub Actions provides 2,000 free minutes/month for public repos
- Increase if needed: Settings → Billing → Compute

---

## Continuous Integration Workflow

Once configured, here's what happens automatically:

### On Every Push to `main`

```
git push origin main
  ↓
GitHub detects push
  ↓
Triggers CI/CD workflow
  ↓
1. Lint Job (5 min)
   - Format validation
   - Config validation
  ↓
2. Test Job (15 min) - 4 Python versions in parallel
   - Install dependencies
   - Run 99 tests
   - Generate coverage report
   - Verify 85% coverage
  ↓
3. Build Job (20 min) - only if tests pass
   - Build Docker image
   - Push to GHCR
   - Create multiple tags
  ↓
4. Verify Job (10 min) - only if build passes
   - Pull published image
   - Verify it works
  ↓
5. Notify Job (1 min) - always
   - Report status
  ↓
✅ Pipeline complete (~50 minutes)
```

### On Pull Request

```
git push origin feature-branch
Create pull request
  ↓
GitHub detects PR
  ↓
Triggers CI/CD workflow
  ↓
1. Lint Job ✅
2. Test Job ✅ (shows coverage change)
3. Build Job ✅ (builds but doesn't push)
  ↓
Shows status checks on PR
Only allows merge if all checks pass
```

### On Version Tag

```
git tag v1.0.0
git push origin v1.0.0
  ↓
Triggers full pipeline
  ↓
Creates Docker image with tags:
  - v1.0.0
  - 1.0
  - latest
  ↓
Image published to GHCR
```

---

## Monitoring & Notifications

### GitHub Notifications

- Email notifications for:
  - Workflow failures
  - Action required on PR
  - Status check changes

### Configure in GitHub

1. **Settings → Notifications**
2. Select notification preferences:
   - ✅ Pull request reviews
   - ✅ Failed workflows
   - ✅ Completed workflows (optional)

### Action Required Events

If workflow fails:
1. Click failing job
2. View error messages
3. Fix locally
4. Push fix
5. Workflow re-runs automatically

---

## Security Considerations

### Tokens & Secrets

- ✅ GITHUB_TOKEN - Provided by GitHub, scope-limited
- ✅ GHCR_TOKEN (if used) - Personal access token, regenerate if leaked
- ✅ GOOGLE_API_KEY - Set via GitHub Secrets, never in code

### Best Practices

1. **Never commit secrets**
   - `.env` in `.gitignore` ✅
   - Secrets in GitHub Settings ✅
   - No tokens in code ✅

2. **Keep tokens secure**
   - Regenerate if exposed
   - Use fine-grained permissions
   - Review token usage periodically

3. **Monitor GHCR images**
   - Check published images on GHCR
   - Verify tags are correct
   - Watch for unexpected images

---

## Next Steps

After successful setup:

1. **Create a Release** (optional)
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **Use Published Image**
   ```bash
   docker pull ghcr.io/your-username/adk:latest
   docker run -it ghcr.io/your-username/adk:latest
   ```

3. **Monitor Workflow**
   - Go to Actions tab
   - Watch workflow runs
   - Check test results
   - Verify image publishing

4. **Develop with Confidence**
   - Push feature branches
   - Create pull requests
   - CI/CD validates automatically
   - Merge with confidence

---

## Useful Commands

```bash
# Check remote
git remote -v

# Update remote URL (if needed)
git remote set-url origin https://github.com/new-username/new-repo.git

# Push all branches
git push -u origin --all

# Push all tags
git push origin --tags

# View workflow status
gh workflow list
gh run list
gh run view <run-id>

# View recent workflow runs
gh run list --limit 10

# Download workflow artifacts
gh run download <run-id> -n coverage-reports
```

---

## Support

**Questions about GitHub Actions?**
- Read GitHub Actions docs: https://docs.github.com/en/actions
- Check workflow syntax: `.github/workflows/ci.yml`
- View workflow guide: `.github/CI-CD-INTEGRATION.md`

**Docker image issues?**
- Read GHCR guide: `.github/PUBLISHING.md`
- Check image tags: https://ghcr.io/your-username/adk

**CI/CD troubleshooting?**
- Check workflow logs in Actions tab
- Read CI-CD-INTEGRATION.md
- Test locally: `uv run pytest tests/`

---

## Summary Checklist

- [ ] Create GitHub repository
- [ ] Add remote to local repo: `git remote add origin <url>`
- [ ] Configure GitHub Actions permissions
- [ ] Enable GHCR (automatic)
- [ ] (Optional) Create GHCR_TOKEN for private repos
- [ ] (Optional) Set up branch protection
- [ ] (Optional) Enable Codecov
- [ ] Push to GitHub: `git push -u origin main`
- [ ] Verify workflow in Actions tab
- [ ] Check test results
- [ ] Verify image published to GHCR
- [ ] Done! ✅

---

**Status**: Ready to configure GitHub CI/CD  
**Time to Setup**: ~15 minutes  
**Maintenance**: Automatic (push → test → publish)

Push to GitHub and watch the CI/CD pipeline run automatically! 🚀
