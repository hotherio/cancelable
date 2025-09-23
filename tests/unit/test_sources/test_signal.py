"""Unit tests for signal cancellation source."""

import signal

import anyio
import pytest

from cancelable.sources.signal import SignalSource


class TestSignalSource:
    """Test SignalSource functionality."""

    @pytest.mark.anyio
    async def test_signal_registration(self):
        """Test signal handler registration."""
        source = SignalSource(signal.SIGUSR1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Check handler is registered
        assert signal.SIGUSR1 in SignalSource._handlers

        await source.stop_monitoring()

    @pytest.mark.anyio
    async def test_multiple_signal_sources(self):
        """Test multiple sources for same signal."""
        source1 = SignalSource(signal.SIGUSR1)
        source2 = SignalSource(signal.SIGUSR1)

        scope1 = anyio.CancelScope()
        scope2 = anyio.CancelScope()

        await source1.start_monitoring(scope1)
        await source2.start_monitoring(scope2)

        # Both should be registered
        assert len(SignalSource._handlers[signal.SIGUSR1]) >= 2

        await source1.stop_monitoring()
        await source2.stop_monitoring()

    @pytest.mark.anyio
    async def test_signal_cleanup(self):
        """Test signal handler cleanup."""
        source = SignalSource(signal.SIGUSR1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)
        await source.stop_monitoring()

        # Handler should be cleaned up if no other sources
        if signal.SIGUSR1 in SignalSource._handlers:
            assert len(SignalSource._handlers[signal.SIGUSR1]) == 0
