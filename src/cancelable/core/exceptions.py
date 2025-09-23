"""
Custom exceptions for the async cancellation system.
"""


from cancelable.core.models import CancellationReason, OperationContext


class CancellationError(Exception):
    """
    Base exception for cancellation-related errors.

    Attributes:
        reason: The reason for cancellation
        message: Optional cancellation message
        context: Optional operation context
    """

    def __init__(
        self,
        reason: CancellationReason,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        self.reason = reason
        self.message = message or f"Operation cancelled: {reason.value}"
        self.context = context
        super().__init__(self.message)


class TimeoutCancellation(CancellationError):
    """Operation cancelled due to timeout."""

    def __init__(
        self,
        timeout_seconds: float,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        default_message = f"Operation timed out after {timeout_seconds}s"
        super().__init__(
            CancellationReason.TIMEOUT,
            message or default_message,
            context,
        )


class ManualCancellation(CancellationError):
    """Operation cancelled manually via token or API."""

    def __init__(
        self,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        super().__init__(
            CancellationReason.MANUAL,
            message or "Operation cancelled manually",
            context,
        )


class SignalCancellation(CancellationError):
    """Operation cancelled by system signal."""

    def __init__(
        self,
        signal_number: int,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        self.signal_number = signal_number
        default_message = f"Operation cancelled by signal {signal_number}"
        super().__init__(
            CancellationReason.SIGNAL,
            message or default_message,
            context,
        )


class ConditionCancellation(CancellationError):
    """Operation cancelled by condition check."""

    def __init__(
        self,
        condition_name: str | None = None,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        self.condition_name = condition_name
        default_message = "Operation cancelled: condition met"
        if condition_name:
            default_message = f"Operation cancelled: {condition_name} condition met"
        super().__init__(
            CancellationReason.CONDITION,
            message or default_message,
            context,
        )


class ParentCancellation(CancellationError):
    """Operation cancelled because parent was cancelled."""

    def __init__(
        self,
        parent_id: str,
        parent_reason: CancellationReason | None = None,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        self.parent_id = parent_id
        self.parent_reason = parent_reason
        default_message = f"Operation cancelled: parent {parent_id} was cancelled"
        if parent_reason:
            default_message = f"Operation cancelled: parent {parent_id} was cancelled ({parent_reason.value})"
        super().__init__(
            CancellationReason.PARENT,
            message or default_message,
            context,
        )
