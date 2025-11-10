"""
Unit tests for decorator utilities.
"""

import anyio
import pytest
import signal
import sys

from hother.cancelable import (
    Cancelable,
    CancelationToken,
    CancelationReason,
)
from hother.cancelable.utils.decorators import (
    cancelable,
    cancelable_combine,
    cancelable_method,
    cancelable_with_condition,
    cancelable_with_signal,
    cancelable_with_token,
    with_cancelable,
    with_current_operation,
    with_timeout,
)


class TestCancelableDecorator:
    """Test @cancelable decorator."""

    @pytest.mark.anyio
    async def test_basic_decorator(self):
        """Test basic usage of @cancelable decorator."""
        @cancelable()
        async def simple_task():
            await anyio.sleep(0.01)
            return "done"

        result = await simple_task()
        assert result == "done"

    @pytest.mark.anyio
    async def test_decorator_with_timeout(self):
        """Test @cancelable with timeout parameter."""
        @cancelable(timeout=1.0)
        async def timed_task():
            await anyio.sleep(0.01)
            return "completed"

        result = await timed_task()
        assert result == "completed"

    @pytest.mark.anyio
    async def test_decorator_without_timeout(self):
        """Test @cancelable without timeout."""
        @cancelable()
        async def no_timeout_task():
            return "done"

        result = await no_timeout_task()
        assert result == "done"

    @pytest.mark.anyio
    async def test_decorator_with_inject_param(self):
        """Test @cancelable with parameter injection."""
        received_cancelable = None

        @cancelable(inject_param="cancelable")
        async def task_with_injection(data: str, cancelable: Cancelable):
            nonlocal received_cancelable
            received_cancelable = cancelable
            return data.upper()

        result = await task_with_injection("hello")
        assert result == "HELLO"
        assert received_cancelable is not None
        assert isinstance(received_cancelable, Cancelable)

    @pytest.mark.anyio
    async def test_decorator_without_inject_param(self):
        """Test @cancelable with injection disabled."""
        @cancelable(inject_param=None)
        async def task_no_injection():
            return "done"

        result = await task_no_injection()
        assert result == "done"

    @pytest.mark.anyio
    async def test_decorator_inject_param_not_in_signature(self):
        """Test that decorator doesn't inject if param not in signature."""
        @cancelable(inject_param="cancelable")
        async def task_without_param(data: str):
            return data.upper()

        result = await task_without_param("hello")
        assert result == "HELLO"

    @pytest.mark.anyio
    async def test_decorator_with_custom_name(self):
        """Test @cancelable with custom operation name."""
        @cancelable(name="custom_operation")
        async def task():
            return "done"

        result = await task()
        assert result == "done"

    @pytest.mark.anyio
    async def test_decorator_with_operation_id(self):
        """Test @cancelable with custom operation ID."""
        @cancelable(operation_id="op-12345")
        async def task():
            return "done"

        result = await task()
        assert result == "done"

    @pytest.mark.anyio
    async def test_decorator_with_register_globally(self):
        """Test @cancelable with global registration."""
        @cancelable(register_globally=True)
        async def task():
            return "done"

        result = await task()
        assert result == "done"

    @pytest.mark.anyio
    async def test_decorator_preserves_metadata(self):
        """Test that decorator preserves function metadata."""
        @cancelable(timeout=5.0, name="test_op")
        async def documented_task():
            """This is a documented function."""
            return "done"

        # Check wrapper has metadata attribute
        assert hasattr(documented_task, "_cancelable_params")
        params = documented_task._cancelable_params
        assert params["timeout"] == 5.0
        assert params["name"] == "test_op"
        assert params["register_globally"] is False

    @pytest.mark.anyio
    async def test_decorator_with_args_and_kwargs(self):
        """Test @cancelable with function arguments."""
        @cancelable()
        async def task_with_args(x: int, y: int, z: int = 0, cancelable: Cancelable = None):
            return x + y + z

        result = await task_with_args(1, 2, z=3)
        assert result == 6


