"""
Integration modules for popular async libraries and frameworks.

This module provides seamless integration with popular Python async frameworks:

- **FastAPI**: Middleware and utilities for request-scoped cancellation in FastAPI applications

Each integration provides framework-specific helpers to make cancellation transparent
and easy to use within that framework's idioms.

Example:
    ```python
    from fastapi import FastAPI
    from hother.cancelable.integrations.fastapi import (
        RequestCancellationMiddleware,
        cancelable_dependency,
    )

    app = FastAPI()
    app.add_middleware(RequestCancellationMiddleware)

    @app.get("/data")
    async def get_data(cancel: Cancelable = Depends(cancelable_dependency)):
        async with cancel:
            return await fetch_data()
    ```
"""
