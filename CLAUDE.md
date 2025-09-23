# Cancelable - Async Cancellation System for Python

## Overview

Cancelable is a comprehensive async cancellation system for Python streams, providing unified cancellation handling from multiple sources including timeouts, tokens, signals, and conditions.

## Project Structure

```
cancelable/
├── src/cancelable/          # Main package source
│   ├── core/               # Core cancellation functionality
│   ├── sources/            # Cancellation sources (timeout, signal, condition)
│   ├── integrations/       # Third-party integrations (httpx, FastAPI, SQLAlchemy)
│   ├── streaming/          # Stream processing with cancellation
│   └── utils/              # Utilities and helpers
├── tests/                  # Test suite
├── docs/                   # Documentation
└── examples/               # Usage examples
```

## Key Components

### Core Classes
- **Cancellable**: Main context manager for cancellation
- **CancellationToken**: Token-based cancellation mechanism
- **OperationRegistry**: Global registry for tracking operations
- **CancellationSource**: Base class for cancellation sources

### Cancellation Sources
- **TimeoutSource**: Timeout-based cancellation
- **SignalSource**: Unix signal-based cancellation
- **ConditionSource**: Custom condition-based cancellation
- **TokenSource**: Token-based cancellation

## Development Commands

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/unit/test_cancellable.py -v

# Run with coverage
uv run pytest --cov=cancelable
```

### Linting & Formatting
```bash
# Run linter
uv run ruff check src

# Fix linting issues automatically
uv run ruff check --fix src

# Type checking
uv run mypy src
```

### Documentation
```bash
# Serve documentation locally
uv run mkdocs serve

# Deploy documentation
uv run mike deploy --update-aliases 0.1 latest
```

## Important Notes

1. **Import Structure**: The package was transformed from `forge.utils.async_utils` to `cancelable`. All imports should use the new structure.

2. **Test Fixtures**: Tests use pytest with anyio backend. The `clean_registry` fixture ensures a clean OperationRegistry for each test.

3. **Async Context Manager**: The Cancellable class is an async context manager that properly handles CancelledError propagation.

4. **Dependencies**: 
   - anyio for async operations
   - pydantic for models
   - structlog for logging
   - httpx, FastAPI, SQLAlchemy for integrations

## Common Issues & Solutions

1. **CancelledError not propagating**: Ensure the `__aexit__` method returns `False` to propagate exceptions.

2. **Test failures with pytest-anyio**: Use `pytest.raises(anyio.get_cancelled_exc_class())` instead of custom assert helpers for cancellation tests.

3. **Hierarchy parser**: The parser skips the root folder when it has no tree decorators (first line without ├, └, or │).

## CI/CD

The project uses GitHub Actions for CI/CD with:
- Testing on Python 3.12 and 3.13
- Linting with ruff
- Type checking with mypy
- Documentation deployment with mike

## Release Process

1. Update version in pyproject.toml
2. Run tests and ensure all pass
3. Build and publish to PyPI
4. Deploy documentation