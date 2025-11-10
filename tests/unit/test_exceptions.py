"""
Unit tests for custom exception classes in hother.cancelable.core.exceptions.
"""

import pytest

from hother.cancelable.core.exceptions import (
    CancelationError,
    ConditionCancelation,
    ManualCancelation,
    ParentCancelation,
    SignalCancelation,
    TimeoutCancelation,
)
from hother.cancelable.core.models import CancelationReason, OperationContext


class TestCancelationError:
    """Test base CancelationError class."""

    def test_basic_instantiation(self):
        """Test basic error creation."""
        error = CancelationError(
            CancelationReason.MANUAL,
            message="Test message",
        )

        assert error.reason == CancelationReason.MANUAL
        assert error.message == "Test message"
        assert error.context is None
        assert str(error) == "Test message"

    def test_default_message(self):
        """Test default message generation."""
        error = CancelationError(CancelationReason.TIMEOUT)

        assert error.reason == CancelationReason.TIMEOUT
        assert error.message == "Operation cancelled: timeout"
        assert str(error) == "Operation cancelled: timeout"

    def test_with_context(self):
        """Test error with operation context."""
        context = OperationContext(name="test_op")
        error = CancelationError(
            CancelationReason.MANUAL,
            message="Context test",
            context=context,
        )

        assert error.context is context
        assert error.context is not None
        assert error.context.name == "test_op"


class TestTimeoutCancelation:
    """Test TimeoutCancelation exception."""

    def test_basic_timeout(self):
        """Test basic timeout exception."""
        error = TimeoutCancelation(5.0)

        assert error.reason == CancelationReason.TIMEOUT
        assert error.timeout_seconds == 5.0
        assert error.message == "Operation timed out after 5.0s"
        assert isinstance(error, CancelationError)

    def test_timeout_with_custom_message(self):
        """Test timeout with custom message."""
        error = TimeoutCancelation(
            2.5,
            message="Custom timeout message",
        )

        assert error.timeout_seconds == 2.5
        assert error.message == "Custom timeout message"

    def test_timeout_with_context(self):
        """Test timeout with operation context."""
        context = OperationContext(name="slow_op")
        error = TimeoutCancelation(1.0, context=context)

        assert error.context is context
        assert error.context is not None
        assert error.context.name == "slow_op"


class TestManualCancelation:
    """Test ManualCancelation exception."""

    def test_basic_manual(self):
        """Test basic manual cancelation."""
        error = ManualCancelation()

        assert error.reason == CancelationReason.MANUAL
        assert error.message == "Operation cancelled manually"
        assert isinstance(error, CancelationError)

    def test_manual_with_custom_message(self):
        """Test manual cancelation with custom message."""
        error = ManualCancelation(message="User cancelled")

        assert error.message == "User cancelled"

    def test_manual_with_context(self):
        """Test manual cancelation with context."""
        context = OperationContext(name="user_cancelled_op")
        error = ManualCancelation(context=context)

        assert error.context is context
        assert error.context is not None
        assert error.context.name == "user_cancelled_op"


class TestSignalCancelation:
    """Test SignalCancelation exception."""

    def test_basic_signal(self):
        """Test basic signal cancelation."""
        error = SignalCancelation(15)  # SIGTERM

        assert error.reason == CancelationReason.SIGNAL
        assert error.signal_number == 15
        assert error.message == "Operation cancelled by signal 15"
        assert isinstance(error, CancelationError)

    def test_signal_with_custom_message(self):
        """Test signal cancelation with custom message."""
        error = SignalCancelation(
            2,  # SIGINT
            message="Interrupted by user",
        )

        assert error.signal_number == 2
        assert error.message == "Interrupted by user"

    def test_signal_with_context(self):
        """Test signal cancelation with context."""
        context = OperationContext(name="signal_handled_op")
        error = SignalCancelation(9, context=context)  # SIGKILL

        assert error.context is context
        assert error.signal_number == 9


class TestConditionCancelation:
    """Test ConditionCancelation exception."""

    def test_basic_condition(self):
        """Test basic condition cancelation."""
        error = ConditionCancelation()

        assert error.reason == CancelationReason.CONDITION
        assert error.condition_name is None
        assert error.message == "Operation cancelled: condition met"
        assert isinstance(error, CancelationError)

    def test_condition_with_name(self):
        """Test condition cancelation with name."""
        error = ConditionCancelation(condition_name="file_not_found")

        assert error.condition_name == "file_not_found"
        assert error.message == "Operation cancelled: file_not_found condition met"

    def test_condition_with_custom_message(self):
        """Test condition with custom message."""
        error = ConditionCancelation(
            condition_name="timeout",
            message="Custom condition message",
        )

        assert error.condition_name == "timeout"
        assert error.message == "Custom condition message"

    def test_condition_with_context(self):
        """Test condition cancelation with context."""
        context = OperationContext(name="condition_based_op")
        error = ConditionCancelation(context=context)

        assert error.context is context


class TestParentCancelation:
    """Test ParentCancelation exception."""

    def test_basic_parent(self):
        """Test basic parent cancelation."""
        error = ParentCancelation("parent_op_123")

        assert error.reason == CancelationReason.PARENT
        assert error.parent_id == "parent_op_123"
        assert error.parent_reason is None
        assert error.message == "Operation cancelled: parent parent_op_123 was cancelled"
        assert isinstance(error, CancelationError)

    def test_parent_with_reason(self):
        """Test parent cancelation with reason."""
        error = ParentCancelation(
            "parent_op_456",
            parent_reason=CancelationReason.TIMEOUT,
        )

        assert error.parent_id == "parent_op_456"
        assert error.parent_reason == CancelationReason.TIMEOUT
        assert error.message == "Operation cancelled: parent parent_op_456 was cancelled (timeout)"

    def test_parent_with_custom_message(self):
        """Test parent cancelation with custom message."""
        error = ParentCancelation(
            "parent_op_789",
            message="Parent operation failed",
        )

        assert error.parent_id == "parent_op_789"
        assert error.message == "Parent operation failed"

    def test_parent_with_context(self):
        """Test parent cancelation with context."""
        context = OperationContext(name="child_op")
        error = ParentCancelation("parent_op", context=context)

        assert error.context is context


class TestExceptionHierarchy:
    """Test exception class hierarchy and inheritance."""

    def test_all_exceptions_inherit_from_cancelation_error(self):
        """Test all specific exceptions inherit from CancelationError."""
        exceptions = [
            TimeoutCancelation(1.0),
            ManualCancelation(),
            SignalCancelation(1),
            ConditionCancelation(),
            ParentCancelation("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, CancelationError)
            assert isinstance(exc, Exception)

    def test_exception_attributes_preserved(self):
        """Test that specific attributes are preserved."""
        timeout_exc = TimeoutCancelation(3.14)
        assert hasattr(timeout_exc, "timeout_seconds")
        assert timeout_exc.timeout_seconds == 3.14

        signal_exc = SignalCancelation(42)
        assert hasattr(signal_exc, "signal_number")
        assert signal_exc.signal_number == 42

        condition_exc = ConditionCancelation(condition_name="test_cond")
        assert hasattr(condition_exc, "condition_name")
        assert condition_exc.condition_name == "test_cond"

        parent_exc = ParentCancelation("parent_123", parent_reason=CancelationReason.MANUAL)
        assert hasattr(parent_exc, "parent_id")
        assert hasattr(parent_exc, "parent_reason")
        assert parent_exc.parent_id == "parent_123"
        assert parent_exc.parent_reason == CancelationReason.MANUAL