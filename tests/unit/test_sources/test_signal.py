"""Unit tests for signal cancelation source."""

import signal
import os

import anyio
import pytest

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.signal import SignalSource


class TestSignalSource:
    """Test SignalSource functionality."""

    @pytest.mark.anyio
    async def test_default_signals(self):
        """Test that SignalSource defaults to SIGINT and SIGTERM."""
        source = SignalSource()

        # Should default to SIGINT and SIGTERM
        assert signal.SIGINT in source.signals
        assert signal.SIGTERM in source.signals

    @pytest.mark.anyio
    async def test_custom_signals(self):
        """Test SignalSource with custom signals."""
        source = SignalSource(signal.SIGUSR1, signal.SIGUSR2)

        assert signal.SIGUSR1 in source.signals
        assert signal.SIGUSR2 in source.signals
        assert len(source.signals) == 2

    @pytest.mark.anyio
    async def test_invalid_signal_type(self):
        """Test that SignalSource raises TypeError for non-integer signal."""
        with pytest.raises(TypeError, match="Signal must be an integer"):
            SignalSource("not_a_signal")

    @pytest.mark.anyio
    async def test_signal_monitoring_lifecycle(self):
        """Test signal source monitoring starts and stops correctly."""
        source = SignalSource(signal.SIGUSR1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Task group should be created
        assert source._task_group is not None
        assert source.scope is scope

        await source.stop_monitoring()

        # Task group should be cleaned up
        assert source._task_group is None

    @pytest.mark.anyio
    async def test_signal_reason(self):
        """Test signal source has correct cancelation reason."""
        source = SignalSource()
        assert source.reason == CancelationReason.SIGNAL

    @pytest.mark.anyio
    async def test_multiple_stops_safe(self):
        """Test that calling stop_monitoring multiple times is safe."""
        source = SignalSource(signal.SIGUSR1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)
        await source.stop_monitoring()

        # Second stop should be safe (no-op)
        await source.stop_monitoring()

    @pytest.mark.anyio
    async def test_stop_monitoring_with_exception(self):
        """Test that stop_monitoring handles task group exit exceptions gracefully."""
        source = SignalSource(signal.SIGUSR1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Mock the task group's __aexit__ to raise an exception
        original_aexit = source._task_group.__aexit__

        async def mock_aexit(*args):
            raise RuntimeError("Simulated task group cleanup error")

        source._task_group.__aexit__ = mock_aexit

        # Should not raise - should suppress exception and clean up
        await source.stop_monitoring()

        # Task group should be cleared despite exception
        assert source._task_group is None
