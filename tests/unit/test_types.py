"""Tests for type utilities in hother.cancelable.types."""

import pytest

from hother.cancelable import Cancelable
from hother.cancelable.types import ensure_cancelable


class TestEnsureCancelable:
    """Test ensure_cancelable type guard utility."""

    @pytest.mark.anyio
    async def test_ensure_cancelable_with_valid_instance(self):
        """Test ensure_cancelable returns the instance when not None."""
        async with Cancelable(name="test") as cancel:
            # Should return the same instance
            result = ensure_cancelable(cancel)
            assert result is cancel
            assert result.context.name == "test"

    def test_ensure_cancelable_with_none_raises_error(self):
        """Test ensure_cancelable raises RuntimeError when passed None."""
        with pytest.raises(
            RuntimeError,
            match="Cancelable parameter is None.*@cancelable decorator",
        ):
            ensure_cancelable(None)

    def test_ensure_cancelable_error_message_content(self):
        """Test the error message provides helpful guidance."""
        try:
            ensure_cancelable(None)
            pytest.fail("Expected RuntimeError to be raised")
        except RuntimeError as e:
            error_msg = str(e)
            # Verify the error message contains helpful information
            assert "Cancelable parameter is None" in error_msg
            assert "@cancelable decorator" in error_msg
            assert "call the function directly" in error_msg
