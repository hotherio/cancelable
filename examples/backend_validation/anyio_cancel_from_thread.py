#!/usr/bin/env python3
"""
Example: Demonstrates LIMITATION in current anyio-based implementation.

IMPORTANT FINDING: The current anyio-based implementation does NOT support
true thread-based cancellation from regular Python threads because:
1. CancellationToken.cancel() is async-only (no sync method)
2. anyio.from_thread.run_sync() only works in anyio worker threads
3. Regular Python threads cannot directly cancel operations

This example shows async task-to-task cancellation which DOES work.
For true thread cancellation, we would need a thread-safe sync cancel method.
"""

import time

import anyio

from hother.cancelable import Cancellable, CancellationToken, CancellationReason


async def main():
    """Main async function demonstrating async-to-async cancellation."""
    print("=== Anyio: Async Task Cancellation (Not Thread-Based) ===\n")
    print("Note: This shows task-to-task cancellation, NOT thread cancellation\n")

    # Create a shared cancellation token
    token = CancellationToken()

    # Create async function that will cancel the operation
    async def cancel_after_delay():
        """Cancel the token after 2 seconds."""
        await anyio.sleep(2.0)
        print("[Canceller] Cancelling operation...")
        await token.cancel(CancellationReason.MANUAL, "Cancelled from canceller task")
        print("[Canceller] Cancel signal sent")

    # Run both the worker and cancellation task concurrently
    async with anyio.create_task_group() as tg:
        # Start the cancellation task
        tg.start_soon(cancel_after_delay)

        # Run the cancellable operation
        async def run_operation():
            try:
                async with Cancellable.with_token(token, name="thread_cancelable") as cancel:
                    cancel.on_cancel(lambda ctx: print(f"[Callback] Operation cancelled: {ctx.cancel_reason}"))

                    print("[Worker] Starting long operation...")
                    for i in range(10):
                        await anyio.sleep(0.5)
                        print(f"[Worker] Working... {i + 1}/10")

                    print("[Worker] Operation completed successfully")

            except anyio.get_cancelled_exc_class():
                print(f"[Worker] Operation was cancelled!")
                print(f"[Worker] Status: {cancel.context.status}")
                print(f"[Worker] Reason: {cancel.context.cancel_reason}")
                print(f"[Worker] Message: {cancel.context.cancel_message}")

        tg.start_soon(run_operation)

    print("\n✅ Async task cancellation successful!")
    print("\n" + "="*60)
    print("IMPORTANT FINDING: Thread-based cancellation from regular")
    print("Python threads is NOT supported by the current implementation")
    print("because CancellationToken.cancel() is async-only.")
    print("="*60)


if __name__ == "__main__":
    anyio.run(main)
