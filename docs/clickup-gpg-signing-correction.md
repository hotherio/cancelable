# Commit and Tag Signing with python-semantic-release

## Critical Finding: GPG + Docker PSR = Not Possible

**Important:** GPG signing does **NOT** work with the python-semantic-release Docker action because:
1. The Docker container does not have GPG installed (only git and openssh-client)
2. The PSR action only supports SSH signing parameters, not GPG
3. Docker container isolation prevents access to host GPG agent

**Solution:** Use SSH signing with Docker-based PSR (recommended) or run PSR directly on the host for GPG signing.

---

## Overview

Python-semantic-release supports signing through:
- **SSH signing** - Works with Docker action (recommended)
- **GPG signing** - Only works when running PSR directly on the host (not in Docker)

---

## SSH Signing with Docker Action (RECOMMENDED)

This is the correct approach for signed commits/tags with Docker-based PSR.

### Setup Steps

1. **Generate SSH signing key pair:**
   ```bash
   ssh-keygen -t ed25519 -f hother_signing_key -N "" -C "github-bot@hother.io"
   ```

2. **Add SSH public key to GitHub:**
   - Go to: Settings → SSH and GPG keys → New SSH key
   - Select "Signing Key" as key type
   - Paste public key content
   - Title: "HOTHER_BOT Signing Key"

3. **Add secrets to GitHub repository:**
   - `SSH_PRIVATE_SIGNING_KEY`: Content of private key file
   - `SSH_PUBLIC_SIGNING_KEY`: Content of public key file (.pub)

### Workflow Configuration

```yaml
- name: Checkout code
  uses: actions/checkout@v5
  with:
    fetch-depth: 0
    token: ${{ secrets.GITHUB_TOKEN }}

- name: Configure Git
  run: |
    git config user.email "github-bot@hother.io"
    git config user.name "Hother Bot"
    git config core.autocrlf false

- name: Python Semantic Release
  id: release
  uses: python-semantic-release/python-semantic-release@v10.5.3
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    git_committer_name: "Hother Bot"
    git_committer_email: "github-bot@hother.io"
    ssh_public_signing_key: ${{ secrets.SSH_PUBLIC_SIGNING_KEY }}
    ssh_private_signing_key: ${{ secrets.SSH_PRIVATE_SIGNING_KEY }}

- name: Publish to PyPI
  if: steps.release.outputs.released == 'true'
  uses: pypa/gh-action-pypi-publish@release/v1
```

**How it works:**
1. SSH keys added to GitHub as signing keys
2. PSR Docker action receives SSH keys via secrets
3. Container uses openssh-client (already installed) to sign commits/tags
4. GitHub verifies signatures and shows "Verified" badge

---

## GPG Signing (NOT with Docker)

If you absolutely need GPG signing, you must run PSR directly on the GitHub runner (not in a Docker container).

### When to use this approach:
- GPG keys already established and required
- Cannot migrate to SSH signing
- Willing to give up Docker action benefits

### Workflow Configuration

```yaml
- name: Checkout code
  uses: actions/checkout@v5
  with:
    fetch-depth: 0
    token: ${{ secrets.GITHUB_TOKEN }}

- name: Import GPG key
  uses: crazy-max/ghaction-import-gpg@v6
  with:
    gpg_private_key: ${{ secrets.HOTHER_BOT_GPG_KEY }}
    passphrase: ${{ secrets.HOTHER_BOT_GPG_PASSPHRASE }}
    git_user_signingkey: true
    git_commit_gpgsign: true
    git_tag_gpgsign: true

- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.13'

- name: Install python-semantic-release
  run: pip install python-semantic-release

- name: Configure Git
  run: |
    git config user.email "github-bot@hother.io"
    git config user.name "Hother Bot"

- name: Run Semantic Release
  run: semantic-release version
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Why this works:**
- Runs directly on GitHub runner (not in Docker)
- GPG is pre-installed on GitHub runners
- `crazy-max/ghaction-import-gpg` configures GPG
- Full access to GPG agent on the host

---

## Comparison: SSH vs GPG vs Unsigned

| Feature | SSH (Docker) | GPG (Direct) | Unsigned |
|---------|--------------|--------------|----------|
| **Uses Docker action** | ✅ Yes | ❌ No | ✅ Yes |
| **Setup complexity** | Low | Medium | Lowest |
| **Key expiration** | ❌ No | ✅ Yes | N/A |
| **Key revocation** | ❌ No | ✅ Yes | N/A |
| **GitHub verified badge** | ✅ | ✅ | ❌ |
| **Key management** | Simpler | More complex | None |
| **Performance** | Slower (Docker) | Faster (Direct) | Slower (Docker) |

---

## Why GPG Doesn't Work with Docker PSR

### Technical Explanation

1. **Missing GPG binary in container:**
   - PSR Dockerfile installs: git, git-lfs, openssh-client, build tools
   - Notably missing: gnupg, gnupg2
   - Error: `error: cannot run gpg: No such file or directory`

2. **PSR action only supports SSH:**
   - From [action.yml](https://github.com/python-semantic-release/python-semantic-release/blob/master/action.yml):
     - `ssh_public_signing_key` ✅
     - `ssh_private_signing_key` ✅
     - No GPG parameters ❌

3. **Container isolation:**
   - Even if Git config is mounted, GPG binary isn't in container
   - Would require: mounting ~/.gnupg, setting GNUPGHOME, handling UID/GID
   - PSR Docker action doesn't expose these mount options

### Common Misconception

**Myth:** "GitHub Actions automatically mounts Git config to Docker containers, so GPG should work."

**Reality:** While Git *config* may be mounted, the GPG *binary* and *agent* are not accessible inside the container. The PSR Docker image simply doesn't include GPG.

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
2. **SSH signing IS the solution** for Docker-based PSR
3. **SSH advantages:**
   - Works with Docker action out of the box
   - Simpler key management (no expiration)
   - Same "Verified" badge on GitHub
   - Modern, well-supported approach
4. **If GPG is required:**
   - Must run PSR directly on runner (not Docker)
   - Slower setup but GPG works perfectly
5. **Docker action benefits preserved with SSH:**
   - Consistent environment
   - Official supported approach
   - No custom Python/dependency setup

---

## References

- [PSR GitHub Actions Documentation](https://python-semantic-release.readthedocs.io/en/latest/configuration/automatic-releases/github-actions.html)
- [PSR commit adding SSH signing](https://github.com/python-semantic-release/python-semantic-release/commit/31ad5eb5a25f0ea703afc295351104aefd66cac1)
- [GitHub Docs: SSH Signing](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification#ssh-commit-signature-verification)
- [PSR action.yml](https://github.com/python-semantic-release/python-semantic-release/blob/master/action.yml)
