#!/usr/bin/env python3
"""
Basic usage examples for the async cancellation system.
"""

import signal

import anyio

from hother.cancelable import Cancellable, CancellationToken, OperationRegistry, cancellable, with_timeout
from hother.cancelable.utils.logging import configure_logging, get_logger

# Configure logging
configure_logging(log_level="INFO")
logger = get_logger(__name__)


async def example_timeout():
    """Example: Basic timeout cancellation."""
    print("\n=== Timeout Example ===")

    try:
        async with Cancellable.with_timeout(2.0, name="timeout_example") as cancel:
            cancel.on_progress(lambda op_id, msg, meta: print(f"  Progress: {msg}"))

            await cancel.report_progress("Starting operation")

            # This will timeout
            await anyio.sleep(5.0)

            await cancel.report_progress("This won't be reached")

    except anyio.get_cancelled_exc_class():
        print(f"Operation timed out after {cancel.context.duration}")
        print(f"Final status: {cancel.context.status.value}")


async def example_manual_cancellation():
    """Example: Manual cancellation with token."""
    print("\n=== Manual Cancellation Example ===")

    # Create a cancellation token
    token = CancellationToken()

    async def background_task():
        """Simulate a long-running task."""
        try:
            async with Cancellable.with_token(token, name="background_task") as cancel:
                cancel.on_progress(lambda op_id, msg, meta: print(f"  Progress: {msg}"))
                for i in range(10):
                    await cancel.report_progress(f"Step {i + 1}/10")
                    await anyio.sleep(0.5)
        except anyio.get_cancelled_exc_class():
            print("  Background task was cancelled!")

    # Run task and cancel after 2 seconds
    try:
        async with anyio.create_task_group() as tg:
            # Start background task
            tg.start_soon(background_task)

            # Cancel after 2 seconds
            await anyio.sleep(2.0)
            print("Cancelling task...")
            await token.cancel(message="User requested cancellation")
    except* anyio.get_cancelled_exc_class():
        # Handle the cancellation from task group
        print("  Task group cancelled due to operation cancellation")


async def example_stream_processing():
    """Example: Cancellable stream processing."""
    print("\n=== Stream Processing Example ===")

    async def number_generator():
        """Generate numbers slowly."""
        for i in range(100):
            await anyio.sleep(0.1)
            yield i

    # Process stream with timeout and progress reporting
    async with Cancellable.with_timeout(3.0, name="stream_processing") as cancel:
        cancel.on_progress(lambda op_id, msg, meta: print(f"  Progress: {msg}"))

        count = 0
        async for number in cancel.stream(number_generator(), report_interval=10):
            count += 1
            # Process number (just print it here)
            if number % 5 == 0:
                print(f"  Processed: {number}")

        print(f"  Total processed: {count}")


async def example_decorated_function():
    """Example: Using decorators."""
    print("\n=== Decorated Function Example ===")

    @cancellable(timeout=2.0, name="decorated_operation")
    async def slow_operation(duration: float, cancellable: Cancellable = None):
        """A slow operation with built-in cancellation."""
        await cancellable.report_progress("Starting slow operation")

        steps = int(duration * 10)
        for i in range(steps):
            await anyio.sleep(0.1)
            if i % 10 == 0:
                await cancellable.report_progress(f"Progress: {(i / steps) * 100:.0f}%")

        await cancellable.report_progress("Operation completed")
        return "Success"

    try:
        # This will complete
        result = await slow_operation(1.5)
        print(f"  Result: {result}")

        # This will timeout
        result = await slow_operation(3.0)
        print(f"  Result: {result}")

    except anyio.get_cancelled_exc_class():
        print("  Operation was cancelled!")


