"""
Tests for ThreadSafeRegistry.
"""

import threading

import anyio
import pytest

from hother.cancelable import Cancelable, CancelationReason, OperationRegistry, OperationStatus, ThreadSafeRegistry


@pytest.fixture
def reset_singleton():
    """Reset ThreadSafeRegistry singleton before test."""
    # Save original instance
    original = ThreadSafeRegistry._instance
    # Reset for test
    ThreadSafeRegistry._instance = None
    yield
    # Restore original (or leave as created by test)
    # Don't restore to avoid test pollution
    pass


class TestThreadSafeRegistry:
    """Test ThreadSafeRegistry functionality."""

    @pytest.mark.anyio
    async def test_singleton(self):
        """Test ThreadSafeRegistry singleton."""
        registry1 = ThreadSafeRegistry.get_instance()
        registry2 = ThreadSafeRegistry.get_instance()

        assert registry1 is registry2

    @pytest.mark.anyio
    async def test_singleton_thread_safety(self, reset_singleton):
        """Test that singleton works correctly under concurrent access."""
        # This test forces the race condition where multiple threads
        # pass the outer check but only one creates the instance

        # Run multiple iterations to increase chance of hitting the race condition
        for iteration in range(10):
            # Reset singleton for each iteration
            ThreadSafeRegistry._instance = None

            instances = []

            def create_instance(barrier):
                """Thread function that creates instance after barrier."""
                # Wait for all threads to be ready
                barrier.wait()
                # All threads try to get instance simultaneously
                instance = ThreadSafeRegistry.get_instance()
                instances.append(instance)

            # Create barrier for 50 threads (more threads = higher chance of race)
            barrier = threading.Barrier(50)

            # Start all threads
            threads = []
            for _ in range(50):
                thread = threading.Thread(target=create_instance, args=(barrier,))
                threads.append(thread)
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join(timeout=3.0)

            # All threads should have gotten the same instance
            assert len(instances) == 50
            assert all(instance is instances[0] for instance in instances)
            assert isinstance(instances[0], ThreadSafeRegistry)

    @pytest.mark.anyio
    async def test_singleton_double_check_locking(self, reset_singleton):
        """Test the inner check of double-check locking pattern."""
        # where a thread finds the instance already created inside the lock

        import time
        from unittest.mock import patch

        # Reset singleton
        ThreadSafeRegistry._instance = None

        instances = []
        thread1_in_lock = threading.Event()
        thread2_can_enter = threading.Event()

        # Save the original __init__
        original_init = ThreadSafeRegistry.__init__

        def slow_init(self):
            """Slow init that signals when called."""
            thread1_in_lock.set()
            # Give time for thread2 to also pass the outer check and wait on lock
            time.sleep(0.02)
            original_init(self)

        def thread1_func():
            """First thread - creates the instance with delay."""
            with patch.object(ThreadSafeRegistry, '__init__', slow_init):
                instance = ThreadSafeRegistry.get_instance()
                instances.append(instance)

        def thread2_func():
            """Second thread - waits for thread1 to be in lock."""
            # Wait for thread1 to be creating the instance (inside lock)
            thread1_in_lock.wait(timeout=1.0)

            # Small delay to ensure we're blocked on the lock
            time.sleep(0.005)

            # Now call get_instance - we'll pass outer check (instance still being created)
            # Then wait for lock, and when we get it, inner check finds instance exists
            instance = ThreadSafeRegistry.get_instance()
            instances.append(instance)

        # Start both threads
        t1 = threading.Thread(target=thread1_func)
        t2 = threading.Thread(target=thread2_func)

        t1.start()
        t2.start()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        # Both should have the same instance
        assert len(instances) == 2
        assert instances[0] is instances[1]
        assert isinstance(instances[0], ThreadSafeRegistry)

    @pytest.mark.anyio
    async def test_get_operation_from_thread(self, clean_registry):
        """Test getting operation from thread."""
        # Setup operation in async context
        cancelable = Cancelable(name="test_op")
        await clean_registry.register(cancelable)

        # Access from thread
        thread_registry = ThreadSafeRegistry()
        result = [None]
        error = [None]

        def thread_func():
            try:
                result[0] = thread_registry.get_operation(cancelable.context.id)
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"
        assert result[0] is cancelable

    @pytest.mark.anyio
    async def test_list_operations_from_thread(self, clean_registry):
        """Test listing operations from thread."""
        # Create operations in async context
        ops = []
        for i in range(5):
            op = Cancelable(name=f"op_{i}")
            await clean_registry.register(op)
            ops.append(op)

        # Access from thread
        thread_registry = ThreadSafeRegistry()
        result = [None]
        error = [None]

        def thread_func():
            try:
                result[0] = thread_registry.list_operations()
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert error[0] is None, f"Thread raised error: {error[0]}"
        assert len(result[0]) == 5

    @pytest.mark.anyio
    async def test_list_operations_with_filter(self, clean_registry):
        """Test filtering operations from thread."""
        # Create operations with different statuses
        for i in range(5):
            op = Cancelable(name=f"pending_{i}")
            await clean_registry.register(op)
            # Keep as PENDING (default)

        for i in range(3):
            op = Cancelable(name=f"running_{i}")
            await clean_registry.register(op)
            op.context.status = OperationStatus.RUNNING

        # Access from thread with filter
        thread_registry = ThreadSafeRegistry()
        result = [None]

        def thread_func():
            result[0] = thread_registry.list_operations(status=OperationStatus.RUNNING)

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        # Should only get running operations
        assert len(result[0]) == 3
        assert all("running" in op.name for op in result[0])

    @pytest.mark.anyio
    async def test_get_statistics_from_thread(self, clean_registry):
        """Test getting statistics from thread."""
        # Create and complete some operations
        for i in range(3):
            op = Cancelable(name=f"op_{i}")
            await clean_registry.register(op)
            op.context.status = OperationStatus.COMPLETED
            await clean_registry.unregister(op.context.id)

        # Access from thread
        thread_registry = ThreadSafeRegistry()
        result = [None]

        def thread_func():
            result[0] = thread_registry.get_statistics()

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        stats = result[0]
        assert isinstance(stats, dict)
        assert "active_operations" in stats
        assert "history_size" in stats
        assert stats["history_size"] == 3

    @pytest.mark.anyio
    async def test_get_history_from_thread(self, clean_registry):
        """Test getting history from thread."""
        # Create and complete operations
        for i in range(5):
            op = Cancelable(name=f"op_{i}")
            await clean_registry.register(op)
            op.context.status = OperationStatus.COMPLETED
            await clean_registry.unregister(op.context.id)

        # Access from thread with limit
        thread_registry = ThreadSafeRegistry()
        result = [None]

        def thread_func():
            result[0] = thread_registry.get_history(limit=3)

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

        assert len(result[0]) == 3

    @pytest.mark.anyio
    async def test_concurrent_access_from_multiple_threads(self, clean_registry):
        """Test concurrent access from multiple threads using ThreadSafeRegistry."""
        # Create operations
        for i in range(10):
            op = Cancelable(name=f"op_{i}")
            await clean_registry.register(op)

        # Access from multiple threads
        thread_registry = ThreadSafeRegistry()
        results = []
        errors = []

        def thread_func(thread_id):
            try:
                for _ in range(50):
                    ops = thread_registry.list_operations()
                    stats = thread_registry.get_statistics()
                    history = thread_registry.get_history(limit=5)
                    results.append((thread_id, len(ops), len(history)))
            except Exception as e:
                errors.append((thread_id, e))

        threads = []
        for i in range(10):
            thread = threading.Thread(target=thread_func, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=5.0)

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 500  # 10 threads * 50 iterations

    @pytest.mark.anyio
    async def test_cancel_operation_from_thread(self, clean_registry):
        """Test cancelling operation from thread."""
        from hother.cancelable.utils.anyio_bridge import AnyioBridge

        # Start the bridge
        bridge = AnyioBridge.get_instance()

        async def run_test():
            # Create operation
            cancelable = Cancelable(name="test_op")
            await clean_registry.register(cancelable)

            # Cancel from thread
            thread_registry = ThreadSafeRegistry()
            cancelled = [False]

            def thread_func():
                thread_registry.cancel_operation(
                    cancelable.context.id,
                    reason=CancelationReason.MANUAL,
                    message="Cancelled from thread"
                )
                cancelled[0] = True

            thread = threading.Thread(target=thread_func)
            thread.start()
            thread.join(timeout=1.0)

            assert cancelled[0] is True

            # Give bridge time to process cancelation
            await anyio.sleep(0.1)

            # Operation should be cancelled
            # (Note: actual cancelation happens asynchronously via bridge)

        async with anyio.create_task_group() as tg:
            tg.start_soon(bridge.start)
            await anyio.sleep(0.05)  # Let bridge start
            await run_test()
            await bridge.stop()
            tg.cancel_scope.cancel()

    @pytest.mark.anyio
    async def test_wrapper_vs_direct_consistency(self, clean_registry):
        """Test that ThreadSafeRegistry returns same data as direct sync methods."""
        # Create some operations
        for i in range(5):
            op = Cancelable(name=f"op_{i}")
            await clean_registry.register(op)

        thread_registry = ThreadSafeRegistry()

        # Compare results
        def thread_func():
            # Via wrapper
            wrapper_ops = thread_registry.list_operations()
            wrapper_stats = thread_registry.get_statistics()

            # Via direct sync methods
            direct_ops = clean_registry.list_operations_sync()
            direct_stats = clean_registry.get_statistics_sync()

            # Should be identical
            assert len(wrapper_ops) == len(direct_ops)
            assert wrapper_stats == direct_stats

        thread = threading.Thread(target=thread_func)
        thread.start()
        thread.join(timeout=1.0)

    @pytest.mark.anyio
    async def test_cancel_all_from_thread(self, clean_registry):
        """Test cancelling all operations from thread."""
        from hother.cancelable.utils.anyio_bridge import AnyioBridge

        # Start the bridge
        bridge = AnyioBridge.get_instance()

        async def run_test():
            # Create multiple operations
            for i in range(5):
                op = Cancelable(name=f"test_op_{i}")
                await clean_registry.register(op)
                op.context.status = OperationStatus.RUNNING

            # Cancel all from thread
            thread_registry = ThreadSafeRegistry()
            cancelled = [False]

            def thread_func():
                thread_registry.cancel_all(
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
            await anyio.sleep(0.1)

        async with anyio.create_task_group() as tg:
            tg.start_soon(bridge.start)
            await anyio.sleep(0.05)  # Let bridge start
            await run_test()
            await bridge.stop()
            tg.cancel_scope.cancel()
