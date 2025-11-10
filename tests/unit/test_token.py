"""
Tests for cancelation token.
"""

from datetime import datetime

import anyio
import pytest

from hother.cancelable import CancelationReason, CancelationToken, ManualCancelation
from hother.cancelable.core.token import LinkedCancelationToken


class TestCancelationToken:
    """Test CancelationToken functionality."""

    @pytest.mark.anyio
    async def test_initial_state(self):
        """Test token initial state."""
        token = CancelationToken()

        assert token.id is not None
        assert not token.is_cancelled
        assert token.reason is None
        assert token.message is None
        assert token.cancelled_at is None

    @pytest.mark.anyio
    async def test_cancel(self):
        """Test token cancelation."""
        token = CancelationToken()

        # Cancel token
        result = await token.cancel(reason=CancelationReason.MANUAL, message="Test cancelation")

        assert result is True
        assert token.is_cancelled
        assert token.reason == CancelationReason.MANUAL
        assert token.message == "Test cancelation"
        assert token.cancelled_at is not None
        assert isinstance(token.cancelled_at, datetime)

    @pytest.mark.anyio
    async def test_cancel_idempotent(self):
        """Test that cancel is idempotent."""
        token = CancelationToken()

        # First cancel
        result1 = await token.cancel(CancelationReason.MANUAL, "First")
        assert result1 is True

        # Second cancel should return False
        result2 = await token.cancel(CancelationReason.TIMEOUT, "Second")
        assert result2 is False

        # Original cancelation info preserved
        assert token.reason == CancelationReason.MANUAL
        assert token.message == "First"

    @pytest.mark.anyio
    async def test_wait_for_cancel(self):
        """Test waiting for cancelation."""
        token = CancelationToken()

        async def cancel_after_delay():
            await anyio.sleep(0.1)
            await token.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_after_delay)

            start = anyio.current_time()
            await token.wait_for_cancel()
            duration = anyio.current_time() - start

            assert 0.08 <= duration <= 0.12  # Allow some variance
            assert token.is_cancelled

    @pytest.mark.anyio
    async def test_check_sync(self):
        """Test synchronous cancelation check."""
        token = CancelationToken()

        # Should not raise when not cancelled
        token.check()

        # Cancel token
        await token.cancel()

        # Should raise when cancelled
        with pytest.raises(ManualCancelation) as exc_info:
            token.check()

        assert "Operation cancelled via token" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_check_async(self):
        """Test asynchronous cancelation check."""
        token = CancelationToken()

        # Should not raise when not cancelled
        await token.check_async()

        # Cancel token
        await token.cancel(message="Custom message")

        # Should raise when cancelled
        with pytest.raises(anyio.get_cancelled_exc_class()) as exc_info:
            await token.check_async()

        assert "Custom message" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_is_cancelation_requested(self):
        """Test non-throwing cancelation check."""
        token = CancelationToken()

        assert not token.is_cancelation_requested()

        await token.cancel()

        assert token.is_cancelation_requested()

    @pytest.mark.anyio
    async def test_callbacks(self):
        """Test cancelation callbacks."""
        token = CancelationToken()
        callback_called = False
        callback_token = None

        async def callback(t):
            nonlocal callback_called, callback_token
            callback_called = True
            callback_token = t

        # Register callback
        await token.register_callback(callback)

        # Cancel token
        await token.cancel()

        # Callback should be called
        assert callback_called
        assert callback_token is token

    @pytest.mark.anyio
    async def test_callback_already_cancelled(self):
        """Test callback registration on already cancelled token."""
        token = CancelationToken()
        await token.cancel()

        callback_called = False

        async def callback(t):
            nonlocal callback_called
            callback_called = True

        # Register callback on cancelled token
        await token.register_callback(callback)

        # Should be called immediately
        assert callback_called

    @pytest.mark.anyio
    async def test_callback_error_handling(self):
        """Test that callback errors don't break cancelation."""
        token = CancelationToken()

        async def bad_callback(t):
            raise ValueError("Callback error")

        async def good_callback(t):
            nonlocal good_called
            good_called = True

        good_called = False

        # Register both callbacks
        await token.register_callback(bad_callback)
        await token.register_callback(good_callback)

        # Cancel should work despite bad callback
        await token.cancel()

        assert token.is_cancelled
        assert good_called

    @pytest.mark.anyio
    async def test_string_representation(self):
        """Test token string representations."""
        token = CancelationToken()

        # Active token
        str_repr = str(token)
        assert "active" in str_repr
        assert token.id[:8] in str_repr

        # Cancelled token
        await token.cancel(CancelationReason.TIMEOUT, "Timed out")

        str_repr = str(token)
        assert "cancelled" in str_repr
        assert "timeout" in str_repr

        # Repr
        repr_str = repr(token)
        assert token.id in repr_str
        assert "is_cancelled=True" in repr_str
        assert "reason=CancelationReason.TIMEOUT" in repr_str

    def test_token_equality(self):
        """Test token equality based on ID."""
        token1 = CancelationToken()
        token2 = CancelationToken()

        # Tokens with different IDs should not be equal
        assert token1 != token2

        # Token should equal itself
        assert token1 == token1

        assert token1 != "not a token"
        assert token1 != 123
        assert token1 != None

    def test_token_hashable(self):
        """Test that tokens are hashable and can be used in sets/dicts."""
        token1 = CancelationToken()
        token2 = CancelationToken()

        token_dict = {token1: "value1", token2: "value2"}
        assert token_dict[token1] == "value1"
        assert token_dict[token2] == "value2"

        # Should be able to use in set
        token_set = {token1, token2}
        assert len(token_set) == 2
        assert token1 in token_set
        assert token2 in token_set

    @pytest.mark.anyio
    async def test_callback_exception_on_already_cancelled(self):
        """Test callback exception when registering on already-cancelled token."""
        token = CancelationToken()

        # Cancel the token first
        await token.cancel()

        # Register a callback that raises an exception
        callback_called = [False]
        exception_raised = [False]

        async def faulty_callback(t):
            callback_called[0] = True
            exception_raised[0] = True
            raise RuntimeError("Callback error")

        # Register callback on already-cancelled token
        # Should call immediately and handle exception gracefully
        await token.register_callback(faulty_callback)

        # Give async callback time to execute
        await anyio.sleep(0.1)

        # Callback should have been called despite exception
        assert callback_called[0]
        assert exception_raised[0]
        # Token should still be cancelled
        assert token.is_cancelation_requested


