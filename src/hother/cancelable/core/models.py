"""
Pydantic models for operation context and status tracking.
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hother.cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class OperationStatus(str, Enum):
    """Operation lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SHIELDED = "shielded"


class CancelationReason(str, Enum):
    """Reason for cancelation."""

    TIMEOUT = "timeout"
    MANUAL = "manual"
    SIGNAL = "signal"
    CONDITION = "condition"
    PARENT = "parent"
    ERROR = "error"


class OperationContext(BaseModel):
    """
    Complete operation context with metadata and status tracking.

    Attributes:
        id: Unique operation identifier
        name: Human-readable operation name
        status: Current operation status
        start_time: When the operation started
        end_time: When the operation ended (if applicable)
        cancel_reason: Reason for cancelation (if cancelled)
        cancel_message: Additional cancelation message
        error: Error message (if failed)
        partial_result: Any partial results before cancelation
        metadata: Additional operation metadata
        parent_id: Parent operation ID (for nested operations)
        child_ids: Set of child operation IDs
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str | None = None
    status: OperationStatus = OperationStatus.PENDING
    start_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    cancel_reason: CancelationReason | None = None
    cancel_message: str | None = None
    error: str | None = None
    partial_result: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    parent_id: str | None = None
    child_ids: set[str] = Field(default_factory=set)

    @property
    def duration(self) -> timedelta | None:
        """Calculate operation duration."""
        if self.end_time:
            return self.end_time - self.start_time
        if self.status == OperationStatus.RUNNING:
            return datetime.now(UTC) - self.start_time
        return None

    @property
    def duration_seconds(self) -> float | None:
        """Get duration in seconds."""
        duration = self.duration
        return duration.total_seconds() if duration else None

    @property
    def is_terminal(self) -> bool:
        """Check if operation is in terminal state."""
        return self.status in {
            OperationStatus.COMPLETED,
            OperationStatus.CANCELLED,
            OperationStatus.FAILED,
            OperationStatus.TIMEOUT,
        }

    @property
    def is_success(self) -> bool:
        """Check if operation completed successfully."""
        return self.status == OperationStatus.COMPLETED

    @property
    def is_cancelled(self) -> bool:
        """Check if operation was cancelled."""
        return self.status in {
            OperationStatus.CANCELLED,
            OperationStatus.TIMEOUT,
        }

    def log_context(self) -> dict[str, Any]:
        """Get context dict for structured logging."""
        return {
            "operation_id": self.id,
            "operation_name": self.name,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "parent_id": self.parent_id,
            "child_count": len(self.child_ids),
            "has_error": bool(self.error),
            "cancel_reason": self.cancel_reason.value if self.cancel_reason else None,
        }

    def update_status(self, status: OperationStatus) -> None:
        """
        Update operation status with appropriate logging.

        Args:
            status: New operation status
        """
        old_status = self.status
        self.status = status

        if status in {OperationStatus.COMPLETED, OperationStatus.CANCELLED, OperationStatus.FAILED, OperationStatus.TIMEOUT}:
            self.end_time = datetime.now(UTC)

        logger.info(
            "Operation status changed",
            extra={
                "old_status": old_status.value,
                "new_status": status.value,
                **self.log_context(),
            },
        )
