# Release Automation Guide

This guide documents the automated release process for the Cancelable project using python-semantic-release.

## Overview

The Cancelable project uses **fully automated semantic versioning**. Every commit to the `main` branch is analyzed, and when appropriate, a new version is automatically released.

### Workflow Diagram

```
┌─────────────────┐
│ Push to main    │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Analyze commits │ ← python-semantic-release
│ (conventional)  │
└────────┬────────┘
         │
         v
    ┌────┴────┐
    │ Release │
    │ needed? │
    └────┬────┘
         │
    ┌────┴────┐
    │   No    │ ──→ [Stop]
    │         │
    └─────────┘
         │
    ┌────┴────┐
    │   Yes   │
    │         │
    └────┬────┘
         │
         v
┌─────────────────┐
│ 1. Bump version │ ── Update pyproject.toml
│ 2. Update       │ ── Update CHANGELOG.md
│ 3. Create tag   │ ── Git tag (GPG signed)
│ 4. Build dist   │ ── uv build
│ 5. Publish PyPI │ ── Trusted Publishing
│ 6. Create GH    │ ── GitHub Release
│    Release      │
│ 7. Deploy docs  │ ── mike deploy
└─────────────────┘
```

## Conventional Commits

### Format

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Commit Types

| Type | Description | Version Bump | Example |
|------|-------------|--------------|---------|
| `feat` | New feature | Minor (0.5.0 → 0.6.0) | `feat: add signal-based cancellation` |
| `fix` | Bug fix | Patch (0.5.0 → 0.5.1) | `fix: resolve race condition in token` |
| `perf` | Performance improvement | Patch | `perf: optimize registry lookup` |
| `refactor` | Code refactoring | Patch | `refactor: simplify token linking` |
| `docs` | Documentation only | None | `docs: update README examples` |
| `chore` | Build/tooling changes | None | `chore: update dependencies` |
| `ci` | CI configuration | None | `ci: add coverage reporting` |
| `style` | Code style/formatting | None | `style: format with ruff` |
| `test` | Add/update tests | None | `test: add timeout source tests` |
| `revert` | Revert previous commit | None | `revert: "feat: add feature X"` |

### Breaking Changes

Breaking changes trigger a **major version bump** (0.5.0 → 1.0.0):

**Option 1: Use `!` after type:**
```bash
git commit -m "feat!: redesign cancellation API

The CancellationToken.cancel() method is now async.
Synchronous code should use cancel_sync() instead."
```

**Option 2: Use `BREAKING CHANGE:` footer:**
```bash
git commit -m "feat: redesign cancellation API

BREAKING CHANGE: The CancellationToken.cancel() method is now
async. Synchronous code should use cancel_sync() instead."
```

### Examples

**Feature (minor bump):**
```bash
git commit -m "feat: add condition-based cancellation source

Adds ConditionSource that polls a predicate function and
cancels when it returns True. Useful for resource monitoring."
```

**Bug fix (patch bump):**
```bash
git commit -m "fix: prevent deadlock in cross-thread cancellation

Ensures proper lock ordering when cancelling from different threads."
```

**Performance (patch bump):**
```bash
git commit -m "perf: cache compiled regex patterns in commit parser"
```

**Documentation (no release):**
```bash
git commit -m "docs: add FastAPI integration examples"
```

**Multiple changes (use highest priority):**
```bash
# This will trigger a minor bump (feat takes precedence)
git commit -m "feat: add new source type

Also fixes minor bug in existing timeout source."
```

## Enforcement

### Pre-commit Validation

Commit messages are validated **before** commit using lefthook:

```yaml
# lefthook.yml
commit-msg:
  commands:
    conventional:
      run: |
        if ! head -1 {1} | grep -qE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+?\))?: .{1,}$'; then
          echo "❌ Commit message must follow Conventional Commits format"
          exit 1
        fi
```

**Bypass if needed (not recommended):**
```bash
git commit --no-verify -m "wip: temporary commit"
```

### GitHub PR Title Check

PR titles are also validated in CI to ensure they follow conventional commits.

## Local Development

### Preview Next Version

Check what version would be released without making changes:

```bash
# Must be on main branch
git checkout main
git pull

# Preview next version
uv run semantic-release --noop version --print

# With debug output
uv run semantic-release --noop --verbose version --print
```

**Example output:**
```
0.6.0  # Next version would be 0.6.0
```

### Preview Changelog

Generate changelog for unreleased commits:

```bash
uv run semantic-release changelog
```

### Test Configuration

Validate semantic-release configuration:

```bash
# Show configuration
uv run semantic-release generate-config

# Check if release would happen
uv run semantic-release --noop version --print
```

## Manual Release Trigger

While releases are automatic, you can manually trigger the workflow:

### Via GitHub UI

1. Go to **Actions** → **Semantic Release**
2. Click **Run workflow**
3. Select branch: `main`
4. Click **Run workflow**

### Via GitHub CLI

```bash
gh workflow run semantic-release.yml
```

## PyPI Trusted Publishing

The project uses PyPI's **Trusted Publishing** for secure, token-free releases.

### How It Works

1. GitHub Actions workflow runs with `id-token: write` permission
2. GitHub provides OIDC token proving workflow identity
3. PyPI verifies token and authorizes publish
4. No API tokens stored or managed!

### Configuration

**On PyPI:**
- Publisher: GitHub Actions
- Owner: `hotherio`
- Repository: `cancelable`
- Workflow: `semantic-release.yml`
- Environment: (none)

**In workflow:**
```yaml
permissions:
  id-token: write  # Required for Trusted Publishing
  contents: write  # Create tags and releases

- name: Publish to PyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  # No password/token needed!
```

### Setup for New Projects

