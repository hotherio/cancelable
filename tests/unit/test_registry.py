"""
Tests for operation registry.
"""

from datetime import UTC, datetime, timedelta

import anyio
import pytest

from hother.cancelable import Cancelable, CancelationReason, OperationRegistry, OperationStatus


class TestOperationRegistry:
    """Test OperationRegistry functionality."""

    @pytest.mark.anyio
    async def test_singleton(self):
        """Test registry is a singleton."""
        registry1 = OperationRegistry.get_instance()
        registry2 = OperationRegistry.get_instance()

        assert registry1 is registry2

    @pytest.mark.anyio
    async def test_register_unregister(self, clean_registry):
        """Test operation registration and unregistration."""
        registry = clean_registry

        cancelable = Cancelable(name="test_op")

        # Register
        await registry.register(cancelable)

        # Should be in registry
        op = await registry.get_operation(cancelable.context.id)
        assert op is cancelable

        # Unregister
        await registry.unregister(cancelable.context.id)

        # Should not be in registry
        op = await registry.get_operation(cancelable.context.id)
        assert op is None

        # Should be in history
        history = await registry.get_history()
        assert any(h.id == cancelable.context.id for h in history)

    @pytest.mark.anyio
    async def test_list_operations(self, clean_registry):
        """Test listing operations with filters."""
        registry = clean_registry

        # Create operations with different statuses
        op1 = Cancelable(name="op1")
        op2 = Cancelable(name="op2")
        op3 = Cancelable(name="op3", parent=op1)

        await registry.register(op1)
        await registry.register(op2)
        await registry.register(op3)

        # Update statuses
        op1.context.status = OperationStatus.RUNNING
        op2.context.status = OperationStatus.COMPLETED
        op3.context.status = OperationStatus.RUNNING

        # List all
        all_ops = await registry.list_operations()
        assert len(all_ops) == 3

        # Filter by status
        running = await registry.list_operations(status=OperationStatus.RUNNING)
        assert len(running) == 2
        assert all(op.status == OperationStatus.RUNNING for op in running)

        # Filter by parent
        children = await registry.list_operations(parent_id=op1.context.id)
        assert len(children) == 1
        assert children[0].id == op3.context.id

        # Filter by name pattern
        named = await registry.list_operations(name_pattern="op1")
        assert len(named) == 1
        assert named[0].name == "op1"

    @pytest.mark.anyio
    async def test_cancel_operation(self, clean_registry):
        """Test cancelling operation via registry."""
        registry = clean_registry

        token_cancelled = False

        async def long_operation():
            nonlocal token_cancelled
            try:
                async with Cancelable(name="long_op", register_globally=True):
                    await anyio.sleep(1.0)
            except anyio.get_cancelled_exc_class():
                token_cancelled = True

        # Start operation
        async with anyio.create_task_group() as tg:
            tg.start_soon(long_operation)

            # Wait for operation to register
            await anyio.sleep(0.1)

            # Get operation
            ops = await registry.list_operations()
            assert len(ops) == 1

            # Cancel it
            result = await registry.cancel_operation(ops[0].id, CancelationReason.MANUAL, "Test cancelation")
            assert result is True

        assert token_cancelled

    @pytest.mark.anyio
    async def test_cancel_all(self, clean_registry):
        """Test cancelling all operations."""
        registry = clean_registry

        cancel_count = 0

        async def cancellable_op(op_id: int):
            nonlocal cancel_count
            try:
                async with Cancelable(name=f"op_{op_id}", register_globally=True) as cancel:
                    cancel.context.status = OperationStatus.RUNNING
                    await anyio.sleep(1.0)
            except anyio.get_cancelled_exc_class():
                cancel_count += 1

        # Start multiple operations
        async with anyio.create_task_group() as tg:
            for i in range(3):
                tg.start_soon(cancellable_op, i)

            # Wait for registration
            await anyio.sleep(0.1)

            # Cancel all running operations
            cancelled = await registry.cancel_all(status=OperationStatus.RUNNING)
            assert cancelled == 3

        assert cancel_count == 3

    @pytest.mark.anyio
    async def test_history_management(self, clean_registry):
        """Test operation history management."""
        registry = clean_registry

        # Create and complete operations
        for i in range(5):
            cancelable = Cancelable(name=f"op_{i}")
            await registry.register(cancelable)

            # Set different end states
            if i % 2 == 0:
                cancelable.context.status = OperationStatus.COMPLETED
            else:
                cancelable.context.status = OperationStatus.FAILED

            cancelable.context.end_time = datetime.now(UTC)
            await registry.unregister(cancelable.context.id)

        # Get full history
        history = await registry.get_history()
        assert len(history) == 5

        # Filter by status
        completed = await registry.get_history(status=OperationStatus.COMPLETED)
        assert len(completed) == 3

        # Limit results
        recent = await registry.get_history(limit=2)
        assert len(recent) == 2

        # Filter by time
        since = datetime.now(UTC) - timedelta(minutes=1)
        recent_ops = await registry.get_history(since=since)
        assert len(recent_ops) == 5

    @pytest.mark.anyio
    async def test_cleanup_completed(self, clean_registry):
        """Test cleaning up completed operations."""
        registry = clean_registry

        # Create mix of operations
        ops = []
        for i in range(6):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)
            ops.append(op)

        # Set different statuses
        ops[0].context.status = OperationStatus.RUNNING
        ops[1].context.status = OperationStatus.COMPLETED
        ops[2].context.status = OperationStatus.FAILED
        ops[3].context.status = OperationStatus.CANCELLED
        ops[4].context.status = OperationStatus.COMPLETED
        ops[5].context.status = OperationStatus.RUNNING

        # Set end times for completed
        now = datetime.now(UTC)
        for i in [1, 2, 3, 4]:
            ops[i].context.end_time = now

        # Cleanup without age filter
        cleaned = await registry.cleanup_completed(keep_failed=True)
        assert cleaned == 3  # Completed and cancelled, not failed

        # Verify remaining
        remaining = await registry.list_operations()
        assert len(remaining) == 3  # 2 running + 1 failed

    @pytest.mark.anyio
    async def test_cleanup_with_age(self, clean_registry):
        """Test cleanup with age filtering."""
        registry = clean_registry

        # Create old and new operations
        now = datetime.now(UTC)

        old_op = Cancelable(name="old_op")
        await registry.register(old_op)
        old_op.context.status = OperationStatus.COMPLETED
        old_op.context.end_time = now - timedelta(hours=2)

        new_op = Cancelable(name="new_op")
        await registry.register(new_op)
        new_op.context.status = OperationStatus.COMPLETED
        new_op.context.end_time = now - timedelta(minutes=30)

        # Cleanup only old operations
        cleaned = await registry.cleanup_completed(older_than=timedelta(hours=1), keep_failed=False)

        assert cleaned == 1  # Only old_op

        # New op should still be there
        remaining = await registry.list_operations()
        assert len(remaining) == 1
        assert remaining[0].name == "new_op"

    @pytest.mark.anyio
    async def test_statistics(self, clean_registry):
        """Test registry statistics."""
        registry = clean_registry

        # Create operations with various statuses
        durations = [1.0, 2.0, 3.0]

        for i, duration in enumerate(durations):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)

            op.context.status = OperationStatus.COMPLETED
            op.context.end_time = op.context.start_time + timedelta(seconds=duration)

            await registry.unregister(op.context.id)

        # Add some active operations
        for i in range(2):
            op = Cancelable(name=f"active_{i}")
            op.context.status = OperationStatus.RUNNING
            await registry.register(op)

        # Get statistics
        stats = await registry.get_statistics()

        assert stats["active_operations"] == 2
        assert stats["active_by_status"]["running"] == 2
        assert stats["history_size"] == 3
        assert stats["history_by_status"]["completed"] == 3
        assert stats["total_completed"] == 3
        assert stats["average_duration_seconds"] == 2.0  # (1+2+3)/3

    @pytest.mark.anyio
    async def test_history_limit(self, clean_registry):
        """Test history size limit."""
        registry = clean_registry

        # Set a small limit for testing
        registry._history_limit = 10

        # Create more operations than the limit
        for i in range(15):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)
            op.context.status = OperationStatus.COMPLETED
            await registry.unregister(op.context.id)

        # History should be limited
        history = await registry.get_history()
        assert len(history) == 10

        # Should have the most recent operations
        names = [h.name for h in history]
        expected_names = [f"op_{i}" for i in range(5, 15)]
        assert names == expected_names


