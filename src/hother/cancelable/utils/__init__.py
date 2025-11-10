"""
Utility modules for the async cancellation system.

This module provides helper functions, decorators, bridges, and testing tools:

- **decorators**: The `@cancelable` decorator and variants for easy function decoration
- **anyio_bridge**: Bridge for integrating with anyio-based async code from threads
- **threading_bridge**: Thread-safe registry and utilities for cross-thread cancellation
- **context_bridge**: Context variable propagation across thread boundaries
- **streams**: Utilities for cancellable async stream processing
- **logging**: Structured logging helpers for cancellation events
- **testing**: Test utilities, fixtures, and helpers for testing cancellable operations

Example:
    ```python
    from hother.cancelable.utils.decorators import cancelable, with_timeout

    @cancelable
    async def fetch_data(url: str):
        # Function is now automatically cancellable
        return await http_get(url)

    @with_timeout(5.0)
    async def quick_operation():
        # Automatically times out after 5 seconds
        return await slow_api_call()
    ```
"""
