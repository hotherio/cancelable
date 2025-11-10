"""
Tests for async cancelation models.
"""

from datetime import timedelta

from hother.cancelable import CancelationReason, OperationContext, OperationStatus


class TestOperationStatus:
    """Test OperationStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert OperationStatus.PENDING.value == "pending"
        assert OperationStatus.RUNNING.value == "running"
        assert OperationStatus.COMPLETED.value == "completed"
        assert OperationStatus.CANCELLED.value == "cancelled"
        assert OperationStatus.FAILED.value == "failed"
        assert OperationStatus.TIMEOUT.value == "timeout"
        assert OperationStatus.SHIELDED.value == "shielded"

    def test_status_comparison(self):
        """Test status comparison."""
        assert OperationStatus.PENDING == OperationStatus.PENDING
        assert OperationStatus.PENDING != OperationStatus.RUNNING


class TestCancelationReason:
    """Test CancelationReason enum."""

    def test_reason_values(self):
        """Test reason enum values."""
        assert CancelationReason.TIMEOUT.value == "timeout"
        assert CancelationReason.MANUAL.value == "manual"
        assert CancelationReason.SIGNAL.value == "signal"
        assert CancelationReason.CONDITION.value == "condition"
        assert CancelationReason.PARENT.value == "parent"
        assert CancelationReason.ERROR.value == "error"


class TestOperationContext:
    """Test OperationContext model."""

    def test_default_values(self):
        """Test default field values."""
        context = OperationContext()

        assert context.id is not None
        assert len(context.id) == 36  # UUID format
        assert context.name is None
        assert context.status == OperationStatus.PENDING
        assert context.start_time is not None
        assert context.end_time is None
        assert context.cancel_reason is None
        assert context.cancel_message is None
        assert context.error is None
        assert context.partial_result is None
        assert context.metadata == {}
        assert context.parent_id is None
        assert context.child_ids == set()

    def test_custom_values(self):
        """Test creating context with custom values."""
        context = OperationContext(
            id="test-id",
            name="test-operation",
            metadata={"key": "value"},
            parent_id="parent-123",
        )

        assert context.id == "test-id"
        assert context.name == "test-operation"
        assert context.metadata == {"key": "value"}
        assert context.parent_id == "parent-123"

    def test_duration_calculation(self):
        """Test duration property."""
        context = OperationContext()

        # No duration for pending
        assert context.duration is None

        # Duration for running
        context.status = OperationStatus.RUNNING
        duration = context.duration
        assert duration is not None
        assert duration.total_seconds() >= 0

        # Fixed duration for completed
        context.status = OperationStatus.COMPLETED
        context.end_time = context.start_time + timedelta(seconds=5)
        assert context.duration.total_seconds() == 5.0

    def test_is_terminal(self):
        """Test is_terminal property."""
        context = OperationContext()

        # Non-terminal states
        for status in [OperationStatus.PENDING, OperationStatus.RUNNING, OperationStatus.SHIELDED]:
            context.status = status
            assert not context.is_terminal

        # Terminal states
        for status in [OperationStatus.COMPLETED, OperationStatus.CANCELLED, OperationStatus.FAILED, OperationStatus.TIMEOUT]:
            context.status = status
            assert context.is_terminal

    def test_is_success(self):
        """Test is_success property."""
        context = OperationContext()

        context.status = OperationStatus.COMPLETED
        assert context.is_success

        context.status = OperationStatus.FAILED
        assert not context.is_success

    def test_is_cancelled(self):
        """Test is_cancelled property."""
        context = OperationContext()

        context.status = OperationStatus.CANCELLED
        assert context.is_cancelled

        context.status = OperationStatus.TIMEOUT
        assert context.is_cancelled

        context.status = OperationStatus.COMPLETED
        assert not context.is_cancelled

    def test_log_context(self):
        """Test log_context method."""
        context = OperationContext(
            id="test-123",
            name="test-op",
            parent_id="parent-456",
        )
        context.child_ids.add("child-789")

        log_ctx = context.log_context()

        assert log_ctx["operation_id"] == "test-123"
        assert log_ctx["operation_name"] == "test-op"
        assert log_ctx["status"] == "pending"
        assert log_ctx["parent_id"] == "parent-456"
        assert log_ctx["child_count"] == 1
        assert log_ctx["has_error"] is False
        assert log_ctx["cancel_reason"] is None

    def test_update_status(self):
        """Test update_status method."""
        context = OperationContext()

        context.update_status(OperationStatus.RUNNING)
        assert context.status == OperationStatus.RUNNING
        assert context.end_time is None

        context.update_status(OperationStatus.COMPLETED)
        assert context.status == OperationStatus.COMPLETED
        assert context.end_time is not None

    def test_model_validation(self):
        """Test Pydantic model validation."""
        # Valid context
        context = OperationContext(
            status=OperationStatus.RUNNING,
            cancel_reason=CancelationReason.TIMEOUT,
        )
        assert context.status == OperationStatus.RUNNING
        assert context.cancel_reason == CancelationReason.TIMEOUT

        # Test serialization
        data = context.model_dump()
        assert data["status"] == "running"
        assert data["cancel_reason"] == "timeout"

        # Test deserialization
        context2 = OperationContext.model_validate(data)
        assert context2.id == context.id
        assert context2.status == context.status
