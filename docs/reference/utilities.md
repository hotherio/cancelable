# Utilities

Utility modules providing helper functions, decorators, bridges, and testing tools.

## Decorators

The `@cancelable` decorator for easily making functions cancellable.

::: hother.cancelable.utils.decorators
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Bridges

### AnyIO Bridge

Bridge for integrating with anyio-based async code.

::: hother.cancelable.utils.anyio_bridge
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### Threading Bridge

Bridge for canceling operations from threads.

::: hother.cancelable.utils.threading_bridge
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### Context Bridge

Context propagation utilities.

::: hother.cancelable.utils.context_bridge
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Stream Processing

Utilities for cancellable async stream processing.

::: hother.cancelable.utils.streams
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Streaming Simulator

Stream cancellation simulator for testing and demonstration.

::: hother.cancelable.streaming.simulator.simulator
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Logging

Structured logging utilities for cancellation events.

::: hother.cancelable.utils.logging
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Testing

Test utilities and fixtures for cancellable operations.

::: hother.cancelable.utils.testing
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true
