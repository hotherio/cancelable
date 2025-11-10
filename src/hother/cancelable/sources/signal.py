"""
Signal-based cancelation source implementation.
"""

from __future__ import annotations

import signal

import anyio
import anyio.abc

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.base import CancelationSource
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class SignalSource(CancelationSource):
    """
    Cancelation source that monitors OS signals.

    Uses anyio's native signal handling for clean integration.
    Supports graceful shutdown via SIGINT, SIGTERM, etc.

    Note: Signal handlers can only be installed in the main thread.
    """

    def __init__(self, *signals: int, name: str | None = None) -> None:
        """
        Initialize signal source.

        Args:
            *signals: Signal numbers to monitor (e.g., signal.SIGINT)
            name: Optional name for the source
        """
        super().__init__(CancelationReason.SIGNAL, name)

        # Validate signals
        for sig in signals:
            if not isinstance(sig, int):
                raise TypeError(f"Signal must be an integer, got {type(sig)}")

        if not signals:
            # Default to SIGINT and SIGTERM
            self.signals = (signal.SIGINT, signal.SIGTERM)
        else:
            self.signals = tuple(signals)

        self.triggered = False
        self._signal_received: int | None = None
        self._task_group: anyio.abc.TaskGroup | None = None

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Start monitoring for signals.

        Args:
            scope: Cancel scope to trigger when signal is received
        """
        self.scope = scope

        # Create task group for background monitoring
        self._task_group = anyio.create_task_group()
        await self._task_group.__aenter__()

        # Start signal monitoring task
        self._task_group.start_soon(self._monitor_signals)

        logger.debug(
            "Signal source activated",
            extra={
                "source": self.name,
                "signals": [signal.Signals(s).name for s in self.signals if s in signal.Signals._value2member_map_],
            },
        )

    async def stop_monitoring(self) -> None:
        """Stop monitoring signals and clean up resources."""
        if self._task_group:
            # Cancel the task group to stop the monitoring task
            try:
                self._task_group.cancel_scope.cancel()
                await self._task_group.__aexit__(None, None, None)
            except BaseException as e:
                # Suppress CancelledError and other exceptions during cleanup
                logger.debug(f"Task group exit: {type(e).__name__}: {e}")
            finally:
                self._task_group = None

        logger.debug(
            "Signal source stopped",
            extra={
                "source": self.name,
                "triggered": self.triggered,
                "signal_received": self._signal_received,
            },
        )

    async def _monitor_signals(self) -> None:
        """
        Monitor for signals using anyio's native signal handling.

        This runs in a background task and waits for any of the configured signals.
        When a signal is received, it triggers cancelation and exits.
        """
        try:
            # Open signal receiver (sync context manager)
            with anyio.open_signal_receiver(*self.signals) as signals:  # type: ignore[arg-type]
                logger.debug(
                    "Signal source monitoring started",
                    extra={
                        "source": self.name,
                        "signals": [
                            signal.Signals(s).name for s in self.signals if s in signal.Signals._value2member_map_
                        ],
                    },
                )

                # Wait for signals
                # Signal reception happens via anyio's native receiver
                # Tested through integration examples (examples/02_advanced/08_signal_handling.py)
                async for signum in signals:  # pragma: no cover
                    if not self.triggered:
                        self.triggered = True
                        self._signal_received = signum

                        # Get signal name
                        signal_name = "UNKNOWN"
                        if signum in signal.Signals._value2member_map_:
                            signal_name = signal.Signals(signum).name

                        message = f"Received signal {signal_name} ({signum})"

                        logger.info(
                            "Signal received, triggering cancelation",
                            extra={
                                "source": self.name,
                                "signal": signal_name,
                                "signum": signum,
                            },
                        )

                        # Trigger cancelation
                        await self.trigger_cancelation(message)
                        break

        # Exception handling for unexpected errors during signal monitoring
        # Defensive code - difficult to trigger without breaking anyio internals
        except Exception as e:  # pragma: no cover
            logger.error(
                "Signal monitoring error",
                extra={
                    "source": self.name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
        finally:
            logger.debug(
                "Signal source monitoring stopped",
                extra={
                    "source": self.name,
                    "triggered": self.triggered,
                    "signal_received": self._signal_received,
                },
            )
