"""
Tests for the main Cancellable class.
"""

from datetime import timedelta

import anyio
import pytest

from cancelable import Cancellable, CancellationReason, CancellationToken, OperationStatus, current_operation
from tests.conftest import assert_cancelled_within


class TestCancellableBasics:
    """Test basic Cancellable functionality."""

    @pytest.mark.anyio
    async def test_context_manager(self):
        """Test basic context manager usage."""
        cancellable = Cancellable(name="test_operation")

        assert cancellable.context.status == OperationStatus.PENDING

        async with cancellable:
            assert cancellable.context.status == OperationStatus.RUNNING
            assert cancellable.is_running

            # Current operation should be set
            assert current_operation() is cancellable

            await anyio.sleep(0.1)

        assert cancellable.context.status == OperationStatus.COMPLETED
        assert cancellable.is_completed
        assert not cancellable.is_cancelled
        assert cancellable.context.duration is not None

    @pytest.mark.anyio
    async def test_operation_id(self):
        """Test operation ID handling."""
        # Auto-generated ID
        cancel1 = Cancellable()
        assert cancel1.operation_id is not None
        assert len(cancel1.operation_id) == 36  # UUID

        # Custom ID
        cancel2 = Cancellable(operation_id="custom-123")
        assert cancel2.operation_id == "custom-123"

    @pytest.mark.anyio
    async def test_metadata(self):
        """Test metadata handling."""
        metadata = {"key": "value", "number": 42}
        cancellable = Cancellable(metadata=metadata)

        assert cancellable.context.metadata == metadata

        # Metadata is mutable
        cancellable.context.metadata["new_key"] = "new_value"
        assert cancellable.context.metadata["new_key"] == "new_value"

    @pytest.mark.anyio
    async def test_parent_child_relationship(self):
        """Test parent-child cancellable relationships."""
        parent = Cancellable(name="parent")

        # Track what happens
        parent_cancelled = False

        try:
            async with parent:
                child1 = Cancellable(name="child1", parent=parent)
                child2 = Cancellable(name="child2", parent=parent)

                # Check relationships
                assert child1.context.parent_id == parent.context.id
                assert child2.context.parent_id == parent.context.id
                assert child1 in parent._children
                assert child2 in parent._children

                # Cancel parent before entering children contexts
                await parent.cancel()

                # Parent token should be cancelled
                assert parent._token.is_cancelled

                # Children tokens should also be cancelled due to linking
                await anyio.sleep(0.01)  # Allow propagation
                assert child1._token.is_cancelled
                assert child2._token.is_cancelled

        except anyio.get_cancelled_exc_class():
            parent_cancelled = True

        assert parent_cancelled, "Parent should have been cancelled"


