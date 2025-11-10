"""
Unit tests for critical edge cases in the hother.cancelable library.

These tests verify that the bugs demonstrated in edge_case.py are properly fixed.
"""

import asyncio
import gc
import threading
import pytest

import anyio

from hother.cancelable import Cancelable
from hother.cancelable.core.cancelable import _current_operation


class TestContextVariableThreadSafety:
    """Test context variable propagation to threads."""

    @pytest.mark.anyio
    async def test_context_variable_propagation_to_threads(self):
        """Test that context variables propagate correctly to background threads."""
        results = []

        def check_context_in_thread(iteration: int):
            """Check context variable from a thread."""
            try:
                # Try to get current operation from thread
                current = _current_operation.get()
                results.append((iteration, current is not None, threading.current_thread().name))
                return current is not None
            except Exception as e:
                results.append((iteration, f"error: {e}", threading.current_thread().name))
                return False

        # Test context variable propagation
        async with Cancelable(name="context_test") as cancel:
            # Verify context is set in main thread
            main_context = _current_operation.get()
            assert main_context is not None
            assert main_context.context.name == "context_test"

            # Run multiple thread checks
            thread_results = await asyncio.gather(*[
                cancel.run_in_thread(check_context_in_thread, i) for i in range(5)
            ])

            # All thread operations should succeed
            assert all(thread_results)

        # Analyze results
        context_propagated = sum(1 for _, propagated, _ in results if propagated)
        context_failed = sum(1 for _, propagated, _ in results if not propagated)

        # All contexts should propagate successfully
        assert context_propagated == 5, f"Context failed in {context_failed} threads"
        assert context_failed == 0, "Context variables must propagate to all threads"

    @pytest.mark.anyio
    async def test_context_variable_isolation_between_operations(self):
        """Test that context variables are properly isolated between operations."""
        contexts: list[Cancelable | None] = [None, None]

        def capture_context_1():
            contexts[0] = _current_operation.get()
            return contexts[0] is not None

        def capture_context_2():
            contexts[1] = _current_operation.get()
            return contexts[1] is not None

        # Test with first operation
        async with Cancelable(name="operation_1") as cancel1:
            result1 = await cancel1.run_in_thread(capture_context_1)
            assert result1

        # Test with second operation
        async with Cancelable(name="operation_2") as cancel2:
            result2 = await cancel2.run_in_thread(capture_context_2)
            assert result2

        # Contexts should be different operations
        assert contexts[0] != contexts[1]
        assert contexts[0] is not None
        assert contexts[1] is not None


class TestCircularReferences:
    """Test for circular reference issues in parent-child relationships."""

    def test_no_circular_references_in_hierarchy(self):
        """Test that deep cancelable hierarchies don't create circular references."""
        # Track initial object count
        initial_objects = len(gc.get_objects())

        # Create a deep hierarchy of cancelables
        root = Cancelable(name="root")
        current = root

        # Create a deep chain: root -> child1 -> child2 -> ... -> child50
        for i in range(50):
            child = Cancelable(name=f"child_{i}", parent=current)
            current = child

        # Delete all references
        del root
        del current

        # Force garbage collection
        collected = gc.collect()

        # Check if objects were properly collected
        final_objects = len(gc.get_objects())
        object_growth = final_objects - initial_objects

        # In a well-behaved system, objects should be collected
        # Allow some growth for internal objects, but not the entire hierarchy
        assert object_growth < 25, f"Circular references detected: {object_growth} objects retained"

    def test_parent_child_relationship_cleanup(self):
        """Test that parent-child relationships are properly cleaned up."""
        initial_objects = len(gc.get_objects())

        # Create parent-child relationship
        parent = Cancelable(name="parent")
        child = Cancelable(name="child", parent=parent)

        # Verify relationship exists
        assert len(parent._children) == 1
        assert child._parent_ref is not None
        assert child._parent_ref() is parent

        # Delete references
        del parent
        del child

        # Force garbage collection
        collected = gc.collect()

        # Check for significant object retention
        final_objects = len(gc.get_objects())
        object_growth = final_objects - initial_objects

        assert object_growth < 10, f"Parent-child relationship leaking: {object_growth} objects retained"

    def test_weak_references_prevent_cycles(self):
        """Test that weak references prevent circular reference cycles."""
        # Create objects
        parent = Cancelable(name="parent")
        child = Cancelable(name="child", parent=parent)

        # Get weak references
        parent_ref = child._parent_ref
        child_ref = parent._children

        # Verify references work
        assert parent_ref is not None
        assert parent_ref() is parent
        assert len(child_ref) == 1
        assert list(child_ref)[0] is child

        # Delete strong references
        del parent
        del child

        # Force garbage collection
        gc.collect()

        # Weak references should now be dead
        assert parent_ref() is None
        assert len(child_ref) == 0