async def example_combined_cancellation():
    """Example: Multiple cancellation sources."""
    print("\n=== Combined Cancellation Example ===")

    # Create multiple cancellation sources
    token = CancellationToken()
    logger.info(f"Created manual token: {token.id}")

    # Create individual cancellables with logging
    timeout_cancellable = Cancellable.with_timeout(10.0)
    logger.info(f"Created timeout cancellable: {timeout_cancellable.context.id} with token {timeout_cancellable._token.id}")

    token_cancellable = Cancellable.with_token(token)
    logger.info(f"Created token cancellable: {token_cancellable.context.id} with token {token_cancellable._token.id}")

    signal_cancellable = Cancellable.with_signal(signal.SIGINT)
    logger.info(f"Created signal cancellable: {signal_cancellable.context.id} with token {signal_cancellable._token.id}")

    # Combine them step by step with logging
    logger.info("=== COMBINING STEP 1: timeout + token ===")
    first_combine = timeout_cancellable.combine(token_cancellable)
    logger.info(f"First combine result: {first_combine.context.id} with token {first_combine._token.id}")

    logger.info("=== COMBINING STEP 2: (timeout+token) + signal ===")
    final_cancellable = first_combine.combine(signal_cancellable)
    logger.info(f"Final combine result: {final_cancellable.context.id} with token {final_cancellable._token.id}")

    logger.info(f"Final combined cancellable: {final_cancellable.context.id}")
    logger.info(f"Final combined cancellable token: {final_cancellable._token.id}")

    final_cancellable.on_cancel(lambda ctx: print(f"  Cancelled: {ctx.cancel_reason.value if ctx.cancel_reason else 'unknown'} - {ctx.cancel_message or 'no message'}"))

    print("  Press Ctrl+C to cancel, or wait for timeout/manual cancel...")

    async with final_cancellable:
        # Simulate work
        for i in range(20):
            await anyio.sleep(0.5)
            print(f"  Working... {i + 1}/20")

            # Manual cancel after 3 seconds
            if i == 6:
                print("  Triggering manual cancellation...")
                logger.info(f"About to cancel token: {token.id}")
                await token.cancel(message="Demonstration cancel")
                logger.info("Token cancel call completed")


async def example_shielded_operations():
    """Example: Shielding critical operations."""
    print("\n=== Shielded Operations Example ===")

    async with Cancellable.with_timeout(2.0, name="parent_operation") as parent:
        print("  Starting parent operation...")
        await anyio.sleep(0.5)

        # Shield critical section
        print("  Entering shielded section...")
        async with parent.shield():
            print("  Critical operation started (won't be cancelled)")
            await anyio.sleep(3.0)  # This exceeds parent timeout but won't be cancelled
            print("  Critical operation completed")

        print("  Back to normal operation")
        await anyio.sleep(1.0)  # This will be cancelled


async def example_operation_registry():
    """Example: Using the operation registry."""
    print("\n=== Operation Registry Example ===")

    registry = OperationRegistry.get_instance()
    await registry.clear_all()

    print("  Demonstrating registry with move_on_after pattern")

    # This pattern allows "soft cancellation" without exceptions
    async def monitored_task(task_id: int, duration: float):
        """Task that can be cancelled via move_on_after."""
        cancel = Cancellable(name=f"monitored_task_{task_id}", register_globally=True)

        # Use move_on_after for soft cancellation
        with anyio.move_on_after(duration) as scope:
            async with cancel:
                for i in range(10):  # Long running task
                    await cancel.report_progress(f"Task {task_id}: step {i + 1}")
                    await anyio.sleep(0.5)

                    # Check if we're cancelled
                    if scope.cancelled_caught:
                        print(f"  Task {task_id}: Timed out")
                        return

                print(f"  Task {task_id}: Completed")

    # Run tasks with different timeouts
    async with anyio.create_task_group() as tg:
        tg.start_soon(monitored_task, 1, 3.0)  # Will complete
        tg.start_soon(monitored_task, 2, 1.5)  # Will timeout
        tg.start_soon(monitored_task, 3, 10.0)  # Will complete

        # Monitor registry while tasks run
        await anyio.sleep(0.5)
        ops = await registry.list_operations()
        print(f"\n  Active operations: {len(ops)}")
        for op in ops:
            print(f"    - {op.name}: {op.status.value}")

        # Wait for completion
        await anyio.sleep(3.5)

    # Show final results
    print("\n  Final results:")
    history = await registry.get_history()
    for op in history:
        print(f"    - {op.name}: {op.status.value} (duration: {op.duration_seconds:.1f}s)")

    await registry.clear_all()


async def example_with_timeout_helper():
    """Example: Using the with_timeout helper."""
    print("\n=== with_timeout Helper Example ===")

    async def fetch_data():
        """Simulate data fetching."""
        await anyio.sleep(1.0)
        return {"data": "example"}

    try:
        # This will succeed
        result = await with_timeout(2.0, fetch_data())
        print(f"  Success: {result}")

        # This will timeout
        result = await with_timeout(0.5, fetch_data())
        print(f"  Success: {result}")

    except anyio.get_cancelled_exc_class():
        print("  Operation timed out!")


async def main():
    """Run all examples."""
    print("Async Cancellation System - Basic Examples")
    print("=========================================")

    examples = [
        example_timeout,
        #example_manual_cancellation,
        #example_stream_processing,
        #example_decorated_function,
        #example_combined_cancellation,
        #example_shielded_operations,
        #example_operation_registry,
        #example_with_timeout_helper,
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"  Example failed: {e}")
        print()  # Empty line between examples


if __name__ == "__main__":
    anyio.run(main)
