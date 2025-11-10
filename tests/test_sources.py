"""
Tests for cancelation sources.
"""

import signal
from datetime import timedelta

import anyio
import pytest

from hother.cancelable import Cancelable
from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.base import CancelationSource
from hother.cancelable.sources.composite import AllOfSource, AnyOfSource, CompositeSource
from hother.cancelable.sources.condition import ConditionSource
from hother.cancelable.sources.signal import SignalSource
from hother.cancelable.sources.timeout import TimeoutSource


class TestTimeoutSource:
    """Test TimeoutSource functionality."""

    @pytest.mark.anyio
    async def test_timeout_basic(self):
        """Test basic timeout functionality."""
        source = TimeoutSource(0.1)
        assert source.timeout == 0.1
        assert source.reason == CancelationReason.TIMEOUT
        assert not source.triggered

        # Test with actual cancelable
        from hother.cancelable import Cancelable

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancelable.with_timeout(0.1):
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.08 <= duration <= 0.12

    @pytest.mark.anyio
    async def test_timeout_with_timedelta(self):
        """Test timeout with timedelta."""
        source = TimeoutSource(timedelta(milliseconds=100))
        assert source.timeout == 0.1

    @pytest.mark.anyio
    async def test_timeout_validation(self):
        """Test timeout validation."""
        with pytest.raises(ValueError):
            TimeoutSource(0)  # Zero timeout

        with pytest.raises(ValueError):
            TimeoutSource(-1)  # Negative timeout

    @pytest.mark.anyio
    async def test_timeout_with_scope(self):
        """Test timeout with manual scope handling."""
        source = TimeoutSource(0.1)

        # Create a cancelable that uses this source
        from hother.cancelable import Cancelable

        cancelable = Cancelable()
        cancelable._sources.append(source)

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(1.0)

        assert cancelable.context.cancel_reason == CancelationReason.TIMEOUT


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

        # Test with actual cancelable
        from hother.cancelable import Cancelable

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancelable.with_condition(condition, check_interval=0.05, condition_name="test_condition"):
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.1 <= duration <= 0.2  # ~3 checks at 0.05s intervals
        assert check_count >= 3

    @pytest.mark.anyio
    async def test_async_condition(self):
        """Test async condition function."""
        check_count = 0

        async def async_condition():
            nonlocal check_count
            check_count += 1
            await anyio.sleep(0.01)  # Simulate async work
            return check_count >= 2

        # Test with actual cancelable
        from hother.cancelable import Cancelable

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancelable.with_condition(async_condition, check_interval=0.1):
                await anyio.sleep(1.0)

        assert check_count >= 2

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

        # Test with actual cancelable
        from hother.cancelable import Cancelable

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancelable.with_condition(faulty_condition, check_interval=0.05):
                await anyio.sleep(1.0)

        # Should continue checking despite error
        assert call_count >= 4

    @pytest.mark.anyio
    async def test_condition_validation(self):
        """Test condition source validation."""
        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=0)

        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=-1)

    @pytest.mark.anyio
    async def test_condition_source_properties(self):
        """Test ConditionSource properties."""

        def test_condition():
            return False

        source = ConditionSource(test_condition, check_interval=0.1, condition_name="my_condition")

        assert source.condition == test_condition
        assert source.check_interval == 0.1
        assert source.condition_name == "my_condition"
        assert source.reason == CancelationReason.CONDITION
        assert not source.triggered


