#!/usr/bin/env python3
"""
Signal-based cancelation example.

This example demonstrates how to use Unix signals for cancelation,
including SIGINT (Ctrl+C), SIGTERM, custom signals, and signal chaining.
"""

import asyncio
import os
import signal
import time
from typing import Any

from hother.cancelable import Cancelable


async def main():
    """Run all signal handling examples."""

    # Note: Some examples require sending signals from another terminal
    pid = os.getpid()
    print("Note: For full testing, you may need to send signals from another terminal:")
    print(f"  kill -INT {pid}    # Send SIGINT")
    print(f"  kill -TERM {pid}   # Send SIGTERM")
    print(f"  kill -USR1 {pid}   # Send SIGUSR1 (for custom handler example)")
    print()

    # Example 1: Basic signal-based cancelation with SIGINT

    async with Cancelable.with_signal(signal.SIGINT, name="sigint_handler") as cancel:
        print(f"Started signal handler: {cancel.context.id}")
        print("Press Ctrl+C to cancel this operation")

        try:
            for i in range(100):
                await cancel.report_progress(f"Processing item {i + 1}/100")
                await asyncio.sleep(0.2)

            print("Processing completed without interruption")

        except asyncio.CancelledError:
            print("Operation was cancelled by SIGINT")

    # Example 2: Handling multiple signals
    print("\nMultiple Signals Example")
    print("=" * 40)

    # Handle both SIGINT and SIGTERM
    async with Cancelable.with_signal(signal.SIGINT, signal.SIGTERM, name="multi_signal_handler") as cancel:
        print(f"Started multi-signal handler: {cancel.context.id}")
        print("Send SIGINT (Ctrl+C) or SIGTERM to cancel")

        try:
            for i in range(50):
                await cancel.report_progress(f"Multi-signal processing {i + 1}/50")
                await asyncio.sleep(0.3)

            print("Multi-signal processing completed")

        except asyncio.CancelledError:
            print(f"Operation cancelled by signal: {cancel.context.cancel_reason}")

    # Example 3: Combining signal handling with timeout
    print("\nSignal with Timeout Example")
    print("=" * 40)

    # Combine signal handling with timeout
    signal_cancel = Cancelable.with_signal(signal.SIGINT, name="signal_part")
    timeout_cancel = Cancelable.with_timeout(8.0, name="timeout_part")

    async with signal_cancel.combine(timeout_cancel) as cancel:
        print(f"Started signal+timeout handler: {cancel.context.id}")
        print("Press Ctrl+C to cancel immediately, or wait 8 seconds for timeout")

        start_time = time.time()
        try:
            for i in range(50):
                elapsed = time.time() - start_time
                await cancel.report_progress(f"Signal/timeout processing {i + 1}/50 (elapsed: {elapsed:.1f}s)")
                await asyncio.sleep(0.2)

            print("Signal/timeout processing completed")

        except asyncio.CancelledError:
            elapsed = time.time() - start_time
            print(f"Operation cancelled after {elapsed:.1f}s by: {cancel.context.cancel_reason}")

    # Example 4: Graceful shutdown with signal handling
    print("\nGraceful Shutdown Example")
    print("=" * 40)

    shutdown_requested = False

    def request_shutdown():
        nonlocal shutdown_requested
        shutdown_requested = True

    async with Cancelable.with_signal(signal.SIGINT, signal.SIGTERM, name="graceful_shutdown") as cancel:
        print(f"Started graceful shutdown handler: {cancel.context.id}")
        print("Press Ctrl+C for graceful shutdown")

        try:
            for i in range(100):
                if shutdown_requested:
                    await cancel.report_progress("Shutdown requested, cleaning up...")
                    # Simulate cleanup time
                    for cleanup_step in range(5):
                        await cancel.report_progress(f"Cleanup step {cleanup_step + 1}/5")
                        await asyncio.sleep(0.1)
                    break

                await cancel.report_progress(f"Normal processing {i + 1}/100")
                await asyncio.sleep(0.1)

                # Simulate periodic cleanup checks
                if i % 20 == 19:
                    request_shutdown()  # Simulate external shutdown request

            print("Graceful shutdown completed")

        except asyncio.CancelledError:
            print("Immediate cancelation requested - fast shutdown")
            # In a real application, you might do minimal cleanup here

    # Example 5: Signal chaining with parent/child operations
    print("\nSignal Chaining Example")
    print("=" * 40)

    # Parent operation that handles signals
    async with Cancelable.with_signal(signal.SIGINT, name="parent_signal_handler") as parent_cancel:
        print(f"Started parent signal handler: {parent_cancel.context.id}")

        # Child operations that inherit cancelation
        async def child_task(task_id: int):
            async with Cancelable(name=f"child_task_{task_id}", parent=parent_cancel) as child_cancel:
                try:
                    for i in range(10):
                        await child_cancel.report_progress(f"Child {task_id} processing {i + 1}/10")
                        await asyncio.sleep(0.1)
                    return f"child_{task_id}_completed"
                except asyncio.CancelledError:
                    return f"child_{task_id}_cancelled"

        # Run multiple child tasks
        tasks = [asyncio.create_task(child_task(i)) for i in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        print("Child task results:", [str(r) for r in results])

    # Example 6: Custom signal handlers alongside Cancelable
    print("\nCustom Signal Handler Example")
    print("=" * 40)

    signal_received = False
    signal_count = 0

    def custom_sigusr1_handler(signum: int, frame: Any) -> None:
        nonlocal signal_received, signal_count
        signal_received = True
        signal_count += 1
        print(f"Custom SIGUSR1 handler called (count: {signal_count})")

    # Register custom signal handler
    old_handler = signal.signal(signal.SIGUSR1, custom_sigusr1_handler)

    try:
        async with Cancelable.with_signal(signal.SIGINT, name="custom_signal_demo") as cancel:
            print(f"Started custom signal demo: {cancel.context.id}")
            print("Send SIGUSR1 (kill -USR1 <pid>) for custom handling")
            print("Press Ctrl+C to cancel")

            try:
                for i in range(100):
                    if signal_received:
                        await cancel.report_progress(f"Signal received {signal_count} times")
                        signal_received = False

                    await cancel.report_progress(f"Custom signal demo {i + 1}/100")
                    await asyncio.sleep(0.2)

                print("Custom signal demo completed")

            except asyncio.CancelledError:
                print("Demo cancelled by SIGINT")

    finally:
        # Restore original signal handler
        signal.signal(signal.SIGUSR1, old_handler)


if __name__ == "__main__":
    print("Signal Handling Examples")
    print("========================")
    print()
    print("This example demonstrates various signal-based cancelation patterns:")
    print("- Basic signal handling (SIGINT)")
    print("- Multiple signal handling")
    print("- Signal + timeout combinations")
    print("- Graceful shutdown patterns")
    print("- Signal chaining with parent/child operations")
    print("- Custom signal handlers alongside Cancelable")
    print()
    print("Run with: python examples/02_advanced/08_signal_handling.py")
    print()

    asyncio.run(main())