class TestLinkedCancelationToken:
    """Test LinkedCancelationToken functionality."""

    @pytest.mark.anyio
    async def test_linked_cancelation(self):
        """Test that linked tokens cancel together."""
        token1 = LinkedCancelationToken()
        token2 = LinkedCancelationToken()

        # Link token2 to token1
        await token2.link(token1)

        # Cancel token1
        await token1.cancel(CancelationReason.MANUAL, "Primary cancelled")

        # Wait a bit for propagation
        await anyio.sleep(0.01)

        # Token2 should also be cancelled
        assert token2.is_cancelled
        assert token2.reason == CancelationReason.PARENT
        assert "Linked token" in token2.message

    @pytest.mark.anyio
    async def test_multiple_links(self):
        """Test token linked to multiple sources."""
        source1 = CancelationToken()
        source2 = CancelationToken()
        linked = LinkedCancelationToken()

        # Link to both sources
        await linked.link(source1)
        await linked.link(source2)

        # Cancel source2
        await source2.cancel()
        await anyio.sleep(0.01)

        # Linked should be cancelled
        assert linked.is_cancelled
        assert linked.reason == CancelationReason.PARENT

    @pytest.mark.anyio
    async def test_circular_linking_prevention(self):
        """Test that circular linking doesn't cause issues."""
        token1 = LinkedCancelationToken()
        token2 = LinkedCancelationToken()

        # Create circular link
        await token1.link(token2)
        await token2.link(token1)

        # Cancel one token
        await token1.cancel()
        await anyio.sleep(0.01)

        # Both should be cancelled without infinite loop
        assert token1.is_cancelled
        assert token2.is_cancelled
