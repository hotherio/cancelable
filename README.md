# Cancelable

[![PyPI version](https://img.shields.io/pypi/v/hother-cancelable?color=brightgreen)](https://pypi.org/project/hother-cancelable/)
[![Python Versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/hother-cancelable/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/hotherio/cancelable/actions/workflows/test.yaml/badge.svg?branch=main)](https://github.com/hotherio/cancelable/actions/workflows/test.yaml)
[![Coverage](https://codecov.io/gh/hotherio/cancelable/branch/main/graph/badge.svg)](https://codecov.io/gh/hotherio/cancelable)

A comprehensive, production-ready async cancellation system for Python 3.12+ using anyio.

<div align="center">
  <a href="https://hotherio.github.io/cancelable/">📚 Documentation</a>
</div>

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Integrations](#integrations)
- [Documentation](#documentation)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Multiple Cancellation Sources**: Timeout, manual tokens, OS signals, and custom conditions
- **Composable Design**: Combine multiple cancellation sources easily
- **Stream Processing**: Built-in support for cancelable async iterators
- **Operation Tracking**: Full lifecycle tracking with status and progress reporting
- **Library Integrations**: Ready-to-use FastAPI integration for request cancellation
- **Type Safe**: Full type hints and runtime validation with Pydantic
- **Production Ready**: Comprehensive error handling, logging, and performance optimized

## Installation

### Core Installation

The core library includes only essential dependencies (`anyio` and `pydantic`):

```bash
uv add hother-cancelable
```

### Optional Extras

Cancelable provides optional extras for various integrations and use cases:

#### Available Extras

| Extra | Dependencies | Purpose |
|-------|-------------|---------|
| `fastapi` | fastapi | FastAPI middleware for request cancellation |
| `examples` | google-genai, pynput, psutil | Run example scripts and demonstrations |

### Installing with Extras

**FastAPI integration:**
```bash
uv add "hother-cancelable[fastapi]"
```

**Examples:**
```bash
uv add "hother-cancelable[examples]"
```

**All extras:**
```bash
uv add "hother-cancelable[fastapi,examples]"
```

## Quick Start

### Basic Usage

```python
from hother.cancelable import Cancelable

# Timeout-based cancellation
async with Cancelable.with_timeout(30.0) as cancel:
    result = await long_running_operation()

# Manual cancellation with token
from hother.cancelable import CancellationToken

token = CancellationToken()

async with Cancelable.with_token(token) as cancel:
    # In another task/thread: await token.cancel()
    result = await interruptible_operation()
```

### Stream Processing

```python
# Cancelable stream processing
async with Cancelable.with_timeout(60.0) as cancel:
    async for item in cancel.stream(data_source(), report_interval=100):
        await process_item(item)
```

### Function Decorators

```python
from hother.cancelable import cancelable

@cancelable(timeout=30.0, register_globally=True)
async def process_data(data: list, cancelable: Cancelable = None):
    for i, item in enumerate(data):
        await cancelable.report_progress(f"Processing item {i+1}/{len(data)}")
        await process_item(item)
```

## Integrations

Cancelable provides seamless integration with FastAPI. See the [integrations documentation](docs/integrations/) for detailed guides and examples.

- **FastAPI**: Add cancellation middleware to FastAPI applications with automatic request-scoped cancellation

## Documentation

To build and serve the documentation locally:

1. Install the documentation dependencies:

```bash
uv sync --group doc
source .venv/bin/activate
```

2. Serve the documentation:

```bash
mkdocs serve
```

## Development

### Dependency Groups

Cancelable uses dependency groups for development and documentation:

| Group | Purpose | Key Dependencies |
|-------|---------|------------------|
| `dev` | Development tools | pytest, ruff, basedpyright, twine, git-cliff |
| `doc` | Documentation building | mkdocs, mkdocs-material, mike |

### Installation

**Basic development setup:**
```bash
uv sync --group dev
source .venv/bin/activate
lefthook install
```

This creates a virtual environment, installs all development dependencies, and installs the library in editable mode. It also sets up Lefthook git hooks.

**Full development setup with extras:**

Some tests and examples require optional extras. To run the full test suite:

```bash
# Install dev tools + all extras
uv sync --group dev --all-extras
```

**Selective installation:**
```bash
# Install with specific extras
uv sync --group dev --extra fastapi --extra examples

# Install documentation tools
uv sync --group doc
```

### Quick Reference

**Available extras:**
- `fastapi` - FastAPI middleware
- `examples` - Example scripts

**Available groups:**
- `dev` - Development tools (pytest, ruff, basedpyright, etc.)
- `doc` - Documentation tools (mkdocs, mkdocs-material, etc.)

### Git Hooks with Lefthook

This project uses Lefthook for managing git hooks. Hooks are automatically installed when you run `make install-dev`.

To run hooks manually:
```
# Run all pre-commit hooks
lefthook run pre-commit
```

### Tests

**Run core tests (without integration extras):**
```bash
uv run pytest
```

Integration tests that require optional dependencies (fastapi) will be automatically skipped if the extras are not installed.

**Run all tests including integrations:**
```bash
# First install all extras
uv sync --all-extras

# Then run tests
uv run pytest
```

**Run specific test categories:**
```bash
# Run only unit tests
uv run pytest tests/unit

# Run only integration tests (requires extras)
uv run pytest tests/integration
```

### Coverage

```bash
uv run pytest --cov=hother.cancelable
```

### Building the package

```
uv build
```

### Release process

This project uses Git tags for versioning with automatic semantic versioning based on conventional commits. Version numbers are automatically derived from Git tags using hatch-vcs.

#### Quick Release Commands

```bash
# Check current version
hatch version

# Create development release (v1.0.0 → v1.0.1-dev1)
hatch release dev

# Create release candidate (v1.0.1-dev1 → v1.0.1rc1)
hatch release rc

# Create final release (v1.0.1rc1 → v1.0.1)
hatch release final
```

#### Release from Specific Commit

You can optionally specify a commit SHA to create a release from:
```bash
# Release from a specific commit
hatch release dev abc123
hatch release rc def456
hatch release final 789xyz
```

The SHA must be:
- Reachable from HEAD (on current branch history)
- Not already included in a previous release

#### How it Works

- **Development releases** (`dev`): Increments patch version and adds `-dev` suffix
- **Release candidates** (`rc`): Removes `-dev` and adds `rc` suffix
- **Final releases** (`final`): Uses git-cliff to analyze commits and automatically bumps major/minor/patch based on conventional commits

The release process:
1. Analyzes commit history (for final releases)
2. Calculates the next version number
3. Creates and pushes the git tag
4. GitHub Actions automatically builds and publishes the release

#### Manual Tagging (Advanced)

If needed, you can still create tags manually:
```bash
# Manual tag creation
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3
```

### Changelog Management

This project uses [git-cliff](https://git-cliff.org/) to automatically generate changelogs from conventional commits.

```
# Generate/update CHANGELOG.md
make changelog

# Preview unreleased changes
make changelog-unreleased

# Get changelog for latest tag (used in releases)
make changelog-tag
```

The changelog is automatically updated and included in GitHub releases when you push a version tag.

Generate the licenses:
```
uv run pip-licenses --from=mixed --order count -f md --output-file licenses.md
uv run pip-licenses --from=mixed --order count -f csv --output-file licenses.csv
```

Build the new documentation:
```
uv run mike deploy --push --update-aliases <version> latest
uv run mike set-default latest
uv run mike list
```
Checking the documentation locally
```
uv run mike serve
```


## Development practices

### Branching & Pull-Requests

Each git branch should have the format `<tag>/item_<id>` with eventually a descriptive suffix.

We us a **Squash & Merge** approach.

### Conventional Commits

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

Format: `<type>(<scope>): <subject>`

`<scope>` is optional

#### Example

```
feat: add hat wobble
^--^  ^------------^
|     |
|     +-> Summary in present tense.
|
+-------> Type: chore, docs, feat, fix, refactor, style, or test.
```

More Examples:

- `feat`: (new feature for the user, not a new feature for build script)
- `fix`: (bug fix for the user, not a fix to a build script)
- `docs`: (changes to the documentation)
- `style`: (formatting, missing semi colons, etc; no production code change)
- `refactor`: (refactoring production code, eg. renaming a variable)
- `test`: (adding missing tests, refactoring tests; no production code change)
- `chore`: (updating grunt tasks etc; no production code change)
- `build`: (changes in the build system)
- `ci`: (changes in the CI/CD and deployment pipelines)
- `perf`: (significant performance improvement)
- `revert`: (revert a previous change)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on how to get started.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