class TestWithTimeout:
    """Test with_timeout utility function."""

    @pytest.mark.anyio
    async def test_with_timeout_basic(self):
        """Test basic timeout functionality."""
        async def quick_task():
            await anyio.sleep(0.01)
            return "completed"

        result = await with_timeout(1.0, quick_task())
        assert result == "completed"

    @pytest.mark.anyio
    async def test_with_timeout_with_operation_id(self):
        """Test with_timeout with custom operation ID."""
        async def task():
            return "done"

        result = await with_timeout(1.0, task(), operation_id="op-123")
        assert result == "done"

    @pytest.mark.anyio
    async def test_with_timeout_with_name(self):
        """Test with_timeout with custom name."""
        async def task():
            return "done"

        result = await with_timeout(1.0, task(), name="test_task")
        assert result == "done"


class TestWithCurrentOperation:
    """Test @with_current_operation decorator."""

    @pytest.mark.anyio
    async def test_current_operation_decorator(self):
        """Test basic @with_current_operation usage."""
        received_operation = None

        @with_current_operation()
        async def task_with_operation(operation: Cancelable = None):
            nonlocal received_operation
            received_operation = operation
            return "done"

        # Run inside a cancelable context
        async with Cancelable(name="parent_op"):
            result = await task_with_operation()

        assert result == "done"
        assert received_operation is not None

    @pytest.mark.anyio
    async def test_current_operation_no_operation_param(self):
        """Test decorator with function that doesn't have operation parameter."""
        @with_current_operation()
        async def task_without_param(data: str):
            return data.upper()

        result = await task_without_param("hello")
        assert result == "HELLO"

    @pytest.mark.anyio
    async def test_current_operation_operation_in_kwargs(self):
        """Test that decorator doesn't override if operation in kwargs."""
        custom_op = Cancelable(name="custom")

        @with_current_operation()
        async def task(operation: Cancelable = None):
            return operation.context.name if operation else None

        async with custom_op:
            # Pass operation explicitly in kwargs
            result = await task(operation=custom_op)

        assert result == "custom"


class TestCancelableMethod:
    """Test @cancelable_method decorator."""

    @pytest.mark.anyio
    async def test_method_decorator_basic(self):
        """Test basic @cancelable_method usage."""
        class Worker:
            @cancelable_method()
            async def process(self):
                return "processed"

        worker = Worker()
        result = await worker.process()
        assert result == "processed"

    @pytest.mark.anyio
    async def test_method_decorator_with_timeout(self):
        """Test @cancelable_method with timeout."""
        class Worker:
            @cancelable_method(timeout=1.0)
            async def process(self):
                await anyio.sleep(0.01)
                return "done"

        worker = Worker()
        result = await worker.process()
        assert result == "done"

    @pytest.mark.anyio
    async def test_method_decorator_without_timeout(self):
        """Test @cancelable_method without timeout."""
        class Worker:
            @cancelable_method()
            async def process(self):
                return "done"

        worker = Worker()
        result = await worker.process()
        assert result == "done"

    @pytest.mark.anyio
    async def test_method_decorator_with_cancelable_param(self):
        """Test @cancelable_method with cancelable parameter injection."""
        received_cancelable = None

        class Worker:
            @cancelable_method()
            async def process(self, data: str, cancelable: Cancelable):
                nonlocal received_cancelable
                received_cancelable = cancelable
                return data.upper()

        worker = Worker()
        result = await worker.process("hello")
        assert result == "HELLO"
        assert received_cancelable is not None

    @pytest.mark.anyio
    async def test_method_decorator_without_cancelable_param(self):
        """Test @cancelable_method when method doesn't have cancelable param."""
        class Worker:
            @cancelable_method()
            async def process(self, data: str):
                return data.upper()

        worker = Worker()
        result = await worker.process("hello")
        assert result == "HELLO"

    @pytest.mark.anyio
    async def test_method_decorator_uses_class_name(self):
        """Test that method decorator includes class name."""
        class DataProcessor:
            @cancelable_method()
            async def transform(self, cancelable: Cancelable):
                # Name should be DataProcessor.transform
                return cancelable.context.name if cancelable else None

        processor = DataProcessor()
        result = await processor.transform()
        assert result == "DataProcessor.transform"

    @pytest.mark.anyio
    async def test_method_decorator_with_custom_name(self):
        """Test @cancelable_method with custom name."""
        class Worker:
            @cancelable_method(name="custom_method")
            async def process(self, cancelable: Cancelable):
                return cancelable.context.name if cancelable else None

        worker = Worker()
        result = await worker.process()
        assert result == "custom_method"

    @pytest.mark.anyio
    async def test_method_decorator_with_register_globally(self):
        """Test @cancelable_method with global registration."""
        class Worker:
            @cancelable_method(register_globally=True)
            async def process(self):
                return "done"

        worker = Worker()
        result = await worker.process()
        assert result == "done"

    @pytest.mark.anyio
    async def test_method_decorator_with_args(self):
        """Test @cancelable_method with method arguments."""
        class Calculator:
            @cancelable_method()
            async def add(self, x: int, y: int, z: int = 0):
                return x + y + z

        calc = Calculator()
        result = await calc.add(1, 2, z=3)
        assert result == 6