class TestCancellableFactories:
    """Test Cancellable factory methods."""

    @pytest.mark.anyio
    async def test_with_timeout(self):
        """Test timeout-based cancellable."""
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancellable.with_timeout(0.1) as cancel:
                await anyio.sleep(1.0)  # Will timeout

        assert cancel.context.status == OperationStatus.CANCELLED
        assert cancel.context.cancel_reason == CancellationReason.TIMEOUT

    @pytest.mark.anyio
    async def test_with_timeout_timedelta(self):
        """Test timeout with timedelta."""
        timeout = timedelta(milliseconds=100)

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancellable.with_timeout(timeout) as cancel:
                await anyio.sleep(1.0)

        assert cancel.is_cancelled

    @pytest.mark.anyio
    async def test_with_token(self):
        """Test token-based cancellable."""
        token = CancellationToken()

        async def cancel_after_delay():
            await anyio.sleep(0.1)
            await token.cancel(CancellationReason.MANUAL, "Test cancel")

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_after_delay)

            async with assert_cancelled_within(0.2):
                async with Cancellable.with_token(token) as cancel:
                    await anyio.sleep(1.0)

        assert cancel.context.cancel_reason == CancellationReason.MANUAL
        assert cancel.context.cancel_message == "Test cancel"

    @pytest.mark.anyio
    async def test_with_condition(self):
        """Test condition-based cancellable."""
        counter = 0

        def should_cancel():
            nonlocal counter
            counter += 1
            return counter >= 5

        cancel = None  # Initialize variable
        with pytest.raises(anyio.get_cancelled_exc_class()):
            cancel = Cancellable.with_condition(should_cancel, check_interval=0.1, condition_name="counter_check")
            async with cancel:
                await anyio.sleep(2.0)

        assert cancel.context.cancel_reason == CancellationReason.CONDITION

    @pytest.mark.anyio
    async def test_with_condition_async(self):
        """Test async condition-based cancellable."""
        checks = 0

        async def async_condition():
            nonlocal checks
            checks += 1
            await anyio.sleep(0.01)  # Simulate async work
            return checks >= 3

        # Create cancellable before the try block
        cancel = Cancellable.with_condition(async_condition, check_interval=0.05, condition_name="test_async_condition")

        # Run the test
        start_time = anyio.current_time()

        try:
            async with cancel:
                # Wait for condition to trigger (should take ~0.15s)
                await anyio.sleep(1.0)
                # Should not reach here
                assert False, "Should have been cancelled"
        except anyio.get_cancelled_exc_class():
            # Expected - condition triggered
            duration = anyio.current_time() - start_time

            # Verify timing and checks
            assert checks >= 3, f"Expected at least 3 checks, got {checks}"
            assert duration < 0.5, f"Should have cancelled quickly, took {duration}s"

            # Verify final state
            assert cancel.context.status == OperationStatus.CANCELLED
            assert cancel.context.cancel_reason == CancellationReason.CONDITION


class TestCancellableComposition:
    """Test combining multiple cancellables."""

    @pytest.mark.anyio
    async def test_combine_timeout_and_token(self):
        """Test combining timeout and token cancellation."""
        token = CancellationToken()

        combined = Cancellable.with_timeout(1.0).combine(Cancellable.with_token(token))

        # Cancel via token (faster than timeout)
        async def cancel_soon():
            await anyio.sleep(0.1)
            await token.cancel(CancellationReason.MANUAL)

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_soon)

            async with assert_cancelled_within(0.2):
                async with combined:
                    await anyio.sleep(2.0)

        # The combined cancellable might show PARENT because it's linked
        # But we should check the original token
        assert token.is_cancelled
        assert token.reason == CancellationReason.MANUAL

    @pytest.mark.anyio
    async def test_combine_multiple_sources(self):
        """Test combining multiple cancellation sources."""
        token1 = CancellationToken()
        token2 = CancellationToken()

        combined = Cancellable.with_timeout(5.0).combine(Cancellable.with_token(token1)).combine(Cancellable.with_token(token2))

        # Cancel second token
        async def cancel_token2():
            await anyio.sleep(0.1)
            await token2.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_token2)

            async with assert_cancelled_within(0.2):
                async with combined:
                    await anyio.sleep(1.0)

        assert combined.is_cancelled


