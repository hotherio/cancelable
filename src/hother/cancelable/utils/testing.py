"""
Testing utilities for async cancelation.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

import anyio
from pydantic import PrivateAttr

from hother.cancelable.core.cancelable import Cancelable
from hother.cancelable.core.models import CancelationReason, OperationContext, OperationStatus
from hother.cancelable.core.token import CancelationToken
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class MockCancelationToken(CancelationToken):
    """
    Mock cancelation token for testing.

    Provides additional testing capabilities like scheduled cancelation.
    """

    # Additional fields for testing
    cancel_history: list[dict[str, Any]] = []
    _scheduled_cancelation: Any = PrivateAttr(default=None)

    async def cancel(
        self,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> bool:
        """Cancel and record in history."""
        self.cancel_history.append(
            {
                "time": datetime.now(UTC),
                "reason": reason,
                "message": message,
            }
        )
        return await super().cancel(reason, message)

    async def schedule_cancel(
        self,
        delay: float,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> None:
        """
        Schedule cancelation after a delay.

        Args:
            delay: Delay in seconds before cancelation
            reason: Cancelation reason
            message: Cancelation message
        """

        async def delayed_cancel():
            await anyio.sleep(delay)
            await self.cancel(reason, message)

        self._scheduled_cancelation = anyio.create_task_group()
        await self._scheduled_cancelation.__aenter__()
        self._scheduled_cancelation.start_soon(delayed_cancel)

    def get_cancel_count(self) -> int:
        """Get number of times cancel was called."""
        return len(self.cancel_history)


class OperationRecorder:
    """
    Records operation events for testing assertions.
    """

    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self.operations: dict[str, OperationContext] = {}
        self._lock = anyio.Lock()

    async def record_event(
        self,
        operation_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Record an operation event."""
        async with self._lock:
            self.events.append(
                {
                    "time": datetime.now(UTC),
                    "operation_id": operation_id,
                    "event_type": event_type,
                    "data": data or {},
                }
            )

    def attach_to_cancellable(self, cancelable: Cancelable) -> Cancelable:
        """
        Attach recorder to a cancelable to track its events.

        Args:
            cancelable: Cancelable to track

        Returns:
            The cancelable (for chaining)
        """
        op_id = cancelable.context.id
        self.operations[op_id] = cancelable.context

        # Record all events
        async def record_progress(op_id: str, msg: str, meta: dict[str, Any] | None):
            await self.record_event(op_id, "progress", {"message": msg, "meta": meta})

        async def record_status(ctx: OperationContext):
            await self.record_event(ctx.id, f"status_{ctx.status.value}", ctx.log_context())

        async def record_error(ctx: OperationContext, error: Exception):
            await self.record_event(ctx.id, "error", {"error_type": type(error).__name__, "error_message": str(error)})

        return (
            cancelable.on_progress(record_progress)
            .on_start(record_status)
            .on_complete(record_status)
            .on_cancel(record_status)
            .on_error(record_error)
        )

    def get_events_for_operation(self, operation_id: str) -> list[dict[str, Any]]:
        """Get all events for a specific operation."""
        return [e for e in self.events if e["operation_id"] == operation_id]

    def get_events_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """Get all events of a specific type."""
        return [e for e in self.events if e["event_type"] == event_type]

    def assert_event_occurred(
        self,
        operation_id: str,
        event_type: str,
        timeout: float = 1.0,
    ) -> dict[str, Any]:
        """
        Assert that an event occurred (synchronous check).

        Args:
            operation_id: Operation ID to check
            event_type: Event type to look for
            timeout: Not used in sync version

        Returns:
            The event data

        Raises:
            AssertionError: If event not found
        """
        events = [e for e in self.events if e["operation_id"] == operation_id and e["event_type"] == event_type]

        if not events:
            raise AssertionError(f"Event '{event_type}' not found for operation {operation_id}")

        return events[-1]  # Return most recent

    def assert_final_status(
        self,
        operation_id: str,
        expected_status: OperationStatus,
    ) -> None:
        """
        Assert the final status of an operation.

        Args:
            operation_id: Operation ID to check
            expected_status: Expected final status

        Raises:
            AssertionError: If status doesn't match
        """
        if operation_id not in self.operations:
            raise AssertionError(f"Operation {operation_id} not found")

        actual_status = self.operations[operation_id].status
        if actual_status != expected_status:
            raise AssertionError(f"Expected status {expected_status.value}, got {actual_status.value}")


async def create_slow_stream(
    items: list[T],
    delay: float = 0.1,
    cancelable: Cancelable | None = None,
) -> AsyncIterator[T]:
    """
    Create a slow async stream for testing cancelation.

    Args:
        items: Items to yield
        delay: Delay between items (seconds)
        cancelable: Optional cancelable to check

    Yields:
        Items with delays
    """
    for i, item in enumerate(items):
        if i > 0:  # No delay before first item
            await anyio.sleep(delay)

        if cancelable:
            await cancelable.token.check_async()

        yield item


