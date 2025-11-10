"""Unit tests for condition cancelation source."""

import anyio
import pytest

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.condition import ConditionSource, ResourceConditionSource


class TestConditionSource:
    """Test ConditionSource functionality."""

    @pytest.mark.anyio
    async def test_condition_basic(self):
        """Test basic condition monitoring."""
        check_count = 0

        def condition():
            nonlocal check_count
            check_count += 1
            return check_count >= 3

        # Use the proper Cancelable API
        from hother.cancelable import Cancelable

        cancelable = Cancelable.with_condition(condition, check_interval=0.05, condition_name="test_condition")

        # Should cancel after 3 checks
        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.1 <= duration <= 0.2  # ~3 checks at 0.05s intervals
        assert check_count >= 3

        # Check that the cancelation reason is correct
        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_async_condition(self):
        """Test async condition function."""
        check_count = 0

        async def async_condition():
            nonlocal check_count
            check_count += 1
            await anyio.sleep(0.01)  # Simulate async work
            return check_count >= 2

        from hother.cancelable import Cancelable

        cancelable = Cancelable.with_condition(async_condition, check_interval=0.1)

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(1.0)

        assert check_count >= 2
        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_condition_error_handling(self):
        """Test condition error handling."""
        call_count = 0

        def faulty_condition():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Condition error")
            return call_count >= 4

        from hother.cancelable import Cancelable

        cancelable = Cancelable.with_condition(faulty_condition, check_interval=0.05)

        # Should continue checking despite error
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(0.5)  # Wait long enough for 4+ checks

        assert call_count >= 4
        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_condition_validation(self):
        """Test condition source validation."""
        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=0)

        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=-1)

    @pytest.mark.anyio
    async def test_condition_unexpected_exception(self):
        """Test condition source handles unexpected exceptions in monitor loop."""
        check_count = 0
        exception_raised = False

        async def condition_with_unexpected_error():
            nonlocal check_count, exception_raised
            check_count += 1
            if check_count == 2:
                # Raise an unexpected exception (not in the inner try-catch)
                # This simulates a bug in the event loop handling
                exception_raised = True
                # Force an exception in the monitoring loop itself
                # by breaking the stop_event
                raise RuntimeError("Unexpected monitor error")
            return False

        from hother.cancelable import Cancelable

        cancelable = Cancelable.with_condition(
            condition_with_unexpected_error,
            check_interval=0.05,
            condition_name="test_unexpected"
        )

        # The monitoring task should handle the exception gracefully
        # and not crash the entire operation
        async with cancelable:
            await anyio.sleep(0.2)

        # Should have attempted checks even with the exception
        assert exception_raised


class TestResourceConditionSource:
    """Test ResourceConditionSource functionality."""

    def test_resource_condition_creation(self):
        """Test creating resource condition source."""
        source = ResourceConditionSource(memory_threshold=80.0, cpu_threshold=90.0, disk_threshold=95.0, check_interval=1.0)

        assert source.memory_threshold == 80.0
        assert source.cpu_threshold == 90.0
        assert source.disk_threshold == 95.0
        assert source.check_interval == 1.0
        assert "resource_check" in source.condition_name

    @pytest.mark.anyio
    async def test_resource_check_no_psutil(self, monkeypatch):
        """Test resource check when psutil is not available."""
        # Mock import error
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        source = ResourceConditionSource(memory_threshold=80.0)
        result = await source._check_resources()

        assert result is False  # Should return False when psutil unavailable


