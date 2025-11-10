"""
Main Cancelable class implementation.
"""

from __future__ import annotations

import contextvars
import inspect
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from enum import StrEnum, auto
from functools import wraps
from typing import Any, TypeVar, cast

import anyio

from hother.cancelable.core.exceptions import CancelationError
from hother.cancelable.core.models import CancelationReason, OperationContext, OperationStatus
from hother.cancelable.core.token import CancelationToken, LinkedCancelationToken
from hother.cancelable.sources.base import CancelationSource
from hother.cancelable.types import ErrorCallbackType, ProgressCallbackType, StatusCallbackType
from hother.cancelable.utils.context_bridge import ContextBridge
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")

# Context variable for current operation
_current_operation: contextvars.ContextVar[Cancelable | None] = contextvars.ContextVar(
    "current_operation", default=None
)


class LinkState(StrEnum):
    """State of token linking process."""

    NOT_LINKED = auto()
    LINKING = auto()
    LINKED = auto()
    CANCELLED = auto()


class Cancelable:
    """
    Main cancelation helper with composable cancelation sources.

    Provides a unified interface for handling cancelation from multiple sources
    including timeouts, tokens, signals, and conditions.
    """

    def __init__(
        self,
        operation_id: str | None = None,
        name: str | None = None,
        parent: Cancelable | None = None,
        metadata: dict[str, Any] | None = None,
        register_globally: bool = False,
    ):
        """
        Initialize a new cancelable operation.

        Args:
            operation_id: Unique operation identifier (auto-generated if not provided)
            name: Human-readable operation name
            parent: Parent cancelable for hierarchical cancelation
            metadata: Additional operation metadata
            register_globally: Whether to register with global registry
        """
        # Create context with conditional ID
        context_kwargs = {
            "name": name,
            "metadata": metadata or {},
        }
        if operation_id is not None:
            context_kwargs["id"] = operation_id

        self.context = OperationContext(**context_kwargs)  # type: ignore[arg-type]

        # Set parent relationship after context creation
        if parent:
            self.context.parent_id = parent.context.id

        self._scope: anyio.CancelScope | None = None
        self._token = LinkedCancelationToken()

        # Use weak references to break circular reference cycles
        self._parent_ref = weakref.ref(parent) if parent else None
        self._children: weakref.WeakSet[Cancelable] = weakref.WeakSet()

        # Register with parent if provided (parent holds strong refs to children)
        if parent:
            parent._children.add(self)
        self._sources: list[CancelationSource] = []
        self._shields: list[anyio.CancelScope] = []
        self._cancellables_to_link: list[Cancelable] | None = None
        self._register_globally = register_globally

        # Token linking state management
        self._link_state = LinkState.NOT_LINKED
        self._link_lock = anyio.Lock()

        # Callbacks
        self._progress_callbacks: list[ProgressCallbackType] = []
        self._status_callbacks: dict[str, list[StatusCallbackType | ErrorCallbackType]] = {
            "start": [],
            "complete": [],
            "cancel": [],
            "error": [],
        }

        # Register with parent
        if parent:
            parent._children.add(self)

        logger.info(
            "Cancelable created",
            extra=self.context.log_context(),
        )

    @property
    def token(self) -> LinkedCancelationToken:
        """
        Get the cancellation token for this operation.

        Returns:
            The LinkedCancelationToken managing this operation's cancellation state.
        """
        return self._token

    def add_source(self, source: CancelationSource) -> Cancelable:
        """
        Add a cancelation source to this operation.

        This allows adding custom or composite sources (like AllOfSource) to an existing
        Cancelable instance.

        Args:
            source: The cancelation source to add

        Returns:
            Self for method chaining

        Example:
            ```python
            from hother.cancelable.sources.composite import AllOfSource

            cancelable = Cancelable(name="my_op")
            all_of = AllOfSource([timeout_source, condition_source])
            cancelable.add_source(all_of)
            ```
        """
        self._sources.append(source)
        return self

    # Factory methods
    @classmethod
    def with_timeout(
        cls, timeout: float | timedelta, operation_id: str | None = None, name: str | None = None, **kwargs: Any
    ) -> Cancelable:
        """
        Create cancelable with timeout.

        Args:
            timeout: Timeout duration in seconds or timedelta
            operation_id: Optional operation ID
            name: Optional operation name
            **kwargs: Additional arguments for Cancelable

        Returns:
            Configured Cancelable instance
        """
        from ..sources.timeout import TimeoutSource

        if isinstance(timeout, timedelta):
            timeout = timeout.total_seconds()

        instance = cls(operation_id=operation_id, name=name or f"timeout_{timeout}s", **kwargs)
        instance._sources.append(TimeoutSource(timeout))
        return instance

    @classmethod
    def with_token(
        cls, token: CancelationToken, operation_id: str | None = None, name: str | None = None, **kwargs: Any
    ) -> Cancelable:
        """
        Create a Cancelable operation using an existing cancellation token.

        This factory method allows you to create a cancellable operation that shares
        a cancellation token with other operations, enabling coordinated cancellation.

        Args:
            token: The CancelationToken to use for this operation
            operation_id: Optional custom operation identifier
            name: Optional operation name (defaults to "token_based")
            **kwargs: Additional arguments passed to Cancelable constructor

        Returns:
            A configured Cancelable instance using the provided token

        Example:
            ```python
            # Share a token between multiple operations
            shared_token = CancelationToken()

            async with Cancelable.with_token(shared_token, name="task1") as cancel1:
                # ... operation 1 ...

            async with Cancelable.with_token(shared_token, name="task2") as cancel2:
                # ... operation 2 ...

            # Cancel both operations via the shared token
            await shared_token.cancel()
            ```
        """
        instance = cls(operation_id=operation_id, name=name or "token_based", **kwargs)
        # Replace default token with provided one
        logger.debug(f"with_token: Replacing default token {instance._token.id} with user token {token.id}")
        instance._token = token
        logger.debug(f"with_token: Created cancelable {instance.context.id} with user token {token.id}")
        return instance

    @classmethod
    def with_signal(
        cls, *signals: int, operation_id: str | None = None, name: str | None = None, **kwargs: Any
    ) -> Cancelable:
        """
        Create cancelable with signal handling.

        Args:
            *signals: Signal numbers to handle
            operation_id: Optional operation ID
            name: Optional operation name
            **kwargs: Additional arguments for Cancelable

        Returns:
            Configured Cancelable instance
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
        **kwargs: Any,
    ) -> Cancelable:
        """
        Create cancelable with condition checking.

        Args:
            condition: Callable that returns True when cancelation should occur
            check_interval: How often to check the condition (seconds)
            condition_name: Name for the condition (for logging)
            operation_id: Optional operation ID
            name: Optional operation name
            **kwargs: Additional arguments for Cancelable

        Returns:
            Configured Cancelable instance
        """
        from ..sources.condition import ConditionSource

        instance = cls(operation_id=operation_id, name=name or "condition_based", **kwargs)
        instance._sources.append(ConditionSource(condition, check_interval, condition_name))
        return instance

    # Composition
    def combine(self, *others: Cancelable) -> Cancelable:
        """
        Combine multiple Cancelable operations into a single coordinated operation.

        Creates a new Cancelable that will be cancelled if ANY of the combined
        operations is cancelled. All cancellation sources from the combined
        operations are merged together.

        Args:
            *others: One or more Cancelable instances to combine with this one

        Returns:
            A new Cancelable instance that coordinates cancellation across all
            combined operations. When entered, all operations' tokens are linked.

        Example:
            ```python
            # Combine timeout and signal handling
            timeout_cancel = Cancelable.with_timeout(30.0)
            signal_cancel = Cancelable.with_signal(signal.SIGTERM)

            async with timeout_cancel.combine(signal_cancel) as cancel:
                # Operation will cancel on either timeout OR signal
                await long_running_operation()
            ```

        Note:
            The combined Cancelable preserves the cancellation reason from
            whichever source triggers first.
        """
        logger.debug("=== COMBINE CALLED ===")
        logger.debug(f"Self: {self.context.id} ({self.context.name}) with token {self._token.id}")
        for i, other in enumerate(others):
            logger.debug(f"Other {i}: {other.context.id} ({other.context.name}) with token {other._token.id}")

        combined = Cancelable(
            name=f"combined_{self.context.name}",
            metadata={
                "sources": [self.context.id] + [o.context.id for o in others],
                "combined": True,
                "preserve_reason": True,  # Add this flag
            },
        )

        logger.debug(f"Created combined cancelable: {combined.context.id} with default token {combined._token.id}")

        # Store the actual cancelables to link their tokens later
        combined._cancellables_to_link = [self] + list(others)
        logger.debug(f"Will link to {len(combined._cancellables_to_link)} cancelables:")
        for i, c in enumerate(combined._cancellables_to_link):
            logger.debug(f"  {i}: {c.context.id} with token {c._token.id}")

        # Combine all sources
        combined._sources.extend(self._sources)
        for other in others:
            combined._sources.extend(other._sources)

        logger.debug(
            "Created combined cancelable",
            extra={
                "operation_id": combined.context.id,
                "source_count": len(combined._sources),
            },
        )

        return combined

    # Callback registration
    def on_progress(
        self,
        callback: ProgressCallbackType,
    ) -> Cancelable:
        """
        Register a callback to be invoked when progress is reported.

        The callback will be called whenever `report_progress()` is invoked
        on this operation. Both sync and async callbacks are supported.

        Args:
            callback: Function to call on progress updates. Receives:
                - operation_id (str): The ID of the operation
                - message (Any): The progress message
                - metadata (dict[str, Any] | None): Optional metadata

        Returns:
            Self for method chaining

        Example:
            ```python
            async with Cancelable(name="download") as cancel:
                cancel.on_progress(lambda id, msg, meta: print(f"Progress: {msg}"))

                for i in range(100):
                    await cancel.report_progress(f"{i}% complete")
                    await asyncio.sleep(0.1)
            ```
        """
        self._progress_callbacks.append(callback)
        return self

    def on_start(self, callback: StatusCallbackType) -> Cancelable:
        """
        Register a callback to be invoked when the operation starts.

        The callback is triggered when entering the async context (on `__aenter__`).

        Args:
            callback: Function receiving the OperationContext. Can be sync or async.

        Returns:
            Self for method chaining
        """
        self._status_callbacks["start"].append(callback)
        return self

    def on_complete(self, callback: StatusCallbackType) -> Cancelable:
        """
        Register a callback to be invoked when the operation completes successfully.

        The callback is triggered when exiting the context without cancellation or error.

        Args:
            callback: Function receiving the OperationContext. Can be sync or async.

        Returns:
            Self for method chaining
        """
        self._status_callbacks["complete"].append(callback)
        return self

    def on_cancel(self, callback: StatusCallbackType) -> Cancelable:
        """
        Register a callback to be invoked when the operation is cancelled.

        The callback is triggered when the operation is cancelled by any source
        (timeout, signal, token, condition, or parent cancellation).

        Args:
            callback: Function receiving the OperationContext. Can be sync or async.

        Returns:
            Self for method chaining
        """
        self._status_callbacks["cancel"].append(callback)
        return self

    def on_error(
        self,
        callback: ErrorCallbackType,
    ) -> Cancelable:
        """
        Register a callback to be invoked when the operation encounters an error.

        The callback is triggered when an exception (other than CancelledError)
        is raised within the operation context.

        Args:
            callback: Function receiving the OperationContext and Exception.
                Can be sync or async.

        Returns:
            Self for method chaining
        """
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
                    "Progress callback error for operation %s: %s",
                    self.context.id,
                    str(e),
                    exc_info=True,
                )

    async def check_cancelation(self) -> None:
        """
        Check if operation is cancelled and raise if so.

        This is a public API for checking cancellation state.
        Use this instead of accessing `_token` directly.

        Raises:
            anyio.CancelledError: If operation is cancelled
        """
        await self._token.check_async()

    # Context manager
    async def __aenter__(self) -> Cancelable:
        """Enter cancelation context."""
        logger.debug(f"=== ENTERING cancelation context for {self.context.id} ({self.context.name}) ===")

        # Set as current operation
        self._context_token = _current_operation.set(self)

        # Safely link all required tokens with race condition protection
        await self._safe_link_tokens()

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
        async def on_token_cancel(token: CancelationToken) -> None:
            """Callback when token is cancelled."""
            logger.error(
                f"🚨 TOKEN CALLBACK TRIGGERED! Token {token.id} cancelled, cancelling scope for {self.context.id}"
            )
            if self._scope and not self._scope.cancel_called:
                logger.error(f"🚨 CANCELLING SCOPE for {self.context.id}")
                self._scope.cancel()
            else:
                logger.error(
                    f"🚨 SCOPE ALREADY CANCELLED OR NONE for {self.context.id} (scope={self._scope}, cancel_called={self._scope.cancel_called if self._scope else 'N/A'})"
                )

        logger.debug(f"Registering token callback for token {self._token.id}")
        await self._token.register_callback(on_token_cancel)
        logger.debug("Token callback registered successfully")

        # Start monitoring
        await self._setup_monitoring()

        # Trigger start callbacks
        await self._trigger_callbacks("start")

        # Enter scope - sync operation
        self._scope_exit = self._scope.__enter__()

        logger.debug(f"=== COMPLETED ENTER for {self.context.id} ===")
        return self

    @property
    def parent(self) -> Cancelable | None:
        """Get parent cancelable, returning None if garbage collected."""
        return self._parent_ref() if self._parent_ref else None

    async def run_in_thread(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Run function in thread with proper context propagation.

        This method solves the context variable thread safety issue by ensuring
        that context variables (including _current_operation) are properly
        propagated to OS threads.

        Args:
            func: Function to run in thread
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func execution

        Example:
            ```python
            async with Cancelable(name="main") as cancel:
                # Context is propagated to thread
                result = await cancel.run_in_thread(expensive_computation, data)
            ```
        """
        # Store current context for thread propagation
        ctx = ContextBridge.copy_context()

        def thread_func():
            # Restore context in thread
            ContextBridge.restore_context(ctx)
            # Set current operation in thread
            _current_operation.set(self)
            return func(*args, **kwargs)

        # Run in thread with context
        return await ContextBridge.run_in_thread_with_context(thread_func)

    def __del__(self):
        """Cleanup when cancelable is garbage collected."""
        # Remove from parent's children set (if parent still exists)
        if self._parent_ref:
            parent = self._parent_ref()
            if parent and self in parent._children:
                parent._children.remove(self)

        # Clear references to help GC
        self._parent_ref = None
        self._children.clear()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> bool:
        """Exit cancelation context."""
        logger.debug(f"=== ENTERING __aexit__ for {self.context.id} ===")
        logger.debug(f"exc_type: {exc_type}, exc_val: {exc_val}")
        logger.debug(f"Current status: {self.context.status}")
        logger.debug(f"Current cancel_reason: {self.context.cancel_reason}")

        try:
            # Exit the scope first - sync operation
            _scope_handled = False
            if self._scope:
                try:
                    # scope.__exit__ returns True if it handled the exception
                    _scope_handled = self._scope.__exit__(exc_type, exc_val, exc_tb)
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
                    # Handle cancelation
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
                        # Check if deadline was exceeded (timeout)
                        # Note: anyio CancelScope always has deadline attribute (defaults to inf)
                        if anyio.current_time() >= self._scope.deadline:
                            self.context.cancel_reason = CancelationReason.TIMEOUT
                            self.context.cancel_message = "Operation timed out"
                            logger.debug("Detected timeout from deadline")
                        else:
                            # Check sources
                            for source in self._sources:
                                if hasattr(source, "triggered") and source.triggered:
                                    self.context.cancel_reason = source.reason
                                    break

                        if not self.context.cancel_reason:
                            self.context.cancel_reason = CancelationReason.MANUAL
                    else:
                        self.context.cancel_reason = CancelationReason.MANUAL

                    # Always update status to CANCELLED for any CancelledError
                    logger.debug(f"Updating status to CANCELLED (was {self.context.status})")
                    self.context.update_status(OperationStatus.CANCELLED)
                    logger.debug(f"Status after update: {self.context.status}")
                    await self._trigger_callbacks("cancel")

                elif issubclass(exc_type, CancelationError):
                    # Our custom cancelation errors
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

            logger.debug(
                f"Exited cancelation context - final status: {self.context.status}",
                extra=self.context.log_context(),
            )

        # Always propagate exceptions - cancelation context should not suppress them
        # The anyio.CancelScope handles cancelation propagation appropriately
        return False

    async def _collect_all_tokens(self, cancelables: list[Cancelable], result: list[CancelationToken]) -> None:
        """Recursively collect all tokens from cancelables and their children."""
        for cancelable in cancelables:
            # Add this cancelable's token
            if cancelable._token not in result:
                result.append(cancelable._token)

            # Recursively add tokens from nested cancelables
            if cancelable._cancellables_to_link is not None:
                await self._collect_all_tokens(cancelable._cancellables_to_link, result)

    async def _setup_monitoring(self) -> None:
        """Setup all cancelation sources."""
        # Setup source monitoring
        for source in self._sources:
            source.set_cancel_callback(self._on_source_cancelled)
            await source.start_monitoring(cast(anyio.CancelScope, self._scope))

    async def _stop_monitoring(self) -> None:
        """Stop all monitoring tasks."""
        # Stop source monitoring
        for source in self._sources:
            try:
                await source.stop_monitoring()
            except Exception as e:
                logger.error(
                    "Error stopping source monitoring for %s: %s",
                    str(source),
                    str(e),
                    exc_info=True,
                )

    async def _safe_link_tokens(self) -> None:
        """Safely link all required tokens with race condition protection."""
        async with self._link_lock:
            if self._link_state != LinkState.NOT_LINKED:
                return  # Already processed

            self._link_state = LinkState.LINKING

            try:
                # Link to parent token if we have a parent
                parent = self.parent
                if parent:
                    logger.debug(f"Linking to parent token: {parent._token.id}")
                    await self._token.link(parent._token)

                # Recursively link to ALL underlying tokens from combined cancelables
                if self._cancellables_to_link is not None:
                    logger.debug(f"Linking to {len(self._cancellables_to_link)} combined cancelables")
                    all_tokens: list[CancelationToken] = []
                    await self._collect_all_tokens(self._cancellables_to_link, all_tokens)

                    # Check if we should preserve cancelation reasons
                    preserve_reason = self.context.metadata.get("preserve_reason", False)

                    logger.debug(f"Found {len(all_tokens)} total tokens to link:")
                    for i, token in enumerate(all_tokens):
                        logger.debug(f"  Token {i}: {token.id}")
                        await self._token.link(token, preserve_reason=preserve_reason)

                self._link_state = LinkState.LINKED

            except Exception as e:
                self._link_state = LinkState.CANCELLED
                logger.error(f"Token linking failed: {e}")
                raise

    async def _on_source_cancelled(self, reason: CancelationReason, message: str) -> None:
        """Handle cancelation from a source."""
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
        Wrap async iterator with cancelation support.

        Args:
            async_iter: Async iterator to wrap
            report_interval: Report progress every N items
            buffer_partial: Whether to buffer items for partial results

        Yields:
            Items from the wrapped iterator
        """
        count = 0
        buffer: list[T] = []

        try:
            async for item in async_iter:
                # Check cancelation
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
        except Exception:  # Intentionally broad to save partial results on any error
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
                "Stream processing completed for operation %s with %d items",
                self.context.id,
                count,
            )

    # Function wrapper
    def wrap(self, operation: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        """
        Wrap an async operation to automatically check for cancelation before execution.

        This is useful for retry loops and other patterns where you want automatic
        cancelation checking without manually accessing the token.

        Note: This assumes the cancelable context is already active (you're inside
        an `async with` block). It does NOT create a new context.

        Args:
            operation: Async callable to wrap

        Returns:
            Wrapped callable that checks cancelation before executing

        Example:
            ```python
            async with Cancelable.with_timeout(30) as cancel:
                wrapped_fetch = cancel.wrap(fetch_data)

                # In a retry loop
                for attempt in range(3):
                    try:
                        result = await wrapped_fetch(url)
                        break
                    except Exception:
                        await anyio.sleep(1)
            ```
        """

        @wraps(operation)
        async def wrapped(*args, **kwargs) -> R:
            # Check cancelation before executing
            await self._token.check_async()
            return await operation(*args, **kwargs)

        return wrapped

    @asynccontextmanager
    async def wrapping(self) -> AsyncIterator[Callable[..., Awaitable[R]]]:
        """
        Async context manager that yields a wrap function for scoped operation wrapping.

        The yielded wrap function checks cancelation before executing any operation.
        This is useful for retry loops where you want all operations in a scope to
        be automatically wrapped with cancelation checking.

        Yields:
            A wrap function that checks cancelation before executing operations

        Example:
            ```python
            from tenacity import AsyncRetrying, stop_after_attempt

            async with Cancelable.with_timeout(30) as cancel:
                async for attempt in AsyncRetrying(stop=stop_after_attempt(3)):
                    with attempt:
                        async with cancel.wrapping() as wrap:
                            result = await wrap(fetch_data, url)
            ```
        """

        async def wrap_fn(fn: Callable[..., Awaitable[R]], *args, **kwargs) -> R:
            await self._token.check_async()
            return await fn(*args, **kwargs)

        yield wrap_fn

    # Shielding
    @asynccontextmanager
    async def shield(self) -> AsyncIterator[Cancelable]:
        """
        Shield a section from cancelation.

        Creates a child operation that is protected from cancelation but still
        participates in the operation hierarchy for monitoring and tracking.

        Yields:
            A new Cancelable for the shielded section
        """
        # Create properly integrated child cancelable
        shielded = Cancelable(name=f"{self.context.name}_shielded", metadata={"shielded": True})
        # Manually set parent relationship for hierarchy tracking but don't add to _children
        # to prevent automatic cancelation propagation
        shielded.context.parent_id = self.context.id

        # Override token linking to prevent cancelation propagation
        # The shielded operation should not be cancelled by parent token
        shielded._token = LinkedCancelationToken()  # Fresh token, no parent linking

        # Use anyio's CancelScope with shield=True
        with anyio.CancelScope(shield=True) as shield_scope:
            self._shields.append(shield_scope)
            try:
                shielded.context.update_status(OperationStatus.SHIELDED)
                yield shielded
            finally:
                # Shield is always in list at this point (added at line 783)
                self._shields.remove(shield_scope)

        # Force a checkpoint after shield to allow cancelation to propagate
        # We need to be in an async context for this to work properly
        try:
            await anyio.lowlevel.checkpoint()
        except:
            # Re-raise any exception including CancelledError
            raise

    # Cancelation
    async def cancel(
        self,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
        propagate_to_children: bool = True,
    ) -> None:
        """
        Cancel the operation.

        Args:
            reason: Reason for cancelation
            message: Optional cancelation message
            propagate_to_children: Whether to cancel child operations
        """
        # Cancel our token
        await self._token.cancel(reason, message)

        # Cancel children if requested
        if propagate_to_children:
            children_to_cancel = list(self._children)  # Snapshot to avoid modification during iteration
            for child in children_to_cancel:
                if child and not child.is_cancelled:
                    await child.cancel(
                        CancelationReason.PARENT,
                        f"Parent operation {self.context.id[:8]} cancelled",
                        propagate_to_children=True,
                    )

        # Clear references to help GC after cancelation
        self._children.clear()
        self._parent_ref = None

        # Log without duplicating cancel_reason
        log_ctx = self.context.log_context()
        # Remove cancel_reason from log_context if it exists to avoid duplication
        log_ctx.pop("cancel_reason", None)

        logger.info(
            "Operation cancelled",
            extra={
                **log_ctx,
                "cancel_reason": reason.value,
                "cancel_message": message,
            },
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
                    "%s callback error for operation %s: %s",
                    callback_type.capitalize(),
                    self.context.id,
                    str(e),
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
                    "Error callback error for operation %s: %s",
                    self.context.id,
                    str(e),
                    exc_info=True,
                )


def current_operation() -> Cancelable | None:
    """Get the current operation from context."""
    return _current_operation.get()