class TestCancelableWithToken:
    """Test @cancelable_with_token decorator."""

    @pytest.mark.anyio
    async def test_token_decorator_basic(self):
        """Test basic token-based cancelation."""
        token = CancelationToken()

        @cancelable_with_token(token, name="token_task")
        async def task(cancelable: Cancelable):
            await anyio.sleep(0.01)
            return "completed"

        result = await task()
        assert result == "completed"

    @pytest.mark.anyio
    async def test_token_decorator_cancelation(self):
        """Test that token can be used to cancel decorated function."""
        token = CancelationToken()

        @cancelable_with_token(token, name="cancelable_task")
        async def task(cancelable: Cancelable):
            await anyio.sleep(0.01)
            return "completed"

        # First call should complete normally
        result = await task()
        assert result == "completed"

        # Cancel the token
        await token.cancel(CancelationReason.MANUAL, "Test")

        # Subsequent calls should be cancelled immediately
        with pytest.raises(anyio.get_cancelled_exc_class()):
            await task()

    @pytest.mark.anyio
    async def test_token_decorator_parameter_injection(self):
        """Test parameter injection in token decorator."""
        token = CancelationToken()
        received_cancelable = None

        @cancelable_with_token(token, inject_param="cancelable")
        async def task(data: str, cancelable: Cancelable):
            nonlocal received_cancelable
            received_cancelable = cancelable
            return data.upper()

        result = await task("hello")
        assert result == "HELLO"
        assert received_cancelable is not None
        assert isinstance(received_cancelable, Cancelable)

    @pytest.mark.anyio
    async def test_token_decorator_no_injection(self):
        """Test token decorator without parameter injection."""
        token = CancelationToken()

        @cancelable_with_token(token, inject_param=None)
        async def task(data: str):
            return data.upper()

        result = await task("hello")
        assert result == "HELLO"

    @pytest.mark.anyio
    async def test_token_decorator_inject_param_not_in_signature(self):
        """Test that decorator doesn't inject if param not in signature.

        Covers branch 249->252: inject_param is set but not in function signature.
        """
        token = CancelationToken()

        @cancelable_with_token(token, inject_param="my_cancel")
        async def task_without_param(data: str):
            # Function doesn't have 'my_cancel' parameter
            return data.upper()

        result = await task_without_param("hello")
        assert result == "HELLO"


