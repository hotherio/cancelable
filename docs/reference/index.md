# API Reference

Welcome to the complete API reference for the Cancelable library. All documentation is automatically generated from code docstrings.

## Navigation

The API reference is organized into the following sections:

### [Core Components](core.md)

The fundamental building blocks for async cancelation:

- **Cancelable** - Main context manager for cancellable operations
- **CancelationToken** - Thread-safe token for manual cancelation
- **LinkedCancelationToken** - Combine multiple cancelation tokens
- **OperationContext** - Track operation state and metadata
- **OperationStatus** - Operation state enumeration
- **OperationRegistry** - Global operation tracking
- **Exceptions** - All cancelation-related exceptions

### [Cancelation Sources](sources.md)

Different ways to trigger cancelation:

- **CancelationSource** - Base class for all sources
- **TimeoutSource** - Time-based cancelation
- **SignalSource** - Unix signal-based cancelation (SIGTERM, SIGINT, etc.)
- **ConditionSource** - Predicate-based cancelation
- **TokenSource** - Token-based cancelation
- **CompositeCancelationSource** - Combine multiple sources

### [Integrations](integrations.md)

Framework and library integrations:

- **FastAPI** - Middleware and utilities for FastAPI applications

### [Utilities](utilities.md)

Helper functions, decorators, bridges, and testing tools:

- **Decorators** - `@cancelable` decorator for easy cancelation
- **Bridges** - AnyIO, threading, and context bridges
- **Streams** - Cancellable async stream processing
- **Streaming Simulator** - Testing and demonstration tools
- **Logging** - Structured logging utilities
- **Testing** - Test utilities and fixtures

## Quick Links

- [Getting Started Guide](../getting_started.md)
- [Usage Patterns](../patterns.md)
- [Examples](../examples/index.md)