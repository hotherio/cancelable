"""
Unit tests for context_bridge.py utilities.
"""

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from hother.cancelable.utils.context_bridge import ContextBridge


class TestContextBridge:
    """Test ContextBridge functionality."""

    def test_copy_context(self):
        """Test copying current context variables."""
        # Create a context variable
        var = contextvars.ContextVar('test_var', default='default')

        # Set a value
        var.set('test_value')

        # Copy context
        context_dict = ContextBridge.copy_context()

        # Should contain our variable
        assert var in context_dict
        assert context_dict[var] == 'test_value'

    def test_restore_context(self):
        """Test restoring context variables."""
        var1 = contextvars.ContextVar('var1', default='default1')
        var2 = contextvars.ContextVar('var2', default='default2')

        # Set values
        var1.set('value1')
        var2.set('value2')

        # Copy context
        context_dict = ContextBridge.copy_context()

        # Reset variables
        var1.set('changed1')
        var2.set('changed2')

        # Restore context
        ContextBridge.restore_context(context_dict)

        # Should have restored values
        assert var1.get() == 'value1'
        assert var2.get() == 'value2'

    @pytest.mark.anyio
    async def test_run_in_thread_with_context(self):
        """Test running function in thread with context propagation."""
        # Create context variable
        var = contextvars.ContextVar('thread_var', default='default')

        # Set value in async context
        var.set('async_value')

        # Function to run in thread
        def thread_function():
            # Should have the context variable value
            return var.get()

        # Run in thread with context
        result = await ContextBridge.run_in_thread_with_context(thread_function)

        assert result == 'async_value'

    @pytest.mark.anyio
    async def test_run_in_thread_with_context_args(self):
        """Test running function in thread with arguments."""
        var = contextvars.ContextVar('arg_var', default='default')
        var.set('context_value')

        def thread_function(x, y, z=None):
            return f"{var.get()}-{x}-{y}-{z}"

        result = await ContextBridge.run_in_thread_with_context(
            thread_function,
            1, 2, z=3
        )

        assert result == "context_value-1-2-3"

    @pytest.mark.anyio
    async def test_run_in_thread_with_context_executor(self):
        """Test using custom thread pool executor."""
        var = contextvars.ContextVar('executor_var', default='default')
        var.set('executor_value')

        def thread_function():
            return var.get()

        # Use custom executor
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = await ContextBridge.run_in_thread_with_context(
                thread_function,
                executor=executor
            )

        assert result == 'executor_value'

    @pytest.mark.anyio
    async def test_context_isolation(self):
        """Test that context changes in thread don't affect main context."""
        var = contextvars.ContextVar('isolation_var', default='original')

        var.set('main_value')

        def thread_function():
            # Change value in thread
            var.set('thread_value')
            return var.get()

        # Run in thread
        thread_result = await ContextBridge.run_in_thread_with_context(thread_function)

        # Thread should see its own change
        assert thread_result == 'thread_value'

        # Main context should still have original value
        assert var.get() == 'main_value'

    @pytest.mark.anyio
    async def test_multiple_context_vars(self):
        """Test propagation of multiple context variables."""
        var1 = contextvars.ContextVar('multi1', default='def1')
        var2 = contextvars.ContextVar('multi2', default='def2')
        var3 = contextvars.ContextVar('multi3', default='def3')

        var1.set('val1')
        var2.set('val2')
        # var3 keeps default

        def thread_function():
            return {
                'var1': var1.get(),
                'var2': var2.get(),
                'var3': var3.get(),
            }

        result = await ContextBridge.run_in_thread_with_context(thread_function)

        assert result == {
            'var1': 'val1',
            'var2': 'val2',
            'var3': 'def3',
        }

    @pytest.mark.anyio
    async def test_context_inheritance(self):
        """Test that thread inherits the context at call time."""
        var = contextvars.ContextVar('inherit_var', default='default')

        async def async_function():
            var.set('async_set')

            # Start thread from within async function
            def thread_function():
                return var.get()

            return await ContextBridge.run_in_thread_with_context(thread_function)

        result = await async_function()
        assert result == 'async_set'