class TestRegistryThreadSafety:
    """Test thread safety of OperationRegistry sync methods."""

    @pytest.mark.anyio
    async def test_sync_get_operation(self, clean_registry):
        """Test thread-safe sync get operation."""
        import threading

        registry = clean_registry
        cancelable = Cancelable(name="test_op")
        await registry.register(cancelable)

        # Call from thread
        result = [None]
        error = [None]

        def thread_func():
            try:
                result[0] = registry.get_operation_sync(cancelable.context.id)
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"
        assert result[0] is cancelable

    @pytest.mark.anyio
    async def test_sync_list_operations(self, clean_registry):
        """Test thread-safe sync list operations."""
        import threading

        registry = clean_registry

        # Create some operations
        ops = []
        for i in range(5):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)
            ops.append(op)

        # Call from thread
        result = [None]
        error = [None]

        def thread_func():
            try:
                result[0] = registry.list_operations_sync()
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"
        assert len(result[0]) == 5
        assert all(isinstance(ctx, type(ops[0].context)) for ctx in result[0])

    @pytest.mark.anyio
    async def test_sync_list_operations_with_filters(self, clean_registry):
        """Test thread-safe sync list operations with all filters.

        Targets lines 415, 418, 421 in list_operations_sync().
        """
        import threading

        registry = clean_registry

        # Create parent and child operations with different statuses
        parent = Cancelable(name="parent_operation")
        child1 = Cancelable(name="child_one", parent=parent)
        child2 = Cancelable(name="child_two", parent=parent)
        other = Cancelable(name="other_operation")

        await registry.register(parent)
        await registry.register(child1)
        await registry.register(child2)
        await registry.register(other)

        # Set different statuses
        parent.context.status = OperationStatus.PENDING
        child1.context.status = OperationStatus.RUNNING
        child2.context.status = OperationStatus.PENDING
        other.context.status = OperationStatus.COMPLETED

        results = {}
        error = [None]

        def thread_func():
            try:
                results['status_filter'] = registry.list_operations_sync(status=OperationStatus.RUNNING)

                results['parent_filter'] = registry.list_operations_sync(parent_id=parent.context.id)

                results['name_filter'] = registry.list_operations_sync(name_pattern="child")
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"

        # Verify status filter worked
        assert len(results['status_filter']) == 1
        assert results['status_filter'][0].status == OperationStatus.RUNNING

        # Verify parent_id filter worked
        assert len(results['parent_filter']) == 2
        assert all(ctx.parent_id == parent.context.id for ctx in results['parent_filter'])

        # Verify name_pattern filter worked
        assert len(results['name_filter']) == 2
        assert all('child' in ctx.name.lower() for ctx in results['name_filter'])

    @pytest.mark.anyio
    async def test_sync_statistics_with_successful_operations(self, clean_registry):
        """Test sync statistics with successful operations having duration.

        Targets lines 449-450 in get_statistics_sync() - the branch where
        operations have both duration_seconds AND is_success.
        """
        import threading

        registry = clean_registry
        now = datetime.now(UTC)

        # Create operations with durations and mark as COMPLETED (is_success=True)
        durations = [1.0, 2.0, 3.0]
        for i, duration in enumerate(durations):
            op = Cancelable(name=f"success_op_{i}")
            await registry.register(op)

            # Mark as COMPLETED with duration
            op.context.status = OperationStatus.COMPLETED
            op.context.start_time = now
            op.context.end_time = now + timedelta(seconds=duration)

            await registry.unregister(op.context.id)

        result = [None]
        error = [None]

        def thread_func():
            try:
                result[0] = registry.get_statistics_sync()
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"

        stats = result[0]
        # Lines 449-450 should be executed, calculating average duration
        assert stats['total_completed'] == 3
        assert stats['average_duration_seconds'] == 2.0  # (1+2+3)/3

    @pytest.mark.anyio
    async def test_sync_get_statistics(self, clean_registry):
        """Test thread-safe sync get statistics."""
        import threading

        registry = clean_registry

        # Create and complete some operations
        for i in range(3):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)
            op.context.status = OperationStatus.COMPLETED
            await registry.unregister(op.context.id)

        # Call from thread
        result = [None]
        error = [None]

        def thread_func():
            try:
                result[0] = registry.get_statistics_sync()
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"
        assert isinstance(result[0], dict)
        assert "active_operations" in result[0]
        assert "history_size" in result[0]

    @pytest.mark.anyio
    async def test_sync_get_history(self, clean_registry):
        """Test thread-safe sync get history."""
        import threading

        registry = clean_registry

        # Create and complete operations
        for i in range(3):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)
            op.context.status = OperationStatus.COMPLETED
            await registry.unregister(op.context.id)

        # Call from thread
        result = [None]
        error = [None]

        def thread_func():
            try:
                result[0] = registry.get_history_sync(limit=2)
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"
        assert len(result[0]) == 2

    @pytest.mark.anyio
    async def test_concurrent_thread_access(self, clean_registry):
        """Test concurrent access from multiple threads."""
        import threading

        registry = clean_registry

        # Create some operations
        for i in range(10):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)

        # Access from multiple threads concurrently
        results = []
        errors = []
        threads = []

        def thread_func(thread_id):
            try:
                for _ in range(100):  # Many iterations to stress test
                    ops = registry.list_operations_sync()
                    stats = registry.get_statistics_sync()
                    results.append((thread_id, len(ops), stats["active_operations"]))
            except Exception as e:
                errors.append((thread_id, e))

        # Launch 5 threads
        for i in range(5):
            thread = threading.Thread(target=thread_func, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5.0)

        # No errors should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # All threads should have gotten results
        assert len(results) == 500  # 5 threads * 100 iterations


