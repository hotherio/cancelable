"""
Thread-safe cancellation token implementation.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import anyio
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from cancelable.core.exceptions import ManualCancellation
from cancelable.core.models import CancellationReason
from cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class CancellationToken(BaseModel):
    """
    Thread-safe cancellation token that can be shared across tasks.

    Attributes:
        id: Unique token identifier
        is_cancelled: Whether the token has been cancelled
        reason: Reason for cancellation
        message: Optional cancellation message
        cancelled_at: When the token was cancelled
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_cancelled: bool = False
    reason: CancellationReason | None = None
    message: str | None = None
    cancelled_at: datetime | None = None

    # Private fields using PrivateAttr
    _event: Any = PrivateAttr(default=None)
    _lock: Any = PrivateAttr(default=None)
    _callbacks: Any = PrivateAttr(default=None)

    def __init__(self, **data):
        super().__init__(**data)
        self._event = anyio.Event()
        self._lock = anyio.Lock()
        self._callbacks = []

        logger.debug("Created cancellation token", token_id=self.id)

    def __hash__(self) -> int:
        """Make token hashable based on ID."""
        return hash(self.id)

    def __eq__(self, other) -> bool:
        """Check equality based on ID."""
        if not isinstance(other, CancellationToken):
            return False
        return self.id == other.id

    async def cancel(
        self,
        reason: CancellationReason = CancellationReason.MANUAL,
        message: str | None = None,
    ) -> bool:
        """
        Cancel the token.

        Args:
            reason: Reason for cancellation
            message: Optional cancellation message

        Returns:
            True if token was cancelled, False if already cancelled
        """
        logger.info(f"=== CANCEL CALLED on token {self.id} ===")
        async with self._lock:
            if self.is_cancelled:
                logger.debug(
                    "Token already cancelled",
                    token_id=self.id,
                    original_reason=self.reason.value if self.reason else None,
                )
                return False

            self.is_cancelled = True
            self.reason = reason
            self.message = message
            self.cancelled_at = datetime.now(UTC)
            self._event.set()

            logger.info(f"Token {self.id} cancelled - calling {len(self._callbacks)} callbacks", token_id=self.id, reason=reason.value, message=message, callback_count=len(self._callbacks))

            # Notify callbacks
            for i, callback in enumerate(list(self._callbacks)):
                try:
                    logger.info(f"Calling callback {i} for token {self.id}")
                    await callback(self)
                    logger.info(f"Callback {i} completed successfully")
                except Exception as e:
                    logger.error(
                        "Error in cancellation callback",
                        token_id=self.id,
                        callback_index=i,
                        error=str(e),
                        exc_info=True,
                    )

            logger.info(f"=== CANCEL COMPLETED for token {self.id} ===")
            return True

    async def wait_for_cancel(self) -> None:
        """Wait until token is cancelled."""
        await self._event.wait()

    def check(self) -> None:
        """
        Check if cancelled and raise exception if so.

        Raises:
            ManualCancellation: If token is cancelled
        """
        if self.is_cancelled:
            logger.debug("Token check triggered cancellation", token_id=self.id)
            raise ManualCancellation(
                message=self.message or "Operation cancelled via token",
            )

    async def check_async(self) -> None:
        """
        Async version of check that allows for proper async cancellation.

        Raises:
            anyio.CancelledError: If token is cancelled
        """
        if self.is_cancelled:
            logger.debug("Token async check triggered cancellation", token_id=self.id)
            raise anyio.get_cancelled_exc_class()(self.message or "Operation cancelled via token")

    def is_cancellation_requested(self) -> bool:
        """
        Non-throwing check for cancellation.

        Returns:
            True if cancellation has been requested
        """
        return self.is_cancelled

    async def register_callback(self, callback) -> None:
        """
        Register a callback to be called on cancellation.

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
                        "Error in immediate cancellation callback",
                        token_id=self.id,
                        error=str(e),
                        exc_info=True,
                    )

    def __str__(self) -> str:
        """String representation of token."""
        if self.is_cancelled:
            return f"CancellationToken(id={self.id[:8]}, cancelled={self.reason.value if self.reason else 'unknown'})"
        return f"CancellationToken(id={self.id[:8]}, active)"

    def __repr__(self) -> str:
        """Detailed representation of token."""
        return f"CancellationToken(id='{self.id}', is_cancelled={self.is_cancelled}, reason={self.reason}, message='{self.message}')"


class LinkedCancellationToken(CancellationToken):
    """
    Cancellation token that can be linked to other tokens.

    When any linked token is cancelled, this token is also cancelled.
    """

    def __init__(self, **data):
        super().__init__(**data)
        self._linked_tokens = []  # Use regular list instead of WeakSet for now

    async def link(self, token: CancellationToken, preserve_reason: bool = False) -> None:
        """
        Link this token to another token.

        When the linked token is cancelled, this token will also be cancelled.

        Args:
            token: Token to link to
            preserve_reason: Whether to preserve the original cancellation reason
        """

        async def on_linked_cancel(linked_token: CancellationToken):
            if preserve_reason and linked_token.reason:
                # Preserve the original reason for combined cancellables
                await self.cancel(
                    reason=linked_token.reason,
                    message=linked_token.message or f"Linked token {linked_token.id[:8]} was cancelled",
                )
            else:
                # Use PARENT for true parent-child relationships
                await self.cancel(
                    reason=CancellationReason.PARENT,
                    message=f"Linked token {linked_token.id[:8]} was cancelled",
                )

        await token.register_callback(on_linked_cancel)
        self._linked_tokens.append(token)

        logger.debug(
            "Linked cancellation tokens",
            token_id=self.id,
            linked_token_id=token.id,
            preserve_reason=preserve_reason,
        )
