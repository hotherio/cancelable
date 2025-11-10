"""
Base class for cancelation sources.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

import anyio

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class CancelationSource(ABC):
    """
    Abstract base class for cancelation sources.

    A cancelation source monitors for a specific condition and triggers
    cancelation when that condition is met.
    """

    def __init__(self, reason: CancelationReason, name: str | None = None):
        """
        Initialize cancelation source.

        Args:
            reason: The cancelation reason this source will use
            name: Optional name for the source
        """
        self.reason = reason
        self.name = name or self.__class__.__name__
        self.scope: anyio.CancelScope | None = None
        self._cancel_callback: Callable[[CancelationReason, str], None | Awaitable[None]] | None = None
        self._monitoring_task: anyio.CancelScope | None = None
        self.triggered: bool = False

    @abstractmethod
    async def start_monitoring(self, scope: anyio.CancelScope) -> None:
        """
        Start monitoring for cancelation condition.

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

    def set_cancel_callback(self, callback: Callable[[CancelationReason, str], None | Awaitable[None]]) -> None:
        """
        Set callback to be called when cancelation is triggered.

        Args:
            callback: Callback function that accepts reason and message (can be sync or async)
        """
        self._cancel_callback = callback

    async def trigger_cancelation(self, message: str | None = None) -> None:
        """
        Trigger cancelation with the configured reason.

        Args:
            message: Optional cancelation message
        """
        if self.scope and not self.scope.cancel_called:
            logger.info(
                "Cancelation triggered",
                extra={
                    "source": self.name,
                    "reason": self.reason.value,
                    "cancel_message": message,
                },
            )

            # Call callback if set
            if self._cancel_callback:
                try:
                    result = self._cancel_callback(self.reason, message or "")
                    # If result is an Awaitable, await it
                    if result is not None:
                        await result
                except Exception as e:
                    logger.error(
                        "Error in cancelation callback",
                        extra={
                            "source": self.name,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            # Cancel the scope
            self.scope.cancel()

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name}(reason={self.reason.value})"