class TestCompositeSource:
    """Test CompositeSource functionality."""

    @pytest.mark.anyio
    async def test_composite_any_of(self):
        """Test composite source with ANY logic."""
        from hother.cancelable import Cancelable

        # Create two cancelables with different timeouts
        cancel1 = Cancelable.with_timeout(0.2)
        cancel2 = Cancelable.with_timeout(0.1)  # This will trigger first

        # Combine them
        combined = cancel1.combine(cancel2)

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with combined:
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.08 <= duration <= 0.12  # Triggered by shorter timeout

    @pytest.mark.anyio
    async def test_composite_empty_sources(self):
        """Test composite with no sources."""
        with pytest.raises(ValueError):
            CompositeSource([])

    @pytest.mark.anyio
    async def test_any_of_alias(self):
        """Test AnyOfSource alias."""
        source = AnyOfSource([TimeoutSource(0.1)])
        assert isinstance(source, CompositeSource)

    @pytest.mark.anyio
    async def test_composite_multiple_types(self):
        """Test combining different source types."""
        from hother.cancelable import Cancelable

        check_count = 0

        def condition():
            nonlocal check_count
            check_count += 1
            return check_count >= 3

        # Create cancelables with different sources
        timeout_cancel = Cancelable.with_timeout(0.5)
        condition_cancel = Cancelable.with_condition(condition, check_interval=0.05)

        # Combine them
        combined = timeout_cancel.combine(condition_cancel)

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with combined:
                await anyio.sleep(1.0)

        # Should be cancelled by condition (faster)
        duration = anyio.current_time() - start
        assert duration < 0.3  # Condition should trigger before timeout
        assert check_count >= 3

    @pytest.mark.anyio
    async def test_composite_triggered_source_tracking(self):
        """Test that composite tracks which source triggered."""
        # Use controlled condition sources to ensure triggering
        check_count_1 = 0
        check_count_2 = 0

        def condition1():
            nonlocal check_count_1
            check_count_1 += 1
            return check_count_1 >= 5  # Won't trigger quickly

        def condition2():
            nonlocal check_count_2
            check_count_2 += 1
            return check_count_2 >= 2  # Triggers fast

        source1 = ConditionSource(condition1, check_interval=0.05, condition_name="slow_condition")
        source2 = ConditionSource(condition2, check_interval=0.05, condition_name="fast_condition")

        composite = CompositeSource([source1, source2], name="test_composite")
        scope = anyio.CancelScope()

        await composite.start_monitoring(scope)

        # Wait for one to trigger
        await anyio.sleep(0.2)

        await composite.stop_monitoring()

        # The fast condition should have triggered
        assert composite.triggered_source is not None
        assert composite.triggered_source.condition_name == "fast_condition"

    @pytest.mark.anyio
    async def test_composite_reason_propagation(self):
        """Test that composite propagates reason from triggered source."""
        # Create sources with different reasons
        check_count = 0
        def condition():
            nonlocal check_count
            check_count += 1
            return check_count >= 2  # Will trigger after ~0.1s

        # Condition source will trigger (has CONDITION reason)
        condition_source = ConditionSource(condition, check_interval=0.05)
        # Timeout source won't trigger in our timeframe
        timeout_source = TimeoutSource(10.0)

        composite = CompositeSource([condition_source, timeout_source])
        scope = anyio.CancelScope()

        await composite.start_monitoring(scope)
        await anyio.sleep(0.2)
        await composite.stop_monitoring()

        # Composite should have condition's reason
        assert composite.reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_composite_custom_name(self):
        """Test composite with custom name."""
        source = TimeoutSource(0.1)
        composite = CompositeSource([source], name="my_custom_composite")

        assert composite.name == "my_custom_composite"

    @pytest.mark.anyio
    async def test_composite_stop_monitoring_with_errors(self):
        """Test composite handles errors when stopping sources."""
        # Create a mock source that raises error on stop
        class FailingSource(CancelationSource):
            def __init__(self):
                super().__init__(CancelationReason.MANUAL, "failing_source")

            async def start_monitoring(self, scope):
                self.scope = scope

            async def stop_monitoring(self):
                raise RuntimeError("Stop failed")

        failing_source = FailingSource()
        good_source = TimeoutSource(1.0)

        composite = CompositeSource([failing_source, good_source])
        scope = anyio.CancelScope()

        await composite.start_monitoring(scope)

        # Should not raise, should handle error gracefully
        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_composite_monitor_source_exception(self):
        """Test composite handles exception in source monitoring."""
        # Create a source that raises during start_monitoring
        class ExceptionSource(CancelationSource):
            def __init__(self):
                super().__init__(CancelationReason.MANUAL, "exception_source")

            async def start_monitoring(self, scope):
                raise ValueError("Cannot start monitoring")

            async def stop_monitoring(self):
                pass

        exception_source = ExceptionSource()
        good_source = TimeoutSource(0.5)

        composite = CompositeSource([exception_source, good_source])
        scope = anyio.CancelScope()

        # Should not crash, should handle exception
        await composite.start_monitoring(scope)

        # Give time for sources to start
        await anyio.sleep(0.1)

        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_composite_scope_already_cancelled(self):
        """Test composite with already-cancelled scope."""
        source = TimeoutSource(0.1)
        composite = CompositeSource([source])

        scope = anyio.CancelScope()
        scope.cancel()  # Pre-cancel the scope

        await composite.start_monitoring(scope)
        await anyio.sleep(0.15)
        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_composite_task_group_cleanup_errors(self):
        """Test composite handles task group cleanup errors."""
        source1 = TimeoutSource(0.1)
        source2 = TimeoutSource(0.2)

        composite = CompositeSource([source1, source2])
        scope = anyio.CancelScope()

        await composite.start_monitoring(scope)

        # Wait for trigger
        await anyio.sleep(0.15)

        # Stop should handle any cleanup errors gracefully
        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_composite_multiple_sources_race(self):
        """Test composite with multiple sources triggering nearly simultaneously."""
        # Create three condition sources that trigger at similar times
        counts = [0, 0, 0]

        def make_condition(idx, threshold):
            def condition():
                counts[idx] += 1
                return counts[idx] >= threshold
            return condition

        source1 = ConditionSource(make_condition(0, 2), check_interval=0.05)
        source2 = ConditionSource(make_condition(1, 2), check_interval=0.05)
        source3 = ConditionSource(make_condition(2, 2), check_interval=0.05)

        composite = CompositeSource([source1, source2, source3])
        scope = anyio.CancelScope()

        await composite.start_monitoring(scope)

        # Wait for one to trigger
        await anyio.sleep(0.2)

        await composite.stop_monitoring()

        # One of them should have triggered
        assert composite.triggered_source is not None


