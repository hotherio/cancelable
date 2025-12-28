# Commit and Tag Signing with python-semantic-release

## Current Implementation: GPG Signing Without Docker

**Implementation:** We are using GPG signing by running python-semantic-release directly on the GitHub runner (not in Docker container).

**Why this approach:**
1. The Docker container does not have GPG installed (only git and openssh-client)
2. The PSR action only supports SSH signing parameters, but SSH signing had libcrypto compatibility issues
3. Running PSR directly on the host allows full GPG functionality with verified signatures

---

## Overview

Python-semantic-release supports signing through:
- **GPG signing** - Works when running PSR directly on the host (current implementation)
- **SSH signing** - Works with Docker action but has libcrypto compatibility issues

---

## GPG Signing Without Docker (CURRENT IMPLEMENTATION)

This is our current approach - running PSR directly on the GitHub runner with GPG signing enabled.

### Workflow Configuration (Currently Used)

```yaml
- name: Checkout code
  uses: actions/checkout@v5
  with:
    fetch-depth: 0
    token: ${{ secrets.GITHUB_TOKEN }}

- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.13'

- name: Install python-semantic-release
  run: pip install python-semantic-release

- name: Import GPG key
  uses: crazy-max/ghaction-import-gpg@v6
  with:
    gpg_private_key: ${{ secrets.HOTHER_BOT_GPG_KEY }}
    passphrase: ${{ secrets.HOTHER_BOT_GPG_PASSPHRASE }}
    git_user_signingkey: true
    git_commit_gpgsign: true
    git_tag_gpgsign: true

- name: Configure Git
  run: |
    git config user.email "github-bot@hother.io"
    git config user.name "Hother Bot"
    git config core.autocrlf false

- name: Run Semantic Release
  id: release
  run: |
    semantic-release version
    if [ $? -eq 0 ]; then
      echo "released=true" >> $GITHUB_OUTPUT
      LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
      echo "tag=$LATEST_TAG" >> $GITHUB_OUTPUT
      VERSION=${LATEST_TAG#v}
      echo "version=$VERSION" >> $GITHUB_OUTPUT
    else
      echo "released=false" >> $GITHUB_OUTPUT
    fi
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- name: Publish to GitHub Release
  if: steps.release.outputs.released == 'true'
  run: semantic-release publish
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

- name: Publish to PyPI
  if: steps.release.outputs.released == 'true'
  uses: pypa/gh-action-pypi-publish@release/v1
```

**Why this works:**
- Runs directly on GitHub runner (not in Docker)
- GPG is pre-installed on GitHub runners
- `crazy-max/ghaction-import-gpg` configures GPG
- Full access to GPG agent on the host

---

## Comparison: GPG vs SSH vs Unsigned

| Feature | GPG (Direct) ✅ Current | SSH (Docker) | Unsigned |
|---------|------------------------|--------------|----------|
| **Uses Docker action** | ❌ No | ✅ Yes | ✅ Yes |
| **Setup complexity** | Medium | Low (but has libcrypto issues) | Lowest |
| **Key expiration** | ✅ Yes | ❌ No | N/A |
| **Key revocation** | ✅ Yes | ❌ No | N/A |
| **GitHub verified badge** | ✅ | ✅ (when working) | ❌ |
| **Key management** | More complex | Simpler | None |
| **Performance** | Faster (Direct) | Slower (Docker) | Slower (Docker) |
| **Compatibility** | ✅ Works | ❌ libcrypto errors | ✅ Works |

---

## Why Neither GPG nor SSH Work Well with Docker PSR

### Technical Explanation

1. **GPG: Missing GPG binary in container**
   - PSR Dockerfile installs: git, git-lfs, openssh-client, build tools
   - Notably missing: gnupg, gnupg2
   - Error: `error: cannot run gpg: No such file or directory`

