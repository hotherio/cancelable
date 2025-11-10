"""
Unit tests for composite cancelation source.
"""

import anyio
import pytest

from hother.cancelable import Cancelable
from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.base import CancelationSource
from hother.cancelable.sources.composite import AllOfSource, AnyOfSource, CompositeSource
from hother.cancelable.sources.timeout import TimeoutSource


class TestCompositeSource:
    """Test CompositeSource functionality."""

    @pytest.mark.anyio
    async def test_composite_requires_sources(self):
        """Test that CompositeSource requires at least one source."""
        with pytest.raises(ValueError, match="At least one source is required"):
            CompositeSource([])

    @pytest.mark.anyio
    async def test_composite_basic_functionality(self):
        """Test basic composite source functionality."""
        triggered = [False]

        async def mark_triggered(reason, message):
            triggered[0] = True

        # Create a manual trigger source
        class ManualSource(CancelationSource):
            def __init__(self):
                super().__init__(CancelationReason.MANUAL)
                self.started = False

            async def start_monitoring(self, scope):
                self.scope = scope
                self.started = True
                # Trigger immediately after starting
                await anyio.sleep(0.01)
                await self.trigger_cancelation("Manual trigger")

            async def stop_monitoring(self):
                pass

        source1 = ManualSource()
        source2 = TimeoutSource(timeout=10.0)

        composite = CompositeSource([source1, source2])
        composite.set_cancel_callback(mark_triggered)

        scope = anyio.CancelScope()
        await composite.start_monitoring(scope)

        # Wait for manual source to trigger
        await anyio.sleep(0.05)

        # Should have triggered
        assert triggered[0] is True
        assert scope.cancel_called

        # Cleanup
        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_composite_tracks_triggered_source(self):
        """Test that composite tracks which source triggered."""
        class ManualSource(CancelationSource):
            def __init__(self, name):
                super().__init__(CancelationReason.MANUAL, name)

            async def start_monitoring(self, scope):
                self.scope = scope
                await anyio.sleep(0.01)
                await self.trigger_cancelation("Trigger")

            async def stop_monitoring(self):
                pass

        source1 = ManualSource("source1")
        source2 = ManualSource("source2")

        composite = CompositeSource([source1, source2])

        scope = anyio.CancelScope()
        await composite.start_monitoring(scope)

        await anyio.sleep(0.05)

        # Should track one of the sources triggered (likely the first one)
        assert composite.triggered_source in [source1, source2]

        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_composite_uses_source_reason(self):
        """Test that composite uses the triggering source's reason."""
        class CustomSource(CancelationSource):
            async def start_monitoring(self, scope):
                self.scope = scope
                await anyio.sleep(0.01)
                await self.trigger_cancelation("Custom trigger")

            async def stop_monitoring(self):
                pass

        source = CustomSource(CancelationReason.TIMEOUT, "custom")
        composite = CompositeSource([source])

        scope = anyio.CancelScope()
        await composite.start_monitoring(scope)

        await anyio.sleep(0.05)

        # Should use timeout reason from source
        assert composite.reason == CancelationReason.TIMEOUT

        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_monitor_source_error_handling(self):
        """Test error handling in _monitor_source."""
        class FailingSource(CancelationSource):
            async def start_monitoring(self, scope):
                raise RuntimeError("Source failed to start")

            async def stop_monitoring(self):
                pass

        failing = FailingSource(CancelationReason.MANUAL)
        composite = CompositeSource([failing])

        scope = anyio.CancelScope()
        await composite.start_monitoring(scope)

        # Give time for error to be logged
        await anyio.sleep(0.05)

        # Should handle error gracefully
        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_stop_monitoring_with_exception(self):
        """Test that stop_monitoring handles exceptions from sources gracefully."""
        class FaultySource(TimeoutSource):
            async def stop_monitoring(self):
                raise RuntimeError("Simulated stop error")

        faulty = FaultySource(timeout=1.0)
        normal = TimeoutSource(timeout=2.0)

        composite = CompositeSource([faulty, normal])

        scope = anyio.CancelScope()
        await composite.start_monitoring(scope)

        # Stop should not raise, even though one source fails
        await composite.stop_monitoring()

    @pytest.mark.anyio
    async def test_stop_monitoring_task_group_cleanup(self):
        """Test task group cleanup in stop_monitoring."""
        source = TimeoutSource(timeout=1.0)
        composite = CompositeSource([source])

        scope = anyio.CancelScope()
        await composite.start_monitoring(scope)

        # Immediately stop to test cleanup
        await composite.stop_monitoring()

        # Should have cleaned up task group
        assert composite._task_group is None

    @pytest.mark.anyio
    async def test_stop_monitoring_without_task_group(self):
        """Test stop_monitoring when _task_group doesn't exist."""
        source = TimeoutSource(timeout=1.0)
        composite = CompositeSource([source])

        # Don't call start_monitoring, so _task_group won't exist
        # Just call stop_monitoring directly
        await composite.stop_monitoring()

        # Should complete without error