class TestAllOfSource:
    """Test AllOfSource functionality."""

    @pytest.mark.anyio
    async def test_all_of_empty_sources(self):
        """Test AllOfSource with no sources."""
        with pytest.raises(ValueError, match="At least one source is required"):
            AllOfSource([])

    @pytest.mark.anyio
    async def test_all_of_creation(self):
        """Test AllOfSource can be created with sources."""
        source1 = TimeoutSource(0.1)
        source2 = TimeoutSource(0.2)
        all_of = AllOfSource([source1, source2])

        assert len(all_of.sources) == 2
        assert all_of.triggered_sources == set()

    @pytest.mark.anyio
    async def test_all_of_requires_all_sources(self):
        """Test AllOfSource only triggers when ALL sources have triggered."""
        # Create sources that we can control
        check_count_1 = 0
        check_count_2 = 0

        def condition1():
            nonlocal check_count_1
            check_count_1 += 1
            return check_count_1 >= 2  # Triggers after ~0.1s (2 * 0.05)

        def condition2():
            nonlocal check_count_2
            check_count_2 += 1
            return check_count_2 >= 4  # Triggers after ~0.2s (4 * 0.05)

        source1 = ConditionSource(condition1, check_interval=0.05)
        source2 = ConditionSource(condition2, check_interval=0.05)

        all_of = AllOfSource([source1, source2])
        scope = anyio.CancelScope()

        await all_of.start_monitoring(scope)

        # After 0.15s, only source1 should have triggered
        await anyio.sleep(0.15)
        assert not scope.cancel_called  # Should NOT be cancelled yet

        # After 0.25s, both should have triggered
        await anyio.sleep(0.15)
        assert scope.cancel_called  # Should NOW be cancelled

        await all_of.stop_monitoring()

        # Both sources should be in triggered set
        assert len(all_of.triggered_sources) == 2

    @pytest.mark.anyio
    async def test_all_of_partial_trigger(self):
        """Test AllOfSource does NOT trigger with only partial sources."""
        # Create two sources, only one will trigger
        count1 = 0
        count2 = 0

        def condition1():
            nonlocal count1
            count1 += 1
            return count1 >= 2  # Will trigger after ~0.1s

        def condition2():
            nonlocal count2
            count2 += 1
            return False  # Will never trigger

        source1 = ConditionSource(condition1, check_interval=0.05)
        source2 = ConditionSource(condition2, check_interval=0.05)

        all_of = AllOfSource([source1, source2])
        scope = anyio.CancelScope()

        await all_of.start_monitoring(scope)

        # Wait for first source to trigger
        await anyio.sleep(0.15)

        # Scope should NOT be cancelled
        assert not scope.cancel_called

        # Only one source should be in triggered set
        assert len(all_of.triggered_sources) == 1

        await all_of.stop_monitoring()

    @pytest.mark.anyio
    async def test_all_of_custom_name(self):
        """Test AllOfSource with custom name."""
        source = TimeoutSource(0.1)
        all_of = AllOfSource([source], name="my_all_of")

        assert all_of.name == "my_all_of"

    @pytest.mark.anyio
    async def test_all_of_triggered_sources_tracking(self):
        """Test AllOfSource tracks triggered sources correctly."""
        # Use condition sources so we can track triggers via trigger_cancelation
        counts = [0, 0, 0]

        def make_condition(idx, threshold):
            def condition():
                counts[idx] += 1
                return counts[idx] >= threshold
            return condition

        # Different thresholds mean they trigger at different times
        source1 = ConditionSource(make_condition(0, 2), check_interval=0.05)  # ~0.1s
        source2 = ConditionSource(make_condition(1, 4), check_interval=0.05)  # ~0.2s
        source3 = ConditionSource(make_condition(2, 6), check_interval=0.05)  # ~0.3s

        all_of = AllOfSource([source1, source2, source3])
        scope = anyio.CancelScope()

        await all_of.start_monitoring(scope)

        # Initially empty
        assert len(all_of.triggered_sources) == 0

        # After 0.12s, one should be triggered
        await anyio.sleep(0.12)
        assert len(all_of.triggered_sources) == 1

        # After 0.22s total (0.10 more), two should be triggered
        await anyio.sleep(0.10)
        assert len(all_of.triggered_sources) == 2

        # After 0.35s total, all three should be triggered
        await anyio.sleep(0.13)
        assert len(all_of.triggered_sources) == 3
        assert scope.cancel_called

        await all_of.stop_monitoring()

    @pytest.mark.anyio
    async def test_all_of_stop_monitoring(self):
        """Test AllOfSource cleanup in stop_monitoring."""
        source1 = TimeoutSource(0.1)
        source2 = TimeoutSource(0.2)

        all_of = AllOfSource([source1, source2])
        scope = anyio.CancelScope()

        await all_of.start_monitoring(scope)

        # Stop before any trigger
        await anyio.sleep(0.05)
        await all_of.stop_monitoring()

        # Should not raise any errors

    @pytest.mark.anyio
    async def test_all_of_monitor_source_exception(self):
        """Test AllOfSource handles exception in source monitoring."""
        # Create a source that raises during start_monitoring
        class ExceptionSource(CancelationSource):
            def __init__(self):
                super().__init__(CancelationReason.MANUAL, "exception_source")

            async def start_monitoring(self, scope):
                raise ValueError("Cannot start monitoring")

            async def stop_monitoring(self):
                pass

        exception_source = ExceptionSource()
        good_source = TimeoutSource(0.5)

        all_of = AllOfSource([exception_source, good_source])
        scope = anyio.CancelScope()

        # Should not crash, should handle exception
        await all_of.start_monitoring(scope)

        # Give time for sources to start
        await anyio.sleep(0.1)

        await all_of.stop_monitoring()




