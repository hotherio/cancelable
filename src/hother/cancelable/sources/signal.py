"""
Signal-based cancellation source implementation.
"""

from __future__ import annotations

import signal
import weakref
from collections.abc import Callable

import anyio

from hother.cancelable.core.models import CancellationReason
from hother.cancelable.sources.base import CancellationSource
from hother.cancelable.utils.anyio_bridge import call_soon_threadsafe
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class SignalSource(CancellationSource):
    """
    Cancellation source that monitors OS signals.

    Supports graceful shutdown via SIGINT, SIGTERM, etc.
    """

    # Class-level signal handlers registry
    _handlers: dict[int, set[weakref.ref]] = {}
    _original_handlers: dict[int, Callable] = {}
    _lock = anyio.Lock()

    def __init__(self, *signals: int, name: str | None = None):
        """
        Initialize signal source.

        Args:
            *signals: Signal numbers to monitor (e.g., signal.SIGINT)
            name: Optional name for the source
        """
        super().__init__(CancellationReason.SIGNAL, name)

        if not signals:
            # Default to SIGINT and SIGTERM
            self.signals = {signal.SIGINT, signal.SIGTERM}
        else:
            self.signals = set(signals)

        self.triggered = False
        self._signal_received = None
        self._cleanup_done = False

        # Validate signals
        for sig in self.signals:
            if not isinstance(sig, int):
                raise TypeError(f"Signal must be an integer, got {type(sig)}")

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Start monitoring for signals.

        Args:
            scope: Cancel scope to trigger on signal
        """
        self.scope = scope

        # Register this instance for each signal
        await self._register_handlers()

        logger.debug(
            "Signal source activated",
            source=self.name,
            signals=[signal.Signals(s).name for s in self.signals if s in signal.Signals._value2member_map_],
        )

    async def stop_monitoring(self) -> None:
        """Unregister signal handlers."""
        if not self._cleanup_done:
            await self._unregister_handlers()
            self._cleanup_done = True

            logger.debug(
                "Signal source stopped",
                source=self.name,
                triggered=self.triggered,
                signal_received=self._signal_received,
            )

    async def _register_handlers(self) -> None:
        """Register signal handlers."""
        async with self._lock:
            for sig in self.signals:
                # Create handler set if needed
                if sig not in self._handlers:
                    self._handlers[sig] = set()

                    # Store original handler
                    try:
                        original = signal.signal(sig, self._signal_handler)
                        self._original_handlers[sig] = original
                    except (ValueError, OSError) as e:
                        logger.warning(
                            "Failed to register signal handler",
                            signal=sig,
                            error=str(e),
                        )
                        continue

                # Add this instance to handlers
                self._handlers[sig].add(weakref.ref(self, self._cleanup_ref))

    async def _unregister_handlers(self) -> None:
        """Unregister signal handlers."""
        async with self._lock:
            for sig in self.signals:
                if sig in self._handlers:
                    # Remove this instance
                    self._handlers[sig].discard(weakref.ref(self))

                    # If no more handlers, restore original
                    if not self._handlers[sig]:
                        del self._handlers[sig]

                        if sig in self._original_handlers:
                            try:
                                signal.signal(sig, self._original_handlers[sig])
                                del self._original_handlers[sig]
                            except (ValueError, OSError) as e:
                                logger.warning(
                                    "Failed to restore signal handler",
                                    signal=sig,
                                    error=str(e),
                                )

    @classmethod
    def _signal_handler(cls, signum: int, frame) -> None:
        """
        Class-level signal handler that notifies all instances.

        Args:
            signum: Signal number received
            frame: Current stack frame
        """
        # Get all handlers for this signal
        handlers = cls._handlers.get(signum, set())

        # Notify each handler
        for handler_ref in list(handlers):
            handler = handler_ref()
            if handler:
                handler._on_signal(signum)
            else:
                # Dead reference, remove it
                handlers.discard(handler_ref)

    def _on_signal(self, signum: int) -> None:
        """
        Handle signal reception.

        This method is called from the signal handler thread and uses the anyio bridge
        to safely schedule the cancellation in the anyio context.

        Args:
            signum: Signal number received
        """
        if not self.triggered and signum in self.signals:
            self.triggered = True
            self._signal_received = signum

            # Get signal name
            signal_name = "UNKNOWN"
            if signum in signal.Signals._value2member_map_:
                signal_name = signal.Signals(signum).name

            # Schedule cancellation via anyio bridge (thread-safe)
            if self.scope:
                message = f"Received signal {signal_name} ({signum})"

                async def schedule_cancellation() -> None:
                    """Async wrapper to call trigger_cancellation."""
                    try:
                        await self.trigger_cancellation(message)
                    except Exception as e:
                        logger.error(
                            "Failed to trigger cancellation from signal",
                            signal=signum,
                            error=str(e),
                            exc_info=True,
                        )

                # Use bridge to schedule in anyio context
                call_soon_threadsafe(schedule_cancellation)

    @staticmethod
    def _cleanup_ref(ref: weakref.ref) -> None:
        """Cleanup callback for weak references."""
        # Remove dead references from all handler sets
        for handlers in SignalSource._handlers.values():
            handlers.discard(ref)
