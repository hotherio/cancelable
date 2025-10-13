"""
Main Cancellable class implementation.
"""

import contextvars
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from functools import wraps
from typing import TYPE_CHECKING, Any, Optional, TypeVar

import anyio

from hother.cancelable.core.exceptions import CancellationError
from hother.cancelable.core.models import CancellationReason, OperationContext, OperationStatus
from hother.cancelable.core.token import CancellationToken, LinkedCancellationToken
from hother.cancelable.sources.base import CancellationSource
from hother.cancelable.utils.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")

# Context variable for current operation
_current_operation: contextvars.ContextVar[Optional["Cancellable"]] = contextvars.ContextVar("current_operation", default=None)


class Cancellable:
    """
    Main cancellation helper with composable cancellation sources.

    Provides a unified interface for handling cancellation from multiple sources
    including timeouts, tokens, signals, and conditions.
    """

    def __init__(
        self,
        operation_id: str | None = None,
        name: str | None = None,
        parent: Optional["Cancellable"] = None,
        metadata: dict[str, Any] | None = None,
        register_globally: bool = False,
    ):
        """
        Initialize a new cancellable operation.

        Args:
            operation_id: Unique operation identifier (auto-generated if not provided)
            name: Human-readable operation name
            parent: Parent cancellable for hierarchical cancellation
            metadata: Additional operation metadata
            register_globally: Whether to register with global registry
        """
        # Create context with conditional ID
        context_kwargs = {
            "name": name,
            "metadata": metadata or {},
            "parent_id": parent.context.id if parent else None,
        }
        if operation_id is not None:
            context_kwargs["id"] = operation_id

        self.context = OperationContext(**context_kwargs)

        self._scope: anyio.CancelScope | None = None
        self._token = LinkedCancellationToken()
        self._parent = parent
        self._children: set[Cancellable] = set()
        self._sources: list[CancellationSource] = []
        self._shields: list[anyio.CancelScope] = []
        self._register_globally = register_globally

        # Callbacks
        self._progress_callbacks: list[Callable] = []
        self._status_callbacks: dict[str, list[Callable]] = {
            "start": [],
            "complete": [],
            "cancel": [],
            "error": [],
        }

        # Register with parent
        if parent:
            parent._children.add(self)

        logger.info(
            "Cancellable created",
            **self.context.log_context(),
        )

    # Factory methods
    @classmethod
    def with_timeout(cls, timeout: float | timedelta, operation_id: str | None = None, name: str | None = None, **kwargs) -> "Cancellable":
        """
        Create cancellable with timeout.

        Args:
            timeout: Timeout duration in seconds or timedelta
            operation_id: Optional operation ID
            name: Optional operation name
            **kwargs: Additional arguments for Cancellable

        Returns:
            Configured Cancellable instance
        """
        from ..sources.timeout import TimeoutSource

        if isinstance(timeout, timedelta):
            timeout = timeout.total_seconds()

        instance = cls(operation_id=operation_id, name=name or f"timeout_{timeout}s", **kwargs)
        instance._sources.append(TimeoutSource(timeout))
        return instance

    @classmethod
    def with_token(cls, token: CancellationToken, operation_id: str | None = None, name: str | None = None, **kwargs) -> "Cancellable":
        """
        Create cancellable with existing token.
        """
        instance = cls(operation_id=operation_id, name=name or "token_based", **kwargs)
        # Replace default token with provided one
        logger.info(f"with_token: Replacing default token {instance._token.id} with user token {token.id}")
        instance._token = token
        logger.info(f"with_token: Created cancellable {instance.context.id} with user token {token.id}")
        return instance

    @classmethod
    def with_signal(cls, *signals: int, operation_id: str | None = None, name: str | None = None, **kwargs) -> "Cancellable":
        """
        Create cancellable with signal handling.

        Args:
            *signals: Signal numbers to handle
            operation_id: Optional operation ID
            name: Optional operation name
            **kwargs: Additional arguments for Cancellable

        Returns:
            Configured Cancellable instance
        """
        from ..sources.signal import SignalSource

        instance = cls(operation_id=operation_id, name=name or "signal_based", **kwargs)
        instance._sources.append(SignalSource(*signals))
        return instance

    @classmethod
    def with_condition(
        cls,
        condition: Callable[[], bool | Awaitable[bool]],
        check_interval: float = 0.1,
        condition_name: str | None = None,
        operation_id: str | None = None,
        name: str | None = None,
        **kwargs,
    ) -> "Cancellable":
        """
        Create cancellable with condition checking.

        Args:
            condition: Callable that returns True when cancellation should occur
            check_interval: How often to check the condition (seconds)
            condition_name: Name for the condition (for logging)
            operation_id: Optional operation ID
            name: Optional operation name
            **kwargs: Additional arguments for Cancellable

        Returns:
            Configured Cancellable instance
        """
        from ..sources.condition import ConditionSource

        instance = cls(operation_id=operation_id, name=name or "condition_based", **kwargs)
        instance._sources.append(ConditionSource(condition, check_interval, condition_name))
        return instance

    # Composition
    def combine(self, *others: "Cancellable") -> "Cancellable":
        """
        Combine multiple cancellables into one.
        """
        logger.info("=== COMBINE CALLED ===")
        logger.info(f"Self: {self.context.id} ({self.context.name}) with token {self._token.id}")
        for i, other in enumerate(others):
            logger.info(f"Other {i}: {other.context.id} ({other.context.name}) with token {other._token.id}")

        combined = Cancellable(
            name=f"combined_{self.context.name}",
            metadata={
                "sources": [self.context.id] + [o.context.id for o in others],
                "combined": True,
                "preserve_reason": True,  # Add this flag
            },
        )

        logger.info(f"Created combined cancellable: {combined.context.id} with default token {combined._token.id}")

        # Store the actual cancellables to link their tokens later
        combined._cancellables_to_link = [self] + list(others)
        logger.info(f"Will link to {len(combined._cancellables_to_link)} cancellables:")
        for i, c in enumerate(combined._cancellables_to_link):
            logger.info(f"  {i}: {c.context.id} with token {c._token.id}")

        # Combine all sources
        combined._sources.extend(self._sources)
        for other in others:
            combined._sources.extend(other._sources)

        logger.debug(
            "Created combined cancellable",
            operation_id=combined.context.id,
            source_count=len(combined._sources),
        )

        return combined

    # Callback registration
    def on_progress(self, callback: Callable[[str, Any, dict[str, Any] | None], None] | Callable[[str, Any, dict[str, Any] | None], Awaitable[None]]) -> "Cancellable":
        """Register progress callback."""
        self._progress_callbacks.append(callback)
        return self

    def on_start(self, callback: Callable[[OperationContext], None] | Callable[[OperationContext], Awaitable[None]]) -> "Cancellable":
        """Register start callback."""
        self._status_callbacks["start"].append(callback)
        return self

    def on_complete(self, callback: Callable[[OperationContext], None] | Callable[[OperationContext], Awaitable[None]]) -> "Cancellable":
        """Register completion callback."""
        self._status_callbacks["complete"].append(callback)
        return self

    def on_cancel(self, callback: Callable[[OperationContext], None] | Callable[[OperationContext], Awaitable[None]]) -> "Cancellable":
        """Register cancellation callback."""
        self._status_callbacks["cancel"].append(callback)
        return self

    def on_error(self, callback: Callable[[OperationContext, Exception], None] | Callable[[OperationContext, Exception], Awaitable[None]]) -> "Cancellable":
        """Register error callback."""
        self._status_callbacks["error"].append(callback)
        return self

    # Progress reporting
    async def report_progress(self, message: Any, metadata: dict[str, Any] | None = None) -> None:
        """
        Report progress to all registered callbacks.

        Args:
            message: Progress message
            metadata: Optional metadata dict
        """
        for callback in self._progress_callbacks:
            try:
                result = callback(self.context.id, message, metadata)
                if inspect.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    "Progress callback error",
                    operation_id=self.context.id,
                    error=str(e),
                    exc_info=True,
                )

    # Context manager
    async def __aenter__(self) -> "Cancellable":
        """Enter cancellation context."""
        logger.info(f"=== ENTERING cancellation context for {self.context.id} ({self.context.name}) ===")

        # Set as current operation
        self._context_token = _current_operation.set(self)

        # Link to parent token if we have a parent
        if self._parent:
            logger.info(f"Linking to parent token: {self._parent._token.id}")
            await self._token.link(self._parent._token)

        # Recursively link to ALL underlying tokens from combined cancellables
        if hasattr(self, "_cancellables_to_link"):
            logger.info(f"Linking to {len(self._cancellables_to_link)} combined cancellables")
            all_tokens = []
            await self._collect_all_tokens(self._cancellables_to_link, all_tokens)

            # Check if we should preserve cancellation reasons
            preserve_reason = self.context.metadata.get("preserve_reason", False)

            logger.info(f"Found {len(all_tokens)} total tokens to link:")
            for i, token in enumerate(all_tokens):
                logger.info(f"  Token {i}: {token.id}")
                await self._token.link(token, preserve_reason=preserve_reason)

        # Update status
        self.context.update_status(OperationStatus.RUNNING)

        # Register with global registry if requested
        if self._register_globally:
            from .registry import OperationRegistry

            registry = OperationRegistry.get_instance()
            await registry.register(self)

        # Create cancel scope
        self._scope = anyio.CancelScope()

        # Set up simple token monitoring via callback
        async def on_token_cancel(token):
            """Callback when token is cancelled."""
            logger.error(f"🚨 TOKEN CALLBACK TRIGGERED! Token {token.id} cancelled, cancelling scope for {self.context.id}")
            if self._scope and not self._scope.cancel_called:
                logger.error(f"🚨 CANCELLING SCOPE for {self.context.id}")
                self._scope.cancel()
            else:
                logger.error(f"🚨 SCOPE ALREADY CANCELLED OR NONE for {self.context.id} (scope={self._scope}, cancel_called={self._scope.cancel_called if self._scope else 'N/A'})")

        logger.info(f"Registering token callback for token {self._token.id}")
        await self._token.register_callback(on_token_cancel)
        logger.info("Token callback registered successfully")

        # Start monitoring
        await self._setup_monitoring()

        # Trigger start callbacks
        await self._trigger_callbacks("start")

        # Enter scope - sync operation
        self._scope_exit = self._scope.__enter__()

        logger.info(f"=== COMPLETED ENTER for {self.context.id} ===")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit cancellation context."""
        logger.debug(f"=== ENTERING __aexit__ for {self.context.id} ===")
        logger.debug(f"exc_type: {exc_type}, exc_val: {exc_val}")
        logger.debug(f"Current status: {self.context.status}")
        logger.debug(f"Current cancel_reason: {self.context.cancel_reason}")

        suppress_exception = False

        try:
            # Exit the scope first - sync operation
            scope_handled = False
            if self._scope:
                try:
                    # scope.__exit__ returns True if it handled the exception
                    scope_handled = self._scope.__exit__(exc_type, exc_val, exc_tb)
                except Exception as e:
                    logger.debug(f"Scope exit raised: {e}")
                    # Re-raise the exception from scope exit
                    raise

            # Determine final status based on the exception
            # We need to update status even if scope handled it, because the exception might still propagate
            if exc_type is not None:
                logger.debug(f"Exception type: {exc_type}")
                if issubclass(exc_type, anyio.get_cancelled_exc_class()):
                    logger.debug("Handling CancelledError")
                    # Handle cancellation
                    # First check if we already have a cancel reason set by a source
                    if self.context.cancel_reason:
                        # A source already set the reason (like condition, timeout, etc.)
                        logger.debug(f"Cancel reason already set: {self.context.cancel_reason}")
                    elif self._token.is_cancelled:
                        # Token was cancelled
                        self.context.cancel_reason = self._token.reason
                        self.context.cancel_message = self._token.message
                        logger.debug(f"Cancel reason from token: {self._token.reason}")
                    elif self._scope and self._scope.cancel_called:
                        # Scope was cancelled - check why
                        # First check if deadline was exceeded (timeout)
                        if hasattr(self._scope, "deadline") and self._scope.deadline is not None:
                            # Check if we passed the deadline
                            if anyio.current_time() >= self._scope.deadline:
                                self.context.cancel_reason = CancellationReason.TIMEOUT
                                self.context.cancel_message = "Operation timed out"
                                logger.debug("Detected timeout from deadline")
                            else:
                                # Check sources
                                for source in self._sources:
                                    if hasattr(source, "triggered") and source.triggered:
                                        self.context.cancel_reason = source.reason
                                        break
                        else:
                            # No deadline, check sources
                            for source in self._sources:
                                if hasattr(source, "triggered") and source.triggered:
                                    self.context.cancel_reason = source.reason
                                    break

                        if not self.context.cancel_reason:
                            self.context.cancel_reason = CancellationReason.MANUAL
                    else:
                        self.context.cancel_reason = CancellationReason.MANUAL

                    # Always update status to CANCELLED for any CancelledError
                    logger.debug(f"Updating status to CANCELLED (was {self.context.status})")
                    self.context.update_status(OperationStatus.CANCELLED)
                    logger.debug(f"Status after update: {self.context.status}")
                    await self._trigger_callbacks("cancel")

                elif issubclass(exc_type, CancellationError):
                    # Our custom cancellation errors
                    self.context.cancel_reason = exc_val.reason
                    self.context.cancel_message = exc_val.message
                    self.context.update_status(OperationStatus.CANCELLED)
                    await self._trigger_callbacks("cancel")
                else:
                    # Other errors
                    self.context.error = str(exc_val)
                    self.context.update_status(OperationStatus.FAILED)
                    await self._trigger_error_callbacks(exc_val)
            else:
                # Successful completion
                self.context.update_status(OperationStatus.COMPLETED)
                await self._trigger_callbacks("complete")

        except Exception as e:
            logger.error(f"Error in __aexit__ status handling: {e}", exc_info=True)

        finally:
            logger.debug(f"=== __aexit__ finally block for {self.context.id} ===")

            # Stop monitoring
            await self._stop_monitoring()

            # Cleanup shields
            for shield in self._shields:
                shield.cancel()

            # Unregister from global registry
            if self._register_globally:
                from .registry import OperationRegistry

                registry = OperationRegistry.get_instance()
                await registry.unregister(self.context.id)

            # Reset context variable
            if hasattr(self, "_context_token"):
                _current_operation.reset(self._context_token)

            logger.info(
                f"Exited cancellation context - final status: {self.context.status}",
                **self.context.log_context(),
            )

        # Return False to propagate exceptions
        return suppress_exception

    async def _collect_all_tokens(self, cancellables: list["Cancellable"], result: list[CancellationToken]) -> None:
        """Recursively collect all tokens from cancellables and their children."""
        for cancellable in cancellables:
            # Add this cancellable's token
            if cancellable._token not in result:
                result.append(cancellable._token)

            # Recursively add tokens from nested cancellables
            if hasattr(cancellable, "_cancellables_to_link"):
                await self._collect_all_tokens(cancellable._cancellables_to_link, result)

    async def _setup_monitoring(self) -> None:
        """Setup all cancellation sources."""
        # Setup source monitoring
        for source in self._sources:
            source.set_cancel_callback(self._on_source_cancelled)
            await source.start_monitoring(self._scope)

    async def _check_cancellation(self) -> None:
        """Check for cancellation from various sources."""
        if self._token.is_cancelled and self._scope and not self._scope.cancel_called:
            self._scope.cancel()

    async def _stop_monitoring(self) -> None:
        """Stop all monitoring tasks."""
        # Stop source monitoring
        for source in self._sources:
            try:
                await source.stop_monitoring()
            except Exception as e:
                logger.error(
                    "Error stopping source monitoring",
                    source=str(source),
                    error=str(e),
                    exc_info=True,
                )

    async def _on_source_cancelled(self, reason: CancellationReason, message: str) -> None:
        """Handle cancellation from a source."""
        self.context.cancel_reason = reason
        self.context.cancel_message = message
        # Also update the status immediately when a source cancels
        self.context.update_status(OperationStatus.CANCELLED)

    # Stream wrapper
    async def stream(
        self,
        async_iter: AsyncIterator[T],
        report_interval: int | None = None,
        buffer_partial: bool = True,
    ) -> AsyncIterator[T]:
        """
        Wrap async iterator with cancellation support.

        Args:
            async_iter: Async iterator to wrap
            report_interval: Report progress every N items
            buffer_partial: Whether to buffer items for partial results

        Yields:
            Items from the wrapped iterator
        """
        count = 0
        buffer = []

        try:
            async for item in async_iter:
                # Check cancellation
                await self._token.check_async()

                yield item
                count += 1

                if buffer_partial:
                    buffer.append(item)
                    # Limit buffer size
                    if len(buffer) > 1000:
                        buffer = buffer[-1000:]

                if report_interval and count % report_interval == 0:
                    await self.report_progress(f"Processed {count} items", {"count": count, "latest_item": item})

        except anyio.get_cancelled_exc_class():
            # Save partial results
            self.context.partial_result = {
                "count": count,
                "buffer": buffer if buffer_partial else None,
            }
            raise
        except Exception:
            # Also save partial results on other exceptions
            self.context.partial_result = {
                "count": count,
                "buffer": buffer if buffer_partial else None,
                "completed": False,
            }
            raise
        else:
            # Save final results if completed normally
            if buffer_partial or count > 0:
                self.context.partial_result = {
                    "count": count,
                    "buffer": buffer if buffer_partial else None,
                    "completed": True,
                }
        finally:
            logger.debug(
                "Stream processing completed",
                operation_id=self.context.id,
                item_count=count,
            )

    # Function wrapper
    def wrap(self, func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        """
        Wrap async function with cancellation.

        Args:
            func: Async function to wrap

        Returns:
            Wrapped function
        """

        @wraps(func)
        async def wrapper(*args, **kwargs) -> R:
            async with self:
                # Inject cancellable if function accepts it
                sig = inspect.signature(func)
                if "cancellable" in sig.parameters:
                    kwargs["cancellable"] = self

                return await func(*args, **kwargs)

        return wrapper

    # Shielding
    @asynccontextmanager
    async def shield(self) -> AsyncIterator["Cancellable"]:
        """
        Shield a section from cancellation.

        Yields:
            A new Cancellable for the shielded section
        """
        # Create child cancellable for the shielded section
        # Set parent_id but don't use parent parameter to avoid token linking
        shielded = Cancellable(name=f"{self.context.name}_shielded", metadata={"shielded": True})
        # Manually set parent_id to avoid token linking
        shielded.context.parent_id = self.context.id

        # Use anyio's CancelScope with shield=True
        with anyio.CancelScope(shield=True) as shield_scope:
            self._shields.append(shield_scope)
            try:
                shielded.context.update_status(OperationStatus.SHIELDED)
                yield shielded
            finally:
                if shield_scope in self._shields:
                    self._shields.remove(shield_scope)

        # Force a checkpoint after shield to allow cancellation to propagate
        # We need to be in an async context for this to work properly
        try:
            await anyio.sleep(0)
        except:
            # Re-raise any exception including CancelledError
            raise

    # Cancellation
    async def cancel(
        self,
        reason: CancellationReason = CancellationReason.MANUAL,
        message: str | None = None,
        propagate_to_children: bool = True,
    ) -> None:
        """
        Cancel the operation.

        Args:
            reason: Reason for cancellation
            message: Optional cancellation message
            propagate_to_children: Whether to cancel child operations
        """
        # Cancel our token
        await self._token.cancel(reason, message)

        # Cancel children if requested
        if propagate_to_children:
            for child in self._children:
                await child.cancel(
                    CancellationReason.PARENT,
                    f"Parent operation {self.context.id[:8]} cancelled",
                    propagate_to_children=True,
                )

        # Log without duplicating cancel_reason
        log_ctx = self.context.log_context()
        # Remove cancel_reason from log_context if it exists to avoid duplication
        log_ctx.pop("cancel_reason", None)

        logger.info(
            "Operation cancelled",
            **log_ctx,
            cancel_reason=reason.value,
            cancel_message=message,
        )

    # Status helpers
    @property
    def is_cancelled(self) -> bool:
        """Check if operation is cancelled."""
        return self.context.is_cancelled

    @property
    def is_running(self) -> bool:
        """Check if operation is running."""
        return self.context.status == OperationStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """Check if operation completed successfully."""
        return self.context.is_success

    @property
    def operation_id(self) -> str:
        """Get operation ID."""
        return self.context.id

    # Callback helpers
    async def _trigger_callbacks(self, callback_type: str) -> None:
        """Trigger callbacks of a specific type."""
        callbacks = self._status_callbacks.get(callback_type, [])
        for callback in callbacks:
            try:
                result = callback(self.context)
                if inspect.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    f"{callback_type.capitalize()} callback error",
                    operation_id=self.context.id,
                    error=str(e),
                    exc_info=True,
                )

    async def _trigger_error_callbacks(self, error: Exception) -> None:
        """Trigger error callbacks."""
        callbacks = self._status_callbacks.get("error", [])
        for callback in callbacks:
            try:
                result = callback(self.context, error)
                if inspect.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    "Error callback error",
                    operation_id=self.context.id,
                    error=str(e),
                    exc_info=True,
                )


def current_operation() -> Cancellable | None:
    """Get the current operation from context."""
    return _current_operation.get()
