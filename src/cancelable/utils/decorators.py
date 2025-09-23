"""
Decorators and convenience functions for async cancellation.
"""

import inspect
from collections.abc import Awaitable, Callable
from datetime import timedelta
from functools import wraps
from typing import TypeVar

from cancelable.core.cancellable import Cancellable, current_operation
from cancelable.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


def cancellable(
    timeout: float | timedelta | None = None,
    operation_id: str | None = None,
    name: str | None = None,
    register_globally: bool = False,
    inject_param: str | None = "cancellable",
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]:
    """
    Decorator to make async function cancellable.

    Args:
        timeout: Optional timeout for the operation
        operation_id: Optional operation ID (auto-generated if not provided)
        name: Optional operation name (defaults to function name)
        register_globally: Whether to register with global registry
        inject_param: Parameter name to inject cancellable (None to disable)

    Returns:
        Decorator function

    Example:
        @cancellable(timeout=30.0, register_globally=True)
        async def my_operation(data: str, cancellable: Cancellable = None):
            await cancellable.report_progress("Starting")
            # ... do work ...
            return result
    """

    def decorator(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> R:
            # Create cancellable
            cancel_kwargs = {
                "operation_id": operation_id,
                "name": name or func.__name__,
                "register_globally": register_globally,
            }

            if timeout:
                cancel = Cancellable.with_timeout(timeout, **cancel_kwargs)
            else:
                cancel = Cancellable(**cancel_kwargs)

            async with cancel:
                # Inject cancellable if requested
                if inject_param:
                    sig = inspect.signature(func)
                    if inject_param in sig.parameters:
                        kwargs[inject_param] = cancel

                # Call the function
                return await func(*args, **kwargs)

        # Add attribute to access decorator parameters
        wrapper._cancellable_params = {
            "timeout": timeout,
            "operation_id": operation_id,
            "name": name or func.__name__,
            "register_globally": register_globally,
        }

        return wrapper

    return decorator


async def with_timeout(
    timeout: float | timedelta,
    coro: Awaitable[T],
    operation_id: str | None = None,
    name: str | None = None,
) -> T:
    """
    Run coroutine with timeout.

    Args:
        timeout: Timeout duration
        coro: Coroutine to run
        operation_id: Optional operation ID
        name: Optional operation name

    Returns:
        Result from coroutine

    Raises:
        CancelledError: If operation times out

    Example:
        result = await with_timeout(5.0, fetch_data())
    """
    cancellable = Cancellable.with_timeout(
        timeout,
        operation_id=operation_id,
        name=name,
    )

    async with cancellable:
        return await coro


def with_current_operation() -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]:
    """
    Decorator that injects current operation into function.

    The function must have a parameter named 'operation' or specify
    a different parameter name.

    Example:
        @with_current_operation()
        async def process_item(item: str, operation: Cancellable = None):
            if operation:
                await operation.report_progress(f"Processing {item}")
            return item.upper()
    """

    def decorator(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> R:
            operation = current_operation()

            # Inject operation if function accepts it
            sig = inspect.signature(func)
            if "operation" in sig.parameters and "operation" not in kwargs:
                kwargs["operation"] = operation

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def cancellable_method(
    timeout: float | timedelta | None = None,
    name: str | None = None,
    register_globally: bool = False,
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]:
    """
    Decorator for async methods that should be cancellable.

    Similar to @cancellable but designed for class methods.

    Example:
        class DataProcessor:
            @cancellable_method(timeout=60.0)
            async def process(self, data: list, cancellable: Cancellable = None):
                for item in data:
                    await self._process_item(item)
                    await cancellable.report_progress(f"Processed {item}")
    """

    def decorator(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @wraps(func)
        async def wrapper(self, *args, **kwargs) -> R:
            # Get method name including class
            method_name = f"{self.__class__.__name__}.{func.__name__}"

            cancel_kwargs = {
                "name": name or method_name,
                "register_globally": register_globally,
            }

            if timeout:
                cancel = Cancellable.with_timeout(timeout, **cancel_kwargs)
            else:
                cancel = Cancellable(**cancel_kwargs)

            async with cancel:
                # Inject cancellable
                sig = inspect.signature(func)
                if "cancellable" in sig.parameters:
                    kwargs["cancellable"] = cancel

                return await func(self, *args, **kwargs)

        return wrapper

    return decorator
