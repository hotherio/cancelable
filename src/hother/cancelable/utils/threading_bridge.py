"""
Thread-safe wrapper for OperationRegistry.

Provides synchronous API for accessing the registry from threads.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from hother.cancelable.core.models import CancelationReason, OperationContext, OperationStatus
from hother.cancelable.core.registry import OperationRegistry

if TYPE_CHECKING:
    from hother.cancelable.core.cancelable import Cancelable


class ThreadSafeRegistry:
    """
    Thread-safe wrapper for OperationRegistry.

    Provides synchronous API for accessing the registry from threads.
    All methods are thread-safe and can be called from any thread.

    This class wraps the OperationRegistry singleton and provides
    convenience methods without the `_sync` suffix.

    Example:
        ```python
        # From a thread (e.g., Flask/Django handler)
        from hother.cancelable import ThreadSafeRegistry

        registry = ThreadSafeRegistry()

        # List running operations
        operations = registry.list_operations(status=OperationStatus.RUNNING)

        # Cancel a specific operation
        registry.cancel_operation(op_id, reason=CancelationReason.MANUAL)

        # Get statistics
        stats = registry.get_statistics()
        print(f"Active operations: {stats['active_operations']}")
        ```

    Note:
        - Read operations (get, list, statistics, history) return immediately with data
        - Write operations (cancel) schedule async work and return immediately
        - For async code, use OperationRegistry directly instead
    """

    def __init__(self):
        """Initialize thread-safe registry wrapper."""
        self._registry = OperationRegistry.get_instance()

    def get_operation(self, operation_id: str) -> Optional["Cancelable"]:
        """
        Get operation by ID.

        Args:
            operation_id: Operation ID to look up

        Returns:
            Cancelable operation or None if not found
        """
        return self._registry.get_operation_sync(operation_id)

    def list_operations(
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
        return self._registry.list_operations_sync(status, parent_id, name_pattern)

    def get_statistics(self) -> dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with operation statistics containing:
            - active_operations: Number of active operations
            - active_by_status: Active operations grouped by status
            - history_size: Number of operations in history
            - history_by_status: Historical operations grouped by status
            - average_duration_seconds: Average duration of completed operations
            - total_completed: Total number of completed operations
        """
        return self._registry.get_statistics_sync()

    def get_history(
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
        return self._registry.get_history_sync(limit, status, since)

    def cancel_operation(
        self,
        operation_id: str,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> None:
        """
        Cancel a specific operation.

        Schedules cancelation to be executed asynchronously and returns immediately.

        Args:
            operation_id: ID of operation to cancel
            reason: Reason for cancelation
            message: Optional cancelation message

        Note:
            This method returns immediately. The cancelation is scheduled
            asynchronously via AnyioBridge.
        """
        self._registry.cancel_operation_sync(operation_id, reason, message)

    def cancel_all(
        self,
        status: OperationStatus | None = None,
        reason: CancelationReason = CancelationReason.MANUAL,
        message: str | None = None,
    ) -> None:
        """
        Cancel all operations with optional status filter.

        Schedules cancelation to be executed asynchronously and returns immediately.

        Args:
            status: Only cancel operations with this status
            reason: Reason for cancelation
            message: Optional cancelation message

        Note:
            This method returns immediately. The cancelation is scheduled
            asynchronously via AnyioBridge.
        """
        self._registry.cancel_all_sync(status, reason, message)

    # Singleton pattern (optional - users can create instances directly or use singleton)

    _instance: "ThreadSafeRegistry | None" = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ThreadSafeRegistry":
        """
        Get singleton instance of thread-safe registry.

        Thread-safe lazy initialization.

        Returns:
            The singleton ThreadSafeRegistry instance

        Example:
            ```python
            registry = ThreadSafeRegistry.get_instance()
            stats = registry.get_statistics()
            ```
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
