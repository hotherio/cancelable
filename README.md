# Cancelable

A comprehensive, production-ready async cancellation system for Python 3.12+ using anyio.

## Features

- **Multiple Cancellation Sources**: Timeout, manual tokens, OS signals, and custom conditions
- **Composable Design**: Combine multiple cancellation sources easily
- **Stream Processing**: Built-in support for cancellable async iterators
- **Operation Tracking**: Full lifecycle tracking with status and progress reporting
- **Library Integrations**: Ready-to-use integrations for httpx, FastAPI, and SQLAlchemy
- **Type Safe**: Full type hints and runtime validation with Pydantic
- **Production Ready**: Comprehensive error handling, logging with structlog, and performance optimized

## Installation

```bash
uv add hother-cancelable
```

## Quick Start

### Basic Usage

```python
from hother.cancelable import Cancellable

# Timeout-based cancellation
async with Cancellable.with_timeout(30.0) as cancel:
    result = await long_running_operation()

# Manual cancellation with token
from hother.cancelable import CancellationToken

token = CancellationToken()

async with Cancellable.with_token(token) as cancel:
    # In another task/thread: await token.cancel()
    result = await interruptible_operation()
```

### Stream Processing

```python
# Cancellable stream processing
async with Cancellable.with_timeout(60.0) as cancel:
    async for item in cancel.stream(data_source(), report_interval=100):
        await process_item(item)
```

### Function Decorators

```python
from hother.cancelable import cancellable

@cancellable(timeout=30.0, register_globally=True)
async def process_data(data: list, cancellable: Cancellable = None):
    for i, item in enumerate(data):
        await cancellable.report_progress(f"Processing item {i+1}/{len(data)}")
        await process_item(item)
```

## Documentation

To build and serve the documentation locally:

1. Install the dependencies:
```
uv sync --group doc
source .venv/bin/activate
```

2. Serve the documentation:
```
mkdocs serve
```

## Development

### Installation

The only command that should be necessary is:
```
uv sync --group dev
source .venv/bin/activate
lefthook install
```

It creates a virtual environment, install all dependencies required for development and install the library in editable mode.
It also installs the Lefthook git hooks manager.

### Git Hooks with Lefthook

This project uses Lefthook for managing git hooks. Hooks are automatically installed when you run `make install-dev`.

To run hooks manually:
```
# Run all pre-commit hooks
lefthook run pre-commit
```

### Tests

uv run -m pytest

### Coverage

uv run python -m pytest src --cov=cancelable

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
