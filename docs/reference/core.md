# Core Components

The core components provide the fundamental building blocks for async cancelation in Python.

## Cancelable

The main context manager for cancelable operations.

::: hother.cancelable.core.cancelable.Cancelable
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Cancelation Tokens

### CancelationToken

Thread-safe token for manual cancelation.

::: hother.cancelable.core.token.CancelationToken
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### LinkedCancelationToken

Token that combines multiple cancelation tokens.

::: hother.cancelable.core.token.LinkedCancelationToken
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Models and Status

### OperationContext

Tracks the state and metadata of a cancelable operation.

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

Enumeration of cancelation reason categories.

::: hother.cancelable.core.models.CancelationReason
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Registry

### OperationRegistry

Global registry for tracking active cancelable operations.

::: hother.cancelable.core.registry.OperationRegistry
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Exceptions

All exception classes used by the cancelation system.

::: hother.cancelable.core.exceptions
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true
