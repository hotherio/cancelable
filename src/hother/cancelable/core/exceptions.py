"""
Custom exceptions for the async cancelation system.
"""


from hother.cancelable.core.models import CancelationReason, OperationContext


class CancelationError(Exception):
    """
    Base exception for cancelation-related errors.

    Attributes:
        reason: The reason for cancelation
        message: Optional cancelation message
        context: Optional operation context
    """

    def __init__(
        self,
        reason: CancelationReason,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        self.reason = reason
        self.message = message or f"Operation cancelled: {reason.value}"
        self.context = context
        super().__init__(self.message)


class TimeoutCancelation(CancelationError):
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
            CancelationReason.TIMEOUT,
            message or default_message,
            context,
        )


class ManualCancelation(CancelationError):
    """Operation cancelled manually via token or API."""

    def __init__(
        self,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        super().__init__(
            CancelationReason.MANUAL,
            message or "Operation cancelled manually",
            context,
        )


class SignalCancelation(CancelationError):
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
            CancelationReason.SIGNAL,
            message or default_message,
            context,
        )


class ConditionCancelation(CancelationError):
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
            CancelationReason.CONDITION,
            message or default_message,
            context,
        )


class ParentCancelation(CancelationError):
    """Operation cancelled because parent was cancelled."""

    def __init__(
        self,
        parent_id: str,
        parent_reason: CancelationReason | None = None,
        message: str | None = None,
        context: OperationContext | None = None,
    ):
        self.parent_id = parent_id
        self.parent_reason = parent_reason
        default_message = f"Operation cancelled: parent {parent_id} was cancelled"
        if parent_reason:
            default_message = f"Operation cancelled: parent {parent_id} was cancelled ({parent_reason.value})"
        super().__init__(
            CancelationReason.PARENT,
            message or default_message,
            context,
        )