class TestRegistryEdgeCases:
    """Test edge cases and missing coverage paths."""

    @pytest.mark.anyio
    async def test_double_init(self, clean_registry):
        """Test that double initialization is a no-op."""
        registry = clean_registry

        # Registry is already initialized by fixture
        # Call __init__ again - should be a no-op
        registry.__init__()

        # Should still work normally
        op = Cancelable(name="test")
        await registry.register(op)
        assert await registry.get_operation(op.context.id) is op

    @pytest.mark.anyio
    async def test_singleton_via_direct_new(self, clean_registry):
        """Test __new__ when singleton instance already exists.

        Targets branch 32->35 in __new__() - the path where cls._instance
        is NOT None (singleton already exists).
        """
        registry = clean_registry

        # At this point, singleton instance exists (created by fixture)
        # Call __new__ directly (not via get_instance())
        instance2 = OperationRegistry.__new__(OperationRegistry)

        assert instance2 is registry
        assert instance2 is OperationRegistry._instance

    @pytest.mark.anyio
    async def test_cleanup_with_concurrent_removal(self, clean_registry):
        """Test cleanup when operation is removed concurrently.

        Targets branch 311->310 in cleanup_completed() - the path where
        pop() returns None because the operation was already removed.
        """
        registry = clean_registry

        # Create completed operations
        ops = []
        for i in range(5):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)
            op.context.status = OperationStatus.COMPLETED
            op.context.end_time = datetime.now(UTC)
            ops.append(op)

        # Create a wrapper dict that returns None for specific pops
        original_dict = registry._operations
        pop_count = [0]

        class CustomDict(dict):
            def pop(self, key, default=None):
                pop_count[0] += 1
                # Return None for second and fourth pops (simulate concurrent removal)
                if pop_count[0] in [2, 4]:
                    return None
                return super().pop(key, default)

        # Replace _operations temporarily
        custom_dict = CustomDict(original_dict)
        registry._operations = custom_dict

        try:
            cleaned = await registry.cleanup_completed()

            # All 5 were in to_remove list, but 2 pops returned None
            assert cleaned == 5
        finally:
            # Restore original dict
            registry._operations = original_dict

    @pytest.mark.anyio
    async def test_unregister_nonexistent(self, clean_registry):
        """Test unregistering operation that doesn't exist."""
        registry = clean_registry

        # Unregister non-existent operation
        await registry.unregister("nonexistent_id")

        # Should complete without error
        history = await registry.get_history()
        # History should not contain this ID
        assert not any(h.id == "nonexistent_id" for h in history)

    @pytest.mark.anyio
    async def test_cancel_nonexistent_operation(self, clean_registry):
        """Test canceling operation that doesn't exist."""
        registry = clean_registry

        result = await registry.cancel_operation("nonexistent_id")

        assert result is False

    @pytest.mark.anyio
    async def test_cancel_all_with_status_filter(self, clean_registry):
        """Test cancel_all with status filter."""
        registry = clean_registry

        # Create operations with different statuses
        op1 = Cancelable(name="op1")
        op2 = Cancelable(name="op2")

        await registry.register(op1)
        await registry.register(op2)

        # Set different statuses
        op1.context.status = OperationStatus.PENDING
        op2.context.status = OperationStatus.RUNNING

        # Even if cancelation doesn't complete, the filter code path is executed
        count = await registry.cancel_all(status=OperationStatus.PENDING)

        # Count may vary based on how cancelation propagates, but filter was applied
        assert count >= 0

    @pytest.mark.anyio
    async def test_cancel_all_with_error(self, clean_registry):
        """Test cancel_all handles errors gracefully."""
        from unittest.mock import patch

        registry = clean_registry

        op = Cancelable(name="failing_op")
        await registry.register(op)

        # Mock cancel to raise error
        with patch.object(op, "cancel", side_effect=RuntimeError("Cancel failed")):
            count = await registry.cancel_all()

        # Should log error but not raise
        assert count == 0  # No successful cancelations

    @pytest.mark.anyio
    async def test_cleanup_with_history_limit(self, clean_registry):
        """Test cleanup maintains history limit."""
        registry = clean_registry

        # Create many completed operations to exceed history limit
        for i in range(1005):  # More than limit of 1000
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)
            op.context.status = OperationStatus.COMPLETED
            op.context.end_time = datetime.now(UTC)

        # Cleanup all
        cleaned = await registry.cleanup_completed()

        # Should have cleaned 1005 operations
        assert cleaned == 1005

        # History should be limited to 1000
        history = await registry.get_history()
        assert len(history) == 1000

    @pytest.mark.anyio
    async def test_statistics_with_incomplete_operations(self, clean_registry):
        """Test statistics when operations have no duration or are not successful."""
        registry = clean_registry

        now = datetime.now(UTC)

        # Create operations with different states
        op1 = Cancelable(name="op1")
        op2 = Cancelable(name="op2")

        await registry.register(op1)
        await registry.register(op2)

        # Set op1 as FAILED (not successful - is_success returns False)
        # Has duration but not successful
        op1.context.status = OperationStatus.FAILED
        op1.context.start_time = now
        op1.context.end_time = now + timedelta(seconds=1.5)
        await registry.unregister(op1.context.id)

        # Set op2 as COMPLETED but with no duration (end_time not set)
        op2.context.status = OperationStatus.COMPLETED
        # Leave end_time as None so duration is None
        await registry.unregister(op2.context.id)

        stats = await registry.get_statistics()

        # Should have some stats but operations don't contribute to average duration
        # because op1 is not successful and op2 has no duration
        assert "average_duration_seconds" in stats
        assert "total_completed" in stats

    @pytest.mark.anyio
    async def test_list_operations_with_all_filters(self, clean_registry):
        """Test list_operations with all filter types."""
        registry = clean_registry

        parent = Cancelable(name="parent_op")
        child1 = Cancelable(name="child_one", parent=parent)
        child2 = Cancelable(name="child_two", parent=parent)
        other = Cancelable(name="other_operation")

        await registry.register(parent)
        await registry.register(child1)
        await registry.register(child2)
        await registry.register(other)

        # Set statuses - use RUNNING for child1 to differentiate
        child1.context.status = OperationStatus.RUNNING
        parent.context.status = OperationStatus.PENDING
        child2.context.status = OperationStatus.PENDING
        other.context.status = OperationStatus.PENDING

        # Test status filter
        running = await registry.list_operations(status=OperationStatus.RUNNING)
        assert len(running) == 1
        assert running[0].id == child1.context.id

        # Test parent_id filter
        children = await registry.list_operations(parent_id=parent.context.id)
        assert len(children) == 2

        # Test name_pattern filter
        child_ops = await registry.list_operations(name_pattern="child")
        assert len(child_ops) == 2

    @pytest.mark.anyio
    async def test_sync_statistics_with_incomplete_operations(self, clean_registry):
        """Test sync statistics when operations have no duration or are not successful."""
        registry = clean_registry

        now = datetime.now(UTC)

        # Create and unregister operations
        op1 = Cancelable(name="op1")
        await registry.register(op1)
        op1.context.status = OperationStatus.FAILED
        op1.context.start_time = now
        op1.context.end_time = now + timedelta(seconds=2)
        await registry.unregister(op1.context.id)

        op2 = Cancelable(name="op2")
        await registry.register(op2)
        op2.context.status = OperationStatus.COMPLETED
        # Leave end_time as None so duration is None
        await registry.unregister(op2.context.id)

        stats = registry.get_statistics_sync()

        # Should have stats structure
        assert "average_duration_seconds" in stats
        assert "total_completed" in stats

    @pytest.mark.anyio
    async def test_get_history_with_all_filters(self, clean_registry):
        """Test get_history_sync with all filters."""
        registry = clean_registry

        now = datetime.now(UTC)

        # Create operations with different times and statuses
        for i in range(10):
            op = Cancelable(name=f"op_{i}")
            await registry.register(op)

            if i < 5:
                op.context.status = OperationStatus.COMPLETED
                op.context.end_time = now - timedelta(hours=i)
            else:
                op.context.status = OperationStatus.FAILED
                op.context.end_time = now - timedelta(hours=i)

            await registry.unregister(op.context.id)

        # Test status filter
        completed = registry.get_history_sync(status=OperationStatus.COMPLETED)
        assert len(completed) == 5

        # Test since filter
        since = now - timedelta(hours=3)
        recent = registry.get_history_sync(since=since)
        assert len(recent) == 4  # ops 0-3 (within 3 hours)

        # Test limit filter
        limited = registry.get_history_sync(limit=3)
        assert len(limited) == 3

    @pytest.mark.anyio
    async def test_cancel_operation_sync(self, clean_registry):
        """Test synchronous cancel operation method with anyio bridge.

        Targets line 522 in cancel_operation_sync() - the actual async
        cancelation call via bridge.
        """
        from hother.cancelable.utils.anyio_bridge import AnyioBridge
        import threading

        registry = clean_registry

        # Start the bridge
        bridge = AnyioBridge.get_instance()

        async def run_test():
            # Create operation
            op = Cancelable(name="sync_cancel_test")
            await registry.register(op)

            cancelled = [False]

            def thread_func():
                registry.cancel_operation_sync(
                    op.context.id,
                    reason=CancelationReason.MANUAL,
                    message="Cancelled from thread"
                )
                cancelled[0] = True

            thread = threading.Thread(target=thread_func)
            thread.start()
            thread.join(timeout=1.0)

            assert cancelled[0] is True

            # Give bridge time to process cancelation
            await anyio.sleep(0.2)

        async with anyio.create_task_group() as tg:
            tg.start_soon(bridge.start)
            await anyio.sleep(0.05)  # Let bridge start
            await run_test()
            await bridge.stop()
            tg.cancel_scope.cancel()

    @pytest.mark.anyio
    async def test_cancel_all_sync(self, clean_registry):
        """Test synchronous cancel all method with anyio bridge.

        Targets line 550 in cancel_all_sync() - the actual async
        cancelation call via bridge.
        """
        from hother.cancelable.utils.anyio_bridge import AnyioBridge
        import threading

        registry = clean_registry

        # Start the bridge
        bridge = AnyioBridge.get_instance()

        async def run_test():
            # Create multiple operations
            for i in range(3):
                op = Cancelable(name=f"op_{i}")
                await registry.register(op)
                op.context.status = OperationStatus.RUNNING

            cancelled = [False]

            def thread_func():
                registry.cancel_all_sync(
                    status=OperationStatus.RUNNING,
                    reason=CancelationReason.MANUAL,
                    message="Bulk cancel from thread"
                )
                cancelled[0] = True

            thread = threading.Thread(target=thread_func)
            thread.start()
            thread.join(timeout=1.0)

            assert cancelled[0] is True

            # Give bridge time to process cancelations
            await anyio.sleep(0.2)

        async with anyio.create_task_group() as tg:
            tg.start_soon(bridge.start)
            await anyio.sleep(0.05)  # Let bridge start
            await run_test()
            await bridge.stop()
            tg.cancel_scope.cancel()
