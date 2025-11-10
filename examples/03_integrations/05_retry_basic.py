"""
Basic retry pattern with cancelable.

This example demonstrates simple retry logic without external dependencies,
using Cancelable.wrap() for automatic cancelation checking.
"""

import anyio

from hother.cancelable import Cancelable

# Simulate an operation that fails sometimes
attempt_count = 0


async def unreliable_operation(value: int) -> int:
    """
    Simulate an operation that fails on first two attempts.

    Args:
        value: Value to process

    Returns:
        Processed value (doubled)

    Raises:
        ValueError: On first two attempts
    """
    global attempt_count
    attempt_count += 1

    print(f"  🔄 Attempt #{attempt_count}: processing value {value}")

    if attempt_count < 3:
        print(f"  ❌ Attempt #{attempt_count} failed!")
        await anyio.sleep(0.1)  # Simulate some work
        raise ValueError(f"Attempt {attempt_count} failed")

    print(f"  ✅ Attempt #{attempt_count} succeeded!")
    return value * 2


async def retry_with_linear_backoff():
    """Example 1: Simple retry with linear backoff."""
    print("\n" + "=" * 60)
    print("Example 1: Retry with Linear Backoff")
    print("=" * 60)

    global attempt_count
    attempt_count = 0

    async with Cancelable.with_timeout(10, name="retry_linear") as cancel:
        # Wrap the operation for automatic cancelation checking
        wrapped_op = cancel.wrap(unreliable_operation)

        last_error = None
        max_retries = 5

        for attempt in range(max_retries):
            try:
                # Report progress
                await cancel.report_progress(
                    f"Starting attempt {attempt + 1}/{max_retries}",
                    {"attempt": attempt + 1, "max_retries": max_retries},
                )

                # Try to execute
                result = await wrapped_op(42)

                # Success!
                print(f"\n✅ Operation succeeded with result: {result}")
                return result

            except ValueError as e:
                last_error = e
                print(f"  ⚠️  Retry {attempt + 1}/{max_retries} failed: {e}")

                # Don't sleep on last attempt
                if attempt < max_retries - 1:
                    delay = 1.0  # Linear backoff: always 1 second
                    print(f"  ⏳ Waiting {delay}s before retry...")
                    await anyio.sleep(delay)

        # All retries exhausted
        print(f"\n❌ All {max_retries} retry attempts exhausted!")
        raise last_error


async def retry_with_exponential_backoff():
    """Example 2: Retry with exponential backoff."""
    print("\n" + "=" * 60)
    print("Example 2: Retry with Exponential Backoff")
    print("=" * 60)

    global attempt_count
    attempt_count = 0

    async with Cancelable.with_timeout(10, name="retry_exponential") as cancel:
        wrapped_op = cancel.wrap(unreliable_operation)

        last_error = None
        max_retries = 5

        for attempt in range(max_retries):
            try:
                await cancel.report_progress(
                    f"Starting attempt {attempt + 1}/{max_retries}",
                    {"attempt": attempt + 1, "max_retries": max_retries},
                )

                result = await wrapped_op(100)
                print(f"\n✅ Operation succeeded with result: {result}")
                return result

            except ValueError as e:
                last_error = e
                print(f"  ⚠️  Retry {attempt + 1}/{max_retries} failed: {e}")

                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                    delay = 2**attempt
                    print(f"  ⏳ Waiting {delay}s before retry (exponential backoff)...")
                    await anyio.sleep(delay)

        print(f"\n❌ All {max_retries} retry attempts exhausted!")
        raise last_error


async def retry_with_manual_cancelation():
    """Example 3: Retry with manual cancelation."""
    print("\n" + "=" * 60)
    print("Example 3: Retry with Manual Cancelation")
    print("=" * 60)

    from hother.cancelable import CancelationToken

    global attempt_count
    attempt_count = 0

    token = CancelationToken()

    async def worker():
        """Worker that retries with cancelation support."""
        async with Cancelable.with_token(token, name="retry_manual") as cancel:
            wrapped_op = cancel.wrap(unreliable_operation)

            for attempt in range(10):  # Many retries
                try:
                    await cancel.report_progress(f"Worker attempt {attempt + 1}", {"attempt": attempt + 1})

                    # This will check cancelation before executing
                    result = await wrapped_op(200)
                    print(f"\n✅ Operation succeeded with result: {result}")
                    return result

                except ValueError as e:
                    print(f"  ⚠️  Retry {attempt + 1} failed: {e}")
                    await anyio.sleep(1)

    async def canceller():
        """Cancel after 2 seconds."""
        await anyio.sleep(2)
        print("\n🛑 Manual cancelation triggered!")
        from hother.cancelable.core.models import CancelationReason

        await token.cancel(CancelationReason.MANUAL, "Manual cancelation after 2 seconds")

    # Run both tasks
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker)
        tg.start_soon(canceller)


async def retry_with_jitter():
    """Example 4: Retry with jittered exponential backoff."""
    print("\n" + "=" * 60)
    print("Example 4: Retry with Jittered Exponential Backoff")
    print("=" * 60)

    import random

    global attempt_count
    attempt_count = 0

    async with Cancelable.with_timeout(10, name="retry_jitter") as cancel:
        wrapped_op = cancel.wrap(unreliable_operation)

        last_error = None
        max_retries = 5

        for attempt in range(max_retries):
            try:
                await cancel.report_progress(
                    f"Starting attempt {attempt + 1}/{max_retries}",
                    {"attempt": attempt + 1, "max_retries": max_retries},
                )

                result = await wrapped_op(300)
                print(f"\n✅ Operation succeeded with result: {result}")
                return result

            except ValueError as e:
                last_error = e
                print(f"  ⚠️  Retry {attempt + 1}/{max_retries} failed: {e}")

                if attempt < max_retries - 1:
                    # Exponential backoff with jitter: base_delay * (1 + random factor)
                    base_delay = 2**attempt
                    jitter = random.uniform(0, 1)
                    delay = base_delay * (1 + jitter * 0.1)  # Add up to 10% jitter
                    print(f"  ⏳ Waiting {delay:.2f}s before retry (exponential + jitter)...")
                    await anyio.sleep(delay)

        print(f"\n❌ All {max_retries} retry attempts exhausted!")
        raise last_error


async def main():
    """Run all examples."""
    print("\n🎯 Basic Retry Patterns with Cancelable")
    print("=========================================")

    try:
        # Example 1: Linear backoff
        await retry_with_linear_backoff()
    except ValueError as e:
        print(f"Final error: {e}")

    try:
        # Example 2: Exponential backoff
        await retry_with_exponential_backoff()
    except ValueError as e:
        print(f"Final error: {e}")

    try:
        # Example 3: Manual cancelation
        await retry_with_manual_cancelation()
    except anyio.get_cancelled_exc_class():
        print("✅ Operation was cancelled as expected")

    try:
        # Example 4: Jitter
        await retry_with_jitter()
    except ValueError as e:
        print(f"Final error: {e}")

    print("\n" + "=" * 60)
    print("✅ All examples completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    anyio.run(main)
