"""
Tenacity integration with cancelable.

This example demonstrates using the Tenacity retry library with Cancelable
for advanced retry patterns with cancelation support.

Install tenacity: pip install tenacity
"""

import anyio

# Check if tenacity is available
try:
    from tenacity import (
        AsyncRetrying,
        RetryError,
        retry_if_exception_type,
        stop_after_attempt,
        stop_after_delay,
        wait_exponential,
        wait_fixed,
    )

    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    print("⚠️  Tenacity not installed. Install with: pip install tenacity")

from hother.cancelable import Cancelable, CancelationToken

# Simulate operations that fail
attempt_count = 0


class TransientError(Exception):
    """Simulated transient error."""


async def unreliable_operation(value: int) -> int:
    """
    Simulate an operation that fails on first two attempts.

    Args:
        value: Value to process

    Returns:
        Processed value (doubled)

    Raises:
        TransientError: On first two attempts
    """
    global attempt_count
    attempt_count += 1

    print(f"  🔄 Attempt #{attempt_count}: processing value {value}")

    if attempt_count < 3:
        print(f"  ❌ Attempt #{attempt_count} failed!")
        await anyio.sleep(0.1)
        raise TransientError(f"Attempt {attempt_count} failed")

    print(f"  ✅ Attempt #{attempt_count} succeeded!")
    return value * 2


async def example_wrap_with_tenacity():
    """Example 1: Using wrap() with Tenacity (recommended pattern)."""
    if not TENACITY_AVAILABLE:
        return None

    print("\n" + "=" * 70)
    print("Example 1: wrap() with Tenacity (Recommended)")
    print("=" * 70)
    print("Pattern: Pre-wrap operation, then use in Tenacity retry loop")

    global attempt_count
    attempt_count = 0

    async with Cancelable.with_timeout(30, name="tenacity_wrap") as cancel:
        # Pre-wrap the operation
        wrapped_op = cancel.wrap(unreliable_operation)

        # Use Tenacity for retry logic
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=10)
        ):
            with attempt:
                # Report progress
                attempt_num = attempt.retry_state.attempt_number
                await cancel.report_progress(f"Tenacity attempt {attempt_num}", {"attempt": attempt_num})

                # Execute wrapped operation
                result = await wrapped_op(42)
                print(f"\n✅ Success! Result: {result}")
                return result


async def example_wrapping_with_tenacity():
    """Example 2: Using wrapping() context manager with Tenacity."""
    if not TENACITY_AVAILABLE:
        return None

    print("\n" + "=" * 70)
    print("Example 2: wrapping() context manager with Tenacity")
    print("=" * 70)
    print("Pattern: Use async context manager for scoped wrapping")

    global attempt_count
    attempt_count = 0

    async with Cancelable.with_timeout(30, name="tenacity_wrapping") as cancel:
        async for attempt in AsyncRetrying(stop=stop_after_attempt(5), wait=wait_fixed(1)):
            with attempt:  # Tenacity's sync context manager
                # Our async context manager
                async with cancel.wrapping() as wrap:
                    attempt_num = attempt.retry_state.attempt_number
                    await cancel.report_progress(f"Attempt {attempt_num} with wrapping()", {"attempt": attempt_num})

                    # Wrap and execute in one call
                    result = await wrap(unreliable_operation, 100)
                    print(f"\n✅ Success! Result: {result}")
                    return result


async def example_conditional_retry():
    """Example 3: Retry only specific exceptions."""
    if not TENACITY_AVAILABLE:
        return None

    print("\n" + "=" * 70)
    print("Example 3: Conditional Retry (Only TransientError)")
    print("=" * 70)

    global attempt_count
    attempt_count = 0

    class PermanentError(Exception):
        """Error that should not be retried."""

    async def mixed_errors(attempt_num: int) -> str:
        """Operation that raises different types of errors."""
        print(f"  🔄 Attempt #{attempt_num}")

        if attempt_num == 1:
            print("  ❌ Transient error (will retry)")
            raise TransientError("Transient failure")
        if attempt_num == 2:
            print("  ❌ Permanent error (will not retry)")
            raise PermanentError("Permanent failure - don't retry!")

        print("  ✅ Success!")
        return "completed"

    async with Cancelable.with_timeout(30, name="conditional_retry") as cancel:
        # Only retry TransientError
        wrapped_op = cancel.wrap(mixed_errors)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(5), wait=wait_fixed(1), retry=retry_if_exception_type(TransientError)
            ):
                with attempt:
                    result = await wrapped_op(attempt.retry_state.attempt_number)
                    print(f"\n✅ Result: {result}")
                    return result

        except PermanentError as e:
            print(f"\n🛑 Permanent error (not retried): {e}")