async def run_with_timeout_test(
    coro: Any,
    expected_timeout: float,
    tolerance: float = 0.1,
) -> None:
    """
    Test that a coroutine times out within expected duration.

    Args:
        coro: Coroutine to run
        expected_timeout: Expected timeout duration
        tolerance: Acceptable deviation from expected timeout

    Raises:
        AssertionError: If timeout doesn't occur or timing is wrong
    """
    start_time = anyio.current_time()

    try:
        await coro
        raise AssertionError("Expected timeout but operation completed")
    except (anyio.get_cancelled_exc_class(), TimeoutError):
        # Expected cancelation
        duration = anyio.current_time() - start_time

        if abs(duration - expected_timeout) > tolerance:
            raise AssertionError(
                f"Timeout occurred after {duration:.2f}s, expected {expected_timeout:.2f}s ± {tolerance:.2f}s"
            )


@asynccontextmanager
async def assert_cancelation_within(
    min_time: float,
    max_time: float,
) -> AsyncIterator[MockCancelationToken]:
    """
    Context manager that asserts cancelation occurs within a time range.

    Args:
        min_time: Minimum time before cancelation
        max_time: Maximum time before cancelation

    Yields:
        Mock cancelation token

    Raises:
        AssertionError: If cancelation timing is wrong
    """
    token = MockCancelationToken()
    start_time = anyio.current_time()

    try:
        yield token
    finally:
        if token.is_cancelled:
            duration = anyio.current_time() - start_time
            if duration < min_time:
                raise AssertionError(f"Cancelation occurred too early: {duration:.2f}s < {min_time:.2f}s")
            if duration > max_time:
                raise AssertionError(f"Cancelation occurred too late: {duration:.2f}s > {max_time:.2f}s")
        else:
            raise AssertionError("Expected cancelation but none occurred")


class CancelationScenario:
    """
    Test scenario builder for cancelation testing.
    """

    def __init__(self, name: str):
        self.name = name
        self.steps: list[dict[str, Any]] = []
        self.assertions: list[dict[str, Any]] = []

    def add_delay(self, duration: float) -> "CancelationScenario":
        """Add a delay step."""
        self.steps.append({"type": "delay", "duration": duration})
        return self

    def add_cancelation(
        self,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> "CancelationScenario":
        """Add a cancelation step."""
        self.steps.append(
            {
                "type": "cancel",
                "reason": reason,
                "message": message,
            }
        )
        return self

    def add_progress_check(
        self,
        expected_message: str,
        timeout: float = 1.0,
    ) -> "CancelationScenario":
        """Add assertion for progress message."""
        self.assertions.append(
            {
                "type": "progress",
                "message": expected_message,
                "timeout": timeout,
            }
        )
        return self

    def add_status_check(
        self,
        expected_status: OperationStatus,
    ) -> "CancelationScenario":
        """Add assertion for operation status."""
        self.assertions.append(
            {
                "type": "status",
                "status": expected_status,
            }
        )
        return self

    async def run(
        self,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> OperationRecorder:
        """
        Run the scenario.

        Args:
            operation: Async callable to test
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Operation recorder with results
        """
        recorder = OperationRecorder()
        token = MockCancelationToken()

        # Create cancelable
        cancelable = Cancelable.with_token(token, name=f"scenario_{self.name}")
        recorder.attach_to_cancellable(cancelable)

        # Schedule steps
        async def run_steps():
            for step in self.steps:
                if step["type"] == "delay":
                    await anyio.sleep(step["duration"])
                elif step["type"] == "cancel":
                    await token.cancel(step["reason"], step["message"])

        # Run operation and steps concurrently
        async with anyio.create_task_group() as tg:
            tg.start_soon(run_steps)

            # Run operation with cancelable
            async with cancelable:
                try:
                    await operation(*args, **kwargs)
                except anyio.get_cancelled_exc_class():
                    pass  # Expected

        # Run assertions
        for assertion in self.assertions:
            if assertion["type"] == "progress":
                events = recorder.get_events_by_type("progress")
                messages = [e["data"]["message"] for e in events]
                if assertion["message"] not in messages:
                    raise AssertionError(f"Expected progress message '{assertion['message']}' not found")
            elif assertion["type"] == "status":
                recorder.assert_final_status(cancelable.context.id, assertion["status"])

        return recorder


# Test fixtures
async def sample_async_operation(
    duration: float = 1.0,
    cancelable: Cancelable | None = None,
) -> str:
    """Sample async operation for testing."""
    if cancelable:
        await cancelable.report_progress("Operation started")

    await anyio.sleep(duration / 2)

    if cancelable:
        await cancelable.report_progress("Operation 50% complete")

    await anyio.sleep(duration / 2)

    if cancelable:
        await cancelable.report_progress("Operation completed")

    return "success"
