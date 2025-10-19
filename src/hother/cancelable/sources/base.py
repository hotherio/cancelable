"""
Base class for cancellation sources.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import anyio

from hother.cancelable.core.models import CancellationReason
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class CancellationSource(ABC):
    """
    Abstract base class for cancellation sources.

    A cancellation source monitors for a specific condition and triggers
    cancellation when that condition is met.
    """

    def __init__(self, reason: CancellationReason, name: str | None = None):
        """
        Initialize cancellation source.

        Args:
            reason: The cancellation reason this source will use
            name: Optional name for the source
        """
        self.reason = reason
        self.name = name or self.__class__.__name__
        self.scope: anyio.CancelScope | None = None
        self._cancel_callback: Callable | None = None
        self._monitoring_task: anyio.CancelScope | None = None
        self.triggered: bool = False

    @abstractmethod
    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Start monitoring for cancellation condition.

        Args:
            scope: The cancel scope to trigger when condition is met
        """
        self.scope = scope

    @abstractmethod
    async def stop_monitoring(self) -> None:
        """Stop monitoring and clean up resources."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None

    def set_cancel_callback(self, callback: Callable[[CancellationReason, str], Any]) -> None:
        """
        Set callback to be called when cancellation is triggered.

        Args:
            callback: Callback function that accepts reason and message
        """
        self._cancel_callback = callback

    async def trigger_cancellation(self, message: str | None = None) -> None:
        """
        Trigger cancellation with the configured reason.

        Args:
            message: Optional cancellation message
        """
        if self.scope and not self.scope.cancel_called:
            logger.info(
                "Cancellation triggered",
                source=self.name,
                reason=self.reason.value,
                message=message,
            )

            # Call callback if set
            if self._cancel_callback:
                try:
                    result = self._cancel_callback(self.reason, message or "")
                    if hasattr(result, "__await__"):
                        await result
                except Exception as e:
                    logger.error(
                        "Error in cancellation callback",
                        source=self.name,
                        error=str(e),
                        exc_info=True,
                    )

            # Cancel the scope
            self.scope.cancel()

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name}(reason={self.reason.value})"
