# Contributing Guide

Thank you for considering contributing to Cancelable! This guide will help you get started.

## Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a branch** for your changes
4. **Make your changes** with tests
5. **Submit a pull request**

## Development Setup

### Prerequisites

- Python 3.12 or 3.13
- [uv](https://github.com/astral-sh/uv) for dependency management
- Git

### Clone and Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/cancelable.git
cd cancelable

# Sync dependencies
uv sync --all-extras

# Run tests to verify setup
uv run pytest
```

## Development Workflow

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=hother.cancelable

# Run specific test file
uv run pytest tests/unit/test_cancellable.py -v

# Run specific test
uv run pytest tests/unit/test_cancellable.py::test_name -v
```

### Linting and Formatting

```bash
# Run linter
uv run ruff check src

# Fix linting issues automatically
uv run ruff check --fix src

# Type checking
uv run mypy src
```

### Running Examples

```bash
# Basic examples
uv run python examples/01_basics/01_basic_cancelation.py
```

### Documentation

```bash
# Serve documentation locally
uv run mkdocs serve

# Build documentation
uv run mkdocs build

# Deploy with versioning
uv run mike deploy --update-aliases 0.1 latest
```

## Making Changes

### Branching Strategy

- **main** - Stable production code
- **feature/*** - New features
- **fix/*** - Bug fixes
- **docs/*** - Documentation improvements

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add custom cancelation source support
fix: resolve race condition in registry cleanup
docs: improve getting started guide
test: add coverage for signal handling
refactor: simplify token cancelation logic
```

### Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for public APIs
- Keep functions focused and small
- Add comments for complex logic

### Testing Requirements

- **Unit tests** for all new functionality
- **Integration tests** for framework integrations
- **Maintain coverage** above 80%
- **Test edge cases** and error conditions

Example test structure:

```python
import pytest
import anyio
from hother.cancelable import Cancelable

def test_timeout_cancelation():
    """Test that operations timeout correctly."""
    async def main():
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancelable.with_timeout(0.1) as cancel:
                await anyio.sleep(1.0)

    anyio.run(main)
```

## Pull Request Process

### Before Submitting

1. **Run tests** - Ensure all tests pass
2. **Run linter** - Fix all linting issues
3. **Update docs** - Document new features
4. **Add tests** - Cover your changes
5. **Update changelog** - Note your changes (if applicable)

### PR Checklist

- [ ] Tests pass (`uv run pytest`)
- [ ] Linter passes (`uv run ruff check src`)
- [ ] Type checks pass (`uv run mypy src`)
- [ ] Documentation updated
- [ ] Examples added (if applicable)
- [ ] Changelog updated (if applicable)
- [ ] Commit messages follow convention

### PR Title

Follow conventional commits format:

```
feat: add condition-based cancelation source
fix: resolve registry cleanup race condition
docs: add LLM streaming example
```

### PR Description

Include:

- **What** - What does this PR do?
- **Why** - Why is this change needed?
- **How** - How does it work?
- **Testing** - How was it tested?
- **Breaking Changes** - Any breaking changes?

Example:

```markdown
## What

Adds support for custom condition-based cancelation sources.

## Why

Users need to cancel operations based on custom business logic,
not just timeouts or signals.

## How

- Created `ConditionSource` class
- Added predicate function support
- Implemented background monitoring task

## Testing

- Added unit tests for ConditionSource
- Added integration test with resource monitoring
- All existing tests pass

## Breaking Changes

None
```

## Contributing Areas

### Documentation

- **Improve guides** - Make concepts clearer
- **Add examples** - Share real-world use cases
- **Fix typos** - Even small improvements help
- **Add diagrams** - Visual explanations

### Code

- **Bug fixes** - Fix reported issues
- **New features** - Implement requested features
- **Performance** - Optimize hot paths
- **Tests** - Increase coverage

### Examples

- **Real-world patterns** - Share your use cases
- **Framework integrations** - New frameworks
- **Best practices** - Production patterns

## Code of Conduct

Be respectful, inclusive, and constructive. We're all here to learn and improve together.

## Getting Help

- **Discussions** - [GitHub Discussions](https://github.com/hotherio/cancelable/discussions)
- **Issues** - [GitHub Issues](https://github.com/hotherio/cancelable/issues)

## Recognition

All contributors are recognized in:

- GitHub contributors page
- Release notes
- Documentation credits

Thank you for contributing! 🎉

---

**Questions?** Open a [discussion](https://github.com/hotherio/cancelable/discussions) or reach out in an issue.
