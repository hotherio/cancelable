"""
Tests for async cancellation decorators.
"""

from datetime import timedelta

import anyio
import pytest

from cancelable import Cancellable, current_operation
from cancelable.utils.decorators import cancellable, cancellable_method, with_current_operation, with_timeout


class TestCancellableDecorator:
    """Test @cancellable decorator."""

    @pytest.mark.anyio
    async def test_basic_decorator(self):
        """Test basic decorator usage."""
        call_count = 0

        @cancellable()
        async def decorated_function(value: int) -> int:
            nonlocal call_count
            call_count += 1
            await anyio.sleep(0.1)
            return value * 2

        result = await decorated_function(21)
        assert result == 42
        assert call_count == 1

    @pytest.mark.anyio
    async def test_decorator_with_timeout(self):
        """Test decorator with timeout."""

        @cancellable(timeout=0.1)
        async def slow_function():
            await anyio.sleep(1.0)
            return "completed"

        with pytest.raises(anyio.get_cancelled_exc_class()):
            await slow_function()

    @pytest.mark.anyio
    async def test_decorator_with_injection(self):
        """Test decorator with cancellable injection."""

        @cancellable(timeout=1.0)
        async def function_with_cancellable(data: str, cancellable: Cancellable = None) -> str:
            await cancellable.report_progress(f"Processing {data}")
            await anyio.sleep(0.1)
            await cancellable.report_progress("Done")
            return data.upper()

        # Capture progress through wrapper attribute
        result = await function_with_cancellable("test")

        assert result == "TEST"

    @pytest.mark.anyio
    async def test_decorator_with_custom_params(self):
        """Test decorator with custom parameters."""
        operation_found = False

        @cancellable(operation_id="custom-op-123", name="custom_operation", register_globally=True)
        async def custom_function(cancellable: Cancellable = None):
            nonlocal operation_found
            # Check registry while operation is running
            from cancelable import OperationRegistry

            registry = OperationRegistry.get_instance()
            ops = await registry.list_operations()
            operation_found = any(op.id == "custom-op-123" for op in ops)
            return cancellable.context.id

        from cancelable import OperationRegistry

        registry = OperationRegistry.get_instance()

        # Clear registry
        await registry.clear_all()

        # Run function
        op_id = await custom_function()

        assert op_id == "custom-op-123"
        assert operation_found, "Operation was not found in registry while running"

        # After completion, should be in history
        history = await registry.get_history()
        assert any(op.id == "custom-op-123" for op in history)

        # Cleanup
        await registry.clear_all()

    @pytest.mark.anyio
    async def test_decorator_no_injection(self):
        """Test decorator with injection disabled."""

        @cancellable(inject_param=None)
        async def no_injection_function(value: int) -> int:
            # No cancellable parameter
            await anyio.sleep(0.05)
            return value + 1

        result = await no_injection_function(10)
        assert result == 11

    @pytest.mark.anyio
    async def test_decorator_custom_injection_name(self):
        """Test decorator with custom injection parameter name."""

        @cancellable(inject_param="cancel_ctx")
        async def custom_param_function(value: int, cancel_ctx: Cancellable = None) -> int:
            await cancel_ctx.report_progress(f"Value: {value}")
            return value * 3

        result = await custom_param_function(7)
        assert result == 21

    @pytest.mark.anyio
    async def test_decorator_preserves_metadata(self):
        """Test that decorator preserves function metadata."""

        @cancellable(timeout=5.0)
        async def documented_function(x: int) -> int:
            """This function has documentation."""
            return x * 2

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This function has documentation."

        # Check decorator parameters are accessible
        assert hasattr(documented_function, "_cancellable_params")
        params = documented_function._cancellable_params
        assert params["timeout"] == 5.0
        assert params["name"] == "documented_function"


class TestWithTimeout:
    """Test with_timeout helper."""

    @pytest.mark.anyio
    async def test_with_timeout_success(self):
        """Test successful completion within timeout."""

        async def quick_operation():
            await anyio.sleep(0.05)
            return "success"

        result = await with_timeout(1.0, quick_operation())
        assert result == "success"

    @pytest.mark.anyio
    async def test_with_timeout_cancellation(self):
        """Test timeout cancellation."""

        async def slow_operation():
            await anyio.sleep(1.0)
            return "success"

        with pytest.raises(anyio.get_cancelled_exc_class()):
            await with_timeout(0.1, slow_operation())

    @pytest.mark.anyio
    async def test_with_timeout_timedelta(self):
        """Test with_timeout with timedelta."""

        async def operation():
            await anyio.sleep(0.05)
            return 42

        result = await with_timeout(timedelta(seconds=1), operation())
        assert result == 42

    @pytest.mark.anyio
    async def test_with_timeout_custom_params(self):
        """Test with_timeout with custom parameters."""

        async def operation():
            # Get current operation to check params
            op = current_operation()
            return op.context.id if op else None

        op_id = await with_timeout(1.0, operation(), operation_id="test-timeout-op", name="timeout_test")

        assert op_id == "test-timeout-op"


