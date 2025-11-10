# Core Components

The core components provide the fundamental building blocks for async cancellation in Python.

## Cancelable

The main context manager for cancellable operations.

::: hother.cancelable.core.cancelable.Cancelable
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Cancellation Tokens

### CancelationToken

Thread-safe token for manual cancellation.

::: hother.cancelable.core.token.CancelationToken
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### LinkedCancelationToken

Token that combines multiple cancellation tokens.

::: hother.cancelable.core.token.LinkedCancelationToken
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Models and Status

### OperationContext

Tracks the state and metadata of a cancellable operation.

::: hother.cancelable.core.models.OperationContext
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### OperationStatus

Enumeration of possible operation states.

::: hother.cancelable.core.models.OperationStatus
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### CancelationReason

Enumeration of cancellation reason categories.

::: hother.cancelable.core.models.CancelationReason
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Registry

### OperationRegistry

Global registry for tracking active cancellable operations.

::: hother.cancelable.core.registry.OperationRegistry
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Exceptions

All exception classes used by the cancellation system.

::: hother.cancelable.core.exceptions
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true
