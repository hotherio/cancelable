"""
Tests for cancellation sources.
"""

import signal
from datetime import timedelta

import anyio
import pytest

from hother.cancelable.core.models import CancellationReason
from hother.cancelable.sources.composite import AnyOfSource, CompositeSource
from hother.cancelable.sources.condition import ConditionSource
from hother.cancelable.sources.signal import SignalSource
from hother.cancelable.sources.timeout import TimeoutSource


class TestTimeoutSource:
    """Test TimeoutSource functionality."""

    @pytest.mark.anyio
    async def test_timeout_basic(self):
        """Test basic timeout functionality."""
        source = TimeoutSource(0.1)
        assert source.timeout == 0.1
        assert source.reason == CancellationReason.TIMEOUT
        assert not source.triggered

        # Test with actual cancellable
        from hother.cancelable import Cancellable

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancellable.with_timeout(0.1):
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.08 <= duration <= 0.12

    @pytest.mark.anyio
    async def test_timeout_with_timedelta(self):
        """Test timeout with timedelta."""
        source = TimeoutSource(timedelta(milliseconds=100))
        assert source.timeout == 0.1

    @pytest.mark.anyio
    async def test_timeout_validation(self):
        """Test timeout validation."""
        with pytest.raises(ValueError):
            TimeoutSource(0)  # Zero timeout

        with pytest.raises(ValueError):
            TimeoutSource(-1)  # Negative timeout

    @pytest.mark.anyio
    async def test_timeout_with_scope(self):
        """Test timeout with manual scope handling."""
        source = TimeoutSource(0.1)

        # Create a cancellable that uses this source
        from hother.cancelable import Cancellable

        cancellable = Cancellable()
        cancellable._sources.append(source)

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancellable:
                await anyio.sleep(1.0)

        assert cancellable.context.cancel_reason == CancellationReason.TIMEOUT


class TestSignalSource:
    """Test SignalSource functionality."""

    @pytest.mark.anyio
    async def test_signal_registration(self):
        """Test signal handler registration."""
        source = SignalSource(signal.SIGUSR1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)

        # Check handler is registered
        assert signal.SIGUSR1 in SignalSource._handlers

        await source.stop_monitoring()

    @pytest.mark.anyio
    async def test_multiple_signal_sources(self):
        """Test multiple sources for same signal."""
        source1 = SignalSource(signal.SIGUSR1)
        source2 = SignalSource(signal.SIGUSR1)

        scope1 = anyio.CancelScope()
        scope2 = anyio.CancelScope()

        await source1.start_monitoring(scope1)
        await source2.start_monitoring(scope2)

        # Both should be registered
        assert len(SignalSource._handlers[signal.SIGUSR1]) >= 2

        await source1.stop_monitoring()
        await source2.stop_monitoring()

    @pytest.mark.anyio
    async def test_signal_cleanup(self):
        """Test signal handler cleanup."""
        source = SignalSource(signal.SIGUSR1)
        scope = anyio.CancelScope()

        await source.start_monitoring(scope)
        await source.stop_monitoring()

        # Handler should be cleaned up if no other sources
        if signal.SIGUSR1 in SignalSource._handlers:
            assert len(SignalSource._handlers[signal.SIGUSR1]) == 0


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

        # Test with actual cancellable
        from hother.cancelable import Cancellable

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancellable.with_condition(condition, check_interval=0.05, condition_name="test_condition"):
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.1 <= duration <= 0.2  # ~3 checks at 0.05s intervals
        assert check_count >= 3

    @pytest.mark.anyio
    async def test_async_condition(self):
        """Test async condition function."""
        check_count = 0

        async def async_condition():
            nonlocal check_count
            check_count += 1
            await anyio.sleep(0.01)  # Simulate async work
            return check_count >= 2

        # Test with actual cancellable
        from hother.cancelable import Cancellable

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancellable.with_condition(async_condition, check_interval=0.1):
                await anyio.sleep(1.0)

        assert check_count >= 2

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

        # Test with actual cancellable
        from hother.cancelable import Cancellable

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with Cancellable.with_condition(faulty_condition, check_interval=0.05):
                await anyio.sleep(1.0)

        # Should continue checking despite error
        assert call_count >= 4

    @pytest.mark.anyio
    async def test_condition_validation(self):
        """Test condition source validation."""
        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=0)

        with pytest.raises(ValueError):
            ConditionSource(lambda: True, check_interval=-1)

    @pytest.mark.anyio
    async def test_condition_source_properties(self):
        """Test ConditionSource properties."""

        def test_condition():
            return False

        source = ConditionSource(test_condition, check_interval=0.1, condition_name="my_condition")

        assert source.condition == test_condition
        assert source.check_interval == 0.1
        assert source.condition_name == "my_condition"
        assert source.reason == CancellationReason.CONDITION
        assert not source.triggered