class TestResourceConditionSourceWithPsutil:
    """Test ResourceConditionSource with psutil installed."""

    @pytest.fixture
    def mock_psutil(self, monkeypatch):
        """Create mock psutil module with controllable values."""
        psutil = pytest.importorskip("psutil")

        class MockMemory:
            def __init__(self, percent):
                self.percent = percent

        class MockDiskUsage:
            def __init__(self, percent):
                self.percent = percent

        mock_values = {
            'memory_percent': 50.0,
            'cpu_percent': 50.0,
            'disk_percent': 50.0,
        }

        def mock_virtual_memory():
            return MockMemory(mock_values['memory_percent'])

        def mock_cpu_percent(interval=None):
            return mock_values['cpu_percent']

        def mock_disk_usage(path):
            return MockDiskUsage(mock_values['disk_percent'])

        monkeypatch.setattr(psutil, 'virtual_memory', mock_virtual_memory)
        monkeypatch.setattr(psutil, 'cpu_percent', mock_cpu_percent)
        monkeypatch.setattr(psutil, 'disk_usage', mock_disk_usage)

        return mock_values

    @pytest.mark.anyio
    async def test_memory_threshold_exceeded(self, mock_psutil):
        """Test cancelation when memory threshold is exceeded."""
        from hother.cancelable import Cancelable

        # Set memory above threshold
        mock_psutil['memory_percent'] = 85.0

        # Create source that monitors memory at 80% threshold
        source = ResourceConditionSource(memory_threshold=80.0, check_interval=0.1)

        # Create cancelable with the source
        cancelable = Cancelable.with_condition(
            source._check_resources,
            check_interval=0.1,
            condition_name="memory_check"
        )

        # Should cancel due to high memory
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(0.5)

        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_cpu_threshold_exceeded(self, mock_psutil):
        """Test cancelation when CPU threshold is exceeded."""
        from hother.cancelable import Cancelable

        # Set CPU above threshold
        mock_psutil['cpu_percent'] = 95.0

        # Create source that monitors CPU at 90% threshold
        source = ResourceConditionSource(cpu_threshold=90.0, check_interval=0.1)

        cancelable = Cancelable.with_condition(
            source._check_resources,
            check_interval=0.1,
            condition_name="cpu_check"
        )

        # Should cancel due to high CPU
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(0.5)

        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_disk_threshold_exceeded(self, mock_psutil):
        """Test cancelation when disk threshold is exceeded."""
        from hother.cancelable import Cancelable

        # Set disk usage above threshold
        mock_psutil['disk_percent'] = 97.0

        # Create source that monitors disk at 95% threshold
        source = ResourceConditionSource(disk_threshold=95.0, check_interval=0.1)

        cancelable = Cancelable.with_condition(
            source._check_resources,
            check_interval=0.1,
            condition_name="disk_check"
        )

        # Should cancel due to high disk usage
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(0.5)

        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_combined_thresholds(self, mock_psutil):
        """Test monitoring multiple resources simultaneously."""
        from hother.cancelable import Cancelable

        # Start with one resource above threshold
        mock_psutil['memory_percent'] = 85.0  # Above 80% threshold
        mock_psutil['cpu_percent'] = 75.0     # Below 85% threshold
        mock_psutil['disk_percent'] = 80.0    # Below 90% threshold

        # Create source monitoring all three resources
        source = ResourceConditionSource(
            memory_threshold=80.0,
            cpu_threshold=85.0,
            disk_threshold=90.0,
            check_interval=0.05
        )

        cancelable = Cancelable.with_condition(
            source._check_resources,
            check_interval=0.05,
            condition_name="combined_check"
        )

        # Should cancel due to high memory (already above threshold)
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(0.5)

        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_thresholds_not_exceeded(self, mock_psutil):
        """Test operation completes normally when resources are OK."""
        from hother.cancelable import Cancelable

        # All resources well below thresholds
        mock_psutil['memory_percent'] = 50.0
        mock_psutil['cpu_percent'] = 40.0
        mock_psutil['disk_percent'] = 60.0

        # Create source with high thresholds
        source = ResourceConditionSource(
            memory_threshold=80.0,
            cpu_threshold=85.0,
            disk_threshold=90.0,
            check_interval=0.05
        )

        cancelable = Cancelable.with_condition(
            source._check_resources,
            check_interval=0.05,
            condition_name="normal_operation"
        )

        # Should complete without cancelation
        completed = False
        async with cancelable:
            await anyio.sleep(0.2)
            completed = True

        assert completed is True
        assert cancelable.context.status.value == "completed"

    @pytest.mark.anyio
    async def test_resource_monitoring_with_work(self, mock_psutil):
        """Test resource monitoring during actual work simulation."""
        from hother.cancelable import Cancelable

        # Start with memory already above threshold
        mock_psutil['memory_percent'] = 80.0  # Above 75% threshold
        mock_psutil['cpu_percent'] = 50.0

        source = ResourceConditionSource(
            memory_threshold=75.0,
            cpu_threshold=85.0,
            check_interval=0.05
        )

        cancelable = Cancelable.with_condition(
            source._check_resources,
            check_interval=0.05,
            condition_name="work_with_monitoring"
        )

        # Should cancel due to high memory before completing work
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                # Try to do long-running work
                await anyio.sleep(1.0)

        # Verify it was cancelled for the right reason
        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_resource_check_returns_false_initially(self, mock_psutil):
        """Test that _check_resources returns False when thresholds not exceeded."""
        mock_psutil['memory_percent'] = 50.0
        mock_psutil['cpu_percent'] = 40.0
        mock_psutil['disk_percent'] = 60.0

        source = ResourceConditionSource(
            memory_threshold=80.0,
            cpu_threshold=85.0,
            disk_threshold=90.0
        )

        result = await source._check_resources()
        assert result is False

    @pytest.mark.anyio
    async def test_resource_check_returns_true_on_threshold(self, mock_psutil):
        """Test that _check_resources returns True when any threshold exceeded."""
        mock_psutil['memory_percent'] = 85.0  # Above 80% threshold
        mock_psutil['cpu_percent'] = 40.0
        mock_psutil['disk_percent'] = 60.0

        source = ResourceConditionSource(
            memory_threshold=80.0,
            cpu_threshold=90.0,
            disk_threshold=95.0
        )

        result = await source._check_resources()
        assert result is True

    @pytest.mark.anyio
    async def test_resource_disk_threshold_only(self, mock_psutil):
        """Test disk threshold check when disk is exceeded."""
        mock_psutil['memory_percent'] = 50.0
        mock_psutil['cpu_percent'] = 40.0
        mock_psutil['disk_percent'] = 96.0  # Above 95% threshold

        source = ResourceConditionSource(
            disk_threshold=95.0  # Only disk threshold set
        )

        result = await source._check_resources()
        assert result is True

    @pytest.mark.anyio
    async def test_resource_disk_threshold_not_exceeded(self, mock_psutil):
        """Test disk threshold check when disk is NOT exceeded."""
        mock_psutil['memory_percent'] = 50.0
        mock_psutil['cpu_percent'] = 40.0
        mock_psutil['disk_percent'] = 80.0  # Below 95% threshold

        source = ResourceConditionSource(
            disk_threshold=95.0  # Only disk threshold set
        )

        result = await source._check_resources()
        assert result is False

    @pytest.mark.anyio
    async def test_no_disk_threshold_set(self, mock_psutil):
        """Test that disk check is skipped when disk_threshold is not set.

        Targets branch 248->260: disk_threshold is None, skip disk check, return False.
        """
        # Set mock values for other resources
        mock_psutil['memory_percent'] = 50.0
        mock_psutil['cpu_percent'] = 40.0
        mock_psutil['disk_percent'] = 90.0  # High, but won't be checked

        # Create source WITHOUT disk_threshold (None)
        source = ResourceConditionSource(
            memory_threshold=80.0,  # Set memory threshold
            cpu_threshold=85.0,     # Set CPU threshold
            # disk_threshold NOT SET (None) - this is the key!
            check_interval=0.1
        )

        # Should return False - memory and CPU OK, disk check skipped
        result = await source._check_resources()
        assert result is False


