"""
Type definitions and protocols for hother.cancelable.

This module provides Protocol classes and type definitions to enable
proper static type checking without suppressions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ParamSpec, Protocol, TypeVar

if TYPE_CHECKING:
    from hother.cancelable.core.models import OperationContext

# Type variables
P = ParamSpec("P")  # For preserving function signatures in decorators
R = TypeVar("R")  # Return type
T = TypeVar("T")  # Generic type


class ProgressCallback(Protocol):
    """
    Protocol for progress callback functions.

    Accepts both sync and async callbacks for progress reporting.
    """

    def __call__(
        self,
        operation_id: str,
        message: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None | Awaitable[None]:
        """
        Called when operation reports progress.

        Args:
            operation_id: ID of the operation reporting progress
            message: Progress message (Any to support structured data)
            metadata: Optional metadata dictionary
        """
        ...


class StatusCallback(Protocol):
    """
    Protocol for status change callback functions.

    Called when operation status changes (started, completed, cancelled).
    """

    def __call__(self, context: OperationContext) -> None | Awaitable[None]:
        """
        Called when operation status changes.

        Args:
            context: The operation context with updated status
        """
        ...


class ErrorCallback(Protocol):
    """
    Protocol for error callback functions.

    Called when operation encounters an error.
    """

    def __call__(
        self,
        context: OperationContext,
        error: Exception,
    ) -> None | Awaitable[None]:
        """
        Called when operation encounters an error.

        Args:
            context: The operation context
            error: The exception that occurred
        """
        ...


# Union types for callbacks that can be sync or async
ProgressCallbackType = (
    Callable[[str, Any, dict[str, Any] | None], None]
    | Callable[[str, Any, dict[str, Any] | None], Awaitable[None]]
)

StatusCallbackType = (
    Callable[["OperationContext"], None]
    | Callable[["OperationContext"], Awaitable[None]]
)

ErrorCallbackType = (
    Callable[["OperationContext", Exception], None]
    | Callable[["OperationContext", Exception], Awaitable[None]]
)


def ensure_cancelable(cancelable: "Cancelable | None") -> "Cancelable":  # type: ignore[name-defined]
    """
    Type guard utility for injected cancelable parameters.

    Use this when decorated with @cancelable to narrow the type
    from `Cancelable | None` to `Cancelable`.

    Args:
        cancelable: The injected cancelable parameter

    Returns:
        The cancelable instance (guaranteed non-None)

    Raises:
        RuntimeError: If cancelable is None (should never happen)

    Example:
        @cancelable(timeout=30.0)
        async def my_function(data: str, cancelable: Cancelable = None):
            cancel = ensure_cancelable(cancelable)
            await cancel.report_progress("Working")
            # Type checker now knows cancel is non-None
    """
    if cancelable is None:
        raise RuntimeError(
            "Cancelable parameter is None. "
            "This should never happen when using @cancelable decorator. "
            "Did you call the function directly without the decorator?"
        )
    return cancelable
