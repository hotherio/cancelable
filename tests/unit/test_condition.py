"""Unit tests for condition cancellation source."""

import anyio
import pytest

from hother.cancelable.core.models import CancelationReason
from hother.cancelable.sources.condition import ConditionSource, ResourceConditionSource


class TestConditionSource:
    """Test ConditionSource functionality."""

    @pytest.mark.anyio
    async def test_condition_basic(self):
        """Test basic condition monitoring."""
        check_count = 0

        def condition():
            nonlocal check_count
            check_count += 1
            return check_count >= 3

        # Use the proper Cancelable API
        from hother.cancelable import Cancelable

        cancelable = Cancelable.with_condition(condition, check_interval=0.05, condition_name="test_condition")

        # Should cancel after 3 checks
        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.1 <= duration <= 0.2  # ~3 checks at 0.05s intervals
        assert check_count >= 3

        # Check that the cancellation reason is correct
        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_async_condition(self):
        """Test async condition function."""
        check_count = 0

        async def async_condition():
            nonlocal check_count
            check_count += 1
            await anyio.sleep(0.01)  # Simulate async work
            return check_count >= 2

        from hother.cancelable import Cancelable

        cancelable = Cancelable.with_condition(async_condition, check_interval=0.1)

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(1.0)

        assert check_count >= 2
        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_condition_error_handling(self):
        """Test condition error handling."""
        call_count = 0

        def faulty_condition():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Condition error")
            return call_count >= 4

        from hother.cancelable import Cancelable

        cancelable = Cancelable.with_condition(faulty_condition, check_interval=0.05)

        # Should continue checking despite error
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancelable:
                await anyio.sleep(0.5)  # Wait long enough for 4+ checks

        assert call_count >= 4
        assert cancelable.context.cancel_reason == CancelationReason.CONDITION

    @pytest.mark.anyio
    async def test_condition_validation(self):
        """Test condition source validation."""
        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=0)

        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=-1)


class TestResourceConditionSource:
    """Test ResourceConditionSource functionality."""

    def test_resource_condition_creation(self):
        """Test creating resource condition source."""
        source = ResourceConditionSource(memory_threshold=80.0, cpu_threshold=90.0, disk_threshold=95.0, check_interval=1.0)

        assert source.memory_threshold == 80.0
        assert source.cpu_threshold == 90.0
        assert source.disk_threshold == 95.0
        assert source.check_interval == 1.0
        assert "resource_check" in source.condition_name

    @pytest.mark.anyio
    async def test_resource_check_no_psutil(self, monkeypatch):
        """Test resource check when psutil is not available."""
        # Mock import error
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        source = ResourceConditionSource(memory_threshold=80.0)
        result = await source._check_resources()

        assert result is False  # Should return False when psutil unavailable