@pytest.mark.skipif(sys.platform == "win32", reason="Signal handling not supported on Windows")
class TestCancelableWithSignal:
    """Test @cancelable_with_signal decorator."""

    @pytest.mark.anyio
    async def test_signal_decorator_basic(self):
        """Test basic signal-based cancelation setup."""

        @cancelable_with_signal(signal.SIGUSR1, name="signal_task")
        async def task(cancelable: Cancelable):
            await anyio.sleep(0.01)
            return "completed"

        result = await task()
        assert result == "completed"

    @pytest.mark.anyio
    async def test_signal_decorator_parameter_injection(self):
        """Test parameter injection in signal decorator."""
        received_cancelable = None

        @cancelable_with_signal(signal.SIGUSR1, inject_param="cancelable")
        async def task(data: str, cancelable: Cancelable):
            nonlocal received_cancelable
            received_cancelable = cancelable
            return data.upper()

        result = await task("hello")
        assert result == "HELLO"
        assert received_cancelable is not None
        assert isinstance(received_cancelable, Cancelable)

    @pytest.mark.anyio
    async def test_signal_decorator_inject_param_not_in_signature(self):
        """Test that decorator doesn't inject if param not in signature.

        Covers branch 305->308: inject_param is set but not in function signature.
        """

        @cancelable_with_signal(signal.SIGUSR1, inject_param="my_cancel")
        async def task_without_param(data: str):
            # Function doesn't have 'my_cancel' parameter
            return data.upper()

        result = await task_without_param("hello")
        assert result == "HELLO"

    @pytest.mark.anyio
    async def test_signal_decorator_no_injection_none(self):
        """Test signal decorator with inject_param=None.

        Covers branch 303->308: inject_param is None, no injection attempted.
        """

        @cancelable_with_signal(signal.SIGUSR1, inject_param=None)
        async def task_no_injection(data: str):
            return data.upper()

        result = await task_no_injection("hello")
        assert result == "HELLO"


class TestCancelableWithCondition:
    """Test @cancelable_with_condition decorator."""

    @pytest.mark.anyio
    async def test_condition_decorator_basic(self):
        """Test basic condition-based cancelation."""
        should_cancel = False

        @cancelable_with_condition(
            lambda: should_cancel, check_interval=0.01, condition_name="test_condition"
        )
        async def task(cancelable: Cancelable):
            await anyio.sleep(0.01)
            return "completed"

        result = await task()
        assert result == "completed"

    @pytest.mark.anyio
    async def test_condition_decorator_cancelation(self):
        """Test that condition triggers cancelation."""
        should_cancel = False

        @cancelable_with_condition(
            lambda: should_cancel, check_interval=0.01, condition_name="cancel_check"
        )
        async def task(cancelable: Cancelable):
            # Loop for a bit to allow condition check
            for _ in range(20):
                await anyio.sleep(0.01)
            return "completed"

        # First call with condition False should succeed
        result = await task()
        assert result == "completed"

        # Set condition to True
        should_cancel = True

        # Should be cancelled when condition is True
        with pytest.raises(anyio.get_cancelled_exc_class()):
            await task()

    @pytest.mark.anyio
    async def test_condition_decorator_parameter_injection(self):
        """Test parameter injection in condition decorator."""
        received_cancelable = None

        @cancelable_with_condition(lambda: False, check_interval=0.1, inject_param="cancelable")
        async def task(data: str, cancelable: Cancelable):
            nonlocal received_cancelable
            received_cancelable = cancelable
            return data.upper()

        result = await task("hello")
        assert result == "HELLO"
        assert received_cancelable is not None
        assert isinstance(received_cancelable, Cancelable)

    @pytest.mark.anyio
    async def test_condition_decorator_async_condition(self):
        """Test condition decorator with async condition function."""
        should_cancel = False

        async def async_condition():
            return should_cancel

        @cancelable_with_condition(async_condition, check_interval=0.01)
        async def task(cancelable: Cancelable):
            await anyio.sleep(0.01)
            return "completed"

        result = await task()
        assert result == "completed"

    @pytest.mark.anyio
    async def test_condition_decorator_inject_param_not_in_signature(self):
        """Test that decorator doesn't inject if param not in signature.

        Covers branch 370->373: inject_param is set but not in function signature.
        """

        @cancelable_with_condition(lambda: False, check_interval=0.1, inject_param="my_cancel")
        async def task_without_param(data: str):
            # Function doesn't have 'my_cancel' parameter
            return data.upper()

        result = await task_without_param("hello")
        assert result == "HELLO"

    @pytest.mark.anyio
    async def test_condition_decorator_no_injection_none(self):
        """Test condition decorator with inject_param=None.

        Covers branch 368->373: inject_param is None, no injection attempted.
        """

        @cancelable_with_condition(lambda: False, check_interval=0.1, inject_param=None)
        async def task_no_injection(data: str):
            return data.upper()

        result = await task_no_injection("hello")
        assert result == "HELLO"