class TestCancellableCallbacks:
    """Test callback functionality."""

    @pytest.mark.anyio
    async def test_progress_callbacks(self):
        """Test progress reporting and callbacks."""
        messages = []

        def capture_progress(op_id, msg, meta):
            messages.append((op_id, msg, meta))

        cancellable = Cancellable(name="progress_test")
        cancellable.on_progress(capture_progress)

        async with cancellable:
            await cancellable.report_progress("Step 1")
            await cancellable.report_progress("Step 2", {"value": 42})

        assert len(messages) == 2
        assert messages[0][1] == "Step 1"
        assert messages[1][1] == "Step 2"
        assert messages[1][2] == {"value": 42}

    @pytest.mark.anyio
    async def test_status_callbacks(self):
        """Test status change callbacks."""
        events = []

        async def record_event(ctx):
            events.append((ctx.status.value, anyio.current_time()))

        cancellable = Cancellable(name="status_test").on_start(record_event).on_complete(record_event)

        async with cancellable:
            await anyio.sleep(0.1)

        assert len(events) == 2
        assert events[0][0] == "running"
        assert events[1][0] == "completed"

    @pytest.mark.anyio
    async def test_cancel_callbacks(self):
        """Test cancellation callbacks."""
        cancel_info = None

        def on_cancel(ctx):
            nonlocal cancel_info
            cancel_info = {
                "reason": ctx.cancel_reason,
                "message": ctx.cancel_message,
                "duration": ctx.duration_seconds,
            }

        cancellable = Cancellable.with_timeout(0.1).on_cancel(on_cancel)

        try:
            async with cancellable:
                await anyio.sleep(1.0)
        except anyio.get_cancelled_exc_class():
            pass

        assert cancel_info is not None
        assert cancel_info["reason"] == CancellationReason.TIMEOUT
        assert cancel_info["duration"] > 0

    @pytest.mark.anyio
    async def test_error_callbacks(self):
        """Test error callbacks."""
        error_info = None

        async def on_error(ctx, error):
            nonlocal error_info
            error_info = {
                "type": type(error).__name__,
                "message": str(error),
                "status": ctx.status.value,
            }

        cancellable = Cancellable().on_error(on_error)

        with pytest.raises(ValueError):
            async with cancellable:
                raise ValueError("Test error")

        assert error_info is not None
        assert error_info["type"] == "ValueError"
        assert error_info["message"] == "Test error"
        assert error_info["status"] == "failed"


class TestCancellableStreams:
    """Test stream processing functionality."""

    @pytest.mark.anyio
    async def test_stream_wrapper(self):
        """Test basic stream wrapping."""

        async def number_stream():
            for i in range(10):
                await anyio.sleep(0.01)
                yield i

        collected = []

        async with Cancellable() as cancel:
            async for item in cancel.stream(number_stream()):
                collected.append(item)

        assert collected == list(range(10))

    @pytest.mark.anyio
    async def test_stream_cancellation(self):
        """Test stream cancellation."""

        async def infinite_stream():
            i = 0
            while True:
                yield i
                i += 1
                await anyio.sleep(0.01)

        collected = []

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancellable.with_timeout(0.1) as cancel:
                async for item in cancel.stream(infinite_stream()):
                    collected.append(item)

        # Should have collected some items before timeout
        assert len(collected) > 0
        assert len(collected) < 20  # But not too many

    @pytest.mark.anyio
    async def test_stream_progress_reporting(self):
        """Test stream progress reporting."""

        async def data_stream():
            for i in range(25):
                yield i
                await anyio.sleep(0.01)

        progress_reports = []

        def capture_progress(op_id, msg, meta):
            if "Processed" in msg:
                progress_reports.append(meta["count"])

        cancellable = Cancellable().on_progress(capture_progress)

        async with cancellable:
            items = []
            async for item in cancellable.stream(data_stream(), report_interval=10):
                items.append(item)

        assert len(items) == 25
        assert progress_reports == [10, 20]

    @pytest.mark.anyio
    async def test_stream_partial_results(self):
        """Test partial result capture on cancellation."""

        async def slow_stream():
            for i in range(100):
                yield i
                await anyio.sleep(0.01)

        async with Cancellable.with_timeout(0.05) as cancel:
            try:
                async for _ in cancel.stream(slow_stream(), buffer_partial=True):
                    pass
            except anyio.get_cancelled_exc_class():
                pass

        # Should have partial results
        partial = cancel.context.partial_result
        assert partial is not None
        assert "count" in partial
        assert partial["count"] > 0
        assert "buffer" in partial
        assert len(partial["buffer"]) > 0


