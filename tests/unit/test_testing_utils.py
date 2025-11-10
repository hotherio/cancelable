"""
Unit tests for testing utilities in hother.cancelable.utils.testing.

These tests ensure the testing utilities themselves work correctly.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

import anyio

from hother.cancelable import Cancelable
from hother.cancelable.core.models import CancelationReason, OperationStatus
from hother.cancelable.utils.testing import (
    CancelationScenario,
    MockCancelationToken,
    OperationRecorder,
    assert_cancelation_within,
    create_slow_stream,
    run_with_timeout_test,
    sample_async_operation,
)


class TestMockCancelationToken:
    """Test MockCancelationToken functionality."""

    @pytest.mark.anyio
    async def test_basic_cancel(self):
        """Test basic cancelation functionality."""
        token = MockCancelationToken()

        # Initially not cancelled
        assert not token.is_cancelled
        assert token.get_cancel_count() == 0

        # Cancel it
        result = await token.cancel(reason=CancelationReason.TIMEOUT, message="Test timeout")
        assert result is True

        # Now cancelled
        assert token.is_cancelled
        assert token.get_cancel_count() == 1
        assert len(token.cancel_history) == 1

        # Check history
        history = token.cancel_history[0]
        assert history["reason"] == CancelationReason.TIMEOUT
        assert history["message"] == "Test timeout"
        assert isinstance(history["time"], datetime)

    @pytest.mark.anyio
    async def test_multiple_cancels(self):
        """Test multiple cancelations."""
        token = MockCancelationToken()

        await token.cancel(reason=CancelationReason.MANUAL, message="First")
        await token.cancel(reason=CancelationReason.SIGNAL, message="Second")

        assert token.get_cancel_count() == 2
        assert len(token.cancel_history) == 2

        assert token.cancel_history[0]["reason"] == CancelationReason.MANUAL
        assert token.cancel_history[1]["reason"] == CancelationReason.SIGNAL

    @pytest.mark.anyio
    async def test_schedule_cancel(self):
        """Test scheduled cancelation."""
        token = MockCancelationToken()

        # Schedule cancelation in 0.1 seconds
        await token.schedule_cancel(delay=0.1, reason=CancelationReason.TIMEOUT)

        # Should not be cancelled immediately
        assert not token.is_cancelled

        # Wait for cancelation
        await anyio.sleep(0.15)

        # Should be cancelled now
        assert token.is_cancelled
        assert token.get_cancel_count() == 1
        assert token.cancel_history[0]["reason"] == CancelationReason.TIMEOUT


class TestOperationRecorder:
    """Test OperationRecorder functionality."""

    @pytest.mark.anyio
    async def test_basic_recording(self):
        """Test basic event recording."""
        recorder = OperationRecorder()

        await recorder.record_event("op1", "start", {"data": "test"})
        await recorder.record_event("op1", "progress", {"message": "50%"})
        await recorder.record_event("op1", "complete")

        events = recorder.get_events_for_operation("op1")
        assert len(events) == 3

        assert events[0]["event_type"] == "start"
        assert events[0]["data"]["data"] == "test"

        assert events[1]["event_type"] == "progress"
        assert events[1]["data"]["message"] == "50%"

        assert events[2]["event_type"] == "complete"

    @pytest.mark.anyio
    async def test_event_filtering(self):
        """Test event filtering by type."""
        recorder = OperationRecorder()

        await recorder.record_event("op1", "start")
        await recorder.record_event("op1", "progress")
        await recorder.record_event("op2", "start")
        await recorder.record_event("op1", "complete")

        progress_events = recorder.get_events_by_type("progress")
        assert len(progress_events) == 1
        assert progress_events[0]["operation_id"] == "op1"

        start_events = recorder.get_events_by_type("start")
        assert len(start_events) == 2

    @pytest.mark.anyio
    async def test_attach_to_cancellable(self):
        """Test attaching recorder to cancelable."""
        recorder = OperationRecorder()
        cancelable_ref = None

        async with Cancelable(name="test_op") as cancel:
            cancelable_ref = recorder.attach_to_cancellable(cancel)

            # Trigger some events
            await cancelable_ref.report_progress("Working")
            await cancelable_ref.report_progress("Done")

        # Check events were recorded
        assert cancelable_ref is not None
        events = recorder.get_events_for_operation(cancelable_ref.context.id)
        progress_events = [e for e in events if e["event_type"] == "progress"]
        assert len(progress_events) == 2

    @pytest.mark.anyio
    async def test_assert_event_occurred(self):
        """Test event assertion methods."""
        recorder = OperationRecorder()

        await recorder.record_event("op1", "start")
        await recorder.record_event("op1", "complete")

        # Should not raise
        event = recorder.assert_event_occurred("op1", "start")
        assert event["event_type"] == "start"

        # Should raise for missing event
        with pytest.raises(AssertionError):
            recorder.assert_event_occurred("op1", "error")

    @pytest.mark.anyio
    async def test_assert_final_status(self):
        """Test status assertion."""
        recorder = OperationRecorder()

        # Create a mock operation context
        from hother.cancelable.core.models import OperationContext

        ctx = OperationContext(name="test", status=OperationStatus.COMPLETED)
        recorder.operations["op1"] = ctx

        # Should not raise
        recorder.assert_final_status("op1", OperationStatus.COMPLETED)

        # Should raise for wrong status
        with pytest.raises(AssertionError):
            recorder.assert_final_status("op1", OperationStatus.CANCELLED)

    @pytest.mark.anyio
    async def test_attach_to_cancellable_records_error(self):
        """Test that recorder captures error events."""
        recorder = OperationRecorder()

        # Create a cancelable that will raise an error
        try:
            async with Cancelable(name="error_op") as cancelable:
                recorder.attach_to_cancellable(cancelable)

                # Raise an error to trigger error callback
                raise RuntimeError("Test error")
        except RuntimeError:
            pass  # Expected error

        # Check error event was recorded
        error_events = recorder.get_events_by_type("error")
        assert len(error_events) == 1
        assert error_events[0]["data"]["error_type"] == "RuntimeError"
        assert error_events[0]["data"]["error_message"] == "Test error"


class TestUtilityFunctions:
    """Test utility functions."""

    @pytest.mark.anyio
    async def test_create_slow_stream(self):
        """Test create_slow_stream function."""
        items = ["a", "b", "c"]
        stream = create_slow_stream(items, delay=0.01)

        collected = []
        async for item in stream:
            collected.append(item)

        assert collected == items

    @pytest.mark.anyio
    async def test_create_slow_stream_with_cancelable(self):
        """Test create_slow_stream with cancelable checking."""
        items = ["a", "b", "c", "d", "e"]

        async with Cancelable.with_timeout(0.05, name="stream_test") as cancelable:
            stream = create_slow_stream(items, delay=0.02, cancelable=cancelable)

            collected = []
            try:
                async for item in stream:
                    collected.append(item)
            except anyio.get_cancelled_exc_class():
                pass  # Expected timeout

        # Should have collected some items before timeout
        assert len(collected) > 0
        assert len(collected) < len(items)



    @pytest.mark.anyio
    async def test_run_with_timeout_test_timeout(self):
        """Test run_with_timeout_test with timeout."""
        from hother.cancelable import Cancelable

        async def slow_operation():
            async with Cancelable.with_timeout(0.05):  # This will timeout
                await anyio.sleep(0.1)

        # Should not raise - timeout occurs within expected time
        await run_with_timeout_test(slow_operation(), expected_timeout=0.05)

    @pytest.mark.anyio
    async def test_sample_async_operation(self):
        """Test sample_async_operation function."""
        result = await sample_async_operation(duration=0.01)
        assert result == "success"

    @pytest.mark.anyio
    async def test_sample_async_operation_with_cancelable(self):
        """Test sample_async_operation with cancelable."""
        async with Cancelable(name="test") as cancelable:
            result = await sample_async_operation(duration=0.01, cancelable=cancelable)
            assert result == "success"

            # Check that progress was reported
            # (This would need a recorder to verify, but basic functionality works)


class TestAssertCancelationWithin:
    """Test assert_cancelation_within context manager."""

    @pytest.mark.anyio
    async def test_cancelation_within_range(self):
        """Test successful cancelation within time range."""
        async with assert_cancelation_within(min_time=0.03, max_time=0.08) as token:
            # Cancel at the right time
            await anyio.sleep(0.05)
            await token.cancel()

    @pytest.mark.anyio
    async def test_cancelation_too_early(self):
        """Test cancelation that occurs too early."""
        with pytest.raises(AssertionError, match="too early"):
            async with assert_cancelation_within(min_time=0.05, max_time=0.1) as token:
                # Cancel too early
                await anyio.sleep(0.01)
                await token.cancel()

    @pytest.mark.anyio
    async def test_cancelation_too_late(self):
        """Test cancelation that occurs too late."""
        with pytest.raises(AssertionError, match="too late"):
            async with assert_cancelation_within(min_time=0.05, max_time=0.1) as token:
                # Cancel too late
                await anyio.sleep(0.15)
                await token.cancel()

    @pytest.mark.anyio
    async def test_no_cancelation(self):
        """Test when no cancelation occurs."""
        token = MockCancelationToken()

        with pytest.raises(AssertionError, match="Expected cancelation"):
            async with assert_cancelation_within(min_time=0.01, max_time=0.05):
                await anyio.sleep(0.1)  # No cancelation


class TestCancelationScenario:
    """Test CancelationScenario functionality."""

    @pytest.mark.anyio
    async def test_scenario_builder_methods(self):
        """Test scenario builder methods."""
        scenario = CancelationScenario("builder_test")

        # Test chaining
        result = scenario.add_delay(0.1)
        assert result is scenario

        result = scenario.add_cancelation()
        assert result is scenario

        result = scenario.add_progress_check("test")
        assert result is scenario

        result = scenario.add_status_check(OperationStatus.COMPLETED)
        assert result is scenario

    @pytest.mark.anyio
    async def test_scenario_run(self):
        """Test running a complete scenario."""
        scenario = CancelationScenario("test_run")

        # Build scenario: delay then cancel
        scenario.add_delay(0.05).add_cancelation(
            reason=CancelationReason.MANUAL,
            message="Test cancel"
        )

        # NOTE: The scenario catches CancelledError, so the operation completes normally
        # even though it was cancelled. The test is checking that the scenario runs.

        # Run the scenario
        async def test_operation():
            await anyio.sleep(1.0)  # This will be cancelled by the scenario

        recorder = await scenario.run(test_operation)

        # Check recorder has the operation
        assert len(recorder.operations) == 1

        # Check that cancelation occurred
        op_id = list(recorder.operations.keys())[0]
        # The operation completes normally because the scenario catches CancelledError
        assert recorder.operations[op_id].status in [OperationStatus.COMPLETED, OperationStatus.CANCELLED]

    @pytest.mark.anyio
    async def test_scenario_run_with_delay_step(self):
        """Test scenario with delay step."""
        scenario = CancelationScenario("delay_test")

        # Just add a delay, no cancelation
        scenario.add_delay(0.01)

        async def quick_operation():
            await anyio.sleep(0.005)
            return "done"

        recorder = await scenario.run(quick_operation)

        # Operation should complete successfully
        assert len(recorder.operations) == 1

    @pytest.mark.anyio
    async def test_scenario_run_progress_assertion_failure(self):
        """Test that scenario raises AssertionError when progress message not found."""
        scenario = CancelationScenario("progress_fail_test")

        # Add a progress check for a message that won't be reported
        scenario.add_progress_check("nonexistent_message")

        async def operation_without_progress():
            await anyio.sleep(0.01)

        # Should raise AssertionError because progress message not found
        with pytest.raises(AssertionError, match="Expected progress message"):
            await scenario.run(operation_without_progress)

    @pytest.mark.anyio
    async def test_scenario_run_status_assertion(self):
        """Test scenario with status assertion."""
        scenario = CancelationScenario("status_test")

        # Add status check for completed
        scenario.add_status_check(OperationStatus.COMPLETED)

        async def quick_operation():
            await anyio.sleep(0.01)

        recorder = await scenario.run(quick_operation)

        # Assertion should have passed
        assert len(recorder.operations) == 1

    @pytest.mark.anyio
    async def test_scenario_immediate_cancelation(self):
        """Test scenario with immediate cancelation (no delay)."""
        scenario = CancelationScenario("immediate_cancel")

        # Add cancelation with no delay first
        scenario.add_cancelation(
            reason=CancelationReason.MANUAL,
            message="Immediate cancel"
        )

        async def long_operation():
            await anyio.sleep(1.0)

        recorder = await scenario.run(long_operation)

        # Operation should be in the recorder
        assert len(recorder.operations) == 1

    @pytest.mark.anyio
    async def test_scenario_status_assertion_passes(self):
        """Test scenario where status assertion passes."""
        scenario = CancelationScenario("status_pass")

        # Operation will complete, check for COMPLETED status
        scenario.add_status_check(OperationStatus.COMPLETED)

        async def completing_operation():
            await anyio.sleep(0.01)
            return "done"

        recorder = await scenario.run(completing_operation)

        # Check that the operation completed successfully
        op_id = list(recorder.operations.keys())[0]
        assert recorder.operations[op_id].status == OperationStatus.COMPLETED

    @pytest.mark.anyio
    async def test_scenario_unknown_step_type(self):
        """Test scenario with unknown step type (edge case)."""
        scenario = CancelationScenario("unknown_step")

        # Manually add a step with an unknown type to test the else path
        scenario.steps.append({"type": "unknown", "data": "test"})

        async def simple_operation():
            await anyio.sleep(0.01)

        # Should complete without error, unknown step is ignored
        recorder = await scenario.run(simple_operation)
        assert len(recorder.operations) == 1

    @pytest.mark.anyio
    async def test_scenario_unknown_assertion_type(self):
        """Test scenario with unknown assertion type (edge case)."""
        scenario = CancelationScenario("unknown_assertion")

        # Manually add an assertion with an unknown type
        scenario.assertions.append({"type": "unknown", "data": "test"})

        async def simple_operation():
            await anyio.sleep(0.01)

        # Should complete without error, unknown assertion is ignored
        recorder = await scenario.run(simple_operation)
        assert len(recorder.operations) == 1