class TestWithCurrentOperation:
    """Test with_current_operation decorator."""

    @pytest.mark.anyio
    async def test_current_operation_injection(self):
        """Test injecting current operation."""

        @with_current_operation()
        async def function_with_operation(value: int, operation: Cancellable = None) -> str:
            if operation:
                return f"{operation.context.name}:{value}"
            return f"no_op:{value}"

        # Without active operation
        result = await function_with_operation(1)
        assert result == "no_op:1"

        # With active operation
        async with Cancellable(name="test_op"):
            result = await function_with_operation(2)
            assert result == "test_op:2"

    @pytest.mark.anyio
    async def test_current_operation_no_param(self):
        """Test function without operation parameter."""

        @with_current_operation()
        async def function_without_param(value: int) -> int:
            # No operation parameter
            return value * 2

        # Should work without error
        result = await function_without_param(5)
        assert result == 10

    @pytest.mark.anyio
    async def test_current_operation_already_provided(self):
        """Test when operation is already provided."""

        @with_current_operation()
        async def function_with_operation(operation: Cancellable = None) -> str:
            return operation.context.name if operation else "none"

        custom_op = Cancellable(name="custom")

        # Explicitly provided operation takes precedence
        async with Cancellable(name="context_op"):
            result = await function_with_operation(operation=custom_op)
            assert result == "custom"


class TestCancellableMethod:
    """Test @cancellable_method decorator."""

    @pytest.mark.anyio
    async def test_method_decorator(self):
        """Test decorator on class methods."""

        class DataProcessor:
            def __init__(self):
                self.processed_count = 0

            @cancellable_method(timeout=1.0)
            async def process(self, items: list[int], cancellable: Cancellable = None) -> int:
                total = 0
                for i, item in enumerate(items):
                    await anyio.sleep(0.01)
                    total += item

                    if i % 10 == 0:
                        await cancellable.report_progress(f"Processed {i}/{len(items)}")

                self.processed_count += len(items)
                return total

        processor = DataProcessor()
        result = await processor.process(list(range(10)))

        assert result == sum(range(10))
        assert processor.processed_count == 10

    @pytest.mark.anyio
    async def test_method_decorator_timeout(self):
        """Test method decorator with timeout."""

        class SlowProcessor:
            @cancellable_method(timeout=0.1)
            async def process(self, cancellable: Cancellable = None):
                await anyio.sleep(1.0)
                return "done"

        processor = SlowProcessor()

        with pytest.raises(anyio.get_cancelled_exc_class()):
            await processor.process()

    @pytest.mark.anyio
    async def test_method_decorator_name(self):
        """Test method decorator generates correct name."""

        class TestClass:
            @cancellable_method()
            async def test_method(self, cancellable: Cancellable = None):
                return cancellable.context.name

        obj = TestClass()
        name = await obj.test_method()

        assert name == "TestClass.test_method"

    @pytest.mark.anyio
    async def test_method_decorator_custom_name(self):
        """Test method decorator with custom name."""

        class TestClass:
            @cancellable_method(name="custom_method_name")
            async def method(self, cancellable: Cancellable = None):
                return cancellable.context.name

        obj = TestClass()
        name = await obj.method()

        assert name == "custom_method_name"

    @pytest.mark.anyio
    async def test_method_decorator_inheritance(self):
        """Test method decorator with inheritance."""

        class BaseProcessor:
            @cancellable_method(timeout=1.0)
            async def process(self, data: str, cancellable: Cancellable = None):
                await cancellable.report_progress("Base processing")
                return data.upper()

        class DerivedProcessor(BaseProcessor):
            @cancellable_method(timeout=2.0)
            async def process(self, data: str, cancellable: Cancellable = None):
                await cancellable.report_progress("Derived processing")
                base_result = await super().process(data)
                return f"[{base_result}]"

        processor = DerivedProcessor()
        result = await processor.process("test")

        # Note: super() call creates new cancellable context
        assert result == "[TEST]"
