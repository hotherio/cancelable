"""
Decorators and convenience functions for async cancelation.
"""

import inspect
from collections.abc import Awaitable, Callable
from datetime import timedelta
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from hother.cancelable.core.cancelable import Cancelable, current_operation
from hother.cancelable.utils.logging import get_logger

if TYPE_CHECKING:
    from hother.cancelable.core.token import CancelationToken

logger = get_logger(__name__)

P = ParamSpec("P")  # For preserving function signatures
T = TypeVar("T")
R = TypeVar("R")


def cancelable(
    timeout: float | timedelta | None = None,
    operation_id: str | None = None,
    name: str | None = None,
    register_globally: bool = False,
    inject_param: str | None = "cancelable",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator to make async function cancelable.

    The decorator automatically creates a Cancelable context and injects it
    via the specified parameter name (default: 'cancelable'). The decorated
    function will ALWAYS receive a non-None Cancelable instance.

    Args:
        timeout: Optional timeout for the operation
        operation_id: Optional operation ID (auto-generated if not provided)
        name: Optional operation name (defaults to function name)
        register_globally: Whether to register with global registry
        inject_param: Parameter name to inject cancelable (None to disable)

    Returns:
        Decorator function

    Example:
        @cancelable(timeout=30.0, register_globally=True)
        async def my_operation(data: str, cancelable: Cancelable = None):
            await cancelable.report_progress("Starting")
            # ... do work ...
            return result

    Note:
        **Type the injected parameter as `Cancelable = None` for type checker
        compatibility.** The decorator ALWAYS provides a non-None instance,
        but the `= None` default signals to type checkers that callers don't
        need to provide this argument.

        For strict type checking within the function, optionally add:
        `assert cancelable is not None`

        Alternatively, disable injection with `inject_param=None` and use
        `current_operation()` instead.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Create cancelable
            cancel_kwargs: dict[str, Any] = {
                "operation_id": operation_id,
                "name": name or func.__name__,
                "register_globally": register_globally,
            }

            if timeout:
                cancel = Cancelable.with_timeout(timeout, **cancel_kwargs)
            else:
                cancel = Cancelable(**cancel_kwargs)

            async with cancel:
                # Inject cancelable if requested
                if inject_param:
                    sig = inspect.signature(func)
                    if inject_param in sig.parameters:
                        kwargs[inject_param] = cancel

                # Call the function
                result = await func(*args, **kwargs)
            return result

        # Add attribute to access decorator parameters (dynamic attribute, no type annotation needed)
        wrapper._cancelable_params = {  # type: ignore[attr-defined]
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
    cancelable = Cancelable.with_timeout(
        timeout,
        operation_id=operation_id,
        name=name,
    )

    async with cancelable:
        result = await coro
    return result


def with_current_operation() -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator that injects current operation into function.

    The function must have a parameter named 'operation'. The decorator
    will inject the current operation context if available (may be None
    if called outside a Cancelable context).

    Example:
        @with_current_operation()
        async def process_item(item: str, operation: Cancelable | None):
            if operation:
                await operation.report_progress(f"Processing {item}")
            return item.upper()

    Note:
        Unlike @cancelable, this decorator injects the CURRENT operation
        (if one exists) rather than creating a new one. The operation
        parameter may be None if no cancelable context is active.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            operation = current_operation()

            # Inject operation if function accepts it
            sig = inspect.signature(func)
            if "operation" in sig.parameters and "operation" not in kwargs:
                kwargs["operation"] = operation

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def cancelable_method(
    timeout: float | timedelta | None = None,
    name: str | None = None,
    register_globally: bool = False,
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]:
    """
    Decorator for async methods that should be cancelable.

    Similar to @cancelable but designed for class methods. The decorator
    automatically creates a Cancelable context and injects it as a
    'cancelable' parameter. The decorated method will ALWAYS receive a
    non-None Cancelable instance.

    Args:
        timeout: Optional timeout for the operation
        name: Optional operation name (defaults to ClassName.method_name)
        register_globally: Whether to register with global registry

    Returns:
        Decorator function

    Example:
        class DataProcessor:
            @cancelable_method(timeout=60.0)
            async def process(self, data: list, cancelable: Cancelable = None):
                for item in data:
                    await self._process_item(item)
                    await cancelable.report_progress(f"Processed {item}")

    Note:
        **Type the injected parameter as `Cancelable = None` for type checker
        compatibility.** The decorator ALWAYS provides a non-None instance,
        but the `= None` default signals to type checkers that callers don't
        need to provide this argument.
    """

    def decorator(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> R:
            # Get method name including class
            method_name = f"{self.__class__.__name__}.{func.__name__}"

            cancel_kwargs: dict[str, Any] = {
                "name": name or method_name,
                "register_globally": register_globally,
            }

            if timeout:
                cancel = Cancelable.with_timeout(timeout, **cancel_kwargs)
            else:
                cancel = Cancelable(**cancel_kwargs)

            async with cancel:
                # Inject cancelable
                sig = inspect.signature(func)
                if "cancelable" in sig.parameters:
                    kwargs["cancelable"] = cancel

                result = await func(self, *args, **kwargs)
            return result

        # Add attribute to access decorator parameters
        wrapper._cancelable_params = {  # type: ignore[attr-defined]
            "timeout": timeout,
            "name": name,
            "register_globally": register_globally,
        }

        return wrapper

    return decorator


def cancelable_with_token(
    token: "CancelationToken",
    operation_id: str | None = None,
    name: str | None = None,
    register_globally: bool = False,
    inject_param: str | None = "cancelable",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator for token-based cancelation.

    Creates a cancelable operation that can be cancelled via the provided token.
    Useful for operations that need to be cancelled from other tasks or threads.

    Args:
        token: CancelationToken to use for cancelation
        operation_id: Optional operation ID (auto-generated if not provided)
        name: Optional operation name (defaults to function name)
        register_globally: Whether to register with global registry
        inject_param: Parameter name to inject Cancelable (None to disable)

    Returns:
        Decorator function

    Example:
        ```python
        token = CancelationToken()

        @cancelable_with_token(token, name="fetch_data")
        async def fetch_data(url: str, cancelable: Cancelable = None):
            await cancelable.report_progress("Fetching...")
            return await httpx.get(url)

        # Cancel from another task
        await token.cancel(CancelationReason.MANUAL, "User cancelled")
        ```

    Note:
        Type the injected parameter as `Cancelable = None` for type checker compatibility.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cancel = Cancelable.with_token(
                token, operation_id=operation_id, name=name or func.__name__, register_globally=register_globally
            )

            async with cancel:
                # Inject cancelable if requested
                if inject_param:
                    sig = inspect.signature(func)
                    if inject_param in sig.parameters:
                        kwargs[inject_param] = cancel

                result = await func(*args, **kwargs)
            return result

        # Add attribute to access decorator parameters
        wrapper._cancelable_params = {  # type: ignore[attr-defined]
            "token": token,
            "operation_id": operation_id,
            "name": name,
            "register_globally": register_globally,
            "inject_param": inject_param,
        }

        return wrapper

    return decorator


def cancelable_with_signal(
    *signals: int,
    operation_id: str | None = None,
    name: str | None = None,
    register_globally: bool = False,
    inject_param: str | None = "cancelable",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator for signal-based cancelation.

    Creates a cancelable operation that responds to OS signals (Unix only).
    Useful for graceful shutdown of long-running services.

    Args:
        *signals: Signal numbers to handle (e.g., signal.SIGTERM, signal.SIGINT)
        operation_id: Optional operation ID (auto-generated if not provided)
        name: Optional operation name (defaults to function name)
        register_globally: Whether to register with global registry
        inject_param: Parameter name to inject Cancelable (None to disable)

    Returns:
        Decorator function

    Example:
        ```python
        import signal

        @cancelable_with_signal(signal.SIGTERM, signal.SIGINT, name="service")
        async def long_running_service(cancelable: Cancelable = None):
            while True:
                await cancelable.report_progress("Processing...")
                await process_batch()
        ```

    Note:
        Type the injected parameter as `Cancelable = None` for type checker compatibility.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cancel = Cancelable.with_signal(
                *signals, operation_id=operation_id, name=name or func.__name__, register_globally=register_globally
            )

            async with cancel:
                # Inject cancelable if requested
                if inject_param:
                    sig = inspect.signature(func)
                    if inject_param in sig.parameters:
                        kwargs[inject_param] = cancel

                result = await func(*args, **kwargs)
            return result  # type: ignore[possibly-unbound]

        # Add attribute to access decorator parameters
        wrapper._cancelable_params = {  # type: ignore[attr-defined]
            "signals": signals,
            "operation_id": operation_id,
            "name": name,
            "register_globally": register_globally,
            "inject_param": inject_param,
        }

        return wrapper

    return decorator


def cancelable_with_condition(
    condition: Callable[[], bool | Awaitable[bool]],
    check_interval: float = 0.1,
    condition_name: str | None = None,
    operation_id: str | None = None,
    name: str | None = None,
    register_globally: bool = False,
    inject_param: str | None = "cancelable",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator for condition-based cancelation.

    Creates a cancelable operation that cancels when a condition becomes True.
    Useful for resource-based cancelation (disk full, memory limit, etc.).

    Args:
        condition: Callable that returns True when cancelation should occur
        check_interval: How often to check the condition (seconds)
        condition_name: Name for the condition (for logging)
        operation_id: Optional operation ID (auto-generated if not provided)
        name: Optional operation name (defaults to function name)
        register_globally: Whether to register with global registry
        inject_param: Parameter name to inject Cancelable (None to disable)

    Returns:
        Decorator function

    Example:
        ```python
        @cancelable_with_condition(
            lambda: disk_full(),
            check_interval=1.0,
            condition_name="disk_space"
        )
        async def data_processing(cancelable: Cancelable = None):
            await process_large_dataset()
        ```

    Note:
        Type the injected parameter as `Cancelable = None` for type checker compatibility.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            cancel = Cancelable.with_condition(
                condition,
                check_interval=check_interval,
                condition_name=condition_name,
                operation_id=operation_id,
                name=name or func.__name__,
                register_globally=register_globally,
            )

            async with cancel:
                # Inject cancelable if requested
                if inject_param:
                    sig = inspect.signature(func)
                    if inject_param in sig.parameters:
                        kwargs[inject_param] = cancel

                result = await func(*args, **kwargs)
            return result  # type: ignore[possibly-unbound]

        # Add attribute to access decorator parameters
        wrapper._cancelable_params = {  # type: ignore[attr-defined]
            "condition": condition,
            "check_interval": check_interval,
            "condition_name": condition_name,
            "operation_id": operation_id,
            "name": name,
            "register_globally": register_globally,
            "inject_param": inject_param,
        }

        return wrapper

    return decorator


def cancelable_combine(
    *cancelables: Cancelable,
    operation_id: str | None = None,
    name: str | None = None,
    register_globally: bool = False,
    inject_param: str | None = "cancelable",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator for combining multiple cancelation sources.

    Creates a cancelable operation that cancels when ANY of the provided
    cancelables trigger. Useful for operations with multiple cancelation conditions.

    Args:
        *cancelables: Cancelables to combine
        operation_id: Optional operation ID (auto-generated if not provided)
        name: Optional operation name (defaults to function name)
        register_globally: Whether to register with global registry
        inject_param: Parameter name to inject Cancelable (None to disable)

    Returns:
        Decorator function

    Example:
        ```python
        token = CancelationToken()

        @cancelable_combine(
            Cancelable.with_timeout(60),
            Cancelable.with_token(token),
            Cancelable.with_signal(signal.SIGTERM),
            name="resilient_op"
        )
        async def resilient_operation(cancelable: Cancelable = None):
            return await complex_task()
        ```

    Note:
        Type the injected parameter as `Cancelable = None` for type checker compatibility.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Combine all cancelables
            if not cancelables:
                raise ValueError("At least one cancelable must be provided to cancelable_combine")

            # Get first cancelable and combine with rest
            # Note: We use the provided cancelables as-is since they may have
            # internal state and sources already configured
            first = cancelables[0]
            if len(cancelables) > 1:
                cancel = first.combine(*cancelables[1:])
            else:
                cancel = first

            # Determine the effective name
            # Always prefer explicit name, then function name (for decorator consistency)
            effective_name = name or func.__name__

            # Create a new cancelable with the desired name to avoid mutating shared state
            # We'll use the combined token from the original

            # Always wrap to apply decorator settings (name, operation_id, register_globally)
            final_cancel = Cancelable.with_token(
                cancel.token,
                operation_id=operation_id or cancel.context.id,
                name=effective_name,
                register_globally=register_globally,
            )

            async with final_cancel:
                # Inject cancelable if requested
                if inject_param:
                    sig = inspect.signature(func)
                    if inject_param in sig.parameters:
                        kwargs[inject_param] = final_cancel

                result = await func(*args, **kwargs)
            return result  # type: ignore[possibly-unbound]

        return wrapper

    return decorator


def with_cancelable(
    cancel: Cancelable,
    inject: bool = False,
    inject_param: str = "cancelable",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Decorator that wraps a function with an existing Cancelable instance.

    This decorator allows you to use a pre-configured Cancelable context
    with your async function. Unlike @cancelable which creates a new context,
    this decorator uses an existing one, enabling sharing of cancelation state
    across multiple functions.

    Args:
        cancel: Existing Cancelable instance to use
        inject: Whether to inject the Cancelable into the function signature (default: False)
        inject_param: Parameter name to inject Cancelable as (default: "cancelable")

    Returns:
        Decorator function

    Example:
        ```python
        from hother.cancelable import Cancelable, with_cancelable, current_operation

        # Create a shared cancelable context
        cancel = Cancelable.with_timeout(30.0, name="data_pipeline")

        @with_cancelable(cancel)
        async def fetch_data():
            # No injection, access via current_operation()
            ctx = current_operation()
            await ctx.report_progress("Fetching data...")
            return await fetch()

        @with_cancelable(cancel, inject=True)
        async def process_data(cancelable: Cancelable = None):
            # With injection
            await cancelable.report_progress("Processing...")
            return await process()

        # Both functions share the same cancelation context
        async with cancel:
            data = await fetch_data()
            result = await process_data()
        ```

    Note:
        When inject=False (default), use current_operation() to access the context
        from within the function if needed.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Note: We don't enter the cancel context here - that's the user's responsibility
            # This decorator just makes the cancel instance available to the function
            # The user must use: async with cancel: await decorated_function()

            # Inject cancelable if requested
            if inject:
                sig = inspect.signature(func)
                if inject_param in sig.parameters:
                    kwargs[inject_param] = cancel

            return await func(*args, **kwargs)

        return wrapper

    return decorator
