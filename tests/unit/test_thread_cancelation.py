"""
Tests for thread-safe cancelation with anyio bridge.

This module tests the thread-safe cancelation features including:
- AnyioBridge thread-to-async communication
- CancelationToken.cancel_sync() method
- Signal handler integration via bridge
- pynput-like keyboard listener scenarios
"""

from __future__ import annotations

import threading
import time
from typing import Any

import anyio
import pytest

from hother.cancelable import AnyioBridge, CancelationToken, call_soon_threadsafe
from hother.cancelable.core.models import CancelationReason


pytestmark = pytest.mark.anyio


@pytest.fixture
async def bridge():
    """Fixture to provide a running bridge instance for each test."""
    # Reset singleton for clean state
    AnyioBridge._instance = None
    bridge_instance = AnyioBridge.get_instance()

    # Start bridge in task group
    async with anyio.create_task_group() as tg:
        tg.start_soon(bridge_instance.start)
        await anyio.sleep(0.2)  # Give bridge time to start

        yield bridge_instance

        # Cleanup: stop bridge properly before cancelling
        await bridge_instance.stop()
        tg.cancel_scope.cancel()


class TestAnyioBridge:
    """Test cases for AnyioBridge thread-safe communication."""

    async def test_bridge_singleton(self, bridge):
        """Test that AnyioBridge is a singleton."""
        bridge2 = AnyioBridge.get_instance()
        assert bridge is bridge2

    async def test_bridge_starts_successfully(self, bridge):
        """Test that bridge starts without errors."""
        assert bridge.is_started

    async def test_bridge_executes_callback_from_thread(self, bridge):
        """Test that bridge executes callbacks scheduled from threads."""
        result = []

        def callback_from_thread():
            result.append("executed")

        # Schedule callback from thread
        def run_in_thread():
            call_soon_threadsafe(callback_from_thread)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        # Wait for callback to execute
        await anyio.sleep(0.3)

        assert result == ["executed"]

    async def test_bridge_executes_async_callback_from_thread(self, bridge):
        """Test that bridge executes async callbacks scheduled from threads."""
        result = []

        async def async_callback():
            await anyio.sleep(0.05)
            result.append("async_executed")

        # Schedule async callback from thread
        def run_in_thread():
            call_soon_threadsafe(async_callback)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        # Wait for callback to execute
        await anyio.sleep(0.4)

        assert result == ["async_executed"]

    async def test_bridge_handles_multiple_callbacks(self, bridge):
        """Test that bridge handles multiple callbacks correctly."""
        results = []

        # Schedule multiple callbacks from thread
        def run_in_thread():
            for i in range(5):
                call_soon_threadsafe(lambda idx=i: results.append(idx))
                time.sleep(0.01)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()

        # Wait for callbacks to execute
        await anyio.sleep(0.4)

        assert sorted(results) == [0, 1, 2, 3, 4]


