# Cancelable - Async Cancellation System for Python

## Overview

Cancelable is a comprehensive async cancellation system for Python, providing unified cancellation handling from multiple sources including timeouts, tokens, signals, and conditions. It enables graceful cancellation of async operations with automatic propagation through operation hierarchies.

**Key Design**: Provider-agnostic cancellation that works across anyio/asyncio backends with support for threads, signals, and custom conditions.

**Namespace Package**: This is under the `hother` namespace. Install with `pip install hother-cancelable` and import as `from hother.cancelable import ...`.

## Development Commands

### Core Tasks
```bash
# Install dependencies (use --group dev --group doc for all tools)
uv sync --all-extras

# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=hother.cancelable --cov-report=html

# Serve documentation locally
uv sync --group doc  # First time only
uv run mkdocs serve  # Visit http://localhost:1234

# Lint and format
uv run ruff check src
uv run ruff check --fix src
```

### Testing Commands
```bash
# Run specific test file
uv run pytest tests/unit/test_cancelable.py -v

# Run specific test function
uv run pytest tests/unit/test_cancelable.py::test_basic_cancellation -v

# Run with output (useful for debugging)
uv run pytest tests/unit/test_cancelable.py -v -s

# Run integration tests only
uv run pytest tests/integration/ -v

# Run unit tests only
uv run pytest tests/unit/ -v

# Run streaming tests
uv run pytest tests/streaming/ -v

# Run with markers
uv run pytest -m "not slow" -v

# Watch mode (requires pytest-watch)
uv run ptw tests/unit/
```

### Running Examples
```bash
# Basic examples
uv run python examples/01_basics/01_basic_cancellation.py
uv run python examples/01_basics/02_timeout_cancellation.py

# Integration examples
uv run python examples/03_integrations/04_fastapi_example.py

# Run with proper module path
uv run python -m examples.01_basics.01_basic_cancellation
```

### Linting & Type Checking
```bash
# Ruff linting
uv run ruff check src tests examples

# Auto-fix issues
uv run ruff check --fix src tests examples

# Type checking with basedpyright
uv run basedpyright src

# Format code
uv run ruff format src tests examples
```

### Documentation
```bash
# Build documentation
uv run mkdocs build

# Serve locally with live reload
uv run mkdocs serve --dev-addr 0.0.0.0:1234

# Deploy with versioning
uv run mike deploy --update-aliases 0.1 latest

# Set default version
uv run mike set-default latest
```

## Project Architecture

### Cancellation Flow Model

The cancellation system follows this propagation model:

```
CancellationSource → CancellationToken → Cancelable → Child Operations
     (trigger)           (propagate)       (execute)      (auto-cancel)
```

**Key Concepts:**

1. **Sources trigger cancellation**: TimeoutSource, SignalSource, ConditionSource, or manual token.cancel()
2. **Tokens propagate**: LinkedCancellationToken connects multiple tokens, cancellation flows to all linked tokens
3. **Cancelable executes**: Raises anyio.CancelledError in the async context
4. **Children inherit**: Child operations automatically cancel when parent cancels

### Core Components

#### `Cancelable[T]` - Main Context Manager
The primary entry point for cancellable operations.

**Entry Points:**
- `async with Cancelable(name="op") as cancel:` - Basic usage
- `Cancelable.with_timeout(seconds, name="op")` - With timeout source
- `Cancelable.with_token(token, name="op")` - With existing token
- `Cancelable.with_signal(signal.SIGTERM, name="op")` - With signal handling
- `Cancelable.combine([source1, source2], name="op")` - Multiple sources

**Key Methods:**
- `await report_progress(message, metadata)` - Report operation progress
- `shield()` - Shield section from cancellation (for cleanup)
- `on_cancel(callback)` - Register cancellation callback
- `on_progress(callback)` - Register progress callback
- `combine(other)` - Combine with another Cancelable

**Properties:**
- `context: OperationContext` - Operation state, status, timing
- `token: CancellationToken` - Associated token (may be LinkedCancellationToken)

#### `CancellationToken` - Token-Based Cancellation
Thread-safe token for manual cancellation.

**Key Methods:**
- `await cancel(message="reason")` - Cancel from async context
- `cancel_sync(message="reason")` - Cancel from sync/thread context
- `is_cancelled: bool` - Check if cancelled
- `on_cancel(callback)` - Register callback