class TestMemoryLeakPrevention:
    """Test that various operations don't cause memory leaks."""

    @pytest.mark.anyio
    async def test_operation_context_cleanup(self):
        """Test that operation contexts are properly cleaned up."""
        from hother.cancelable.core.models import OperationContext
        from hother.cancelable.core.token import LinkedCancelationToken

        # Count specific object types that should be cleaned up
        def count_relevant_objects():
            objects = gc.get_objects()
            cancelable_count = sum(1 for obj in objects if isinstance(obj, Cancelable))
            context_count = sum(1 for obj in objects if isinstance(obj, OperationContext))
            token_count = sum(1 for obj in objects if isinstance(obj, LinkedCancelationToken))
            return cancelable_count, context_count, token_count

        initial_cancelable, initial_context, initial_token = count_relevant_objects()

        # Create and use multiple operations
        for i in range(10):
            async with Cancelable(name=f"operation_{i}") as cancel:
                # Do some work
                await asyncio.sleep(0.001)

        # Force garbage collection multiple times
        for _ in range(3):
            gc.collect()

        # Check that relevant objects were cleaned up
        final_cancelable, final_context, final_token = count_relevant_objects()

        # Allow some objects to remain (due to internal references, registry, etc.)
        # but not proportional to operations created
        cancelable_growth = final_cancelable - initial_cancelable
        context_growth = final_context - initial_context
        token_growth = final_token - initial_token

        assert cancelable_growth < 5, f"Cancelable objects leaking: {cancelable_growth} retained"
        assert context_growth < 5, f"OperationContext objects leaking: {context_growth} retained"
        assert token_growth < 5, f"LinkedCancelationToken objects leaking: {token_growth} retained"

    @pytest.mark.anyio
    async def test_thread_operation_cleanup(self):
        """Test that thread-based operations clean up properly."""
        from hother.cancelable.core.models import OperationContext
        from hother.cancelable.core.token import LinkedCancelationToken

        # Count specific object types that should be cleaned up
        def count_relevant_objects():
            objects = gc.get_objects()
            cancelable_count = sum(1 for obj in objects if isinstance(obj, Cancelable))
            context_count = sum(1 for obj in objects if isinstance(obj, OperationContext))
            token_count = sum(1 for obj in objects if isinstance(obj, LinkedCancelationToken))
            return cancelable_count, context_count, token_count

        initial_cancelable, initial_context, initial_token = count_relevant_objects()

        def dummy_thread_work():
            return "completed"

        # Create operations that use threads
        async with Cancelable(name="thread_test") as cancel:
            results = await asyncio.gather(*[
                cancel.run_in_thread(dummy_thread_work) for _ in range(10)
            ])

            assert len(results) == 10
            assert all(r == "completed" for r in results)

        # Force garbage collection multiple times
        for _ in range(3):
            gc.collect()

        # Check that relevant objects were cleaned up
        final_cancelable, final_context, final_token = count_relevant_objects()

        # Allow some objects to remain but not proportional to operations created
        cancelable_growth = final_cancelable - initial_cancelable
        context_growth = final_context - initial_context
        token_growth = final_token - initial_token

        assert cancelable_growth < 3, f"Cancelable objects leaking: {cancelable_growth} retained"
        assert context_growth < 3, f"OperationContext objects leaking: {context_growth} retained"
        assert token_growth < 3, f"LinkedCancelationToken objects leaking: {token_growth} retained"
