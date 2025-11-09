"""
Context bridge utilities for thread-safe context variable propagation.

This module provides utilities to safely propagate context variables between
async tasks and OS threads, solving the context variable thread safety issue.
"""

import asyncio
import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")


class ContextBridge:
    """
    Thread-safe context variable bridge for async-to-thread communication.

    This class solves the issue where context variables don't propagate
    to OS threads created by ThreadPoolExecutor, breaking operation tracking
    in multi-threaded applications.
    """

    @staticmethod
    def copy_context() -> dict[contextvars.ContextVar[Any], Any]:
        """
        Copy current context variables to a dict for thread transport.

        Returns:
            Dictionary mapping context variables to their current values
        """
        ctx = contextvars.copy_context()
        return dict(ctx)

    @staticmethod
    def restore_context(context_dict: dict[contextvars.ContextVar[Any], Any]) -> None:
        """
        Restore context variables from a dictionary.

        Args:
            context_dict: Dictionary mapping context variables to values
        """
        for var, value in context_dict.items():
            var.set(value)

    @staticmethod
    async def run_in_thread_with_context(
        func: Callable[..., T], *args: Any, executor: ThreadPoolExecutor | None = None, **kwargs: Any
    ) -> T:
        """
        Run function in thread with context variables propagated.

        This method safely copies context variables to the thread, runs the
        function, and returns the result.

        Args:
            func: Function to run in thread
            *args: Positional arguments for func
            executor: Optional thread pool executor (default: None for default executor)
            **kwargs: Keyword arguments for func

        Returns:
            Result of func execution

        Example:
            ```python
            async def async_func():
                result = await ContextBridge.run_in_thread_with_context(
                    expensive_computation, data, param=value
                )
                return result
            ```
        """
        # Copy current context
        ctx = ContextBridge.copy_context()

        def thread_func():
            # Restore context in thread
            ContextBridge.restore_context(ctx)
            return func(*args, **kwargs)

        # Run in thread
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, thread_func)