class TestConditionSourceEdgeCases:
    """Test edge cases for ConditionSource."""

    @pytest.mark.anyio
    async def test_stop_monitoring_without_task_group(self):
        """Test stop_monitoring when _task_group is None."""
        def simple_condition():
            return False

        source = ConditionSource(simple_condition)

        # Don't call start_monitoring, so _task_group won't exist
        await source.stop_monitoring()

        # Should complete without error

    @pytest.mark.anyio
    async def test_stop_monitoring_with_task_group_error(self):
        """Test stop_monitoring handles task group exit errors."""
        from unittest.mock import AsyncMock, MagicMock

        def simple_condition():
            return False

        source = ConditionSource(simple_condition, check_interval=0.01)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Mock the task group to raise an error on exit
        original_exit = source._task_group.__aexit__

        async def failing_exit(*args):
            raise RuntimeError("Task group exit failed")

        source._task_group.__aexit__ = failing_exit

        # Should handle error gracefully
        await source.stop_monitoring()

        # Task group should be cleaned up despite error
        assert source._task_group is None
        assert source._stop_event is None

    @pytest.mark.anyio
    async def test_monitor_condition_unexpected_exception(self):
        """Test _monitor_condition handles unexpected exceptions."""
        call_count = [0]

        async def failing_condition():
            call_count[0] += 1
            if call_count[0] == 2:
                # Raise unexpected exception on second call
                raise ValueError("Unexpected error")
            return False

        source = ConditionSource(failing_condition, check_interval=0.01)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Wait for condition to be checked multiple times
        await anyio.sleep(0.05)

        # Should have logged error but continued monitoring
        assert call_count[0] >= 2

        await source.stop_monitoring()

    @pytest.mark.anyio
    async def test_monitor_condition_cancelled_error(self):
        """Test that monitoring task properly handles CancelledError.

        Targets lines 151-154: except CancelledError with debug log and re-raise.
        """
        def never_true_condition():
            return False

        source = ConditionSource(never_true_condition, check_interval=0.1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Let monitoring task start
        await anyio.sleep(0.01)

        # Cancel the scope to trigger CancelledError in monitoring task
        scope.cancel()

        # Stop monitoring - this should handle the cancelation gracefully
        try:
            await source.stop_monitoring()
        except anyio.get_cancelled_exc_class():
            # Expected if cancelation propagates
            pass

        # The monitoring task should have been stopped
        assert source._task_group is None


    @pytest.mark.anyio
    async def test_monitor_infrastructure_error(self):
        """Test that outer exception handler catches monitoring infrastructure errors.

        This test targets lines 162-163 in condition.py by triggering an exception
        in the monitoring loop infrastructure (outside condition checking).
        """
        from unittest.mock import AsyncMock

        condition_called = False

        def simple_condition():
            nonlocal condition_called
            condition_called = True
            return False

        source = ConditionSource(simple_condition, check_interval=0.1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Wait for condition to be called at least once
        await anyio.sleep(0.15)
        assert condition_called

        # Now make the stop event wait() raise an exception
        # This simulates an infrastructure failure outside condition checking
        original_wait = source._stop_event.wait

        async def failing_wait():
            raise RuntimeError("Simulated infrastructure failure")

        source._stop_event.wait = failing_wait

        # Wait for the error to be logged (monitoring continues despite error)
        await anyio.sleep(0.15)

        # Clean up - restore original wait before stopping
        source._stop_event.wait = original_wait
        await source.stop_monitoring()


class TestResourceConditionSourceDiskThreshold:
    """Test ResourceConditionSource disk threshold coverage."""

    @pytest.fixture
    def mock_psutil_disk_ok(self, monkeypatch):
        """Mock psutil with disk usage below threshold."""
        psutil = pytest.importorskip("psutil")

        class MockDiskUsage:
            def __init__(self, percent):
                self.percent = percent

        def mock_disk_usage(path):
            return MockDiskUsage(80.0)  # Below 95% threshold

        monkeypatch.setattr(psutil, 'disk_usage', mock_disk_usage)
        return psutil

    @pytest.mark.anyio
    async def test_disk_threshold_not_exceeded(self, mock_psutil_disk_ok):
        """Test disk threshold check when disk is NOT exceeded.

        Targets branch 248->260: disk check performed, threshold not exceeded, returns False.
        """
        from hother.cancelable import Cancelable

        # Create source that ONLY monitors disk (no memory or CPU thresholds)
        source = ResourceConditionSource(
            disk_threshold=95.0,  # Set high threshold
            check_interval=0.1
        )

        # Test the internal _check_resources method directly
        result = await source._check_resources()

        # Should return False because disk usage (80%) is below threshold (95%)
        assert result is False