class TestCompositeSource:
    """Test CompositeSource functionality."""

    @pytest.mark.anyio
    async def test_composite_any_of(self):
        """Test composite source with ANY logic."""
        from hother.cancelable import Cancellable

        # Create two cancellables with different timeouts
        cancel1 = Cancellable.with_timeout(0.2)
        cancel2 = Cancellable.with_timeout(0.1)  # This will trigger first

        # Combine them
        combined = cancel1.combine(cancel2)

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with combined:
                await anyio.sleep(1.0)

        duration = anyio.current_time() - start
        assert 0.08 <= duration <= 0.12  # Triggered by shorter timeout

    @pytest.mark.anyio
    async def test_composite_empty_sources(self):
        """Test composite with no sources."""
        with pytest.raises(ValueError):
            CompositeSource([])

    @pytest.mark.anyio
    async def test_any_of_alias(self):
        """Test AnyOfSource alias."""
        source = AnyOfSource([TimeoutSource(0.1)])
        assert isinstance(source, CompositeSource)

    @pytest.mark.anyio
    async def test_composite_multiple_types(self):
        """Test combining different source types."""
        from hother.cancelable import Cancellable

        check_count = 0

        def condition():
            nonlocal check_count
            check_count += 1
            return check_count >= 3

        # Create cancellables with different sources
        timeout_cancel = Cancellable.with_timeout(0.5)
        condition_cancel = Cancellable.with_condition(condition, check_interval=0.05)

        # Combine them
        combined = timeout_cancel.combine(condition_cancel)

        start = anyio.current_time()
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with combined:
                await anyio.sleep(1.0)

        # Should be cancelled by condition (faster)
        duration = anyio.current_time() - start
        assert duration < 0.3  # Condition should trigger before timeout
        assert check_count >= 3


class TestAllOfSource:
    """Test AllOfSource functionality."""

    @pytest.mark.anyio
    async def test_all_of_basic(self):
        """Test ALL logic - all sources must trigger."""
        # For ALL logic, we need to implement it differently
        # since our current combine() implements ANY logic
        # Let's test the concept with manual coordination

        from hother.cancelable import Cancellable, CancellationToken

        token1 = CancellationToken()
        token2 = CancellationToken()

        # Track which tokens have been cancelled
        cancelled_tokens = set()

        async def track_cancellation(token, name):
            await token.wait_for_cancel()
            cancelled_tokens.add(name)

            # If both are cancelled, cancel the main operation
            if len(cancelled_tokens) == 2:
                await main_token.cancel()

        main_token = CancellationToken()

        async with anyio.create_task_group() as tg:
            # Monitor both tokens
            tg.start_soon(track_cancellation, token1, "token1")
            tg.start_soon(track_cancellation, token2, "token2")

            # Cancel tokens at different times
            async def cancel_tokens():
                await anyio.sleep(0.1)
                await token1.cancel()
                await anyio.sleep(0.1)
                await token2.cancel()

            tg.start_soon(cancel_tokens)

            # Main operation
            start = anyio.current_time()
            with pytest.raises(anyio.get_cancelled_exc_class()):
                async with Cancellable.with_token(main_token):
                    await anyio.sleep(1.0)

            duration = anyio.current_time() - start
            assert 0.2 <= duration <= 0.25  # After both tokens cancelled

    @pytest.mark.anyio
    async def test_all_of_partial_trigger(self):
        """Test ALL logic when only some sources trigger."""
        # This is more of a conceptual test since we don't have AllOfSource implemented
        # in the main codebase yet

        from hother.cancelable import Cancellable, CancellationToken

        token1 = CancellationToken()
        token2 = CancellationToken()

        # Only cancel one token
        async def cancel_one():
            await anyio.sleep(0.1)
            await token1.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_one)

            # Create cancellables that would need both tokens
            # Since we don't have ALL logic, just verify individual behavior
            async with Cancellable.with_token(token2):
                await anyio.sleep(0.2)  # Should complete without cancellation

            # Token2 was never cancelled
            assert not token2.is_cancelled
            assert token1.is_cancelled