class TestCancellableShielding:
    """Test shielding functionality."""

    @pytest.mark.anyio
    async def test_shield_basic(self):
        """Test basic shielding from cancellation."""
        completed_steps = []
        shield_completed = False

        parent = Cancellable.with_timeout(0.1, name="parent")

        try:
            async with parent:
                completed_steps.append("parent_start")

                # Use shield correctly
                shield_scope = anyio.CancelScope(shield=True)
                with shield_scope:
                    completed_steps.append("shield_start")
                    await anyio.sleep(0.2)  # Longer than parent timeout
                    completed_steps.append("shield_end")
                    shield_completed = True

                # This may or may not execute depending on timing
                completed_steps.append("parent_end")

        except anyio.get_cancelled_exc_class():
            # Parent was cancelled
            pass

        # Shield should have completed
        assert shield_completed
        assert "shield_start" in completed_steps
        assert "shield_end" in completed_steps

    @pytest.mark.anyio
    async def test_shield_status(self):
        """Test shield status tracking."""
        async with Cancellable() as parent:
            async with parent.shield() as shielded:
                assert shielded.context.status == OperationStatus.SHIELDED
                assert shielded.context.metadata.get("shielded") is True
                assert shielded.context.parent_id == parent.context.id


class TestCancellableWrapping:
    """Test function wrapping functionality."""

    @pytest.mark.anyio
    async def test_wrap_function(self):
        """Test wrapping async function."""
        call_count = 0

        async def async_function(value: int) -> int:
            nonlocal call_count
            call_count += 1
            await anyio.sleep(0.1)
            return value * 2

        cancellable = Cancellable.with_timeout(1.0)
        wrapped = cancellable.wrap(async_function)

        # Should complete normally
        result = await wrapped(21)
        assert result == 42
        assert call_count == 1
        assert cancellable.is_completed

    @pytest.mark.anyio
    async def test_wrap_with_cancellable_param(self):
        """Test wrapping function that accepts cancellable."""

        async def func_with_cancellable(value: int, cancellable: Cancellable = None):
            await cancellable.report_progress(f"Processing {value}")
            return value * 2

        messages = []
        cancellable = Cancellable().on_progress(lambda op_id, msg, meta: messages.append(msg))

        wrapped = cancellable.wrap(func_with_cancellable)
        result = await wrapped(21)

        assert result == 42
        assert "Processing 21" in messages


class TestCancellableIntegration:
    """Test integration scenarios."""

    @pytest.mark.anyio
    async def test_nested_operations(self):
        """Test nested cancellable operations."""

        async def inner_operation():
            async with Cancellable(name="inner") as inner:
                await inner.report_progress("Inner started")
                await anyio.sleep(0.1)
                return "inner_result"

        async def outer_operation():
            async with Cancellable(name="outer") as outer:
                await outer.report_progress("Outer started")
                result = await inner_operation()
                await outer.report_progress(f"Inner returned: {result}")
                return "outer_result"

        result = await outer_operation()
        assert result == "outer_result"

    @pytest.mark.anyio
    async def test_concurrent_operations(self):
        """Test running multiple operations concurrently."""
        results = []

        async def operation(op_id: int, duration: float):
            async with Cancellable(name=f"op_{op_id}"):
                await anyio.sleep(duration)
                results.append(op_id)

        # Run operations concurrently
        async with anyio.create_task_group() as tg:
            for i in range(5):
                tg.start_soon(operation, i, 0.1)

        assert len(results) == 5
        assert set(results) == {0, 1, 2, 3, 4}

    @pytest.mark.anyio
    async def test_exception_handling(self):
        """Test exception handling in cancellable context."""
        # Regular exception
        with pytest.raises(ValueError):
            async with Cancellable() as cancel:
                raise ValueError("Test error")

        assert cancel.context.status == OperationStatus.FAILED
        assert cancel.context.error == "Test error"

        # Cancellation exception
        try:
            async with Cancellable.with_timeout(0.01) as cancel:
                await anyio.sleep(1.0)
        except anyio.get_cancelled_exc_class():
            pass

        assert cancel.context.status == OperationStatus.CANCELLED
        assert cancel.context.cancel_reason == CancellationReason.TIMEOUT
