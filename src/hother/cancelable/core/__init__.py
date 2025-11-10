"""
Core components of the async cancellation system.

This module provides the fundamental building blocks for cancellable async operations:

- **Cancelable**: Main context manager for creating cancellable operations
- **CancellationToken**: Thread-safe token for manual cancellation control
- **LinkedCancellationToken**: Combines multiple tokens for coordinated cancellation
- **OperationContext**: Tracks state, timing, and metadata of operations
- **OperationRegistry**: Global registry for tracking and managing all active operations
- **Exceptions**: All cancellation-related exception classes

Example:
    ```python
    from hother.cancelable.core import Cancelable

    async with Cancelable.with_timeout(30.0, name="api_call") as cancel:
        result = await make_api_call()
    ```
"""