**Linking Pattern:**
```python
# LinkedCancellationToken combines multiple tokens
token1 = CancellationToken()
token2 = CancellationToken()
linked = LinkedCancellationToken([token1, token2])
# Cancelling either token1 or token2 cancels linked
```

#### `OperationRegistry` - Global Tracking
Tracks all active operations globally.

**Key Methods:**
- `register(context)` - Register operation
- `unregister(operation_id)` - Remove operation
- `get(operation_id)` - Get operation context
- `list_active()` - List all active operations
- `cancel_all()` - Emergency cancel all operations

**Thread-Safe Variant:**
- `ThreadSafeRegistry` - For cross-thread operation tracking

#### Cancellation Sources

**`TimeoutSource(timeout: float)`**
- Cancels after specified seconds
- Uses anyio's move_on_after internally

**`SignalSource(*signals)`**
- Cancels on Unix signals (SIGTERM, SIGINT, etc.)
- Thread-safe signal handling
- Platform-specific (Unix only)

**`ConditionSource(predicate, check_interval=1.0)`**
- Polls predicate function
- Cancels when predicate returns True
- Useful for resource monitoring, stop flags

**`TokenSource(token)`**
- Wraps existing CancellationToken
- Used internally for token-based cancellation

### Context Manager Lifecycle

```python
async with Cancelable(name="op") as cancel:
    # __aenter__:
    # 1. Creates OperationContext
    # 2. Registers with OperationRegistry
    # 3. Starts cancellation sources
    # 4. Sets _current_operation context var

    await do_work()  # Your code

    # __aexit__:
    # 1. Stops cancellation sources
    # 2. Updates context (completed/cancelled)
    # 3. Unregisters from registry
    # 4. Returns False (propagates exceptions)
```

**Critical**: `__aexit__` returns `False` to ensure `CancelledError` propagates. This is required for proper async cancellation.

### Integration Patterns

**FastAPI**:
```python
from hother.cancelable.integrations.fastapi import RequestCancellationMiddleware

app.add_middleware(RequestCancellationMiddleware)
# Automatic per-request cancellation tokens
```

**httpx**:
```python
from hother.cancelable.integrations.httpx import CancelableTransport

async with httpx.AsyncClient(transport=CancelableTransport(cancel)) as client:
    response = await client.get(url)
```

**SQLAlchemy**:
```python
from hother.cancelable.integrations.sqlalchemy import cancelable_session

async with cancelable_session(engine, cancel) as session:
    result = await session.execute(query)
```

## Project Structure

```
cancelable/
├── src/hother/cancelable/      # Namespace package
│   ├── core/
│   │   ├── cancelable.py       # Main Cancelable class
│   │   ├── token.py            # CancellationToken, LinkedCancellationToken
│   │   └── registry.py         # OperationRegistry, ThreadSafeRegistry
│   ├── sources/
│   │   ├── base.py             # CancellationSource ABC
│   │   ├── timeout.py          # TimeoutSource
│   │   ├── signal.py           # SignalSource
│   │   ├── condition.py        # ConditionSource
│   │   ├── token.py            # TokenSource
│   │   └── composite.py        # CompositeCancellationSource
│   ├── integrations/
│   │   ├── fastapi.py          # FastAPI middleware
│   │   ├── httpx.py            # httpx transport
│   │   ├── sqlalchemy.py       # SQLAlchemy session
│   │   └── tenacity.py         # Retry integration
│   ├── streaming/
│   │   └── simulator.py        # Stream cancellation simulator
│   └── utils/
│       ├── decorators.py       # @cancelable decorator
│       ├── anyio_bridge.py     # Anyio context bridge
│       ├── threading_bridge.py # Thread cancellation bridge
│       ├── streams.py          # Cancelable stream utilities
│       ├── logging.py          # Structured logging
│       └── testing.py          # Test utilities
├── tests/
│   ├── unit/                   # Unit tests by component
│   ├── integration/            # Integration tests (fastapi, httpx, sqlalchemy)
│   ├── streaming/              # Stream processing tests
│   └── test_sources/           # Cancellation source tests
├── examples/
│   ├── 01_basics/              # Basic patterns (4 examples)
│   ├── 02_advanced/            # Advanced patterns (9 examples)
│   ├── 03_integrations/        # Integration examples (6 examples)
│   ├── 04_streams/             # Stream processing
│   ├── 05_monitoring/          # Monitoring dashboard
│   └── 06_llm/                 # LLM streaming
├── docs/
│   ├── .hooks/                 # MkDocs custom hooks (snippets, embedding)
│   ├── examples/               # Example documentation
│   ├── concepts/               # Core concept explanations
│   ├── integrations/           # Integration guides
│   └── advanced/               # Advanced patterns
└── pyproject.toml              # Project config, namespace package
```

