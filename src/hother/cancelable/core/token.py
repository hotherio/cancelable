"""
Thread-safe cancelation token implementation.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import anyio
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from hother.cancelable.core.exceptions import ManualCancelation
from hother.cancelable.core.models import CancelationReason
from hother.cancelable.utils.anyio_bridge import call_soon_threadsafe
from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class CancelationToken(BaseModel):
    """
    Thread-safe cancelation token that can be shared across tasks.

    Attributes:
        id: Unique token identifier
        is_cancelled: Whether the token has been cancelled
        reason: Reason for cancelation
        message: Optional cancelation message
        cancelled_at: When the token was cancelled
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_cancelled: bool = False
    reason: CancelationReason | None = None
    message: str | None = None
    cancelled_at: datetime | None = None

    # Private fields using PrivateAttr
    _event: Any = PrivateAttr(default=None)
    _lock: Any = PrivateAttr(default=None)
    _state_lock: Any = PrivateAttr(default=None)  # Thread-safe lock for state updates
    _callbacks: Any = PrivateAttr(default=None)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._event = anyio.Event()
        self._lock = anyio.Lock()
        self._state_lock = threading.Lock()  # Thread-safe lock for state updates
        self._callbacks = []

        logger.debug(f"Created cancelation token {self.id}")

    def __hash__(self) -> int:
        """Make token hashable based on ID."""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Check equality based on ID."""
        if not isinstance(other, CancelationToken):
            return False
        return self.id == other.id

    async def cancel(
        self,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> bool:
        """
        Cancel the token.

        Args:
            reason: Reason for cancelation
            message: Optional cancelation message

        Returns:
            True if token was cancelled, False if already cancelled
        """
        logger.info(f"=== CANCEL CALLED on token {self.id} ===")
        async with self._lock:
            if self.is_cancelled:
                logger.debug(
                    "Token already cancelled",
                    extra={
                        "token_id": self.id,
                        "original_reason": self.reason.value if self.reason else None,
                    },
                )
                return False

            self.is_cancelled = True
            self.reason = reason
            self.message = message
            self.cancelled_at = datetime.now(UTC)
            self._event.set()

            logger.info(
                f"Token {self.id} cancelled - calling {len(self._callbacks)} callbacks",
                extra={
                    "token_id": self.id,
                    "reason": reason.value,
                    "cancel_message": message,
                    "callback_count": len(self._callbacks),
                },
            )

            # Notify callbacks
            for i, callback in enumerate(list(self._callbacks)):
                try:
                    logger.debug(f"Calling callback {i} for token {self.id}")
                    await callback(self)
                    logger.debug(f"Callback {i} completed successfully")
                except Exception as e:
                    logger.error(
                        "Error in cancelation callback",
                        extra={
                            "token_id": self.id,
                            "callback_index": i,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

            logger.info(f"=== CANCEL COMPLETED for token {self.id} ===")
            return True

    def cancel_sync(
        self,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> bool:
        """
        Thread-safe synchronous cancelation from any thread.

        This method can be called from regular Python threads (pynput, signal handlers, etc.)
        and will safely cancel the token and notify async waiters via the anyio bridge.

        Args:
            reason: Reason for cancelation
            message: Optional cancelation message

        Returns:
            True if token was cancelled, False if already cancelled

        Example:
            ```python
            def on_signal(signum):
                # Called from signal handler thread
                token.cancel_sync(CancelationReason.SIGNAL)
            ```
        """
        logger.info(f"=== CANCEL_SYNC CALLED on token {self.id} from thread ===")

        # Update state with thread-safe lock
        with self._state_lock:
            if self.is_cancelled:
                logger.debug(
                    "Token already cancelled",
                    extra={
                        "token_id": self.id,
                        "original_reason": self.reason.value if self.reason else None,
                    },
                )
                return False

            self.is_cancelled = True
            self.reason = reason
            self.message = message
            self.cancelled_at = datetime.now(UTC)

        logger.debug(
            f"Token {self.id} cancelled (sync) - notifying async waiters",
            extra={
                "token_id": self.id,
                "reason": reason.value,
                "cancel_message": message,
            },
        )

        # Notify async waiters (thread-safe)
        self._notify_async_waiters()

        # Schedule callbacks (thread-safe)
        self._schedule_callbacks()

        logger.debug(f"=== CANCEL_SYNC COMPLETED for token {self.id} ===")
        return True

    def _notify_async_waiters(self) -> None:
        """
        Set the anyio event from a thread.

        Uses the anyio bridge to safely set the event in the anyio context.
        """

        def set_event() -> None:
            self._event.set()

        call_soon_threadsafe(set_event)

    def _schedule_callbacks(self) -> None:
        """
        Schedule callbacks to run in the anyio context.

        Uses the anyio bridge to safely execute callbacks from a thread.
        """
        # Take snapshot of callbacks with thread-safe lock
        with self._state_lock:
            callbacks_to_call = list(self._callbacks)

        logger.debug(
            f"Scheduling {len(callbacks_to_call)} callbacks for token {self.id}",
            extra={
                "token_id": self.id,
                "callback_count": len(callbacks_to_call),
            },
        )

        # Schedule each callback via bridge
        for i, callback in enumerate(callbacks_to_call):

            async def run_callback(idx: int = i, cb: Any = callback) -> None:  # Capture loop variables
                try:
                    logger.debug(f"Calling callback {idx} for token {self.id}")
                    await cb(self)
                    logger.debug(f"Callback {idx} completed successfully")
                except Exception as e:
                    logger.error(
                        "Error in cancelation callback",
                        exc_info=True,
                        extra={"token_id": self.id, "callback_index": idx, "error": str(e)},
                    )

            call_soon_threadsafe(run_callback)

    async def wait_for_cancel(self) -> None:
        """Wait until token is cancelled."""
        await self._event.wait()

    def check(self) -> None:
        """
        Check if cancelled and raise exception if so.

        Raises:
            ManualCancelation: If token is cancelled
        """
        if self.is_cancelled:
            logger.debug("Token check triggered cancelation", extra={"token_id": self.id})
            raise ManualCancelation(
                message=self.message or "Operation cancelled via token",
            )

    async def check_async(self) -> None:
        """
        Async version of check that allows for proper async cancelation.

        Raises:
            anyio.CancelledError: If token is cancelled
        """
        if self.is_cancelled:
            logger.debug("Token async check triggered cancelation", extra={"token_id": self.id})
            raise anyio.get_cancelled_exc_class()(self.message or "Operation cancelled via token")

    def is_cancelation_requested(self) -> bool:
        """
        Non-throwing check for cancelation.

        Returns:
            True if cancelation has been requested
        """
        return self.is_cancelled

    async def register_callback(self, callback: Callable[[CancelationToken], Awaitable[None]]) -> None:
        """
        Register a callback to be called on cancelation.

        The callback should accept the token as its only argument.

        Args:
            callback: Async callable that accepts the token
        """
        logger.info(f"Registering callback for token {self.id} (currently {len(self._callbacks)} callbacks)")
        async with self._lock:
            self._callbacks.append(callback)
            logger.info(f"Callback registered. Now {len(self._callbacks)} callbacks for token {self.id}")

            # If already cancelled, call immediately
            if self.is_cancelled:
                logger.info(f"Token {self.id} already cancelled, calling callback immediately")
                try:
                    await callback(self)
                except Exception as e:
                    logger.error(
                        "Error in immediate cancelation callback",
                        extra={
                            "token_id": self.id,
                            "error": str(e),
                        },
                        exc_info=True,
                    )

    def __str__(self) -> str:
        """String representation of token."""
        if self.is_cancelled:
            return f"CancelationToken(id={self.id[:8]}, cancelled={self.reason.value if self.reason else 'unknown'})"
        return f"CancelationToken(id={self.id[:8]}, active)"

    def __repr__(self) -> str:
        """Detailed representation of token."""
        return f"CancelationToken(id='{self.id}', is_cancelled={self.is_cancelled}, reason={self.reason}, message='{self.message}')"


class LinkedCancelationToken(CancelationToken):
    """
    Cancelation token that can be linked to other tokens.

    When any linked token is cancelled, this token is also cancelled.
    """

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._linked_tokens: list[CancelationToken] = []  # Use regular list instead of WeakSet for now

    async def link(self, token: CancelationToken, preserve_reason: bool = False) -> None:
        """
        Link this token to another token.

        When the linked token is cancelled, this token will also be cancelled.

        Args:
            token: Token to link to
            preserve_reason: Whether to preserve the original cancelation reason
        """

        async def on_linked_cancel(linked_token: CancelationToken):
            if preserve_reason and linked_token.reason:
                # Preserve the original reason for combined cancelables
                await self.cancel(
                    reason=linked_token.reason,
                    message=linked_token.message or f"Linked token {linked_token.id[:8]} was cancelled",
                )
            else:
                # Use PARENT for true parent-child relationships
                await self.cancel(
                    reason=CancelationReason.PARENT,
                    message=f"Linked token {linked_token.id[:8]} was cancelled",
                )

        await token.register_callback(on_linked_cancel)
        self._linked_tokens.append(token)

        logger.debug(
            "Linked cancelation tokens",
            extra={"token_id": self.id, "linked_token_id": token.id, "preserve_reason": preserve_reason},
        )