class TestCancelableCombine:
    """Test @cancelable_combine decorator."""

    @pytest.mark.anyio
    async def test_combine_decorator_basic(self):
        """Test basic combine decorator with timeout."""
        timeout_cancel = Cancelable.with_timeout(1.0)

        @cancelable_combine(timeout_cancel, name="combined_task")
        async def task(cancelable: Cancelable):
            await anyio.sleep(0.01)
            return "completed"

        result = await task()
        assert result == "completed"

    @pytest.mark.anyio
    async def test_combine_decorator_with_token_cancel(self):
        """Test that combined sources work correctly."""
        token = CancelationToken()

        @cancelable_combine(
            Cancelable.with_timeout(10.0), Cancelable.with_token(token), name="multi_cancel"
        )
        async def task(cancelable: Cancelable):
            await anyio.sleep(0.01)
            return "completed"

        # Should work normally
        result = await task()
        assert result == "completed"

    @pytest.mark.anyio
    async def test_combine_decorator_parameter_injection(self):
        """Test parameter injection in combine decorator."""
        received_cancelable = None
        timeout_cancel = Cancelable.with_timeout(1.0)

        @cancelable_combine(timeout_cancel, inject_param="cancelable")
        async def task(data: str, cancelable: Cancelable):
            nonlocal received_cancelable
            received_cancelable = cancelable
            return data.upper()

        result = await task("hello")
        assert result == "HELLO"
        assert received_cancelable is not None
        assert isinstance(received_cancelable, Cancelable)

    @pytest.mark.anyio
    async def test_combine_decorator_name_override(self):
        """Test that custom name overrides combined name."""
        timeout_cancel = Cancelable.with_timeout(1.0)
        received_cancelable = None

        @cancelable_combine(timeout_cancel, name="custom_name")
        async def task(cancelable: Cancelable):
            nonlocal received_cancelable
            received_cancelable = cancelable
            return "done"

        result = await task()
        assert result == "done"
        assert received_cancelable is not None
        assert received_cancelable.context.name == "custom_name"

    @pytest.mark.anyio
    async def test_combine_decorator_uses_function_name(self):
        """Test that function name is used if no custom name provided."""
        received_cancelable = None

        @cancelable_combine(Cancelable.with_timeout(1.0))
        async def my_special_task(cancelable: Cancelable):
            nonlocal received_cancelable
            received_cancelable = cancelable
            return "done"

        result = await my_special_task()
        assert result == "done"
        assert received_cancelable is not None
        # Should use function name instead of generated "combined_" name
        assert received_cancelable.context.name == "my_special_task"

    @pytest.mark.anyio
    async def test_combine_decorator_empty_raises_error(self):
        """Test that combining with no cancelables raises error."""
        with pytest.raises(ValueError, match="At least one cancelable must be provided"):

            @cancelable_combine()
            async def task():
                return "done"

            await task()

    @pytest.mark.anyio
    async def test_combine_decorator_inject_param_not_in_signature(self):
        """Test that decorator doesn't inject if param not in signature.

        Covers branch 454->457: inject_param is set but not in function signature.
        """
        timeout_cancel = Cancelable.with_timeout(1.0)

        @cancelable_combine(timeout_cancel, inject_param="my_cancel")
        async def task_without_param(data: str):
            # Function doesn't have 'my_cancel' parameter
            return data.upper()

        result = await task_without_param("hello")
        assert result == "HELLO"

    @pytest.mark.anyio
    async def test_combine_decorator_no_injection_none(self):
        """Test combine decorator with inject_param=None.

        Covers branch 452->457: inject_param is None, no injection attempted.
        """
        timeout_cancel = Cancelable.with_timeout(1.0)

        @cancelable_combine(timeout_cancel, inject_param=None)
        async def task_no_injection(data: str):
            return data.upper()

        result = await task_no_injection("hello")
        assert result == "HELLO"


