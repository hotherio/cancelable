"""
Global operation registry for tracking and managing operations.
"""

import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional

import anyio

from hother.cancelable.core.models import CancelationReason, OperationContext, OperationStatus
from hother.cancelable.utils.logging import get_logger

if TYPE_CHECKING:
    from .cancelable import Cancelable

logger = get_logger(__name__)


class OperationRegistry:
    """
    Singleton registry for tracking all cancelable operations.

    Provides centralized management and monitoring of operations across
    the application.
    """

    _instance: Optional["OperationRegistry"] = None

    def __new__(cls) -> "OperationRegistry":
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize registry (only once)."""
        if self._initialized:
            return

        self._operations: dict[str, Cancelable] = {}
        self._history: list[OperationContext] = []
        self._history_limit = 1000
        self._lock: anyio.Lock = anyio.Lock()
        self._data_lock = threading.Lock()  # Thread-safe lock for data access
        self._initialized = True

        logger.info("Operation registry initialized")

    @classmethod
    def get_instance(cls) -> "OperationRegistry":
        """
        Get singleton instance of the registry.

        Returns:
            The global OperationRegistry instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def register(self, operation: "Cancelable") -> None:
        """
        Register an operation with the registry.

        Args:
            operation: Cancelable operation to register
        """
        async with self._lock:
            with self._data_lock:
                self._operations[operation.context.id] = operation
                total = len(self._operations)

            logger.info(
                "Operation registered",
                extra={
                    "operation_id": operation.context.id,
                    "operation_name": operation.context.name,
                    "total_operations": total,
                },
            )

    async def unregister(self, operation_id: str) -> None:
        """
        Unregister an operation and add to history.

        Args:
            operation_id: ID of operation to unregister
        """
        async with self._lock:
            with self._data_lock:
                operation = self._operations.pop(operation_id, None)
                if operation:
                    # Add to history
                    self._history.append(operation.context.model_copy(deep=True))

                    # Maintain history limit
                    if len(self._history) > self._history_limit:
                        self._history = self._history[-self._history_limit :]

            if operation:
                logger.debug(
                    "Operation unregistered",
                    extra={
                        "operation_id": operation_id,
                        "final_status": operation.context.status.value,
                        "duration": operation.context.duration_seconds,
                    },
                )

    async def get_operation(self, operation_id: str) -> Optional["Cancelable"]:
        """
        Get operation by ID.

        Args:
            operation_id: Operation ID to look up

        Returns:
            Cancelable operation or None if not found
        """
        async with self._lock:
            with self._data_lock:
                return self._operations.get(operation_id)

    async def list_operations(
        self,
        status: OperationStatus | None = None,
        parent_id: str | None = None,
        name_pattern: str | None = None,
    ) -> list[OperationContext]:
        """
        List operations with optional filtering.

        Args:
            status: Filter by operation status
            parent_id: Filter by parent operation ID
            name_pattern: Filter by name (substring match)

        Returns:
            List of matching operation contexts
        """
        async with self._lock:
            with self._data_lock:
                operations = [op.context for op in self._operations.values()]

            # Apply filters (outside lock - operating on copied list)
            if status:
                operations = [op for op in operations if op.status == status]

            if parent_id:
                operations = [op for op in operations if op.parent_id == parent_id]

            if name_pattern:
                operations = [op for op in operations if op.name and name_pattern.lower() in op.name.lower()]

            return operations

    async def cancel_operation(
        self,
        operation_id: str,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> bool:
        """
        Cancel a specific operation.

        Args:
            operation_id: ID of operation to cancel
            reason: Reason for cancelation
            message: Optional cancelation message

        Returns:
            True if operation was cancelled, False if not found
        """
        if operation := await self.get_operation(operation_id):
            await operation.cancel(reason, message)
            return True

        logger.warning(
            "Attempted to cancel non-existent operation",
            extra={"operation_id": operation_id},
        )
        return False

    async def cancel_all(
        self,
        status: OperationStatus | None = None,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> int:
        """
        Cancel all operations with optional status filter.

        Args:
            status: Only cancel operations with this status
            reason: Reason for cancelation
            message: Optional cancelation message

        Returns:
            Number of operations cancelled
        """
        async with self._lock:
            with self._data_lock:
                to_cancel = list(self._operations.values())

            if status:
                to_cancel = [op for op in to_cancel if op.context.status == status]

        # Cancel outside lock to avoid deadlock
        count = 0
        for operation in to_cancel:
            try:
                await operation.cancel(reason, message or "Bulk cancelation")
                count += 1
            except Exception as e:
                logger.error(
                    "Error cancelling operation",
                    extra={
                        "operation_id": operation.context.id,
                        "error": str(e),
                    },
                    exc_info=True,
                )

        logger.info(
            "Bulk cancelation completed",
            extra={
                "cancelled_count": count,
                "filter_status": status.value if status else None,
            },
        )

        return count

    async def get_history(
        self,
        limit: int | None = None,
        status: OperationStatus | None = None,
        since: datetime | None = None,
    ) -> list[OperationContext]:
        """
        Get operation history.

        Args:
            limit: Maximum number of operations to return
            status: Filter by final status
            since: Only return operations completed after this time

        Returns:
            List of historical operation contexts
        """
        async with self._lock:
            with self._data_lock:
                history = self._history.copy()

            # Apply filters (outside lock - operating on copied list)
            if status:
                history = [op for op in history if op.status == status]

            if since:
                history = [op for op in history if op.end_time and op.end_time >= since]

            # Apply limit
            if limit:
                history = history[-limit:]

            return history

    async def cleanup_completed(
        self,
        older_than: timedelta | None = None,
        keep_failed: bool = True,
    ) -> int:
        """
        Clean up completed operations from active tracking.

        Args:
            older_than: Only cleanup operations older than this
            keep_failed: Whether to keep failed operations

        Returns:
            Number of operations cleaned up
        """
        async with self._lock:
            with self._data_lock:
                now = datetime.now(UTC)
                to_remove: list[str] = []

                for op_id, operation in self._operations.items():
                    context = operation.context

                    # Skip non-terminal operations
                    if not context.is_terminal:
                        continue

                    # Skip failed operations if requested
                    if keep_failed and context.status == OperationStatus.FAILED:
                        continue

                    # Check age if specified
                    if older_than and context.end_time:
                        age = now - context.end_time
                        if age < older_than:
                            continue

                    to_remove.append(op_id)

                # Remove operations
                for op_id in to_remove:
                    if operation := self._operations.pop(op_id, None):
                        self._history.append(operation.context.model_copy(deep=True))

                # Maintain history limit
                if len(self._history) > self._history_limit:
                    self._history = self._history[-self._history_limit :]

        logger.info(
            "Cleaned up completed operations",
            extra={
                "cleaned_count": len(to_remove),
                "older_than_seconds": older_than.total_seconds() if older_than else None,
            },
        )

        return len(to_remove)

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with operation statistics
        """
        async with self._lock:
            with self._data_lock:
                active_by_status = {}
                for operation in self._operations.values():
                    status = operation.context.status.value
                    active_by_status[status] = active_by_status.get(status, 0) + 1

                history_by_status = {}
                total_duration = 0.0
                completed_count = 0

                for context in self._history:
                    status = context.status.value
                    history_by_status[status] = history_by_status.get(status, 0) + 1

                    if context.duration_seconds and context.is_success:
                        total_duration += context.duration_seconds
                        completed_count += 1

                avg_duration = total_duration / completed_count if completed_count > 0 else 0

                return {
                    "active_operations": len(self._operations),
                    "active_by_status": active_by_status,
                    "history_size": len(self._history),
                    "history_by_status": history_by_status,
                    "average_duration_seconds": avg_duration,
                    "total_completed": completed_count,
                }

    async def clear_all(self) -> None:
        """Clear all operations and history (for testing)."""
        async with self._lock:
            with self._data_lock:
                self._operations.clear()
                self._history.clear()
            logger.warning("Registry cleared - all operations removed")

    # Thread-safe synchronous methods

    def get_operation_sync(self, operation_id: str) -> Optional["Cancelable"]:
        """
        Get operation by ID (thread-safe, synchronous).

        This method can be called from any thread.

        Args:
            operation_id: Operation ID to look up

        Returns:
            Cancelable operation or None if not found
        """
        with self._data_lock:
            return self._operations.get(operation_id)

    def list_operations_sync(
        self,
        status: OperationStatus | None = None,
        parent_id: str | None = None,
        name_pattern: str | None = None,
    ) -> list[OperationContext]:
        """
        List operations with optional filtering (thread-safe, synchronous).

        This method can be called from any thread.

        Args:
            status: Filter by operation status
            parent_id: Filter by parent operation ID
            name_pattern: Filter by name (substring match)

        Returns:
            List of matching operation contexts
        """
        with self._data_lock:
            # Create copies to avoid holding lock during filtering
            operations = [op.context.model_copy() for op in self._operations.values()]

        # Apply filters outside lock
        if status:
            operations = [op for op in operations if op.status == status]

        if parent_id:
            operations = [op for op in operations if op.parent_id == parent_id]

        if name_pattern:
            operations = [op for op in operations if op.name and name_pattern.lower() in op.name.lower()]

        return operations

    def get_statistics_sync(self) -> dict[str, Any]:
        """
        Get registry statistics (thread-safe, synchronous).

        This method can be called from any thread.

        Returns:
            Dictionary with operation statistics
        """
        with self._data_lock:
            active_by_status = {}
            for operation in self._operations.values():
                status = operation.context.status.value
                active_by_status[status] = active_by_status.get(status, 0) + 1

            history_by_status = {}
            total_duration = 0.0
            completed_count = 0

            for context in self._history:
                status = context.status.value
                history_by_status[status] = history_by_status.get(status, 0) + 1

                if context.duration_seconds and context.is_success:
                    total_duration += context.duration_seconds
                    completed_count += 1

            avg_duration = total_duration / completed_count if completed_count > 0 else 0

            return {
                "active_operations": len(self._operations),
                "active_by_status": active_by_status,
                "history_size": len(self._history),
                "history_by_status": history_by_status,
                "average_duration_seconds": avg_duration,
                "total_completed": completed_count,
            }

    def get_history_sync(
        self,
        limit: int | None = None,
        status: OperationStatus | None = None,
        since: datetime | None = None,
    ) -> list[OperationContext]:
        """
        Get operation history (thread-safe, synchronous).

        This method can be called from any thread.

        Args:
            limit: Maximum number of operations to return
            status: Filter by final status
            since: Only return operations completed after this time

        Returns:
            List of historical operation contexts
        """
        with self._data_lock:
            history = self._history.copy()

        # Apply filters outside lock
        if status:
            history = [op for op in history if op.status == status]

        if since:
            history = [op for op in history if op.end_time and op.end_time >= since]

        # Apply limit
        if limit:
            history = history[-limit:]

        return history

    def cancel_operation_sync(
        self,
        operation_id: str,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> None:
        """
        Cancel a specific operation (thread-safe, asynchronous execution).

        This method can be called from any thread. It schedules the cancelation
        to be executed asynchronously and returns immediately.

        Args:
            operation_id: ID of operation to cancel
            reason: Reason for cancelation
            message: Optional cancelation message

        Note:
            The cancelation is scheduled via AnyioBridge and executes asynchronously.
            This method returns immediately without waiting for completion.
        """
        from hother.cancelable.utils.anyio_bridge import call_soon_threadsafe

        async def do_cancel():
            await self.cancel_operation(operation_id, reason, message)

        call_soon_threadsafe(do_cancel)

    def cancel_all_sync(
        self,
        status: OperationStatus | None = None,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> None:
        """
        Cancel all operations (thread-safe, asynchronous execution).

        This method can be called from any thread. It schedules the cancelation
        to be executed asynchronously and returns immediately.

        Args:
            status: Only cancel operations with this status
            reason: Reason for cancelation
            message: Optional cancelation message

        Note:
            The cancelation is scheduled via AnyioBridge and executes asynchronously.
            This method returns immediately without waiting for completion.
        """
        from hother.cancelable.utils.anyio_bridge import call_soon_threadsafe

        async def do_cancel():
            await self.cancel_all(status, reason, message)

        call_soon_threadsafe(do_cancel)