2. **GPG: PSR action only supports SSH signing parameters**
   - From [action.yml](https://github.com/python-semantic-release/python-semantic-release/blob/master/action.yml):
     - `ssh_public_signing_key` ✅
     - `ssh_private_signing_key` ✅
     - No GPG parameters ❌

3. **SSH: libcrypto compatibility issues**
   - Error: `Error loading key "/github/home/.ssh/signing_key": error in libcrypto`
   - Occurs with both ed25519 and RSA keys
   - Related to OpenSSL version in container vs key format
   - PSR v10.5.3 includes SSH signing fixes but libcrypto errors persist

4. **Container isolation:**
   - Even if Git config is mounted, GPG binary isn't in container
   - SSH key loading has compatibility issues with container's libcrypto
   - Would require specific OpenSSL/libcrypto versions

### Common Misconception

**Myth:** "GitHub Actions automatically mounts Git config to Docker containers, so GPG should work."

**Reality:** While Git *config* may be mounted, the GPG *binary* and *agent* are not accessible inside the container. The PSR Docker image simply doesn't include GPG. SSH signing is supported but has libcrypto compatibility issues.

---

## Troubleshooting

### "error: cannot run gpg: No such file or directory"

**Cause:** Trying to use GPG signing with Docker-based PSR

**Solution:** Switch to SSH signing (see above) or run PSR directly on host

### "Commits not signed" with SSH signing

**Check:**
1. SSH public key added to GitHub as "Signing Key" (not just SSH key)
2. Secrets configured: `SSH_PRIVATE_SIGNING_KEY`, `SSH_PUBLIC_SIGNING_KEY`
3. Both secrets contain the full key content (including headers/footers)

**Verify in workflow logs:**
```bash
# Should see PSR using SSH signing
python-semantic-release version
```

### SSH key not recognized

**Solution:**
- Ensure public key is added to your GitHub account as a **Signing Key**
- Go to: Settings → SSH and GPG keys
- Key type must be "Signing Key" (not "Authentication Key")

---

## Migration Guide: GPG to SSH

If you're currently using GPG and want to migrate to SSH signing:

1. **Generate SSH signing key** (see setup steps above)
2. **Add to GitHub** as signing key
3. **Update workflow:**
   - Remove `crazy-max/ghaction-import-gpg` step
   - Add SSH key parameters to PSR action
4. **Update secrets:**
   - Add `SSH_PUBLIC_SIGNING_KEY`
   - Add `SSH_PRIVATE_SIGNING_KEY`
   - Can remove `GPG_PRIVATE_KEY` and `GPG_PASSPHRASE` (optional)
5. **Test:** Trigger a release and verify "Verified" badge appears

---

## Key Takeaways

1. **GPG + Docker PSR = IMPOSSIBLE** (container lacks GPG binary)
2. **SSH + Docker PSR = PROBLEMATIC** (libcrypto compatibility errors)
3. **GPG without Docker = CURRENT SOLUTION:**
   - Run PSR directly on GitHub runner
   - Full GPG functionality with verified signatures
   - Better performance (no Docker overhead)
   - Proven to work reliably
4. **Trade-offs accepted:**
   - No Docker container isolation for PSR
   - Manual Python/PSR installation in workflow
   - Slightly more complex workflow setup
5. **Benefits achieved:**
   - ✅ Signed commits and tags
   - ✅ "Verified" badge on GitHub
   - ✅ Reliable, consistent releases
   - ✅ Better performance than Docker

---

## References

- [PSR GitHub Actions Documentation](https://python-semantic-release.readthedocs.io/en/latest/configuration/automatic-releases/github-actions.html)
- [PSR commit adding SSH signing](https://github.com/python-semantic-release/python-semantic-release/commit/31ad5eb5a25f0ea703afc295351104aefd66cac1)
- [GitHub Docs: SSH Signing](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification#ssh-commit-signature-verification)
- [PSR action.yml](https://github.com/python-semantic-release/python-semantic-release/blob/master/action.yml)
