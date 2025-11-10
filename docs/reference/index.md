# API Reference

Welcome to the complete API reference for the Cancelable library. All documentation is automatically generated from code docstrings.

## Navigation

The API reference is organized into the following sections:

### [Core Components](core.md)

The fundamental building blocks for async cancellation:

- **Cancelable** - Main context manager for cancellable operations
- **CancellationToken** - Thread-safe token for manual cancellation
- **LinkedCancellationToken** - Combine multiple cancellation tokens
- **OperationContext** - Track operation state and metadata
- **OperationStatus** - Operation state enumeration
- **OperationRegistry** - Global operation tracking
- **Exceptions** - All cancellation-related exceptions

### [Cancellation Sources](sources.md)

Different ways to trigger cancellation:

- **CancellationSource** - Base class for all sources
- **TimeoutSource** - Time-based cancellation
- **SignalSource** - Unix signal-based cancellation (SIGTERM, SIGINT, etc.)
- **ConditionSource** - Predicate-based cancellation
- **TokenSource** - Token-based cancellation
- **CompositeCancellationSource** - Combine multiple sources

### [Integrations](integrations.md)

Framework and library integrations:

- **FastAPI** - Middleware and utilities for FastAPI applications

### [Utilities](utilities.md)

Helper functions, decorators, bridges, and testing tools:

- **Decorators** - `@cancelable` decorator for easy cancellation
- **Bridges** - AnyIO, threading, and context bridges
- **Streams** - Cancellable async stream processing
- **Streaming Simulator** - Testing and demonstration tools
- **Logging** - Structured logging utilities
- **Testing** - Test utilities and fixtures

## Quick Links

- [Getting Started Guide](../getting_started.md)
- [Usage Patterns](../patterns.md)
- [Examples](../examples/index.md)