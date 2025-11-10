"""
Unit tests for CancelationSource base class.
"""

import anyio
import pytest

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.base import CancelationSource


class MockCancelationSource(CancelationSource):
    """Concrete implementation of CancelationSource for testing."""

    def __init__(self, reason: CancelationReason = CancelationReason.MANUAL, name: str | None = None):
        super().__init__(reason, name)
        self.start_called = False
        self.stop_called = False

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """Start monitoring."""
        await super().start_monitoring(scope)
        self.start_called = True

    async def stop_monitoring(self) -> None:
        """Stop monitoring."""
        await super().stop_monitoring()
        self.stop_called = True


class TestCancelationSource:
    """Test CancelationSource base class functionality."""

    def test_init_with_name(self):
        """Test initialization with custom name."""
        source = MockCancelationSource(CancelationReason.TIMEOUT, name="CustomSource")
        assert source.reason == CancelationReason.TIMEOUT
        assert source.name == "CustomSource"
        assert source.scope is None
        assert source._cancel_callback is None
        assert source._monitoring_task is None
        assert source.triggered is False

    def test_init_default_name(self):
        """Test initialization with default name (class name)."""
        source = MockCancelationSource(CancelationReason.MANUAL)
        assert source.name == "MockCancelationSource"

    @pytest.mark.anyio
    async def test_start_monitoring_sets_scope(self):
        """Test that start_monitoring sets the scope."""
        source = MockCancelationSource()
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        assert source.scope is scope
        assert source.start_called is True

    @pytest.mark.anyio
    async def test_stop_monitoring_cleans_up(self):
        """Test that stop_monitoring cleans up monitoring task."""
        source = MockCancelationSource()

        # Set a mock monitoring task
        mock_task = anyio.CancelScope()
        source._monitoring_task = mock_task

        await source.stop_monitoring()

        assert source._monitoring_task is None
        assert source.stop_called is True

    def test_set_cancel_callback(self):
        """Test setting cancel callback."""
        source = MockCancelationSource()
        callback_called = [False]

        def callback(reason, message):
            callback_called[0] = True

        source.set_cancel_callback(callback)

        assert source._cancel_callback is callback

    @pytest.mark.anyio
    async def test_trigger_cancelation_basic(self):
        """Test basic cancelation triggering."""
        source = MockCancelationSource(CancelationReason.TIMEOUT)
        scope = anyio.CancelScope()
        source.scope = scope

        await source.trigger_cancelation("Test message")

        assert scope.cancel_called

    @pytest.mark.anyio
    async def test_trigger_cancelation_with_sync_callback(self):
        """Test cancelation with synchronous callback."""
        source = MockCancelationSource()
        scope = anyio.CancelScope()
        source.scope = scope

        callback_called = [False]
        callback_reason = [None]
        callback_message = [None]

        def callback(reason, message):
            callback_called[0] = True
            callback_reason[0] = reason
            callback_message[0] = message

        source.set_cancel_callback(callback)
        await source.trigger_cancelation("Test message")

        assert callback_called[0]
        assert callback_reason[0] == CancelationReason.MANUAL
        assert callback_message[0] == "Test message"
        assert scope.cancel_called

    @pytest.mark.anyio
    async def test_trigger_cancelation_with_async_callback(self):
        """Test cancelation with asynchronous callback."""
        source = MockCancelationSource()
        scope = anyio.CancelScope()
        source.scope = scope

        callback_called = [False]

        async def async_callback(reason, message):
            callback_called[0] = True
            await anyio.sleep(0.01)

        source.set_cancel_callback(async_callback)
        await source.trigger_cancelation("Async test")

        assert callback_called[0]
        assert scope.cancel_called

    @pytest.mark.anyio
    async def test_trigger_cancelation_callback_error(self):
        """Test that callback errors don't prevent cancelation."""
        source = MockCancelationSource()
        scope = anyio.CancelScope()
        source.scope = scope

        def faulty_callback(reason, message):
            raise RuntimeError("Callback error")

        source.set_cancel_callback(faulty_callback)
        # Should not raise, callback error should be caught
        await source.trigger_cancelation("Test")

        # Scope should still be cancelled despite callback error
        assert scope.cancel_called

    @pytest.mark.anyio
    async def test_trigger_cancelation_already_cancelled(self):
        """Test triggering when scope is already cancelled."""
        source = MockCancelationSource()
        scope = anyio.CancelScope()
        scope.cancel()  # Already cancelled
        source.scope = scope

        callback_called = [False]

        def callback(reason, message):
            callback_called[0] = True

        source.set_cancel_callback(callback)
        # Should not call callback when already cancelled
        await source.trigger_cancelation("Test")

        assert not callback_called[0]

    def test_str_representation(self):
        """Test string representation."""
        source = MockCancelationSource(CancelationReason.TIMEOUT, name="TestSource")
        str_repr = str(source)

        assert "TestSource" in str_repr
        assert "timeout" in str_repr
