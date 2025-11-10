"""
Unit tests for anyio_bridge.py utilities.
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

from hother.cancelable.utils.anyio_bridge import AnyioBridge, call_soon_threadsafe


class TestAnyioBridge:
    """Test AnyioBridge functionality."""

    def test_singleton_pattern(self):
        """Test singleton pattern works correctly."""
        # Reset singleton for clean test
        AnyioBridge._instance = None

        bridge1 = AnyioBridge.get_instance()
        bridge2 = AnyioBridge.get_instance()

        assert bridge1 is bridge2
        assert isinstance(bridge1, AnyioBridge)

    @pytest.mark.anyio
    async def test_bridge_initialization(self):
        """Test bridge initialization."""
        bridge = AnyioBridge(buffer_size=500)

        assert not bridge.is_started
        assert bridge._buffer_size == 500
        assert bridge._send_stream is None
        assert bridge._receive_stream is None
        assert bridge._started is False
        assert len(bridge._pending_callbacks) == 0

    @pytest.mark.anyio
    async def test_bridge_queuing_before_start(self):
        """Test callback queuing when bridge not started."""
        bridge = AnyioBridge()
        called = []

        def callback():
            called.append("called")

        # Call before starting
        bridge.call_soon_threadsafe(callback)
        assert len(called) == 0  # Not called yet
        assert len(bridge._pending_callbacks) == 1

        # Call again
        bridge.call_soon_threadsafe(lambda: called.append("called2"))
        assert len(bridge._pending_callbacks) == 2

    @pytest.mark.anyio
    async def test_bridge_start_processes_pending(self):
        """Test that starting bridge processes pending callbacks."""
        bridge = AnyioBridge()

        # Queue callbacks before starting
        called = []
        bridge.call_soon_threadsafe(lambda: called.append("pending1"))
        bridge.call_soon_threadsafe(lambda: called.append("pending2"))

        # Mock the streams and worker to avoid infinite loop
        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock) as mock_worker:

            mock_send, mock_receive = MagicMock(), MagicMock()
            mock_stream.return_value = (mock_send, mock_receive)

            # Start the bridge
            start_task = asyncio.create_task(bridge.start())

            # Wait a bit for initialization
            await anyio.sleep(0.01)

            # Should be started
            assert bridge.is_started
            assert bridge._send_stream is mock_send
            assert bridge._receive_stream is mock_receive

            # Should have processed pending callbacks
            assert mock_send.send_nowait.call_count == 2

            # Cancel the start task to avoid hanging
            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_call_soon_threadsafe_after_start(self):
        """Test calling callbacks after bridge is started."""
        bridge = AnyioBridge()

        # Mock the streams
        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock):

            mock_send, mock_receive = MagicMock(), MagicMock()
            mock_stream.return_value = (mock_send, mock_receive)

            # Start bridge
            start_task = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)  # Let it initialize

            # Now call callback
            def callback():
                pass

            bridge.call_soon_threadsafe(callback)

            # Should go directly to stream
            mock_send.send_nowait.assert_called_with(callback)

            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_bridge_queue_full_handling(self):
        """Test behavior when bridge queue is full."""
        bridge = AnyioBridge()

        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock):

            mock_send, mock_receive = MagicMock(), MagicMock()
            mock_send.send_nowait.side_effect = anyio.WouldBlock()
            mock_stream.return_value = (mock_send, mock_receive)

            # Start bridge
            start_task = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)

            # Call callback when queue is full
            def callback():
                pass

            # Should not raise exception, just drop the callback
            bridge.call_soon_threadsafe(callback)

            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_convenience_function(self):
        """Test the global call_soon_threadsafe convenience function."""
        # Reset singleton
        AnyioBridge._instance = None

        # Mock the instance
        with patch.object(AnyioBridge, 'get_instance') as mock_get_instance:
            mock_bridge = MagicMock()
            mock_get_instance.return_value = mock_bridge

            def callback():
                pass

            call_soon_threadsafe(callback)

            mock_bridge.call_soon_threadsafe.assert_called_with(callback)

    @pytest.mark.anyio
    async def test_multiple_bridge_instances(self):
        """Test that multiple bridge instances are independent."""
        bridge1 = AnyioBridge()
        bridge2 = AnyioBridge()

        assert bridge1 is not bridge2

        # Each should have independent pending queues
        bridge1.call_soon_threadsafe(lambda: None)
        bridge2.call_soon_threadsafe(lambda: None)

        assert len(bridge1._pending_callbacks) == 1
        assert len(bridge2._pending_callbacks) == 1

    @pytest.mark.anyio
    async def test_bridge_start_already_started_warning(self):
        """Test warning when calling start() on already started bridge."""
        bridge = AnyioBridge()

        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock):

            mock_send, mock_receive = MagicMock(), MagicMock()
            mock_stream.return_value = (mock_send, mock_receive)

            # Start bridge first time
            start_task1 = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)

            assert bridge.is_started

            # Try to start again - should log warning and return early
            start_task2 = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)

            # Second start should complete without error
            assert bridge.is_started

            # Cleanup
            start_task1.cancel()
            start_task2.cancel()
            try:
                await start_task1
            except asyncio.CancelledError:
                pass
            try:
                await start_task2
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_bridge_pending_callback_queue_full_on_startup(self):
        """Test WouldBlock handling when processing pending callbacks during startup."""
        bridge = AnyioBridge(buffer_size=1)

        # Queue multiple callbacks before starting
        for i in range(5):
            bridge.call_soon_threadsafe(lambda: None)

        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock):

            mock_send, mock_receive = MagicMock(), MagicMock()
            # Make send_nowait raise WouldBlock after first callback
            mock_send.send_nowait.side_effect = [None, anyio.WouldBlock(), anyio.WouldBlock(), anyio.WouldBlock(), anyio.WouldBlock()]
            mock_stream.return_value = (mock_send, mock_receive)

            # Start bridge - should handle WouldBlock gracefully
            start_task = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)

            assert bridge.is_started
            # First callback should succeed, rest should be dropped
            assert mock_send.send_nowait.call_count >= 2

            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_call_soon_threadsafe_send_exception(self):
        """Test exception handling in call_soon_threadsafe."""
        bridge = AnyioBridge()

        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock):

            mock_send, mock_receive = MagicMock(), MagicMock()
            # Make send_nowait raise a different exception (not WouldBlock)
            mock_send.send_nowait.side_effect = RuntimeError("Simulated send error")
            mock_stream.return_value = (mock_send, mock_receive)

            # Start bridge
            start_task = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)

            # Call callback - should handle exception gracefully
            def callback():
                pass

            # Should not raise, exception should be caught and logged
            bridge.call_soon_threadsafe(callback)

            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_worker_end_of_stream_handling(self):
        """Test that worker gracefully handles EndOfStream."""
        bridge = AnyioBridge()

        # Create real streams
        send_stream, receive_stream = anyio.create_memory_object_stream(10)
        bridge._send_stream = send_stream
        bridge._receive_stream = receive_stream
        bridge._started = True

        # Start worker
        worker_task = asyncio.create_task(bridge._worker())

        # Close the send stream to trigger EndOfStream on receive
        await send_stream.aclose()

        # Wait for worker to complete
        await anyio.sleep(0.1)

        # Worker should complete gracefully
        assert worker_task.done()

        # Clean up receive stream
        await receive_stream.aclose()

    @pytest.mark.anyio
    async def test_worker_exception_handling(self):
        """Test that worker handles general exceptions."""
        bridge = AnyioBridge()

        # Create a mock receive stream that raises an exception
        mock_receive = AsyncMock()
        mock_receive.receive.side_effect = RuntimeError("Simulated worker error")

        bridge._receive_stream = mock_receive
        bridge._started = True

        # Start worker - should handle exception and exit
        worker_task = asyncio.create_task(bridge._worker())

        # Wait for worker to handle exception
        await anyio.sleep(0.1)

        # Worker should complete despite exception
        assert worker_task.done()

    def test_singleton_double_check_locking(self):
        """Test the inner check of double-check locking pattern in get_instance."""
        # This test forces the race condition where multiple threads
        # pass the outer check but only one creates the instance

        import time

        # Reset singleton
        AnyioBridge._instance = None

        instances = []
        thread1_in_lock = threading.Event()

        # Save original __init__
        original_init = AnyioBridge.__init__

        def slow_init(self, buffer_size=1000):
            """Slow init that signals when called."""
            thread1_in_lock.set()
            # Give time for thread2 to also pass the outer check and wait on lock
            time.sleep(0.02)
            original_init(self, buffer_size)

        def thread1_func():
            """First thread - creates the instance with delay."""
            with patch.object(AnyioBridge, '__init__', slow_init):
                instance = AnyioBridge.get_instance()
                instances.append(instance)

        def thread2_func():
            """Second thread - waits for thread1 to be in lock."""
            # Wait for thread1 to be creating the instance (inside lock)
            thread1_in_lock.wait(timeout=1.0)

            # Small delay to ensure we're blocked on the lock
            time.sleep(0.005)

            # Now call get_instance - we'll pass outer check (instance still being created)
            # Then wait for lock, and when we get it, inner check finds instance exists
            instance = AnyioBridge.get_instance()
            instances.append(instance)

        # Start both threads
        t1 = threading.Thread(target=thread1_func)
        t2 = threading.Thread(target=thread2_func)

        t1.start()
        t2.start()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        # Both should have the same instance
        assert len(instances) == 2
        assert instances[0] is instances[1]
        assert isinstance(instances[0], AnyioBridge)

    @pytest.mark.anyio
    async def test_stop_method_closes_streams(self):
        """Test that stop() properly closes send and receive streams."""
        bridge = AnyioBridge()

        # Create and start bridge
        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock):

            mock_send, mock_receive = AsyncMock(), AsyncMock()
            mock_stream.return_value = (mock_send, mock_receive)

            # Start bridge
            start_task = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)

            assert bridge.is_started
            assert bridge._send_stream is mock_send
            assert bridge._receive_stream is mock_receive

            # Stop the bridge
            await bridge.stop()

            # Should have called aclose on both streams
            mock_send.aclose.assert_called_once()
            mock_receive.aclose.assert_called_once()

            # Should reset state
            assert not bridge.is_started
            assert bridge._send_stream is None
            assert bridge._receive_stream is None

            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_stop_method_handles_stream_close_errors(self):
        """Test that stop() handles exceptions during stream closing."""
        bridge = AnyioBridge()

        with patch('anyio.create_memory_object_stream') as mock_stream, \
             patch.object(bridge, '_worker', new_callable=AsyncMock):

            mock_send, mock_receive = AsyncMock(), AsyncMock()
            # Make streams raise exceptions on aclose
            mock_send.aclose.side_effect = RuntimeError("Send stream close error")
            mock_receive.aclose.side_effect = RuntimeError("Receive stream close error")
            mock_stream.return_value = (mock_send, mock_receive)

            # Start bridge
            start_task = asyncio.create_task(bridge.start())
            await anyio.sleep(0.01)

            # Stop should handle exceptions gracefully
            await bridge.stop()

            # Should still reset state despite errors
            assert not bridge.is_started
            assert bridge._send_stream is None
            assert bridge._receive_stream is None

            start_task.cancel()
            try:
                await start_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.anyio
    async def test_stop_method_when_streams_dont_exist(self):
        """Test that stop() handles case where streams don't exist."""
        bridge = AnyioBridge()

        # Stop without starting (no streams exist)
        await bridge.stop()

        # Should handle gracefully
        assert not bridge.is_started
        assert bridge._send_stream is None
        assert bridge._receive_stream is None