class TestAnyOfSource:
    """Test AnyOfSource (alias for CompositeSource)."""

    @pytest.mark.anyio
    async def test_any_of_is_alias(self):
        """Test that AnyOfSource is an alias for CompositeSource."""
        source = TimeoutSource(timeout=1.0)
        any_of = AnyOfSource([source])

        assert isinstance(any_of, CompositeSource)


class TestAllOfSource:
    """Test AllOfSource functionality."""

    @pytest.mark.anyio
    async def test_all_of_requires_sources(self):
        """Test that AllOfSource requires at least one source."""
        with pytest.raises(ValueError, match="At least one source is required"):
            AllOfSource([])

    @pytest.mark.anyio
    async def test_all_of_initialization(self):
        """Test AllOfSource initialization."""
        source1 = TimeoutSource(timeout=1.0)
        source2 = TimeoutSource(timeout=2.0)

        all_of = AllOfSource([source1, source2])

        assert all_of.name == "all_of"
        assert len(all_of.sources) == 2
        assert len(all_of.triggered_sources) == 0

    @pytest.mark.anyio
    async def test_all_of_start_monitoring(self):
        """Test AllOfSource start_monitoring."""
        class ManualSource(CancelationSource):
            def __init__(self, name, delay=0.01):
                super().__init__(CancelationReason.MANUAL, name)
                self.delay = delay

            async def start_monitoring(self, scope):
                self.scope = scope
                await anyio.sleep(self.delay)
                await self.trigger_cancelation(f"{self.name} triggered")

            async def stop_monitoring(self):
                pass

        source1 = ManualSource("s1", 0.01)
        source2 = ManualSource("s2", 0.02)

        all_of = AllOfSource([source1, source2])

        scope = anyio.CancelScope()
        await all_of.start_monitoring(scope)

        # Wait for both to trigger
        await anyio.sleep(0.05)

        # Should have triggered when both sources triggered
        assert len(all_of.triggered_sources) == 2
        assert scope.cancel_called

        await all_of.stop_monitoring()

    @pytest.mark.anyio
    async def test_all_of_waits_for_all_sources(self):
        """Test that AllOfSource waits for all sources before triggering."""
        class ManualSource(CancelationSource):
            def __init__(self, name, should_trigger):
                super().__init__(CancelationReason.MANUAL, name)
                self.should_trigger = should_trigger

            async def start_monitoring(self, scope):
                self.scope = scope
                if self.should_trigger:
                    await anyio.sleep(0.01)
                    await self.trigger_cancelation(f"{self.name} triggered")
                # else: never triggers

            async def stop_monitoring(self):
                pass

        source1 = ManualSource("s1", should_trigger=True)
        source2 = ManualSource("s2", should_trigger=False)  # Won't trigger

        all_of = AllOfSource([source1, source2])

        scope = anyio.CancelScope()
        await all_of.start_monitoring(scope)

        # Wait for first source
        await anyio.sleep(0.05)

        # Should NOT have cancelled yet (only 1 of 2 triggered)
        assert len(all_of.triggered_sources) == 1
        assert not scope.cancel_called

        await all_of.stop_monitoring()

    @pytest.mark.anyio
    async def test_all_of_stop_monitoring(self):
        """Test AllOfSource stop_monitoring."""
        source = TimeoutSource(timeout=1.0)
        all_of = AllOfSource([source])

        scope = anyio.CancelScope()
        await all_of.start_monitoring(scope)

        await all_of.stop_monitoring()

        # Task group should be cleaned up
        assert all_of._task_group.cancel_scope.cancel_called

    @pytest.mark.anyio
    async def test_all_of_monitor_source_error(self):
        """Test AllOfSource _monitor_source error handling."""
        class FailingSource(CancelationSource):
            async def start_monitoring(self, scope):
                raise RuntimeError("Source failed")

            async def stop_monitoring(self):
                pass

        failing = FailingSource(CancelationReason.MANUAL)
        all_of = AllOfSource([failing])

        scope = anyio.CancelScope()
        await all_of.start_monitoring(scope)

        await anyio.sleep(0.05)

        # Should handle error gracefully
        await all_of.stop_monitoring()

    @pytest.mark.anyio
    async def test_all_of_stop_monitoring_without_task_group(self):
        """Test AllOfSource stop_monitoring when _task_group doesn't exist."""
        source = TimeoutSource(timeout=1.0)
        all_of = AllOfSource([source])

        # Don't call start_monitoring, so _task_group won't exist
        await all_of.stop_monitoring()

        # Should complete without error

    @pytest.mark.anyio
    async def test_all_of_stop_monitoring_source_error(self):
        """Test AllOfSource handles errors during source.stop_monitoring."""
        class FailingStopSource(TimeoutSource):
            async def stop_monitoring(self):
                raise RuntimeError("Stop failed")

        failing = FailingStopSource(timeout=1.0)
        normal = TimeoutSource(timeout=2.0)

        all_of = AllOfSource([failing, normal])

        scope = anyio.CancelScope()
        await all_of.start_monitoring(scope)

        # Stop should not raise, even though one source fails
        await all_of.stop_monitoring()
