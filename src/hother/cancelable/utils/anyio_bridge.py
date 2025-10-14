"""
Global bridge for thread-safe anyio operations.

Allows regular Python threads to schedule callbacks in anyio context,
providing an equivalent to asyncio's loop.call_soon_threadsafe().
"""

from __future__ import annotations

import anyio
import threading
from typing import Callable, Self
from collections import deque

from .logging import get_logger

logger = get_logger(__name__)


class AnyioBridge:
    """
    Singleton bridge for thread-to-anyio communication.

    Provides call_soon_threadsafe equivalent for anyio by using
    memory object streams and a background worker task.

    Example:
        ```python
        bridge = AnyioBridge.get_instance()

        async with anyio.create_task_group() as tg:
            tg.start_soon(bridge.start)

            # Now thread-safe calls work
            def from_thread():
                bridge.call_soon_threadsafe(some_callback)
        ```
    """

    _instance: AnyioBridge | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._send_stream: anyio.abc.ObjectSendStream | None = None
        self._receive_stream: anyio.abc.ObjectReceiveStream | None = None
        self._started: bool = False

        # Fallback queue for callbacks received before bridge starts
        self._pending_callbacks: deque[Callable] = deque()
        self._pending_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> Self:
        """
        Get singleton instance of the bridge.

        Thread-safe lazy initialization.

        Returns:
            The singleton AnyioBridge instance
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def start(self) -> None:
        """
        Start the bridge worker task.

        Should be called once at application startup from async context.
        Must be run in a task group as it blocks forever.

        Example:
            ```python
            async with anyio.create_task_group() as tg:
                tg.start_soon(bridge.start)
                # Bridge is now running
            ```
        """
        if self._started:
            logger.warning("Bridge already started, ignoring duplicate start")
            logger.info(f"Bridge worker alive check - stream is: {self._receive_stream}")
            return

        logger.debug("Starting anyio bridge")

        # Create communication streams
        self._send_stream, self._receive_stream = \
            anyio.create_memory_object_stream(1000)

        # Process any pending callbacks that arrived before bridge started
        with self._pending_lock:
            pending_count = len(self._pending_callbacks)
            if pending_count > 0:
                logger.info(f"Processing {pending_count} pending callbacks")
                while self._pending_callbacks:
                    callback = self._pending_callbacks.popleft()
                    try:
                        self._send_stream.send_nowait(callback)
                    except anyio.WouldBlock:
                        logger.warning("Bridge queue full during startup, callback dropped")

        self._started = True
        logger.info("Anyio bridge started and ready")

        # Start worker loop (blocks forever)
        await self._worker()

    async def _worker(self) -> None:
        """
        Worker task that processes callbacks from threads.

        Runs forever until the receive stream is closed.
        """
        logger.info("Bridge worker started, waiting for callbacks...")
        try:
            while True:
                # Explicitly receive next callback (yields properly)
                logger.debug("Bridge worker waiting for next callback...")
                callback = await self._receive_stream.receive()
                logger.debug(f"Bridge worker received callback: {callback}")

                try:
                    # Execute callback
                    logger.debug("Bridge worker executing callback...")
                    result = callback()
                    logger.debug(f"Callback result: {result}")

                    # If it's a coroutine, await it
                    if hasattr(result, '__await__'):
                        logger.debug("Callback is coroutine, awaiting...")
                        await result
                        logger.debug("Coroutine completed")
                    else:
                        logger.debug("Callback completed (sync)")
                except Exception as e:
                    logger.error(
                        f"Bridge callback error: {e}",
                        exc_info=True
                    )

                # Explicitly yield control to anyio scheduler
                await anyio.sleep(0)

        except anyio.EndOfStream:
            logger.info("Bridge stream closed, worker ending normally")
        except Exception as e:
            logger.error(
                f"Bridge worker error: {e}",
                exc_info=True
            )

        logger.warning("Bridge worker loop ended")

    def call_soon_threadsafe(self, callback: Callable) -> None:
        """
        Schedule callback to run in anyio context from any thread.

        This is the anyio equivalent of asyncio's loop.call_soon_threadsafe().
        The callback will be executed in the anyio event loop context.

        Args:
            callback: Function to call (can be sync or async)

        Note:
            If the bridge hasn't started yet, callbacks are queued
            and will be processed once the bridge starts.
        """
        if not self._started:
            # Queue for later processing
            with self._pending_lock:
                self._pending_callbacks.append(callback)
                logger.debug(
                    f"Bridge not started, queuing callback "
                    f"(queue size: {len(self._pending_callbacks)})"
                )
            return

        logger.debug(f"Queueing callback to bridge: {callback}")
        try:
            self._send_stream.send_nowait(callback)
            logger.debug("Callback successfully queued to bridge stream")
        except anyio.WouldBlock:
            logger.warning(
                "Bridge queue full (1000 callbacks), "
                "callback dropped - consider increasing buffer size"
            )
        except Exception as e:
            logger.error(f"Failed to schedule callback: {e}", exc_info=True)

    @property
    def is_started(self) -> bool:
        """Check if bridge is started and ready."""
        return self._started


# Global convenience function
def call_soon_threadsafe(callback: Callable) -> None:
    """
    Convenience function for thread-safe anyio scheduling.

    Equivalent to bridge.get_instance().call_soon_threadsafe(callback).

    Args:
        callback: Function to call in anyio context

    Example:
        ```python
        def on_signal(signum):
            # Called from signal handler thread
            async def cancel_operation():
                await token.cancel()

            call_soon_threadsafe(cancel_operation)
        ```
    """
    bridge = AnyioBridge.get_instance()
    bridge.call_soon_threadsafe(callback)