class TestDecoratorEdgeCases:
    """Test edge cases and error handling in decorators."""

    @pytest.mark.anyio
    async def test_nested_decorators(self):
        """Test that decorators can be nested."""

        @cancelable(timeout=1.0, inject_param="outer_cancel")
        async def outer_task(outer_cancel: Cancelable = None):
            @cancelable()
            async def inner_task(inner_cancelable: Cancelable = None):
                return "inner"

            return await inner_task()

        result = await outer_task()
        assert result == "inner"

    @pytest.mark.anyio
    async def test_decorator_with_exception(self):
        """Test that decorators properly propagate exceptions."""

        @cancelable()
        async def failing_task():
            raise ValueError("Task failed")

        with pytest.raises(ValueError, match="Task failed"):
            await failing_task()

    @pytest.mark.anyio
    async def test_all_decorators_preserve_function_name(self):
        """Test that all decorators preserve function name."""
        token = CancelationToken()

        @cancelable()
        async def task1():
            return "1"

        @cancelable_with_token(token)
        async def task2():
            return "2"

        @cancelable_with_condition(lambda: False, check_interval=0.1)
        async def task3():
            return "3"

        timeout_cancel = Cancelable.with_timeout(1.0)

        @cancelable_combine(timeout_cancel)
        async def task4():
            return "4"

        assert task1.__name__ == "task1"
        assert task2.__name__ == "task2"
        assert task3.__name__ == "task3"
        assert task4.__name__ == "task4"