## Testing Strategy

### Test Organization

- **`tests/unit/`**: Component-level tests
  - `test_cancelable.py` - Core Cancelable functionality
  - `test_token.py` - Token and LinkedCancellationToken
  - `test_registry.py` - OperationRegistry
  - `test_decorators.py` - @cancelable decorator
  - `test_sources/` - Individual source tests

- **`tests/integration/`**: Integration tests
  - `test_fastapi.py` - FastAPI middleware
  - `test_httpx.py` - HTTP client transport
  - `test_sqlalchemy.py` - Database sessions

- **`tests/streaming/`**: Stream cancellation tests

### Key Test Fixtures

**`clean_registry`** (autouse):
```python
@pytest.fixture(autouse=True)
def clean_registry():
    """Ensures a clean OperationRegistry for each test."""
    registry = OperationRegistry()
    registry.clear()
    yield registry
    registry.clear()
```

**Anyio backend** (pytest.ini):
```ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
anyio_backend = "asyncio"
```

### Testing Patterns

**Testing Cancellation:**
```python
async def test_timeout_cancellation():
    with pytest.raises(anyio.get_cancelled_exc_class()):
        async with Cancelable.with_timeout(0.1, name="test"):
            await anyio.sleep(1.0)  # Will timeout
```

**Testing Context State:**
```python
async def test_operation_completed():
    async with Cancelable(name="test") as cancel:
        await anyio.sleep(0.1)

    assert cancel.context.status == OperationStatus.COMPLETED
    assert cancel.context.duration > 0
```

**Testing Token Cancellation:**
```python
async def test_token_cancel():
    token = CancellationToken()

    async def worker():
        async with Cancelable.with_token(token) as cancel:
            await anyio.sleep(10)

    async def canceller():
        await anyio.sleep(0.1)
        await token.cancel("test")

    with pytest.raises(anyio.get_cancelled_exc_class()):
        async with anyio.create_task_group() as tg:
            tg.start_soon(worker)
            tg.start_soon(canceller)
```

### Coverage Requirements

- **Target**: 100% coverage
- **Use `# pragma: no cover`** only for:
  - Defensive code that's hard to trigger
  - Platform-specific branches
  - Type checking blocks (`if TYPE_CHECKING:`)
- **Coverage report**: `uv run pytest --cov=hother.cancelable --cov-report=html`

## Key Configuration Files

### `pyproject.toml`
- **Namespace package**: `packages = [{include = "hother", from = "src"}]`
- **Optional dependencies**: httpx, sqlalchemy, fastapi, asyncer, examples
- **Dependency groups**: dev (testing/linting), doc (mkdocs)
- **Tool configs**: ruff, basedpyright, pytest, coverage

### `lefthook.yml`
Git hooks for:
- Pre-commit: ruff linting, basedpyright type checking
- Pre-push: tests with coverage

### `mkdocs.yml`
- **Custom hooks**: `docs/.hooks/main.py` (snippet embedding system)
- **Theme**: Material with custom overrides
- **Plugins**: mkdocstrings, social cards, glightbox
- **Watch paths**: src/, examples/, docs/, docs/.hooks/

### `Makefile`
Convenience commands:
- `make install`: Setup dependencies
- `make test`: Run tests
- `make lint`: Run linting
- `make docs`: Serve documentation


## CI/CD

The project uses GitHub Actions for CI/CD:

- **Testing**: Python 3.12 and 3.13 on Ubuntu
- **Linting**: ruff check with auto-fix suggestions
- **Type checking**: basedpyright with strict mode
- **Coverage**: 100% coverage requirement
- **Documentation**: Builds and deploys with mike to GitHub Pages
- **Pre-commit hooks**: lefthook runs on every commit

## Release Process

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md** with release notes
3. **Run full test suite**: `uv run pytest --cov`
4. **Build package**: `uv build`
5. **Test package locally**: `uv pip install dist/hother_cancelable-*.whl`
6. **Publish to PyPI**: `uv publish`
7. **Tag release**: `git tag v0.1.0 && git push --tags`
8. **Deploy docs**: `uv run mike deploy --update-aliases 0.1 latest`
9. **Create GitHub release** with changelog