1. Create package on PyPI (one-time manual publish)
2. Go to PyPI → Project → Publishing
3. Add GitHub publisher:
   - Owner: organization/user
   - Repository: repo-name
   - Workflow: semantic-release.yml
4. Save configuration
5. Future releases publish automatically!

## Troubleshooting

### No Release Created

**Problem:** Pushed to main, but no release was created.

**Possible causes:**

1. **No releasable commits since last release:**
   ```bash
   # Check commits since last tag
   git log $(git describe --tags --abbrev=0)..HEAD --oneline

   # Look for feat:, fix:, perf:, or refactor: commits
   ```

   **Solution:** Only `feat`, `fix`, `perf`, and `refactor` trigger releases.

2. **Branch not configured for releases:**
   ```bash
   # Verify you're on main
   git branch --show-current
   ```

   **Solution:** Releases only happen from `main` branch.

3. **Invalid commit format:**
   ```bash
   # Check recent commits
   git log --oneline -5
   ```

   **Solution:** Ensure commits follow conventional commits format.

### Version Conflict

**Problem:** `Version x.y.z already exists on PyPI`

**Cause:** Tag exists but PyPI publish failed previously.

**Solution:**
```bash
# Option 1: Delete local and remote tag, create new commit
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z

# Make a small change
git commit --allow-empty -m "chore: trigger new release"
git push

# Option 2: Manually publish to PyPI
uv build
uv publish
```

### PyPI Upload Fails

**Problem:** `Error: Trusted publishing exchange failure`

**Possible causes:**

1. **Publisher not configured on PyPI:**
   - Go to PyPI project settings → Publishing
   - Add GitHub publisher with correct details

2. **Workflow permissions incorrect:**
   ```yaml
   # Verify in .github/workflows/semantic-release.yml
   permissions:
     id-token: write  # Must be present
   ```

3. **Wrong workflow name:**
   - PyPI publisher must match exact workflow filename
   - Default: `semantic-release.yml`

### Documentation Not Deployed

**Problem:** Release succeeded but docs not updated.

**Cause:** Docs workflow depends on `release.published` event.

**Check:**
```bash
# Verify docs.yaml uses correct event
grep -A 3 "release:" .github/workflows/docs.yaml

# Should show:
#   release:
#     types:
#     - published
```

**Manual deploy:**
```bash
uv sync --group doc
uv run mike deploy --push --update-aliases v0.5 latest
```

## Migration from git-cliff

### What Changed

| Before (git-cliff) | After (PSR) |
|-------------------|-------------|
| Manual trigger via GitHub Actions | Automatic on push to main |
| Three-stage releases (dev/rc/final) | Single semantic release |
| `tools/release.py` custom script | python-semantic-release |
| `cliff.toml` configuration | `pyproject.toml` configuration |
| Manual version bumping | Automatic from commits |
| Separate changelog generation | Integrated changelog |

### Removed Files

- `tools/release.py` - Custom release script
- `cliff.toml` - git-cliff configuration
- `.github/workflows/bump.yml` - Manual bump workflow
- `.github/workflows/release.yml` - Tag-triggered release

### Preserved

- **Conventional commits** - Still required (now enforced)
- **GPG signing** - Tags and commits still signed
- **CHANGELOG.md** - Still auto-generated
- **PyPI publishing** - Now via Trusted Publishing
- **Documentation deployment** - Still automatic

## Best Practices

### Commit Messages

1. **Write clear, descriptive messages:**
   ```bash
   # Good
   feat: add timeout parameter to Cancelable context

   # Bad
   feat: add timeout
   ```

2. **Include context in body:**
   ```bash
   feat: add condition-based cancellation

   Allows cancellation based on custom predicates that are
   polled periodically. Useful for resource monitoring and
   external stop signals.
   ```

3. **Document breaking changes:**
   ```bash
   feat!: make CancellationToken.cancel() async

   BREAKING CHANGE: The cancel() method is now async and must
   be awaited. Synchronous callers should use cancel_sync()
   instead.

   Migration guide:
   - Old: token.cancel()
   - New: await token.cancel()  # async context
   - New: token.cancel_sync()   # sync context
   ```

### Pull Requests

1. **Use conventional format in PR title:**
   ```
   feat: add feature X
   fix: resolve bug Y
   docs: update guide Z
   ```

2. **PR title becomes the commit message** when squash merging

3. **Include breaking changes in PR description** if applicable

### Versioning Strategy

- **0.x.y**: Pre-1.0 development (current)
  - Breaking changes allowed on minor bumps
  - Set `major_on_zero = false` in config

- **1.x.y**: Stable releases (future)
  - Breaking changes require major bump
  - Set `major_on_zero = true` when ready

## Advanced Configuration

### Custom Commit Types

To add custom commit types, edit `pyproject.toml`:

```toml
[tool.semantic_release.commit_parser_options]
allowed_tags = [
    "build", "chore", "ci", "docs", "feat", "fix",
    "perf", "refactor", "style", "test", "revert",
    "custom",  # Add custom type
]
minor_tags = ["feat", "custom"]  # Types that trigger minor bump
patch_tags = ["fix", "perf", "refactor"]  # Types that trigger patch bump
```

### Changelog Template

Custom changelog templates can be added in `templates/` directory:

```bash
# Project structure
templates/
  └── CHANGELOG.md.j2
```

### Version Variables

Access version in other files using template variables:

```toml
[tool.semantic_release]
version_toml = [
    "pyproject.toml:project.version",
    "src/hother/cancelable/__init__.py:__version__",
]
```

## Reference

- [python-semantic-release Documentation](https://python-semantic-release.readthedocs.io/)
- [Conventional Commits Specification](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
- [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
- [Keep a Changelog](https://keepachangelog.com/)