class TestTokenCancelSync:
    """Test cases for CancelationToken.cancel_sync() method."""

    async def test_cancel_sync_from_thread(self, bridge):
        """Test that cancel_sync() can be called from a thread."""
        token = CancelationToken()

        # Cancel from thread
        def cancel_in_thread():
            result = token.cancel_sync(
                reason=CancelationReason.MANUAL, message="Cancelled from thread"
            )
            assert result is True

        thread = threading.Thread(target=cancel_in_thread)
        thread.start()
        thread.join()

        # Wait for cancelation to propagate
        await anyio.sleep(0.3)

        # Verify token is cancelled
        assert token.is_cancelled
        assert token.reason == CancelationReason.MANUAL
        assert token.message == "Cancelled from thread"

    async def test_cancel_sync_sets_event(self, bridge):
        """Test that cancel_sync() sets the anyio event via bridge."""
        token = CancelationToken()

        # Start task waiting for cancelation
        async def waiter():
            await token.wait_for_cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(waiter)
            await anyio.sleep(0.1)  # Let waiter start

            # Cancel from thread
            def cancel_in_thread():
                token.cancel_sync()

            thread = threading.Thread(target=cancel_in_thread)
            thread.start()
            thread.join()

            # Wait for event to be set
            await anyio.sleep(0.3)

            # Verify waiter completed (token is cancelled)
            assert token.is_cancelled

            tg.cancel_scope.cancel()

    async def test_cancel_sync_triggers_callbacks(self, bridge):
        """Test that cancel_sync() triggers registered callbacks."""
        token = CancelationToken()
        callback_executed = []

        async def my_callback(t: CancelationToken):
            callback_executed.append(True)
            assert t.is_cancelled

        # Register callback
        await token.register_callback(my_callback)

        # Cancel from thread
        def cancel_in_thread():
            token.cancel_sync()

        thread = threading.Thread(target=cancel_in_thread)
        thread.start()
        thread.join()

        # Wait for callback to execute
        await anyio.sleep(0.4)

        assert callback_executed == [True]

    async def test_cancel_sync_idempotent(self, bridge):
        """Test that cancel_sync() is idempotent."""
        token = CancelationToken()

        # Cancel twice from thread
        def cancel_in_thread():
            result1 = token.cancel_sync()
            result2 = token.cancel_sync()
            assert result1 is True
            assert result2 is False  # Already cancelled

        thread = threading.Thread(target=cancel_in_thread)
        thread.start()
        thread.join()

        await anyio.sleep(0.2)

        assert token.is_cancelled

    async def test_cancel_sync_thread_safe(self, bridge):
        """Test that cancel_sync() is thread-safe with multiple threads."""
        token = CancelationToken()
        success_count = []

        # Try to cancel from multiple threads simultaneously
        def cancel_in_thread():
            if token.cancel_sync():
                success_count.append(1)

        threads = [threading.Thread(target=cancel_in_thread) for _ in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        await anyio.sleep(0.3)

        # Only one thread should succeed
        assert sum(success_count) == 1
        assert token.is_cancelled


class TestPynputScenario:
    """Test cases simulating pynput-like keyboard listener scenarios."""

    async def test_keyboard_listener_simulation(self, bridge):
        """Test simulated keyboard listener cancelling operation."""
        token = CancelationToken()

        class SimulatedKeyboardHandler:
            """Simulates pynput keyboard listener."""

            def __init__(self, token: CancelationToken):
                self.token = token
                self.listener_thread = None

            def on_key_press(self, key: str):
                """Simulates key press callback from pynput thread."""
                if key == "SPACE":
                    # Cancel token from keyboard thread
                    self.token.cancel_sync(
                        reason=CancelationReason.MANUAL, message="User pressed SPACE"
                    )

            def start(self):
                """Start simulated listener thread."""

                def run():
                    time.sleep(0.2)  # Simulate some delay
                    self.on_key_press("SPACE")  # Simulate space press

                self.listener_thread = threading.Thread(target=run)
                self.listener_thread.start()

            def join(self):
                """Wait for listener thread."""
                if self.listener_thread:
                    self.listener_thread.join()

        # Start keyboard listener
        kb = SimulatedKeyboardHandler(token)
        kb.start()

        # Wait for token to be cancelled
        with anyio.fail_after(2.0):
            await token.wait_for_cancel()

        kb.join()

        assert token.is_cancelled
        assert token.reason == CancelationReason.MANUAL
        assert "SPACE" in token.message

    async def test_streaming_with_keyboard_cancelation(self, bridge):
        """Test LLM-like streaming with keyboard cancelation."""
        token = CancelationToken()
        chunks_processed = []

        # Simulate keyboard handler
        class KeyboardHandler:
            def __init__(self, token: CancelationToken):
                self.token = token

            def trigger_cancel_from_thread(self):
                time.sleep(0.3)  # Wait a bit
                self.token.cancel_sync()

        async def stream_chunks():
            """Simulate streaming chunks of data."""
            for i in range(20):
                if token.is_cancelled:
                    break
                chunks_processed.append(i)
                await anyio.sleep(0.1)

        # Start keyboard handler in thread
        kb = KeyboardHandler(token)
        cancel_thread = threading.Thread(target=kb.trigger_cancel_from_thread)
        cancel_thread.start()

        # Start streaming
        await stream_chunks()

        cancel_thread.join()

        # Should have processed some but not all chunks
        assert 0 < len(chunks_processed) < 20
        assert token.is_cancelled


class TestBridgeErrorHandling:
    """Test error handling in bridge and cancel_sync."""

    async def test_bridge_handles_callback_errors(self, bridge):
        """Test that bridge handles errors in callbacks gracefully."""

        def failing_callback():
            raise ValueError("Intentional test error")

        result = []

        def successful_callback():
            result.append("success")

        # Schedule failing and successful callbacks
        call_soon_threadsafe(failing_callback)
        call_soon_threadsafe(successful_callback)

        await anyio.sleep(0.4)

        # Successful callback should still execute
        assert result == ["success"]

    async def test_cancel_sync_with_failing_callback(self, bridge):
        """Test that cancel_sync continues even if a callback fails."""
        token = CancelationToken()
        successful_callbacks = []

        async def failing_callback(t: CancelationToken):
            raise ValueError("Callback error")

        async def successful_callback(t: CancelationToken):
            successful_callbacks.append(True)

        # Register callbacks
        await token.register_callback(failing_callback)
        await token.register_callback(successful_callback)

        # Cancel from thread
        def cancel_in_thread():
            token.cancel_sync()

        thread = threading.Thread(target=cancel_in_thread)
        thread.start()
        thread.join()

        await anyio.sleep(0.4)

        # Token should be cancelled and successful callback executed
        assert token.is_cancelled
        assert successful_callbacks == [True]
