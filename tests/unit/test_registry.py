"""
Tests for operation registry.
"""

from datetime import UTC, datetime, timedelta

import anyio
import pytest

from cancelable import Cancellable, CancellationReason, OperationRegistry, OperationStatus


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

        cancellable = Cancellable(name="test_op")

        # Register
        await registry.register(cancellable)

        # Should be in registry
        op = await registry.get_operation(cancellable.context.id)
        assert op is cancellable

        # Unregister
        await registry.unregister(cancellable.context.id)

        # Should not be in registry
        op = await registry.get_operation(cancellable.context.id)
        assert op is None

        # Should be in history
        history = await registry.get_history()
        assert any(h.id == cancellable.context.id for h in history)

    @pytest.mark.anyio
    async def test_list_operations(self, clean_registry):
        """Test listing operations with filters."""
        registry = clean_registry

        # Create operations with different statuses
        op1 = Cancellable(name="op1")
        op2 = Cancellable(name="op2")
        op3 = Cancellable(name="op3", parent=op1)

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
                async with Cancellable(name="long_op", register_globally=True):
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
            result = await registry.cancel_operation(ops[0].id, CancellationReason.MANUAL, "Test cancellation")
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
                async with Cancellable(name=f"op_{op_id}", register_globally=True) as cancel:
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
            cancellable = Cancellable(name=f"op_{i}")
            await registry.register(cancellable)

            # Set different end states
            if i % 2 == 0:
                cancellable.context.status = OperationStatus.COMPLETED
            else:
                cancellable.context.status = OperationStatus.FAILED

            cancellable.context.end_time = datetime.now(UTC)
            await registry.unregister(cancellable.context.id)

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
            op = Cancellable(name=f"op_{i}")
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

        old_op = Cancellable(name="old_op")
        await registry.register(old_op)
        old_op.context.status = OperationStatus.COMPLETED
        old_op.context.end_time = now - timedelta(hours=2)

        new_op = Cancellable(name="new_op")
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
            op = Cancellable(name=f"op_{i}")
            await registry.register(op)

            op.context.status = OperationStatus.COMPLETED
            op.context.end_time = op.context.start_time + timedelta(seconds=duration)

            await registry.unregister(op.context.id)

        # Add some active operations
        for i in range(2):
            op = Cancellable(name=f"active_{i}")
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
            op = Cancellable(name=f"op_{i}")
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