class TestWithCancelable:
    """Test @with_cancelable decorator."""

    @pytest.mark.anyio
    async def test_with_existing_instance_no_injection(self):
        """Test @with_cancelable with existing instance and no injection."""
        cancel = Cancelable(name="test_operation")
        result_value = None

        @with_cancelable(cancel)
        async def task():
            nonlocal result_value
            # Access via current_operation
            from hother.cancelable import current_operation
            ctx = current_operation()
            assert ctx is not None
            assert ctx.context.name == "test_operation"
            result_value = "completed"
            return result_value

        async with cancel:
            result = await task()
            assert result == "completed"
            assert result_value == "completed"

    @pytest.mark.anyio
    async def test_with_existing_instance_with_injection(self):
        """Test @with_cancelable with injection enabled."""
        cancel = Cancelable(name="test_operation")
        received_cancel = None

        @with_cancelable(cancel, inject=True)
        async def task(cancelable: Cancelable):
            nonlocal received_cancel
            received_cancel = cancelable
            await cancelable.report_progress("working")
            return "done"

        async with cancel:
            result = await task()
            assert result == "done"
            assert received_cancel is cancel

    @pytest.mark.anyio
    async def test_with_existing_instance_custom_inject_param(self):
        """Test @with_cancelable with custom inject parameter name."""
        cancel = Cancelable(name="test_operation")
        received_cancel = None

        @with_cancelable(cancel, inject=True, inject_param="ctx")
        async def task(ctx: Cancelable = None):
            nonlocal received_cancel
            received_cancel = ctx
            return "done"

        async with cancel:
            result = await task()
            assert result == "done"
            assert received_cancel is cancel

    @pytest.mark.anyio
    async def test_with_timeout_instance(self):
        """Test @with_cancelable with timeout instance."""
        cancel = Cancelable.with_timeout(1.0, name="timed_op")

        @with_cancelable(cancel)
        async def task():
            await anyio.sleep(0.01)
            return "completed"

        async with cancel:
            result = await task()
            assert result == "completed"

    @pytest.mark.anyio
    async def test_with_timeout_instance_triggers(self):
        """Test @with_cancelable respects timeout from instance."""
        cancel = Cancelable.with_timeout(0.1, name="timed_op")

        @with_cancelable(cancel)
        async def task():
            await anyio.sleep(1.0)
            return "should not reach"

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancel:
                await task()

    @pytest.mark.anyio
    async def test_with_token_instance(self):
        """Test @with_cancelable with token-based instance."""
        token = CancelationToken()
        cancel = Cancelable.with_token(token, name="token_op")

        @with_cancelable(cancel, inject=True)
        async def task(cancelable: Cancelable):
            # Verify we got the right cancelable instance
            assert cancelable is cancel
            await anyio.sleep(0.1)
            return "completed"

        # Test that decorator works with token-based cancelable
        async with cancel:
            result = await task()
            assert result == "completed"

    @pytest.mark.anyio
    async def test_shared_instance_multiple_functions(self):
        """Test sharing same Cancelable instance across multiple functions."""
        cancel = Cancelable(name="shared_context")
        results = []

        @with_cancelable(cancel)
        async def task1():
            from hother.cancelable import current_operation
            ctx = current_operation()
            assert ctx.context.name == "shared_context"
            results.append("task1")
            return "done1"

        @with_cancelable(cancel)
        async def task2():
            from hother.cancelable import current_operation
            ctx = current_operation()
            assert ctx.context.name == "shared_context"
            results.append("task2")
            return "done2"

        async with cancel:
            result1 = await task1()
            result2 = await task2()
            assert result1 == "done1"
            assert result2 == "done2"
            assert results == ["task1", "task2"]

    @pytest.mark.anyio
    async def test_preserves_function_name(self):
        """Test that decorator preserves function name."""
        cancel = Cancelable(name="test")

        @with_cancelable(cancel)
        async def my_function():
            return "test"

        assert my_function.__name__ == "my_function"

    @pytest.mark.anyio
    async def test_no_injection_when_param_not_in_signature(self):
        """Test no injection when parameter not in function signature."""
        cancel = Cancelable(name="test")

        @with_cancelable(cancel, inject=True, inject_param="cancelable")
        async def task_without_param(data: str):
            # Should not fail even though inject=True
            return data.upper()

        async with cancel:
            result = await task_without_param("hello")
            assert result == "HELLO"

    @pytest.mark.anyio
    async def test_with_args_and_kwargs(self):
        """Test decorator works with function args and kwargs."""
        cancel = Cancelable(name="test")

        @with_cancelable(cancel, inject=True)
        async def task(arg1: str, arg2: int, cancelable: Cancelable = None, kwarg1: str = "default"):
            assert cancelable is cancel
            return f"{arg1}-{arg2}-{kwarg1}"

        async with cancel:
            result = await task("test", 42, kwarg1="custom")
            assert result == "test-42-custom"

    @pytest.mark.anyio
    async def test_exception_propagation(self):
        """Test that exceptions are properly propagated."""
        cancel = Cancelable(name="test")

        @with_cancelable(cancel)
        async def failing_task():
            raise ValueError("Task failed")

        with pytest.raises(ValueError, match="Task failed"):
            async with cancel:
                await failing_task()

    @pytest.mark.anyio
    async def test_current_operation_access(self):
        """Test accessing context via current_operation()."""
        from hother.cancelable import current_operation

        cancel = Cancelable.with_timeout(10.0, name="test_context")
        progress_messages = []

        @with_cancelable(cancel)
        async def task():
            ctx = current_operation()
            assert ctx is not None
            assert ctx.context.name == "test_context"

            # Test progress reporting via current_operation
            await ctx.report_progress("step 1")
            progress_messages.append("step 1")
            await anyio.sleep(0.01)

            await ctx.report_progress("step 2")
            progress_messages.append("step 2")

            return "completed"

        async with cancel:
            result = await task()
            assert result == "completed"
            assert progress_messages == ["step 1", "step 2"]
