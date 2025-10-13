"""
Timeout-based cancellation source implementation.
"""

import asyncio
from datetime import timedelta

import anyio

from hother.cancelable.core.models import CancellationReason
from hother.cancelable.sources.base import CancellationSource
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class TimeoutSource(CancellationSource):
    """
    Cancellation source that triggers after a specified timeout.
    """

    def __init__(self, timeout: float | timedelta, name: str | None = None):
        """
        Initialize timeout source.

        Args:
            timeout: Timeout duration in seconds or as timedelta
            name: Optional name for the source
        """
        super().__init__(CancellationReason.TIMEOUT, name)

        if isinstance(timeout, timedelta):
            timeout = timeout.total_seconds()

        if timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {timeout}")

        self.timeout = timeout
        self.triggered = False

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Set scope deadline for timeout.

        Args:
            scope: Cancel scope to configure
        """
        self.scope = scope
        scope.deadline = anyio.current_time() + self.timeout

        logger.debug(
            "Timeout source activated",
            source=self.name,
            timeout_seconds=self.timeout,
            deadline=scope.deadline,
        )

        # Also monitor to set triggered flag
        async def monitor():
            try:
                await anyio.sleep(self.timeout)
                # If we reach here, timeout occurred
                self.triggered = True
                logger.debug(f"Timeout source triggered after {self.timeout}s")
            except anyio.get_cancelled_exc_class():
                # Cancelled before timeout
                pass

        # Start monitoring in background
        self._monitoring_task = asyncio.create_task(monitor())

    async def stop_monitoring(self) -> None:
        """Stop timeout monitoring."""
        if hasattr(self, "_monitoring_task") and self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.debug(
            "Timeout source stopped",
            source=self.name,
            triggered=self.triggered,
        )