async def example_stop_conditions():
    """Example 4: Multiple stop conditions."""
    if not TENACITY_AVAILABLE:
        return None

    print("\n" + "=" * 70)
    print("Example 4: Multiple Stop Conditions")
    print("=" * 70)
    print("Stops after: 10 attempts OR 15 seconds elapsed")

    global attempt_count
    attempt_count = 0

    async with Cancelable.with_timeout(20, name="stop_conditions") as cancel:
        wrapped_op = cancel.wrap(unreliable_operation)

        try:
            async for attempt in AsyncRetrying(
                stop=(
                    stop_after_attempt(10)  # Max 10 attempts OR
                    | stop_after_delay(15)  # 15 seconds elapsed
                ),
                wait=wait_fixed(2),
            ):
                with attempt:
                    attempt_num = attempt.retry_state.attempt_number
                    elapsed = attempt.retry_state.seconds_since_start or 0
                    await cancel.report_progress(
                        f"Attempt {attempt_num} (elapsed: {elapsed:.1f}s)", {"attempt": attempt_num, "elapsed": elapsed}
                    )

                    result = await wrapped_op(200)
                    print(f"\n✅ Result: {result}")
                    return result

        except RetryError as e:
            print(f"\n❌ Retry exhausted: {e}")


async def example_manual_cancelation():
    """Example 5: Manual cancelation during Tenacity retry."""
    if not TENACITY_AVAILABLE:
        return

    print("\n" + "=" * 70)
    print("Example 5: Manual Cancelation During Retry")
    print("=" * 70)

    global attempt_count
    attempt_count = 0

    token = CancelationToken()

    async def worker():
        """Worker with Tenacity retry."""
        async with Cancelable.with_token(token, name="manual_cancel_retry") as cancel:
            wrapped_op = cancel.wrap(unreliable_operation)

            async for attempt in AsyncRetrying(stop=stop_after_attempt(20), wait=wait_fixed(1)):
                with attempt:
                    attempt_num = attempt.retry_state.attempt_number
                    print(f"  🔄 Worker attempt #{attempt_num}")

                    result = await wrapped_op(300)
                    print(f"\n✅ Result: {result}")
                    return result

    async def canceller():
        """Cancel after 2.5 seconds."""
        await anyio.sleep(2.5)
        print("\n🛑 Cancelling from another task...")
        from hother.cancelable.core.models import CancelationReason

        await token.cancel(CancelationReason.MANUAL, "Manual cancelation triggered")

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(worker)
            tg.start_soon(canceller)
    except anyio.get_cancelled_exc_class():
        print("✅ Worker was cancelled successfully")


async def example_progress_tracking():
    """Example 6: Progress tracking with Tenacity."""
    if not TENACITY_AVAILABLE:
        return None

    print("\n" + "=" * 70)
    print("Example 6: Progress Tracking")
    print("=" * 70)

    global attempt_count
    attempt_count = 0

    # Track progress
    progress_messages = []

    async with Cancelable.with_timeout(30, name="progress_tracking") as cancel:
        # Register progress callback
        cancel.on_progress(lambda op_id, msg, meta: progress_messages.append((msg, meta)))

        wrapped_op = cancel.wrap(unreliable_operation)

        async for attempt in AsyncRetrying(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1)):
            with attempt:
                attempt_num = attempt.retry_state.attempt_number
                await cancel.report_progress(
                    f"📊 Attempt {attempt_num}", {"attempt": attempt_num, "stage": "before_execution"}
                )

                result = await wrapped_op(400)

                await cancel.report_progress(
                    f"✅ Attempt {attempt_num} succeeded",
                    {"attempt": attempt_num, "stage": "after_execution", "result": result},
                )

                print(f"\n📊 Progress History ({len(progress_messages)} messages):")
                for msg, meta in progress_messages:
                    print(f"  - {msg} | {meta}")

                return result


async def main():
    """Run all examples."""
    if not TENACITY_AVAILABLE:
        print("\n❌ Tenacity is not installed.")
        print("Install it with: pip install tenacity")
        print("Or: uv add tenacity")
        return

    print("\n🎯 Tenacity Integration with Cancelable")
    print("=========================================")

    # Example 1: wrap() with Tenacity (recommended)
    try:
        await example_wrap_with_tenacity()
    except Exception as e:
        print(f"Error: {e}")

    # Example 2: wrapping() context manager
    try:
        await example_wrapping_with_tenacity()
    except Exception as e:
        print(f"Error: {e}")

    # Example 3: Conditional retry
    try:
        await example_conditional_retry()
    except Exception as e:
        print(f"Error: {e}")

    # Example 4: Stop conditions
    try:
        await example_stop_conditions()
    except Exception as e:
        print(f"Error: {e}")

    # Example 5: Manual cancelation
    try:
        await example_manual_cancelation()
    except Exception as e:
        print(f"Error: {e}")

    # Example 6: Progress tracking
    try:
        await example_progress_tracking()
    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "=" * 70)
    print("✅ All examples completed!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    anyio.run(main)
