"""
Timeout-based cancelation source implementation.
"""

from datetime import timedelta

import anyio

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.base import CancelationSource
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class TimeoutSource(CancelationSource):
    """
    Cancelation source that triggers after a specified timeout.
    """

    def __init__(self, timeout: float | timedelta, name: str | None = None):
        """
        Initialize timeout source.

        Args:
            timeout: Timeout duration in seconds or as timedelta
            name: Optional name for the source
        """
        super().__init__(CancelationReason.TIMEOUT, name)

        if isinstance(timeout, timedelta):
            timeout = timeout.total_seconds()

        if timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {timeout}")

        self.timeout = timeout
        self.triggered = False
        self._deadline_time: float | None = None

    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Set scope deadline for timeout.

        Args:
            scope: Cancel scope to configure
        """
        self.scope = scope
        self._deadline_time = anyio.current_time() + self.timeout
        scope.deadline = self._deadline_time

        logger.debug(
            "Timeout source activated",
            extra={
                "source": self.name,
                "timeout_seconds": self.timeout,
                "deadline": scope.deadline,
            },
        )

    async def stop_monitoring(self) -> None:
        """Stop timeout monitoring."""
        # Check if timeout occurred by comparing current time with deadline
        if self._deadline_time and anyio.current_time() >= self._deadline_time:
            self.triggered = True

        logger.debug(
            "Timeout source stopped",
            extra={
                "source": self.name,
                "triggered": self.triggered,
            },
        )
