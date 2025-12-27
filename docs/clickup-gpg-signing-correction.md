# GPG Signing with python-semantic-release

## Overview

Python-semantic-release supports GPG signing through **both** Docker action and pip installation approaches. The common misconception that "Docker can't access GPG" is incorrect.

## How Docker-Based GPG Signing Works

The `crazy-max/ghaction-import-gpg` action configures GPG on the GitHub Actions runner (host). The PSR Docker action inherits this configuration automatically through GitHub Actions' standard mounts.

**No special Docker configuration needed!**

### Workflow Configuration (Docker Action)

```yaml
- name: Import GPG key
  id: import-gpg
  uses: crazy-max/ghaction-import-gpg@v6
  with:
    gpg_private_key: ${{ secrets.HOTHER_BOT_GPG_KEY }}
    passphrase: ${{ secrets.HOTHER_BOT_GPG_PASSPHRASE }}
    git_user_signingkey: true
    git_commit_gpgsign: true
    git_tag_gpgsign: true

- name: Configure Git
  env:
    GIT_EMAIL: ${{ steps.import-gpg.outputs.email }}
    GIT_NAME: ${{ steps.import-gpg.outputs.name }}
  run: |
    git config user.email "$GIT_EMAIL"
    git config user.name "$GIT_NAME"
    git config commit.gpgsign true
    git config tag.gpgsign true

- name: Python Semantic Release
  id: release
  uses: python-semantic-release/python-semantic-release@v10.5.3
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    git_committer_name: ${{ steps.import-gpg.outputs.name }}
    git_committer_email: ${{ steps.import-gpg.outputs.email }}
```

**How it works:**
1. GPG key imported to runner's keyring by `crazy-max/ghaction-import-gpg`
2. Git configured globally on runner
3. PSR Docker action inherits Git config via GitHub Actions mounts
4. Signing works automatically

## Alternative: pip-installed PSR

Both approaches support GPG signing equally well.

### When to use Docker action (Recommended)
- ✅ Standard workflow
- ✅ Simpler setup (one step)
- ✅ Better caching
- ✅ Consistent environment

### When to use pip install
- Need specific PSR version not available as Docker action
- Want to run PSR locally in dev environment
- Need to customize PSR execution extensively

### pip Installation Example

```yaml
- name: Setup Python
  uses: actions/setup-python@v4
  with:
    python-version: '3.11'

- name: Install PSR
  run: pip install python-semantic-release

- name: Import GPG key
  uses: crazy-max/ghaction-import-gpg@v6
  with:
    gpg_private_key: ${{ secrets.HOTHER_BOT_GPG_KEY }}
    passphrase: ${{ secrets.HOTHER_BOT_GPG_PASSPHRASE }}
    git_user_signingkey: true
    git_commit_gpgsign: true
    git_tag_gpgsign: true

- name: Run PSR
  run: semantic-release version
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Both produce identical results - GPG-signed commits and tags.

## Common Misconception: "Docker can't access GPG"

**False.** This misconception arises from:
1. Default Docker isolation (true for standalone Docker)
2. Missing configuration (forgetting to enable signing)
3. Misunderstanding GitHub Actions' mount behavior

**Reality:** GitHub Actions automatically makes host Git configuration available to Docker actions, including GPG setup.

## SSH Signing Alternative

PSR Docker action also supports SSH signing natively:

```yaml
- name: Python Semantic Release
  uses: python-semantic-release/python-semantic-release@v10.5.3
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    ssh_private_signing_key: ${{ secrets.SSH_PRIVATE_SIGNING_KEY }}
    ssh_public_signing_key: ${{ secrets.SSH_PUBLIC_SIGNING_KEY }}
```

## Comparison: GPG vs SSH vs Unsigned

| Feature | GPG (Docker) | GPG (pip) | SSH (Docker native) | Unsigned |
|---------|--------------|-----------|---------------------|----------|
| Setup complexity | Low | Medium | Low | Lowest |
| Expiration support | ✅ | ✅ | ❌ | N/A |
| Revocation support | ✅ | ✅ | ❌ | N/A |
| GitHub verified badge | ✅ | ✅ | ✅ | ❌ |
| Docker action support | ✅ | N/A | ✅ Native | ✅ |

## Troubleshooting

### "Commits not signed" with Docker action

**Check:**
1. `git_commit_gpgsign: true` in import-gpg action
2. `git config commit.gpgsign true` in workflow
3. Secrets configured: `HOTHER_BOT_GPG_KEY`, `HOTHER_BOT_GPG_PASSPHRASE`

**Verify in workflow logs:**
```bash
git config --global --get commit.gpgsign  # Should be: true
git config --global --get user.signingkey # Should show key ID
```

### "gpg: cannot run gpg: No such file or directory"

**Cause:** Git config not properly set before PSR runs

**Solution:** Ensure `Configure Git` step runs before PSR step and has:
```yaml
git config commit.gpgsign true
git config tag.gpgsign true
```

Also ensure `git_commit_gpgsign: true` in the import-gpg action.

## Key Takeaways

1. **Docker DOES support GPG signing** with `crazy-max/ghaction-import-gpg`
2. **Docker action is simpler** than pip installation for CI/CD
3. **Both approaches work equally well** for GPG signing
4. **GitHub Actions automatically mounts** Git config to Docker containers
5. **No special Docker configuration needed** - standard PSR action works

## References

- [crazy-max/ghaction-import-gpg](https://github.com/crazy-max/ghaction-import-gpg) - Handles GPG setup for GitHub Actions
- [python-semantic-release Docker action](https://github.com/python-semantic-release/python-semantic-release)
- [GitHub Actions Docker container mounts](https://docs.github.com/en/actions/using-jobs/running-jobs-in-a-container)
