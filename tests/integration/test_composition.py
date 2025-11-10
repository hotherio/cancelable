"""Integration tests for composing cancelation sources."""

import anyio
import pytest

from hother.cancelable import Cancelable, CancelationReason, CancelationToken


class TestCancelableComposition:
    """Test composing multiple cancelation sources."""

    @pytest.mark.anyio
    async def test_combine_timeout_and_token(self):
        """Test combining timeout and token cancelation."""
        token = CancelationToken()

        combined = Cancelable.with_timeout(1.0).combine(Cancelable.with_token(token))

        # Cancel via token (faster than timeout)
        async def cancel_soon():
            await anyio.sleep(0.1)
            await token.cancel(CancelationReason.MANUAL)

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_soon)

            with pytest.raises(anyio.get_cancelled_exc_class()):
                async with combined:
                    await anyio.sleep(2.0)

        # Should be cancelled by token, not timeout
        assert combined._token.reason == CancelationReason.MANUAL

    @pytest.mark.anyio
    async def test_combine_multiple_sources(self):
        """Test combining multiple cancelation sources."""
        token1 = CancelationToken()
        token2 = CancelationToken()

        combined = Cancelable.with_timeout(5.0).combine(Cancelable.with_token(token1)).combine(Cancelable.with_token(token2))

        # Cancel second token
        async def cancel_token2():
            await anyio.sleep(0.1)
            await token2.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_token2)

            with pytest.raises(anyio.get_cancelled_exc_class()):
                async with combined:
                    await anyio.sleep(1.0)

        assert combined.is_cancelled

    @pytest.mark.anyio
    async def test_nested_composition(self):
        """Test nested composition of cancelables."""
        token = CancelationToken()

        # Create nested composition
        inner = Cancelable.with_timeout(5.0).combine(Cancelable.with_token(token))
        outer = Cancelable.with_timeout(10.0).combine(inner)

        # Cancel via token
        async def cancel_token():
            await anyio.sleep(0.1)
            await token.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_token)

            with pytest.raises(anyio.get_cancelled_exc_class()):
                async with outer:
                    await anyio.sleep(1.0)

    @pytest.mark.anyio
    async def test_condition_with_timeout(self):
        """Test combining condition and timeout."""
        counter = 0

        def check_condition():
            nonlocal counter
            counter += 1
            return counter >= 10

        combined = Cancelable.with_timeout(0.2).combine(Cancelable.with_condition(check_condition, check_interval=0.05))

        # Timeout should trigger first (10 checks * 0.05s = 0.5s > 0.2s timeout)
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with combined:
                await anyio.sleep(1.0)

        assert counter < 10  # Condition shouldn't have been met
